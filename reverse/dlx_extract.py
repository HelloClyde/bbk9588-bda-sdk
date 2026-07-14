from __future__ import annotations

import argparse
import struct
import zlib
from pathlib import Path

from dlx_inspect import parse_dlx


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        rows.extend(rgb[y * stride : (y + 1) * stride])
    payload = b"\x89PNG\r\n\x1a\n"
    payload += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += png_chunk(b"IDAT", zlib.compress(bytes(rows), 9))
    payload += png_chunk(b"IEND", b"")
    path.write_bytes(payload)


def rgb565_to_rgb(data: bytes, width: int, height: int, endian: str = "little") -> bytes:
    out = bytearray()
    for i in range(width * height):
        raw = data[i * 2 : i * 2 + 2]
        v = int.from_bytes(raw, endian)
        r = (v >> 11) & 0x1F
        g = (v >> 5) & 0x3F
        b = v & 0x1F
        out.extend(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))
    return bytes(out)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="导出 BBK DLX 资源。",
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("dlx", type=Path, help="要导出的 DLX 文件")
    ap.add_argument("-o", "--out-dir", type=Path, default=Path("build/dlx_extract"), help="输出目录")
    ap.add_argument("--vx-endian", choices=["little", "big"], default="little", help="VX RGB565 像素字节序")
    ns = ap.parse_args()

    report = parse_dlx(ns.dlx)
    data = ns.dlx.read_bytes()
    out_dir = ns.out_dir / ns.dlx.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    for r in report["resources"]:
        off = int(r["file_offset"])
        size = int(r["size"])
        blob = data[off : off + size]
        kind = str(r["kind"]).lower()
        suffix = ".bin"
        if kind == "bmp":
            suffix = ".bmp"
        elif kind == "png":
            suffix = ".png"
        elif kind == "jpeg":
            suffix = ".jpg"
        elif kind == "gzip":
            suffix = ".gz"
        raw_path = out_dir / f"res{int(r['index']):02d}_{kind}_type{int(r['type'])}{suffix}"
        raw_path.write_bytes(blob)
        print(f"原始资源: {raw_path}")

        if kind == "vx" and "vx" in r:
            vx = r["vx"]
            width = int(vx["width"])
            height = int(vx["height"])
            pixels = blob[0x18 : 0x18 + width * height * 2]
            if len(pixels) == width * height * 2:
                png_path = out_dir / f"res{int(r['index']):02d}_vx_{width}x{height}.png"
                write_png(png_path, width, height, rgb565_to_rgb(pixels, width, height, ns.vx_endian))
                print(f"PNG 预览: {png_path}")


if __name__ == "__main__":
    main()
