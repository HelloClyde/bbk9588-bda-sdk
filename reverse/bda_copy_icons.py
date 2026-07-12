from __future__ import annotations

import argparse
from pathlib import Path

from bda_header import decoded_header_words, fix_header_checksum


def icon_ranges(data: bytes) -> list[tuple[int, int]]:
    words = decoded_header_words(data)
    cur = words[6]
    ranges: list[tuple[int, int]] = []
    for size in words[7:11]:
        ranges.append((cur, cur + size))
        cur += size
    return ranges


def main() -> None:
    ap = argparse.ArgumentParser(
        description="把一个 BDA 的四个 VX 菜单图标复制到另一个 BDA。",
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("input", type=Path, help="要修改的 BDA")
    ap.add_argument("--icons-from", type=Path, required=True, help="提供 VX 图标资源的 BDA")
    ap.add_argument("-o", "--output", type=Path, required=True, help="输出 BDA 路径")
    ns = ap.parse_args()

    data = bytearray(ns.input.read_bytes())
    src = ns.icons_from.read_bytes()
    dst_ranges = icon_ranges(data)
    src_ranges = icon_ranges(src)

    for idx, ((da, db), (sa, sb)) in enumerate(zip(dst_ranges, src_ranges)):
        if db - da != sb - sa:
            raise SystemExit(
                f"图标 {idx} 大小不匹配：input=0x{db-da:x}, icons-from=0x{sb-sa:x}；"
                "只能复制相同大小的图标区"
            )
        if src[sa : sa + 2] != b"VX":
            raise SystemExit(f"源图标 {idx} 缺少 VX 签名")
        data[da:db] = src[sa:sb]
        print(f"icon{idx}: 0x{sa:x}-0x{sb:x} -> 0x{da:x}-0x{db:x}")

    checksum = fix_header_checksum(data)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"output={ns.output}")
    print(f"checksum=0x{checksum:08x}")


if __name__ == "__main__":
    main()
