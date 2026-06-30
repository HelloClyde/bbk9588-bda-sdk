from __future__ import annotations

import argparse
from pathlib import Path

from bda_set_icon_png import make_vx, read_png, resize_cover, rgb565_bytes


def parse_bg(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError("background must be RRGGBB")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def parse_resource(spec: str, bg: tuple[int, int, int]) -> bytes:
    parts = spec.split(":")
    path = Path(parts[0])
    data = path.read_bytes()
    suffix = path.suffix.lower()

    if suffix == ".png":
        if len(parts) != 3:
            raise SystemExit(f"PNG resource needs WIDTH:HEIGHT: {spec}")
        width = int(parts[1], 0)
        height = int(parts[2], 0)
        src_w, src_h, pixels = read_png(path)
        resized = resize_cover(src_w, src_h, pixels, width, height)
        return make_vx(width, height, rgb565_bytes(resized, bg))

    if len(parts) != 1:
        raise SystemExit(f"only PNG resources take dimensions: {spec}")
    return data


def build_dlx(resources: list[bytes], variant: int, name: str) -> bytes:
    if not 0 <= len(resources) <= 255:
        raise SystemExit("DLX supports 0..255 resources in this builder")

    count = len(resources)
    if variant == 3:
        header_size = 0x24 + count * 12
        name_bytes = name.encode("ascii", "replace")[:15] + b"\0"
        name_bytes = name_bytes.ljust(16, b"\0")
        header = bytearray()
        header.extend(b"DLX")
        header.append(count)
        header.extend(b"\x01\x03\x00\x00")
        header.extend((0x19811108).to_bytes(4, "little"))
        header.extend(header_size.to_bytes(4, "little"))
        header.extend(sum(len(r) for r in resources).to_bytes(4, "little"))
        header.extend(name_bytes)
    elif variant == 0:
        header_size = 0x24 + count * 12
        name_bytes = name.encode("ascii", "replace")[:19] + b"\0"
        name_bytes = name_bytes.ljust(20, b"\0")
        header = bytearray()
        header.extend(b"DLX")
        header.append(count)
        header.extend(b"\x01\x00\x00\x00")
        header.extend((0x19811108).to_bytes(4, "little"))
        header.extend(header_size.to_bytes(4, "little"))
        header.extend(name_bytes)
    else:
        raise SystemExit("this builder currently supports variant 0 and 3")

    rel = 0
    for blob in resources:
        header.extend((1).to_bytes(4, "little"))
        header.extend(rel.to_bytes(4, "little"))
        header.extend(len(blob).to_bytes(4, "little"))
        rel += len(blob)

    if len(header) != header_size:
        raise AssertionError((len(header), header_size))
    return bytes(header) + b"".join(resources)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a simple BBK DLX resource container.")
    ap.add_argument("--resource", action="append", required=True, help="BMP/VX raw path, or PNG:WIDTH:HEIGHT")
    ap.add_argument("--variant", type=int, choices=[0, 3], default=3)
    ap.add_argument("--name", default="Vrix.Ipona")
    ap.add_argument("--background", type=parse_bg, default=(0, 0, 0), help="PNG alpha matte color, default 000000")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    resources = [parse_resource(spec, ns.background) for spec in ns.resource]
    data = build_dlx(resources, ns.variant, ns.name)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"output={ns.output}")
    print(f"resources={len(resources)}")
    print(f"size=0x{len(data):x}")


if __name__ == "__main__":
    main()
