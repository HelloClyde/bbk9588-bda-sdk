from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

from bda_api_catalog import NOTES, inventory_totals, parse_sdk_defines
from system_bin_probe import APP_PARAM_TABLE_OFF, C200_LOAD_BASE, find_c200


TABLE_SLOTS = {
    "GUI": (0x04, "window/control/draw table"),
    "FS": (0x08, "文件系统表"),
    "SYS": (0x0C, "系统/设备表"),
    "MEM": (0x10, "内存表"),
    "RES": (0x14, "资源/DLX/trace 表"),
}


UNKNOWN_CANDIDATE_NOTES: dict[tuple[str, int], str] = {
    ("FS", 0x064): "已分析为低层 block read support helper；volume/index 和 block 参数依赖内部状态，不公开 wrapper。",
    ("FS", 0x068): "已分析为 file-object block read helper；a3 是内部 file object/descriptor，不公开 wrapper。",
    ("FS", 0x074): "已定位但不公开：FS 内部状态/helper，不是通用 stat/read API。",
    ("FS", 0x080): "已定位但不公开：FS 内部状态/helper，普通 BDA 不应直接调用。",
    ("RES", 0x000): "已分析为 resource manager 全局 reset，普通 BDA 不应公开调用。",
    ("RES", 0x004): "已分析为 resource manager 文件/cache 路径，不是 DLX loader，不公开 wrapper。",
    ("RES", 0x008): "已分析为 resource manager cleanup，会释放全局 buffer/file handle，不公开 wrapper。",
    ("RES", 0x00C): "已分析为 resource descriptor/global state 写入 helper，不公开 wrapper。",
    ("RES", 0x010): "已分析为 resource manager close/cleanup helper，不公开 wrapper。",
    ("RES", 0x040): "已分析为内置 resource/cache 打开路径，失败时可能弹 message box，不公开 wrapper。",
    ("SYS", 0x000): "已分析为 descriptor-driven system resource dispatcher，不是普通 app API。",
    ("SYS", 0x008): "已分析为 10-slot system resource scheduler/tick helper，不公开 wrapper。",
    ("SYS", 0x00C): "已分析为 system resource scheduler helper，含 busy-wait，不公开 wrapper。",
    ("SYS", 0x010): "已分析为 system resource slot state 写入 helper，不公开 wrapper。",
    ("SYS", 0x050): "已确认 ret1/stub，不是 loader 或 runtime init API，不公开 wrapper。",
    ("SYS", 0x054): "已确认 ret1/stub，不是 loader 或 runtime init API，不公开 wrapper。",
    ("SYS", 0x084): "已分析为内部 helper，只调用固定子过程，不是 input reset/init/poll。",
    ("SYS", 0x094): "已分析为 raw audio state 写入 helper，不是 high-level setter/restore。",
}


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def va_to_off(va: int) -> int:
    return va - C200_LOAD_BASE


def in_c200(data: bytes, va: int, size: int = 4) -> bool:
    off = va_to_off(va)
    return 0 <= off <= len(data) - size


def disasm_one(data: bytes, va: int) -> str:
    if not in_c200(data, va, 4):
        return ""
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)
    off = va_to_off(va)
    insns = list(md.disasm(data[off : off + 8], va))
    if not insns:
        return ""
    ins = insns[0]
    return f"{ins.mnemonic} {ins.op_str}".strip()


