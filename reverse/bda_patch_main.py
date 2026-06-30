from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs

from bda_layout import analyze


def find_main_offset(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    layout = analyze(path)
    entry = layout["entry_offset"]
    entry_va = layout["runtime_entry_va"]
    if entry is None or entry_va is None:
        raise SystemExit(f"could not infer entry for {path}")
    base = int(entry_va) - int(entry)

    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)
    jals: list[int] = []
    for ins in md.disasm(data[int(entry) : int(entry) + 0x100], int(entry_va)):
        if ins.mnemonic == "jal":
            try:
                jals.append(int(ins.op_str, 16))
            except ValueError:
                pass
    if len(jals) < 2:
        raise SystemExit(f"could not find second startup jal/main in {path}")
    main_va = jals[1]
    return main_va - base, main_va


def main() -> None:
    ap = argparse.ArgumentParser(description="Patch the second startup jal target, usually app main.")
    ap.add_argument("source", type=Path)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--wipe-bytes", type=lambda x: int(x, 0), default=0x300)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    offset, main_va = find_main_offset(ns.template)
    subprocess.check_call(
        [
            sys.executable,
            str(Path(__file__).with_name("native_bda_patch.py")),
            str(ns.source),
            "--template",
            str(ns.template),
            "--offset",
            hex(offset),
            "--wipe-bytes",
            hex(ns.wipe_bytes),
            "-o",
            str(ns.output),
        ]
    )
    print(f"main_offset=0x{offset:x}")
    print(f"main_va=0x{main_va:x}")


if __name__ == "__main__":
    main()
