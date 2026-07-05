"""Parsing, inspection, and address helpers for the BBK 9588 hardware emulator."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

try:
    from capstone import CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN, Cs
except Exception:  # pragma: no cover - optional local dependency
    Cs = None

from emu.core.defs import (
    GPIO_KEY_CODE_BITS,
    GPIO_KEY_IDLE_LEVELS,
    RAM_BASE,
    GuiKeyEvent,
    GuiTouchEvent,
    MmioAccess,
    MmioLevel,
    MmioPulse,
    ScheduledCall,
    ScheduledKeyControllerEvent,
    ScheduledPoke,
    ScheduledTouchControllerEvent,
    StopInputNodeCondition,
    TouchSample,
    WatchRange,
)

def disasm_head(data: bytes, base: int, count: int) -> list[dict[str, str | int]]:
    if Cs is None:
        return []
    md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
    rows = []
    for ins in md.disasm(data[: count * 4], base):
        rows.append({"addr": f"0x{ins.address:08x}", "mnemonic": ins.mnemonic, "op_str": ins.op_str})
        if len(rows) >= count:
            break
    return rows


def inspect_image(path: Path, base: int, count: int) -> dict[str, object]:
    data = path.read_bytes()
    words = [f"0x{struct.unpack_from('<I', data, i)[0]:08x}" for i in range(0, min(0x40, len(data)), 4)]
    return {
        "path": str(path),
        "size": len(data),
        "base": f"0x{base:08x}",
        "first_words_le": words,
        "disasm": disasm_head(data, base, count),
    }


def access_to_dict(a: MmioAccess) -> dict[str, object]:
    return {
        "pc": f"0x{a.pc:08x}",
        "kind": a.kind,
        "addr": f"0x{a.addr:08x}",
        "size": a.size,
        "value": None if a.value is None else f"0x{a.value:x}",
    }


def va_to_phys(va: int) -> int:
    if va >= RAM_BASE:
        return va & 0x1FFFFFFF
    return va


def parse_watch_range(text: str) -> WatchRange:
    name = text
    spec = text
    if "=" in text:
        name, spec = text.split("=", 1)
    if ":" not in spec:
        raise argparse.ArgumentTypeError("watch range must be addr:size or name=addr:size")
    addr_s, size_s = spec.split(":", 1)
    va = int(addr_s, 0)
    size = int(size_s, 0)
    if size <= 0:
        raise argparse.ArgumentTypeError("watch range size must be positive")
    return WatchRange(name=name, va=va, size=size, phys=va_to_phys(va))


def parse_stop_input_node(text: str) -> StopInputNodeCondition:
    pc: int | None = None
    spec = text
    if "@" in spec:
        spec, pc_s = spec.rsplit("@", 1)
        pc = int(pc_s, 0)
    parts = spec.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("input node stop must be va:callback:min_status_3c[@pc]")
    va = int(parts[0], 0)
    callback = int(parts[1], 0)
    min_status_3c = int(parts[2], 0)
    if not 0 <= min_status_3c <= 0xFF:
        raise argparse.ArgumentTypeError("min_status_3c must fit in one byte")
    return StopInputNodeCondition(va=va, callback=callback, min_status_3c=min_status_3c, pc=pc)


def parse_page_range(text: str) -> tuple[int, int]:
    if ":" not in text:
        raise argparse.ArgumentTypeError("page range must be start:end")
    start_s, end_s = text.split(":", 1)
    start = int(start_s, 0)
    end = int(end_s, 0)
    if start < 0 or end <= start:
        raise argparse.ArgumentTypeError("page range must be a positive half-open range start:end")
    return start, end


def parse_scheduled_poke(text: str) -> ScheduledPoke:
    spec = text
    idle_hit = 1
    if "@" in spec:
        spec, hit_s = spec.rsplit("@", 1)
        idle_hit = int(hit_s, 0)
    parts = spec.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("poke must be addr:size:value[@idle_hit]")
    va = int(parts[0], 0)
    size = int(parts[1], 0)
    value = int(parts[2], 0)
    if size not in (1, 2, 4):
        raise argparse.ArgumentTypeError("poke size must be 1, 2, or 4")
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("idle_hit must be positive")
    return ScheduledPoke(va=va, size=size, value=value, idle_hit=idle_hit, phys=va_to_phys(va))


def parse_scheduled_call(text: str) -> ScheduledCall:
    spec = text
    idle_hit = 1
    if "@" in spec:
        spec, hit_s = spec.rsplit("@", 1)
        idle_hit = int(hit_s, 0)
    parts = spec.split(":")
    if not 1 <= len(parts) <= 5:
        raise argparse.ArgumentTypeError("call must be addr[:a0[:a1[:a2[:a3]]]][@idle_hit]")
    va = int(parts[0], 0)
    args = [0, 0, 0, 0]
    for idx, value in enumerate(parts[1:]):
        args[idx] = int(value, 0)
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("idle_hit must be positive")
    return ScheduledCall(va=va, args=tuple(args), idle_hit=idle_hit)


def parse_touch_sample(text: str) -> TouchSample:
    if "@" not in text:
        raise argparse.ArgumentTypeError("touch sample must be x:y:down@idle_hit or x:y:down@pc:addr")
    body, hit_s = text.split("@", 1)
    parts = body.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("touch sample must be x:y:down@idle_hit or x:y:down@pc:addr")
    x = int(parts[0], 0)
    y = int(parts[1], 0)
    down = bool(int(parts[2], 0))
    pc_hit = None
    if hit_s.lower().startswith("pc:"):
        idle_hit = 0
        pc_hit = int(hit_s.split(":", 1)[1], 0)
    else:
        idle_hit = int(hit_s, 0)
    if not (0 <= x < 240 and 0 <= y < 320):
        raise argparse.ArgumentTypeError("touch coordinates must be inside 240x320 portrait screen")
    if pc_hit is None and idle_hit <= 0:
        raise argparse.ArgumentTypeError("idle_hit must be positive")
    return TouchSample(x=x, y=y, down=down, idle_hit=idle_hit, pc_hit=pc_hit)


def parse_touch_state(text: str) -> tuple[int, int, bool]:
    parts = text.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("touch state must be x:y:down")
    x = int(parts[0], 0)
    y = int(parts[1], 0)
    down = bool(int(parts[2], 0))
    if not (0 <= x < 240 and 0 <= y < 320):
        raise argparse.ArgumentTypeError("touch coordinates must be inside 240x320 portrait screen")
    return x, y, down


def parse_touch_controller_event(text: str) -> ScheduledTouchControllerEvent:
    if "@" not in text:
        raise argparse.ArgumentTypeError("touch controller event must be x:y:down@idle_hit")
    body, hit_s = text.split("@", 1)
    parts = body.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("touch controller event must be x:y:down@idle_hit")
    x = int(parts[0], 0)
    y = int(parts[1], 0)
    down = bool(int(parts[2], 0))
    idle_hit = int(hit_s, 0)
    if not (0 <= x < 240 and 0 <= y < 320):
        raise argparse.ArgumentTypeError("touch coordinates must be inside 240x320 portrait screen")
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("idle_hit must be positive")
    return ScheduledTouchControllerEvent(x=x, y=y, down=down, idle_hit=idle_hit)


def parse_key_controller_event(text: str) -> ScheduledKeyControllerEvent:
    if "@" not in text:
        raise argparse.ArgumentTypeError("key controller event must be code:down@idle_hit")
    body, hit_s = text.split("@", 1)
    parts = body.split(":")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("key controller event must be code:down@idle_hit")
    code = int(parts[0], 0)
    down = bool(int(parts[1], 0))
    idle_hit = int(hit_s, 0)
    if code not in GPIO_KEY_CODE_BITS:
        known = ", ".join(str(value) for value in sorted(GPIO_KEY_CODE_BITS))
        raise argparse.ArgumentTypeError(f"unknown key code {code}; known codes: {known}")
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("idle_hit must be positive")
    return ScheduledKeyControllerEvent(code=code, down=down, idle_hit=idle_hit)


def parse_gui_key_event(text: str) -> GuiKeyEvent:
    if "@" not in text:
        raise argparse.ArgumentTypeError("GUI key event must be code@idle_hit")
    code_s, hit_s = text.split("@", 1)
    code = int(code_s, 0)
    idle_hit = int(hit_s, 0)
    if not 0 <= code <= 0xFF:
        raise argparse.ArgumentTypeError("GUI key code must fit in one byte")
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("idle_hit must be positive")
    return GuiKeyEvent(code=code, idle_hit=idle_hit)


def parse_gui_touch_event(text: str) -> GuiTouchEvent:
    if "@" not in text:
        raise argparse.ArgumentTypeError("GUI touch event must be x:y:down@idle_hit")
    body, hit_s = text.split("@", 1)
    parts = body.split(":")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("GUI touch event must be x:y:down@idle_hit")
    x = int(parts[0], 0)
    y = int(parts[1], 0)
    down = bool(int(parts[2], 0))
    idle_hit = int(hit_s, 0)
    if not (0 <= x < 240 and 0 <= y < 320):
        raise argparse.ArgumentTypeError("GUI touch coordinates must be inside 240x320 portrait screen")
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("idle_hit must be positive")
    return GuiTouchEvent(x=x, y=y, down=down, idle_hit=idle_hit)


def parse_mmio_level(text: str) -> MmioLevel:
    if ":" not in text:
        raise argparse.ArgumentTypeError("MMIO level must be addr:value")
    addr_s, value_s = text.split(":", 1)
    addr = int(addr_s, 0)
    value = int(value_s, 0)
    if not (0x10000000 <= addr < 0x14000000):
        raise argparse.ArgumentTypeError("MMIO level address must be physical MMIO, e.g. 0x10010100")
    return MmioLevel(addr=addr, value=value)


def parse_mmio_pulse(text: str) -> MmioPulse:
    if "@" not in text:
        raise argparse.ArgumentTypeError("MMIO pulse must be addr:value@idle_hit[:reads]")
    level_s, schedule_s = text.split("@", 1)
    if ":" not in level_s:
        raise argparse.ArgumentTypeError("MMIO pulse must be addr:value@idle_hit[:reads]")
    addr_s, value_s = level_s.split(":", 1)
    schedule_parts = schedule_s.split(":")
    if not 1 <= len(schedule_parts) <= 2:
        raise argparse.ArgumentTypeError("MMIO pulse must be addr:value@idle_hit[:reads]")
    addr = int(addr_s, 0)
    value = int(value_s, 0)
    idle_hit = int(schedule_parts[0], 0)
    read_count = int(schedule_parts[1], 0) if len(schedule_parts) == 2 else 1
    if not (0x10000000 <= addr < 0x14000000):
        raise argparse.ArgumentTypeError("MMIO pulse address must be physical MMIO, e.g. 0x10010100")
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("MMIO pulse idle_hit must be positive")
    if read_count <= 0:
        raise argparse.ArgumentTypeError("MMIO pulse reads must be positive")
    return MmioPulse(addr=addr, value=value, idle_hit=idle_hit, read_count=read_count)


def parse_key_pulse(text: str) -> MmioPulse:
    if "@" not in text:
        raise argparse.ArgumentTypeError("key pulse must be code@idle_hit[:reads]")
    code_s, schedule_s = text.split("@", 1)
    schedule_parts = schedule_s.split(":")
    if not 1 <= len(schedule_parts) <= 2:
        raise argparse.ArgumentTypeError("key pulse must be code@idle_hit[:reads]")
    code = int(code_s, 0)
    idle_hit = int(schedule_parts[0], 0)
    read_count = int(schedule_parts[1], 0) if len(schedule_parts) == 2 else 4
    if code not in GPIO_KEY_CODE_BITS:
        known = ", ".join(str(value) for value in sorted(GPIO_KEY_CODE_BITS))
        raise argparse.ArgumentTypeError(f"unknown key code {code}; known codes: {known}")
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("key pulse idle_hit must be positive")
    if read_count <= 0:
        raise argparse.ArgumentTypeError("key pulse reads must be positive")
    addr, mask = GPIO_KEY_CODE_BITS[code]
    idle_value = GPIO_KEY_IDLE_LEVELS.get(addr, 0)
    if addr == 0x10010200:
        idle_value |= 0x40000000
    return MmioPulse(addr=addr, value=idle_value & ~mask, idle_hit=idle_hit, read_count=read_count)


def cli_option_provided(argv: list[str], option: str) -> bool:
    return any(arg == option or arg.startswith(option + "=") for arg in argv)


def find_workspace_file(name: str) -> Path:
    matches = sorted(path for path in Path(".").rglob(name) if path.is_file())
    if not matches:
        raise FileNotFoundError(f"could not find {name!r} under current workspace")
    return matches[0]
