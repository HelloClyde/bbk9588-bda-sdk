#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


ENTRY_START = 0x17B
ENTRY_SIZE = 0x100
TRAILER_OFF = 0x508


def main() -> None:
    ap = argparse.ArgumentParser(description="Add one BDA filename to the observed Config.inf download-app table.")
    ap.add_argument("config", type=Path)
    ap.add_argument("--name", required=True, help="GBK filename, e.g. HelloWorld.bda")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    data = bytearray(ns.config.read_bytes())
    encoded = ns.name.encode("gbk")
    if len(encoded) + 1 > ENTRY_SIZE:
        raise SystemExit("name too long for one Config.inf slot")

    # The dump has slot 0 as: 0x01 + GBK filename + NUL padding at 0x17a.
    # Keep the original slot and place the new one in the next 0x100-byte slot.
    slot = ENTRY_START + ENTRY_SIZE
    if slot + ENTRY_SIZE > TRAILER_OFF:
        raise SystemExit("no room before observed trailer")
    data[slot : slot + ENTRY_SIZE] = b"\0" * ENTRY_SIZE
    data[slot] = 1
    data[slot + 1 : slot + 1 + len(encoded)] = encoded

    # Low-risk guesses: header word 0 is an item count in the low half on this dump,
    # and word at 0x18 is also 1. Update only the obvious count first.
    data[0:2] = (2).to_bytes(2, "little")
    checksum = sum(data[:TRAILER_OFF]) & 0xFFFFFFFF
    data[TRAILER_OFF : TRAILER_OFF + 4] = checksum.to_bytes(4, "little")

    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"wrote {ns.output}")
    print(f"slot=0x{slot:x} name={ns.name}")
    print(f"checksum=0x{checksum:x}")


if __name__ == "__main__":
    main()
