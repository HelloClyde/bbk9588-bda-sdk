from __future__ import annotations

import argparse
from pathlib import Path

from bda_layout import analyze
from bda_patch_main import find_main_offset
from bda_set_icon_png import (
    ICON_SPECS,
    icon_ranges,
    make_vx,
    read_png,
    resize_cover,
    rgb565_bytes,
)
from minimips import assemble_file


XOR_KEY = 0x44525744
CHECKSUM_OFF = 0x84
CHECKSUM_XOR_KEY = 0x322D464B
TITLE_OFFSET = 0x2C
TITLE_SIZE = 16
CATEGORY_OFFSET = 0x0C
NOP = b"\0\0\0\0"


def fix_header_checksum(data: bytearray) -> int:
    buf = bytearray(data[:CHECKSUM_OFF])
    for off in range(0, 0x2C, 4):
        v = int.from_bytes(buf[off : off + 4], "little") ^ XOR_KEY
        buf[off : off + 4] = v.to_bytes(4, "little")
    checksum = (sum(buf) & 0xFFFFFFFF) ^ CHECKSUM_XOR_KEY
    data[CHECKSUM_OFF : CHECKSUM_OFF + 4] = checksum.to_bytes(4, "little")
    return checksum


def set_title(data: bytearray, title: str) -> None:
    encoded = title.encode("gbk")
    if len(encoded) > TITLE_SIZE:
        raise SystemExit(f"title is {len(encoded)} bytes in GBK, max {TITLE_SIZE}")
    data[TITLE_OFFSET : TITLE_OFFSET + TITLE_SIZE] = encoded.ljust(TITLE_SIZE, b"\0")


def set_category(data: bytearray, category: int) -> None:
    encoded = category ^ XOR_KEY
    data[CATEGORY_OFFSET : CATEGORY_OFFSET + 4] = encoded.to_bytes(4, "little")


def patch_main_blob(data: bytearray, template: Path, blob: bytes, wipe_bytes: int) -> tuple[int, int, int]:
    offset, main_va = find_main_offset(template)
    if len(blob) > wipe_bytes:
        raise SystemExit(f"code is 0x{len(blob):x} bytes, exceeds wipe area 0x{wipe_bytes:x}")
    if offset < 0 or offset + wipe_bytes > len(data):
        raise SystemExit("patch range is outside file")
    data[offset : offset + wipe_bytes] = NOP * (wipe_bytes // 4)
    data[offset : offset + len(blob)] = blob
    return offset, main_va, len(blob)


def assemble_main(template: Path, source: Path) -> bytes:
    offset, _main_va = find_main_offset(template)
    layout = analyze(template)
    file_base = layout["runtime_file_base"]
    if file_base is None:
        raise SystemExit(f"could not infer runtime file base for {template}")
    base_va = int(file_base) + offset
    return assemble_file(source, int(base_va))


def set_icon_png(data: bytearray, png: Path, background: tuple[int, int, int]) -> None:
    src_w, src_h, src_pixels = read_png(png)
    ranges = icon_ranges(data)
    for idx, ((width, height), (start, end)) in enumerate(zip(ICON_SPECS, ranges)):
        resized = resize_cover(src_w, src_h, src_pixels, width, height)
        vx = make_vx(width, height, rgb565_bytes(resized, background))
        if len(vx) != end - start:
            raise SystemExit(f"generated icon {idx} size mismatch")
        data[start:end] = vx


def parse_bg(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("background must be RRGGBB")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def verify(data: bytes) -> tuple[str, int, bool]:
    title = data[TITLE_OFFSET : TITLE_OFFSET + TITLE_SIZE].split(b"\0", 1)[0].decode("gbk", "replace")
    category = int.from_bytes(data[CATEGORY_OFFSET : CATEGORY_OFFSET + 4], "little") ^ XOR_KEY
    buf = bytearray(data[:CHECKSUM_OFF])
    for off in range(0, 0x2C, 4):
        v = int.from_bytes(buf[off : off + 4], "little") ^ XOR_KEY
        buf[off : off + 4] = v.to_bytes(4, "little")
    expected = sum(buf) & 0xFFFFFFFF
    actual = int.from_bytes(data[CHECKSUM_OFF : CHECKSUM_OFF + 4], "little") ^ CHECKSUM_XOR_KEY
    return title, category, actual == expected


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a native BBK 9588 BDA from a template and tiny MIPS source.")
    ap.add_argument("--template", type=Path, required=True, help="Existing native BDA used as container/template")
    ap.add_argument("--source", type=Path, help="MIPS source to patch into the app main function")
    ap.add_argument("--raw-bin", type=Path, help="Raw MIPS little-endian binary to patch into the app main function")
    ap.add_argument("--title", help="Menu title, GBK/ASCII, max 16 bytes")
    ap.add_argument("--category", type=lambda x: int(x, 0), help="Decoded menu category")
    ap.add_argument("--icon-png", type=Path, help="RGB/RGBA non-interlaced PNG used for all four icon sizes")
    ap.add_argument("--icon-background", type=parse_bg, default=(0, 0, 0), help="RGBA matte color, default 000000")
    ap.add_argument("--wipe-bytes", type=lambda x: int(x, 0), default=0x300)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    data = bytearray(ns.template.read_bytes())
    if ns.source and ns.raw_bin:
        raise SystemExit("pass only one of --source or --raw-bin")
    if ns.source or ns.raw_bin:
        blob = assemble_main(ns.template, ns.source) if ns.source else ns.raw_bin.read_bytes()
        offset, main_va, code_size = patch_main_blob(data, ns.template, blob, ns.wipe_bytes)
        print(f"patched_main_offset=0x{offset:x}")
        print(f"patched_main_va=0x{main_va:x}")
        print(f"code_size=0x{code_size:x}")
    if ns.title is not None:
        set_title(data, ns.title)
        print(f"title={ns.title}")
    if ns.category is not None:
        set_category(data, ns.category)
        print(f"category=0x{ns.category:x}")
    if ns.icon_png is not None:
        set_icon_png(data, ns.icon_png, ns.icon_background)
        print(f"icon_png={ns.icon_png}")

    checksum = fix_header_checksum(data)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    title, category, ok = verify(data)
    print(f"output={ns.output}")
    print(f"checksum=0x{checksum:08x}")
    print(f"verify_title={title}")
    print(f"verify_category=0x{category:x}")
    print(f"verify_checksum={ok}")


if __name__ == "__main__":
    main()
