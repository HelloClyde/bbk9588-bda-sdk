from __future__ import annotations

import argparse
import struct
from pathlib import Path

from capstone import CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32, Cs


TEXT_BASE = 0x80000000
APP_PARAM_TABLE_OFF = 0x281680
APP_PARAM_TABLE_VA = 0x80281680
APP_CODE_VA = 0x81C00020


def find_c200(root: Path) -> Path:
    for path in root.rglob("C200.bin"):
        data = path.read_bytes()[:8]
        if data == bytes.fromhex("00 80 1f 3c 00 40 ff 27"):
            return path
    raise SystemExit("C200.bin with raw MIPS reset stub was not found")


def disasm(data: bytes, va: int, count: int = 24) -> list[str]:
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 + CS_MODE_LITTLE_ENDIAN)
    off = va - TEXT_BASE
    out = []
    for idx, ins in enumerate(md.disasm(data[off : off + 0x300], va)):
        out.append(f"{ins.address:08x}: {ins.bytes.hex(' '):<12} {ins.mnemonic:<8} {ins.op_str}")
        if idx + 1 >= count:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe BBK 9588 system bin for native BDA loader evidence.")
    ap.add_argument("--root", type=Path, default=Path("."))
    ns = ap.parse_args()

    path = find_c200(ns.root)
    data = path.read_bytes()
    print(f"system_bin={path}")
    print(f"text_base=0x{TEXT_BASE:08x}")
    print(f"native_bda_code_va=0x{APP_CODE_VA:08x}")
    print()

    words = struct.unpack_from("<8I", data, APP_PARAM_TABLE_OFF)
    print(f"8 words copied from VA 0x{APP_PARAM_TABLE_VA:08x} to 0x81c00000:")
    for idx, word in enumerate(words):
        print(f"  0x81c000{idx * 4:02x}: 0x{word:08x}")
    print()

    print("copy 8-word helper table:")
    print("\n".join(disasm(data, 0x80027330, 14)))
    print()

    print("load BDA bytes to 0x81c00020 and call it:")
    print("\n".join(disasm(data, 0x80028764, 18)))
    print()

    print("second BDA launch path:")
    print("\n".join(disasm(data, 0x800289b0, 16)))


if __name__ == "__main__":
    main()
