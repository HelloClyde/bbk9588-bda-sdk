#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from config_inf_add import max_full_slots, parse_entries, read_count, stored_checksum, checksum


def strings_gbk(data: bytes, min_len: int = 4) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    start = None
    for i, b in enumerate(data + b"\0"):
        if b != 0:
            if start is None:
                start = i
        elif start is not None:
            chunk = data[start:i]
            if len(chunk) >= min_len:
                for enc in ("gbk", "ascii"):
                    try:
                        s = chunk.decode(enc)
                    except UnicodeDecodeError:
                        continue
                    if any(ch.isprintable() for ch in s):
                        out.append((start, s))
                        break
            start = None
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description="检查 BBK 9588 Config.inf 条目和 checksum。",
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("config", nargs="?", type=Path, default=Path("\u7cfb\u7edf") / "\u6570\u636e" / "Config.inf", help="要检查的 Config.inf 路径")
    ns = ap.parse_args()

    p = ns.config
    data = p.read_bytes()
    print(f"path={p} size={len(data)}")
    print(f"count={read_count(data)} slots={max_full_slots(data)} checksum=0x{stored_checksum(data):08x} computed=0x{checksum(data):08x}")
    print("entries:")
    for entry in parse_entries(data):
        state = "on" if entry.enabled else "off"
        print(f"  [{entry.index}] off=0x{entry.offset:04x} {state} {entry.name}")
    print("first_words:")
    for off in range(0, min(0x40, len(data)), 4):
        print(f"  {off:04x}: {int.from_bytes(data[off:off+4], 'little'):08x}")
    print("strings:")
    for off, s in strings_gbk(data):
        print(f"  0x{off:04x}: {s}")


if __name__ == "__main__":
    main()
