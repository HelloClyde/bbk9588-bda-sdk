from __future__ import annotations

import argparse
from pathlib import Path


XOR_KEY = 0x44525744
CHECKSUM_OFF = 0x84
CHECKSUM_XOR_KEY = 0x322D464B


def decoded_header_words(data: bytes) -> list[int]:
    return [int.from_bytes(data[i : i + 4], "little") ^ XOR_KEY for i in range(0, 0x2C, 4)]


def icon_ranges(data: bytes) -> list[tuple[int, int]]:
    words = decoded_header_words(data)
    cur = words[6]
    ranges: list[tuple[int, int]] = []
    for size in words[7:11]:
        ranges.append((cur, cur + size))
        cur += size
    return ranges


def fix_header_checksum(data: bytearray) -> int:
    buf = bytearray(data[:CHECKSUM_OFF])
    for off in range(0, 0x2C, 4):
        v = int.from_bytes(buf[off : off + 4], "little") ^ XOR_KEY
        buf[off : off + 4] = v.to_bytes(4, "little")
    checksum = (sum(buf) & 0xFFFFFFFF) ^ CHECKSUM_XOR_KEY
    data[CHECKSUM_OFF : CHECKSUM_OFF + 4] = checksum.to_bytes(4, "little")
    return checksum


def main() -> None:
    ap = argparse.ArgumentParser(description="Copy the four VX icon resources from one BDA to another.")
    ap.add_argument("input", type=Path, help="BDA to modify")
    ap.add_argument("--icons-from", type=Path, required=True, help="BDA providing icon VX resources")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    data = bytearray(ns.input.read_bytes())
    src = ns.icons_from.read_bytes()
    dst_ranges = icon_ranges(data)
    src_ranges = icon_ranges(src)

    for idx, ((da, db), (sa, sb)) in enumerate(zip(dst_ranges, src_ranges)):
        if db - da != sb - sa:
            raise SystemExit(
                f"icon {idx} size mismatch: input=0x{db-da:x}, icons-from=0x{sb-sa:x}; "
                "same-size copy only"
            )
        if src[sa : sa + 2] != b"VX":
            raise SystemExit(f"source icon {idx} missing VX signature")
        data[da:db] = src[sa:sb]
        print(f"icon{idx}: 0x{sa:x}-0x{sb:x} -> 0x{da:x}-0x{db:x}")

    checksum = fix_header_checksum(data)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"output={ns.output}")
    print(f"checksum=0x{checksum:08x}")


if __name__ == "__main__":
    main()
