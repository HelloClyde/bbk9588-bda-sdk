#!/usr/bin/env python3
"""Scan a BDA-like binary for printable strings and embedded VX resources."""

from __future__ import annotations

import argparse
from pathlib import Path


def rd32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little")


def iter_ascii_strings(data: bytes, min_len: int = 2):
    start = None
    buf = bytearray()
    for i, b in enumerate(data):
        ok = b in (9, 10, 13) or 0x20 <= b <= 0x7E
        if ok:
            if start is None:
                start = i
            buf.append(b)
            continue
        if start is not None and len(buf) >= min_len:
            yield start, bytes(buf).decode("ascii", errors="replace")
        start = None
        buf.clear()
    if start is not None and len(buf) >= min_len:
        yield start, bytes(buf).decode("ascii", errors="replace")


def iter_vx(data: bytes):
    off = 0
    while True:
        off = data.find(b"VX", off)
        if off < 0:
            return
        if off + 0x18 <= len(data):
            width = rd32(data, off + 6)
            height = rd32(data, off + 10)
            size = 0x18 + width * height * 2
            if 0 < width <= 1024 and 0 < height <= 1024 and off + size <= len(data):
                yield off, width, height, size
        off += 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--min-len", type=int, default=2)
    args = ap.parse_args()

    data = args.path.read_bytes()
    print(f"path={args.path}")
    print("interesting ASCII strings:")
    for off, s in iter_ascii_strings(data, args.min_len):
        interesting = (
            "\\" in s
            or "/" in s
            or "." in s
            or "%" in s
            or s.lower() in {"rb", "wb", "wb+", "rbf", "mp3", "wav"}
            or len(s) >= 6
        )
        if interesting:
            print(f"0x{off:x}: {s!r}")
    print("VX hits:")
    for off, width, height, size in iter_vx(data):
        print(f"0x{off:x}: {width}x{height} size=0x{size:x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
