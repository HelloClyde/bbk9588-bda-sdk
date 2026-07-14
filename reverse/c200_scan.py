#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN


def u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little")


def find_all(data: bytes, needle: bytes) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            return out
        out.append(pos)
        start = pos + 1


def printable_window(data: bytes, off: int, radius: int = 64) -> str:
    lo = max(0, off - radius)
    hi = min(len(data), off + radius)
    chunk = data[lo:hi]
    return "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)


def disasm_window(data: bytes, off: int, base: int, before: int, after: int) -> str:
    start = max(0, off - before)
    start &= ~3
    end = min(len(data), off + after)
    md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
    lines = []
    for ins in md.disasm(data[start:end], base + start):
        marker = "=>" if start <= off < start + ins.address - (base + start) + 4 else "  "
        lines.append(f"{marker} {ins.address:08x}: {ins.mnemonic:<8} {ins.op_str}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Scan C200.bin for native BDA loader/menu evidence.")
    ap.add_argument("bin", type=Path)
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0x80004000)
    ap.add_argument("--disasm", action="store_true")
    ns = ap.parse_args()

    data = ns.bin.read_bytes()
    needles = {
        "xor_key_44525740": (0x44525740).to_bytes(4, "little"),
        "xor_key_hi_4452": (0x4452).to_bytes(2, "little"),
        "xor_key_lo_5740": (0x5740).to_bytes(2, "little"),
        "xor_key_plus2_5742": (0x5742).to_bytes(2, "little"),
        "app_code_va_81c00020": (0x81C00020).to_bytes(4, "little"),
        "app_code_hi_81c0": (0x81C0).to_bytes(2, "little"),
        "app_code_lo_0020": (0x0020).to_bytes(2, "little"),
        "app_table_81c00000": (0x81C00000).to_bytes(4, "little"),
        "dot_bda_lower": b".bda",
        "dot_bda_upper": b".BDA",
        "BDA": b"BDA",
        "bda": b"bda",
        "shell": b"\\shell\\",
    }

    for name, needle in needles.items():
        hits = find_all(data, needle)
        print(f"{name}: {len(hits)}")
        for off in hits[:40]:
            print(f"  file=0x{off:06x} va=0x{ns.base + off:08x} {printable_window(data, off, 48)}")
            if ns.disasm and name not in {"dot_bda_lower", "dot_bda_upper", "BDA", "bda", "shell"}:
                print(disasm_window(data, off, ns.base, 0x80, 0x100))


if __name__ == "__main__":
    main()
