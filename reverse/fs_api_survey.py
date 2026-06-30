from __future__ import annotations

import argparse
import collections
from pathlib import Path

from bda_api_scan import scan_calls
from bda_layout import analyze
from bda_table_call_scan import find_global_load
from bda_table_globals import detect_globals


def classify_calls(path: Path) -> list[dict[str, int | str]]:
    data = path.read_bytes()
    layout = analyze(path)
    entry = int(layout["entry_offset"])
    base = int(layout["runtime_entry_va"]) - entry
    globals_by_addr = {addr: name for name, addr in detect_globals(path).items()}
    rows = []
    for call in scan_calls(data, entry, len(data)):
        found = find_global_load(data, call["load_off"], call["base_reg"], globals_by_addr)
        table = found[0] if found else "UNKNOWN"
        rows.append({**call, "table": table, "va": base + call["load_off"]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Survey FS table offsets across native BDA apps.")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--offset", type=lambda x: int(x, 0), default=None)
    ap.add_argument("--top", type=int, default=80)
    ns = ap.parse_args()

    total = collections.Counter()
    by_file: dict[str, collections.Counter[int]] = {}
    samples: dict[int, list[tuple[str, int]]] = collections.defaultdict(list)

    for path in sorted(ns.root.rglob("*.bda")):
        if any(part.lower() in {"build", "reverse"} for part in path.parts):
            continue
        try:
            rows = classify_calls(path)
        except Exception as exc:
            print(f"skip {path}: {exc}")
            continue
        counter = collections.Counter()
        for row in rows:
            if row["table"] != "FS":
                continue
            off = int(row["api_offset"])
            counter[off] += 1
            total[off] += 1
            if len(samples[off]) < 12:
                samples[off].append((str(path), int(row["va"])))
        if counter:
            by_file[str(path)] = counter

    if ns.offset is not None:
        off = ns.offset
        print(f"FS +0x{off:03x} total={total[off]}")
        for path, counter in sorted(by_file.items(), key=lambda kv: kv[1][off], reverse=True):
            if counter[off]:
                print(f"{counter[off]:3d}  {path}")
        print("samples:")
        for path, va in samples[off]:
            print(f"  {path} va=0x{va:08x}")
        return

    print("FS offset totals:")
    for off, count in total.most_common(ns.top):
        print(f"  +0x{off:03x}: {count}")
        for path, va in samples[off][:4]:
            print(f"      {path} va=0x{va:08x}")

    print("\nPer-file FS offset counts:")
    for path, counter in sorted(by_file.items()):
        hot = ", ".join(f"+0x{off:03x}:{count}" for off, count in counter.most_common(16))
        print(f"{path}: {hot}")


if __name__ == "__main__":
    main()
