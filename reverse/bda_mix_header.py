from __future__ import annotations

import argparse
from pathlib import Path


SIZE_XOR_KEY = 0x44525740


def main() -> None:
    ap = argparse.ArgumentParser(description="Copy an app header prefix from one BDA to another and fix encoded size.")
    ap.add_argument("--header-from", type=Path, required=True)
    ap.add_argument("--body-from", type=Path, required=True)
    ap.add_argument("--bytes", type=lambda x: int(x, 0), default=0x80)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    head = ns.header_from.read_bytes()
    body = bytearray(ns.body_from.read_bytes())
    body[: ns.bytes] = head[: ns.bytes]
    size_word = len(body) ^ SIZE_XOR_KEY
    body[0x10:0x14] = size_word.to_bytes(4, "little")

    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(body)
    print(f"output={ns.output}")
    print(f"copied_header_bytes=0x{ns.bytes:x}")
    print(f"size_word=0x{size_word:08x}")


if __name__ == "__main__":
    main()
