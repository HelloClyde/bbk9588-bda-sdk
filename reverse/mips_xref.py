#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN


REGS = [
    "$zero",
    "$at",
    "$v0",
    "$v1",
    "$a0",
    "$a1",
    "$a2",
    "$a3",
    "$t0",
    "$t1",
    "$t2",
    "$t3",
    "$t4",
    "$t5",
    "$t6",
    "$t7",
    "$s0",
    "$s1",
    "$s2",
    "$s3",
    "$s4",
    "$s5",
    "$s6",
    "$s7",
    "$t8",
    "$t9",
    "$k0",
    "$k1",
    "$gp",
    "$sp",
    "$fp",
    "$ra",
]


def s16(x: int) -> int:
    return x - 0x10000 if x & 0x8000 else x


def u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little")


def decode_i(word: int) -> tuple[int, int, int, int]:
    op = (word >> 26) & 0x3F
    rs = (word >> 21) & 0x1F
    rt = (word >> 16) & 0x1F
    imm = word & 0xFFFF
    return op, rs, rt, imm


def disasm(data: bytes, base: int, off: int, size: int = 0x160) -> str:
    md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
    start = max(0, off) & ~3
    end = min(len(data), start + size)
    return "\n".join(
        f"{ins.address:08x}: {ins.mnemonic:<8} {ins.op_str}"
        for ins in md.disasm(data[start:end], base + start)
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Find simple MIPS lui/addiu/ori references to an address.")
    ap.add_argument("bin", type=Path)
    ap.add_argument("target", type=lambda x: int(x, 0))
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0x80000000)
    ns = ap.parse_args()

    data = ns.bin.read_bytes()
    hi_values = {((ns.target >> 16) & 0xFFFF), (((ns.target + 0x8000) >> 16) & 0xFFFF)}
    hits: list[tuple[int, str, int]] = []

    for off in range(0, len(data) - 8, 4):
        w = u32(data, off)
        op, _rs, rt, imm = decode_i(w)
        if op != 0x0F or imm not in hi_values:  # lui rt, adjusted hi
            continue
        for j in range(off + 4, min(off + 0x40, len(data) - 4), 4):
            w2 = u32(data, j)
            op2, rs2, rt2, imm2 = decode_i(w2)
            if rs2 != rt:
                continue
            val_addiu = ((imm << 16) + s16(imm2)) & 0xFFFFFFFF
            val_ori = (imm << 16) | imm2
            if op2 == 0x09 and abs((val_addiu - ns.target) & 0xFFFFFFFF) < 0x200:
                hits.append((off, f"{REGS[rt]} addiu -> 0x{val_addiu:08x}", j))
            if op2 == 0x0D and abs((val_ori - ns.target) & 0xFFFFFFFF) < 0x200:
                hits.append((off, f"{REGS[rt]} ori -> 0x{val_ori:08x}", j))

    print(f"target=0x{ns.target:08x} hits={len(hits)}")
    for off, why, use_off in hits[:80]:
        print(f"\nfile=0x{off:06x} va=0x{ns.base + off:08x} use=0x{ns.base + use_off:08x} {why}")
        print(disasm(data, ns.base, max(0, off - 0x40), 0x120))


if __name__ == "__main__":
    main()
