from __future__ import annotations

import argparse
import collections
import struct
from pathlib import Path

from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

from bda_api_scan import scan_calls
from bda_layout import analyze
from bda_table_globals import detect_globals


REGS = [
    "$zero", "$at", "$v0", "$v1", "$a0", "$a1", "$a2", "$a3",
    "$t0", "$t1", "$t2", "$t3", "$t4", "$t5", "$t6", "$t7",
    "$s0", "$s1", "$s2", "$s3", "$s4", "$s5", "$s6", "$s7",
    "$t8", "$t9", "$k0", "$k1", "$gp", "$sp", "$fp", "$ra",
]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def decode_i(word: int) -> tuple[int, int, int, int]:
    return (word >> 26) & 0x3F, (word >> 21) & 0x1F, (word >> 16) & 0x1F, word & 0xFFFF


def adjusted_hi(value: int) -> int:
    return ((value + 0x8000) >> 16) & 0xFFFF


def find_global_load(data: bytes, off: int, reg: int, globals_by_addr: dict[int, str]) -> tuple[str, int] | None:
    start = max(0, off - 0x50)
    for pos in range(off - 4, start - 1, -4):
        word = u32(data, pos)
        op, rs, rt, imm = decode_i(word)
        if op != 0x23 or rt != reg:  # lw reg, imm(base)
            continue
        for lui_pos in range(pos - 4, max(0, pos - 0x30) - 1, -4):
            lui = u32(data, lui_pos)
            lui_op, _lui_rs, lui_rt, lui_imm = decode_i(lui)
            if lui_op != 0x0F or lui_rt != rs:
                continue
            addr = ((lui_imm << 16) + s16(imm)) & 0xFFFFFFFF
            name = globals_by_addr.get(addr)
            if name:
                return name, addr
    return None


def disasm_context(data: bytes, base: int, off: int, size: int = 0x58) -> list[str]:
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)
    start = max(0, off - 0x18) & ~3
    end = min(len(data), start + size)
    return [
        f"{ins.address:08x}: {ins.mnemonic:<8} {ins.op_str}"
        for ins in md.disasm(data[start:end], base + start)
    ]


def parse_global(items: list[str]) -> dict[int, str]:
    result = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"bad --global item {item!r}; use NAME=0xADDR")
        name, value = item.split("=", 1)
        result[int(value, 0)] = name
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Classify indirect BDA API calls by the table global that feeds them.")
    ap.add_argument("bda", type=Path)
    ap.add_argument("--base", type=lambda x: int(x, 0), default=None)
    ap.add_argument("--global", dest="globals", action="append", default=[])
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--context", action="store_true")
    ap.add_argument("--table", default=None, help="Only print samples/counts for this table name, e.g. FS.")
    ap.add_argument("--offset", type=lambda x: int(x, 0), default=None, help="Only print samples/counts for this API offset.")
    ns = ap.parse_args()

    data = ns.bda.read_bytes()
    layout = analyze(ns.bda)
    entry = int(layout["entry_offset"])
    base = ns.base
    if base is None:
        base = int(layout["runtime_entry_va"]) - entry

    globals_by_addr = parse_global(ns.globals)
    if not globals_by_addr:
        detected = detect_globals(ns.bda)
        globals_by_addr = {addr: name for name, addr in detected.items()}
    if not globals_by_addr:
        globals_by_addr = {
            0x81C20470: "RES",
            0x81C20474: "GUI",
            0x81C20478: "SYS",
            0x81C2047C: "FS",
            0x81C20480: "MEM",
        }

    rows = []
    for call in scan_calls(data, entry, len(data)):
        found = find_global_load(data, call["load_off"], call["base_reg"], globals_by_addr)
        table = found[0] if found else "UNKNOWN"
        rows.append({**call, "table": table})

    if ns.table is not None:
        rows = [row for row in rows if row["table"] == ns.table]
    if ns.offset is not None:
        rows = [row for row in rows if row["api_offset"] == ns.offset]

    counts = collections.Counter((row["table"], row["api_offset"]) for row in rows)
    print(f"{ns.bda} base=0x{base:08x} calls={len(rows)}")
    for (table, api_off), count in sorted(counts.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        print(f"{table:7s} +0x{api_off:03x}: {count}")

    print("\nsamples:")
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[(row["table"], row["api_offset"])].append(row)
    for key in sorted(grouped):
        for row in grouped[key][: ns.samples]:
            va = base + row["load_off"]
            print(
                f"{row['table']:7s} +0x{row['api_offset']:03x} "
                f"file=0x{row['load_off']:06x} va=0x{va:08x} "
                f"base={REGS[row['base_reg']]} target={REGS[row['target_reg']]}"
            )
            if ns.context:
                for line in disasm_context(data, base, row["load_off"]):
                    print(f"  {line}")


if __name__ == "__main__":
    main()
