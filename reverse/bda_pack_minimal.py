from __future__ import annotations

import argparse
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from bda_build import CHECKSUM_OFF, CHECKSUM_XOR_KEY, XOR_KEY, fix_header_checksum, set_category, set_title
from bda_set_icon_png import make_vx, read_png, resize_cover, rgb565_bytes
from minimips import assemble_file


ENTRY_OFFSET = 0x95F8
ENTRY_VA = 0x81C00020
ICON_START = 0x88
ICON_SPECS = ((80, 80), (80, 80), (54, 54), (58, 58))
ICON_SIZES = tuple(24 + w * h * 2 for w, h in ICON_SPECS)


def bundled_prefix() -> str | None:
    root = Path(__file__).resolve().parents[1] / "tools"
    for gcc in root.glob("g++-mipsel-none-elf-*/bin/mipsel-none-elf-gcc.exe"):
        return str(gcc.parent / "mipsel-none-elf-")
    return None


def find_tool(prefix: str, name: str) -> str:
    exe = f"{prefix}{name}"
    candidates = [exe]
    if not exe.lower().endswith(".exe"):
        candidates.append(exe + ".exe")
    for candidate in candidates:
        p = Path(candidate)
        if p.is_file():
            return str(p)
        found = shutil.which(candidate)
        if found is not None:
            return found
    raise SystemExit(f"could not find {exe}")


def compile_raw(source: Path, prefix: str) -> bytes:
    if source.suffix.lower() in {".s", ".asm"}:
        return assemble_file(source, ENTRY_VA)

    cc = find_tool(prefix, "gcc")
    objcopy = find_tool(prefix, "objcopy")
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        elf = tdir / "app.elf"
        raw = tdir / "app.bin"
        lds = tdir / "bda_minimal.ld"
        lds.write_text(
            f"""
ENTRY(bda_main)
SECTIONS
{{
  . = 0x{ENTRY_VA:x};
  .text : {{ *(.text.bda_main) *(.text*) }}
  .rodata : {{ *(.rodata*) }}
  .data : {{ *(.data*) }}
  .bss : {{ *(.bss*) *(COMMON) }}
}}
""".strip()
            + "\n",
            encoding="ascii",
        )
        subprocess.check_call(
            [
                cc,
                "-EL",
                "-march=mips32",
                "-mno-abicalls",
                "-G0",
                "-fno-pic",
                "-Os",
                "-ffreestanding",
                "-fno-builtin",
                "-nostdlib",
                "-Wl,--build-id=none",
                f"-Wl,-T,{lds}",
                str(source),
                "-o",
                str(elf),
            ]
        )
        subprocess.check_call([objcopy, "-O", "binary", str(elf), str(raw)])
        return raw.read_bytes()


def put_encoded_word(data: bytearray, off: int, decoded: int) -> None:
    struct.pack_into("<I", data, off, decoded ^ XOR_KEY)


def make_flat_icon(width: int, height: int, fg: tuple[int, int, int], bg: tuple[int, int, int]) -> bytes:
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            border = x < 3 or y < 3 or x >= width - 3 or y >= height - 3
            diag = abs(x - y) <= 1 or abs((width - 1 - x) - y) <= 1
            r, g, b = fg if border or diag else bg
            pixels.append((r, g, b, 255))
    return make_vx(width, height, rgb565_bytes(pixels, bg))


def parse_bg(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("background must be RRGGBB")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def build_icons(icon_png: Path | None, icon_background: tuple[int, int, int]) -> bytes:
    out = bytearray()
    if icon_png is not None:
        src_w, src_h, src_pixels = read_png(icon_png)
        for width, height in ICON_SPECS:
            resized = resize_cover(src_w, src_h, src_pixels, width, height)
            out.extend(make_vx(width, height, rgb565_bytes(resized, icon_background)))
        return bytes(out)

    colors = (
        ((255, 255, 255), (0, 64, 96)),
        ((255, 255, 255), (96, 32, 0)),
        ((0, 0, 0), (180, 220, 255)),
        ((255, 255, 255), (40, 40, 40)),
    )
    for (width, height), (fg, bg) in zip(ICON_SPECS, colors):
        out.extend(make_flat_icon(width, height, fg, bg))
    return bytes(out)


def build_header(data: bytearray, title: str, category: int) -> None:
    decoded_words = [
        0x004B4242,  # "BBK"
        0x5D245562,
        0x01000102,
        category,
        len(data) - 4,
        ENTRY_OFFSET,
        ICON_START,
        ICON_SIZES[0],
        ICON_SIZES[1],
        ICON_SIZES[2],
        ICON_SIZES[3],
    ]
    for idx, word in enumerate(decoded_words):
        put_encoded_word(data, idx * 4, word)
    set_title(data, title)
    data[0x3C:CHECKSUM_OFF] = b"\0" * (CHECKSUM_OFF - 0x3C)


def build_bda(
    source: Path,
    title: str,
    category: int,
    prefix: str,
    icon_png: Path | None,
    icon_background: tuple[int, int, int],
) -> bytearray:
    blob = compile_raw(source, prefix)
    data = bytearray(b"\0" * ENTRY_OFFSET)

    icons = build_icons(icon_png, icon_background)
    if len(icons) != ENTRY_OFFSET - ICON_START:
        raise SystemExit(f"icon layout size is 0x{len(icons):x}, expected 0x{ENTRY_OFFSET - ICON_START:x}")
    data[ICON_START:ENTRY_OFFSET] = icons

    data.extend(blob)
    if len(data) % 4:
        data.extend(b"\0" * (4 - (len(data) % 4)))

    build_header(data, title, category)
    fix_header_checksum(data)
    return data


def verify(data: bytes) -> tuple[str, int, bool, int]:
    title = data[0x2C:0x3C].split(b"\0", 1)[0].decode("gbk", "replace")
    category = struct.unpack_from("<I", data, 0x0C)[0] ^ XOR_KEY
    decoded_size = struct.unpack_from("<I", data, 0x10)[0] ^ XOR_KEY
    buf = bytearray(data[:CHECKSUM_OFF])
    for off in range(0, 0x2C, 4):
        v = struct.unpack_from("<I", buf, off)[0] ^ XOR_KEY
        struct.pack_into("<I", buf, off, v)
    expected = sum(buf) & 0xFFFFFFFF
    actual = struct.unpack_from("<I", data, CHECKSUM_OFF)[0] ^ CHECKSUM_XOR_KEY
    return title, category, actual == expected, decoded_size


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a first-pass native BDA without using an existing BDA template.")
    ap.add_argument("source", type=Path, help="freestanding C source with bda_main")
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--title", default="NoTplHello")
    ap.add_argument("--category", type=lambda x: int(x, 0), default=9)
    ap.add_argument("--icon-png", type=Path, help="RGB/RGBA non-interlaced PNG used for all four icon sizes")
    ap.add_argument("--icon-background", type=parse_bg, default=(0, 0, 0), help="RGBA matte color, default 000000")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    prefix = ns.prefix or bundled_prefix() or "mipsel-none-elf-"
    data = build_bda(ns.source, ns.title, ns.category, prefix, ns.icon_png, ns.icon_background)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    title, category, ok, decoded_size = verify(data)
    print(f"output={ns.output}")
    print(f"size=0x{len(data):x}")
    print(f"decoded_size=0x{decoded_size:x}")
    print(f"entry_offset=0x{ENTRY_OFFSET:x}")
    print(f"entry_va=0x{ENTRY_VA:x}")
    print(f"title={title}")
    print(f"category=0x{category:x}")
    print(f"checksum_ok={ok}")


if __name__ == "__main__":
    main()
