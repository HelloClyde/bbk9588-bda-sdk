#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


KEY = 0x44525740


def find_all(data: bytes, needle: bytes) -> list[int]:
    out = []
    start = 0
    while needle:
        pos = data.find(needle, start)
        if pos < 0:
            return out
        out.append(pos)
        start = pos + 1
    return out


def gbk_title(data: bytes) -> bytes:
    return data[0x2C:0x3C].split(b"\0", 1)[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Look for duplicate identity fields inside a BDA.")
    ap.add_argument("bda", type=Path, nargs="+")
    ns = ap.parse_args()

    for p in ns.bda:
        data = p.read_bytes()
        title = gbk_title(data)
        cat = int.from_bytes(data[0x0C:0x10], "little") ^ KEY
        size_dec = int.from_bytes(data[0x10:0x14], "little") ^ KEY
        print(f"\n== {p} size={len(data)} cat=0x{cat:x} enc_size={size_dec} title={title.hex()}")
        for label, needle in [
            ("title", title),
            ("raw_cat_word", data[0x0C:0x10]),
            ("enc_size_word", data[0x10:0x14]),
            ("raw_header_0x00_0x2c", data[:0x2C]),
            ("raw_header_0x00_0x40", data[:0x40]),
        ]:
            hits = find_all(data, needle)
            hits2 = [h for h in hits if h != 0 and not (label == "title" and h == 0x2C)]
            print(f"  {label}: total={len(hits)} other={[hex(h) for h in hits2[:20]]}")


if __name__ == "__main__":
    main()
