from __future__ import annotations

import argparse
from pathlib import Path

from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

from bda_layout import analyze


def main() -> None:
    ap = argparse.ArgumentParser(description="Preview MIPS32 little-endian code in a BBK .bda file.")
    ap.add_argument("bda", type=Path)
    ap.add_argument("--offset", type=lambda x: int(x, 0), default=None)
    ap.add_argument("--base", type=lambda x: int(x, 0), default=None)
    ap.add_argument("--count", type=int, default=80)
    ns = ap.parse_args()

    layout = analyze(ns.bda)
    offset = ns.offset if ns.offset is not None else layout["entry_offset"]
    entry_va = layout["runtime_entry_va"]
    base = ns.base
    if base is None and offset is not None and entry_va is not None:
        base = int(entry_va) - int(offset)
    if offset is None or base is None:
        raise SystemExit("could not infer code offset/base; pass --offset and --base")

    data = ns.bda.read_bytes()
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)
    addr = int(base) + int(offset)
    for idx, ins in enumerate(md.disasm(data[int(offset) : int(offset) + 0x1000], addr)):
        print(f"{ins.address:08X}: {ins.bytes.hex(' '):<12} {ins.mnemonic:<8} {ins.op_str}")
        if idx + 1 >= ns.count:
            break


if __name__ == "__main__":
    main()
