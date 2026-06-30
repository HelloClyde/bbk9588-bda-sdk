from __future__ import annotations

import argparse
import re
import struct
from pathlib import Path


COMMON_MIPS = {
    "addiu",
    "addu",
    "and",
    "andi",
    "beq",
    "beqz",
    "bgez",
    "bgtz",
    "blez",
    "bltz",
    "bne",
    "bnez",
    "j",
    "jal",
    "jalr",
    "jr",
    "lbu",
    "lhu",
    "ll",
    "lui",
    "lw",
    "move",
    "nop",
    "or",
    "ori",
    "sb",
    "sll",
    "slt",
    "slti",
    "sra",
    "srl",
    "subu",
    "sw",
    "xor",
    "xori",
}


def strings(data: bytes, min_len: int = 5) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for m in re.finditer(rb"[\x20-\x7e]{%d,}" % min_len, data):
        out.append((m.start(), m.group().decode("ascii", "replace")))
    return out


def mips_score(words: tuple[int, ...]) -> int:
    score = 0
    for w in words:
        op = (w >> 26) & 0x3F
        funct = w & 0x3F
        if op in {0x02, 0x03, 0x04, 0x05, 0x08, 0x09, 0x0A, 0x0B, 0x0D, 0x0F, 0x20, 0x23, 0x24, 0x25, 0x28, 0x2B}:
            score += 1
        elif op == 0 and funct in {0x00, 0x02, 0x03, 0x08, 0x09, 0x21, 0x23, 0x24, 0x25, 0x2A}:
            score += 1
    return score


def find_mips_windows(data: bytes, limit: int = 0x20000) -> list[tuple[int, int]]:
    hits: list[tuple[int, int]] = []
    end = min(len(data) - 1024, limit)
    for off in range(0, max(0, end), 4):
        words = struct.unpack_from("<256I", data, off)
        score = mips_score(words)
        if score >= 205:
            hits.append((off, score))
    collapsed: list[tuple[int, int]] = []
    for off, score in hits:
        if collapsed and off - collapsed[-1][0] <= 0x40:
            if score > collapsed[-1][1]:
                collapsed[-1] = (off, score)
        else:
            collapsed.append((off, score))
    return collapsed[:16]


def signed16(v: int) -> int:
    return v - 0x10000 if v & 0x8000 else v


def materialized_addresses(data: bytes, start: int = 0x9000, end: int | None = None) -> list[tuple[int, int]]:
    end = min(len(data) - 4, end or len(data))
    last_lui: dict[int, tuple[int, int]] = {}
    out: list[tuple[int, int]] = []
    for off in range(start, max(start, end), 4):
        (w,) = struct.unpack_from("<I", data, off)
        op = (w >> 26) & 0x3F
        rt = (w >> 16) & 0x1F
        rs = (w >> 21) & 0x1F
        imm = w & 0xFFFF
        if op == 0x0F:
            last_lui[rt] = (off, imm << 16)
        elif op in {0x09, 0x0D} and rs == rt and rs in last_lui:
            _, high = last_lui[rs]
            low = signed16(imm) if op == 0x09 else imm
            addr = (high + low) & 0xFFFFFFFF
            if 0x81000000 <= addr <= 0x82000000:
                out.append((off, addr))
    return out


def infer_load_base(data: bytes) -> list[tuple[int, int]]:
    ascii_offsets = [off for off, _ in strings(data, 5)]
    addrs = materialized_addresses(data)
    counts: dict[int, int] = {}
    for _, addr in addrs:
        for off in ascii_offsets:
            base = addr - off
            if 0x81BE0000 <= base <= 0x81C00000:
                counts[base] = counts.get(base, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:8]


def analyze(path: Path) -> None:
    data = path.read_bytes()
    words = struct.unpack_from("<16I", data + b"\0" * 64)
    print(f"\n== {path} ({len(data)} bytes)")
    print("header_words:", " ".join(f"{w:08X}" for w in words))
    print("mips_windows:", ", ".join(f"0x{o:X}:{s}" for o, s in find_mips_windows(data)) or "-")
    bases = infer_load_base(data)
    print("load_base_candidates:", ", ".join(f"0x{b:X}:{n}" for b, n in bases) or "-")
    interesting = []
    for off, s in strings(data):
        low = s.lower()
        if any(k in low for k in ("www.eebbk.com", "\\shell\\", "malloc", "main", "wndproc", "bbasic", "gameboy")):
            interesting.append((off, s))
    for off, s in interesting[:24]:
        print(f"str 0x{off:06X}: {s[:100]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe BBK .bda application files.")
    ap.add_argument("paths", nargs="+", type=Path)
    ns = ap.parse_args()
    for p in ns.paths:
        if p.is_dir():
            for child in sorted(p.glob("*.bda")):
                analyze(child)
        else:
            analyze(p)


if __name__ == "__main__":
    main()
