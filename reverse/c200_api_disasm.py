from __future__ import annotations

import argparse
from pathlib import Path
import sys

from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

from c200_api_tables import UNKNOWN_CANDIDATE_NOTES, build_catalog, in_c200, table_entry, va_to_off


def find_row(catalog: dict[str, object], name: str | None, table: str | None, offset: int | None) -> dict[str, object]:
    rows = catalog["rows"]
    if name is not None:
        for row in rows:
            if name in row["sdk_names"]:
                return row
        raise SystemExit(f"未找到 SDK 名称：{name}")
    if table is None or offset is None:
        raise SystemExit("需要传 --name，或同时传 --table 和 --offset")
    table = table.upper()
    for row in rows:
        if row["table"] == table and int(row["offset"]) == offset:
            return row
    for row in catalog.get("unknown_candidate_rows", []):
        if row["table"] == table and int(row["offset"]) == offset:
            row = dict(row)
            row.setdefault("sdk_names", [])
            return row
    seeds = catalog["table_seeds"]
    table_va = seeds.get(table)
    if not isinstance(table_va, int):
        raise SystemExit(f"未知表：{table}")
    c200_path = Path(str(catalog["system_bin"]))
    target = table_entry(c200_path.read_bytes(), table_va, offset)
    if target is None:
        raise SystemExit(f"表项超出 C200 映像：{table}+0x{offset:x}")
    return {
        "table": table,
        "table_va": table_va,
        "offset": offset,
        "entry_va": table_va + offset,
        "target_va": target,
        "sdk_names": [],
        "target_in_c200": in_c200(c200_path.read_bytes(), target),
        "candidate_note": UNKNOWN_CANDIDATE_NOTES.get(
            (table, offset), "未分类 candidate：只能作为 disasm 导航，不能当作 SDK API。"
        ),
    }


def disasm_function(data: bytes, va: int, size: int) -> list[str]:
    if not in_c200(data, va, 4):
        raise SystemExit(f"函数地址不在 C200 映像内：0x{va:08x}")
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)
    off = va_to_off(va)
    lines: list[str] = []
    for ins in md.disasm(data[off : off + size], va):
        lines.append(f"{ins.address:08x}: {ins.mnemonic:<8} {ins.op_str}")
    return lines


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(
        description="按 SDK 名称、表 offset 或 VA 反汇编 C200 里的 BDA API 函数。",
        add_help=False,
    )
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("--root", type=Path, default=Path("."), help="仓库根目录")
    ap.add_argument("--sdk", type=Path, default=Path("reverse") / "bda_research_sdk.h", help="SDK 头文件")
    ap.add_argument("--name", help="SDK 宏名，例如 BDA_GUI_MSGBOX")
    ap.add_argument("--table", choices=["GUI", "FS", "SYS", "MEM", "RES"], help="API 表名")
    ap.add_argument("--offset", type=lambda text: int(text, 0), help="表内 offset，例如 0x2b8")
    ap.add_argument("--va", type=lambda text: int(text, 0), help="直接反汇编 C200 内函数 VA，例如 0x8017e1a0")
    ap.add_argument("--size", type=lambda text: int(text, 0), default=0x180, help="反汇编字节数")
    ns = ap.parse_args()

    catalog = build_catalog(ns.root, ns.sdk)
    c200_path = Path(str(catalog["system_bin"]))
    data = c200_path.read_bytes()

    if ns.va is not None:
        if ns.name is not None or ns.table is not None or ns.offset is not None:
            raise SystemExit("--va 不能和 --name/--table/--offset 同时使用")
        target = ns.va
        print(f"system_bin={c200_path}")
        print("table=(direct) offset=(direct)")
        print("sdk_names=(direct)")
        print("entry_va=(direct)")
        print(f"target_va=0x{target:08x}")
        print(f"file_off=0x{va_to_off(target):x}")
        print(f"target_in_c200={'yes' if in_c200(data, target) else 'no'}")
        print()
        print("\n".join(disasm_function(data, target, ns.size)))
        return

    row = find_row(catalog, ns.name, ns.table, ns.offset)
    target = row["target_va"]
    if not isinstance(target, int):
        raise SystemExit("该表项没有函数地址")

    print(f"system_bin={c200_path}")
    print(f"table={row['table']} offset=+0x{int(row['offset']):03x}")
    names = row.get("sdk_names", [])
    print(f"sdk_names={', '.join(names) if names else '(未命名)'}")
    print(f"entry_va=0x{int(row['entry_va']):08x}")
    print(f"target_va=0x{target:08x}")
    print(f"file_off=0x{va_to_off(target):x}")
    print(f"target_in_c200={'yes' if row.get('target_in_c200') else 'no'}")
    note = row.get("note")
    if note:
        print(f"note={note}")
    print()
    print("\n".join(disasm_function(data, target, ns.size)))


if __name__ == "__main__":
    main()
