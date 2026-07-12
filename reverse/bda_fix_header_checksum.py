from __future__ import annotations

import argparse
from pathlib import Path

from bda_header import decoded_checksum_sum, fix_header_checksum


def main() -> None:
    ap = argparse.ArgumentParser(
        description="修复 BDA header 0x84 处的 checksum 字段。",
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("input", type=Path, help="要修复 checksum 的 BDA 文件")
    ap.add_argument("-o", "--output", type=Path, required=True, help="输出 BDA 路径")
    ns = ap.parse_args()

    data = bytearray(ns.input.read_bytes())

    new_sum = decoded_checksum_sum(data)
    patched = fix_header_checksum(data)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)

    print(f"output={ns.output}")
    print("mode=exact")
    print(f"new_sum=0x{new_sum:x} patched_raw84=0x{patched:08x}")


if __name__ == "__main__":
    main()