def read_seed_tables(data: bytes) -> dict[str, int]:
    words = struct.unpack_from("<8I", data, APP_PARAM_TABLE_OFF)
    return {table: words[slot_off // 4] for table, (slot_off, _desc) in TABLE_SLOTS.items()}


def table_entry(data: bytes, table_va: int, offset: int) -> int | None:
    entry_va = table_va + offset
    if not in_c200(data, entry_va, 4):
        return None
    return u32(data, va_to_off(entry_va))


def build_catalog(root: Path, sdk: Path, inventory: Path | None = Path("reverse/reports/bda_inventory.json")) -> dict[str, object]:
    c200 = find_c200(root)
    data = c200.read_bytes()
    seeds = read_seed_tables(data)
    sdk_defs = parse_sdk_defines(sdk)
    rows: list[dict[str, object]] = []
    for (table, offset), names in sorted(sdk_defs.items(), key=lambda item: (item[0][0], item[0][1])):
        table_va = seeds.get(table)
        target = table_entry(data, table_va, offset) if table_va is not None else None
        row = {
            "table": table,
            "table_va": table_va,
            "offset": offset,
            "entry_va": (table_va + offset) if table_va is not None else None,
            "target_va": target,
            "target_in_c200": bool(target is not None and in_c200(data, target)),
            "first_insn": disasm_one(data, target) if target is not None else "",
            "sdk_names": names,
            "note": NOTES.get((table, offset), ""),
        }
        rows.append(row)
    unknown_rows: list[dict[str, object]] = []
    if inventory is not None and inventory.exists():
        totals, apps_by_offset = inventory_totals(inventory)
        for offset, total_calls in totals.most_common(40):
            for table, table_va in seeds.items():
                if (table, offset) in sdk_defs:
                    continue
                target = table_entry(data, table_va, offset)
                if target is None or target == 0 or not in_c200(data, target):
                    continue
                unknown_rows.append(
                    {
                        "table": table,
                        "table_va": table_va,
                        "offset": offset,
                        "entry_va": table_va + offset,
                        "target_va": target,
                        "target_in_c200": True,
                        "first_insn": disasm_one(data, target),
                        "total_calls_same_offset": total_calls,
                        "app_count_same_offset": len(apps_by_offset.get(offset, set())),
                        "candidate_note": UNKNOWN_CANDIDATE_NOTES.get(
                            (table, offset), "未分类 candidate：只能作为 disasm 导航，不能当作 SDK API。"
                        ),
                    }
                )
    return {
        "system_bin": str(c200),
        "c200_load_base": C200_LOAD_BASE,
        "table_seeds": seeds,
        "rows": rows,
        "unknown_candidate_rows": unknown_rows,
    }


def hex_or_blank(value: object) -> str:
    return f"0x{value:08x}" if isinstance(value, int) else ""


def write_markdown(catalog: dict[str, object], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    seeds = catalog["table_seeds"]
    rows = catalog["rows"]
    lines: list[str] = []
    lines.append("# C200 原生 BDA API 表")
    lines.append("")
    lines.append("本表由 `reverse/c200_api_tables.py` 从本地 `C200.bin` 直接读取。")
    lines.append("它把 SDK 中已命名的 table offset 映射到 C200 里的 function pointer 地址，供后续 disasm 和注释使用。")
    lines.append("未命名 candidate 来自原机 BDA inventory 的高频 offset；candidate 只说明某个 table+offset 组合有 C200 function pointer，不等于 ABI 已确认。")
    lines.append("")
    lines.append(f"- C200 加载基址：`0x{int(catalog['c200_load_base']):08x}`")
    lines.append(f"- 固件文件：`{catalog['system_bin']}`")
    lines.append("")
    lines.append("## Runtime Table Seeds")
    lines.append("")
    lines.append("C200 会把 `0x80281680` 处的 8 个 word 复制到 `0x81c00000`，原生 BDA 从这里取得 table pointer。")
    lines.append("")
    lines.append("| Table | Runtime slot | C200 table VA | Notes |")
    lines.append("| --- | ---: | ---: | --- |")
    for table, (slot_off, desc) in TABLE_SLOTS.items():
        lines.append(f"| {table} | `0x81c000{slot_off:02x}` | `{hex_or_blank(seeds.get(table))}` | {desc} |")
    lines.append("")
    lines.append("## SDK Named Entries")
    lines.append("")
    lines.append("| Table | Offset | SDK name | entry VA | function VA | in C200 | first insn | Notes |")
    lines.append("| --- | ---: | --- | ---: | ---: | --- | --- | --- |")
    for row in rows:
        names = ", ".join(f"`{name}`" for name in row["sdk_names"])
        in_fw = "是" if row["target_in_c200"] else "否"
        note = row["note"] or "已有 SDK name，仍需 function-level disasm 确认 ABI。"
        lines.append(
            "| {table} | +0x{offset:03x} | {names} | `{entry}` | `{target}` | {in_fw} | `{insn}` | {note} |".format(
                table=row["table"],
                offset=int(row["offset"]),
                names=names,
                entry=hex_or_blank(row["entry_va"]),
                target=hex_or_blank(row["target_va"]),
                in_fw=in_fw,
                insn=str(row["first_insn"]).replace("|", "\\|"),
                note=note.replace("|", "\\|"),
            )
        )
    lines.append("")
    lines.append("## 使用建议")
    lines.append("")
    lines.append("- `function VA` 可用 `C200_LOAD_BASE=0x80004000` 转换成 file offset：`file_off = va - 0x80004000`。")
    lines.append("- `C200 内=否` 的项可能是 null pointer、外部 RAM table，或当前 offset 并非该表稳定成员，不能直接当作已确认 API。")
    lines.append("- function-level ABI 仍要结合原机 BDA call site、寄存器/stack 参数和真机/emu probe 确认。")
    unknown_rows = catalog.get("unknown_candidate_rows", [])
    if unknown_rows:
        lines.append("")
        lines.append("## Unnamed Hot Offset C200 Candidates")
        lines.append("")
        lines.append("下表读取 inventory 高频 offset，并在尚未命名的 runtime table entry 中查同 offset 的 function pointer。")
        lines.append("因为 inventory 的 offset 统计未区分 table，本表只用于 disasm 导航；同一 offset 在某张 table 已命名，不代表其他 table 的同 offset 也已确认。")
        lines.append("")
        lines.append("| Offset | Raw calls same offset | App count | Candidate table | entry VA | function VA | first insn | Candidate status |")
        lines.append("| ---: | ---: | ---: | --- | ---: | ---: | --- | --- |")
        for row in unknown_rows:
            lines.append(
                "| +0x{offset:03x} | {calls} | {apps} | {table} | `{entry}` | `{target}` | `{insn}` | {note} |".format(
                    offset=int(row["offset"]),
                    calls=int(row["total_calls_same_offset"]),
                    apps=int(row["app_count_same_offset"]),
                    table=row["table"],
                    entry=hex_or_blank(row["entry_va"]),
                    target=hex_or_blank(row["target_va"]),
                    insn=str(row["first_insn"]).replace("|", "\\|"),
                    note=str(row.get("candidate_note", "")).replace("|", "\\|"),
                )
            )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="从 C200.bin 导出原生 BDA runtime API table function pointer。",
        add_help=False,
    )
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("--root", type=Path, default=Path("."), help="仓库根目录")
    ap.add_argument("--sdk", type=Path, default=Path("reverse") / "bda_research_sdk.h", help="SDK header")
    ap.add_argument("--inventory", type=Path, default=Path("reverse") / "reports" / "bda_inventory.json", help="原机 BDA inventory JSON")
    ap.add_argument("-o", "--output", type=Path, default=Path("reverse") / "docs" / "system_api_tables.md", help="输出 Markdown 文件")
    ap.add_argument("--json-out", type=Path, help="可选 JSON 输出路径")
    ns = ap.parse_args()

    catalog = build_catalog(ns.root, ns.sdk, ns.inventory)
    write_markdown(catalog, ns.output)
    if ns.json_out:
        ns.json_out.parent.mkdir(parents=True, exist_ok=True)
        ns.json_out.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2),
            encoding="utf-8",
            newline="\n",
        )
    print(f"system_bin={catalog['system_bin']}")
    print(f"rows={len(catalog['rows'])}")
    print(f"unknown_candidates={len(catalog.get('unknown_candidate_rows', []))}")
    print(f"markdown={ns.output}")


if __name__ == "__main__":
    main()
