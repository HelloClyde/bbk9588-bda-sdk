#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


def strings_gbk(data: bytes, min_len: int = 4) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    start = None
    for i, b in enumerate(data + b"\0"):
        if b != 0:
            if start is None:
                start = i
        elif start is not None:
            chunk = data[start:i]
            if len(chunk) >= min_len:
                for enc in ("gbk", "ascii"):
                    try:
                        s = chunk.decode(enc)
                    except UnicodeDecodeError:
                        continue
                    if any(ch.isprintable() for ch in s):
                        out.append((start, s))
                        break
            start = None
    return out


def main() -> None:
    p = Path("\u7cfb\u7edf") / "\u6570\u636e" / "Config.inf"
    data = p.read_bytes()
    print(f"path={p} size={len(data)}")
    print("first_words:")
    for off in range(0, min(0x40, len(data)), 4):
        print(f"  {off:04x}: {int.from_bytes(data[off:off+4], 'little'):08x}")
    print("strings:")
    for off, s in strings_gbk(data):
        print(f"  0x{off:04x}: {s}")


if __name__ == "__main__":
    main()
