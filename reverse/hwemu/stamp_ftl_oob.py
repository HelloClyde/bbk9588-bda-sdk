from __future__ import annotations

import argparse
import struct
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Stamp minimal BBK9588/C200 FTL OOB mapping tags into a raw NAND image.")
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--fat-page-base", type=lambda text: int(text, 0), default=0x1C40)
    ap.add_argument("--logical-blocks", type=lambda text: int(text, 0), default=0x800)
    ap.add_argument("--sequence", type=lambda text: int(text, 0), default=1)
    ap.add_argument("--page-size", type=int, default=2048)
    ap.add_argument("--spare-size", type=int, default=64)
    ap.add_argument("--pages-per-block", type=int, default=64)
    args = ap.parse_args()

    if args.fat_page_base % args.pages_per_block:
        raise SystemExit("--fat-page-base must be block-aligned")
    stride = args.page_size + args.spare_size
    physical_block_base = args.fat_page_base // args.pages_per_block
    data = bytearray(args.input.read_bytes())
    page_count = len(data) // stride
    max_physical_blocks = page_count // args.pages_per_block
    count = min(args.logical_blocks, max_physical_blocks - physical_block_base)
    if count <= 0:
        raise SystemExit("no physical blocks available for stamping")

    for logical_block in range(count):
        physical_block = physical_block_base + logical_block
        page = physical_block * args.pages_per_block
        oob = page * stride + args.page_size
        if oob + args.spare_size > len(data):
            break
        # C200's FTL scan reads the first page spare area of each block.
        # At spare[-6] it compares a 16-bit generation counter; at spare[-4]
        # it accepts normal mappings when the low 16 bits are < block_count.
        struct.pack_into("<H", data, oob + args.spare_size - 6, args.sequence & 0xFFFF)
        struct.pack_into("<I", data, oob + args.spare_size - 4, logical_block & 0xFFFF)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(
        f"wrote {args.output} size=0x{len(data):x} "
        f"physical_block_base=0x{physical_block_base:x} stamped_blocks=0x{count:x}"
    )


if __name__ == "__main__":
    main()
