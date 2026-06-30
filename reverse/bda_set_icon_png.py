from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path


XOR_KEY = 0x44525744
CHECKSUM_OFF = 0x84
CHECKSUM_XOR_KEY = 0x322D464B
ICON_SPECS = ((80, 80), (80, 80), (54, 54), (58, 58))


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def read_png(path: Path) -> tuple[int, int, list[tuple[int, int, int, int]]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SystemExit("only PNG input is supported")
    pos = 8
    width = height = color_type = bit_depth = None
    idat = bytearray()
    while pos + 8 <= len(data):
        ln = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        payload = data[pos + 8 : pos + 8 + ln]
        pos += 12 + ln
        if kind == b"IHDR":
            width, height, bit_depth, color_type, comp, filt, interlace = struct.unpack(">IIBBBBB", payload)
            if bit_depth != 8 or comp != 0 or filt != 0 or interlace != 0:
                raise SystemExit("PNG must be non-interlaced 8-bit")
            if color_type not in (2, 6):
                raise SystemExit("PNG must be RGB or RGBA")
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None:
        raise SystemExit("missing PNG IHDR")

    channels = 3 if color_type == 2 else 4
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    rows: list[bytearray] = []
    i = 0
    prev = bytearray(stride)
    for _y in range(height):
        ft = raw[i]
        i += 1
        cur = bytearray(raw[i : i + stride])
        i += stride
        for x in range(stride):
            left = cur[x - channels] if x >= channels else 0
            up = prev[x]
            ul = prev[x - channels] if x >= channels else 0
            if ft == 0:
                val = cur[x]
            elif ft == 1:
                val = cur[x] + left
            elif ft == 2:
                val = cur[x] + up
            elif ft == 3:
                val = cur[x] + ((left + up) >> 1)
            elif ft == 4:
                p = left + up - ul
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - ul)
                pred = left if pa <= pb and pa <= pc else up if pb <= pc else ul
                val = cur[x] + pred
            else:
                raise SystemExit(f"unsupported PNG filter {ft}")
            cur[x] = val & 0xFF
        rows.append(cur)
        prev = cur

    pixels: list[tuple[int, int, int, int]] = []
    for row in rows:
        for x in range(0, len(row), channels):
            if channels == 3:
                r, g, b = row[x], row[x + 1], row[x + 2]
                a = 255
            else:
                r, g, b, a = row[x], row[x + 1], row[x + 2], row[x + 3]
            pixels.append((r, g, b, a))
    return width, height, pixels


def resize_cover(
    src_w: int, src_h: int, pixels: list[tuple[int, int, int, int]], dst_w: int, dst_h: int
) -> list[tuple[int, int, int, int]]:
    scale = max(dst_w / src_w, dst_h / src_h)
    crop_w = dst_w / scale
    crop_h = dst_h / scale
    ox = (src_w - crop_w) / 2
    oy = (src_h - crop_h) / 2
    out: list[tuple[int, int, int, int]] = []
    for y in range(dst_h):
        sy = min(src_h - 1, max(0, int(oy + (y + 0.5) / scale)))
        for x in range(dst_w):
            sx = min(src_w - 1, max(0, int(ox + (x + 0.5) / scale)))
            out.append(pixels[sy * src_w + sx])
    return out


def rgb565_bytes(pixels: list[tuple[int, int, int, int]], bg: tuple[int, int, int]) -> bytes:
    out = bytearray()
    br, bgc, bb = bg
    for r, g, b, a in pixels:
        if a < 255:
            r = (r * a + br * (255 - a)) // 255
            g = (g * a + bgc * (255 - a)) // 255
            b = (b * a + bb * (255 - a)) // 255
        v = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        out.extend(v.to_bytes(2, "little"))
    return bytes(out)


def make_vx(width: int, height: int, pixels565: bytes) -> bytes:
    # This preserves the observed VX header shape: magic, padding, width, height,
    # padding/color-key-looking fields.
    hdr = bytearray()
    hdr.extend(b"VX")
    hdr.extend(b"\xCC\xCC\xCC\xCC")
    hdr.extend(width.to_bytes(4, "little"))
    hdr.extend(height.to_bytes(4, "little"))
    hdr.extend(b"\xCC\xCC\xCC\xCC\xCC\xCC\xFF\xFF\xFF\xFF")
    return bytes(hdr) + pixels565


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


def parse_bg(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("background must be RRGGBB")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate BDA VX icon resources from a PNG.")
    ap.add_argument("input", type=Path, help="BDA to modify")
    ap.add_argument("--png", type=Path, required=True, help="RGB/RGBA non-interlaced 8-bit PNG")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--background", type=parse_bg, default=(0, 0, 0), help="RGBA matte color, default 000000")
    ns = ap.parse_args()

    src_w, src_h, src_pixels = read_png(ns.png)
    data = bytearray(ns.input.read_bytes())
    ranges = icon_ranges(data)
    for idx, ((width, height), (start, end)) in enumerate(zip(ICON_SPECS, ranges)):
        resized = resize_cover(src_w, src_h, src_pixels, width, height)
        vx = make_vx(width, height, rgb565_bytes(resized, ns.background))
        if len(vx) != end - start:
            raise SystemExit(f"generated icon {idx} size mismatch")
        data[start:end] = vx
        print(f"icon{idx}: {width}x{height} -> 0x{start:x}-0x{end:x}")
    checksum = fix_header_checksum(data)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"output={ns.output}")
    print(f"checksum=0x{checksum:08x}")


if __name__ == "__main__":
    main()
