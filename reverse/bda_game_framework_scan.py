from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

from bda_api_scan import scan_calls
from bda_layout import analyze
from bda_table_call_scan import find_global_load
from bda_table_globals import detect_globals


SP = 29
RA = 31


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def decode_i(word: int) -> tuple[int, int, int, int]:
    return (word >> 26) & 0x3F, (word >> 21) & 0x1F, (word >> 16) & 0x1F, word & 0xFFFF


def signed16(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def is_function_prologue(data: bytes, offset: int) -> bool:
    op, rs, rt, imm = decode_i(u32(data, offset))
    if op != 0x09 or rs != SP or rt != SP or signed16(imm) >= 0:
        return False
    for pos in range(offset + 4, min(offset + 0x30, len(data) - 4), 4):
        save_op, save_rs, save_rt, _save_imm = decode_i(u32(data, pos))
        if save_op == 0x2B and save_rs == SP and save_rt == RA:
            return True
    return False


def find_function_start(data: bytes, offset: int, lower_bound: int) -> int:
    for pos in range(offset & ~3, max(lower_bound, offset - 0x500) - 1, -4):
        if is_function_prologue(data, pos):
            # GCC commonly materializes the first table/global pointer before
            # reserving the stack frame: lui; lw/addiu; addiu sp,sp,-N.
            if pos >= lower_bound + 8 and (u32(data, pos - 8) >> 26) == 0x0F:
                return pos - 8
            if pos >= lower_bound + 4 and (u32(data, pos - 4) >> 26) == 0x0F:
                return pos - 4
            return pos
    return offset


def next_prologue(data: bytes, start: int, upper_bound: int) -> int:
    for pos in range(start + 0x10, min(upper_bound, len(data) - 4), 4):
        if is_function_prologue(data, pos):
            return pos
    return min(upper_bound, len(data))


def absolute_stores(data: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    stores = []
    hi_by_reg: dict[int, int] = {}
    for pos in range(start, min(end, len(data) - 4), 4):
        op, rs, rt, imm = decode_i(u32(data, pos))
        if op == 0x0F:
            hi_by_reg[rt] = imm << 16
            continue
        if op == 0x2B and rs in hi_by_reg:
            address = (hi_by_reg[rs] + signed16(imm)) & 0xFFFFFFFF
            stores.append((pos, rt, address))
    return stores


def has_output_triplet(data: bytes, start: int, end: int) -> bool:
    offsets_by_base: dict[int, set[int]] = {}
    for pos in range(start, min(end, len(data) - 4), 4):
        op, rs, _rt, imm = decode_i(u32(data, pos))
        if op == 0x2B and imm in {0, 4, 8}:
            offsets_by_base.setdefault(rs, set()).add(imm)
    return any(offsets == {0, 4, 8} for offsets in offsets_by_base.values())


def analyze_game_framework(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    layout = analyze(path)
    entry = int(layout["entry_offset"])
    base = int(layout["runtime_entry_va"]) - entry
    table_globals = detect_globals(path)
    globals_by_address = {address: name for name, address in table_globals.items()}

    gui_calls = []
    for call in scan_calls(data, entry, len(data)):
        found = find_global_load(data, call["load_off"], call["base_reg"], globals_by_address)
        if found and found[0] == "GUI":
            start = find_function_start(data, call["load_off"], entry)
            gui_calls.append({**call, "function_start": start})

    calls_by_function: dict[int, set[int]] = {}
    for call in gui_calls:
        calls_by_function.setdefault(call["function_start"], set()).add(call["api_offset"])

    root_required = {0x04C, 0x088, 0x08C, 0x304, 0x30C}
    root_candidates = [
        start for start, offsets in calls_by_function.items() if root_required.issubset(offsets)
    ]
    root_start = root_candidates[0] if root_candidates else None

    root = None
    if root_start is not None:
        stores = absolute_stores(data, root_start, root_start + 0x200)
        message_slots = [address for _pos, source, address in stores if source == 5]
        handle_slots = [address for _pos, source, address in stores if source == 4]
        draw_slots = [address for _pos, source, address in stores if source == 2]
        bridge = message_slots[0] if message_slots else None
        root = {
            "wndproc_va": base + root_start,
            "event_bridge_va": bridge,
            "wparam_slot_va": bridge + 4 if bridge is not None else None,
            "lparam_slot_va": bridge + 8 if bridge is not None else None,
            "root_handle_va": handle_slots[0] if handle_slots else None,
            "current_draw_va": draw_slots[-1] if draw_slots else None,
        }

    pump_required = {0x030, 0x050, 0x054}
    pump_functions = [
        start for start, offsets in calls_by_function.items() if pump_required.issubset(offsets)
    ]
    fetch_functions = [
        start
        for start in pump_functions
        if has_output_triplet(data, start, next_prologue(data, start, start + 0x180))
    ]

    registration_calls = sorted(
        {
            (base + call["load_off"], base + call["function_start"])
            for call in gui_calls
            if call["api_offset"] == 0x084
        }
    )

    return {
        "path": str(path),
        "runtime_file_base": base,
        "table_globals": table_globals,
        "root": root,
        "event_pump_functions": [base + start for start in sorted(set(pump_functions))],
        "event_fetch_functions": [base + start for start in sorted(set(fetch_functions))],
        "frame_registration_calls": [
            {"call_va": call_va, "function_va": function_va}
            for call_va, function_va in registration_calls
        ],
    }


def format_address(value: object) -> str:
    return "-" if value is None else f"0x{int(value):08x}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recover the common static game window/event framework from an original BDA."
    )
    parser.add_argument("bda", type=Path, nargs="+")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    reports = [analyze_game_framework(path) for path in args.bda]
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
        return

    for report in reports:
        print(report["path"])
        root = report["root"]
        if isinstance(root, dict):
            print(
                "  root wndproc={wndproc} bridge={bridge}/{wparam}/{lparam} "
                "handle={handle} draw={draw}".format(
                    wndproc=format_address(root["wndproc_va"]),
                    bridge=format_address(root["event_bridge_va"]),
                    wparam=format_address(root["wparam_slot_va"]),
                    lparam=format_address(root["lparam_slot_va"]),
                    handle=format_address(root["root_handle_va"]),
                    draw=format_address(root["current_draw_va"]),
                )
            )
        else:
            print("  root wndproc: not found")
        pumps = ", ".join(format_address(value) for value in report["event_pump_functions"])
        fetches = ", ".join(format_address(value) for value in report["event_fetch_functions"])
        print(f"  pump functions: {pumps or '-'}")
        print(f"  bridge fetch functions: {fetches or '-'}")
        for registration in report["frame_registration_calls"]:
            print(
                f"  GUI+0x084 call={format_address(registration['call_va'])} "
                f"function={format_address(registration['function_va'])}"
            )


if __name__ == "__main__":
    main()
