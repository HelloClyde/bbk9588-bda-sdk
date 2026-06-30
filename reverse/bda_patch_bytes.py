#!/usr/bin/env python3
"""Patch byte sequences in a BDA/binary file.

This is intentionally small: it replaces an existing byte sequence with a
same-length or shorter sequence, padding the remainder with NUL bytes.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_bytes(text: str, encoding: str) -> bytes:
    if text.startswith("hex:"):
        return bytes.fromhex(text[4:].replace(" ", ""))
    if text.startswith("gbk:"):
        return text[4:].encode("gbk")
    if text.startswith("ascii:"):
        return text[6:].encode("ascii")
    return text.encode(encoding)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--from-bytes", required=True)
    ap.add_argument("--to-bytes", required=True)
    ap.add_argument("--encoding", default="gbk")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--offset", type=lambda s: int(s, 0))
    ns = ap.parse_args()

    old = parse_bytes(ns.from_bytes, ns.encoding)
    new = parse_bytes(ns.to_bytes, ns.encoding)
    if len(new) > len(old):
        raise SystemExit(f"replacement is longer: {len(new)} > {len(old)}")

    data = bytearray(Path(ns.input).read_bytes())
    start = 0
    patched = 0
    while patched < ns.count:
        if ns.offset is None:
            off = data.find(old, start)
            if off < 0:
                raise SystemExit(f"pattern not found after {patched} replacement(s)")
        else:
            off = ns.offset
            if data[off : off + len(old)] != old:
                got = data[off : off + len(old)].hex()
                raise SystemExit(f"pattern mismatch at 0x{off:x}: got {got}")
        data[off : off + len(old)] = new + (b"\0" * (len(old) - len(new)))
        start = off + len(old)
        patched += 1

    Path(ns.output).write_bytes(data)
    print(f"patched={patched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
