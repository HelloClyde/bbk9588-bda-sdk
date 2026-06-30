from __future__ import annotations

import argparse
from pathlib import Path


XOR_KEY = 0x44525744
CHECKSUM_XOR_KEY = 0x322D464B
CHECKSUM_OFF = 0x84


def decoded_header_sum(data: bytes) -> int:
    buf = bytearray(data[:CHECKSUM_OFF])
    for off in range(0, 0x2C, 4):
        v = int.from_bytes(buf[off : off + 4], "little") ^ XOR_KEY
        buf[off : off + 4] = v.to_bytes(4, "little")
    return sum(buf) & 0xFFFFFFFF


def main() -> None:
    ap = argparse.ArgumentParser(description="Patch the observed BDA header checksum word at 0x84.")
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument(
        "--mode",
        choices=["exact", "xor-template", "delta-template", "low16-delta"],
        default="exact",
        help="exact uses the verified firmware formula; heuristic modes are kept for comparison.",
    )
    ap.add_argument("--template", type=Path, required=True)
    ns = ap.parse_args()

    data = bytearray(ns.input.read_bytes())
    templ = ns.template.read_bytes()

    new_sum = decoded_header_sum(data)
    templ_sum = decoded_header_sum(templ)
    templ_raw = int.from_bytes(templ[CHECKSUM_OFF : CHECKSUM_OFF + 4], "little")

    if ns.mode == "exact":
        patched = new_sum ^ CHECKSUM_XOR_KEY
    elif ns.mode == "xor-template":
        key = templ_raw ^ templ_sum
        patched = new_sum ^ key
    elif ns.mode == "delta-template":
        delta = (templ_raw - templ_sum) & 0xFFFFFFFF
        patched = (new_sum + delta) & 0xFFFFFFFF
    else:
        delta = ((templ_raw & 0xFFFF) - (templ_sum & 0xFFFF)) & 0xFFFF
        patched = (templ_raw & 0xFFFF0000) | ((new_sum + delta) & 0xFFFF)

    data[CHECKSUM_OFF : CHECKSUM_OFF + 4] = patched.to_bytes(4, "little")
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)

    print(f"output={ns.output}")
    print(f"mode={ns.mode}")
    print(f"template_sum=0x{templ_sum:x} template_raw=0x{templ_raw:08x}")
    print(f"new_sum=0x{new_sum:x} patched_raw84=0x{patched:08x}")


if __name__ == "__main__":
    main()
