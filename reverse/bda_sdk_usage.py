from __future__ import annotations

import argparse
import collections
import hashlib
from pathlib import Path

from bda_api_catalog import NOTES, parse_sdk_defines
from bda_api_scan import scan_calls
from bda_layout import analyze
from bda_table_call_scan import find_global_load
from bda_table_globals import detect_globals
from c200_api_tables import disasm_one, in_c200, read_seed_tables, table_entry
from system_bin_probe import find_c200


TABLE_ORDER = {"RES": 0, "GUI": 1, "SYS": 2, "FS": 3, "MEM": 4, "UNKNOWN": 5}

UNEXPOSED_NOTES: dict[tuple[str, int], str] = {
    ("FS", 0x068): "file-object block read helper；a3 是内部 file descriptor，不公开 SDK wrapper。",
    ("SYS", 0x050): "C200 中是立即返回 1 的 stub，不公开 SDK wrapper。",
    ("SYS", 0x054): "C200 中是立即返回 1 的 stub，不公开 SDK wrapper。",
}


def collect_usage(bda: Path) -> tuple[collections.Counter[tuple[str, int]], dict[str, int], int]:
    data = bda.read_bytes()
    layout = analyze(bda)
    entry = int(layout["entry_offset"])
    base = int(layout["runtime_entry_va"]) - entry
    globals_by_name = detect_globals(bda)
    globals_by_addr = {address: name for name, address in globals_by_name.items()}
    counts: collections.Counter[tuple[str, int]] = collections.Counter()

    for call in scan_calls(data, entry, len(data)):
        found = find_global_load(data, call["load_off"], call["base_reg"], globals_by_addr)
        table = found[0] if found else "UNKNOWN"
        counts[(table, int(call["api_offset"]))] += 1

    return counts, globals_by_name, base


def fmt_va(value: int | None) -> str:
    return f"`0x{value:08x}`" if value is not None else "-"


def write_report(
    bda: Path,
    output: Path,
    root: Path,
    sdk: Path,
    title: str | None = None,
) -> dict[str, object]:
    counts, globals_by_name, runtime_base = collect_usage(bda)
    sdk_defs = parse_sdk_defines(sdk)
    c200 = find_c200(root)
    c200_data = c200.read_bytes()
    seeds = read_seed_tables(c200_data)
    digest = hashlib.sha256(bda.read_bytes()).hexdigest()
    report_title = title or bda.name

    table_totals: collections.Counter[str] = collections.Counter()
    table_unique: collections.Counter[str] = collections.Counter()
    for (table, _offset), count in counts.items():
        table_totals[table] += count
        table_unique[table] += 1

    lines = [
        f"# {report_title} runtime API inventory",
        "",
        "本表由 `reverse/bda_sdk_usage.py` 从 BDA 间接调用、SDK header 和 C200 固件函数表直接生成。",
        "它只统计可识别的 runtime table 间接调用；随 BDA 静态链接的 GUI framework/libc 函数不在此表中。",
        "",
        f"- BDA：`{bda}`",
        f"- SHA-256：`{digest}`",
        f"- runtime file base：`0x{runtime_base:08x}`",
        f"- C200：`{c200}`",
        f"- 间接调用总数：{sum(counts.values())}",
        f"- 唯一 table entry：{len(counts)}",
        "",
        "生成命令：",
        "",
        "```powershell",
        f'python reverse\\bda_sdk_usage.py "{bda}" -o "{output}"',
        "```",
        "",
        "## Table 汇总",
        "",
        "| Table | 调用数 | 唯一 entry | BDA table global | C200 table VA |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]

    for table in sorted(table_totals, key=lambda item: TABLE_ORDER.get(item, 99)):
        table_global = globals_by_name.get(table)
        table_va = seeds.get(table)
        lines.append(
            f"| {table} | {table_totals[table]} | {table_unique[table]} | "
            f"{fmt_va(table_global)} | {fmt_va(table_va)} |"
        )

    lines.extend(
        [
            "",
            "## 完整调用表",
            "",
            "`未公开` 表示已识别固件行为但不适合作为通用 SDK API；它不等于未知。",
            "",
            "| Table | Offset | 调用数 | SDK 名称 | C200 function VA | First instruction | 行为 |",
            "| --- | ---: | ---: | --- | ---: | --- | --- |",
        ]
    )

    for (table, offset), count in sorted(
        counts.items(), key=lambda item: (TABLE_ORDER.get(item[0][0], 99), item[0][1])
    ):
        names = sdk_defs.get((table, offset), [])
        sdk_name = ", ".join(f"`{name}`" for name in names)
        if not sdk_name:
            sdk_name = "未公开" if (table, offset) in UNEXPOSED_NOTES else "未命名"

        table_va = seeds.get(table)
        target = table_entry(c200_data, table_va, offset) if table_va is not None else None
        target_va = target if target is not None and target != 0 else None
        first_insn = disasm_one(c200_data, target_va) if target_va is not None and in_c200(c200_data, target_va) else ""
        note = NOTES.get((table, offset), UNEXPOSED_NOTES.get((table, offset), "需要继续确认 ABI。"))
        note = note.replace("|", "\\|")
        first_insn = first_insn.replace("|", "\\|")
        lines.append(
            f"| {table} | +0x{offset:03x} | {count} | {sdk_name} | {fmt_va(target_va)} | "
            f"`{first_insn}` | {note} |"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "calls": sum(counts.values()),
        "unique_entries": len(counts),
        "output": output,
        "sha256": digest,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="生成单个原机 BDA 的 runtime API/SDK/C200 对照表。",
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("bda", type=Path, help="要分析的 BDA 文件")
    ap.add_argument("--root", type=Path, default=Path("."), help="仓库根目录")
    ap.add_argument("--sdk", type=Path, default=Path("sdk") / "api" / "bda_sdk.h", help="SDK header")
    ap.add_argument("--title", help="报告标题；默认使用 BDA 文件名")
    ap.add_argument("-o", "--output", type=Path, required=True, help="输出 Markdown")
    ns = ap.parse_args()

    result = write_report(ns.bda, ns.output, ns.root, ns.sdk, ns.title)
    print(f"calls={result['calls']}")
    print(f"unique_entries={result['unique_entries']}")
    print(f"sha256={result['sha256']}")
    print(f"output={result['output']}")


if __name__ == "__main__":
    main()
