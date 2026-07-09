from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a BBK9588 NAND image with C200 plus a raw FAT logical area.")
    ap.add_argument("--base-nand", type=Path, required=True)
    ap.add_argument("--fat-image", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--fat-page-base", type=lambda text: int(text, 0), default=0x1C40)
    ap.add_argument("--page-size", type=int, default=2048)
    ap.add_argument("--spare-size", type=int, default=64)
    ap.add_argument(
        "--free-blocks",
        type=lambda text: int(text, 0),
        default=0x100,
        help="erased physical blocks to append after the FAT payload for FTL writes",
    )
    ap.add_argument("--pages-per-block", type=int, default=64)
    args = ap.parse_args()

    stride = args.page_size + args.spare_size
    base = args.base_nand.read_bytes()
    fat = args.fat_image.read_bytes()
    page_count = (len(fat) + args.page_size - 1) // args.page_size
    free_pages = max(0, args.free_blocks) * args.pages_per_block
    out_size = max(len(base), (args.fat_page_base + page_count + free_pages) * stride)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as f:
        chunk = b"\xFF" * (1024 * 1024)
        remaining = out_size
        while remaining:
            n = min(remaining, len(chunk))
            f.write(chunk[:n])
            remaining -= n
        f.seek(0)
        f.write(base)
        for page in range(page_count):
            chunk = fat[page * args.page_size : (page + 1) * args.page_size]
            if len(chunk) < args.page_size:
                chunk += b"\x00" * (args.page_size - len(chunk))
            f.seek((args.fat_page_base + page) * stride)
            f.write(chunk)
            f.write(b"\xFF" * args.spare_size)

    print(
        f"wrote {args.output} size=0x{out_size:x} "
        f"fat_page_base=0x{args.fat_page_base:x} pages=0x{page_count:x} "
        f"free_blocks=0x{max(0, args.free_blocks):x}"
    )


if __name__ == "__main__":
    main()
