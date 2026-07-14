#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


ENTRY_START = 0x17B
ENTRY_SIZE = 0x100
TRAILER_OFF = 0x508


@dataclass(frozen=True)
class ConfigInfEntry:
    index: int
    offset: int
    enabled: bool
    name: str


def read_count(data: bytes) -> int:
    return int.from_bytes(data[0:2], "little")


def write_count(data: bytearray, count: int) -> None:
    data[0:2] = count.to_bytes(2, "little")
    data[2:4] = count.to_bytes(2, "little")


def checksum(data: bytes) -> int:
    if len(data) < TRAILER_OFF + 4:
        raise ValueError("Config.inf 太小，缺少 checksum trailer")
    return sum(data[:TRAILER_OFF]) & 0xFFFFFFFF


def stored_checksum(data: bytes) -> int:
    if len(data) < TRAILER_OFF + 4:
        raise ValueError("Config.inf 太小，缺少 checksum trailer")
    return int.from_bytes(data[TRAILER_OFF : TRAILER_OFF + 4], "little")


def max_full_slots(data: bytes) -> int:
    usable = min(TRAILER_OFF, len(data) - 4) - ENTRY_START
    if usable < 0:
        return 0
    return usable // ENTRY_SIZE


def parse_entries(data: bytes) -> list[ConfigInfEntry]:
    count = read_count(data)
    slots = max_full_slots(data)
    entries: list[ConfigInfEntry] = []
    for index in range(min(count, slots)):
        off = ENTRY_START + index * ENTRY_SIZE
        chunk = data[off : off + ENTRY_SIZE]
        enabled = bool(chunk and chunk[0])
        raw_name = chunk[1:].split(b"\0", 1)[0]
        try:
            name = raw_name.decode("gbk") if raw_name else ""
        except UnicodeDecodeError:
            name = raw_name.decode("gbk", errors="replace")
        entries.append(ConfigInfEntry(index=index, offset=off, enabled=enabled, name=name))
    return entries


def encode_slot(name: str) -> bytes:
    encoded = name.encode("gbk")
    if len(encoded) + 1 > ENTRY_SIZE:
        raise ValueError("entry name 超过一个 Config.inf slot 长度")
    slot = bytearray(b"\0" * ENTRY_SIZE)
    slot[0] = 1
    slot[1 : 1 + len(encoded)] = encoded
    return bytes(slot)


def update_checksum(data: bytearray) -> int:
    value = checksum(data)
    data[TRAILER_OFF : TRAILER_OFF + 4] = value.to_bytes(4, "little")
    return value


def add_or_replace_entry(data: bytes, name: str, replace_index: int | None = None) -> tuple[bytes, int, int]:
    out = bytearray(data)
    slots = max_full_slots(out)
    count = read_count(out)
    if replace_index is not None:
        if replace_index < 0 or replace_index >= min(count, slots):
            raise ValueError(f"replace_index 超出已有 entry 范围：{replace_index}")
        index = replace_index
    else:
        if count >= slots:
            raise ValueError(f"Config.inf 没有完整空 slot：count={count} slots={slots}；可用 --replace-index 临时替换")
        index = count
        write_count(out, count + 1)

    off = ENTRY_START + index * ENTRY_SIZE
    out[off : off + ENTRY_SIZE] = encode_slot(name)
    value = update_checksum(out)
    return bytes(out), off, value


def main() -> None:
    ap = argparse.ArgumentParser(
        description="向 BBK 9588 Config.inf app table 添加或替换一个 BDA entry name。",
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("config", type=Path, help="原始 系统\\数据\\Config.inf 路径")
    ap.add_argument("--name", required=True, help="GBK entry name，例如 HelloWorld.bda")
    ap.add_argument("--replace-index", type=int, help="替换已有 slot，0 表示第一个 entry；不传则尝试追加")
    ap.add_argument("--list", action="store_true", help="写入前列出现有 entries")
    ap.add_argument("-o", "--output", type=Path, required=True, help="输出 Config.inf 路径")
    ns = ap.parse_args()

    data = ns.config.read_bytes()
    if ns.list:
        print(f"count={read_count(data)} slots={max_full_slots(data)} checksum=0x{stored_checksum(data):08x}")
        for entry in parse_entries(data):
            state = "on" if entry.enabled else "off"
            print(f"[{entry.index}] off=0x{entry.offset:x} {state} {entry.name}")

    try:
        new_data, slot, value = add_or_replace_entry(data, ns.name, ns.replace_index)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(new_data)
    print(f"wrote {ns.output}")
    print(f"count={read_count(new_data)} slots={max_full_slots(new_data)}")
    print(f"slot=0x{slot:x} name={ns.name}")
    print(f"checksum=0x{value:08x}")


if __name__ == "__main__":
    main()
