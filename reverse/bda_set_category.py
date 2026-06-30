from __future__ import annotations

import argparse
from pathlib import Path


XOR_KEY = 0x44525744
CATEGORY_OFFSET = 0x0C
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
    ap = argparse.ArgumentParser(description="Patch the XOR-encoded BDA category/menu group field.")
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--category", type=lambda x: int(x, 0), required=True)
    ns = ap.parse_args()

    data = bytearray(ns.input.read_bytes())
    encoded = ns.category ^ XOR_KEY
    data[CATEGORY_OFFSET : CATEGORY_OFFSET + 4] = encoded.to_bytes(4, "little")
    checksum = fix_header_checksum(data)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"output={ns.output}")
    print(f"category=0x{ns.category:x}")
    print(f"encoded=0x{encoded:08x}")
    print(f"checksum=0x{checksum:08x}")


if __name__ == "__main__":
    main()
