from __future__ import annotations

import argparse
from pathlib import Path


TITLE_OFFSET = 0x2C
TITLE_SIZE = 16
XOR_KEY = 0x44525744
CHECKSUM_OFF = 0x84
CHECKSUM_XOR_KEY = 0x322D464B


def fix_header_checksum(data: bytearray) -> int:
    buf = bytearray(data[:CHECKSUM_OFF])
    for off in range(0, 0x2C, 4):
        v = int.from_bytes(buf[off : off + 4], "little") ^ XOR_KEY
        buf[off : off + 4] = v.to_bytes(4, "little")
    checksum = (sum(buf) & 0xFFFFFFFF) ^ CHECKSUM_XOR_KEY
    data[CHECKSUM_OFF : CHECKSUM_OFF + 4] = checksum.to_bytes(4, "little")
    return checksum


def main() -> None:
    ap = argparse.ArgumentParser(description="Patch the 16-byte BDA menu title field.")
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--title", required=True, help="ASCII/GBK title, max 16 encoded bytes including padding.")
    ns = ap.parse_args()

    encoded = ns.title.encode("gbk")
    if len(encoded) > TITLE_SIZE:
        raise SystemExit(f"title is {len(encoded)} bytes in GBK, max {TITLE_SIZE}")

    data = bytearray(ns.input.read_bytes())
    data[TITLE_OFFSET : TITLE_OFFSET + TITLE_SIZE] = encoded.ljust(TITLE_SIZE, b"\0")
    checksum = fix_header_checksum(data)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"output={ns.output}")
    print(f"title={ns.title}")
    print(f"checksum=0x{checksum:08x}")


if __name__ == "__main__":
    main()
