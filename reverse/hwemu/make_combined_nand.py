from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a BBK9588 NAND image with C200 plus a raw FAT logical area.")
    ap.add_argument("--base-nand", type=Path, required=True)
    ap.add_argument("--fat-image", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--fat-page-base", type=lambda text: int(text, 0), default=0x1C40)
    ap.add_argument("--page-size", type=int, default=2048)
    ap.add_argument("--spare-size", type=int, default=64)
    args = ap.parse_args()

    stride = args.page_size + args.spare_size
    base = args.base_nand.read_bytes()
    fat = args.fat_image.read_bytes()
    page_count = (len(fat) + args.page_size - 1) // args.page_size
    out_size = max(len(base), (args.fat_page_base + page_count) * stride)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as f:
        f.truncate(out_size)
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
        f"fat_page_base=0x{args.fat_page_base:x} pages=0x{page_count:x}"
    )


if __name__ == "__main__":
    main()
