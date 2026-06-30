from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from bda_layout import analyze, find_entry


JR_RA = bytes.fromhex("08 00 e0 03")
NOP = bytes.fromhex("00 00 00 00")


def pick_template_by_size(root: Path, size: int) -> Path:
    matches = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() == ".bda" and p.stat().st_size == size
    ]
    matches = [
        p
        for p in matches
        if find_entry(p.read_bytes()) is not None and analyze(p)["load_base"] is not None
    ]
    if not matches:
        raise SystemExit(f"no .bda with size {size} found under {root}")
    return matches[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Create a minimal native BDA by patching a template entry point.")
    ap.add_argument("--template", type=Path, help="Template .bda. If omitted, --template-size is used.")
    ap.add_argument("--root", type=Path, default=Path("."), help="Root for --template-size search.")
    ap.add_argument("--template-size", type=int, default=185868, help="Default picks the calculator-sized BDA.")
    ap.add_argument("-o", "--output", type=Path, default=Path("build/native_noop.bda"))
    ap.add_argument("--wipe-bytes", type=lambda x: int(x, 0), default=0x100, help="Bytes to NOP after entry.")
    ns = ap.parse_args()

    template = ns.template or pick_template_by_size(ns.root, ns.template_size)
    data = bytearray(template.read_bytes())
    entry = find_entry(data)
    if entry is None:
        raise SystemExit(f"could not find standard BDA entry signature in {template}")

    wipe = max(8, ns.wipe_bytes)
    wipe = min(wipe, len(data) - entry)
    data[entry : entry + wipe] = NOP * (wipe // 4)
    data[entry : entry + 8] = JR_RA + NOP

    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"template={template}")
    print(f"output={ns.output}")
    print(f"entry_offset=0x{entry:x}")
    print("entry_code=jr $ra; nop")


if __name__ == "__main__":
    main()
