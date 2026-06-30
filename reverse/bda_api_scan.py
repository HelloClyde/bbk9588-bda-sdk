from __future__ import annotations

import argparse
import collections
import json
import struct
from pathlib import Path

from bda_layout import ENTRY_SIG


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from("<I", data, off)[0]


def is_jalr_reg(word: int, reg: int) -> bool:
    return (word & 0xFC1FFFFF) == 0x0000F809 and ((word >> 21) & 31) == reg


def scan_calls(data: bytes, start: int, end: int) -> list[dict[str, int]]:
    calls = []
    for off in range(start, min(end, len(data) - 8), 4):
        word = u32(data, off)
        if (word >> 26) != 0x23:
            continue
        base = (word >> 21) & 31
        target = (word >> 16) & 31
        imm = word & 0xFFFF
        if imm >= 0x500 or imm % 4:
            continue
        for jalr_off in range(off + 4, min(off + 28, len(data) - 4), 4):
            if is_jalr_reg(u32(data, jalr_off), target):
                calls.append(
                    {
                        "load_off": off,
                        "jalr_off": jalr_off,
                        "base_reg": base,
                        "target_reg": target,
                        "api_offset": imm,
                    }
                )
                break
    return calls


def main() -> None:
    ap = argparse.ArgumentParser(description="Scan native BDA files for indirect API-table calls.")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--json", action="store_true")
    ns = ap.parse_args()

    report = []
    total = collections.Counter()
    for path in sorted(ns.root.rglob("*.bda")):
        if any(part.lower() in {"build", "reverse"} for part in path.parts):
            continue
        data = path.read_bytes()
        entry = data.find(ENTRY_SIG)
        if entry < 0:
            continue
        calls = scan_calls(data, entry, len(data))
        if not calls:
            continue
        counts = collections.Counter(c["api_offset"] for c in calls)
        total.update(counts)
        report.append(
            {
                "path": str(path),
                "entry_offset": entry,
                "call_count": len(calls),
                "offset_counts": {f"0x{k:x}": v for k, v in sorted(counts.items())},
                "samples": [
                    {
                        **c,
                        "load_off": f"0x{c['load_off']:x}",
                        "jalr_off": f"0x{c['jalr_off']:x}",
                        "api_offset": f"0x{c['api_offset']:x}",
                    }
                    for c in calls[:24]
                ],
            }
        )

    if ns.json:
        print(json.dumps({"files": report, "total": {f"0x{k:x}": v for k, v in total.items()}}, indent=2))
        return

    print("Total API-table offset use:")
    for offset, count in total.most_common(40):
        print(f"  +0x{offset:03x}: {count}")
    print()
    for item in report:
        print(f"{item['path']}: {item['call_count']} indirect calls")
        hot = sorted(item["offset_counts"].items(), key=lambda kv: int(kv[0], 16))[:20]
        print("  " + ", ".join(f"{k}:{v}" for k, v in hot))


if __name__ == "__main__":
    main()
