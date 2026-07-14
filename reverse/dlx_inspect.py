from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def cstr(data: bytes, off: int, limit: int) -> str:
    raw = data[off : off + limit].split(b"\0", 1)[0]
    for enc in ("gbk", "latin1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin1", "replace")


def resource_kind(blob: bytes) -> str:
    if blob.startswith(b"BM"):
        return "BMP"
    if blob.startswith(b"VX"):
        return "VX"
    if blob.startswith(b"\x1f\x8b"):
        return "GZIP"
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if blob.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    return "BIN"


def vx_info(blob: bytes) -> dict[str, int] | None:
    if len(blob) < 0x18 or not blob.startswith(b"VX"):
        return None
    return {
        "width": u32(blob, 6),
        "height": u32(blob, 10),
        "pixel_bytes": max(0, len(blob) - 0x18),
    }


def bmp_info(blob: bytes) -> dict[str, int] | None:
    if len(blob) < 0x36 or not blob.startswith(b"BM"):
        return None
    return {
        "file_size": u32(blob, 2),
        "pixel_offset": u32(blob, 10),
        "dib_size": u32(blob, 14),
        "width": u32(blob, 18),
        "height": u32(blob, 22),
        "bpp": struct.unpack_from("<H", blob, 28)[0],
    }


def parse_dlx(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    if len(data) < 0x24 or data[:3] != b"DLX":
        raise ValueError(f"{path} 不是可识别的 DLX 文件")

    count = data[3]
    major = data[4]
    variant = data[5]
    stamp = u32(data, 8)
    header_size = u32(data, 12)

    if variant == 3:
        total_payload_size = u32(data, 16)
        name = cstr(data, 20, 16)
        table_off = 0x24
        entry_order = "type,offset,size"
    else:
        total_payload_size = None
        name = cstr(data, 16, 20)
        table_off = 0x24
        entry_order = "type,offset,size"

    resources = []
    for i in range(count):
        eoff = table_off + i * 12
        if eoff + 12 > len(data):
            break
        a = u32(data, eoff)
        b = u32(data, eoff + 4)
        c = u32(data, eoff + 8)
        rtype, rel_off, size = a, b, c
        off = header_size + rel_off
        blob = data[off : off + size]
        item: dict[str, object] = {
            "index": i,
            "type": rtype,
            "rel_offset": rel_off,
            "file_offset": off,
            "size": size,
            "kind": resource_kind(blob),
        }
        vi = vx_info(blob)
        if vi is not None:
            item["vx"] = vi
        bi = bmp_info(blob)
        if bi is not None:
            item["bmp"] = bi
        resources.append(item)

    return {
        "path": str(path),
        "size": len(data),
        "count": count,
        "major": major,
        "variant": variant,
        "stamp": f"0x{stamp:08x}",
        "header_size": header_size,
        "name": name,
        "entry_order": entry_order,
        "total_payload_size": total_payload_size,
        "resources": resources,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="检查 BBK DLX 资源容器。",
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("dlx", type=Path, nargs="+", help="要检查的 DLX 文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON 报告")
    ns = ap.parse_args()

    reports = [parse_dlx(path) for path in ns.dlx]
    if ns.json:
        print(json.dumps(reports if len(reports) != 1 else reports[0], ensure_ascii=False, indent=2))
        return

    for report in reports:
        print(f"{report['path']} size={report['size']} count={report['count']} variant={report['variant']} header=0x{report['header_size']:x} name={report['name']!r}")
        if report["total_payload_size"] is not None:
            print(f"  payload_size=0x{report['total_payload_size']:x}")
        for r in report["resources"]:
            extra = ""
            if "vx" in r:
                vx = r["vx"]
                extra = f" {vx['width']}x{vx['height']} pixels=0x{vx['pixel_bytes']:x}"
            elif "bmp" in r:
                bmp = r["bmp"]
                extra = f" {bmp['width']}x{bmp['height']} {bmp['bpp']}bpp"
            print(
                f"  #{r['index']:02d} type={r['type']} off=0x{r['file_offset']:x} "
                f"rel=0x{r['rel_offset']:x} size=0x{r['size']:x} {r['kind']}{extra}"
            )


if __name__ == "__main__":
    main()
