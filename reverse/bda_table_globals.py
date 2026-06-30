from __future__ import annotations

import argparse
import struct
from pathlib import Path

from bda_layout import analyze


TABLE_NAMES = ("GUI", "FS", "SYS", "MEM", "RES")
RUNTIME_TABLE_ADDRS = {
    0x81C00004: "GUI",
    0x81C00008: "FS",
    0x81C0000C: "SYS",
    0x81C00010: "MEM",
    0x81C00014: "RES",
}


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def s16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def decode_i(word: int) -> tuple[int, int, int, int]:
    return (word >> 26) & 0x3F, (word >> 21) & 31, (word >> 16) & 31, word & 0xFFFF


def find_runtime_loads(data: bytes, entry: int, base: int, span: int) -> list[tuple[int, int, str, int]]:
    loads = []
    reg_values: dict[int, int] = {}
    for off in range(entry, min(len(data) - 4, entry + span), 4):
        word = u32(data, off)
        op, rs, rt, imm = decode_i(word)
        if op == 0x0F:  # lui
            reg_values[rt] = (imm << 16) & 0xFFFFFFFF
            continue
        if op == 0x23 and rs in reg_values:  # lw
            addr = (reg_values[rs] + s16(imm)) & 0xFFFFFFFF
            name = RUNTIME_TABLE_ADDRS.get(addr)
            if name:
                loads.append((off, rt, name, addr))
    return loads


def find_store_after(data: bytes, start: int, reg: int, limit: int = 0x40) -> tuple[int, int] | None:
    reg_values: dict[int, int] = {}
    for off in range(start + 4, min(len(data) - 4, start + limit), 4):
        word = u32(data, off)
        op, rs, rt, imm = decode_i(word)
        if op == 0x0F:
            reg_values[rt] = (imm << 16) & 0xFFFFFFFF
            continue
        if op == 0x2B and rt == reg and rs in reg_values:  # sw reg, imm(base)
            return off, (reg_values[rs] + s16(imm)) & 0xFFFFFFFF
    return None


def detect_globals(path: Path, span: int = 0x180) -> dict[str, int]:
    data = path.read_bytes()
    layout = analyze(path)
    entry = int(layout["entry_offset"])
    base = int(layout["runtime_entry_va"]) - entry
    result: dict[str, int] = {}
    for off, reg, name, _runtime_addr in find_runtime_loads(data, entry, base, span):
        stored = find_store_after(data, off, reg)
        if stored:
            _store_off, global_addr = stored
            result[name] = global_addr
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Detect BDA globals that cache runtime API table pointers.")
    ap.add_argument("bda", nargs="+", type=Path)
    ns = ap.parse_args()

    for path in ns.bda:
        globals_by_name = detect_globals(path)
        print(path)
        for name in TABLE_NAMES:
            value = globals_by_name.get(name)
            if value is not None:
                print(f"  {name}=0x{value:08x}")
        if globals_by_name:
            args = " ".join(f"--global {name}=0x{globals_by_name[name]:08x}" for name in TABLE_NAMES if name in globals_by_name)
            print(f"  scan args: {args}")


if __name__ == "__main__":
    main()
