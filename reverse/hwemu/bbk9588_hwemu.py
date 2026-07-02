#!/usr/bin/env python3
"""Early BBK 9588/JZ4740 hardware emulator harness.

This is a hardware-level trace harness, not a BDA API shim. It loads a raw MIPS
system image, maps RAM, executes from reset when Unicorn is available, and logs
unimplemented MMIO accesses. The emulator should grow from concrete traces only.
"""

from __future__ import annotations

import argparse
import json
import pickle
import struct
import sys
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path

try:
    from capstone import CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN, Cs
except Exception:  # pragma: no cover - optional local dependency
    Cs = None

try:
    from unicorn import Uc, UcError, UC_ARCH_MIPS, UC_MODE_32, UC_MODE_LITTLE_ENDIAN
    from unicorn import UC_HOOK_BLOCK, UC_HOOK_CODE, UC_HOOK_MEM_INVALID, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn import UC_MEM_READ, UC_MEM_WRITE
    from unicorn import UC_MEM_FETCH_UNMAPPED, UC_MEM_READ_UNMAPPED, UC_MEM_WRITE_UNMAPPED
    from unicorn.mips_const import (
        UC_MIPS_REG_0,
        UC_MIPS_REG_1,
        UC_MIPS_REG_2,
        UC_MIPS_REG_3,
        UC_MIPS_REG_4,
        UC_MIPS_REG_5,
        UC_MIPS_REG_6,
        UC_MIPS_REG_7,
        UC_MIPS_REG_8,
        UC_MIPS_REG_9,
        UC_MIPS_REG_10,
        UC_MIPS_REG_11,
        UC_MIPS_REG_12,
        UC_MIPS_REG_13,
        UC_MIPS_REG_14,
        UC_MIPS_REG_15,
        UC_MIPS_REG_16,
        UC_MIPS_REG_17,
        UC_MIPS_REG_18,
        UC_MIPS_REG_19,
        UC_MIPS_REG_20,
        UC_MIPS_REG_21,
        UC_MIPS_REG_22,
        UC_MIPS_REG_23,
        UC_MIPS_REG_24,
        UC_MIPS_REG_25,
        UC_MIPS_REG_26,
        UC_MIPS_REG_27,
        UC_MIPS_REG_28,
        UC_MIPS_REG_29,
        UC_MIPS_REG_30,
        UC_MIPS_REG_31,
        UC_MIPS_REG_CP0_STATUS,
        UC_MIPS_REG_HI,
        UC_MIPS_REG_LO,
        UC_MIPS_REG_PC,
        UC_MIPS_REG_SP,
    )
except Exception:  # pragma: no cover - optional local dependency
    Uc = None


RAM_BASE = 0x80000000
PHYS_RAM_BASE = 0x00000000
KSEG1_BASE = 0xA0000000
MMIO_BASE = 0xB0000000
PHYS_MMIO_BASE = 0x10000000
MMIO_SIZE = 0x04000000
EXT_BANK_BASE = 0x18000000
EXT_BANK_KSEG1_BASE = 0xB8000000
EXT_BANK_SIZE = 0x02000000

GPIO_KEY_IDLE_LEVELS = {
    0x10010100: 0x78040000,
    0x10010200: 0x08000000,
    0x10010300: 0x20200000,
}

TOUCH_PEN_GPIO_ADDR = 0x10010200
TOUCH_PEN_GPIO_BIT = 0x08000000
TOUCH_PEN_GPIO_LEVELS = (
    (0x10010200, 0x08000000),
    (0x10010100, 0x00040000),
)
SADC_BASE = 0x10070000
SADC_STATUS = SADC_BASE + 0x0C
SADC_TOUCH_DATA = SADC_BASE + 0x18
SADC_DATA = SADC_BASE + 0x1C

GPIO_KEY_CODE_BITS = {
    # Return code from the scanner at 0x8001b464 -> active-low GPIO bit.
    10: (0x10010100, 0x40000000),
    5: (0x10010100, 0x10000000),
    7: (0x10010100, 0x08000000),
    6: (0x10010100, 0x20000000),
    9: (0x10010200, 0x08000000),
    4: (0x10010300, 0x00200000),
}

BDA_ENTRY_SIG = bytes.fromhex("e8 ff bd 27 10 00 bf af")
BDA_RUNTIME_TABLE_SRC = 0x80281680
BDA_RUNTIME_TABLE_DST = 0x81C00000
BDA_RUNTIME_ENTRY_VA = 0x81C00020
BDA_RETURN_PC = 0x80008A8C
BDA_DISPLAY_CALLBACK_TABLE = 0x8046A510

ASCII_5X7_FONT = {
    " ": (0, 0, 0, 0, 0, 0, 0),
    "!": (0x04, 0x04, 0x04, 0x04, 0x04, 0, 0x04),
    "-": (0, 0, 0, 0x1F, 0, 0, 0),
    ".": (0, 0, 0, 0, 0, 0x0C, 0x0C),
    ":": (0, 0x0C, 0x0C, 0, 0x0C, 0x0C, 0),
    "0": (0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E),
    "1": (0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "2": (0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F),
    "3": (0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E),
    "4": (0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02),
    "5": (0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E),
    "6": (0x0E, 0x10, 0x10, 0x1E, 0x11, 0x11, 0x0E),
    "7": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08),
    "8": (0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E),
    "9": (0x0E, 0x11, 0x11, 0x0F, 0x01, 0x01, 0x0E),
    "A": (0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "B": (0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E),
    "C": (0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E),
    "D": (0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E),
    "E": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F),
    "F": (0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10),
    "G": (0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F),
    "H": (0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11),
    "I": (0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E),
    "J": (0x01, 0x01, 0x01, 0x01, 0x11, 0x11, 0x0E),
    "K": (0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11),
    "L": (0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F),
    "M": (0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11),
    "N": (0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11),
    "O": (0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "P": (0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10),
    "Q": (0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D),
    "R": (0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11),
    "S": (0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E),
    "T": (0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04),
    "U": (0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E),
    "V": (0x11, 0x11, 0x11, 0x11, 0x0A, 0x0A, 0x04),
    "W": (0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11),
    "X": (0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11),
    "Y": (0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04),
    "Z": (0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F),
}


@dataclass
class MmioAccess:
    pc: int
    kind: str
    addr: int
    size: int
    value: int | None = None


@dataclass
class TraceState:
    image: Path
    base: int
    pc: int
    ram_size: int
    insn_count: int = 0
    last_pc: int = 0
    mmio: list[MmioAccess] = field(default_factory=list)
    invalid: list[MmioAccess] = field(default_factory=list)
    pcs: list[int] = field(default_factory=list)
    calls: list[dict[str, str]] = field(default_factory=list)
    events: list[dict[str, str]] = field(default_factory=list)
    recoveries: list[str] = field(default_factory=list)
    stop_reason: str | None = None


@dataclass
class WatchRange:
    name: str
    va: int
    size: int
    phys: int
    accesses: list[dict[str, str | int]] = field(default_factory=list)


@dataclass
class ScheduledPoke:
    va: int
    size: int
    value: int
    idle_hit: int
    phys: int
    applied: bool = False


@dataclass
class ScheduledCall:
    va: int
    args: tuple[int, int, int, int]
    idle_hit: int
    return_pc: int = 0x80008A8C
    applied: bool = False
    returned: bool = False


@dataclass
class MmioLevel:
    addr: int
    value: int


@dataclass
class MmioPulse:
    addr: int
    value: int
    idle_hit: int
    read_count: int = 1
    reads_seen: int = 0
    active: bool = False
    expired: bool = False


@dataclass
class FirmwareKeySample:
    code: int
    idle_hit: int
    applied: bool = False
    returned: bool = False


@dataclass
class TouchSample:
    x: int
    y: int
    down: bool
    idle_hit: int
    pc_hit: int | None = None
    applied: bool = False
    returned: bool = False


@dataclass
class ScheduledBdaLaunch:
    path: Path
    idle_hit: int
    applied: bool = False
    returned: bool = False
    entry_offset: int | None = None
    loaded_size: int = 0


@dataclass
class GuiKeyEvent:
    code: int
    idle_hit: int
    applied: bool = False
    pumped: bool = False


@dataclass
class GuiTouchEvent:
    x: int
    y: int
    down: bool
    idle_hit: int
    applied: bool = False
    pumped: bool = False


@dataclass
class ScheduledTouchControllerEvent:
    x: int
    y: int
    down: bool
    idle_hit: int
    applied: bool = False


@dataclass
class ScheduledBdaKeyEvent:
    code: int
    event_hit: int
    event_type: int = 9
    applied: bool = False


@dataclass
class ScheduledBdaEvent:
    event_type: int
    event_hit: int
    word0: int = 0
    word2: int = 0
    word3: int = 0
    applied: bool = False


@dataclass
class ScheduledBdaTouchEvent:
    x: int
    y: int
    down: bool
    event_hit: int
    event_type: int
    applied: bool = False


class Bbk9588HwEmu:
    def __init__(
        self,
        image: Path,
        base: int,
        pc: int,
        ram_size: int,
        trace_limit: int,
        recover_jr: bool,
        profile: str,
        payload: Path | None = None,
        payload_addr: int = 0x80004000,
        idle_stop_hits: int = 256,
        app_idle_stop_hits: int = 0,
        bda_idle_stop_polls: int = 1,
        watch_ranges: list[WatchRange] | None = None,
        scheduled_pokes: list[ScheduledPoke] | None = None,
        scheduled_calls: list[ScheduledCall] | None = None,
        call_stack: int | None = None,
        mmio_levels: list[MmioLevel] | None = None,
        mmio_pulses: list[MmioPulse] | None = None,
        firmware_key_samples: list[FirmwareKeySample] | None = None,
        touch_samples: list[TouchSample] | None = None,
        bda_launches: list[ScheduledBdaLaunch] | None = None,
        gui_key_events: list[GuiKeyEvent] | None = None,
        gui_touch_events: list[GuiTouchEvent] | None = None,
        touch_controller_events: list[ScheduledTouchControllerEvent] | None = None,
        bda_key_events: list[ScheduledBdaKeyEvent] | None = None,
        bda_events: list[ScheduledBdaEvent] | None = None,
        bda_touch_events: list[ScheduledBdaTouchEvent] | None = None,
        trace_pcs: list[int] | None = None,
        stop_pcs: list[int] | None = None,
        nand_image: Path | None = None,
        nand_page_size: int = 2048,
        nand_spare_size: int = 64,
        readonly_nand_page_ranges: list[tuple[int, int]] | None = None,
        block_image: Path | None = None,
        usb_connected: bool = False,
        bda_text_mode: str = "ascii-hook",
        bda_native_glyph_layout: str = "rows-msb-vscale2",
        bda_native_raster_mode: str = "firmware",
        scheduler_tick_clamp: bool = False,
        fs_dir_scan_stop_samples: int = 0,
        fast_hooks: bool = False,
        fast_hook_image_jals: bool = False,
        fast_hook_image_branches: bool = False,
        nand_loop_accelerator: bool = False,
        resource_cache16_accelerator: bool = False,
        raster_copy_accelerator: bool = True,
        glyph_mask_accelerator: bool = True,
        surface_pixel_accelerator: bool = True,
        surface_hline_accelerator: bool = True,
        font_helper_accelerator: bool = False,
        gui_ring_pump: bool = False,
        repeat_prologue_mode: str = "off",
    ):
        if Uc is None:
            raise RuntimeError("unicorn is not installed")
        self.image = image
        self.base = base
        self.pc = pc
        self.ram_size = ram_size
        self.trace_limit = trace_limit
        self.recover_jr = recover_jr
        self.profile = profile
        self.payload = payload
        self.payload_addr = payload_addr
        self.payload_size = payload.stat().st_size if payload is not None else 0
        self.idle_stop_hits = idle_stop_hits
        self.app_idle_stop_hits = app_idle_stop_hits
        self.bda_idle_stop_polls = bda_idle_stop_polls
        self.watch_ranges = watch_ranges or []
        self.watch_accesses: list[dict[str, str | int]] = []
        self.scheduled_pokes = scheduled_pokes or []
        self.poke_events: list[dict[str, str | int]] = []
        self.scheduled_calls = scheduled_calls or []
        self.call_stack = call_stack if call_stack is not None else RAM_BASE + ram_size - 0x1000
        self.call_events: list[dict[str, str | int]] = []
        self.mmio_read_levels = {level.addr: level.value for level in (mmio_levels or [])}
        self.mmio_pulses = mmio_pulses or []
        self.mmio_pulse_events: list[dict[str, str | int]] = []
        self.firmware_key_samples = firmware_key_samples or []
        self.pending_forced_scan_code: int | None = None
        self.firmware_key_events: list[dict[str, str | int]] = []
        self.touch_samples = touch_samples or []
        self.pending_touch_sample: TouchSample | None = None
        self.touch_sample_events: list[dict[str, str | int]] = []
        self.bda_launches = bda_launches or []
        self.bda_launch_events: list[dict[str, str | int]] = []
        self.gui_key_events = gui_key_events or []
        self.gui_key_event_log: list[dict[str, str | int]] = []
        self.gui_touch_events = gui_touch_events or []
        self.gui_touch_event_log: list[dict[str, str | int]] = []
        self.touch_controller_events = touch_controller_events or []
        self.touch_controller_event_log: list[dict[str, str | int]] = []
        self.touch_controller_poll_hits = 0
        self.bda_key_events = bda_key_events or []
        self.bda_key_event_log: list[dict[str, str | int]] = []
        self.bda_events = bda_events or []
        self.bda_event_log: list[dict[str, str | int]] = []
        self.bda_touch_events = bda_touch_events or []
        self.bda_touch_event_log: list[dict[str, str | int]] = []
        self.trace_pcs = set(trace_pcs or [])
        self.stop_pcs = set(stop_pcs or [])
        self.trace_pc_counts = {pc: 0 for pc in self.trace_pcs}
        self.trace_pc_hits: list[dict[str, str | int]] = []
        self.gpio_idle_levels = dict(GPIO_KEY_IDLE_LEVELS)
        self.recent_gpio_accesses: list[dict[str, str | int]] = []
        self.recent_intc_accesses: list[dict[str, str | int]] = []
        self.nand_cmd = 0
        self.nand_addr_bytes: list[int] = []
        self.nand_read_id = [0xEC, 0xDA, 0x10, 0x95, 0x44]
        self.nand_data = bytearray(nand_image.read_bytes()) if nand_image is not None else None
        self.nand_image = nand_image
        self.nand_legacy_erased = nand_image is None
        self.nand_page_size = nand_page_size
        self.nand_spare_size = nand_spare_size
        self.readonly_nand_page_ranges = readonly_nand_page_ranges or []
        self.nand_read_buffer = b"\xFF" * 4
        self.nand_read_index = 0
        self.nand_busy_reads = 0
        self.nand_reads: list[dict[str, str | int]] = []
        self.nand_data_window_reads: list[dict[str, str | int]] = []
        self.nand_data_window_read_count = 0
        self.nand_latch_writes: list[dict[str, str | int]] = []
        self.nand_current_page = 0
        self.nand_current_column = 0
        self.nand_current_offset = 0
        self.nand_last_oob_page: int | None = None
        self.nand_program_buffer = bytearray()
        self.nand_program_page = 0
        self.nand_program_column = 0
        self.nand_program_writes: list[dict[str, str | int]] = []
        self.nand_erase_events: list[dict[str, str | int]] = []
        self.nand_erase_count = 0
        self.nand_page_overrides: dict[int, bytes] = {}
        self.block_image = block_image
        self.block_data = bytearray(block_image.read_bytes()) if block_image is not None else None
        self.block_sector_overrides: dict[int, bytes] = {}
        self.usb_connected = usb_connected
        self.recent_udc_accesses: list[dict[str, str | int]] = []
        self.touch_x = 0
        self.touch_y = 0
        self.touch_down = False
        self.sadc_next_axis = 0
        self.sadc_status_event = 0
        self.sadc_conversion_events_remaining = 0
        self.recent_sadc_accesses: list[dict[str, str | int]] = []
        self.bda_text_mode = bda_text_mode
        self.bda_native_glyph_layout = bda_native_glyph_layout
        self.bda_native_raster_mode = bda_native_raster_mode
        self.scheduler_tick_clamp = scheduler_tick_clamp
        self.fs_dir_scan_stop_samples = fs_dir_scan_stop_samples
        self.fast_hooks = fast_hooks
        self.fast_hook_image_jals = fast_hook_image_jals
        self.fast_hook_image_branches = fast_hook_image_branches
        self.nand_loop_accelerator = nand_loop_accelerator
        self.resource_cache16_accelerator = resource_cache16_accelerator
        self.raster_copy_accelerator = raster_copy_accelerator
        self.glyph_mask_accelerator = glyph_mask_accelerator
        self.surface_pixel_accelerator = surface_pixel_accelerator
        self.surface_hline_accelerator = surface_hline_accelerator
        self.font_helper_accelerator = font_helper_accelerator
        self.gui_ring_pump = gui_ring_pump
        self.gui_ring_pump_events: list[dict[str, str | int]] = []
        self.nand_loop_accel_count = 0
        self.nand_loop_events: list[dict[str, str | int]] = []
        self.resource_cache16_accel_count = 0
        self.resource_cache16_events: list[dict[str, str | int]] = []
        self.cluster_read_accel_count = 0
        self.cluster_read_events: list[dict[str, str | int]] = []
        self.fat16_layout_cache: dict[str, int] | None = None
        self.nand_fat_sector0_cache: int | None = None
        self.dirent_copy_accel_count = 0
        self.dirent_copy_events: list[dict[str, str | int]] = []
        self.logo_strip_blit_accel_count = 0
        self.free_scan_accel_count = 0
        self.surface_setpixel_accel_count = 0
        self.surface_hline_accel_count = 0
        self.surface_color_span_accel_count = 0
        self.surface_block_read_accel_count = 0
        self.surface_block_write_accel_count = 0
        self.surface_pixel_read_count = 0
        self.surface_event_count = 0
        self.surface_events: list[dict[str, str | int]] = []
        self.surface_events_by_mode: dict[str, list[dict[str, str | int]]] = {}
        self.halfword_copy_accel_count = 0
        self.raster_loop_accel_count = 0
        self.glyph_mask_loop_accel_count = 0
        self.repeat_prologue_mode = repeat_prologue_mode
        self.recovery_reg_snapshots: dict[int, dict[str, int]] = {}
        self.mmio_delay_branch_count = 0
        self.native_synthetic_glyph_code: int | None = None
        self.block_events: list[dict[str, str | int]] = []
        self.preexecuted_jr_delay_pc: int | None = None
        self.idle_loop_hits = 0
        self.app_idle_loop_hits = 0
        self.bda_event_poll_hits = 0
        self.bda_idle_empty_polls = 0
        self.wait_wake_count = 0
        self.timer_tick_count = 0
        self.tcu_enabled_mask = 0
        self.tcu_pending_mask = 0
        self.intc_pending_mask = 0
        self.tcu_period_insn = 5_000
        self.next_tcu_irq_insn: int | None = None
        self.irq24_period_insn = 1_000
        self.next_irq24_insn: int | None = None
        self.interrupt_return_pc: int | None = None
        self.interrupt_suppress_pc_once: int | None = None
        self.interrupt_deliveries: list[dict[str, str | int]] = []
        self.internal_chunk_stop = False
        self.scheduler_poll_count = 0
        self.scheduler_dispatch_count = 0
        self.task_events: list[dict[str, object]] = []
        self.task_table_write_events: list[dict[str, object]] = []
        self.context_switch_events: list[dict[str, object]] = []
        self.repeat_prologue_events: list[dict[str, object]] = []
        self.fs_dir_scan_events: list[dict[str, str | int | None]] = []
        self.return_epilogue_events: list[dict[str, object]] = []
        self.repaint_call_context: dict[str, int] | None = None
        self.scratch_alloc_va = RAM_BASE + ram_size - 0x100000
        self.scratch_alloc_end_va = RAM_BASE + ram_size - 0x10000
        self.mmio_regs: dict[int, int] = {}
        self.lcd_writes: list[dict[str, str | int]] = []
        self.framebuffer_writes: list[dict[str, str | int]] = []
        self.blit_events: list[dict[str, str | int]] = []
        self.uart_bytes = bytearray()
        self.uart_writes: list[dict[str, str | int]] = []
        self.window_close_context: dict[str, int] | None = None
        self.dialog_draw_context: dict[str, int] | None = None
        self.event_dispatch_contexts: list[dict[str, int]] = []
        self.object_callback_contexts: list[dict[str, int]] = []
        self.display_event_contexts: list[dict[str, int]] = []
        self.synthetic_event_va: int | None = None
        self.event_queue_snapshots: list[dict[str, object]] = []
        self.bda_initial_draw_pending = False
        self.bda_initial_draw_context: dict[str, int] | None = None
        self.bda_app_active = False
        self.state = TraceState(image=image, base=base, pc=pc, ram_size=ram_size)
        self.uc = Uc(UC_ARCH_MIPS, UC_MODE_32 | UC_MODE_LITTLE_ENDIAN)
        self._map_memory()
        self._load_payload()
        self._apply_profile()
        self._apply_block_image_globals()
        self._install_hooks()

    def _looks_like_code_return(self, va: int) -> bool:
        va &= 0xFFFFFFFF
        if self.payload is not None and self.payload_addr <= va < self.payload_addr + self.payload_size:
            return True
        if self.payload is None:
            image_size = self.image.stat().st_size
            if self.base <= va < self.base + image_size:
                return True
        return BDA_RUNTIME_ENTRY_VA <= va < 0x81D00000

    def _is_bda_runtime_va(self, va: int) -> bool:
        va &= 0xFFFFFFFF
        return BDA_RUNTIME_ENTRY_VA <= va < 0x81D00000

    def _map_memory(self) -> None:
        data = self.image.read_bytes()
        # Unicorn's MIPS CPU translates KSEG0 addresses such as 0x80000000 to
        # physical address 0x00000000. Map physical RAM first and place the
        # image at the physical alias of the requested base.
        self.uc.mem_map(PHYS_RAM_BASE, self.ram_size)
        phys_base = self.base & 0x1FFFFFFF if self.base >= RAM_BASE else self.base
        self.uc.mem_write(phys_base, data)

        # Map JZ47xx physical MMIO and KSEG1 aliases explicitly. Some Unicorn
        # MIPS paths do not consistently translate 0xbxxxxxxx device loads
        # before hook dispatch, so model both views and keep them mirrored.
        self.uc.mem_map(PHYS_MMIO_BASE, MMIO_SIZE)
        self.uc.mem_map(MMIO_BASE, MMIO_SIZE)
        # External memory/bus bank used by NAND-style command/data windows.
        self.uc.mem_map(EXT_BANK_BASE, EXT_BANK_SIZE)
        self.uc.mem_map(EXT_BANK_KSEG1_BASE, EXT_BANK_SIZE)
        self.uc.mem_write(EXT_BANK_BASE, b"\xFF" * 4)
        self.uc.mem_write(EXT_BANK_KSEG1_BASE, b"\xFF" * 4)

        # KSEG1 uncached RAM alias. Unicorn cannot alias memory, so map a
        # separate range and copy the boot image if the selected base lives here.
        self.uc.mem_map(KSEG1_BASE, self.ram_size)
        if self.base >= KSEG1_BASE and self.base < KSEG1_BASE + self.ram_size:
            self.uc.mem_write(self.base, data)

    def _load_payload(self) -> None:
        if self.payload is None:
            return
        data = self.payload.read_bytes()
        phys = self.payload_addr & 0x1FFFFFFF if self.payload_addr >= RAM_BASE else self.payload_addr
        if phys + len(data) > self.ram_size:
            raise ValueError(
                f"payload does not fit RAM: addr=0x{self.payload_addr:08x} size=0x{len(data):x}"
            )
        self.uc.mem_write(phys, data)
        self._trace_event("payload-load", pc=self.pc, addr=self.payload_addr, size=len(data))

    def _write_u32_va(self, va: int, value: int) -> None:
        phys = va & 0x1FFFFFFF if va >= RAM_BASE else va
        self.uc.mem_write(phys, struct.pack("<I", value & 0xFFFFFFFF))

    def _mmio_alias_for_phys(self, pa: int) -> int | None:
        if PHYS_MMIO_BASE <= pa < PHYS_MMIO_BASE + MMIO_SIZE:
            return MMIO_BASE + (pa - PHYS_MMIO_BASE)
        if EXT_BANK_BASE <= pa < EXT_BANK_BASE + EXT_BANK_SIZE:
            return EXT_BANK_KSEG1_BASE + (pa - EXT_BANK_BASE)
        return None

    def _canonical_mmio_address(self, address: int) -> int:
        if MMIO_BASE <= address < MMIO_BASE + MMIO_SIZE:
            return PHYS_MMIO_BASE + (address - MMIO_BASE)
        if EXT_BANK_KSEG1_BASE <= address < EXT_BANK_KSEG1_BASE + EXT_BANK_SIZE:
            return EXT_BANK_BASE + (address - EXT_BANK_KSEG1_BASE)
        return address

    def _write_u32_phys(self, pa: int, value: int) -> None:
        data = struct.pack("<I", value & 0xFFFFFFFF)
        self.uc.mem_write(pa, data)
        alias = self._mmio_alias_for_phys(pa)
        if alias is not None:
            self.uc.mem_write(alias, data)

    def _read_mem_va(self, va: int, size: int) -> int:
        phys = va & 0x1FFFFFFF if va >= RAM_BASE else va
        return int.from_bytes(self.uc.mem_read(phys, size), "little")

    def _write_mem_va(self, va: int, size: int, value: int) -> None:
        phys = va & 0x1FFFFFFF if va >= RAM_BASE else va
        self.uc.mem_write(phys, (value & ((1 << (size * 8)) - 1)).to_bytes(size, "little"))

    def _scratch_alloc(self, size: int, align: int = 4) -> int:
        size = (size + align - 1) & ~(align - 1)
        va = self.scratch_alloc_va
        next_va = va + size
        if next_va > self.scratch_alloc_end_va:
            raise MemoryError("emulator scratch allocator exhausted")
        self.scratch_alloc_va = next_va
        self.uc.mem_write(va_to_phys(va), b"\x00" * size)
        return va

    def _apply_block_image_globals(self) -> None:
        if self.block_data is None:
            return
        # C200's logical block layer stores the exposed media byte size here;
        # 0x80182d58 returns it directly and 0x80182bf4 checks reads against it.
        self._write_u32_va(0x804BF464, len(self.block_data))

    def _init_bda_display_context(self, pc: int) -> None:
        """Seed the app display callback globals normally prepared by C200.

        Direct diagnostic BDA launch skips the menu-side initializer at
        0x8012d20c. Native apps can immediately call widget/display helpers
        that dereference 0x8047409c, so reproduce the small set of global
        writes needed before entering the BDA runtime.
        """
        self._init_bda_font_context(pc)
        current = self._read_mem_va(0x8047409C, 4) & 0xFFFFFFFF
        if current == BDA_DISPLAY_CALLBACK_TABLE:
            return

        self._write_u32_va(0x8047409C, BDA_DISPLAY_CALLBACK_TABLE)
        self._write_u32_va(0x804740A0, 0)
        self._write_u32_va(0x804740A4, 0)
        # Normal startup writes this callback at 0x800dbe64. Direct BDA launch
        # can enter repaint without running that initializer.
        self._write_u32_va(0x8082584C, 0x800DCFE0)
        if self._read_mem_va(0x80825850, 4) == 0:
            event_ring = self._scratch_alloc(0x1C * 0x10)
            self._write_u32_va(0x80825850, event_ring)
            self._write_u32_va(0x80825854, 0x10)
            self._write_u32_va(0x80825858, 0)
            self._write_u32_va(0x8082585C, 0)

        # 0x8012d20c also caches an inset rectangle from the active display
        # descriptor at 0x80474030. If the descriptor is already live, mirror
        # those derived values; otherwise keep the 240x320 portrait defaults.
        try:
            display_desc = self._read_mem_va(0x80474030, 4) & 0xFFFFFFFF
            width = (self._read_mem_va(display_desc + 0x0C, 4) - 2) & 0xFFFFFFFF if display_desc else 0xEE
            height = (self._read_mem_va(display_desc + 0x10, 4) - 2) & 0xFFFFFFFF if display_desc else 0x13E
        except Exception:
            width = 0xEE
            height = 0x13E

        self._write_u32_va(0x804A6C98, 0)
        self._write_u32_va(0x804A6CA0, 0)
        self._write_u32_va(0x804A6CA4, width)
        self._write_u32_va(0x804A6CA8, 0)
        self._write_u32_va(0x804A6CAC, height)
        self._write_u32_va(0x804A6CB0, 0)
        self._trace_event("bda-display-context", pc=pc, addr=0x8047409C, value=BDA_DISPLAY_CALLBACK_TABLE, size=4)

    def _init_bda_font_context(self, pc: int) -> None:
        """Seed the default UI font context used by window repaint paths.

        The normal firmware font/resource initializer at 0x80129690 expects
        resource paths that are not yet modeled by the FAT/block hooks. Direct
        BDA launch still reaches widget repaint code that dereferences the
        default context at 0x80825a80, so provide a minimal font object using
        the firmware's own font vtable and simple 16x16 metrics.
        """
        try:
            if self._read_mem_va(0x80825AC0, 4) != 0:
                return
        except Exception:
            return

        font = self._scratch_alloc(0x70)
        metrics = self._scratch_alloc(0x18)
        provider = self._scratch_alloc(0x40)
        provider_name = self._scratch_alloc(0x04)
        self.uc.mem_write(va_to_phys(provider_name), b"SGM\x00")
        self._write_u32_va(metrics + 0x08, 16)
        self._write_u32_va(metrics + 0x0C, 16)
        self._write_u32_va(metrics + 0x14, 256)
        self._write_u32_va(provider + 0x0C, provider_name)
        self._write_u32_va(provider + 0x14, 0x8012A6A8)
        self._write_u32_va(provider + 0x18, 0x8012A6A8)
        self._write_u32_va(provider + 0x1C, 0x8012A6A8)
        self._write_u32_va(font + 0x58, 0x803AF0B0)
        self._write_u32_va(font + 0x5C, provider)
        self._write_u32_va(font + 0x68, metrics)

        self._write_u32_va(0x80825AB8, 16)
        self._write_u32_va(0x80825AC0, font)
        self._write_u32_va(0x80825AC4, 0)
        self._trace_event("bda-font-context", pc=pc, addr=0x80825A80, value=font, size=0x70)

    def _seed_surface_dirty_rect(self, surface: int, pc: int) -> None:
        if not self.bda_app_active or not self._is_mapped_ram_va(surface, 0xC8):
            return
        try:
            if self._read_mem_va(surface + 0x04, 4) != 0x82:
                return
            dirty = surface + 0xB0
            if self._read_mem_va(dirty + 0x10, 4) != 0:
                return
            node = self._scratch_alloc(0x14)
            self._write_u32_va(node + 0x00, 0)
            self._write_u32_va(node + 0x04, 0)
            self._write_u32_va(node + 0x08, 0xEF)
            self._write_u32_va(node + 0x0C, 0x13F)
            self._write_u32_va(node + 0x10, 0)
            self._write_u32_va(dirty + 0x00, 0)
            self._write_u32_va(dirty + 0x04, 0)
            self._write_u32_va(dirty + 0x08, 0xEF)
            self._write_u32_va(dirty + 0x0C, 0x13F)
            self._write_u32_va(dirty + 0x10, node)
            self._write_u32_va(dirty + 0x14, node)
            self._trace_event("surface-dirty-seed", pc=pc, addr=dirty, value=node, size=0x14)
        except Exception:
            return

    def _bda_text_draw_args(self) -> dict[str, int] | None:
        if not self.bda_app_active:
            return None
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        a3 = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        try:
            y_ptr = self._read_mem_va(sp + 0x10, 4) & 0xFFFFFFFF
            text_ptr = self._read_mem_va(sp + 0x1C, 4) & 0xFFFFFFFF
            text_len = self._read_mem_va(sp + 0x20, 4) & 0xFFFFFFFF
            x = self._read_mem_va(a3, 4) & 0xFFFFFFFF
            y = self._read_mem_va(y_ptr, 4) & 0xFFFFFFFF
            ch = self._read_mem_va(text_ptr, 1) & 0xFF
        except Exception:
            return None
        if text_len == 0:
            return None
        if x > 0x1000 or y > 0x1000:
            return None
        return {
            "sp": sp,
            "x_ptr": a3,
            "y_ptr": y_ptr,
            "text_ptr": text_ptr,
            "text_len": text_len,
            "x": x,
            "y": y,
            "ch": ch,
        }

    def _trace_bda_native_text_draw(self, pc: int) -> None:
        args = self._bda_text_draw_args()
        if args is None:
            return
        font = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        vtable = self._read_u32_va_safe(font + 0x58) or 0
        provider = self._read_u32_va_safe(font + 0x5C) or 0
        metrics = self._read_u32_va_safe(font + 0x68) or 0
        self._trace_event(
            "native-text-draw",
            pc=pc,
            addr=args["text_ptr"],
            value=args["ch"],
            size=args["text_len"],
            x=args["x"],
            y=args["y"],
            font=font,
            vtable=vtable,
            provider=provider,
            metrics=metrics,
        )

    def _trace_system_text_entry(self, pc: int) -> None:
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        a0 = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        a1 = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        a2 = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        a3 = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        text_ptr = 0
        text_len = 0
        x = a1
        y = a2
        if pc == 0x800C0D40:
            text_ptr = a3
            # Trace runs before the function prologue. The fifth o32 argument
            # is still at caller_sp+0x10 here; after the prologue this becomes
            # callee_sp+0x60.
            text_len = self._read_u32_va_safe(sp + 0x10) or 0
        elif pc == 0x80119B50:
            text_ptr = a3
            text_len = self._read_u32_va_safe(sp + 0x70) or 0
        elif pc == 0x8011A3C4:
            text_ptr = self._read_u32_va_safe(sp + 0x1C) or 0
            text_len = self._read_u32_va_safe(sp + 0x20) or 0
            x_ptr = a3
            y_ptr = self._read_u32_va_safe(sp + 0x10) or 0
            x = self._read_u32_va_safe(x_ptr) or 0
            y = self._read_u32_va_safe(y_ptr) or 0
        if text_ptr == 0:
            return
        row = {
            "kind": "system-text-entry",
            "pc": f"0x{pc:08x}",
            "addr": f"0x{text_ptr:08x}",
            "value": f"0x{text_len:08x}",
            "size": f"0x{text_len & 0xFFFFFFFF:08x}",
            "surface": f"0x{a0:08x}",
            "x": f"0x{x & 0xFFFFFFFF:08x}",
            "y": f"0x{y & 0xFFFFFFFF:08x}",
            "a1": f"0x{a1:08x}",
            "a2": f"0x{a2:08x}",
            "a3": f"0x{a3:08x}",
            "ra": f"0x{self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF:08x}",
        }
        if text_len == 0xFFFFFFFF:
            max_len = 96
        else:
            max_len = max(0, min(int(text_len), 96))
        if max_len:
            try:
                raw = bytes(self.uc.mem_read(va_to_phys(text_ptr), max_len))
                if text_len == 0xFFFFFFFF:
                    raw = raw.split(b"\x00", 1)[0]
                row["text_hex"] = raw[:64].hex()
                row["text_gb18030"] = raw.decode("gb18030", errors="replace")
            except Exception:
                pass
        self.state.events.append(row)
        if len(self.state.events) > self.trace_limit:
            del self.state.events[0]

    def _draw_synthetic_glyph_for_bda_text(self, pc: int) -> bool:
        """Render a temporary ASCII glyph for direct-BDA smoke tests."""
        args = self._bda_text_draw_args()
        if args is None:
            return False
        a3 = args["x_ptr"]
        text_ptr = args["text_ptr"]
        text_len = args["text_len"]
        x = args["x"]
        y = args["y"]
        ch = args["ch"]

        # Dialog text often uses a cursor baseline; keep the marker in bounds.
        draw_x = max(0, min(239, int(x)))
        draw_y = max(0, min(319, int(y)))
        if draw_y + 8 >= 320:
            draw_y = max(0, 319 - 8)
        if draw_x + 6 >= 240:
            draw_x = max(0, 239 - 6)

        color = 0xFFFF
        glyph_key = chr(ch).upper() if 0x20 <= ch < 0x7F else "?"
        rows = ASCII_5X7_FONT.get(glyph_key)
        if rows is None:
            rows = (0x1F, 0x01, 0x02, 0x04, 0x04, 0, 0x04)
        pixels = []
        for row, bits in enumerate(rows):
            for col in range(5):
                if bits & (1 << (4 - col)):
                    pixels.append((draw_x + col, draw_y + row))

        for base in (0x80825B90, 0xA1F82000):
            for px, py in pixels:
                addr = base + ((py * 240 + px) << 1)
                try:
                    self._write_mem_va(addr, 2, color)
                except Exception:
                    pass
        try:
            self._write_u32_va(a3, min(239, x + 6))
        except Exception:
            pass
        self._trace_event(
            "synthetic-glyph",
            pc=pc,
            addr=text_ptr,
            value=ch,
            size=text_len,
            x=draw_x,
            y=draw_y,
        )
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        return True

    def _ascii_glyph_16x16_1bpp(self, code: int) -> bytes:
        glyph_key = chr(code).upper() if 0x20 <= code < 0x7F else "?"
        rows = ASCII_5X7_FONT.get(glyph_key)
        if rows is None:
            rows = (0x1F, 0x01, 0x02, 0x04, 0x04, 0, 0x04)
        out = bytearray(0x20)
        layout = self.bda_native_glyph_layout

        def set_pixel(x: int, y: int) -> None:
            if not (0 <= x < 16 and 0 <= y < 16):
                return
            if layout.startswith("rows-lsb"):
                bit = x
            else:
                bit = 15 - x
            row_bits = (out[y * 2] << 8) | out[y * 2 + 1]
            row_bits |= 1 << bit
            out[y * 2] = (row_bits >> 8) & 0xFF
            out[y * 2 + 1] = row_bits & 0xFF

        if layout in {
            "cols-msb-vscale2",
            "cols-lsb-vscale2",
            "cols-msb-vscale2-hscale2",
            "cols-lsb-vscale2-hscale2",
        }:
            col_bits = [0] * 16
            x_scale = 2 if "-hscale2" in layout else 1
            x_offset = 3 if "-hscale2" in layout else 4
            for src_y, bits in enumerate(rows):
                for sy in (0, 1):
                    dst_y = 1 + src_y * 2 + sy
                    for src_x in range(5):
                        if bits & (1 << (4 - src_x)):
                            for sx in range(x_scale):
                                dst_x = x_offset + src_x * x_scale + sx
                                if 0 <= dst_x < 16:
                                    col_bits[dst_x] |= 1 << (15 - dst_y)
            for x, bits in enumerate(col_bits):
                idx = x * 2
                if layout.startswith("cols-lsb"):
                    bits = int(f"{bits:016b}"[::-1], 2)
                out[idx] = (bits >> 8) & 0xFF
                out[idx + 1] = bits & 0xFF
            return bytes(out)

        y_offset = 0 if layout.endswith("-y0") else 1
        x_offset = 3 if "-x3" in layout else 4
        x_scale = 2 if "-hscale2" in layout else 1
        for src_y, bits in enumerate(rows):
            for sy in (0, 1):
                dst_y = y_offset + src_y * 2 + sy
                for src_x in range(5):
                    if not (bits & (1 << (4 - src_x))):
                        continue
                    for sx in range(x_scale):
                        dst_x = x_offset + src_x * x_scale + sx
                        set_pixel(dst_x, dst_y)
        return bytes(out)

    def _draw_ascii_glyph_to_raster_surface(
        self,
        dst: int,
        stride: int,
        code: int,
        fg: int,
        bg: int = 0,
        opaque: bool = False,
    ) -> int:
        glyph_key = chr(code).upper() if 0x20 <= code < 0x7F else "?"
        rows = ASCII_5X7_FONT.get(glyph_key)
        if rows is None:
            rows = (0x1F, 0x01, 0x02, 0x04, 0x04, 0, 0x04)
        if opaque:
            for y in range(16):
                for x in range(16):
                    self._write_mem_va((dst + y * stride + x * 2) & 0xFFFFFFFF, 2, bg & 0xFFFF)
        pixels = 0
        for src_y, bits in enumerate(rows):
            for sy in (0, 1):
                y = 1 + src_y * 2 + sy
                for src_x in range(5):
                    if not (bits & (1 << (4 - src_x))):
                        continue
                    for sx in (0, 1):
                        x = 3 + src_x * 2 + sx
                        self._write_mem_va((dst + y * stride + x * 2) & 0xFFFFFFFF, 2, fg & 0xFFFF)
                        pixels += 1
        return pixels

    def _return_synthetic_event_from_bad_queue(self, pc: int) -> bool:
        src = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
        if src % 4 == 0:
            return False
        queue = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        if self.synthetic_event_va is None:
            self.synthetic_event_va = self._scratch_alloc(0x20)
        event = self.synthetic_event_va
        self._write_u32_va(event + 0x00, 0)
        self._write_u32_va(event + 0x04, 0x0A)
        self._write_u32_va(event + 0x08, 0)
        self._write_u32_va(event + 0x0C, 0)

        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        status_ptr = self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF
        try:
            self._write_mem_va(status_ptr, 1, 0x0A)
            self._write_u32_va(queue + 0x18, 0)
        except Exception:
            pass
        ra = self._read_mem_va(sp + 0x20, 4) & 0xFFFFFFFF
        self.uc.reg_write(UC_MIPS_REG_19, self._read_mem_va(sp + 0x1C, 4) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_18, self._read_mem_va(sp + 0x18, 4) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_17, self._read_mem_va(sp + 0x14, 4) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_16, self._read_mem_va(sp + 0x10, 4) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_31, ra)
        self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x28) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_2, event)
        self._trace_event("event-queue-bad-read", pc=pc, addr=src, value=queue, size=4)
        self.uc.reg_write(UC_MIPS_REG_PC, ra)
        return True

    def _read_block_va_safe(self, va: int, size: int) -> bytes | None:
        try:
            return bytes(self.uc.mem_read(va_to_phys(va), size))
        except Exception:
            return None

    def _read_u32_va_safe(self, va: int) -> int | None:
        data = self._read_block_va_safe(va, 4)
        if data is None:
            return None
        return struct.unpack_from("<I", data)[0]

    def _is_mapped_ram_va(self, va: int, size: int = 1) -> bool:
        if va == 0:
            return False
        if va < RAM_BASE:
            return False
        phys = va_to_phys(va)
        return 0 <= phys and phys + size <= self.ram_size

    def _queue_object_snapshot(self, obj: int | None) -> dict[str, object]:
        out: dict[str, object] = {
            "global_80473f6c": None if obj is None else f"0x{obj:08x}",
        }
        if obj is None or not self._is_mapped_ram_va(obj, 0x10):
            return out

        obj_data = self._read_block_va_safe(obj, 0x40)
        if obj_data is None:
            out["object_error"] = "unreadable"
            return out
        obj_words = [struct.unpack_from("<I", obj_data, i)[0] for i in range(0, 0x40, 4)]
        queue = obj_words[2]
        out["object_words"] = [f"0x{word:08x}" for word in obj_words]
        out["object_type_byte"] = f"0x{obj_data[0]:02x}"
        out["queue_ptr"] = f"0x{queue:08x}"
        if not self._is_mapped_ram_va(queue, 0x20):
            return out

        q_data = self._read_block_va_safe(queue, 0x40)
        if q_data is None:
            out["queue_error"] = "unreadable"
            return out
        q_words = [struct.unpack_from("<I", q_data, i)[0] for i in range(0, 0x40, 4)]
        out["queue_words"] = [f"0x{word:08x}" for word in q_words]
        ring_start = q_words[1]
        ring_end = q_words[2]
        read_ptr = q_words[4]
        count = q_words[6]
        out["queue_fields"] = {
            "ring_start_04": f"0x{ring_start:08x}",
            "ring_end_08": f"0x{ring_end:08x}",
            "read_ptr_10": f"0x{read_ptr:08x}",
            "count_18": f"0x{count:08x}",
        }
        entries = []
        if self._is_mapped_ram_va(ring_start, 4) and self._is_mapped_ram_va(ring_end, 4):
            max_entries = min(16, max(0, (ring_end - ring_start) // 4))
            for idx in range(max_entries):
                entry_va = ring_start + idx * 4
                value = self._read_u32_va_safe(entry_va)
                entries.append(
                    {
                        "index": idx,
                        "addr": f"0x{entry_va:08x}",
                        "value": None if value is None else f"0x{value:08x}",
                        "is_read_ptr": entry_va == read_ptr,
                    }
                )
        out["ring_entries"] = entries
        return out

    def _capture_event_queue_snapshot(self, kind: str, pc: int) -> None:
        obj = self._read_u32_va_safe(0x80473F6C)
        row = self._queue_object_snapshot(obj)
        row["kind"] = kind
        row["pc"] = f"0x{pc:08x}"
        row["a0"] = f"0x{self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF:08x}"
        row["a1"] = f"0x{self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF:08x}"
        row["v0"] = f"0x{self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF:08x}"
        self.event_queue_snapshots.append(row)
        if len(self.event_queue_snapshots) > 64:
            del self.event_queue_snapshots[0]

    def _capture_fs_dir_scan(self, pc: int) -> None:
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        s1 = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        row: dict[str, str | int | None] = {
            "pc": f"0x{pc:08x}",
            "count": len(self.fs_dir_scan_events) + 1,
            "v0": f"0x{self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF:08x}",
            "a0": f"0x{self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF:08x}",
            "s1": f"0x{s1:08x}",
            "s2": f"0x{self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF:08x}",
            "sp": f"0x{sp:08x}",
            "sp90": None,
            "sp9c": None,
            "dir0": None,
            "dir_attr": None,
            "dir_cluster": None,
            "dir_size": None,
            "dirent_hex": None,
        }
        sp90 = self._read_u32_va_safe(sp + 0x90)
        sp9c = self._read_u32_va_safe(sp + 0x9C)
        if sp90 is not None:
            row["sp90"] = f"0x{sp90:08x}"
        if sp9c is not None:
            row["sp9c"] = f"0x{sp9c:08x}"
        if self._is_mapped_ram_va(s1, 0x20):
            data = self._read_block_va_safe(s1, 0x20)
            if data is not None:
                row["dir0"] = f"0x{data[0]:02x}"
                row["dir_attr"] = f"0x{data[0x0B]:02x}"
                row["dir_name_hex"] = data[:11].hex()
                row["dir_cluster"] = f"0x{((struct.unpack_from('<H', data, 0x14)[0] << 16) | struct.unpack_from('<H', data, 0x1A)[0]) & 0xFFFFFFFF:08x}"
                row["dir_size"] = f"0x{struct.unpack_from('<I', data, 0x1C)[0]:08x}"
                row["dirent_hex"] = data.hex()
        self.fs_dir_scan_events.append(row)
        if len(self.fs_dir_scan_events) > 256:
            del self.fs_dir_scan_events[0]
        if self.fs_dir_scan_stop_samples > 0 and row["count"] >= self.fs_dir_scan_stop_samples:
            self.state.stop_reason = "fs_dir_scan_probe"
            self.uc.emu_stop()

    def _handle_fs_dir_scan_branch(self, pc: int) -> bool:
        """Model delay slots in C200's FAT directory scan loop.

        Unicorn's MIPS backend intermittently loses progress in this loop after
        branch recovery. These are direct translations of the instructions in
        0x80173630..0x80173768 and 0x80173f14..0x80173f2c.
        """
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        s1 = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        s2 = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        s5 = self.uc.reg_read(UC_MIPS_REG_21) & 0xFFFFFFFF
        s6 = self.uc.reg_read(UC_MIPS_REG_22) & 0xFFFFFFFF
        v0 = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
        v1 = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        a0 = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF

        if pc == 0x80173630:
            loaded_a0 = self._read_mem_va(sp + 0x9C, 4) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_4, loaded_a0)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80173F2C if s6 == s5 else 0x80173638)
            return True
        if pc == 0x80173640:
            self.uc.reg_write(UC_MIPS_REG_4, 0xE5)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80173F14 if v1 != 0 else 0x80173648)
            return True
        if pc == 0x80173710:
            loaded_v0 = self._read_mem_va(sp + 0x88, 4) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_2, loaded_v0)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x8017375C if v0 == v1 else 0x80173718)
            return True
        if pc == 0x80173768:
            self.uc.reg_write(UC_MIPS_REG_17, (s1 + 0x20) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80173630 if v1 != 0 else 0x80173770)
            return True
        if pc == 0x80173F14:
            self.uc.reg_write(UC_MIPS_REG_2, 0x2E)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x8017375C if v1 == a0 else 0x80173F1C)
            return True
        if pc == 0x80173F1C:
            self.uc.reg_write(UC_MIPS_REG_2, (s2 + 0x20) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80173704 if v1 != v0 else 0x80173F24)
            return True
        if pc == 0x80173F24:
            self.uc.reg_write(UC_MIPS_REG_18, v0 & 0xFFFF)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80173764)
            return True
        if pc == 0x80173F2C:
            loaded_v0 = self._read_mem_va(sp + 0x90, 4) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_2, loaded_v0)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80173638 if a0 == 0 else 0x80173F34)
            return True
        return False

    def _capture_return_epilogue(self, pc: int) -> None:
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        row: dict[str, object] = {
            "pc": f"0x{pc:08x}",
            "sp": f"0x{sp:08x}",
            "ra": f"0x{self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF:08x}",
            "words": [],
        }
        words: list[str | None] = []
        for off in range(-0x20, 0x61, 4):
            value = self._read_u32_va_safe((sp + off) & 0xFFFFFFFF)
            words.append(None if value is None else f"{off:+#04x}=0x{value:08x}")
        row["words"] = words
        self.return_epilogue_events.append(row)
        if len(self.return_epilogue_events) > 64:
            del self.return_epilogue_events[0]

    def _handle_display_getter_jalr(self, pc: int) -> bool:
        target = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
        getter_offsets = {
            0x800A899C: 0x14,
            0x800A89A4: 0x00,
            0x800A89AC: 0x04,
            0x800A89B4: 0x3C,
        }
        offset = getter_offsets.get(target)
        if offset is None:
            return False
        obj = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        value = self._read_u32_va_safe(obj + offset) or 0
        self.uc.reg_write(UC_MIPS_REG_2, value)
        self.uc.reg_write(UC_MIPS_REG_PC, (pc + 8) & 0xFFFFFFFF)
        self._trace_event("display-getter-jalr", pc=pc, target=target, addr=obj, value=value)
        return True

    def _apply_profile(self) -> None:
        if self.profile == "none":
            return
        if self.profile != "bbk9588-uboot":
            raise ValueError(f"unknown profile: {self.profile}")
        # CPCCR/CPPCR reads should not look like a completely unclocked SoC.
        self._write_u32_phys(0x10000000, 0x00000003)
        self._write_u32_phys(0x10000010, 0x01490010)
        # C200 display globals used before the full LCD allocator path has run.
        # The firmware later programs the same 0xa1f8xxxx buffers for LCD DMA.
        self._write_u32_va(0x8033C0B4, 0x000000F0)  # width
        self._write_u32_va(0x8033C0B8, 0x00000140)  # height
        self._write_u32_va(0x8033C0BC, 0x00000010)  # bpp/mode
        self._write_u32_va(0x8033C0E4, 0xA1F81000)
        self._write_u32_va(0x8033C0E8, 0xA1F82000)
        # This helper's mode=0x10 path is an immediate zero return, but Unicorn
        # repeatedly faults between the caller's jal and this large-stack entry,
        # leaking 0x418 bytes per call. Patch it into the equivalent early
        # return until the MIPS backend is replaced or the root fault is fixed.
        self._write_u32_va(0x800A91F4, 0x03E00008)  # jr ra
        self._write_u32_va(0x800A91F8, 0x00001021)  # move v0,zero
        # The caller's jal to that helper also trips Unicorn's branch recovery
        # and resumes at the jal instead of the post-call instruction. Patch the
        # call site to the same zero-return result for this trace path.
        self._write_u32_va(0x800A88E8, 0x00001021)  # move v0,zero
        self._write_u32_va(0x800A88EC, 0x00000000)  # nop

    def _install_hooks(self) -> None:
        if self.fast_hooks:
            if self.fast_hook_image_branches:
                for pc in sorted(self._image_recoverable_branch_pcs()):
                    self.uc.hook_add(UC_HOOK_CODE, self._on_recovery_snapshot_code, begin=pc, end=pc)
            for pc in sorted(self._fast_code_hook_pcs()):
                self.uc.hook_add(UC_HOOK_CODE, self._on_code, begin=pc, end=pc)
        else:
            self.uc.hook_add(UC_HOOK_CODE, self._on_code)
        self.uc.hook_add(UC_HOOK_BLOCK, self._on_block)
        self._install_mem_hooks()
        self.uc.hook_add(UC_HOOK_MEM_INVALID, self._on_invalid)

    def _install_mem_hooks(self) -> None:
        # Do not install a global RAM MEM hook. Unicorn MIPS mishandles a
        # `jal` whose delay slot performs a hooked RAM store: the branch target
        # first instruction is executed twice. Hook only device/diagnostic
        # ranges so normal RAM delay slots run without Python intervention.
        ranges: list[tuple[int, int]] = [
            (PHYS_MMIO_BASE, PHYS_MMIO_BASE + MMIO_SIZE - 1),
            (MMIO_BASE, MMIO_BASE + MMIO_SIZE - 1),
            (EXT_BANK_BASE, EXT_BANK_BASE + EXT_BANK_SIZE - 1),
            (EXT_BANK_KSEG1_BASE, EXT_BANK_KSEG1_BASE + EXT_BANK_SIZE - 1),
            (0x01F80000, 0x01FA8000 - 1),
            (0xA1F80000, 0xA1FA8000 - 1),
        ]
        for watch in self.watch_ranges:
            ranges.append((watch.phys, watch.phys + watch.size - 1))
        for begin, end in self._merge_hook_ranges(ranges):
            self.uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, self._on_mem, begin=begin, end=end)

    def _merge_hook_ranges(self, ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
        if not ranges:
            return []
        ordered = sorted((max(0, a), max(0, b)) for a, b in ranges if b >= a)
        merged: list[tuple[int, int]] = []
        for begin, end in ordered:
            if not merged or begin > merged[-1][1] + 1:
                merged.append((begin, end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        return merged

    def _fast_code_hook_pcs(self) -> set[int]:
        pcs = set(self.trace_pcs)
        pcs.update(self.stop_pcs)
        if self.fast_hook_image_jals:
            pcs.update(self._image_jal_pcs())
        pcs.update(self._image_store_delay_branch_pcs())
        pcs.update(
            {
                0x80903AA0,
                0x80901384,
                0x80901D2C,
                0x80901E24,
                0x80900F70,
                0x80900F78,
                0x80900F80,
                0x80902448,
                0x8090247C,
                0x80902524,
                0x80903BB0,
                0x80903BB8,
                0x80903BC0,
                0x80903BCC,
                0x80903BD4,
                0x80903BE8,
                0x80903C2C,
                0x80903EA4,
                0x80903EAC,
                0x80903EFC,
                0x80904EC8,
                0x80906780,
                0x809080A0,
                0x80908188,
                0x809081A0,
                0x809081A4,
                0x80908284,
                0x80908288,
                0x8090828C,
                0x80908294,
                0x80900D48,
                0x80905EA0,
                0x8000403C,
                0x80004074,
                0x800042F0,
                0x800043CC,
                0x80004CC4,
                0x80004CD4,
                0x80006BD0,
                0x80006BF8,
                0x800074A0,
                0x800098C0,
                0x8000C15C,
                0x8000D990,
                0x8000FEC0,
                0x8000FE74,
                0x8000FEB4,
                0x800100C8,
                0x80008354,
                0x80008470,
                0x800080F0,
                0x800081A8,
                0x800087C4,
                0x800088AC,
                0x80008A84,
                0x80009950,
                0x800099F0,
                0x80010D70,
                0x80010D7C,
                0x80010D88,
                0x80010D94,
                0x80010DA0,
                0x800128CC,
                0x800128D4,
                0x800128F4,
                0x800128F8,
                0x800129AC,
                0x800133EC,
                0x800176E0,
                0x80017CB4,
                0x80017D54,
                0x80017DE8,
                0x80018C58,
                0x80018DAC,
                0x8001A3A0,
                0x8001A6B0,
                0x8001B464,
                0x8005BCD4,
                0x800A7B40,
                0x800A7C18,
                0x800A7DC0,
                0x800A7FD8,
                0x800A80E8,
                0x800A899C,
                0x800A89A4,
                0x800A89AC,
                0x800A89B4,
                0x800AC388,
                0x800BC944,
                0x800BC9AC,
                0x800BC9CC,
                0x800BC2E0,
                0x800BD840,
                0x800CE9F0,
                0x800CEA30,
                0x800D3368,
                0x800D3634,
                0x800DE5BC,
                0x800E0D68,
                0x800E123C,
                0x800E1408,
                0x80170C74,
                0x8001920C,
                0x8001925C,
                0x8012A6A8,
                0x8012C920,
                0x80172840,
                0x8017B45C,
                0x8017B4E0,
                0x8012BDF4,
                0x8012BEA4,
                0x8012BE84,
                0x8012B034,
                0x8012B064,
                0x8012BF64,
                0x80173630,
                0x80173638,
                0x80173640,
                0x80173710,
                0x80173764,
                0x80173768,
                0x8017376C,
                0x801737B8,
                0x80173F14,
                0x80173F1C,
                0x80173F24,
                0x80173F2C,
                0x8017A860,
                0x8011B428,
                0x80175E40,
                0x8017BEF4,
                0x8017CA10,
                0x801802E8,
                0x8017FDCC,
                0x8018057C,
                0x801813E0,
                0x80181400,
                0x80182A90,
                0x80182BF4,
                0x80182D58,
                0x80183E0C,
                0x80183E10,
                0x80183FA4,
                0x80183FA8,
                0x80184140,
                0x80184150,
                0x801841BC,
                0x801841CC,
                0x801843D8,
                0x801843DC,
                0x80184530,
                0x80183304,
                0x80184D08,
            }
        )
        return pcs

    def _image_store_delay_branch_pcs(self) -> set[int]:
        data = self.image.read_bytes()
        pcs: set[int] = set()
        for off in range(0, len(data) - 7, 4):
            word = int.from_bytes(data[off : off + 4], "little")
            delay = int.from_bytes(data[off + 4 : off + 8], "little")
            if not self._is_recoverable_branch_word(word):
                continue
            delay_opcode = (delay >> 26) & 0x3F
            if delay_opcode in (40, 41, 43):  # sb/sh/sw
                pcs.add((self.base + off) & 0xFFFFFFFF)
        return pcs

    def _image_jal_pcs(self) -> set[int]:
        data = self.image.read_bytes()
        pcs: set[int] = set()
        for off in range(0, len(data) - 3, 4):
            word = int.from_bytes(data[off : off + 4], "little")
            if ((word >> 26) & 0x3F) == 3:
                pc = (self.base + off) & 0xFFFFFFFF
                target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
                pcs.add(pc)
                pcs.add(target & 0xFFFFFFFF)
        return pcs

    def _image_recoverable_branch_pcs(self) -> set[int]:
        data = self.image.read_bytes()
        pcs: set[int] = set()
        for off in range(0, len(data) - 3, 4):
            word = int.from_bytes(data[off : off + 4], "little")
            if self._is_recoverable_exception_word(word):
                pcs.add((self.base + off) & 0xFFFFFFFF)
        return pcs

    def _snapshot_regs_for_recovery(self) -> dict[str, int]:
        return {name: self.uc.reg_read(reg) & 0xFFFFFFFF for name, reg in self._state_regs()}

    def _restore_regs_for_recovery(self, snapshot: dict[str, int]) -> None:
        for name, reg in self._state_regs():
            if name in snapshot:
                self.uc.reg_write(reg, snapshot[name] & 0xFFFFFFFF)

    def _on_recovery_snapshot_code(self, uc, address: int, size: int, user_data) -> None:
        self.recovery_reg_snapshots[address & 0xFFFFFFFF] = self._snapshot_regs_for_recovery()
        if len(self.recovery_reg_snapshots) > 256:
            self.recovery_reg_snapshots.pop(next(iter(self.recovery_reg_snapshots)))

    def _on_block(self, uc, address: int, size: int, user_data) -> None:
        self.state.last_pc = address
        self.state.pcs.append(address)
        if len(self.state.pcs) > 64:
            del self.state.pcs[0]
        if self._maybe_deliver_external_interrupt(address):
            self.uc.emu_stop()

    def _on_code(self, uc, address: int, size: int, user_data) -> None:
        word = self._read_word_at_va(address)
        if word is not None and self._is_recoverable_exception_word(word):
            self.recovery_reg_snapshots[address & 0xFFFFFFFF] = self._snapshot_regs_for_recovery()
        self._recover_bda_corrupt_pointer_registers(address)
        if self.profile == "bbk9588-uboot" and self._handle_bda_sdkinput_copy_branch(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_bda_sdkinput_copy_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_nand_data_loop_accelerator(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_resource_cache16_hit(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_fat16_cluster_read(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_dirent_copy(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_logo_strip_blit(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_fullscreen_fill_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_boot_frame_copy_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_byte_copy_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_portrait_blit_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_cache_scan_tail(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_fat_free_scan_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_free_scan_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_halfword_copy_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_raster_copy_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_glyph_mask_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_color_span_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_setpixel(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_hline(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_block_read(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_block_write(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_c200_reset_init_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._apply_touch_sample(address):
            return
        if self.profile == "bbk9588-uboot" and address == 0x80006BD0:
            dst = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            value = self.uc.reg_read(UC_MIPS_REG_5) & 0xFF
            size_bytes = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
            if size_bytes <= 0x200000 and self._is_mapped_ram_va(dst, size_bytes):
                self.uc.mem_write(va_to_phys(dst), bytes([value]) * size_bytes)
                self.uc.reg_write(UC_MIPS_REG_2, dst)
                self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
                self._trace_event("memset-bulk", pc=address, addr=dst, value=value, size=size_bytes)
                return
        if self.profile == "bbk9588-uboot" and address == 0x80006BF8:
            dst = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            src = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
            size_bytes = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
            if size_bytes <= 0x200000 and self._is_mapped_ram_va(dst, size_bytes) and self._is_mapped_ram_va(src, size_bytes):
                data = self._read_block_va_safe(src, size_bytes)
                if data is not None:
                    self.uc.mem_write(va_to_phys(dst), data)
                    self.uc.reg_write(UC_MIPS_REG_2, dst)
                    self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
                    self._trace_event("memcpy-bulk", pc=address, addr=dst, value=src, size=size_bytes)
                    return
        self._compensate_repeated_stack_prologue(address)
        self._preexecute_jr_delay(address)
        if not self.fast_hooks:
            self._trace_call(address)
        self._trace_selected_pc(address)
        if address in self.stop_pcs:
            self.state.stop_reason = f"stop_pc_0x{address:08x}"
            self.uc.emu_stop()
            return
        if self._handle_interrupt_return(address):
            return
        if self._maybe_deliver_external_interrupt(address):
            return
        if self._handle_branch_with_mmio_delay(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_malloc_scan_loop(address):
            return
        self._capture_scheduled_call_return(address)
        self._capture_firmware_key_sample_return(address)
        self._capture_touch_sample_return(address)
        self._capture_bda_launch_return(address)
        if self.profile == "bbk9588-uboot" and self._handle_block_image_hook(address):
            return
        if self.profile == "bbk9588-uboot" and address == 0x8001B464 and self._handle_forced_key_scan(address):
            return
        if self.profile == "bbk9588-uboot" and address in (0x8001A6B0, 0x8001A3A0):
            if self._handle_forced_touch_sample(address):
                return
        if self.profile == "bbk9588-uboot" and address == 0x80903AA0:
            # Unicorn can lose the link register after early CP0/cache paths.
            # Fix it at callee entry so the function prologue saves the real
            # caller return address on its stack frame.
            if (self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF) == 4:
                self.uc.reg_write(UC_MIPS_REG_31, 0x80900F70)
        if self.profile == "bbk9588-uboot" and address == 0x80902448:
            if (self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF) == 4:
                self.uc.reg_write(UC_MIPS_REG_31, 0x80903B88)
        if self.profile == "bbk9588-uboot" and address == 0x80903EFC:
            index = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
            block_count = self._read_word_at_va(0x8095BA94) or 0
            if block_count and index >= block_count:
                self._trace_event("nand-index-clamp", pc=address, value=index, limit=block_count)
                self.uc.reg_write(UC_MIPS_REG_2, 0)
        if self.profile == "bbk9588-uboot" and address == 0x800088AC:
            target_node = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            self._write_u32_va(0x80473F30, target_node)
            if self._handle_task_context_restore(address, save_current=False):
                return
        if self.profile == "bbk9588-uboot" and address == 0x800081A8:
            pending = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            self._write_u32_va(0x80473F1C, pending)
            if self._handle_task_context_restore(address, save_current=True):
                return
        if self.profile == "bbk9588-uboot" and address == 0x800A7B40:
            if self._handle_task_context_restore(address, save_current=False):
                return
        if self.profile == "bbk9588-uboot" and address == 0x800A7C18:
            if self._handle_task_context_restore(address, save_current=True):
                return
        if self.profile == "bbk9588-uboot" and address == 0x8005BCD4:
            # MIPS WAIT sleeps until an interrupt on real hardware. Unicorn
            # does not inject the matching interrupt source yet, so model an
            # immediate wake and resume at the register-restore path.
            self.wait_wake_count += 1
            if self._service_pending_irq_from_wait(address, 0x8005BCE8):
                return
            self._trace_event("wait-wake", pc=address, target=0x8005BCE8)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x8005BCE8)
            return
        if self.profile == "bbk9588-uboot" and address == 0x800087C4:
            self.timer_tick_count += 1
        if self.profile == "bbk9588-uboot" and address == 0x80007E08:
            self.scheduler_poll_count += 1
            if self.scheduler_tick_clamp:
                enabled = self._read_mem_va(0x80473F09, 1) & 0xFF
                pending = self._read_mem_va(0x80473F08, 1) & 0xFF
                delay = self._read_mem_va(0x80473F4D, 1) & 0xFF
                if enabled == 1 and (pending != 0 or delay != 0):
                    self._write_mem_va(0x80473F08, 1, 0)
                    self._write_mem_va(0x80473F4D, 1, 0)
                    self._trace_event("scheduler-tick-clamp", pc=address, value=pending, size=delay)
                if enabled == 1:
                    self._trace_event("scheduler-dispatch-direct", pc=address, target=0x800080F0)
                    self.uc.reg_write(UC_MIPS_REG_PC, 0x800080F0)
                    return
        if self.profile == "bbk9588-uboot" and address == 0x800080F0:
            self.scheduler_dispatch_count += 1
        if self.profile == "bbk9588-uboot" and address == 0x80008470:
            self._capture_task_event("task-create", address)
        if self.profile == "bbk9588-uboot" and address in (0x8000A7FC, 0x8000A8A8, 0x8000AA6C, 0x8000AC3C, 0x8000AD90):
            self._capture_task_event("task-table-op", address)
        if self.profile == "bbk9588-uboot" and address in (
            0x80173630,
            0x80173638,
            0x80173764,
            0x8017376C,
            0x80173F2C,
        ):
            self._capture_fs_dir_scan(address)
        if self.profile == "bbk9588-uboot" and self._handle_fs_dir_scan_branch(address):
            return
        if self.profile == "bbk9588-uboot" and address == 0x8001432C:
            v0 = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_17, v0)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x800143B4 if v0 == 0 else 0x80014334)
            self._trace_event("branch-delay-fix", pc=address, value=v0, target=0x800143B4 if v0 == 0 else 0x80014334)
            return
        if self.profile == "bbk9588-uboot" and address == 0x80014414:
            v0 = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_17, v0)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80014334)
            self._trace_event("jump-delay-fix", pc=address, value=v0, target=0x80014334)
            return
        if self.profile == "bbk9588-uboot" and address == 0x80014388:
            s1 = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
            if s1 == 0:
                self.uc.reg_write(UC_MIPS_REG_2, 0xFFFFFFFF)
                self.uc.reg_write(UC_MIPS_REG_PC, 0x80014390)
                self._trace_event("alarm-null-skip", pc=address, target=0x80014390)
                return
        if self.profile == "bbk9588-uboot" and address == 0x8001439C:
            s1 = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
            if s1 == 0:
                self.uc.reg_write(UC_MIPS_REG_2, 2)
                self.uc.reg_write(UC_MIPS_REG_PC, 0x80014304)
                self._trace_event("alarm-tail-skip", pc=address, target=0x80014304)
                return
        if self.profile == "bbk9588-uboot" and address == 0x80170C74:
            a0 = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            if a0 == 0:
                target = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
                self.uc.reg_write(UC_MIPS_REG_2, 0)
                self.uc.reg_write(UC_MIPS_REG_PC, target)
                self._trace_event("null-object-close", pc=address, target=target)
                return
        if self.profile == "bbk9588-uboot" and address in {
            0x8000FEB4: 0x18,
            0x800100C8: 0x28,
            0x801802E8: 0x28,
            0x8017FDCC: 0x30,
            0x8018057C: 0x30,
            0x80184D08: 0x20,
        }:
            frame_size = {
                0x8000FEB4: 0x18,
                0x800100C8: 0x28,
                0x801802E8: 0x28,
                0x8017FDCC: 0x30,
                0x8018057C: 0x30,
                0x80184D08: 0x20,
            }[address]
            target = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_29, (sp + frame_size) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_PC, target)
            self._trace_event("epilogue-jr-fix", pc=address, sp=sp, target=target, size=frame_size)
            return
        if self.profile == "bbk9588-uboot" and address in (0x801813E0, 0x80181400):
            self._capture_return_epilogue(address)
        if self.profile == "bbk9588-uboot" and address == 0x80181400:
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            shifted_ra = self._read_u32_va_safe(sp + 0x50) or 0
            if not (0x80004000 <= ra < 0x80900000) and (0x80004000 <= shifted_ra < 0x80900000):
                shifted_slots = {
                    UC_MIPS_REG_16: 0x38,
                    UC_MIPS_REG_17: 0x3C,
                    UC_MIPS_REG_18: 0x40,
                    UC_MIPS_REG_19: 0x44,
                    UC_MIPS_REG_20: 0x48,
                    UC_MIPS_REG_21: 0x4C,
                }
                for reg, off in shifted_slots.items():
                    value = self._read_u32_va_safe(sp + off)
                    if value is not None:
                        self.uc.reg_write(reg, value)
                self.uc.reg_write(UC_MIPS_REG_31, shifted_ra)
                self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x58) & 0xFFFFFFFF)
                self.uc.reg_write(UC_MIPS_REG_PC, shifted_ra)
                self._trace_event("epilogue-shift-fix", pc=address, sp=sp, value=ra, target=shifted_ra)
                return
        if self.profile == "bbk9588-uboot" and address in (0x80009950, 0x800099F0):
            self._capture_event_queue_snapshot("event-queue-global-ref", address)
        if self.profile == "bbk9588-uboot" and address == 0x8005BCD4:
            self._apply_touch_controller_events(address)
        if self.profile == "bbk9588-uboot" and address == 0x80008A84:
            self.idle_loop_hits += 1
            if self.idle_loop_hits == 1:
                self._trace_event("idle-loop", pc=address, value=self.idle_loop_hits)
            self._apply_scheduled_pokes(address)
            self._activate_mmio_pulses(address)
            if self._apply_gui_key_events(address):
                return
            if self._apply_gui_touch_events(address):
                return
            self._apply_touch_controller_events(address)
            if self._apply_touch_sample(address):
                return
            if self._apply_firmware_key_sample(address):
                return
            if self._apply_bda_launch(address):
                return
            if self._apply_scheduled_calls(address):
                return
            if self._apply_gui_ring_pump(address):
                return
            if self._service_pending_irq_from_wait(address, 0x80008A8C):
                return
            if self.idle_stop_hits > 0 and self.idle_loop_hits >= self.idle_stop_hits:
                self.state.stop_reason = "idle_loop"
                self.uc.emu_stop()
        if self.profile == "bbk9588-uboot" and address == 0x800BD840:
            self.app_idle_loop_hits += 1
            if self.app_idle_loop_hits == 1:
                self._trace_event("app-repaint-loop", pc=address, value=self.app_idle_loop_hits)
            if self.app_idle_stop_hits > 0 and self.app_idle_loop_hits >= self.app_idle_stop_hits:
                self.state.stop_reason = "app_repaint_loop"
                self.uc.emu_stop()
                return
            if not self.bda_app_active:
                return
            # Unicorn repeatedly lands back on this branch target after the
            # preceding bnez delay slot. Model this call-site explicitly:
            #   800bd840: move a1,t1
            #   800bd844: jal  0x800d35f0
            #   800bd848: move a0,s1
            self.uc.reg_write(UC_MIPS_REG_5, self.uc.reg_read(UC_MIPS_REG_9) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_4, self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_31, 0x800BD84C)
            self.repaint_call_context = {
                "sp": self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF,
                "s0": self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF,
                "s1": self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF,
                "ra": 0x800BD84C,
            }
            if self.app_idle_loop_hits == 1:
                self._trace_event("app-repaint-call-fix", pc=address, target=0x800D35F0)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x800D35F0)
            return
        if self.profile == "bbk9588-uboot" and address == 0x800BC2E0:
            if self.bda_initial_draw_context is not None:
                ctx = self.bda_initial_draw_context
                self.bda_initial_draw_context = None
                self.uc.reg_write(UC_MIPS_REG_4, ctx["a0"])
                self.uc.reg_write(UC_MIPS_REG_5, ctx["a1"])
                self.uc.reg_write(UC_MIPS_REG_6, ctx["a2"])
                self.uc.reg_write(UC_MIPS_REG_7, ctx["a3"])
                self.uc.reg_write(UC_MIPS_REG_31, ctx["ra"])
                self._trace_event("bda-initial-draw-return", pc=address, target=ctx["ra"])
            elif self.bda_initial_draw_pending:
                self.bda_initial_draw_pending = False
                self.bda_initial_draw_context = {
                    "a0": self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF,
                    "a1": self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF,
                    "a2": self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF,
                    "a3": self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF,
                    "ra": self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF,
                }
                self.uc.reg_write(UC_MIPS_REG_4, 0)
                self.uc.reg_write(UC_MIPS_REG_5, 0)
                self.uc.reg_write(UC_MIPS_REG_6, 0xEF)
                self.uc.reg_write(UC_MIPS_REG_7, 0x13F)
                self.uc.reg_write(UC_MIPS_REG_31, 0x800BC2E0)
                self.uc.reg_write(UC_MIPS_REG_PC, 0x800D3800)
                self._trace_event("bda-initial-draw-call", pc=address, target=0x800D3800)
                return
        if self.profile == "bbk9588-uboot" and address == 0x800D3634 and self.repaint_call_context:
            # Return block for the explicit 0x800bd840 -> 0x800d35f0 call-site
            # above. The generic stack compensation can corrupt this narrow
            # frame, so restore the ABI-preserved registers and return address
            # from the saved call context.
            ctx = self.repaint_call_context
            self.repaint_call_context = None
            self.uc.reg_write(UC_MIPS_REG_16, ctx["s0"])
            self.uc.reg_write(UC_MIPS_REG_17, ctx["s1"])
            self.uc.reg_write(UC_MIPS_REG_31, ctx["ra"])
            self.uc.reg_write(UC_MIPS_REG_29, ctx["sp"])
            self.uc.reg_write(UC_MIPS_REG_2, self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF)
            self._trace_event("app-repaint-return-fix", pc=address, target=ctx["ra"])
            self.uc.reg_write(UC_MIPS_REG_PC, ctx["ra"])
            return
        if self.profile == "bbk9588-uboot" and address == 0x800CE9F0:
            self.window_close_context = {
                "sp": self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF,
                "ra": self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF,
            }
        if self.profile == "bbk9588-uboot" and address == 0x800CEA30 and self.window_close_context:
            ctx = self.window_close_context
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if ra == 0 and ctx["ra"] not in (0, 4):
                self.uc.reg_write(UC_MIPS_REG_31, ctx["ra"])
                self.uc.reg_write(UC_MIPS_REG_PC, ctx["ra"])
                self.window_close_context = None
                self._trace_event("window-close-return-fix", pc=address, target=ctx["ra"], sp=ctx["sp"])
                return
            self.window_close_context = None
        if self.profile == "bbk9588-uboot" and address == 0x800E123C:
            self.dialog_draw_context = {
                "sp": self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF,
                "ra": self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF,
            }
        if self.profile == "bbk9588-uboot" and address == 0x800E1408 and self.dialog_draw_context:
            ctx = self.dialog_draw_context
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if not self._looks_like_code_return(ra) and self._looks_like_code_return(ctx["ra"]):
                self.uc.reg_write(UC_MIPS_REG_31, ctx["ra"])
                self.uc.reg_write(UC_MIPS_REG_PC, ctx["ra"])
                self.dialog_draw_context = None
                self._trace_event("dialog-draw-return-fix", pc=address, target=ctx["ra"], bad_ra=ra)
                return
            self.dialog_draw_context = None
        if self.profile == "bbk9588-uboot" and address == 0x800E0D68:
            self.event_dispatch_contexts.append(
                {
                    "sp": self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF,
                    "ra": self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF,
                }
            )
        if self.profile == "bbk9588-uboot" and address == 0x800E0E18 and self.event_dispatch_contexts:
            ctx = self.event_dispatch_contexts.pop()
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if not self._looks_like_code_return(ra) and self._looks_like_code_return(ctx["ra"]):
                self.uc.reg_write(UC_MIPS_REG_31, ctx["ra"])
                self.uc.reg_write(UC_MIPS_REG_PC, ctx["ra"])
                self._trace_event("event-dispatch-return-fix", pc=address, target=ctx["ra"], bad_ra=ra)
                return
        if self.profile == "bbk9588-uboot" and address == 0x800DD4B8:
            self.object_callback_contexts.append(
                {
                    "sp": self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF,
                    "ra": self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF,
                }
            )
        if self.profile == "bbk9588-uboot" and address == 0x800DD510 and self.object_callback_contexts:
            ctx = self.object_callback_contexts.pop()
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if not self._looks_like_code_return(ra) and self._looks_like_code_return(ctx["ra"]):
                self.uc.reg_write(UC_MIPS_REG_31, ctx["ra"])
                self.uc.reg_write(UC_MIPS_REG_PC, ctx["ra"])
                self._trace_event("object-callback-return-fix", pc=address, target=ctx["ra"], bad_ra=ra)
                return
        if self.profile == "bbk9588-uboot" and address == 0x800DD58C:
            self.display_event_contexts.append(
                {
                    "sp": self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF,
                    "s0": self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF,
                    "s1": self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF,
                    "s2": self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF,
                    "s3": self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF,
                    "s4": self.uc.reg_read(UC_MIPS_REG_20) & 0xFFFFFFFF,
                    "ra": self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF,
                }
            )
        if self.profile == "bbk9588-uboot" and address == 0x800DD734 and self.display_event_contexts:
            ctx = self.display_event_contexts.pop()
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if not self._looks_like_code_return(ra) and self._looks_like_code_return(ctx["ra"]):
                self.uc.reg_write(UC_MIPS_REG_29, ctx["sp"])
                self.uc.reg_write(UC_MIPS_REG_16, ctx["s0"])
                self.uc.reg_write(UC_MIPS_REG_17, ctx["s1"])
                self.uc.reg_write(UC_MIPS_REG_18, ctx["s2"])
                self.uc.reg_write(UC_MIPS_REG_19, ctx["s3"])
                self.uc.reg_write(UC_MIPS_REG_20, ctx["s4"])
                self.uc.reg_write(UC_MIPS_REG_31, ctx["ra"])
                self.uc.reg_write(UC_MIPS_REG_PC, ctx["ra"])
                self._trace_event("display-event-return-fix", pc=address, target=ctx["ra"], bad_ra=ra)
                return
        if self.profile == "bbk9588-uboot" and address == 0x800B3950:
            self._seed_surface_dirty_rect(self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF, address)
        if self.profile == "bbk9588-uboot" and address in (0x800C0D40, 0x80119B50, 0x8011A3C4):
            self._trace_system_text_entry(address)
        if self.profile == "bbk9588-uboot" and self.bda_text_mode == "ascii-hook" and address == 0x8011A3C4:
            if self._draw_synthetic_glyph_for_bda_text(address):
                return
        if self.profile == "bbk9588-uboot" and self.bda_text_mode == "native" and address == 0x8011A3C4:
            self._trace_bda_native_text_draw(address)
        if self.profile == "bbk9588-uboot" and address == 0x8011B054:
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            glyph = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
            code: int | None = None
            if self.bda_app_active and not self._is_mapped_ram_va(glyph, 1) and self._is_mapped_ram_va(0x80825AD0, 0x48):
                if glyph < 0x4000:
                    code = (glyph // 0x20) & 0xFF
                    self.native_synthetic_glyph_code = code
                    glyph_data = self._ascii_glyph_16x16_1bpp(code)
                    self.uc.mem_write(va_to_phys(0x80825AD0), glyph_data)
                    self.uc.mem_write(va_to_phys(0x80825AF0), glyph_data)
                else:
                    code = 0
                self.uc.reg_write(UC_MIPS_REG_6, 0x80825AD0)
                width = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
                height = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
                mode = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
                dst = self._read_u32_va_safe(sp + 0x10) or 0
                bg = self._read_u32_va_safe(sp + 0x14) or 0
                fg = self._read_u32_va_safe(sp + 0x18) or 0
                opaque = bool(self._read_u32_va_safe(sp + 0x1C) or 0)
                x_pad = self._read_u32_va_safe(sp + 0x20) or 0
                y_flip = self._read_u32_va_safe(sp + 0x24) or 0
                stride = (mode * (width + x_pad + y_flip)) & 0xFFFFFFFF
                self._trace_event(
                    "font-glyph-buffer-recover",
                    pc=address,
                    addr=glyph,
                    value=0x80825AD0,
                    size=code,
                    width=width,
                    height=height,
                    mode=mode,
                )
                if (
                    self.bda_text_mode == "native"
                    and self.bda_native_raster_mode == "synth"
                    and dst
                    and width == 16
                    and height == 16
                    and mode == 2
                    and 0x20 <= code < 0x7F
                    and self._is_mapped_ram_va(dst, max(stride, 32) * 16)
                ):
                    pixels = self._draw_ascii_glyph_to_raster_surface(dst, stride or 32, code, fg, bg, opaque)
                    self.uc.reg_write(UC_MIPS_REG_2, stride or 32)
                    self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
                    self._trace_event(
                        "native-glyph-raster-synth",
                        pc=address,
                        addr=dst,
                        value=code,
                        size=pixels,
                        stride=stride or 32,
                        fg=fg,
                        bg=bg,
                        opaque=int(opaque),
                    )
                    return
            elif (
                self.bda_app_active
                and self.bda_text_mode == "native"
                and glyph in (0x80825AD0, 0x80825AF0)
                and self.native_synthetic_glyph_code is not None
            ):
                code = self.native_synthetic_glyph_code
                width = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
                height = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
                mode = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
                dst = self._read_u32_va_safe(sp + 0x10) or 0
                bg = self._read_u32_va_safe(sp + 0x14) or 0
                fg = self._read_u32_va_safe(sp + 0x18) or 0
                opaque = bool(self._read_u32_va_safe(sp + 0x1C) or 0)
                x_pad = self._read_u32_va_safe(sp + 0x20) or 0
                y_flip = self._read_u32_va_safe(sp + 0x24) or 0
                stride = (mode * (width + x_pad + y_flip)) & 0xFFFFFFFF
                if (
                    dst
                    and width == 16
                    and height == 16
                    and mode == 2
                    and 0x20 <= code < 0x7F
                    and self._is_mapped_ram_va(dst, max(stride, 32) * 16)
                ):
                    pixels = self._draw_ascii_glyph_to_raster_surface(dst, stride or 32, code, fg, bg, opaque)
                else:
                    pixels = 0
                self._trace_event(
                    "native-glyph-raster-synth-repeat",
                    pc=address,
                    addr=dst,
                    value=code,
                    size=pixels,
                    stride=stride or 32,
                    fg=fg,
                    bg=bg,
                    opaque=int(opaque),
                )
                if self.bda_native_raster_mode == "synth":
                    self.uc.reg_write(UC_MIPS_REG_2, stride or 32)
                    self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
                    return
            if self.bda_text_mode == "native":
                self._trace_event(
                    "native-glyph-raster-entry",
                    pc=address,
                    a0=self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF,
                    a1=self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF,
                    a2=self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF,
                    a3=self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF,
                    sp=sp,
                    dst=self._read_u32_va_safe(sp + 0x10) or 0,
                    bg=self._read_u32_va_safe(sp + 0x14) or 0,
                    fg=self._read_u32_va_safe(sp + 0x18) or 0,
                    opaque=self._read_u32_va_safe(sp + 0x1C) or 0,
                    x_pad=self._read_u32_va_safe(sp + 0x20) or 0,
                    y_flip=self._read_u32_va_safe(sp + 0x24) or 0,
                )
        if self.profile == "bbk9588-uboot" and self.bda_text_mode == "native" and address in {
            0x8011B0CC,
            0x8011B20C,
            0x8011B25C,
        }:
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            s0 = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
            s1 = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
            s3 = self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF
            s4 = self.uc.reg_read(UC_MIPS_REG_20) & 0xFFFFFFFF
            self._trace_event(
                "native-text-raster-path",
                pc=address,
                a0=self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF,
                a1=self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF,
                a2=self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF,
                a3=self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF,
                s0=s0,
                s1=s1,
                s3=s3,
                s4=s4,
                sp=sp,
                s0_w04=self._read_u32_va_safe(s0 + 0x04) or 0,
                s0_w34=self._read_u32_va_safe(s0 + 0x34) or 0,
                s0_w38=self._read_u32_va_safe(s0 + 0x38) or 0,
                s0_w40=self._read_u32_va_safe(s0 + 0x40) or 0,
                s0_w48=self._read_u32_va_safe(s0 + 0x48) or 0,
                s1_w14=self._read_u32_va_safe(s1 + 0x14) or 0,
                s1_w18=self._read_u32_va_safe(s1 + 0x18) or 0,
            )
        if self.profile == "bbk9588-uboot" and address == 0x800B7350:
            target = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
            s1 = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
            a0 = self._read_u32_va_safe(s1 + 0x10) or 0
            if self._looks_like_code_return(target):
                self.uc.reg_write(UC_MIPS_REG_4, a0)
                self.uc.reg_write(UC_MIPS_REG_31, 0x800B7358)
                self.uc.reg_write(UC_MIPS_REG_PC, target)
                self._trace_event("jalr-delay-fix", pc=address, target=target, addr=s1, value=a0)
                return
        if self.profile == "bbk9588-uboot" and address == 0x800B737C:
            v1 = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
            value = self._read_u32_va_safe(v1 + 0x98) or 0
            self.uc.reg_write(UC_MIPS_REG_2, value)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x800B7350)
            self._trace_event("jump-delay-load-fix", pc=address, target=0x800B7350, addr=v1 + 0x98, value=value)
            return
        if self.profile == "bbk9588-uboot" and address == 0x8000B2C8:
            self._capture_event_queue_snapshot("event-queue-before-pop-read", address)
            if self._return_synthetic_event_from_bad_queue(address):
                return
        if self.profile == "bbk9588-uboot" and address in (0x8000B25C, 0x8012CCF0, 0x8012CCFC):
            self._capture_event_queue_snapshot("event-queue-read-path", address)
        if self.profile == "bbk9588-uboot" and address == 0x8012CCFC:
            event = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
            if event == 0:
                self.bda_event_poll_hits += 1
                if self.synthetic_event_va is None:
                    self.synthetic_event_va = self._scratch_alloc(0x20)
                event = self.synthetic_event_va
                bda_key = self._next_bda_key_event_due()
                if bda_key is not None:
                    self.bda_idle_empty_polls = 0
                    self._write_bda_synthetic_event(event, bda_key.event_type, bda_key.code)
                    bda_key.applied = True
                    row = {
                        "event": "bda-key",
                        "pc": f"0x{address:08x}",
                        "event_hit": bda_key.event_hit,
                        "code": bda_key.code,
                        "event_type": bda_key.event_type,
                        "event_va": f"0x{event:08x}",
                    }
                    self.bda_key_event_log.append(row)
                    self.uc.reg_write(UC_MIPS_REG_2, event)
                    self._trace_event(
                        "bda-key-event",
                        pc=address,
                        addr=event,
                        value=(bda_key.event_type << 8) | (bda_key.code & 0xFF),
                        size=4,
                    )
                    return
                bda_touch = self._next_bda_touch_event_due()
                if bda_touch is not None:
                    self.bda_idle_empty_polls = 0
                    self._write_touch_globals(bda_touch.x, bda_touch.y, bda_touch.down)
                    self._write_bda_synthetic_event(
                        event,
                        bda_touch.event_type,
                        (bda_touch.x & 0xFFFF) | ((bda_touch.y & 0xFFFF) << 16),
                        int(bda_touch.down),
                        0,
                    )
                    bda_touch.applied = True
                    row = {
                        "event": "bda-touch",
                        "pc": f"0x{address:08x}",
                        "event_hit": bda_touch.event_hit,
                        "event_type": bda_touch.event_type,
                        "x": bda_touch.x,
                        "y": bda_touch.y,
                        "down": int(bda_touch.down),
                        "event_va": f"0x{event:08x}",
                    }
                    self.bda_touch_event_log.append(row)
                    self.uc.reg_write(UC_MIPS_REG_2, event)
                    self._trace_event(
                        "bda-touch-event",
                        pc=address,
                        addr=event,
                        value=(bda_touch.x & 0xFFFF) | ((bda_touch.y & 0xFFFF) << 16),
                        size=0x10,
                    )
                    return
                bda_event = self._next_bda_event_due()
                if bda_event is not None:
                    self.bda_idle_empty_polls = 0
                    self._write_bda_synthetic_event(
                        event,
                        bda_event.event_type,
                        bda_event.word0,
                        bda_event.word2,
                        bda_event.word3,
                    )
                    bda_event.applied = True
                    row = {
                        "event": "bda-event",
                        "pc": f"0x{address:08x}",
                        "event_hit": bda_event.event_hit,
                        "event_type": bda_event.event_type,
                        "word0": f"0x{bda_event.word0 & 0xFFFFFFFF:08x}",
                        "word2": f"0x{bda_event.word2 & 0xFFFFFFFF:08x}",
                        "word3": f"0x{bda_event.word3 & 0xFFFFFFFF:08x}",
                        "event_va": f"0x{event:08x}",
                    }
                    self.bda_event_log.append(row)
                    self.uc.reg_write(UC_MIPS_REG_2, event)
                    self._trace_event(
                        "bda-event",
                        pc=address,
                        addr=event,
                        value=bda_event.event_type,
                        size=0x10,
                    )
                    return
                display_flags = self._read_u32_va_safe(0x80825840) or 0
                if (
                    self.bda_app_active
                    and self.bda_initial_draw_context is None
                    and display_flags == 0
                    and not self._has_pending_future_bda_key_event()
                    and not self._has_pending_future_bda_event()
                    and not self._has_pending_future_bda_touch_event()
                ):
                    self.bda_idle_empty_polls += 1
                    if self.bda_idle_empty_polls >= self.bda_idle_stop_polls:
                        self.state.stop_reason = "bda_event_idle"
                        self._trace_event("bda-event-idle", pc=address, value=self.bda_idle_empty_polls)
                        self.uc.emu_stop()
                        return
                else:
                    self.bda_idle_empty_polls = 0
                event_type = 0x03 if (display_flags & 0x70000000) else 0x00
                self._write_bda_synthetic_event(event, event_type)
                self.uc.reg_write(UC_MIPS_REG_2, event)
                self._trace_event("event-null-fix", pc=address, addr=event, value=event_type, flags=display_flags)
        if self.profile == "bbk9588-uboot" and address in (
            0x80010D70,
            0x80010D7C,
            0x80010D88,
            0x80010D94,
            0x80010DA0,
        ):
            # These C200 LCD helpers are pure getters implemented as
            # "lui; jr ra; lw". Unicorn's MIPS delay-slot handling is unstable
            # on this path, so return their known profile values at function
            # entry instead of relying on the delay-slot load.
            getter_values = {
                0x80010D70: 0x000000F0,
                0x80010D7C: 0x00000140,
                0x80010D88: 0x00000010,
                0x80010D94: 0xA1F82000,
                0x80010DA0: 0xA1F81000,
            }
            value = getter_values[address]
            self.uc.reg_write(UC_MIPS_REG_2, value)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self._trace_event("lcd-getter", pc=address, value=value)
            return
        if self.profile == "bbk9588-uboot" and address == 0x8012BE84:
            surface = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            x = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
            y = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
            try:
                stride = self._read_mem_va(surface + 0x18, 4) & 0xFFFFFFFF
                buffer = self._read_mem_va(surface + 0x44, 4) & 0xFFFFFFFF
                ptr = (buffer + y * stride + (x << 1)) & 0xFFFFFFFF
                value = self._read_mem_va(ptr, 2) & 0xFFFF
            except Exception:
                stride = 0
                buffer = 0
                ptr = 0
                value = 0
            self.uc.reg_write(UC_MIPS_REG_2, value)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self.surface_pixel_read_count += 1
            self._record_surface_event(
                "pixel-read",
                address,
                surface=surface,
                buffer=buffer,
                x=x,
                y=y,
                width=1,
                height=1,
                pitch=stride,
                color=value,
                addr=ptr,
            )
            if self.surface_pixel_read_count <= 32 or self.surface_pixel_read_count % 4096 == 0:
                self._trace_event("surface-pixel-read", pc=address, addr=ptr, value=value, size=2)
            return
        if self.profile == "bbk9588-uboot" and self.font_helper_accelerator and address == 0x8012A6A8:
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if ra in (0x80119C98, 0x80119EA4, 0x8011A16C, 0x80119FC8):
                text = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
                remaining = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
                consumed = 0
                if remaining:
                    try:
                        first = self._read_mem_va(text, 1) & 0xFF
                        consumed = 2 if first >= 0x80 and remaining >= 2 else 1
                    except Exception:
                        consumed = 1
                self.uc.reg_write(UC_MIPS_REG_2, consumed)
                self.uc.reg_write(UC_MIPS_REG_PC, ra)
                self._trace_event("font-next-char", pc=address, addr=text, value=consumed, size=remaining)
                return
            if ra == 0x8012A730:
                text = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
                try:
                    glyph_index = self._read_mem_va(text, 1) & 0xFF
                except Exception:
                    glyph_index = 0
                self.uc.reg_write(UC_MIPS_REG_2, glyph_index)
                self.uc.reg_write(UC_MIPS_REG_PC, ra)
                self._trace_event("font-glyph-index", pc=address, addr=text, value=glyph_index, size=1)
                return
        if self.profile == "bbk9588-uboot" and address in (0x800A899C, 0x800A89A4, 0x800A89AC, 0x800A89B4):
            # Small display-object getters implemented as "jr ra; lw". Model
            # the delay-slot load explicitly to avoid Unicorn returning to 0.
            obj = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            getter_offsets = {
                0x800A899C: 0x14,
                0x800A89A4: 0x00,
                0x800A89AC: 0x04,
                0x800A89B4: 0x3C,
            }
            value = self._read_u32_va_safe(obj + getter_offsets[address]) or 0
            self.uc.reg_write(UC_MIPS_REG_2, value)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self._trace_event("display-getter", pc=address, addr=obj, value=value)
            return
        if self.profile == "bbk9588-uboot" and address == 0x800043CC:
            # C200 software delay loop. Fast-forward it so traces expose real
            # device waits instead of spending millions of instructions here.
            count = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
            if count:
                self._trace_event("delay-skip", pc=address, count=count)
                self.uc.reg_write(UC_MIPS_REG_2, 0)
        if self.profile == "bbk9588-uboot" and address == 0x8000FEC0:
            self._trace_blit_submit(address)
        if self.profile == "bbk9588-uboot" and address == 0x800BC9CC:
            table = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
            target = self._read_u32_va_safe(table + 0x28) or 0
            self.uc.reg_write(UC_MIPS_REG_2, target)
            if self._handle_display_getter_jalr(0x800BC9AC):
                return
        if self.profile == "bbk9588-uboot" and address in (0x800BC944, 0x800BC9AC):
            if self._handle_display_getter_jalr(address):
                return
        if self.profile == "bbk9588-uboot" and address == 0x800D3368:
            # Direct diagnostic BDA launch can reach this layout-list append
            # with a zero-sized pool descriptor, causing 0x800d2ce0 to return
            # null. Real launcher context appears to initialize that pool; give
            # this narrow node append a scratch node so app startup can proceed.
            v0 = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
            if v0 == 0:
                node = self._scratch_alloc(0x20)
                self.uc.reg_write(UC_MIPS_REG_2, node)
                self._trace_event("layout-node-scratch", pc=address, addr=node, size=0x20)
        if self.profile == "bbk9588-uboot" and address in (0x800128CC, 0x80010D94):
            self._write_u32_va(0x8033C0E4, 0xA1F81000)
            self._write_u32_va(0x8033C0E8, 0xA1F82000)
        if self.profile == "bbk9588-uboot" and address == 0x800128D4:
            self.uc.reg_write(UC_MIPS_REG_2, 0xA1F82000)
        if self.profile == "bbk9588-uboot" and address == 0x800129AC:
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if not (0x80004000 <= ra < 0x80900000):
                sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
                self._trace_event("ra-fix", pc=address, value=ra, target=0x80004CC4, sp=sp)
                self.uc.reg_write(UC_MIPS_REG_31, 0x80004CC4)
                self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x18) & 0xFFFFFFFF)
                self.uc.reg_write(UC_MIPS_REG_PC, 0x80004CC4)
        if self.profile == "bbk9588-uboot" and address == 0x800176E0:
            # Returning from 0x800171b4 sometimes skips its "jr ra" delay-slot
            # stack restore. Correct it only when the current frame's saved RA
            # is not a C200 code address but the next frame's saved RA is.
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            saved_ra = self._read_mem_va(sp + 0x10, 4)
            next_saved_ra = self._read_mem_va(sp + 0x28, 4)
            if not (0x80004000 <= saved_ra < 0x80900000) and (0x80004000 <= next_saved_ra < 0x80900000):
                self._trace_event("stack-fix", pc=address, sp=sp, value=saved_ra, target=next_saved_ra)
                self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x18) & 0xFFFFFFFF)
        if self.profile == "bbk9588-uboot" and address == 0x800DE5BC:
            # Same Unicorn delay-slot stack leak pattern in the main UI init
            # path. The current frame's saved RA is at sp+0x18; if it is zero
            # but sp+0x30 contains a valid caller, one nested 0x18-byte frame
            # failed to unwind.
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            saved_ra = self._read_mem_va(sp + 0x18, 4)
            next_saved_ra = self._read_mem_va(sp + 0x30, 4)
            if not (0x80004000 <= saved_ra < 0x80900000) and (0x80004000 <= next_saved_ra < 0x80900000):
                self._trace_event("stack-fix", pc=address, sp=sp, value=saved_ra, target=next_saved_ra)
                self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x18) & 0xFFFFFFFF)
        if self.profile == "bbk9588-uboot" and address == 0x80183304:
            # 0x8018308c's epilogue sometimes sees SP 0x38 bytes too high.
            # The correct saved RA is then at sp+4 instead of sp+0x3c.
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            saved_ra = self._read_mem_va(sp + 0x3C, 4)
            shifted_saved_ra = self._read_mem_va(sp + 4, 4)
            if not (0x80004000 <= saved_ra < 0x80900000) and (0x80004000 <= shifted_saved_ra < 0x80900000):
                self._trace_event("stack-fix", pc=address, sp=sp, value=saved_ra, target=shifted_saved_ra)
                self.uc.reg_write(UC_MIPS_REG_29, (sp - 0x38) & 0xFFFFFFFF)
        if self.profile == "bbk9588-uboot" and address == 0x8017A860:
            # Branching to the short epilogue at 0x8017a858 can skip the
            # "lw ra,0x10(sp)" immediately before "jr ra". If RA is invalid,
            # complete the epilogue here and return to the saved caller.
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            saved_ra = self._read_mem_va(sp + 0x10, 4)
            if not (0x80004000 <= ra < 0x80900000) and (0x80004000 <= saved_ra < 0x80900000):
                self._trace_event("epilogue-fix", pc=address, sp=sp, value=ra, target=saved_ra)
                self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x18) & 0xFFFFFFFF)
                self.uc.reg_write(UC_MIPS_REG_31, saved_ra)
                self.uc.reg_write(UC_MIPS_REG_PC, saved_ra)
                return
            shifted_saved_ra = self._read_mem_va(sp - 8, 4)
            if not (0x80004000 <= ra < 0x80900000) and (0x80004000 <= shifted_saved_ra < 0x80900000):
                self._trace_event("epilogue-fix", pc=address, sp=sp, value=ra, target=shifted_saved_ra)
                self.uc.reg_write(UC_MIPS_REG_31, shifted_saved_ra)
                self.uc.reg_write(UC_MIPS_REG_PC, shifted_saved_ra)
                return
        if self.profile == "bbk9588-uboot" and address == 0x801737B8:
            # Deep FAT directory scanning can arrive at this large-frame
            # epilogue with SP 0x20 bytes too low after Unicorn/repeat-prologue
            # recovery. Prefer the adjacent valid frame only when the normal
            # saved RA slot is clearly not a firmware return address.
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            saved_ra = self._read_mem_va(sp + 0xEC, 4)
            shifted_saved_ra = self._read_mem_va(sp + 0x10C, 4)
            if not (0x80004000 <= saved_ra < 0x80900000) and (0x80004000 <= shifted_saved_ra < 0x80900000):
                self._trace_event("stack-fix", pc=address, sp=sp, value=saved_ra, target=shifted_saved_ra)
                self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x20) & 0xFFFFFFFF)
        if self.profile == "bbk9588-uboot" and address in (
            0x80900F70,
            0x80900F78,
            0x80900F80,
            0x80902448,
            0x8090247C,
            0x809024B8,
            0x809024C4,
            0x809024CC,
            0x809024D4,
            0x809024DC,
            0x809024F8,
            0x80902510,
            0x80902520,
            0x809080A0,
            0x80908188,
            0x809081A0,
            0x809081A4,
            0x80908284,
            0x80908288,
            0x8090828C,
            0x80903BB0,
            0x80903BB8,
            0x80903BC0,
            0x80903BCC,
            0x80903BD4,
            0x80903BE8,
            0x80903C2C,
            0x80904EC8,
            0x80908294,
        ):
            self._trace_event(
                "probe",
                pc=address,
                v0=self.uc.reg_read(UC_MIPS_REG_2),
                a0=self.uc.reg_read(UC_MIPS_REG_4),
                a2=self.uc.reg_read(UC_MIPS_REG_6),
                s0=self.uc.reg_read(UC_MIPS_REG_16),
                sp=self.uc.reg_read(UC_MIPS_REG_29),
                ra=self.uc.reg_read(UC_MIPS_REG_31),
            )
        if self.profile == "bbk9588-uboot" and address == 0x80906780:
            # This BSS/global is consumed as a divisor in the serial/print path.
            # If NAND geometry probing failed, avoid a divide-by-zero so the
            # next missing peripheral remains visible in the trace.
            divisor = self._read_word_at_va(0x8095BB54)
            if divisor == 0:
                self._write_u32_va(0x8095BB54, 0x40)
        self.state.insn_count += 1
        self.state.last_pc = address
        self.state.pcs.append(address)
        if len(self.state.pcs) > 64:
            del self.state.pcs[0]

    def _compensate_repeated_stack_prologue(self, address: int) -> None:
        if self.repeat_prologue_mode == "off":
            return
        if self.profile != "bbk9588-uboot" or self.state.last_pc != address:
            return
        word = self._read_word_at_va(address)
        if word is None:
            return
        opcode = (word >> 26) & 0x3F
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        imm = word & 0xFFFF
        if imm & 0x8000:
            imm -= 0x10000
        # Work around a Unicorn MIPS quirk observed on U-Boot helper entries:
        # the first instruction can be presented twice. If that instruction is
        # a stack-frame allocation, cancel the first copy so the second leaves
        # one real frame, not two.
        if opcode == 9 and rs == 29 and rt == 29 and imm < 0:
            sp = self.uc.reg_read(UC_MIPS_REG_29)
            row: dict[str, object] = {
                "pc": f"0x{address:08x}",
                "mode": self.repeat_prologue_mode,
                "word": f"0x{word:08x}",
                "sp": f"0x{sp & 0xFFFFFFFF:08x}",
                "ra": f"0x{self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF:08x}",
                "last_pc": f"0x{self.state.last_pc:08x}",
                "recent_pcs": [f"0x{pc:08x}" for pc in self.state.pcs[-16:]],
                "recent_recoveries": self.state.recoveries[-8:],
            }
            self.repeat_prologue_events.append(row)
            if len(self.repeat_prologue_events) > 256:
                del self.repeat_prologue_events[0]
            self._trace_event("repeat-sp-observed", pc=address, sp=sp, imm=imm)
            if self.repeat_prologue_mode == "stop":
                self.state.stop_reason = "repeat_prologue"
                self.uc.emu_stop()
                return
            if self.repeat_prologue_mode == "fix":
                self.uc.reg_write(UC_MIPS_REG_29, (sp - imm) & 0xFFFFFFFF)
                self._trace_event("repeat-sp-fix", pc=address, sp=sp, imm=imm)

    def _preexecute_jr_delay(self, address: int) -> None:
        if self.profile != "bbk9588-uboot":
            return
        return
        word = self._read_word_at_va(address)
        if word is None:
            return
        # Unicorn's MIPS core is observed to skip jr delay slots on these boot
        # paths. Pre-execute the delay slot so stack epilogues such as
        # "jr ra; addiu sp,sp,0x18" do not leak stack space per call.
        if (word >> 26) == 0 and (word & 0x001FFFFF) == 0x00000008 and (word & 0x3F) == 8:
            self._emulate_delay_slot(address + 4)
            self.preexecuted_jr_delay_pc = address

    def _trace_event(self, kind: str, **values: int) -> None:
        row = {"kind": kind}
        row.update({k: f"0x{v & 0xFFFFFFFF:08x}" for k, v in values.items()})
        self.state.events.append(row)
        if len(self.state.events) > max(128, self.trace_limit):
            del self.state.events[0]

    def _read_task_name(self, node_va: int) -> str:
        raw = self._read_block_va_safe((node_va + 0x50) & 0xFFFFFFFF, 0x30)
        if raw is None:
            return ""
        raw = raw.split(b"\x00", 1)[0]
        if not raw:
            return ""
        for encoding in ("gb18030", "ascii", "latin1"):
            try:
                return raw.decode(encoding, errors="replace")
            except Exception:
                continue
        return raw.hex()

    def _read_c_string_va_safe(self, va: int, limit: int = 160) -> str | None:
        if va in (0, 0xFFFFFFFF) or not self._is_mapped_ram_va(va, 1):
            return None
        raw = bytearray()
        for off in range(limit):
            if not self._is_mapped_ram_va((va + off) & 0xFFFFFFFF, 1):
                break
            ch = self._read_mem_va((va + off) & 0xFFFFFFFF, 1) & 0xFF
            if ch == 0:
                break
            raw.append(ch)
        if not raw:
            return None
        printable = sum(1 for b in raw if b in (9, 10, 13) or 0x20 <= b < 0x7F or b >= 0x80)
        if printable < max(1, len(raw) * 3 // 4):
            return None
        for encoding in ("gb18030", "utf-8", "ascii", "latin1"):
            try:
                text = bytes(raw).decode(encoding, errors="replace")
                break
            except Exception:
                continue
        else:
            text = bytes(raw).hex()
        return text.replace("\r", "\\r").replace("\n", "\\n")

    def _task_node_snapshot(self, node_va: int | None) -> dict[str, object] | None:
        if node_va is None or node_va in (0, 1) or not (0x80000000 <= node_va < 0x81000000):
            return None
        raw = self._read_block_va_safe(node_va, 0x80)
        if raw is None:
            return None

        def u32(off: int) -> int:
            return struct.unpack_from("<I", raw, off)[0]

        def u8(off: int) -> int:
            return raw[off]

        return {
            "node": f"0x{node_va:08x}",
            "entry": f"0x{u32(0x00):08x}",
            "stack_or_arg4": f"0x{u32(0x04):08x}",
            "arg0": f"0x{u32(0x08):08x}",
            "arg1": f"0x{u32(0x0c):08x}",
            "arg2": f"0x{u32(0x10):08x}",
            "arg3": f"0x{u32(0x14):08x}",
            "next": f"0x{u32(0x18):08x}",
            "prev": f"0x{u32(0x1c):08x}",
            "wait_obj": f"0x{u32(0x20):08x}",
            "msg_head": f"0x{u32(0x24):08x}",
            "msg_tail": f"0x{u32(0x28):08x}",
            "flags34": f"0x{u8(0x34):02x}",
            "task_id35": f"0x{u8(0x35):02x}",
            "slot36": f"0x{u8(0x36):02x}",
            "group37": f"0x{u8(0x37):02x}",
            "mask38": f"0x{u8(0x38):02x}",
            "group_mask39": f"0x{u8(0x39):02x}",
            "name": self._read_task_name(node_va),
        }

    def _capture_task_event(self, kind: str, pc: int) -> None:
        s0 = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        s1 = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        s2 = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        a0 = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        a1 = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        a2 = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        a3 = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        row: dict[str, object] = {
            "kind": kind,
            "pc": f"0x{pc:08x}",
            "s0_node": f"0x{s0:08x}",
            "s1_task_id": f"0x{s1 & 0xFF:02x}",
            "s2_entry": f"0x{s2:08x}",
            "a0": f"0x{a0:08x}",
            "a1": f"0x{a1:08x}",
            "a2": f"0x{a2:08x}",
            "a3": f"0x{a3:08x}",
            "sp": f"0x{sp:08x}",
            "stack_38": f"0x{(self._read_u32_va_safe(sp + 0x38) or 0):08x}",
            "stack_3c": f"0x{(self._read_u32_va_safe(sp + 0x3C) or 0):08x}",
            "stack_40": f"0x{(self._read_u32_va_safe(sp + 0x40) or 0):08x}",
            "node": self._task_node_snapshot(s0),
        }
        self.task_events.append(row)
        if len(self.task_events) > max(256, self.trace_limit):
            del self.task_events[0]

    def _capture_task_table_write(self, address: int, value: int) -> None:
        pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        phys = address & 0x1FFFFFFF if address >= RAM_BASE else address
        slot = (phys - 0x006C5D10) // 4
        row: dict[str, object] = {
            "pc": f"0x{pc:08x}",
            "addr": f"0x{address:08x}",
            "slot": int(slot),
            "value": f"0x{value & 0xFFFFFFFF:08x}",
            "node": self._task_node_snapshot(value & 0xFFFFFFFF),
        }
        self.task_table_write_events.append(row)
        if len(self.task_table_write_events) > max(512, self.trace_limit):
            del self.task_table_write_events[0]

    def _task_context_reg_offsets(self) -> list[tuple[int, int]]:
        return [
            (UC_MIPS_REG_31, 0x00),
            (UC_MIPS_REG_30, 0x04),
            (UC_MIPS_REG_25, 0x08),
            (UC_MIPS_REG_24, 0x0C),
            (UC_MIPS_REG_23, 0x10),
            (UC_MIPS_REG_22, 0x14),
            (UC_MIPS_REG_21, 0x18),
            (UC_MIPS_REG_20, 0x1C),
            (UC_MIPS_REG_19, 0x20),
            (UC_MIPS_REG_18, 0x24),
            (UC_MIPS_REG_17, 0x28),
            (UC_MIPS_REG_16, 0x2C),
            (UC_MIPS_REG_15, 0x30),
            (UC_MIPS_REG_14, 0x34),
            (UC_MIPS_REG_13, 0x38),
            (UC_MIPS_REG_12, 0x3C),
            (UC_MIPS_REG_11, 0x40),
            (UC_MIPS_REG_10, 0x44),
            (UC_MIPS_REG_9, 0x48),
            (UC_MIPS_REG_8, 0x4C),
            (UC_MIPS_REG_7, 0x50),
            (UC_MIPS_REG_6, 0x54),
            (UC_MIPS_REG_5, 0x58),
            (UC_MIPS_REG_4, 0x5C),
            (UC_MIPS_REG_3, 0x60),
            (UC_MIPS_REG_2, 0x64),
            (UC_MIPS_REG_1, 0x68),
        ]

    def _save_task_context(self, node_va: int, resume_pc: int) -> int | None:
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        ctx_sp = (sp - 0x7C) & 0xFFFFFFFF
        if self._read_block_va_safe(ctx_sp, 0x7C) is None:
            return None
        for reg, off in self._task_context_reg_offsets():
            self._write_u32_va(ctx_sp + off, self.uc.reg_read(reg) & 0xFFFFFFFF)
        try:
            status = self.uc.reg_read(UC_MIPS_REG_CP0_STATUS) & 0xFFFFFFFF
        except Exception:
            status = 0x10000401
        try:
            lo = self.uc.reg_read(UC_MIPS_REG_LO) & 0xFFFFFFFF
            hi = self.uc.reg_read(UC_MIPS_REG_HI) & 0xFFFFFFFF
        except Exception:
            lo = hi = 0
        self._write_u32_va(ctx_sp + 0x6C, status)
        self._write_u32_va(ctx_sp + 0x70, resume_pc)
        self._write_u32_va(ctx_sp + 0x74, lo)
        self._write_u32_va(ctx_sp + 0x78, hi)
        self._write_u32_va(node_va, ctx_sp)
        return ctx_sp

    def _restore_task_context(self, ctx_sp: int) -> int | None:
        raw = self._read_block_va_safe(ctx_sp, 0x7C)
        if raw is None:
            return None

        def u32(off: int) -> int:
            return struct.unpack_from("<I", raw, off)[0]

        for reg, off in self._task_context_reg_offsets():
            self.uc.reg_write(reg, u32(off))
        try:
            self.uc.reg_write(UC_MIPS_REG_CP0_STATUS, u32(0x6C))
        except Exception:
            pass
        try:
            self.uc.reg_write(UC_MIPS_REG_LO, u32(0x74))
            self.uc.reg_write(UC_MIPS_REG_HI, u32(0x78))
        except Exception:
            pass
        target = u32(0x70)
        self.uc.reg_write(UC_MIPS_REG_29, (ctx_sp + 0x7C) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_PC, target)
        return target

    def _find_task_node_for_current_sp(self) -> int | None:
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        best_node: int | None = None
        best_delta: int | None = None
        for task_id in range(0x40):
            node_va = self._read_u32_va_safe(0x806C5D10 + task_id * 4) or 0
            if not (0x806C0000 <= node_va < 0x80880000):
                continue
            ctx_sp = self._read_u32_va_safe(node_va) or 0
            if not (0x806C0000 <= ctx_sp < 0x80880000):
                continue
            restored_sp = (ctx_sp + 0x7C) & 0xFFFFFFFF
            delta = abs(int(sp) - int(restored_sp))
            if delta <= 0x400 and (best_delta is None or delta < best_delta):
                best_node = node_va
                best_delta = delta
        return best_node

    def _handle_task_context_restore(self, pc: int, save_current: bool) -> bool:
        target_node = self._read_u32_va_safe(0x80473F30) or 0
        current_node = self._read_u32_va_safe(0x80473F50) or 0
        if not (0x806C0000 <= target_node < 0x80880000):
            return False

        saved_sp = None
        if save_current and 0x806C0000 <= current_node < 0x80880000:
            stack_node = self._find_task_node_for_current_sp()
            if stack_node is not None and stack_node != current_node:
                self._trace_event("task-current-node-sp-correct", pc=pc, addr=current_node, value=stack_node)
                current_node = stack_node
            # 0x800a7c18 is called with jal from the scheduler, so ra is the
            # correct resume PC for the task being switched out.
            resume_pc = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            saved_sp = self._save_task_context(current_node, resume_pc)

        ctx_sp = self._read_u32_va_safe(target_node) or 0
        target = self._restore_task_context(ctx_sp)
        if target is None:
            return False

        current_id = self._read_mem_va(0x80473F10, 1) & 0xFF
        self._write_mem_va(0x80473F09, 1, 1)
        self._write_mem_va(0x80473F11, 1, current_id)
        self._write_u32_va(0x80473F50, target_node)
        row: dict[str, object] = {
            "pc": f"0x{pc:08x}",
            "save_current": int(save_current),
            "current_node": f"0x{current_node:08x}",
            "target_node": f"0x{target_node:08x}",
            "saved_sp": None if saved_sp is None else f"0x{saved_sp:08x}",
            "target_sp": f"0x{ctx_sp:08x}",
            "target_pc": f"0x{target:08x}",
            "target_task": self._task_node_snapshot(target_node),
        }
        self.context_switch_events.append(row)
        if len(self.context_switch_events) > max(256, self.trace_limit):
            del self.context_switch_events[0]
        return True

    def task_table_snapshot(self) -> dict[str, object]:
        entries: list[dict[str, object]] = []
        for task_id in range(0x40):
            node_va = self._read_u32_va_safe(0x806C5D10 + task_id * 4)
            if node_va is None or node_va == 0:
                continue
            snap = self._task_node_snapshot(node_va)
            entries.append(
                {
                    "task_id": task_id,
                    "value": f"0x{node_va:08x}",
                    "node": snap,
                }
            )
        return {
            "table_va": "0x806c5d10",
            "entries": entries,
            "recent_events": self.task_events[-256:],
            "recent_table_writes": self.task_table_write_events[-512:],
            "recent_context_switches": self.context_switch_events[-256:],
        }

    def _trace_blit_submit(self, pc: int) -> None:
        desc = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        try:
            raw = bytes(self.uc.mem_read(va_to_phys(desc), 0x34))
        except Exception:
            return

        def u32(off: int) -> int:
            return struct.unpack_from("<I", raw, off)[0]

        def u16(off: int) -> int:
            return struct.unpack_from("<H", raw, off)[0]

        row: dict[str, str | int] = {
            "pc": f"0x{pc:08x}",
            "desc": f"0x{desc:08x}",
            "op": f"0x{u32(0x04):08x}",
            "arg": f"0x{u32(0x08):08x}",
            "mode": f"0x{u32(0x0c):08x}",
            "width": u16(0x10),
            "height": u16(0x12),
            "buffer": f"0x{u32(0x14):08x}",
            "area": f"0x{u32(0x18):08x}",
            "result": f"0x{u32(0x30):08x}",
        }
        self.blit_events.append(row)
        if len(self.blit_events) > 256:
            del self.blit_events[0]

    def _trace_call(self, address: int) -> None:
        word = self._read_word_at_va(address)
        if word is None:
            return
        opcode = (word >> 26) & 0x3F
        target = None
        kind = None
        if opcode == 3:  # jal
            target = ((address + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
            kind = "jal"
        elif opcode == 0 and (word & 0x3F) == 9:  # jalr
            rs = (word >> 21) & 0x1F
            regs = self._reg_map()
            target = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
            kind = f"jalr r{rs}"
        if target is None:
            return
        self.state.calls.append(
            {
                "pc": f"0x{address:08x}",
                "kind": kind or "",
                "target": f"0x{target:08x}",
                "ra": f"0x{self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF:08x}",
                "s0": f"0x{self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF:08x}",
                "s1": f"0x{self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF:08x}",
            }
        )
        if len(self.state.calls) > 64:
            del self.state.calls[0]

    def _trace_selected_pc(self, address: int) -> None:
        if address not in self.trace_pcs:
            return
        self.trace_pc_counts[address] = self.trace_pc_counts.get(address, 0) + 1
        row = {
            "pc": f"0x{address:08x}",
            "count": self.trace_pc_counts[address],
            "v0": f"0x{self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF:08x}",
            "v1": f"0x{self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF:08x}",
            "a0": f"0x{self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF:08x}",
            "a1": f"0x{self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF:08x}",
            "a2": f"0x{self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF:08x}",
            "a3": f"0x{self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF:08x}",
            "t0": f"0x{self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF:08x}",
            "t1": f"0x{self.uc.reg_read(UC_MIPS_REG_9) & 0xFFFFFFFF:08x}",
            "t9": f"0x{self.uc.reg_read(UC_MIPS_REG_25) & 0xFFFFFFFF:08x}",
            "s0": f"0x{self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF:08x}",
            "s1": f"0x{self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF:08x}",
            "s2": f"0x{self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF:08x}",
            "sp": f"0x{self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF:08x}",
            "ra": f"0x{self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF:08x}",
        }
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        stack_words = []
        if self._is_mapped_ram_va(sp, 0x28):
            for off in range(0, 0x28, 4):
                stack_words.append(f"0x{self._read_mem_va(sp + off, 4) & 0xFFFFFFFF:08x}")
            row["sp_words_00_24"] = stack_words
        for reg_name, reg_id in (
            ("v0", UC_MIPS_REG_2),
            ("v1", UC_MIPS_REG_3),
            ("a0", UC_MIPS_REG_4),
            ("a1", UC_MIPS_REG_5),
            ("a2", UC_MIPS_REG_6),
            ("a3", UC_MIPS_REG_7),
            ("s0", UC_MIPS_REG_16),
            ("s1", UC_MIPS_REG_17),
            ("s2", UC_MIPS_REG_18),
            ("s4", UC_MIPS_REG_20),
        ):
            text = self._read_c_string_va_safe(self.uc.reg_read(reg_id) & 0xFFFFFFFF)
            if text is not None:
                row[f"{reg_name}_str"] = text
            ptr = self.uc.reg_read(reg_id) & 0xFFFFFFFF
            if self._is_mapped_ram_va(ptr, 0x10):
                row[f"{reg_name}_words_00_0c"] = [
                    f"0x{self._read_mem_va(ptr + off, 4) & 0xFFFFFFFF:08x}" for off in range(0, 0x10, 4)
                ]
        self.trace_pc_hits.append(row)
        if len(self.trace_pc_hits) > max(128, self.trace_limit):
            del self.trace_pc_hits[0]

    def _schedule_next_tcu_irq(self) -> None:
        if self.tcu_enabled_mask & 0x3:
            self.next_tcu_irq_insn = self.state.insn_count + self.tcu_period_insn
        else:
            self.next_tcu_irq_insn = None

    def _schedule_next_irq24(self) -> None:
        self.next_irq24_insn = self.state.insn_count + self.irq24_period_insn

    def _refresh_tcu_pending(self) -> None:
        if self.next_tcu_irq_insn is None:
            return
        if self.state.insn_count < self.next_tcu_irq_insn:
            return
        newly_pending = (self.tcu_enabled_mask & 0x3) & ~self.tcu_pending_mask
        if newly_pending:
            self.tcu_pending_mask |= newly_pending
            if newly_pending & 0x1:
                self.intc_pending_mask |= 1 << 23
                self._trace_event("tcu-irq-pending", pc=self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF, value=23)
            if newly_pending & 0x2:
                self.intc_pending_mask |= 1 << 22
                self._trace_event("tcu-irq-pending", pc=self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF, value=22)
        self.next_tcu_irq_insn = self.state.insn_count + self.tcu_period_insn

    def _refresh_irq24_pending(self) -> None:
        if self.next_irq24_insn is None:
            self._schedule_next_irq24()
            return
        if self.state.insn_count < self.next_irq24_insn:
            return
        if not (self.intc_pending_mask & (1 << 24)):
            self.intc_pending_mask |= 1 << 24
            self._trace_event("periodic-irq24-pending", pc=self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF, value=24)
        self.next_irq24_insn = self.state.insn_count + self.irq24_period_insn

    def _update_tcu_period_from_register(self, value: int) -> None:
        compare = value & 0xFFFFFFFF
        if compare == 0:
            return
        self.tcu_period_insn = max(5_000, min(compare, 5_000_000))

    def _handle_interrupt_return(self, pc: int) -> bool:
        if pc not in (0x800A7DC0, 0x800A7FD8, 0x800A80E8) or self.interrupt_return_pc is None:
            return False
        target = self.interrupt_return_pc
        self.interrupt_return_pc = None
        self.interrupt_suppress_pc_once = target
        self.uc.reg_write(UC_MIPS_REG_PC, target)
        self._trace_event("external-interrupt-return", pc=pc, target=target)
        self.internal_chunk_stop = True
        self.uc.emu_stop()
        return True

    def _interrupt_delivery_inhibited_pc(self, pc: int) -> bool:
        # Avoid interrupt injection inside firmware exception/CP0 status helper
        # code. 0x800a8134 restores CP0 Status and is followed by ssnop hazard
        # padding; delivering before that helper returns can trap execution in
        # the same post-mtc0 padding instead of advancing the interrupted code.
        return (
            0x80008760 <= pc < 0x80008828
            or 0x80008828 <= pc < 0x800088C0
            or 0x80004E64 <= pc < 0x80004F08
            or 0x800A7D00 <= pc < 0x800A8100
            or 0x800A80F0 <= pc < 0x800A8150
            or 0x800040BC <= pc < 0x80004190
            or 0x800051BC <= pc < 0x800053B0
        )

    def _maybe_deliver_external_interrupt(self, pc: int) -> bool:
        if self.profile != "bbk9588-uboot":
            return False
        self._refresh_tcu_pending()
        self._refresh_irq24_pending()
        if self.interrupt_suppress_pc_once is not None and pc == self.interrupt_suppress_pc_once:
            self._trace_event("external-interrupt-suppress-once", pc=pc)
            self.interrupt_suppress_pc_once = None
            return False
        if self.interrupt_return_pc is not None and pc == self.interrupt_return_pc:
            self._trace_event("external-interrupt-return-observed", pc=pc)
            self.interrupt_return_pc = None
        if self.interrupt_return_pc is not None or self.intc_pending_mask == 0:
            return False
        # Unicorn's Python MIPS binding exposes CP0 Status but not EPC/Cause.
        # Jumping to C200's exception entry without a real EPC corrupts the
        # firmware's saved context (observed as PC/RA=0x01000000). Keep IRQ
        # sources pending and service them from modeled WAIT/poll sites until
        # the CP0 exception model can set EPC accurately.
        return False
        if self._interrupt_delivery_inhibited_pc(pc):
            return False
        status = self.uc.reg_read(UC_MIPS_REG_CP0_STATUS) & 0xFFFFFFFF
        if (status & 0x1) == 0:
            return False
        self.interrupt_return_pc = pc
        self.uc.reg_write(UC_MIPS_REG_26, pc)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x800A7DF4)
        row = {
            "pc": f"0x{pc:08x}",
            "target": "0x800a7df4",
            "pending": f"0x{self.intc_pending_mask:08x}",
            "insn": self.state.insn_count,
        }
        self.interrupt_deliveries.append(row)
        if len(self.interrupt_deliveries) > 128:
            del self.interrupt_deliveries[0]
        self._trace_event("external-interrupt-deliver", pc=pc, target=0x800A7DF4, value=self.intc_pending_mask)
        self.internal_chunk_stop = True
        return True

    def _service_pending_irq_from_wait(self, pc: int, return_pc: int) -> bool:
        pending = self.intc_pending_mask & 0xFFFFFFFF
        while pending:
            irq = pending.bit_length() - 1
            entry = 0x80474684 + irq * 8
            handler = self._read_u32_va_safe(entry)
            if handler not in (None, 0, 0x80005294):
                break
            # Some modeled periodic sources can be pending before C200 has a
            # real handler for them. Treat the firmware default IRQ stub as
            # consumed so it cannot mask lower, serviceable device IRQs.
            self.intc_pending_mask &= ~(1 << irq)
            if irq == 23:
                self.tcu_pending_mask &= ~0x1
                self._schedule_next_tcu_irq()
            elif irq == 22:
                self.tcu_pending_mask &= ~0x2
                self._schedule_next_tcu_irq()
            elif irq == 24:
                self._schedule_next_irq24()
            self._trace_event("wait-irq-skip-default", pc=pc, value=irq, target=handler or 0)
            pending = self.intc_pending_mask & 0xFFFFFFFF
        else:
            return False
        arg = self._read_u32_va_safe(entry + 4) or 0
        self.intc_pending_mask &= ~(1 << irq)
        if irq == 23:
            self.tcu_pending_mask &= ~0x1
        elif irq == 22:
            self.tcu_pending_mask &= ~0x2
        self.uc.reg_write(UC_MIPS_REG_4, arg & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_31, return_pc & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_PC, handler & 0xFFFFFFFF)
        self._trace_event("wait-irq-service", pc=pc, target=handler, value=irq, size=arg)
        return True

    def _store_delay_info(self, pc: int) -> tuple[int, int, int, int, str] | None:
        word = self._read_word_at_va(pc)
        if word is None:
            return None
        opcode = (word >> 26) & 0x3F
        if opcode not in (40, 41, 43):  # sb/sh/sw
            return None
        regs = self._reg_map()
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        imm = word & 0xFFFF
        if imm & 0x8000:
            imm -= 0x10000
        va = (self.uc.reg_read(regs[rs]) + imm) & 0xFFFFFFFF
        phys = va_to_phys(va)
        size = {40: 1, 41: 2, 43: 4}[opcode]
        value = self.uc.reg_read(regs[rt]) & ((1 << (size * 8)) - 1)
        name = {40: "sb", 41: "sh", 43: "sw"}[opcode]
        return va, phys, size, value, f"{name} r{rt},{imm}(r{rs})"

    def _mmio_store_delay_info(self, pc: int) -> tuple[int, int, int, str] | None:
        delay = self._store_delay_info(pc)
        if delay is None:
            return None
        _va, phys, size, value, text = delay
        if not (
            PHYS_MMIO_BASE <= phys < PHYS_MMIO_BASE + MMIO_SIZE
            or EXT_BANK_BASE <= phys < EXT_BANK_BASE + EXT_BANK_SIZE
        ):
            return None
        return phys, size, value, text

    def _branch_target(self, pc: int, word: int) -> tuple[int, bool, str] | None:
        opcode = (word >> 26) & 0x3F
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        regs = self._reg_map()
        if opcode in (2, 3):  # j/jal
            target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
            return target & 0xFFFFFFFF, True, "jal" if opcode == 3 else "j"
        imm = word & 0xFFFF
        if imm & 0x8000:
            imm -= 0x10000
        if opcode in (4, 5):  # beq/bne
            rs_val = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
            rt_val = self.uc.reg_read(regs[rt]) & 0xFFFFFFFF
            taken = (rs_val == rt_val) if opcode == 4 else (rs_val != rt_val)
            target = (pc + 4 + (imm << 2)) & 0xFFFFFFFF if taken else (pc + 8) & 0xFFFFFFFF
            return target, taken, "beq" if opcode == 4 else "bne"
        if opcode in (6, 7):  # blez/bgtz
            rs_raw = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
            rs_val = rs_raw - 0x100000000 if rs_raw & 0x80000000 else rs_raw
            taken = (rs_val <= 0) if opcode == 6 else (rs_val > 0)
            target = (pc + 4 + (imm << 2)) & 0xFFFFFFFF if taken else (pc + 8) & 0xFFFFFFFF
            return target, taken, "blez" if opcode == 6 else "bgtz"
        if opcode == 1 and rt in (0, 1):  # bltz/bgez
            rs_raw = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
            rs_val = rs_raw - 0x100000000 if rs_raw & 0x80000000 else rs_raw
            taken = (rs_val < 0) if rt == 0 else (rs_val >= 0)
            target = (pc + 4 + (imm << 2)) & 0xFFFFFFFF if taken else (pc + 8) & 0xFFFFFFFF
            return target, taken, "bltz" if rt == 0 else "bgez"
        if opcode == 0 and (word & 0x001FFFFF) == 0x00000008 and (word & 0x3F) == 8:
            target = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
            return target, True, "jr"
        return None

    def _handle_branch_with_mmio_delay(self, pc: int) -> bool:
        word = self._read_word_at_va(pc)
        if word is None or not self._is_recoverable_branch_word(word):
            return False
        delay = self._store_delay_info(pc + 4)
        if delay is None:
            return False
        target_info = self._branch_target(pc, word)
        if target_info is None:
            return False
        target, taken, kind = target_info
        va, phys, size, value, delay_text = delay
        is_mmio = (
            PHYS_MMIO_BASE <= phys < PHYS_MMIO_BASE + MMIO_SIZE
            or EXT_BANK_BASE <= phys < EXT_BANK_BASE + EXT_BANK_SIZE
        )
        is_ram = va >= RAM_BASE and 0 <= phys and phys + size <= self.ram_size
        if not is_mmio and not is_ram:
            return False
        if ((word >> 26) & 0x3F) == 3:  # jal
            self.uc.reg_write(UC_MIPS_REG_31, (pc + 8) & 0xFFFFFFFF)
        self.uc.mem_write(phys, value.to_bytes(size, "little"))
        if is_mmio:
            self._model_mmio(UC_MEM_WRITE, phys, size, value)
        self.uc.reg_write(UC_MIPS_REG_PC, target)
        self.mmio_delay_branch_count += 1
        if self.mmio_delay_branch_count <= 32 or self.mmio_delay_branch_count % 256 == 0:
            self._trace_event("mmio-delay-branch" if is_mmio else "ram-delay-branch", pc=pc, target=target, value=value, size=size)
        if len(self.state.recoveries) < self.trace_limit:
            self.state.recoveries.append(
                f"{'mmio' if is_mmio else 'ram'}-delay-{kind} pc=0x{pc:08x} target=0x{target:08x} taken={taken} delay={delay_text}"
            )
        return True

    def _on_mem(self, uc, access: int, address: int, size: int, value: int, user_data) -> None:
        phys_address = va_to_phys(address)
        if (
            self.profile == "bbk9588-uboot"
            and access == UC_MEM_READ
            and phys_address == 0x18000000
            and size in (1, 2, 4)
        ):
            self._model_mmio(access, phys_address, size, value)
            return
        self._trace_watch_access(access, phys_address, size, value)
        if self.profile == "bbk9588-uboot" and access == UC_MEM_WRITE and size == 4:
            if 0x006C5D10 <= phys_address < 0x006C5E10:
                self._capture_task_table_write(address, value)
        if access == UC_MEM_WRITE and (
            0xA1F80000 <= address < 0xA1FA8000 or 0x01F80000 <= address < 0x01FA8000
        ):
            pc = uc.reg_read(UC_MIPS_REG_PC)
            self.framebuffer_writes.append(
                {
                    "pc": f"0x{pc:08x}",
                    "addr": f"0x{address:08x}",
                    "size": size,
                    "value": f"0x{value & ((1 << (size * 8)) - 1):x}",
                }
            )
            if len(self.framebuffer_writes) > 512:
                del self.framebuffer_writes[0]
        if self.profile == "bbk9588-uboot" and access == UC_MEM_WRITE and 0x0095BA80 <= address < 0x0095BAB8:
            pc = uc.reg_read(UC_MIPS_REG_PC)
            self._trace_event("watch-write", pc=pc, addr=address, value=value, size=size)
        if self.profile == "bbk9588-uboot" and access == UC_MEM_WRITE and 0x011B6000 <= address < 0x011B8000:
            pc = uc.reg_read(UC_MIPS_REG_PC)
            if pc in (0x8090247C, 0x80902524):
                self._trace_event("stack-write", pc=pc, addr=address, value=value, size=size)
        device_address = self._canonical_mmio_address(address)
        if (PHYS_MMIO_BASE <= device_address < PHYS_MMIO_BASE + MMIO_SIZE) or (
            EXT_BANK_BASE <= device_address < EXT_BANK_BASE + EXT_BANK_SIZE
        ):
            self._model_mmio(access, device_address, size, value)
            kind = "write" if access == UC_MEM_WRITE else "read"
            observed_value = self._observed_mmio_value(access, device_address, size, value)
            self._trace_recent_control_mmio(kind, device_address, size, observed_value)
            if len(self.state.mmio) < self.trace_limit:
                pc = uc.reg_read(UC_MIPS_REG_PC)
                self.state.mmio.append(MmioAccess(pc=pc, kind=kind, addr=device_address, size=size, value=observed_value))

    def _observed_mmio_value(self, access: int, address: int, size: int, value: int) -> int:
        if access == UC_MEM_WRITE:
            return value
        try:
            return int.from_bytes(self.uc.mem_read(address, size), "little")
        except Exception:
            return value

    def _trace_recent_control_mmio(self, kind: str, address: int, size: int, value: int) -> None:
        if not (
            0x10001000 <= address < 0x10001100
            or 0x10010000 <= address < 0x10010400
            or SADC_BASE <= address < SADC_BASE + 0x100
            or 0x13040000 <= address < 0x13040100
        ):
            return
        pc = self.uc.reg_read(UC_MIPS_REG_PC)
        row = {
            "pc": f"0x{pc:08x}",
            "kind": kind,
            "addr": f"0x{address:08x}",
            "size": size,
            "value": f"0x{value & ((1 << (size * 8)) - 1):x}",
        }
        if 0x10001000 <= address < 0x10001100:
            target = self.recent_intc_accesses
        elif SADC_BASE <= address < SADC_BASE + 0x100:
            target = self.recent_sadc_accesses
        elif 0x13040000 <= address < 0x13040100:
            target = self.recent_udc_accesses
        else:
            target = self.recent_gpio_accesses
        target.append(row)
        if len(target) > 256:
            del target[0]

    def _model_udc_read_value(self, address: int, size: int) -> int:
        offset = address - 0x13040000
        if not self.usb_connected:
            return 0
        if offset == 0x01 and size == 1:
            return 0x10
        return 0

    def _touch_adc_raw(self, axis: int) -> int:
        if axis == 0:
            return 300 + round((239 - max(0, min(239, self.touch_x))) * 3400 / 239)
        return 300 + round((319 - max(0, min(319, self.touch_y))) * 3400 / 319)

    def _model_sadc_read_value(self, address: int, size: int) -> int:
        if address == SADC_STATUS:
            return self.sadc_status_event & 0xFF
        if address == SADC_TOUCH_DATA and size == 4:
            return self._touch_adc_raw(0) | (self._touch_adc_raw(1) << 16)
        if address == SADC_DATA:
            value = self._touch_adc_raw(self.sadc_next_axis)
            self.sadc_next_axis ^= 1
            return value
        return self.mmio_regs.get(address, 0)

    def _write_mmio_value(self, address: int, size: int, value: int) -> None:
        data = (value & ((1 << (size * 8)) - 1)).to_bytes(size, "little")
        self.uc.mem_write(address, data)
        alias = self._mmio_alias_for_phys(address)
        if alias is not None:
            self.uc.mem_write(alias, data)

    def _trace_watch_access(self, access: int, address: int, size: int, value: int) -> None:
        if not self.watch_ranges:
            return
        for watch in self.watch_ranges:
            if watch.phys <= address < watch.phys + watch.size:
                pc = self.uc.reg_read(UC_MIPS_REG_PC)
                kind = "write" if access == UC_MEM_WRITE else "read"
                read_value: int | None
                if access == UC_MEM_WRITE:
                    read_value = value
                else:
                    try:
                        read_value = int.from_bytes(self.uc.mem_read(address, size), "little")
                    except Exception:
                        read_value = None
                row: dict[str, str | int] = {
                    "name": watch.name,
                    "pc": f"0x{pc:08x}",
                    "kind": kind,
                    "addr": f"0x{address:08x}",
                    "va": f"0x{watch.va + (address - watch.phys):08x}",
                    "size": size,
                    "value": "" if read_value is None else f"0x{read_value & ((1 << (size * 8)) - 1):x}",
                }
                self.watch_accesses.append(row)
                if len(self.watch_accesses) > 512:
                    del self.watch_accesses[0]
                watch.accesses.append(row)
                if len(watch.accesses) > 512:
                    del watch.accesses[0]
                break

    def _apply_scheduled_pokes(self, pc: int) -> None:
        for poke in self.scheduled_pokes:
            if poke.applied or poke.idle_hit != self.idle_loop_hits:
                continue
            mask = (1 << (poke.size * 8)) - 1
            self.uc.mem_write(poke.phys, (poke.value & mask).to_bytes(poke.size, "little"))
            poke.applied = True
            row = {
                "pc": f"0x{pc:08x}",
                "idle_hit": poke.idle_hit,
                "va": f"0x{poke.va:08x}",
                "phys": f"0x{poke.phys:08x}",
                "size": poke.size,
                "value": f"0x{poke.value & mask:x}",
            }
            self.poke_events.append(row)
            self._trace_event("poke-va", pc=pc, addr=poke.va, value=poke.value, size=poke.size)

    def _apply_scheduled_calls(self, pc: int) -> bool:
        for call in self.scheduled_calls:
            if call.applied or call.idle_hit != self.idle_loop_hits:
                continue
            regs = [UC_MIPS_REG_4, UC_MIPS_REG_5, UC_MIPS_REG_6, UC_MIPS_REG_7]
            for reg, value in zip(regs, call.args):
                self.uc.reg_write(reg, value & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_SP, self.call_stack & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_31, call.return_pc & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_PC, call.va & 0xFFFFFFFF)
            call.applied = True
            row = {
                "pc": f"0x{pc:08x}",
                "idle_hit": call.idle_hit,
                "target": f"0x{call.va:08x}",
                "return_pc": f"0x{call.return_pc:08x}",
                "sp": f"0x{self.call_stack & 0xFFFFFFFF:08x}",
                "a0": f"0x{call.args[0] & 0xFFFFFFFF:08x}",
                "a1": f"0x{call.args[1] & 0xFFFFFFFF:08x}",
                "a2": f"0x{call.args[2] & 0xFFFFFFFF:08x}",
                "a3": f"0x{call.args[3] & 0xFFFFFFFF:08x}",
            }
            self.call_events.append(row)
            self._trace_event("call-va", pc=pc, addr=call.va, value=call.args[0], size=4)
            return True
        return False

    def _capture_scheduled_call_return(self, pc: int) -> None:
        for call in self.scheduled_calls:
            if not call.applied or call.returned or pc != call.return_pc:
                continue
            call.returned = True
            row = {
                "event": "return",
                "pc": f"0x{pc:08x}",
                "target": f"0x{call.va:08x}",
                "v0": f"0x{self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF:08x}",
                "a0": f"0x{self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF:08x}",
                "a1": f"0x{self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF:08x}",
                "a2": f"0x{self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF:08x}",
                "a3": f"0x{self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF:08x}",
                "sp": f"0x{self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF:08x}",
                "ra": f"0x{self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF:08x}",
            }
            self.call_events.append(row)
            self._trace_event("call-return", pc=pc, addr=call.va, value=self.uc.reg_read(UC_MIPS_REG_2), size=4)

    def _apply_firmware_key_sample(self, pc: int) -> bool:
        for sample in self.firmware_key_samples:
            if sample.applied or sample.idle_hit != self.idle_loop_hits:
                continue
            self.pending_forced_scan_code = sample.code & 0xFF
            self.uc.reg_write(UC_MIPS_REG_SP, self.call_stack & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_31, 0x80008A8C)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x8005CE48)
            sample.applied = True
            row = {
                "event": "sample",
                "pc": f"0x{pc:08x}",
                "idle_hit": sample.idle_hit,
                "code": sample.code,
                "target": "0x8005ce48",
                "forced_scan": "0x8001b464",
                "return_pc": "0x80008a8c",
                "sp": f"0x{self.call_stack & 0xFFFFFFFF:08x}",
            }
            self.firmware_key_events.append(row)
            self._trace_event("fw-key-sample", pc=pc, addr=0x8005CE48, value=sample.code, size=1)
            return True
        return False

    def _capture_firmware_key_sample_return(self, pc: int) -> None:
        if pc != 0x80008A8C:
            return
        for sample in self.firmware_key_samples:
            if not sample.applied or sample.returned:
                continue
            sample.returned = True
            row = {
                "event": "return",
                "pc": f"0x{pc:08x}",
                "code": sample.code,
                "v0": f"0x{self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF:08x}",
                "sp": f"0x{self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF:08x}",
                "ra": f"0x{self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF:08x}",
            }
            self.firmware_key_events.append(row)
            self._trace_event("fw-key-return", pc=pc, addr=0x8005CE48, value=self.uc.reg_read(UC_MIPS_REG_2), size=4)
            return

    def _handle_forced_key_scan(self, pc: int) -> bool:
        if self.pending_forced_scan_code is None:
            return False
        code = self.pending_forced_scan_code
        self.pending_forced_scan_code = None
        ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
        self.uc.reg_write(UC_MIPS_REG_2, code)
        self.uc.reg_write(UC_MIPS_REG_PC, ra)
        self.firmware_key_events.append(
            {
                "event": "forced-scan",
                "pc": f"0x{pc:08x}",
                "code": code,
                "return_pc": f"0x{ra:08x}",
            }
        )
        self._trace_event("fw-key-scan", pc=pc, addr=pc, value=code, size=1)
        return True

    def _apply_touch_sample(self, pc: int) -> bool:
        for sample in self.touch_samples:
            if sample.applied:
                continue
            if sample.pc_hit is None:
                if sample.idle_hit != self.idle_loop_hits:
                    continue
            elif sample.pc_hit != pc:
                continue
            self.pending_touch_sample = sample
            if sample.pc_hit is not None:
                self._write_touch_globals(sample.x, sample.y, sample.down)
                sample.applied = True
                row = {
                    "event": "sample-pending",
                    "pc": f"0x{pc:08x}",
                    "pc_hit": f"0x{sample.pc_hit:08x}",
                    "x": sample.x,
                    "y": sample.y,
                    "down": int(sample.down),
                }
                self.touch_sample_events.append(row)
                self._trace_event("touch-sample-pending", pc=pc, addr=pc, value=(sample.x & 0xFFFF) | (sample.y << 16), size=4)
                return False
            self.uc.reg_write(UC_MIPS_REG_31, 0x80008A8C)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x8005CCF4)
            sample.applied = True
            row = {
                "event": "sample",
                "pc": f"0x{pc:08x}",
                "idle_hit": sample.idle_hit,
                "pc_hit": None if sample.pc_hit is None else f"0x{sample.pc_hit:08x}",
                "x": sample.x,
                "y": sample.y,
                "down": int(sample.down),
                "target": "0x8005ccf4",
                "return_pc": "0x80008a8c",
                "sp": f"0x{self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF:08x}",
            }
            self.touch_sample_events.append(row)
            self._trace_event("touch-sample", pc=pc, addr=0x8005CCF4, value=(sample.x & 0xFFFF) | (sample.y << 16), size=4)
            return True
        return False

    def _capture_touch_sample_return(self, pc: int) -> None:
        if pc != 0x80008A8C:
            return
        for sample in self.touch_samples:
            if not sample.applied or sample.returned:
                continue
            sample.returned = True
            row = {
                "event": "return",
                "pc": f"0x{pc:08x}",
                "x": sample.x,
                "y": sample.y,
                "down": int(sample.down),
                "v0": f"0x{self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF:08x}",
                "touch_x_80370fc8": f"0x{self._read_mem_va(0x80370FC8, 4) & 0xFFFFFFFF:08x}",
                "touch_y_80370fcc": f"0x{self._read_mem_va(0x80370FCC, 4) & 0xFFFFFFFF:08x}",
                "release_state_80370fd0": f"0x{self._read_mem_va(0x80370FD0, 4) & 0xFFFFFFFF:08x}",
                "flag_8048dd00": f"0x{self._read_mem_va(0x8048DD00, 4) & 0xFFFFFFFF:08x}",
                "flag_8048dd04": f"0x{self._read_mem_va(0x8048DD04, 4) & 0xFFFFFFFF:08x}",
                "flag_8048dd08": f"0x{self._read_mem_va(0x8048DD08, 4) & 0xFFFFFFFF:08x}",
            }
            self.touch_sample_events.append(row)
            self.pending_touch_sample = None
            self._trace_event("touch-return", pc=pc, addr=0x8005CCF4, value=self.uc.reg_read(UC_MIPS_REG_2), size=4)
            return

    def _handle_forced_touch_sample(self, pc: int) -> bool:
        sample = self.pending_touch_sample
        if sample is None:
            return False
        ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
        if pc == 0x8001A6B0:
            value = 1 if sample.down else 0
            self.uc.reg_write(UC_MIPS_REG_2, value)
            self.uc.reg_write(UC_MIPS_REG_PC, ra)
            self.touch_sample_events.append(
                {
                    "event": "forced-pen-state",
                    "pc": f"0x{pc:08x}",
                    "down": int(sample.down),
                    "return_pc": f"0x{ra:08x}",
                }
            )
            self._trace_event("touch-pen-state", pc=pc, addr=pc, value=value, size=1)
            return True
        if pc == 0x8001A3A0:
            x_ptr = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            y_ptr = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
            x = max(0, min(239, sample.x))
            y = max(0, min(319, sample.y))
            self._write_mem_va(x_ptr, 2, x)
            self._write_mem_va(y_ptr, 2, y)
            self._write_mem_va(0x807F7116, 2, x)
            self._write_mem_va(0x807F7118, 2, y)
            self.uc.reg_write(UC_MIPS_REG_2, x)
            self.uc.reg_write(UC_MIPS_REG_PC, ra)
            self.touch_sample_events.append(
                {
                    "event": "forced-coords",
                    "pc": f"0x{pc:08x}",
                    "x": x,
                    "y": y,
                    "x_ptr": f"0x{x_ptr:08x}",
                    "y_ptr": f"0x{y_ptr:08x}",
                    "return_pc": f"0x{ra:08x}",
                }
            )
            self._trace_event("touch-coords", pc=pc, addr=x_ptr, value=(x & 0xFFFF) | (y << 16), size=4)
            return True
        return False

    def _apply_bda_launch(self, pc: int) -> bool:
        for launch in self.bda_launches:
            if launch.applied or launch.idle_hit != self.idle_loop_hits:
                continue
            data = launch.path.read_bytes()
            entry_off = data.find(BDA_ENTRY_SIG)
            if entry_off < 0:
                launch.applied = True
                self.bda_launch_events.append(
                    {
                        "event": "launch-error",
                        "pc": f"0x{pc:08x}",
                        "idle_hit": launch.idle_hit,
                        "path": str(launch.path),
                        "error": "native-entry-signature-not-found",
                    }
                )
                self._trace_event("bda-launch-error", pc=pc, addr=0, value=0)
                continue

            payload = data[entry_off:]
            dst_phys = va_to_phys(BDA_RUNTIME_ENTRY_VA)
            if dst_phys + len(payload) > self.ram_size:
                raise ValueError(f"BDA payload does not fit RAM: {launch.path} size=0x{len(payload):x}")

            table = self.uc.mem_read(va_to_phys(BDA_RUNTIME_TABLE_SRC), 0x20)
            self.uc.mem_write(va_to_phys(BDA_RUNTIME_TABLE_DST), bytes(table))
            self.uc.mem_write(dst_phys, payload)
            self._init_bda_display_context(pc)
            self.bda_app_active = True
            self.bda_initial_draw_pending = True
            self.bda_initial_draw_context = None
            launch.entry_offset = entry_off
            launch.loaded_size = len(payload)
            launch.applied = True

            self.uc.reg_write(UC_MIPS_REG_4, 0)
            self.uc.reg_write(UC_MIPS_REG_5, 0)
            self.uc.reg_write(UC_MIPS_REG_6, 0)
            self.uc.reg_write(UC_MIPS_REG_7, 0)
            self.uc.reg_write(UC_MIPS_REG_SP, self.call_stack & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_31, BDA_RETURN_PC)
            self.uc.reg_write(UC_MIPS_REG_PC, BDA_RUNTIME_ENTRY_VA)
            row = {
                "event": "launch",
                "pc": f"0x{pc:08x}",
                "idle_hit": launch.idle_hit,
                "path": str(launch.path),
                "entry_offset": f"0x{entry_off:x}",
                "runtime_entry": f"0x{BDA_RUNTIME_ENTRY_VA:08x}",
                "runtime_file_base": f"0x{(BDA_RUNTIME_ENTRY_VA - entry_off) & 0xFFFFFFFF:08x}",
                "loaded_size": f"0x{len(payload):x}",
                "return_pc": f"0x{BDA_RETURN_PC:08x}",
                "sp": f"0x{self.call_stack & 0xFFFFFFFF:08x}",
            }
            self.bda_launch_events.append(row)
            self._trace_event("bda-launch", pc=pc, addr=BDA_RUNTIME_ENTRY_VA, value=entry_off, size=len(payload))
            return True
        return False

    def _capture_bda_launch_return(self, pc: int) -> None:
        if pc != BDA_RETURN_PC:
            return
        for launch in self.bda_launches:
            if not launch.applied or launch.returned:
                continue
            launch.returned = True
            self.bda_launch_events.append(
                {
                    "event": "return",
                    "pc": f"0x{pc:08x}",
                    "path": str(launch.path),
                    "v0": f"0x{self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF:08x}",
                    "sp": f"0x{self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF:08x}",
                    "ra": f"0x{self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF:08x}",
                }
            )
            self._trace_event("bda-return", pc=pc, addr=BDA_RUNTIME_ENTRY_VA, value=self.uc.reg_read(UC_MIPS_REG_2), size=4)
            return

    def _apply_gui_key_events(self, pc: int) -> bool:
        for event in self.gui_key_events:
            if event.applied or event.idle_hit != self.idle_loop_hits:
                continue
            event.applied = True
            key_code = event.code & 0xFF
            table_entry_va = 0x806C5D10 + key_code * 4
            node_va = self._read_mem_va(table_entry_va, 4) & 0xFFFFFFFF
            row: dict[str, str | int] = {
                "event": "gui-key",
                "pc": f"0x{pc:08x}",
                "idle_hit": event.idle_hit,
                "code": key_code,
                "table_entry": f"0x{table_entry_va:08x}",
                "node": f"0x{node_va:08x}",
            }
            if not (0x806C0000 <= node_va < 0x80700000):
                row["error"] = "missing-key-table-node"
                self.gui_key_event_log.append(row)
                self._trace_event("gui-key-miss", pc=pc, addr=table_entry_va, value=key_code, size=1)
                continue

            slot = self._read_mem_va(node_va + 0x37, 1) & 0xFF
            mask = self._read_mem_va(node_va + 0x38, 1) & 0xFF
            group_mask = self._read_mem_va(node_va + 0x39, 1) & 0xFF
            input_byte_va = 0x80473F40 + slot
            input_group_va = 0x80473F38
            old_input = self._read_mem_va(input_byte_va, 1) & 0xFF
            new_input = old_input | mask
            self._write_mem_va(input_byte_va, 1, new_input)
            old_group = self._read_mem_va(input_group_va, 1) & 0xFF
            new_group = old_group | group_mask
            self._write_mem_va(input_group_va, 1, new_group)
            old_flags = self._read_mem_va(node_va + 0x34, 1) & 0xFF
            new_flags = old_flags | 0x08
            self._write_mem_va(node_va + 0x34, 1, new_flags)
            old_gate = self._read_mem_va(0x80473F08, 1) & 0xFF
            row.update(
                {
                    "slot": slot,
                    "mask": f"0x{mask:02x}",
                    "group_mask": f"0x{group_mask:02x}",
                    "input_va": f"0x{input_byte_va:08x}",
                    "input_old": f"0x{old_input:02x}",
                    "input_new": f"0x{new_input:02x}",
                    "group_old": f"0x{old_group:02x}",
                    "group_new": f"0x{new_group:02x}",
                    "flags_old": f"0x{old_flags:02x}",
                    "flags_new": f"0x{new_flags:02x}",
                    "gate_80473f08_old": f"0x{old_gate:02x}",
                }
            )
            if not event.pumped:
                self._write_mem_va(0x80473F08, 1, 0)
                self.uc.reg_write(UC_MIPS_REG_31, 0x80008A8C)
                self.uc.reg_write(UC_MIPS_REG_PC, 0x800080F0)
                event.pumped = True
                row.update(
                    {
                        "gate_80473f08_new": "0x00",
                        "pump_target": "0x800080f0",
                        "return_pc": "0x80008a8c",
                        "sp": f"0x{self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF:08x}",
                    }
                )
            self.gui_key_event_log.append(row)
            self._trace_event("gui-key-event", pc=pc, addr=node_va, value=key_code, size=1)
            return event.pumped
        return False

    def _apply_gui_touch_events(self, pc: int) -> bool:
        for event in self.gui_touch_events:
            if event.applied or event.idle_hit != self.idle_loop_hits:
                continue
            event.applied = True
            active = self._read_u32_va_safe(0x80474048) or 0
            if active == 0 or not self._is_mapped_ram_va(active, 0x90):
                self.gui_touch_event_log.append(
                    {
                        "event": "gui-touch",
                        "pc": f"0x{pc:08x}",
                        "error": "missing-active-object",
                        "active": f"0x{active:08x}",
                    }
                )
                continue
            left = self._read_u32_va_safe(active + 4) or 0
            top = self._read_u32_va_safe(active + 8) or 0
            local_x = max(0, min(0xFFFF, event.x - left))
            local_y = max(0, min(0xFFFF, event.y - top))
            event_type = 1 if event.down else 2
            packed = (local_x & 0xFFFF) | ((local_y & 0xFFFF) << 16)
            self.uc.reg_write(UC_MIPS_REG_4, active)
            self.uc.reg_write(UC_MIPS_REG_5, event_type)
            self.uc.reg_write(UC_MIPS_REG_6, 0)
            self.uc.reg_write(UC_MIPS_REG_7, packed)
            self.uc.reg_write(UC_MIPS_REG_29, self.call_stack)
            self.uc.reg_write(UC_MIPS_REG_31, 0x80008A8C)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x800DD380)
            event.pumped = True
            row = {
                "event": "gui-touch",
                "pc": f"0x{pc:08x}",
                "active": f"0x{active:08x}",
                "x": event.x,
                "y": event.y,
                "local_x": local_x,
                "local_y": local_y,
                "event_type": event_type,
                "packed": f"0x{packed:08x}",
                "return_pc": "0x80008a8c",
            }
            self.gui_touch_event_log.append(row)
            self._trace_event("gui-touch-event", pc=pc, addr=active, value=packed, size=event_type)
            return True
        return False

    def _apply_touch_controller_events(self, pc: int) -> bool:
        applied = False
        self.touch_controller_poll_hits += 1
        for event in self.touch_controller_events:
            if event.applied or event.idle_hit != self.touch_controller_poll_hits:
                continue
            self.set_touch_controller_state(event.x, event.y, event.down, pc=pc)
            event.applied = True
            applied = True
            row = {
                "event": "touch-controller-event",
                "pc": f"0x{pc:08x}",
                "idle_hit": event.idle_hit,
                "controller_poll_hit": self.touch_controller_poll_hits,
                "x": event.x,
                "y": event.y,
                "down": int(event.down),
            }
            self.touch_controller_event_log.append(row)
            self._trace_event(
                "touch-controller-event",
                pc=pc,
                value=(event.x & 0xFFFF) | ((event.y & 0xFFFF) << 16),
                size=int(event.down),
            )
        return applied

    def _apply_gui_ring_pump(self, pc: int) -> bool:
        if not self.gui_ring_pump:
            return False
        queue_va = 0x80825840
        buffer_va = self._read_u32_va_safe(queue_va + 0x10)
        capacity = self._read_u32_va_safe(queue_va + 0x14)
        read_idx = self._read_u32_va_safe(queue_va + 0x18)
        write_idx = self._read_u32_va_safe(queue_va + 0x1C)
        if buffer_va is None or capacity is None or read_idx is None or write_idx is None:
            return False
        if capacity <= 0 or capacity > 0x100 or read_idx == write_idx:
            return False
        read_idx %= capacity
        write_idx %= capacity
        record_size = 0x1C
        record_va = buffer_va + read_idx * record_size
        if not self._is_mapped_ram_va(record_va, record_size):
            return False
        obj = self._read_u32_va_safe(record_va) or 0
        event = self._read_u32_va_safe(record_va + 4) or 0
        if obj in (0, 0xFFFFFFFF):
            next_idx = (read_idx + 1) % capacity
            self._write_u32_va(queue_va + 0x18, next_idx)
            return False
        next_idx = (read_idx + 1) % capacity
        self._write_u32_va(queue_va + 0x18, next_idx)
        if next_idx == write_idx:
            flags = self._read_u32_va_safe(queue_va) or 0
            self._write_u32_va(queue_va, flags & ~0x40000000)
        self.uc.reg_write(UC_MIPS_REG_4, record_va)
        self.uc.reg_write(UC_MIPS_REG_5, 0)
        self.uc.reg_write(UC_MIPS_REG_6, 0)
        self.uc.reg_write(UC_MIPS_REG_7, 0)
        self.uc.reg_write(UC_MIPS_REG_29, self.call_stack)
        self.uc.reg_write(UC_MIPS_REG_31, 0x80008A8C)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x800DD4B8)
        row = {
            "event": "gui-ring-pump",
            "pc": f"0x{pc:08x}",
            "record": f"0x{record_va:08x}",
            "object": f"0x{obj:08x}",
            "gui_event": f"0x{event:08x}",
            "read_old": read_idx,
            "read_new": next_idx,
            "write": write_idx,
        }
        self.gui_ring_pump_events.append(row)
        self._trace_event("gui-ring-pump", pc=pc, addr=record_va, value=event, size=record_size)
        return True

    def _next_bda_key_event_due(self) -> ScheduledBdaKeyEvent | None:
        for event in self.bda_key_events:
            if not event.applied and event.event_hit == self.bda_event_poll_hits:
                return event
        return None

    def _next_bda_event_due(self) -> ScheduledBdaEvent | None:
        for event in self.bda_events:
            if not event.applied and event.event_hit == self.bda_event_poll_hits:
                return event
        return None

    def _next_bda_touch_event_due(self) -> ScheduledBdaTouchEvent | None:
        for event in self.bda_touch_events:
            if not event.applied and event.event_hit == self.bda_event_poll_hits:
                return event
        return None

    def _has_pending_future_bda_key_event(self) -> bool:
        return any((not event.applied) and event.event_hit > self.bda_event_poll_hits for event in self.bda_key_events)

    def _has_pending_future_bda_event(self) -> bool:
        return any((not event.applied) and event.event_hit > self.bda_event_poll_hits for event in self.bda_events)

    def _has_pending_future_bda_touch_event(self) -> bool:
        return any((not event.applied) and event.event_hit > self.bda_event_poll_hits for event in self.bda_touch_events)

    def _write_touch_globals(self, x: int, y: int, down: bool) -> None:
        x = max(0, min(239, x))
        y = max(0, min(319, y))
        self._write_touch_latch(x, y, down)
        prev_x = self._read_u32_va_safe(0x80370FC8)
        prev_y = self._read_u32_va_safe(0x80370FCC)
        self._write_u32_va(0x80370FC0, x if prev_x is None else prev_x)
        self._write_u32_va(0x80370FC4, y if prev_y is None else prev_y)
        self._write_u32_va(0x80370FC8, x)
        self._write_u32_va(0x80370FCC, y)
        self._write_u32_va(0x80370FD0, 0 if down else 1)
        self._write_u32_va(0x80370FD4, 0x7F)
        self._write_u32_va(0x8048DD00, 0 if down else 1)
        self._write_u32_va(0x8048DD04, 1 if down else 0)
        self._write_u32_va(0x8048DD08, 0)

    def _write_touch_latch(self, x: int, y: int, down: bool) -> None:
        raw_x = 300 + round((239 - max(0, min(239, x))) * 3400 / 239)
        raw_y = 300 + round((319 - max(0, min(319, y))) * 3400 / 319)
        self._write_mem_va(0x807F7110, 1, 1 if down else 0)
        self._write_mem_va(0x807F7112, 2, raw_x)
        self._write_mem_va(0x807F7114, 2, raw_y)
        self._write_mem_va(0x807F7116, 2, raw_x)
        self._write_mem_va(0x807F7118, 2, raw_y)

    def set_touch_controller_state(self, x: int, y: int, down: bool, pc: int | None = None) -> None:
        """Set the modeled touchscreen controller state.

        C200's touch path reads both the 0x807f7110 latch/coordinate globals
        and active-low GPIO pen-state inputs. The calibration path also polls
        GPIOB bit18 at 0x10010100 directly, so keep it in sync with GPIOC bit27.
        """
        x = max(0, min(239, x))
        y = max(0, min(319, y))
        self.touch_x = x
        self.touch_y = y
        self.touch_down = down
        self._write_touch_globals(x, y, down)
        if down:
            self.sadc_next_axis = 0
            self.sadc_conversion_events_remaining = 5
            self.sadc_status_event |= 0x10
        else:
            self.sadc_conversion_events_remaining = 0
            self.sadc_status_event |= 0x08
            # The calibration path waits on the low-level touch completion
            # flag set by C200's touch release ISR at 0x80017758.
            self._write_mem_va(0x80477D84, 1, 1)
            self._write_u32_va(0x80362794, 0x28)
        self._write_touch_latch(x, y, down)
        last_addr = TOUCH_PEN_GPIO_ADDR
        last_gpio = 0
        for addr, bit in TOUCH_PEN_GPIO_LEVELS:
            gpio = self.gpio_idle_levels.get(addr, GPIO_KEY_IDLE_LEVELS.get(addr, 0))
            if down:
                gpio &= ~bit
            else:
                gpio |= bit
            self.gpio_idle_levels[addr] = gpio & 0xFFFFFFFF
            self.mmio_read_levels.pop(addr, None)
            last_addr = addr
            last_gpio = gpio & 0xFFFFFFFF
        self.intc_pending_mask |= 1 << 12
        if pc is None:
            pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        self._trace_event("touch-controller-state", pc=pc, addr=last_addr, value=last_gpio, size=int(down), x=x, y=y)

    def _write_bda_synthetic_event(
        self,
        event_va: int,
        event_type: int,
        word0: int = 0,
        word2: int = 0,
        word3: int = 0,
    ) -> None:
        self._write_u32_va(event_va + 0x00, word0 & 0xFFFFFFFF)
        self._write_u32_va(event_va + 0x04, event_type & 0xFFFFFFFF)
        self._write_u32_va(event_va + 0x08, word2 & 0xFFFFFFFF)
        self._write_u32_va(event_va + 0x0C, word3 & 0xFFFFFFFF)

    def _handle_block_image_hook(self, pc: int) -> bool:
        if self.block_data is None:
            return False
        if pc == 0x80182D58:
            value = len(self.block_data) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_2, value)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self._trace_event("block-size-hook", pc=pc, value=value)
            return True
        if pc not in (0x80182A90, 0x80182BF4):
            return False

        dest_va = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        offset = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        raw_length = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        source_offset = offset * 512
        length = raw_length * 512
        ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
        ok = source_offset <= len(self.block_data) and length <= len(self.block_data) - source_offset
        copied = 0
        dest_phys = va_to_phys(dest_va)
        op = "read" if pc == 0x80182A90 else "write"
        preview = ""
        if ok and op == "read":
            data = bytes(self.block_data[source_offset : source_offset + length])
            self.uc.mem_write(dest_phys, data)
            result = 0
            copied = len(data)
            preview = data[:16].hex()
        elif ok:
            data = bytes(self.uc.mem_read(dest_phys, length))
            self.block_data[source_offset : source_offset + length] = data
            first_sector = source_offset // 512
            sector_count = (length + 511) // 512
            for index in range(sector_count):
                sector = first_sector + index
                start = sector * 512
                self.block_sector_overrides[sector] = bytes(self.block_data[start : start + 512])
            result = 0
            copied = len(data)
            preview = data[:16].hex()
        else:
            result = 0xFFFFFFFF
        row: dict[str, str | int] = {
            "pc": f"0x{pc:08x}",
            "op": op,
            "dest_va": f"0x{dest_va:08x}",
            "dest_phys": f"0x{dest_phys:08x}",
            "offset": f"0x{offset:x}",
            "source_offset": f"0x{source_offset:x}",
            "raw_length": raw_length,
            "length": length,
            "copied": copied,
            "preview": preview,
            "result": f"0x{result:08x}",
            "ra": f"0x{ra:08x}",
        }
        self.block_events.append(row)
        if len(self.block_events) > 128:
            del self.block_events[0]
        self.uc.reg_write(UC_MIPS_REG_2, result)
        self.uc.reg_write(UC_MIPS_REG_PC, ra)
        self._trace_event("block-read-hook", pc=pc, addr=dest_va, value=offset, size=length)
        return True

    def _fat16_layout_from_block_image(self) -> dict[str, int] | None:
        if self.block_data is None:
            return None
        if self.fat16_layout_cache is not None:
            return self.fat16_layout_cache

        candidates = [0x20, 0]
        candidates.extend(lba for lba in range(1, min(0x100, len(self.block_data) // 512)) if lba not in candidates)
        for volume_lba in candidates:
            offset = volume_lba * 512
            if offset + 512 > len(self.block_data):
                continue
            boot = self.block_data[offset : offset + 512]
            if boot[510:512] != b"\x55\xaa":
                continue
            bytes_per_sector = struct.unpack_from("<H", boot, 0x0B)[0]
            sectors_per_cluster = boot[0x0D]
            reserved_sectors = struct.unpack_from("<H", boot, 0x0E)[0]
            fat_count = boot[0x10]
            root_entries = struct.unpack_from("<H", boot, 0x11)[0]
            total_sectors_16 = struct.unpack_from("<H", boot, 0x13)[0]
            sectors_per_fat_16 = struct.unpack_from("<H", boot, 0x16)[0]
            total_sectors_32 = struct.unpack_from("<I", boot, 0x20)[0]
            if bytes_per_sector != 512 or sectors_per_cluster == 0 or fat_count == 0 or sectors_per_fat_16 == 0:
                continue
            total_sectors = total_sectors_16 or total_sectors_32
            root_dir_sectors = ((root_entries * 32) + (bytes_per_sector - 1)) // bytes_per_sector
            fat_lba = volume_lba + reserved_sectors
            root_lba = fat_lba + fat_count * sectors_per_fat_16
            first_data_lba = root_lba + root_dir_sectors
            if first_data_lba >= total_sectors + volume_lba:
                continue
            self.fat16_layout_cache = {
                "volume_lba": volume_lba,
                "bytes_per_sector": bytes_per_sector,
                "sectors_per_cluster": sectors_per_cluster,
                "fat_lba": fat_lba,
                "root_lba": root_lba,
                "root_dir_sectors": root_dir_sectors,
                "first_data_lba": first_data_lba,
                "total_sectors": total_sectors,
            }
            return self.fat16_layout_cache
        return None

    def _fat16_layout_from_backing(self) -> dict[str, int] | None:
        if self.block_data is not None:
            return self._fat16_layout_from_block_image()
        if self.fat16_layout_cache is not None:
            return self.fat16_layout_cache

        candidates = [0x20, 0]
        candidates.extend(lba for lba in range(1, 0x100) if lba not in candidates)
        for volume_lba in candidates:
            boot = self._read_backing_sector(volume_lba)
            if boot is None or len(boot) < 512 or boot[510:512] != b"\x55\xaa":
                continue
            bytes_per_sector = struct.unpack_from("<H", boot, 0x0B)[0]
            sectors_per_cluster = boot[0x0D]
            reserved_sectors = struct.unpack_from("<H", boot, 0x0E)[0]
            fat_count = boot[0x10]
            root_entries = struct.unpack_from("<H", boot, 0x11)[0]
            total_sectors_16 = struct.unpack_from("<H", boot, 0x13)[0]
            sectors_per_fat_16 = struct.unpack_from("<H", boot, 0x16)[0]
            total_sectors_32 = struct.unpack_from("<I", boot, 0x20)[0]
            if bytes_per_sector != 512 or sectors_per_cluster == 0 or fat_count == 0 or sectors_per_fat_16 == 0:
                continue
            total_sectors = total_sectors_16 or total_sectors_32
            root_dir_sectors = ((root_entries * 32) + (bytes_per_sector - 1)) // bytes_per_sector
            fat_lba = volume_lba + reserved_sectors
            root_lba = fat_lba + fat_count * sectors_per_fat_16
            first_data_lba = root_lba + root_dir_sectors
            if first_data_lba >= total_sectors + volume_lba:
                continue
            self.fat16_layout_cache = {
                "volume_lba": volume_lba,
                "bytes_per_sector": bytes_per_sector,
                "sectors_per_cluster": sectors_per_cluster,
                "fat_lba": fat_lba,
                "root_lba": root_lba,
                "root_dir_sectors": root_dir_sectors,
                "first_data_lba": first_data_lba,
                "total_sectors": total_sectors,
            }
            return self.fat16_layout_cache
        return None

    def _nand_fat_sector0_index(self) -> int | None:
        if self.nand_data is None:
            return None
        if self.nand_fat_sector0_cache is not None:
            return self.nand_fat_sector0_cache
        stride = self.nand_page_size + self.nand_spare_size
        if stride <= 0:
            return None
        page_count = len(self.nand_data) // stride
        for page in range(page_count):
            page_off = page * stride
            body = self.nand_data[page_off : page_off + self.nand_page_size]
            for sector_in_page in range(self.nand_page_size // 512):
                off = sector_in_page * 512
                sector = body[off : off + 512]
                if len(sector) < 512 or sector[510:512] != b"\x55\xaa":
                    continue
                if sector[54:59] != b"FAT16" and sector[82:87] != b"FAT16":
                    continue
                hidden = struct.unpack_from("<I", sector, 28)[0]
                absolute_sector = page * (self.nand_page_size // 512) + sector_in_page
                sector0 = absolute_sector - hidden
                if sector0 >= 0:
                    self.nand_fat_sector0_cache = sector0
                    return sector0
        return None

    def _read_backing_sector(self, sector: int) -> bytes | None:
        if sector < 0:
            return None
        if self.block_data is not None:
            offset = sector * 512
            if offset + 512 <= len(self.block_data):
                return bytes(self.block_data[offset : offset + 512])
            return None
        sector0 = self._nand_fat_sector0_index()
        if sector0 is None or self.nand_data is None:
            return None
        relative = sector0 + sector
        sectors_per_page = self.nand_page_size // 512
        if relative < 0 or sectors_per_page <= 0:
            return None
        page = relative // sectors_per_page
        sector_in_page = relative % sectors_per_page
        override = self.nand_page_overrides.get(page)
        if override is not None:
            page_data = override[: self.nand_page_size]
        else:
            stride = self.nand_page_size + self.nand_spare_size
            offset = page * stride
            if offset + self.nand_page_size > len(self.nand_data):
                return None
            page_data = self.nand_data[offset : offset + self.nand_page_size]
        off = sector_in_page * 512
        if off + 512 > len(page_data):
            return None
        return bytes(page_data[off : off + 512])

    def _handle_fat16_cluster_read(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8017B4E0:
            return False
        layout = self._fat16_layout_from_backing()
        if layout is None:
            return False

        cluster = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        dest_va = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        if cluster < 2 or cluster >= 0xFFF8:
            return False

        sectors_per_read = self._read_mem_va(0x80474254, 1) & 0xFF if self._is_mapped_ram_va(0x80474254, 1) else 1
        if sectors_per_read == 0 or sectors_per_read > layout["sectors_per_cluster"]:
            sectors_per_read = layout["sectors_per_cluster"]
        length = sectors_per_read * layout["bytes_per_sector"]
        if length <= 0 or length > 0x20000 or not self._is_mapped_ram_va(dest_va, length):
            return False

        table = 0x8086D200 + ((cluster & 1) * 0x20)
        for slot in range(2):
            entry = table + slot * 0x10
            entry_cluster = self._read_u32_va_safe(entry)
            if entry_cluster != cluster:
                continue
            buffer_va = self._read_u32_va_safe(entry + 4) or 0
            if not self._is_mapped_ram_va(buffer_va, length):
                return False
            data = self._read_block_va_safe(buffer_va, length)
            if data is None:
                return False
            self.uc.mem_write(va_to_phys(dest_va), data)
            hits = (self._read_u32_va_safe(entry + 8) or 0) + 1
            self._write_u32_va(entry + 8, hits & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_2, 1)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self.cluster_read_accel_count += 1
            row: dict[str, str | int] = {
                "pc": f"0x{pc:08x}",
                "cluster": f"0x{cluster:x}",
                "dest_va": f"0x{dest_va:08x}",
                "slot": slot,
                "buffer": f"0x{buffer_va:08x}",
                "length": length,
                "preview": data[:16].hex(),
                "count": self.cluster_read_accel_count,
                "mode": "cache-hit",
            }
            self.cluster_read_events.append(row)
            if len(self.cluster_read_events) > 128:
                del self.cluster_read_events[0]
            self._trace_event("fat16-cluster-read-cache-hit", pc=pc, addr=dest_va, value=cluster, size=length)
            return True

        lba = layout["first_data_lba"] + (cluster - 2) * layout["sectors_per_cluster"]
        chunks: list[bytes] = []
        for sector_index in range(sectors_per_read):
            sector_data = self._read_backing_sector(lba + sector_index)
            if sector_data is None:
                return False
            chunks.append(sector_data)
        data = b"".join(chunks)[:length]
        victim_slot: int | None = None
        victim_hits = 0xFFFFFFFF
        for slot in range(2):
            entry = table + slot * 0x10
            hits = self._read_u32_va_safe(entry + 8)
            if hits is None:
                return False
            if hits <= victim_hits:
                victim_hits = hits
                victim_slot = slot
        cache_mode = "backing-read"
        cache_buffer = 0
        if victim_slot is not None and victim_hits != 1:
            entry = table + victim_slot * 0x10
            cache_buffer = self._read_u32_va_safe(entry + 4) or 0
            if self._is_mapped_ram_va(cache_buffer, length):
                self.uc.mem_write(va_to_phys(cache_buffer), data)
                self._write_u32_va(entry, cluster)
                self._write_u32_va(entry + 8, 1)
                cache_mode = "miss-load"

        self.uc.mem_write(va_to_phys(dest_va), data)
        self.uc.reg_write(UC_MIPS_REG_2, 1)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)

        self.cluster_read_accel_count += 1
        row: dict[str, str | int] = {
            "pc": f"0x{pc:08x}",
            "cluster": f"0x{cluster:x}",
            "dest_va": f"0x{dest_va:08x}",
            "lba": f"0x{lba:x}",
            "sectors": sectors_per_read,
            "length": length,
            "preview": data[:16].hex(),
            "count": self.cluster_read_accel_count,
            "mode": cache_mode,
        }
        if victim_slot is not None:
            row["slot"] = victim_slot
        if cache_buffer:
            row["buffer"] = f"0x{cache_buffer:08x}"
        self.cluster_read_events.append(row)
        if len(self.cluster_read_events) > 128:
            del self.cluster_read_events[0]
        self._trace_event("fat16-cluster-read", pc=pc, addr=dest_va, value=cluster, size=length)
        return True

    def _handle_resource_cache16_hit(self, pc: int) -> bool:
        if not self.fast_hooks or not self.resource_cache16_accelerator or pc != 0x8017CA10:
            return False
        if not self._read_u32_va_safe(0x804BF434):
            return False
        index = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        if index < 2:
            return False
        limit = self._read_u32_va_safe(0x80474264)
        if limit is not None and index >= ((limit + 2) & 0xFFFFFFFF):
            return False
        base_sector = self._read_u32_va_safe(0x80474260)
        if base_sector is None:
            return False
        sector = ((index >> 8) + base_sector) & 0xFFFFFFFF
        low = index & 0xFF
        table = 0x8086D180
        for slot in range(8):
            entry = table + slot * 0x10
            entry_sector = self._read_u32_va_safe(entry)
            if entry_sector != sector:
                continue
            buffer_va = self._read_u32_va_safe(entry + 4) or 0
            data_va = (buffer_va + low * 2) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(data_va, 2):
                return False
            value = self._read_mem_va(data_va, 2) & 0xFFFF
            hits = (self._read_u32_va_safe(entry + 8) or 0) + 1
            self._write_u32_va(entry + 8, hits & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_2, value)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self.resource_cache16_accel_count += 1
            if self.resource_cache16_accel_count <= 32 or self.resource_cache16_accel_count % 4096 == 0:
                row = {
                    "pc": f"0x{pc:08x}",
                    "index": f"0x{index:x}",
                    "sector": f"0x{sector:x}",
                    "slot": slot,
                    "buffer": f"0x{buffer_va:08x}",
                    "value": f"0x{value:04x}",
                    "count": self.resource_cache16_accel_count,
                }
                self.resource_cache16_events.append(row)
                if len(self.resource_cache16_events) > 128:
                    del self.resource_cache16_events[0]
            return True
        backing_sector = self._read_backing_sector(sector)
        if backing_sector is None:
            return False
        victim_slot: int | None = None
        victim_hits = 0xFFFFFFFF
        for slot in range(8):
            entry = table + slot * 0x10
            hits = self._read_u32_va_safe(entry + 8)
            if hits is None:
                return False
            if hits <= victim_hits:
                victim_hits = hits
                victim_slot = slot
        if victim_slot is None:
            return False
        entry = table + victim_slot * 0x10
        buffer_va = self._read_u32_va_safe(entry + 4) or 0
        dirty = self._read_u32_va_safe(entry + 0x0C) or 0
        if dirty:
            # The firmware flushes dirty cache slots before reuse. Do not
            # shortcut that path until the writeback side is modeled.
            return False
        if not self._is_mapped_ram_va(buffer_va, 0x200):
            return False
        self.uc.mem_write(va_to_phys(buffer_va), backing_sector[:0x200])
        value = struct.unpack_from("<H", backing_sector, low * 2)[0]
        self._write_u32_va(entry, sector)
        self._write_u32_va(entry + 8, 1)
        self._write_u32_va(entry + 0x0C, 0)
        self.uc.reg_write(UC_MIPS_REG_2, value)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.resource_cache16_accel_count += 1
        if self.resource_cache16_accel_count <= 32 or self.resource_cache16_accel_count % 4096 == 0:
            row = {
                "pc": f"0x{pc:08x}",
                "index": f"0x{index:x}",
                "sector": f"0x{sector:x}",
                "slot": victim_slot,
                "buffer": f"0x{buffer_va:08x}",
                "value": f"0x{value:04x}",
                "count": self.resource_cache16_accel_count,
                "mode": "miss-load",
            }
            self.resource_cache16_events.append(row)
            if len(self.resource_cache16_events) > 128:
                del self.resource_cache16_events[0]
        return True

    def _handle_dirent_copy(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x80175E40:
            return False
        src = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        dst = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(src, 0x20) or not self._is_mapped_ram_va(dst, 0x20):
            return False
        data = self._read_block_va_safe(src, 0x20)
        if data is None:
            return False
        out = bytearray(0x20)
        out[0:8] = data[0:8]
        out[8:11] = data[8:11]
        out[0x0B] = data[0x0B]
        out[0x0C] = data[0x0C]
        out[0x0D] = data[0x0D]
        out[0x0E:0x10] = data[0x0E:0x10]
        out[0x10:0x12] = data[0x10:0x12]
        out[0x12:0x14] = data[0x12:0x14]
        high_cluster = struct.unpack_from("<H", data, 0x14)[0]
        low_cluster = struct.unpack_from("<H", data, 0x1A)[0]
        struct.pack_into("<I", out, 0x14, ((high_cluster << 16) | low_cluster) & 0xFFFFFFFF)
        out[0x18:0x1A] = data[0x16:0x18]
        out[0x1A:0x1C] = data[0x18:0x1A]
        out[0x1C:0x20] = data[0x1C:0x20]
        if out[0] == 5:
            out[0] = 0xE5
        self.uc.mem_write(va_to_phys(dst), bytes(out))
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.dirent_copy_accel_count += 1
        row = {
            "pc": f"0x{pc:08x}",
            "src": f"0x{src:08x}",
            "dst": f"0x{dst:08x}",
            "name_hex": bytes(out[:11]).hex(),
            "attr": f"0x{out[0x0B]:02x}",
            "cluster": f"0x{struct.unpack_from('<I', out, 0x14)[0]:08x}",
            "size": f"0x{struct.unpack_from('<I', out, 0x1C)[0]:08x}",
            "first_byte": f"0x{out[0]:02x}",
            "count": self.dirent_copy_accel_count,
        }
        self.dirent_copy_events.append(row)
        if len(self.dirent_copy_events) > 128:
            del self.dirent_copy_events[0]
        return True

    def _handle_logo_strip_blit(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8001DF78:
            return False
        src = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF  # s0
        dst = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF  # s1
        width = 240
        height = 28
        row_bytes = width * 2
        if not self._is_mapped_ram_va(src, row_bytes * height):
            return False
        if not self._is_mapped_ram_va((dst - row_bytes * height + 2) & 0xFFFFFFFF, row_bytes * height):
            return False
        for row in range(height):
            data = self._read_block_va_safe(src + row * row_bytes, row_bytes)
            if data is None:
                return False
            out = bytearray(row_bytes)
            for x in range(width):
                out[x * 2 : x * 2 + 2] = data[(width - 1 - x) * 2 : (width - x) * 2]
            row_start = (dst - row * row_bytes - row_bytes + 2) & 0xFFFFFFFF
            self.uc.mem_write(va_to_phys(row_start), bytes(out))
        self.uc.reg_write(UC_MIPS_REG_PC, 0x8001DF5C)
        self.logo_strip_blit_accel_count += 1
        return True

    def _handle_fullscreen_fill_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x800133EC:
            return False
        count = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        dst = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
        color = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFF
        if count == 0 or count > 240 * 320:
            return False
        if not self._is_mapped_ram_va(dst, count * 2):
            return False
        self.uc.mem_write(va_to_phys(dst), struct.pack("<H", color) * count)
        self.uc.reg_write(UC_MIPS_REG_2, (dst + count * 2) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_3, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x800133FC)
        self._trace_event("fullscreen-fill-loop", pc=pc, addr=dst, size=count, value=color)
        return True

    def _handle_boot_frame_copy_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc not in (0x800128F4, 0x800128F8):
            return False
        row = self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF
        col = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        src = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        dest_ptr = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        row_base = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        if row >= 320 or col >= 240:
            return False
        if not self._is_mapped_ram_va(src, (320 * 240 - (row * 240 + col)) * 2):
            return False
        first_loaded = pc == 0x800128F8
        while row < 320:
            while col < 240:
                if first_loaded:
                    value = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFF
                    first_loaded = False
                else:
                    value = self._read_mem_va(src, 2)
                self.uc.mem_write(va_to_phys((dest_ptr - 2) & 0xFFFFFFFF), struct.pack("<H", value))
                src = (src + 2) & 0xFFFFFFFF
                dest_ptr = (dest_ptr - 2) & 0xFFFFFFFF
                col += 1
            row += 1
            if row >= 320:
                break
            row_base = (row_base - 0x1E0) & 0xFFFFFFFF
            dest_ptr = row_base
            col = 0
        self.uc.reg_write(UC_MIPS_REG_4, dest_ptr)
        self.uc.reg_write(UC_MIPS_REG_5, 240)
        self.uc.reg_write(UC_MIPS_REG_6, src)
        self.uc.reg_write(UC_MIPS_REG_7, row_base)
        self.uc.reg_write(UC_MIPS_REG_8, 320)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x80012920)
        self._trace_event("boot-frame-copy-loop", pc=pc, addr=dest_ptr, size=240 * 320, value=src)
        return True

    def _handle_malloc_scan_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x800074A0:
            return False
        count = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        index = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        s0 = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        request = (self.uc.reg_read(UC_MIPS_REG_4) + 3) & ~3
        if count == 0 or index >= count or request > 0x200000:
            return False
        found = None
        scan = s0
        for current in range(index, count):
            size_word = self._read_u32_va_safe(scan + 4)
            if size_word is None:
                return False
            if (size_word & 1) == 0 and size_word >= request:
                found = (current, scan, size_word)
                break
            scan = (scan - 8) & 0xFFFFFFFF
        if found is None:
            self.uc.reg_write(UC_MIPS_REG_5, count)
            self.uc.reg_write(UC_MIPS_REG_16, scan)
            self.uc.reg_write(UC_MIPS_REG_6, request)
            self.uc.reg_write(UC_MIPS_REG_2, request)
            self.uc.reg_write(UC_MIPS_REG_3, 0)
            self.uc.reg_write(UC_MIPS_REG_24, count)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x800074D4)
            self._trace_event("malloc-scan-loop", pc=pc, addr=s0, value=count - index, size=request)
            return True
        current, scan, size_word = found
        self.uc.reg_write(UC_MIPS_REG_5, current)
        self.uc.reg_write(UC_MIPS_REG_16, scan)
        self.uc.reg_write(UC_MIPS_REG_6, size_word)
        self.uc.reg_write(UC_MIPS_REG_17, request)
        self.uc.reg_write(UC_MIPS_REG_2, request | 1)
        self.uc.reg_write(UC_MIPS_REG_3, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x8000755C)
        self._trace_event("malloc-scan-hit-loop", pc=pc, addr=scan, value=size_word, size=request)
        return True

    def _handle_byte_copy_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8017B45C:
            return False
        count = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        src = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        dst = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        original_dst = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        if count == 0 or count > 0x10000:
            return False
        if not self._is_mapped_ram_va(src, count) or not self._is_mapped_ram_va(dst, count):
            return False
        data = self._read_block_va_safe(src, count)
        if data is None:
            return False
        self.uc.mem_write(va_to_phys(dst), data)
        self.uc.reg_write(UC_MIPS_REG_5, (src + count) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_6, 0)
        self.uc.reg_write(UC_MIPS_REG_3, (dst + count) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_2, original_dst)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self._trace_event("byte-copy-loop", pc=pc, addr=dst, size=count, value=src)
        return True

    def _handle_portrait_blit_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8012C920:
            return False
        fb = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        row = self.uc.reg_read(UC_MIPS_REG_11) & 0xFFFFFFFF
        col = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        dest_base = self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF
        src_row_index = self.uc.reg_read(UC_MIPS_REG_10) & 0xFFFFFFFF
        src_base = self.uc.reg_read(UC_MIPS_REG_12) & 0xFFFFFFFF
        reverse = self._read_mem_va(0x804A6C64, 1) != 0
        if row >= 320 or col >= 240:
            return False
        if not self._is_mapped_ram_va(fb, 240 * 320 * 2):
            return False
        for y in range(row, 320):
            start_col = col if y == row else 0
            src = (src_base + (src_row_index << 5) + start_col * 2) & 0xFFFFFFFF
            for x in range(start_col, 240):
                value = self._read_mem_va(src + (x - start_col) * 2, 2)
                draw_x = 239 - x if reverse else x
                dest = (fb + (dest_base + draw_x) * 2) & 0xFFFFFFFF
                self.uc.mem_write(va_to_phys(dest), struct.pack("<H", value))
            dest_base = (dest_base - 240) & 0xFFFFFFFF
            src_row_index = (src_row_index + 15) & 0xFFFFFFFF
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self._trace_event("portrait-blit-loop", pc=pc, addr=fb, size=(320 - row) * 240, value=src_base)
        return True

    def _handle_cache_scan_tail(self, pc: int) -> bool:
        if not self.fast_hooks or self.block_data is None or pc != 0x8017BEF4:
            return False
        if (self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF) == 0:
            return False
        mode = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        scanned = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        limit = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        if mode != 0 or scanned >= limit or limit > 0x20000:
            return False
        self._write_u32_va(0x8047425C, 2)
        self.uc.reg_write(UC_MIPS_REG_17, limit)
        self.uc.reg_write(UC_MIPS_REG_2, self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x8017BF2C)
        self._trace_event("cache-scan-tail", pc=pc, size=limit - scanned, value=limit)
        return True

    def _handle_fat_free_scan_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x80172840:
            return False
        mode = self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF
        if mode != 0:
            return False
        current = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        limit = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        free_count = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        last_value = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
        if current > limit or limit - current > 0x200000:
            return False
        base_sector = self._read_u32_va_safe(0x80474260)
        if base_sector is None:
            return False
        if (last_value & 0xFFFF) == 0:
            free_count = (free_count + 1) & 0xFFFFFFFF
        if current == limit:
            remaining_free = 0
        else:
            start_byte = current * 2
            end_byte = limit * 2
            if start_byte > end_byte:
                return False
            remaining = bytearray()
            sector = base_sector + (start_byte // 512)
            offset = start_byte % 512
            while len(remaining) < (end_byte - start_byte):
                sector_data = self._read_backing_sector(sector)
                if sector_data is None:
                    return False
                chunk = sector_data[offset:]
                need = (end_byte - start_byte) - len(remaining)
                remaining += chunk[:need]
                sector += 1
                offset = 0
            table = bytes(remaining)
            remaining_free = sum(
                1 for index in range(0, len(table), 2) if table[index] == 0 and table[index + 1] == 0
            )
        if current > limit or limit - current > 0x200000:
            return False
        free_count = (free_count + remaining_free) & 0xFFFFFFFF
        self.uc.reg_write(UC_MIPS_REG_16, limit)
        self.uc.reg_write(UC_MIPS_REG_17, free_count)
        self.uc.reg_write(UC_MIPS_REG_4, 0)
        self.uc.reg_write(UC_MIPS_REG_3, free_count)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x801727E0)
        self._trace_event("fat-free-scan-loop", pc=pc, addr=current, value=limit, size=free_count)
        return True

    def _handle_free_scan_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x80006658:
            return False
        target = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        count = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        index = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        scan = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        if target == 0 or count == 0 or index >= count or count > 0x10000:
            return False

        start_index = index
        found_index: int | None = None
        found_scan = scan
        while index < count:
            value = self._read_u32_va_safe(scan)
            if value is None:
                return False
            if value == target:
                found_index = index
                found_scan = scan
                break
            index += 1
            scan = (scan - 8) & 0xFFFFFFFF

        if found_index is None:
            self.uc.reg_write(UC_MIPS_REG_17, count)
            self.uc.reg_write(UC_MIPS_REG_16, scan)
            self.uc.reg_write(UC_MIPS_REG_5, count)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80006678)
            self._trace_event("free-scan-loop", pc=pc, addr=target, value=count - start_index, size=count)
        else:
            self.uc.reg_write(UC_MIPS_REG_17, found_index)
            self.uc.reg_write(UC_MIPS_REG_16, found_scan)
            self.uc.reg_write(UC_MIPS_REG_5, count)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80006690)
            self._trace_event(
                "free-scan-hit-loop",
                pc=pc,
                addr=target,
                value=found_index - start_index,
                size=count,
            )
        self.free_scan_accel_count += 1
        return True

    def _handle_halfword_copy_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc not in (0x8012B034, 0x8012B064):
            return False
        count = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF  # a3
        if count == 0 or count > 0x20000:
            return False
        dst = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF  # a0
        src = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF  # v1
        size = count * 2
        if not self._is_mapped_ram_va(src, size):
            return False
        if pc == 0x8012B064:
            if not self._is_mapped_ram_va(dst, size):
                return False
            data = self._read_block_va_safe(src, size)
            if len(data) != size:
                return False
            self.uc.mem_write(va_to_phys(dst), data)
            final_dst = (dst + size) & 0xFFFFFFFF
        else:
            low_dst = (dst - (count - 1) * 2) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(low_dst, size):
                return False
            data = self._read_block_va_safe(src, size)
            if len(data) != size:
                return False
            out = bytearray(size)
            for i in range(count):
                out[(count - 1 - i) * 2 : (count - i) * 2] = data[i * 2 : i * 2 + 2]
            self.uc.mem_write(va_to_phys(low_dst), bytes(out))
            final_dst = (dst - size) & 0xFFFFFFFF
        last = struct.unpack_from("<H", data, size - 2)[0]
        self.uc.reg_write(UC_MIPS_REG_2, last)
        self.uc.reg_write(UC_MIPS_REG_3, (src + size) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_4, final_dst)
        self.uc.reg_write(UC_MIPS_REG_7, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.halfword_copy_accel_count += 1
        if self.halfword_copy_accel_count <= 32 or self.halfword_copy_accel_count % 4096 == 0:
            self._trace_event("halfword-copy-loop", pc=pc, addr=dst, value=src, size=size)
        return True

    def _handle_raster_copy_loop(self, pc: int) -> bool:
        if not self.fast_hooks or not self.raster_copy_accelerator or pc != 0x800AC388:
            return False
        count = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        fixed = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        step = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        src_base = self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF
        dest = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        if count == 0 or count > 4096 or not self._is_mapped_ram_va(dest, count * 2):
            return False

        out = bytearray()
        last_src = src_base
        last_value = 0
        current = fixed
        for _ in range(count):
            signed_index = struct.unpack("<i", struct.pack("<I", current & 0xFFFFFFFF))[0] >> 16
            src = (src_base + signed_index * 2) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(src, 2):
                return False
            last_src = src
            last_value = self._read_mem_va(src, 2) & 0xFFFF
            out.extend(struct.pack("<H", last_value))
            current = (current + step) & 0xFFFFFFFF
        self.uc.mem_write(va_to_phys(dest), bytes(out))
        self.uc.reg_write(UC_MIPS_REG_2, last_src)
        self.uc.reg_write(UC_MIPS_REG_3, last_value)
        self.uc.reg_write(UC_MIPS_REG_4, 0)
        self.uc.reg_write(UC_MIPS_REG_6, (dest + count * 2) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_7, current)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x800AC3AC)
        self.raster_loop_accel_count += 1
        if self.raster_loop_accel_count <= 32 or self.raster_loop_accel_count % 4096 == 0:
            self._trace_event("raster-copy-loop", pc=pc, addr=dest, value=src_base, size=count)
        return True

    def _handle_glyph_mask_loop(self, pc: int) -> bool:
        if not self.fast_hooks or not self.glyph_mask_accelerator or pc != 0x8011B428:
            return False
        bit_index = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        limit = self.uc.reg_read(UC_MIPS_REG_13) & 0xFFFFFFFF
        glyph_ptr = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        dest = self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF
        color = self.uc.reg_read(UC_MIPS_REG_14) & 0xFFFF
        draw_pair = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        if limit <= bit_index or limit - bit_index > 4096:
            return False
        count = limit - bit_index
        if not self._is_mapped_ram_va(dest, count * 2 + 2):
            return False
        byte_count = ((limit + 7) >> 3) - (bit_index >> 3)
        if byte_count <= 0 or byte_count > 1024 or not self._is_mapped_ram_va(glyph_ptr, byte_count):
            return False

        current_byte = self.uc.reg_read(UC_MIPS_REG_12) & 0xFF
        ptr = glyph_ptr
        out_dest = dest
        written = 0
        for index in range(bit_index, limit):
            if (index & 7) == 0:
                current_byte = self._read_mem_va(ptr, 1) & 0xFF
                ptr = (ptr + 1) & 0xFFFFFFFF
            mask = 0x80 >> (index & 7)
            if current_byte & mask:
                packed = struct.pack("<H", color)
                self.uc.mem_write(va_to_phys(out_dest), packed)
                written += 1
                if draw_pair:
                    self.uc.mem_write(va_to_phys((out_dest + 2) & 0xFFFFFFFF), packed)
                    written += 1
            out_dest = (out_dest + 2) & 0xFFFFFFFF

        self.uc.reg_write(UC_MIPS_REG_2, current_byte)
        self.uc.reg_write(UC_MIPS_REG_4, 0)
        self.uc.reg_write(UC_MIPS_REG_6, ptr)
        self.uc.reg_write(UC_MIPS_REG_7, limit)
        self.uc.reg_write(UC_MIPS_REG_8, out_dest)
        self.uc.reg_write(UC_MIPS_REG_12, current_byte)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x8011B47C)
        self.glyph_mask_loop_accel_count += 1
        if self.glyph_mask_loop_accel_count <= 32 or self.glyph_mask_loop_accel_count % 4096 == 0:
            self._trace_event("glyph-mask-loop", pc=pc, addr=dest, value=glyph_ptr, size=count, color=color, written=written)
        return True

    def _mirror_lcd_pixel_if_enabled(self, x: int, y: int, color: int) -> None:
        if (self._read_u32_va_safe(0x80474040) or 0) == 0:
            return
        width = self._read_mem_va(0x804A6B88, 2) & 0xFFFF
        height = self._read_mem_va(0x804A6B8C, 2) & 0xFFFF
        fb = self._read_u32_va_safe(0x804A6C60) or 0
        if width == 0 or height == 0 or fb == 0:
            return
        mx = int(x)
        my = height - int(y) - 1
        if self._read_mem_va(0x804A6C64, 1) & 0xFF:
            mx = width - mx - 1
        if mx < 0 or my < 0 or mx >= width or my >= height:
            return
        dest = (fb + ((my * width + mx) << 1)) & 0xFFFFFFFF
        if self._is_mapped_ram_va(dest, 2):
            self.uc.mem_write(va_to_phys(dest), struct.pack("<H", color & 0xFFFF))

    def _record_surface_event(
        self,
        mode: str,
        pc: int,
        *,
        surface: int,
        buffer: int,
        x: int,
        y: int,
        width: int,
        height: int,
        pitch: int,
        color: int | None = None,
        addr: int | None = None,
    ) -> None:
        self.surface_event_count += 1
        row: dict[str, str | int] = {
            "pc": f"0x{pc:08x}",
            "mode": mode,
            "surface": f"0x{surface:08x}",
            "buffer": f"0x{buffer:08x}",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "pitch": pitch,
            "mirror_enabled": int((self._read_u32_va_safe(0x80474040) or 0) != 0),
            "count": self.surface_event_count,
        }
        if color is not None:
            row["color"] = f"0x{color & 0xFFFF:04x}"
        if addr is not None:
            row["addr"] = f"0x{addr:08x}"
        self.surface_events.append(row)
        if len(self.surface_events) > 256:
            del self.surface_events[0]
        mode_events = self.surface_events_by_mode.setdefault(mode, [])
        mode_events.append(row)
        if len(mode_events) > 64:
            del mode_events[0]

    def _handle_surface_setpixel(self, pc: int) -> bool:
        if not self.fast_hooks or not self.surface_pixel_accelerator or pc != 0x8012BDF4:
            return False
        surface = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        x = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        y = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        color = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFF
        if x & 0x80000000 or y & 0x80000000:
            return False
        if not self._is_mapped_ram_va(surface, 0x48):
            return False
        pitch = self._read_u32_va_safe(surface + 0x18) or 0
        buffer_va = self._read_u32_va_safe(surface + 0x44) or 0
        dest = (buffer_va + y * pitch + x * 2) & 0xFFFFFFFF
        if pitch == 0 or buffer_va == 0 or not self._is_mapped_ram_va(dest, 2):
            return False
        self._mirror_lcd_pixel_if_enabled(x, y, color)
        self.uc.mem_write(va_to_phys(dest), struct.pack("<H", color))
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.surface_setpixel_accel_count += 1
        self._record_surface_event(
            "setpixel",
            pc,
            surface=surface,
            buffer=buffer_va,
            x=x,
            y=y,
            width=1,
            height=1,
            pitch=pitch,
            color=color,
            addr=dest,
        )
        return True

    def _handle_surface_hline(self, pc: int) -> bool:
        if not self.fast_hooks or not self.surface_hline_accelerator or pc != 0x8012BEA4:
            return False
        surface = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        x0 = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        y = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        width = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        if width == 0 or width > 4096:
            return False
        if x0 & 0x80000000 or y & 0x80000000:
            return False
        if not self._is_mapped_ram_va(surface, 0x48) or not self._is_mapped_ram_va(sp + 0x38, 2):
            return False
        pitch = self._read_u32_va_safe(surface + 0x18) or 0
        buffer_va = self._read_u32_va_safe(surface + 0x44) or 0
        color = self._read_mem_va(sp + 0x38, 2) & 0xFFFF
        dest = (buffer_va + y * pitch + x0 * 2) & 0xFFFFFFFF
        byte_count = width * 2
        if pitch == 0 or buffer_va == 0 or not self._is_mapped_ram_va(dest, byte_count):
            return False
        for offset in range(width):
            self._mirror_lcd_pixel_if_enabled(x0 + offset, y, color)
        self.uc.mem_write(va_to_phys(dest), struct.pack("<H", color) * width)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.surface_hline_accel_count += 1
        self._record_surface_event(
            "hline",
            pc,
            surface=surface,
            buffer=buffer_va,
            x=x0,
            y=y,
            width=width,
            height=1,
            pitch=pitch,
            color=color,
            addr=dest,
        )
        return True

    def _handle_surface_color_span_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8012BF64:
            return False
        surface = self.uc.reg_read(UC_MIPS_REG_21) & 0xFFFFFFFF  # s5
        x_base = self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF  # s3
        y = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF  # s2
        index = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF  # s1
        width = self.uc.reg_read(UC_MIPS_REG_20) & 0xFFFFFFFF  # s4
        src_va = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF  # s0
        if index >= width:
            return False
        count = width - index
        if count > 0x400 or not self._is_mapped_ram_va(surface, 0x48):
            return False
        pitch = self._read_u32_va_safe(surface + 0x18) or 0
        buffer_va = self._read_u32_va_safe(surface + 0x44) or 0
        x = (x_base + index) & 0xFFFFFFFF
        if pitch == 0 or buffer_va == 0 or x > 0xFFFF or y > 0xFFFF:
            return False
        src_size = count * 2
        dest = (buffer_va + y * pitch + x * 2) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(src_va, src_size) or not self._is_mapped_ram_va(dest, src_size):
            return False
        colors = self._read_block_va_safe(src_va, src_size)
        if len(colors) != src_size:
            return False
        self.uc.mem_write(va_to_phys(dest), colors)
        if (self._read_u32_va_safe(0x80474040) or 0) != 0:
            for i in range(count):
                color = struct.unpack_from("<H", colors, i * 2)[0]
                self._mirror_lcd_pixel_if_enabled(x + i, y, color)

        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(sp + 0x10, 0x1C):
            return False
        restore_slots = (
            (UC_MIPS_REG_16, 0x10),
            (UC_MIPS_REG_17, 0x14),
            (UC_MIPS_REG_18, 0x18),
            (UC_MIPS_REG_19, 0x1C),
            (UC_MIPS_REG_20, 0x20),
            (UC_MIPS_REG_21, 0x24),
        )
        for reg, off in restore_slots:
            value = self._read_u32_va_safe(sp + off)
            if value is None:
                return False
            self.uc.reg_write(reg, value)
        ra = self._read_u32_va_safe(sp + 0x28)
        if ra is None or not (0x80000000 <= ra <= 0x81FFFFFF):
            return False
        self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x30) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_31, ra)
        self.uc.reg_write(UC_MIPS_REG_PC, ra)
        self.surface_color_span_accel_count += 1
        self._record_surface_event(
            "color-span",
            pc,
            surface=surface,
            buffer=buffer_va,
            x=x,
            y=y,
            width=count,
            height=1,
            pitch=pitch,
            addr=dest,
        )
        return True

    def _surface_block_args(self, pc: int) -> tuple[int, int, int, int, int, int, int] | None:
        surface = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        x = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        y = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        width = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        height = self._read_u32_va_safe(sp + 0x10)
        buffer_va = self._read_u32_va_safe(sp + 0x14)
        stride = self._read_u32_va_safe(sp + 0x18)
        if height is None or buffer_va is None or stride is None:
            return None
        if width == 0 or height == 0 or width > 4096 or height > 4096 or stride > 0x20000:
            return None
        if x & 0x80000000 or y & 0x80000000:
            return None
        if not self._is_mapped_ram_va(surface, 0x48):
            return None
        pitch = self._read_u32_va_safe(surface + 0x18) or 0
        surface_buffer = self._read_u32_va_safe(surface + 0x44) or 0
        if pitch == 0 or surface_buffer == 0:
            return None
        if width * 2 > pitch:
            return None
        if not self._is_mapped_ram_va(buffer_va, (height - 1) * stride + width * 2):
            return None
        source_end = surface_buffer + (y + height - 1) * pitch + (x + width) * 2
        if not self._is_mapped_ram_va(surface_buffer + y * pitch + x * 2, width * 2):
            return None
        if not self._is_mapped_ram_va(source_end - width * 2, width * 2):
            return None
        return surface, x, y, width, height, buffer_va, stride

    def _handle_surface_block_read(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8012C3D0:
            return False
        args = self._surface_block_args(pc)
        if args is None:
            return False
        surface, x, y, width, height, buffer_va, stride = args
        pitch = self._read_u32_va_safe(surface + 0x18) or 0
        surface_buffer = self._read_u32_va_safe(surface + 0x44) or 0
        row_bytes = width * 2
        for row in range(height):
            src = surface_buffer + (y + row) * pitch + x * 2
            dst = buffer_va + row * stride
            data = self._read_block_va_safe(src, row_bytes)
            if data is None:
                return False
            self.uc.mem_write(va_to_phys(dst), data)
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.surface_block_read_accel_count += 1
        self._record_surface_event(
            "block-read",
            pc,
            surface=surface,
            buffer=surface_buffer,
            x=x,
            y=y,
            width=width,
            height=height,
            pitch=pitch,
            addr=buffer_va,
        )
        if self.surface_block_read_accel_count <= 32 or self.surface_block_read_accel_count % 4096 == 0:
            self._trace_event("surface-block-read", pc=pc, addr=buffer_va, value=(x & 0xFFFF) | ((y & 0xFFFF) << 16), size=width * height)
        return True

    def _handle_surface_block_write(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8012C1BC:
            return False
        args = self._surface_block_args(pc)
        if args is None:
            return False
        surface, x, y, width, height, buffer_va, stride = args
        pitch = self._read_u32_va_safe(surface + 0x18) or 0
        surface_buffer = self._read_u32_va_safe(surface + 0x44) or 0
        row_bytes = width * 2
        for row in range(height):
            src = buffer_va + row * stride
            dst = surface_buffer + (y + row) * pitch + x * 2
            data = self._read_block_va_safe(src, row_bytes)
            if data is None:
                return False
            self.uc.mem_write(va_to_phys(dst), data)
            for col in range(width):
                color = struct.unpack_from("<H", data, col * 2)[0]
                self._mirror_lcd_pixel_if_enabled(x + col, y + row, color)
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.surface_block_write_accel_count += 1
        self._record_surface_event(
            "block-write",
            pc,
            surface=surface,
            buffer=surface_buffer,
            x=x,
            y=y,
            width=width,
            height=height,
            pitch=pitch,
            addr=buffer_va,
        )
        if self.surface_block_write_accel_count <= 32 or self.surface_block_write_accel_count % 4096 == 0:
            self._trace_event("surface-block-write", pc=pc, addr=buffer_va, value=(x & 0xFFFF) | ((y & 0xFFFF) << 16), size=width * height)
        return True

    def _activate_mmio_pulses(self, pc: int) -> None:
        for pulse in self.mmio_pulses:
            if pulse.active or pulse.expired or pulse.idle_hit != self.idle_loop_hits:
                continue
            pulse.active = True
            row = {
                "pc": f"0x{pc:08x}",
                "addr": f"0x{pulse.addr:08x}",
                "value": f"0x{pulse.value:08x}",
                "idle_hit": pulse.idle_hit,
                "read_count": pulse.read_count,
                "event": "activate",
            }
            self.mmio_pulse_events.append(row)
            self._trace_event("gpio-pulse", pc=pc, addr=pulse.addr, value=pulse.value, size=4)

    def _consume_mmio_pulse(self, address: int, size: int) -> int | None:
        if size != 4:
            return None
        for pulse in self.mmio_pulses:
            if not pulse.active or pulse.expired or pulse.addr != address:
                continue
            pulse.reads_seen += 1
            if pulse.reads_seen >= pulse.read_count:
                pulse.active = False
                pulse.expired = True
                self.mmio_pulse_events.append(
                    {
                        "addr": f"0x{pulse.addr:08x}",
                        "value": f"0x{pulse.value:08x}",
                        "idle_hit": pulse.idle_hit,
                        "reads_seen": pulse.reads_seen,
                        "event": "expire",
                    }
                )
            return pulse.value
        return None

    def _prepare_nand_page_read(self) -> None:
        if len(self.nand_addr_bytes) < 5:
            self.nand_read_buffer = b"\xFF" * 4096
            self.nand_read_index = 0
            self.nand_current_page = 0
            self.nand_current_column = 0
            self.nand_current_offset = 0
            return
        column = self.nand_addr_bytes[0] | (self.nand_addr_bytes[1] << 8)
        page = self.nand_addr_bytes[2] | (self.nand_addr_bytes[3] << 8) | (self.nand_addr_bytes[4] << 16)
        pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        if (
            self.profile == "bbk9588-uboot"
            and pc == 0x809066C0
            and column == 0
            and self.nand_last_oob_page is not None
            and page != self.nand_last_oob_page
        ):
            self._trace_event("nand-data-page-correct", pc=pc, value=page, target=self.nand_last_oob_page)
            page = self.nand_last_oob_page
        if column >= self.nand_page_size and pc in (0x8090674C,):
            self.nand_last_oob_page = page
        stride = self.nand_page_size + self.nand_spare_size
        offset = page * stride + column
        self.nand_current_page = page
        self.nand_current_column = column
        self.nand_current_offset = offset
        override = self.nand_page_overrides.get(page)
        if override is not None:
            data = override[column : column + 4096]
            if len(data) < 4096:
                data += self._default_nand_read_data(column + len(data), 4096 - len(data))
            source = "overlay"
        elif self.nand_data is None or offset >= len(self.nand_data):
            data = self._default_nand_read_data(column, 4096)
            source = "erased"
        else:
            data = self.nand_data[offset : offset + 4096]
            if len(data) < 4096:
                data += self._default_nand_read_data(column + len(data), 4096 - len(data))
            data = bytes(data)
            source = "image"
        self.nand_read_buffer = bytes(data)
        self.nand_read_index = 0
        row = {
            "page": f"0x{page:x}",
            "column": f"0x{column:x}",
            "offset": f"0x{offset:x}",
            "source": source,
        }
        self.nand_reads.append(row)
        if len(self.nand_reads) > 128:
            del self.nand_reads[0]

    def _default_nand_read_data(self, column: int, size: int) -> bytes:
        return b"\xFF" * size

    def _begin_nand_program(self) -> None:
        self.nand_program_buffer.clear()
        self.nand_program_page = 0
        self.nand_program_column = 0

    def _update_nand_program_address(self) -> None:
        if len(self.nand_addr_bytes) < 5:
            return
        self.nand_program_column = self.nand_addr_bytes[0] | (self.nand_addr_bytes[1] << 8)
        self.nand_program_page = (
            self.nand_addr_bytes[2] | (self.nand_addr_bytes[3] << 8) | (self.nand_addr_bytes[4] << 16)
        )

    def _append_nand_program_data(self, value: int, size: int) -> None:
        self.nand_program_buffer.extend((value & ((1 << (size * 8)) - 1)).to_bytes(size, "little"))

    def _append_nand_program_bytes(self, data: bytes) -> None:
        self.nand_program_buffer.extend(data)

    def _is_readonly_nand_page(self, page: int) -> bool:
        return any(start <= page < end for start, end in self.readonly_nand_page_ranges)

    def _nand_row_from_addr_bytes(self) -> int:
        row = 0
        for shift, byte in enumerate(self.nand_addr_bytes[:3]):
            row |= (byte & 0xFF) << (shift * 8)
        return row & 0xFFFFFFFF

    def _commit_nand_erase(self) -> None:
        if len(self.nand_addr_bytes) < 2:
            return
        pages_per_block = 64
        stride = self.nand_page_size + self.nand_spare_size
        row = self._nand_row_from_addr_bytes()
        block_start = row & ~(pages_per_block - 1)
        erased_pages = 0
        readonly_pages = 0
        page_data = b"\xFF" * stride
        for page in range(block_start, block_start + pages_per_block):
            if self._is_readonly_nand_page(page):
                readonly_pages += 1
                continue
            if self.nand_data is not None:
                offset = page * stride
                end_offset = offset + stride
                if end_offset > len(self.nand_data):
                    self.nand_data.extend(b"\xFF" * (end_offset - len(self.nand_data)))
                self.nand_data[offset:end_offset] = page_data
            self.nand_page_overrides[page] = page_data
            erased_pages += 1
        self.nand_erase_count += 1
        row_info = {
            "row": f"0x{row:x}",
            "block_start": f"0x{block_start:x}",
            "pages": erased_pages,
            "readonly_pages": readonly_pages,
        }
        self.nand_erase_events.append(row_info)
        if len(self.nand_erase_events) > 128:
            del self.nand_erase_events[0]
        self._trace_event(
            "nand-erase",
            pc=self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF,
            addr=block_start,
            size=erased_pages,
            value=readonly_pages,
        )

    def clear_nand_page_overrides(self, ranges: list[tuple[int, int]]) -> int:
        if not ranges:
            return 0
        before = len(self.nand_page_overrides)
        self.nand_page_overrides = {
            page: data
            for page, data in self.nand_page_overrides.items()
            if not any(start <= page < end for start, end in ranges)
        }
        removed = before - len(self.nand_page_overrides)
        if removed:
            self._trace_event("nand-overrides-clear", pc=self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF, size=removed)
        return removed

    def _commit_nand_program(self) -> None:
        if not self.nand_program_buffer or len(self.nand_addr_bytes) < 5:
            return
        self._update_nand_program_address()
        stride = self.nand_page_size + self.nand_spare_size
        page = self.nand_program_page
        column = self.nand_program_column
        readonly_page = self._is_readonly_nand_page(page)
        if readonly_page:
            row = {
                "page": f"0x{page:x}",
                "column": f"0x{column:x}",
                "size": len(self.nand_program_buffer),
                "first": bytes(self.nand_program_buffer[:16]).hex(),
                "ignored": "readonly",
            }
            self.nand_program_writes.append(row)
            if len(self.nand_program_writes) > 128:
                del self.nand_program_writes[0]
            self._trace_event(
                "nand-program-readonly-ignore",
                pc=self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF,
                addr=page,
                size=len(self.nand_program_buffer),
                value=column,
            )
            self.nand_program_buffer.clear()
            return
        page_data = bytearray(self.nand_page_overrides.get(page, b""))
        if not page_data:
            offset = page * stride
            if self.nand_data is not None and offset < len(self.nand_data):
                page_data = bytearray(self.nand_data[offset : offset + stride])
            if len(page_data) < stride:
                page_data.extend(b"\xFF" * (stride - len(page_data)))
        end = min(stride, column + len(self.nand_program_buffer))
        if column < stride:
            # NAND page program can only clear bits (1 -> 0). Bits return to 1
            # only after a block erase command, so merge programmed bytes with
            # the existing page contents instead of replacing them.
            programmed = self.nand_program_buffer[: end - column]
            for i, byte in enumerate(programmed, start=column):
                page_data[i] &= byte
        if self.nand_data is not None and not readonly_page:
            offset = page * stride
            end_offset = offset + stride
            if end_offset > len(self.nand_data):
                self.nand_data.extend(b"\xFF" * (end_offset - len(self.nand_data)))
            self.nand_data[offset:end_offset] = page_data
        self.nand_page_overrides[page] = bytes(page_data)
        row = {
            "page": f"0x{page:x}",
            "column": f"0x{column:x}",
            "size": len(self.nand_program_buffer),
            "first": bytes(self.nand_program_buffer[:16]).hex(),
        }
        self.nand_program_writes.append(row)
        if len(self.nand_program_writes) > 128:
            del self.nand_program_writes[0]
        self._trace_event(
            "nand-program",
            pc=self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF,
            addr=page,
            size=len(self.nand_program_buffer),
            value=column,
        )
        self.nand_program_buffer.clear()

    def _read_nand_data_window(self, size: int) -> bytes:
        start = self.nand_read_index
        end = self.nand_read_index + size
        data = self.nand_read_buffer[self.nand_read_index:end]
        self.nand_read_index = end
        if len(data) < size:
            data += b"\xFF" * (size - len(data))
        self.nand_data_window_read_count += 1
        sample = start < 16 or start >= self.nand_page_size - 16 or self.nand_data_window_read_count <= 16
        if sample:
            pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
            self.nand_data_window_reads.append(
                {
                    "pc": f"0x{pc:08x}",
                    "page": f"0x{self.nand_current_page:x}",
                    "column": f"0x{self.nand_current_column:x}",
                    "offset": f"0x{self.nand_current_offset:x}",
                    "read_index": f"0x{start:x}",
                    "size": size,
                    "data": data[: min(size, 4)].hex(),
                }
            )
            if len(self.nand_data_window_reads) > 256:
                del self.nand_data_window_reads[0]
        return data + b"\xFF" * (4 - size)

    def _read_nand_data_bytes(self, size: int) -> bytes:
        start = self.nand_read_index
        end = self.nand_read_index + size
        data = self.nand_read_buffer[start:end]
        self.nand_read_index = end
        if len(data) < size:
            data += b"\xFF" * (size - len(data))
        self.nand_data_window_read_count += size
        pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        self.nand_data_window_reads.append(
            {
                "pc": f"0x{pc:08x}",
                "page": f"0x{self.nand_current_page:x}",
                "column": f"0x{self.nand_current_column:x}",
                "offset": f"0x{self.nand_current_offset:x}",
                "read_index": f"0x{start:x}",
                "size": size,
                "data": data[: min(size, 16)].hex(),
                "accelerated": 1,
            }
        )
        if len(self.nand_data_window_reads) > 256:
            del self.nand_data_window_reads[0]
        return data

    def _handle_nand_data_loop_accelerator(self, pc: int) -> bool:
        if not self.nand_loop_accelerator:
            return False
        if pc in (0x80183E0C, 0x80183E10):
            count = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
            dst = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
            counter_reg = UC_MIPS_REG_3
            dst_reg = UC_MIPS_REG_16
            target = 0x80183E24
        elif pc in (0x801843D8, 0x801843DC):
            count = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
            dst = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
            counter_reg = UC_MIPS_REG_3
            dst_reg = UC_MIPS_REG_16
            target = 0x801843F0
        elif pc in (0x80183FA4, 0x80183FA8):
            count = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
            dst = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
            counter_reg = UC_MIPS_REG_17
            dst_reg = UC_MIPS_REG_16
            target = 0x80183FBC
        elif pc in (0x80184150, 0x801841CC):
            return self._handle_nand_program_branch_loop_accelerator(pc)
        else:
            return self._handle_nand_program_loop_accelerator(pc)
        if count == 0 or count > 0x1000 or not self._is_mapped_ram_va(dst, count):
            return False
        data = self._read_nand_data_bytes(count)
        self.uc.mem_write(va_to_phys(dst), data)
        self.uc.reg_write(counter_reg, 0)
        self.uc.reg_write(dst_reg, (dst + count) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_PC, target)
        self.nand_loop_accel_count += 1
        self._record_nand_loop_event("read", pc, dst, count, target, preview=data[:16].hex())
        if self.nand_loop_accel_count <= 32 or self.nand_loop_accel_count % 256 == 0:
            self._trace_event("nand-loop-accelerate", pc=pc, addr=dst, size=count, target=target)
        return True

    def _handle_nand_program_loop_accelerator(self, pc: int) -> bool:
        if self.nand_cmd != 0x80:
            return False
        if pc == 0x80184140:
            count = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
            src = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
            counter_reg = UC_MIPS_REG_3
            src_reg = UC_MIPS_REG_17
            target = 0x80184158
            extra_regs: dict[int, int] = {}
        elif pc == 0x801841BC:
            count = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
            src = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
            counter_reg = UC_MIPS_REG_5
            src_reg = UC_MIPS_REG_17
            target = 0x801841D4
            extra_regs = {}
        elif pc == 0x80184530:
            count = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
            src = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
            counter_reg = UC_MIPS_REG_7
            src_reg = UC_MIPS_REG_3
            target = 0x8018454C
            extra_regs = {UC_MIPS_REG_4: 0x00010000}
        else:
            return False
        if count == 0 or count > 0x1000 or not self._is_mapped_ram_va(src, count):
            return False
        data = self._read_block_va_safe(src, count)
        if data is None:
            return False
        self._append_nand_program_bytes(data)
        self.uc.reg_write(counter_reg, 0)
        self.uc.reg_write(src_reg, (src + count) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_2, data[-1])
        for reg, value in extra_regs.items():
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_MIPS_REG_PC, target)
        self.nand_loop_accel_count += 1
        self._record_nand_loop_event("program", pc, src, count, target, preview=data[:16].hex())
        if self.nand_loop_accel_count <= 32 or self.nand_loop_accel_count % 256 == 0:
            self._trace_event("nand-program-loop-accelerate", pc=pc, addr=src, size=count, target=target)
        return True

    def _handle_nand_program_branch_loop_accelerator(self, pc: int) -> bool:
        if self.nand_cmd != 0x80:
            return False
        if pc == 0x80184150:
            remaining = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
            src = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
            counter_reg = UC_MIPS_REG_3
            src_reg = UC_MIPS_REG_17
            target = 0x80184158
        elif pc == 0x801841CC:
            remaining = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
            src = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
            counter_reg = UC_MIPS_REG_5
            src_reg = UC_MIPS_REG_17
            target = 0x801841D4
        else:
            return False
        if remaining > 0x1000 or not self._is_mapped_ram_va(src, remaining):
            return False
        current = self.uc.reg_read(UC_MIPS_REG_2) & 0xFF
        tail = b"" if remaining == 0 else self._read_block_va_safe(src, remaining)
        if tail is None:
            return False
        data = bytes([current]) + tail
        self._append_nand_program_bytes(data)
        self.uc.reg_write(counter_reg, 0)
        self.uc.reg_write(src_reg, (src + remaining) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_2, data[-1])
        self.uc.reg_write(UC_MIPS_REG_PC, target)
        self.nand_loop_accel_count += 1
        self._record_nand_loop_event("program-branch", pc, src, len(data), target, preview=data[:16].hex())
        if self.nand_loop_accel_count <= 32 or self.nand_loop_accel_count % 256 == 0:
            self._trace_event("nand-program-branch-accelerate", pc=pc, addr=src, size=len(data), target=target)
        return True

    def _record_nand_loop_event(
        self,
        mode: str,
        pc: int,
        addr: int,
        size: int,
        target: int,
        *,
        preview: str = "",
    ) -> None:
        row = {
            "pc": f"0x{pc:08x}",
            "mode": mode,
            "addr": f"0x{addr:08x}",
            "size": size,
            "target": f"0x{target:08x}",
            "page": f"0x{self.nand_current_page:x}",
            "column": f"0x{self.nand_current_column:x}",
            "read_index": f"0x{self.nand_read_index:x}",
            "program_page": f"0x{self.nand_program_page:x}",
            "program_column": f"0x{self.nand_program_column:x}",
            "program_buffer_size": len(self.nand_program_buffer),
            "preview": preview,
            "count": self.nand_loop_accel_count,
        }
        self.nand_loop_events.append(row)
        if len(self.nand_loop_events) > 128:
            del self.nand_loop_events[0]

    def _trace_nand_latch_write(self, kind: str, address: int, value: int) -> None:
        pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        self.nand_latch_writes.append(
            {
                "pc": f"0x{pc:08x}",
                "kind": kind,
                "addr": f"0x{address:08x}",
                "value": f"0x{value & 0xFF:02x}",
                "cmd": f"0x{self.nand_cmd:02x}",
                "addr_bytes": " ".join(f"{b:02x}" for b in self.nand_addr_bytes),
                "s0": f"0x{self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF:08x}",
                "s1": f"0x{self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF:08x}",
                "s2": f"0x{self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF:08x}",
                "v0": f"0x{self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF:08x}",
                "v1": f"0x{self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF:08x}",
            }
        )
        if len(self.nand_latch_writes) > 512:
            del self.nand_latch_writes[0]

    def _model_mmio(self, access: int, address: int, size: int, value: int) -> None:
        if self.profile != "bbk9588-uboot":
            return

        if access == UC_MEM_WRITE:
            mask = (1 << (size * 8)) - 1
            self.mmio_regs[address] = value & mask
            if 0x13040000 <= address < 0x13040100:
                # UDC registers are not normal RAM. Keep configuration writes
                # in mmio_regs for inspection, but do not let them become the
                # value later read back as cable/status/interrupt state.
                self._write_mmio_value(address, size, 0)
            if SADC_BASE <= address < SADC_BASE + 0x100:
                if address == SADC_STATUS:
                    cleared_conversion = bool(value & 0x04)
                    self.sadc_status_event &= ~(value & 0xFF)
                    if cleared_conversion and self.sadc_conversion_events_remaining > 0:
                        self.sadc_conversion_events_remaining -= 1
                    if (
                        self.touch_down
                        and cleared_conversion
                        and self.sadc_conversion_events_remaining > 0
                        and (self.mmio_regs.get(SADC_BASE + 0x08, 0) & 0x10)
                    ):
                        self.sadc_status_event |= 0x04
                        self.intc_pending_mask |= 1 << 12
                    self._write_mmio_value(address, size, self.sadc_status_event)
                    return
                if (
                    address == SADC_BASE + 0x08
                    and self.touch_down
                    and (value & 0x10)
                    and self.sadc_conversion_events_remaining > 0
                ):
                    self.sadc_status_event |= 0x04
                    self.intc_pending_mask |= 1 << 12
                self._write_mmio_value(address, size, value)
            if address == 0x10001010 and size == 4:
                # C200's IRQ mask/ack helper writes the current IRQ bit back
                # to the INTC pending register after dispatch. Model that as
                # an acknowledge for now; the source device can assert it again.
                ack = value & 0xFFFFFFFF
                self.intc_pending_mask &= ~ack
                if ack & (1 << 23):
                    self.tcu_pending_mask &= ~0x1
                if ack & (1 << 22):
                    self.tcu_pending_mask &= ~0x2
                if ack & ((1 << 23) | (1 << 22)):
                    self._schedule_next_tcu_irq()
                if ack & (1 << 24):
                    self._schedule_next_irq24()
            elif address == 0x10002038 and size == 4:
                self.tcu_enabled_mask |= value & 0xFFFFFFFF
                self._schedule_next_tcu_irq()
            elif address == 0x1000203C and size == 4:
                self.tcu_enabled_mask &= ~(value & 0xFFFFFFFF)
                self._schedule_next_tcu_irq()
            elif address == 0x10002028 and size == 4:
                self.tcu_pending_mask &= ~(value & 0xFFFFFFFF)
                if value & 0x1:
                    self.intc_pending_mask &= ~(1 << 23)
                if value & 0x2:
                    self.intc_pending_mask &= ~(1 << 22)
                self._schedule_next_tcu_irq()
            elif address in (0x10002050, 0x10002054) and size == 4:
                self._update_tcu_period_from_register(value)
                self._schedule_next_tcu_irq()
            if address == 0x10030000 and size == 1:
                pc = self.uc.reg_read(UC_MIPS_REG_PC)
                byte = value & 0xFF
                self.uart_bytes.append(byte)
                self.uart_writes.append(
                    {
                        "pc": f"0x{pc:08x}",
                        "value": f"0x{byte:02x}",
                        "char": chr(byte) if 0x20 <= byte <= 0x7E else "",
                    }
                )
                if len(self.uart_writes) > 256:
                    del self.uart_writes[0]
            if 0x10043000 <= address < 0x10043100 or 0x10021000 <= address < 0x10021100:
                pc = self.uc.reg_read(UC_MIPS_REG_PC)
                self.lcd_writes.append(
                    {
                        "pc": f"0x{pc:08x}",
                        "addr": f"0x{address:08x}",
                        "size": size,
                        "value": f"0x{value & mask:x}",
                    }
                )
                if len(self.lcd_writes) > 256:
                    del self.lcd_writes[0]

        # JZ4740 NAND external bus as used by this bootloader:
        #   0xb8000000 -> data window, 0xb8008000 -> command latch,
        #   0xb8010000 -> address latch. Unicorn exposes these as physical
        #   0x18000000, 0x18008000, and 0x18010000.
        if access == UC_MEM_WRITE:
            if self.nand_legacy_erased:
                if address == 0x18008000 and size == 1:
                    self._trace_nand_latch_write("cmd", address, value)
                    self.nand_cmd = value & 0xFF
                    self.nand_addr_bytes.clear()
                    self.nand_read_index = 0
                    if self.nand_cmd != 0x90:
                        self.uc.mem_write(0x18000000, b"\xFF" * 4)
                    if self.nand_cmd == 0x30:
                        self.nand_busy_reads = 1
                elif address == 0x18010000 and size == 1:
                    self._trace_nand_latch_write("addr", address, value)
                    self.nand_addr_bytes.append(value & 0xFF)
                    if self.nand_cmd == 0x90 and self.nand_addr_bytes == [0]:
                        self.nand_read_index = 0
                        self.uc.mem_write(0x18000000, bytes([self.nand_read_id[0]]))
                    elif self.nand_cmd != 0x90:
                        self.uc.mem_write(0x18000000, b"\xFF" * 4)
                return
            if address == 0x18008000 and size == 1:
                self._trace_nand_latch_write("cmd", address, value)
                self.nand_cmd = value & 0xFF
                if self.nand_cmd in (0x00, 0x60, 0x90, 0xFF):
                    self.nand_addr_bytes.clear()
                    self.nand_read_index = 0
                if self.nand_cmd == 0x80:
                    self.nand_addr_bytes.clear()
                    self.nand_read_index = 0
                    self._begin_nand_program()
                if self.nand_cmd == 0x90:
                    self.nand_read_buffer = bytes(self.nand_read_id) + b"\xFF" * 8
                elif self.nand_cmd == 0x30:
                    self._prepare_nand_page_read()
                    self.nand_busy_reads = 1
                elif self.nand_cmd == 0x10:
                    self._commit_nand_program()
                    self.nand_busy_reads = 1
                elif self.nand_cmd == 0xD0:
                    self._commit_nand_erase()
                    self.nand_busy_reads = 1
                    self.nand_addr_bytes.clear()
                    self.nand_read_index = 0
                elif self.nand_cmd == 0x70:
                    self.nand_read_buffer = b"\x40\xFF\xFF\xFF"
                    self.nand_read_index = 0
                elif self.nand_cmd != 0x00:
                    self.uc.mem_write(0x18000000, b"\xFF" * 4)
            elif address == 0x18010000 and size == 1:
                self._trace_nand_latch_write("addr", address, value)
                self.nand_addr_bytes.append(value & 0xFF)
                if self.nand_cmd == 0x80:
                    self._update_nand_program_address()
                if self.nand_cmd == 0x90 and self.nand_addr_bytes == [0]:
                    self.nand_read_index = 0
                    self.nand_read_buffer = bytes(self.nand_read_id) + b"\xFF" * 8
                elif self.nand_cmd != 0x90:
                    self.uc.mem_write(0x18000000, b"\xFF" * 4)
            elif address == 0x18000000 and size in (1, 2, 4):
                if self.nand_cmd == 0x80:
                    self._append_nand_program_data(value, size)
            return

        if access == UC_MEM_READ:
            pulse_value = self._consume_mmio_pulse(address, size)
            if pulse_value is not None:
                self._write_u32_phys(address, pulse_value)
            elif 0x13040000 <= address < 0x13040100:
                self._write_mmio_value(address, size, self._model_udc_read_value(address, size))
            elif SADC_BASE <= address < SADC_BASE + 0x100:
                self._write_mmio_value(address, size, self._model_sadc_read_value(address, size))
            elif address in self.mmio_read_levels and size == 4:
                self._write_u32_phys(address, self.mmio_read_levels[address])
            elif address == 0x10010200 and size == 4:
                # GPIO/EMC NAND ready bit polled with mask 0x40000000.
                if self.nand_busy_reads > 0:
                    self.nand_busy_reads -= 1
                    ready = 0
                else:
                    ready = 0x40000000
                self._write_u32_phys(address, ready | self.gpio_idle_levels.get(address, 0))
            elif address == 0x10030014 and size in (1, 2, 4):
                # UART line/status register. C200 waits for bit 0x20 before
                # writes and bit 0x40 in a later diagnostics/flush path.
                self.uc.mem_write(address, (0x60).to_bytes(size, "little"))
            elif address == 0x10001010 and size == 4:
                self._refresh_tcu_pending()
                self._refresh_irq24_pending()
                self._write_u32_phys(address, self.intc_pending_mask)
            elif address == 0x10003000 and size == 4:
                # Timer/counter unit status. The diagnostic path at 0x800055a0
                # polls bit 0x80 between programming compare/control words.
                self._write_u32_phys(address, 0x00000080)
            elif 0x10010000 <= address < 0x10010400 and size == 4:
                # GPIO reads must be actively refreshed. Otherwise a previous
                # injected pulse remains in Unicorn's backing MMIO page and
                # incorrectly behaves like a latched input level.
                self._write_u32_phys(address, self.mmio_regs.get(address, self.gpio_idle_levels.get(address, 0)))
            elif address == 0x13010114 and size == 4:
                # BCH/ECC interrupt/status. U-Boot polls bit 2 in the NAND
                # read path around 0x8090329c. C200's NAND page reader waits
                # for bit 3, then requires bit 0 set and bit 1 clear.
                self._write_u32_phys(address, 0x0000000D)
            elif address == 0x1004300C and size == 4:
                # LCD controller command/status path used by C200 init. Bit 7
                # is polled as ready after writes to 0xb0043000.
                self._write_u32_phys(address, 0x00000080)
            elif address == 0x10021004 and size == 4:
                # C200 graphics/blit engine status. Init waits for bit 0x800
                # after issuing command 6 at 0xb0021000, and treats bit 0x100
                # as busy in the setup path.
                self._write_u32_phys(address, 0x00000800)
            elif address == 0x10021028 and size in (2, 4):
                # Graphics/blit completion flags. Callers acknowledge with
                # writes to this register, then poll bit0/bit1 for completion.
                self._write_mmio_value(address, size, 0x0003)
            elif address in (0x13020008, 0x13020028) and size == 4:
                # LCD DMA descriptors use these words as countdown/control
                # fields and wait for hardware to clear them.
                self._write_u32_phys(address, 0)
            elif address == 0x18000000 and size in (1, 2, 4):
                if self.nand_legacy_erased:
                    if self.nand_cmd == 0x90:
                        self.nand_read_index += 1
                        b = self.nand_read_id[min(self.nand_read_index, len(self.nand_read_id) - 1)]
                        data = bytes([b]) + b"\xFF" * 3
                    else:
                        data = b"\xFF" * 4
                    self.uc.mem_write(address, data)
                    return
                self.uc.mem_write(address, self._read_nand_data_window(size))

    def _on_invalid(self, uc, access: int, address: int, size: int, value: int, user_data) -> bool:
        pc = uc.reg_read(UC_MIPS_REG_PC)
        if access == UC_MEM_READ_UNMAPPED:
            kind = "read_unmapped"
        elif access == UC_MEM_WRITE_UNMAPPED:
            kind = "write_unmapped"
        elif access == UC_MEM_FETCH_UNMAPPED:
            kind = "fetch_unmapped"
        else:
            kind = f"invalid_{access}"
        if access == UC_MEM_READ_UNMAPPED and self._recover_bda_corrupt_pointer_read(pc, address, size):
            return True
        if len(self.state.invalid) < self.trace_limit:
            self.state.invalid.append(MmioAccess(pc=pc, kind=kind, addr=address, size=size, value=value))
        return False

    def _recover_bda_corrupt_pointer_read(self, pc: int, address: int, size: int) -> bool:
        if not self.bda_app_active or not self._is_bda_runtime_va(pc):
            return False
        if self._is_mapped_ram_va(address, size):
            return False

        regs = self._reg_map()
        values = [(idx, reg, self.uc.reg_read(reg) & 0xFFFFFFFF) for idx, reg in enumerate(regs)]
        bad_regs = [
            (idx, reg)
            for idx, reg, reg_value in values
            if 4 <= idx <= 7 and reg_value != 0 and reg_value == (address & 0xFFFFFFFF)
        ]
        if not bad_regs:
            return False

        low16 = address & 0xFFFF
        candidates = [
            reg_value
            for _, _, reg_value in values
            if reg_value != address
            and (reg_value & 0xFFFF) == low16
            and self._is_mapped_ram_va(reg_value, size)
            and self._is_bda_runtime_va(reg_value)
        ]
        if not candidates:
            return False
        fixed = candidates[0]
        for _, reg in bad_regs:
            self.uc.reg_write(reg, fixed)
        self._trace_event("bda-pointer-recover", pc=pc, addr=address, value=fixed, size=size)
        return True

    def _recover_bda_corrupt_pointer_registers(self, pc: int) -> None:
        if not self.bda_app_active or not self._is_bda_runtime_va(pc):
            return
        regs = self._reg_map()
        values = [(idx, reg, self.uc.reg_read(reg) & 0xFFFFFFFF) for idx, reg in enumerate(regs)]
        for idx, reg, reg_value in values:
            if not (4 <= idx <= 7) or reg_value == 0 or self._is_mapped_ram_va(reg_value, 1):
                continue
            low16 = reg_value & 0xFFFF
            candidates = [
                other_value
                for other_idx, _, other_value in values
                if other_idx != idx
                and (other_value & 0xFFFF) == low16
                and self._is_mapped_ram_va(other_value, 1)
                and self._is_bda_runtime_va(other_value)
            ]
            if not candidates:
                continue
            fixed = candidates[0]
            self.uc.reg_write(reg, fixed)
            self._trace_event("bda-reg-pointer-recover", pc=pc, addr=reg_value, value=fixed, size=idx)

    def _handle_bda_sdkinput_copy_loop(self, pc: int) -> bool:
        if not self.bda_app_active or pc != 0x81C0392C:
            return False
        src_base = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        idx = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
        dst_cursor = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        src = (src_base + idx) & 0xFFFFFFFF
        if idx > 0x100 or not self._is_bda_runtime_va(src_base) or not self._is_mapped_ram_va(src, 1):
            return False
        try:
            ch = self._read_mem_va(src, 1) & 0xFF
        except Exception:
            return False
        self.uc.reg_write(UC_MIPS_REG_3, (dst_cursor + 1) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_6, ch)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x81C03934)
        self._trace_event("bda-copy-loop-fix", pc=pc, addr=src, value=ch, size=idx)
        return True

    def _handle_bda_sdkinput_copy_branch(self, pc: int) -> bool:
        if not self.bda_app_active or pc != 0x81C038A0:
            return False
        idx = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
        limit = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        if idx == limit:
            target = 0x81C038A8
            self.uc.reg_write(UC_MIPS_REG_PC, target)
            self._trace_event("bda-copy-branch-fix", pc=pc, value=idx, size=limit, target=target)
            return True

        src_base = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        dst_cursor = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        src = (src_base + idx) & 0xFFFFFFFF
        dst_cursor = (dst_cursor + 1) & 0xFFFFFFFF
        dst = (dst_cursor + 0x0A) & 0xFFFFFFFF
        if idx > 0x100 or not self._is_bda_runtime_va(src_base) or not self._is_mapped_ram_va(src, 1):
            return False
        try:
            ch = self._read_mem_va(src, 1) & 0xFF
            self._write_mem_va(dst, 1, ch)
        except Exception:
            return False
        self.uc.reg_write(UC_MIPS_REG_2, (idx + 1) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_3, dst_cursor)
        self.uc.reg_write(UC_MIPS_REG_6, ch)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x81C038A0)
        self._trace_event("bda-copy-branch-fix", pc=pc, addr=src, value=ch, size=idx, target=dst)
        return True

    def _read_word_at_va(self, va: int) -> int | None:
        phys = va & 0x1FFFFFFF if va >= RAM_BASE else va
        try:
            return struct.unpack("<I", self.uc.mem_read(phys, 4))[0]
        except Exception:
            return None

    def _reg_map(self) -> list[int]:
        return [
            UC_MIPS_REG_0,
            UC_MIPS_REG_1,
            UC_MIPS_REG_2,
            UC_MIPS_REG_3,
            UC_MIPS_REG_4,
            UC_MIPS_REG_5,
            UC_MIPS_REG_6,
            UC_MIPS_REG_7,
            UC_MIPS_REG_8,
            UC_MIPS_REG_9,
            UC_MIPS_REG_10,
            UC_MIPS_REG_11,
            UC_MIPS_REG_12,
            UC_MIPS_REG_13,
            UC_MIPS_REG_14,
            UC_MIPS_REG_15,
            UC_MIPS_REG_16,
            UC_MIPS_REG_17,
            UC_MIPS_REG_18,
            UC_MIPS_REG_19,
            UC_MIPS_REG_20,
            UC_MIPS_REG_21,
            UC_MIPS_REG_22,
            UC_MIPS_REG_23,
            UC_MIPS_REG_24,
            UC_MIPS_REG_25,
            UC_MIPS_REG_26,
            UC_MIPS_REG_27,
            UC_MIPS_REG_28,
            UC_MIPS_REG_29,
            UC_MIPS_REG_30,
            UC_MIPS_REG_31,
        ]

    def _emulate_delay_slot(self, pc: int) -> str:
        word = self._read_word_at_va(pc)
        if word is None or word == 0:
            return "nop"
        opcode = (word >> 26) & 0x3F
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        imm = word & 0xFFFF
        if imm & 0x8000:
            imm -= 0x10000
        regs = self._reg_map()
        if opcode == 0:
            rd = (word >> 11) & 0x1F
            shamt = (word >> 6) & 0x1F
            funct = word & 0x3F
            if funct in (0x21, 0x25):  # addu/or
                left = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
                right = self.uc.reg_read(regs[rt]) & 0xFFFFFFFF
                value = (left + right) & 0xFFFFFFFF if funct == 0x21 else left | right
                if rd:
                    self.uc.reg_write(regs[rd], value)
                name = "addu" if funct == 0x21 else "or"
                return f"{name} r{rd},r{rs},r{rt}"
            if funct == 0x2B:  # sltu
                left = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
                right = self.uc.reg_read(regs[rt]) & 0xFFFFFFFF
                if rd:
                    self.uc.reg_write(regs[rd], 1 if left < right else 0)
                return f"sltu r{rd},r{rs},r{rt}"
            if funct == 0x00 and rs == 0:  # sll
                value = (self.uc.reg_read(regs[rt]) << shamt) & 0xFFFFFFFF
                if rd:
                    self.uc.reg_write(regs[rd], value)
                return f"sll r{rd},r{rt},{shamt}"
        if opcode == 9:  # addiu
            value = (self.uc.reg_read(regs[rs]) + imm) & 0xFFFFFFFF
            if rt:
                self.uc.reg_write(regs[rt], value)
            return f"addiu r{rt},r{rs},{imm}"
        if opcode in (10, 11):  # slti/sltiu
            rs_raw = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
            if opcode == 10:
                rs_val = rs_raw - 0x100000000 if rs_raw & 0x80000000 else rs_raw
                value = 1 if rs_val < imm else 0
                name = "slti"
            else:
                value = 1 if rs_raw < (imm & 0xFFFFFFFF) else 0
                name = "sltiu"
            if rt:
                self.uc.reg_write(regs[rt], value)
            return f"{name} r{rt},r{rs},{imm}"
        if opcode == 13:  # ori
            value = (self.uc.reg_read(regs[rs]) | (word & 0xFFFF)) & 0xFFFFFFFF
            if rt:
                self.uc.reg_write(regs[rt], value)
            return f"ori r{rt},r{rs},0x{word & 0xffff:x}"
        if opcode in (32, 33, 35, 36, 37):  # lb/lh/lw/lbu/lhu
            size = {32: 1, 33: 2, 35: 4, 36: 1, 37: 2}[opcode]
            addr = (self.uc.reg_read(regs[rs]) + imm) & 0xFFFFFFFF
            value = self._read_mem_va(addr, size)
            if opcode in (32, 33):
                sign = 1 << (size * 8 - 1)
                if value & sign:
                    value -= 1 << (size * 8)
            if rt:
                self.uc.reg_write(regs[rt], value & 0xFFFFFFFF)
            name = {32: "lb", 33: "lh", 35: "lw", 36: "lbu", 37: "lhu"}[opcode]
            return f"{name} r{rt},{imm}(r{rs})"
        if opcode in (40, 41, 43):  # sb/sh/sw
            size = {40: 1, 41: 2, 43: 4}[opcode]
            addr = (self.uc.reg_read(regs[rs]) + imm) & 0xFFFFFFFF
            value = self.uc.reg_read(regs[rt])
            self._write_mem_va(addr, size, value)
            phys = va_to_phys(addr)
            if (PHYS_MMIO_BASE <= phys < PHYS_MMIO_BASE + MMIO_SIZE) or (
                EXT_BANK_BASE <= phys < EXT_BANK_BASE + EXT_BANK_SIZE
            ):
                self._model_mmio(UC_MEM_WRITE, phys, size, value)
            name = {40: "sb", 41: "sh", 43: "sw"}[opcode]
            return f"{name} r{rt},{imm}(r{rs})"
        return f"unemulated-delay word=0x{word:08x}"

    def _handle_c200_reset_init_loop(self, pc: int) -> bool:
        if pc == 0x8000403C:
            self.uc.reg_write(UC_MIPS_REG_8, 0x80004000)
            self.uc.reg_write(UC_MIPS_REG_9, 0x80004000)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80004050)
            self._trace_event("c200-cache-init-loop", pc=pc, target=0x80004050)
            return True
        if pc == 0x80004074:
            start = self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF
            end = self.uc.reg_read(UC_MIPS_REG_9) & 0xFFFFFFFF
            if start <= end and self._is_mapped_ram_va(start, end - start):
                self.uc.mem_write(va_to_phys(start), b"\x00" * (end - start))
            self.uc.reg_write(UC_MIPS_REG_8, end)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80004080)
            self._trace_event("c200-bss-clear-loop", pc=pc, addr=start, size=(end - start) & 0xFFFFFFFF, target=0x80004080)
            return True
        return False

    def _is_recoverable_branch_word(self, word: int) -> bool:
        opcode = (word >> 26) & 0x3F
        funct = word & 0x3F
        if opcode in (1, 2, 3, 4, 5, 6, 7):
            return True
        return opcode == 0 and funct == 8

    def _is_recoverable_exception_word(self, word: int) -> bool:
        opcode = (word >> 26) & 0x3F
        funct = word & 0x3F
        # cache/sync and simple COP0 moves are hardware-management operations.
        # The current functional emulator keeps only enough CP0 state to let
        # firmware reset stubs proceed.
        return opcode in (16, 47) or (opcode == 0 and funct == 0x0F) or self._is_recoverable_branch_word(word)

    def _next_recoverable_exception_pc(self, start_pc: int, limit: int = 0x80) -> int | None:
        for pc in range(start_pc, start_pc + limit, 4):
            word = self._read_word_at_va(pc)
            if word is None:
                return None
            if self._is_recoverable_exception_word(word):
                return pc
        return None

    def _recover_exception(self, exc: Exception) -> bool:
        if not self.recover_jr:
            return False
        current_pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        if self._looks_like_code_return(current_pc) and self._read_word_at_va(current_pc) is not None:
            pc = current_pc
        else:
            pc = self.state.last_pc
            word_at_last = self._read_word_at_va(pc)
            if word_at_last is not None and not self._is_recoverable_exception_word(word_at_last):
                pc = self._next_recoverable_exception_pc(pc) or pc
        if self.profile == "bbk9588-uboot" and pc in (0x80010D88, 0x80010D90, 0x80010D9C, 0x80010DA8):
            target = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_PC, target)
            if len(self.state.recoveries) < self.trace_limit:
                self.state.recoveries.append(
                    f"getter-delay-exception pc=0x{pc:08x} target=0x{target:08x} exc={exc}"
                )
            return True
        word = self._read_word_at_va(pc)
        if word is None:
            return False
        snapshot = self.recovery_reg_snapshots.get(pc)
        if snapshot is not None:
            self._restore_regs_for_recovery(snapshot)
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        funct = word & 0x3F
        opcode = (word >> 26) & 0x3F
        if opcode == 16 and rs in (0, 4):  # mfc0/mtc0
            if rs == 0 and rt:
                self.uc.reg_write(self._reg_map()[rt], 0)
            self.uc.reg_write(UC_MIPS_REG_PC, (pc + 4) & 0xFFFFFFFF)
            if len(self.state.recoveries) < self.trace_limit:
                name = "mfc0" if rs == 0 else "mtc0"
                self.state.recoveries.append(f"{name}-exception pc=0x{pc:08x} next=0x{(pc + 4) & 0xFFFFFFFF:08x} exc={exc}")
            return True
        if opcode == 47 or (opcode == 0 and funct == 0x0F):  # cache/sync
            self.uc.reg_write(UC_MIPS_REG_PC, (pc + 4) & 0xFFFFFFFF)
            if len(self.state.recoveries) < self.trace_limit:
                name = "cache" if opcode == 47 else "sync"
                self.state.recoveries.append(f"{name}-exception pc=0x{pc:08x} next=0x{(pc + 4) & 0xFFFFFFFF:08x} exc={exc}")
            return True
        # j/jal. Unicorn can raise a CPU exception on branch instructions after
        # some CP0/cache setup paths even when the target is mapped. Treat that
        # as an engine quirk, not a device model event.
        if opcode in (2, 3):
            target = ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
            if opcode == 3:
                self.uc.reg_write(UC_MIPS_REG_31, (pc + 8) & 0xFFFFFFFF)
            delay = self._emulate_delay_slot(pc + 4)
            self.uc.reg_write(UC_MIPS_REG_PC, target)
            if len(self.state.recoveries) < self.trace_limit:
                name = "jal" if opcode == 3 else "j"
                self.state.recoveries.append(
                    f"{name}-exception pc=0x{pc:08x} target=0x{target:08x} delay={delay} exc={exc}"
                )
            return True

        if opcode in (4, 5):  # beq/bne
            regs = self._reg_map()
            rs_val = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
            rt = (word >> 16) & 0x1F
            rt_val = self.uc.reg_read(regs[rt]) & 0xFFFFFFFF
            imm = word & 0xFFFF
            if imm & 0x8000:
                imm -= 0x10000
            taken = (rs_val == rt_val) if opcode == 4 else (rs_val != rt_val)
            delay = self._emulate_delay_slot(pc + 4)
            target = (pc + 4 + (imm << 2)) & 0xFFFFFFFF if taken else (pc + 8) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_PC, target)
            if len(self.state.recoveries) < self.trace_limit:
                name = "beq" if opcode == 4 else "bne"
                self.state.recoveries.append(
                    f"{name}-exception pc=0x{pc:08x} target=0x{target:08x} taken={taken} delay={delay} exc={exc}"
                )
            return True

        if opcode in (6, 7):  # blez/bgtz
            regs = self._reg_map()
            rs_raw = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
            rs_val = rs_raw - 0x100000000 if rs_raw & 0x80000000 else rs_raw
            imm = word & 0xFFFF
            if imm & 0x8000:
                imm -= 0x10000
            taken = (rs_val <= 0) if opcode == 6 else (rs_val > 0)
            delay = self._emulate_delay_slot(pc + 4)
            target = (pc + 4 + (imm << 2)) & 0xFFFFFFFF if taken else (pc + 8) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_PC, target)
            if len(self.state.recoveries) < self.trace_limit:
                name = "blez" if opcode == 6 else "bgtz"
                self.state.recoveries.append(
                    f"{name}-exception pc=0x{pc:08x} target=0x{target:08x} taken={taken} delay={delay} exc={exc}"
                )
            return True

        if opcode == 1:  # REGIMM: bltz/bgez
            rt = (word >> 16) & 0x1F
            if rt in (0, 1):
                regs = self._reg_map()
                rs_raw = self.uc.reg_read(regs[rs]) & 0xFFFFFFFF
                rs_val = rs_raw - 0x100000000 if rs_raw & 0x80000000 else rs_raw
                imm = word & 0xFFFF
                if imm & 0x8000:
                    imm -= 0x10000
                taken = (rs_val < 0) if rt == 0 else (rs_val >= 0)
                delay = self._emulate_delay_slot(pc + 4)
                target = (pc + 4 + (imm << 2)) & 0xFFFFFFFF if taken else (pc + 8) & 0xFFFFFFFF
                self.uc.reg_write(UC_MIPS_REG_PC, target)
                if len(self.state.recoveries) < self.trace_limit:
                    name = "bltz" if rt == 0 else "bgez"
                    self.state.recoveries.append(
                        f"{name}-exception pc=0x{pc:08x} target=0x{target:08x} taken={taken} delay={delay} exc={exc}"
                    )
                return True

        # jr rs: opcode=0, rt/rd/shamt=0, funct=8.
        if opcode == 0 and (word & 0x001FFFFF) == 0x00000008 and funct == 8:
            reg_map = self._reg_map()
            target = self.uc.reg_read(reg_map[rs]) & 0xFFFFFFFF
            if self.preexecuted_jr_delay_pc == pc:
                delay = "preexecuted"
            else:
                delay = self._emulate_delay_slot(pc + 4)
            self.uc.reg_write(UC_MIPS_REG_PC, target)
            if len(self.state.recoveries) < self.trace_limit:
                self.state.recoveries.append(
                    f"jr-exception pc=0x{pc:08x} target=0x{target:08x} delay={delay} exc={exc}"
                )
            return True
        return False

    def run(self, steps: int, max_seconds: float | None = None) -> TraceState:
        self.uc.reg_write(UC_MIPS_REG_PC, self.pc)
        # Stack is normally set by the reset code. Seed it only on the first
        # run so a long-lived emulator can continue in small frontend steps.
        if self.state.insn_count == 0:
            self.uc.reg_write(UC_MIPS_REG_SP, RAM_BASE + min(self.ram_size, 0x400000) - 0x100)
        remaining = steps
        deadline = None if max_seconds is None or max_seconds <= 0 else time.monotonic() + max_seconds
        if self.fast_hooks:
            chunk_size = 100_000 if deadline is not None else 2_000_000
        else:
            chunk_size = steps
        try:
            while remaining > 0:
                if deadline is not None and time.monotonic() >= deadline:
                    self.state.stop_reason = self.state.stop_reason or "max_seconds"
                    break
                start_pc = self.uc.reg_read(UC_MIPS_REG_PC)
                before = self.state.insn_count
                count = min(remaining, chunk_size)
                try:
                    self.internal_chunk_stop = False
                    self.uc.emu_start(start_pc, 0, count=count)
                    ran = max(1, self.state.insn_count - before)
                    if self.fast_hooks and not self.internal_chunk_stop:
                        remaining -= count
                    else:
                        remaining -= ran
                    if self.state.stop_reason:
                        break
                except UcError as exc:
                    ran = max(1, self.state.insn_count - before)
                    remaining -= ran
                    if not self._recover_exception(exc):
                        raise
        finally:
            self.pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        return self.state

    def _state_regs(self) -> list[tuple[str, int]]:
        return [
            ("zero", UC_MIPS_REG_0),
            ("at", UC_MIPS_REG_1),
            ("v0", UC_MIPS_REG_2),
            ("v1", UC_MIPS_REG_3),
            ("a0", UC_MIPS_REG_4),
            ("a1", UC_MIPS_REG_5),
            ("a2", UC_MIPS_REG_6),
            ("a3", UC_MIPS_REG_7),
            ("t0", UC_MIPS_REG_8),
            ("t1", UC_MIPS_REG_9),
            ("t2", UC_MIPS_REG_10),
            ("t3", UC_MIPS_REG_11),
            ("t4", UC_MIPS_REG_12),
            ("t5", UC_MIPS_REG_13),
            ("t6", UC_MIPS_REG_14),
            ("t7", UC_MIPS_REG_15),
            ("s0", UC_MIPS_REG_16),
            ("s1", UC_MIPS_REG_17),
            ("s2", UC_MIPS_REG_18),
            ("s3", UC_MIPS_REG_19),
            ("s4", UC_MIPS_REG_20),
            ("s5", UC_MIPS_REG_21),
            ("s6", UC_MIPS_REG_22),
            ("s7", UC_MIPS_REG_23),
            ("t8", UC_MIPS_REG_24),
            ("t9", UC_MIPS_REG_25),
            ("k0", UC_MIPS_REG_26),
            ("k1", UC_MIPS_REG_27),
            ("gp", UC_MIPS_REG_28),
            ("sp", UC_MIPS_REG_29),
            ("fp", UC_MIPS_REG_30),
            ("ra", UC_MIPS_REG_31),
            ("pc", UC_MIPS_REG_PC),
        ]

    def save_emulator_state(self, path: Path) -> None:
        payload = {
            "version": 1,
            "ram_size": self.ram_size,
            "regs": {name: self.uc.reg_read(reg) & 0xFFFFFFFF for name, reg in self._state_regs()},
            "cp0_status": self.uc.reg_read(UC_MIPS_REG_CP0_STATUS) & 0xFFFFFFFF,
            "pc": self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF,
            "insn_count": self.state.insn_count,
            "mmio_regs": self.mmio_regs,
            "gpio_idle_levels": self.gpio_idle_levels,
            "nand_cmd": self.nand_cmd,
            "nand_addr_bytes": self.nand_addr_bytes,
            "nand_read_buffer": bytes(self.nand_read_buffer),
            "nand_read_index": self.nand_read_index,
            "nand_busy_reads": self.nand_busy_reads,
            "nand_last_oob_page": self.nand_last_oob_page,
            "nand_data_window_read_count": self.nand_data_window_read_count,
            "nand_loop_accel_count": self.nand_loop_accel_count,
            "nand_program_buffer": bytes(self.nand_program_buffer),
            "nand_program_page": self.nand_program_page,
            "nand_program_column": self.nand_program_column,
            "nand_erase_count": self.nand_erase_count,
            "nand_page_overrides": self.nand_page_overrides,
            "block_sector_overrides": self.block_sector_overrides,
            "usb_connected": self.usb_connected,
            "touch_x": self.touch_x,
            "touch_y": self.touch_y,
            "touch_down": self.touch_down,
            "sadc_next_axis": self.sadc_next_axis,
            "sadc_status_event": self.sadc_status_event,
            "sadc_conversion_events_remaining": self.sadc_conversion_events_remaining,
            "tcu_enabled_mask": self.tcu_enabled_mask,
            "tcu_pending_mask": self.tcu_pending_mask,
            "intc_pending_mask": self.intc_pending_mask,
            "tcu_period_insn": self.tcu_period_insn,
            "next_tcu_irq_insn": self.next_tcu_irq_insn,
            "irq24_period_insn": self.irq24_period_insn,
            "next_irq24_insn": self.next_irq24_insn,
            "interrupt_return_pc": self.interrupt_return_pc,
            "interrupt_suppress_pc_once": self.interrupt_suppress_pc_once,
            "mmio_delay_branch_count": self.mmio_delay_branch_count,
            "scratch_alloc_va": self.scratch_alloc_va,
            "ram_z": zlib.compress(bytes(self.uc.mem_read(PHYS_RAM_BASE, self.ram_size)), level=1),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))

    def load_emulator_state(self, path: Path) -> None:
        payload = pickle.loads(path.read_bytes())
        if payload.get("version") != 1:
            raise ValueError(f"unsupported emulator state version: {payload.get('version')}")
        if int(payload["ram_size"]) != self.ram_size:
            raise ValueError(f"state RAM size mismatch: {payload['ram_size']} != {self.ram_size}")
        ram = zlib.decompress(payload["ram_z"])
        if len(ram) != self.ram_size:
            raise ValueError(f"state RAM payload mismatch: {len(ram)} != {self.ram_size}")
        self.uc.mem_write(PHYS_RAM_BASE, ram)
        self.uc.mem_write(KSEG1_BASE, ram)
        for name, reg in self._state_regs():
            if name in payload["regs"]:
                self.uc.reg_write(reg, int(payload["regs"][name]) & 0xFFFFFFFF)
        self.pc = int(payload["regs"].get("pc", payload.get("pc", self.pc))) & 0xFFFFFFFF
        self.uc.reg_write(UC_MIPS_REG_PC, self.pc)
        self.uc.reg_write(UC_MIPS_REG_CP0_STATUS, int(payload.get("cp0_status", 1)) & 0xFFFFFFFF)
        self.state.insn_count = int(payload.get("insn_count", 1))
        self.state.last_pc = self.pc
        self.state.pcs = [self.pc]
        self.state.stop_reason = None
        self.mmio_regs = {int(k): int(v) for k, v in payload.get("mmio_regs", {}).items()}
        saved_gpio_idle_levels = {int(k): int(v) for k, v in payload.get("gpio_idle_levels", {}).items()}
        self.gpio_idle_levels = dict(GPIO_KEY_IDLE_LEVELS)
        for addr, value in saved_gpio_idle_levels.items():
            if value != 0 or addr not in GPIO_KEY_IDLE_LEVELS:
                self.gpio_idle_levels[addr] = value
        self.nand_cmd = int(payload.get("nand_cmd", 0))
        self.nand_addr_bytes = list(payload.get("nand_addr_bytes", []))
        self.nand_read_buffer = bytes(payload.get("nand_read_buffer", b"\xFF" * 4))
        self.nand_read_index = int(payload.get("nand_read_index", 0))
        self.nand_busy_reads = int(payload.get("nand_busy_reads", 0))
        self.nand_data_window_read_count = int(payload.get("nand_data_window_read_count", self.nand_data_window_read_count))
        self.nand_loop_accel_count = int(payload.get("nand_loop_accel_count", self.nand_loop_accel_count))
        self.nand_program_buffer = bytearray(payload.get("nand_program_buffer", b""))
        self.nand_program_page = int(payload.get("nand_program_page", 0))
        self.nand_program_column = int(payload.get("nand_program_column", 0))
        self.nand_erase_count = int(payload.get("nand_erase_count", self.nand_erase_count))
        self.nand_page_overrides = {int(k): bytes(v) for k, v in payload.get("nand_page_overrides", {}).items()}
        self.block_sector_overrides = {
            int(k): bytes(v) for k, v in payload.get("block_sector_overrides", {}).items()
        }
        if self.block_data is not None:
            for sector, data in self.block_sector_overrides.items():
                offset = sector * 512
                end_offset = offset + len(data)
                if end_offset > len(self.block_data):
                    self.block_data.extend(b"\x00" * (end_offset - len(self.block_data)))
                self.block_data[offset:end_offset] = data
        if self.readonly_nand_page_ranges:
            self.nand_page_overrides = {
                page: data
                for page, data in self.nand_page_overrides.items()
                if not self._is_readonly_nand_page(page)
            }
        self.usb_connected = bool(payload.get("usb_connected", self.usb_connected))
        self.touch_x = int(payload.get("touch_x", self.touch_x))
        self.touch_y = int(payload.get("touch_y", self.touch_y))
        self.touch_down = bool(payload.get("touch_down", self.touch_down))
        for addr, bit in TOUCH_PEN_GPIO_LEVELS:
            gpio = self.gpio_idle_levels.get(addr, GPIO_KEY_IDLE_LEVELS.get(addr, 0))
            if self.touch_down:
                gpio &= ~bit
            else:
                gpio |= bit
            self.gpio_idle_levels[addr] = gpio & 0xFFFFFFFF
            self.mmio_read_levels.pop(addr, None)
        self.sadc_next_axis = int(payload.get("sadc_next_axis", self.sadc_next_axis)) & 1
        self.sadc_status_event = int(payload.get("sadc_status_event", self.sadc_status_event)) & 0xFF
        self.sadc_conversion_events_remaining = int(
            payload.get("sadc_conversion_events_remaining", self.sadc_conversion_events_remaining)
        )
        if self.nand_data is not None:
            stride = self.nand_page_size + self.nand_spare_size
            for page, data in self.nand_page_overrides.items():
                offset = page * stride
                end_offset = offset + len(data)
                if end_offset > len(self.nand_data):
                    self.nand_data.extend(b"\xFF" * (end_offset - len(self.nand_data)))
                self.nand_data[offset:end_offset] = data
        loaded_oob_page = payload.get("nand_last_oob_page")
        self.nand_last_oob_page = None if loaded_oob_page is None else int(loaded_oob_page)
        self.tcu_enabled_mask = int(payload.get("tcu_enabled_mask", self.mmio_regs.get(0x10002038, self.tcu_enabled_mask)))
        self.tcu_pending_mask = int(payload.get("tcu_pending_mask", self.tcu_pending_mask))
        self.intc_pending_mask = int(payload.get("intc_pending_mask", self.intc_pending_mask))
        self.tcu_period_insn = int(payload.get("tcu_period_insn", self.tcu_period_insn))
        self.irq24_period_insn = int(payload.get("irq24_period_insn", self.irq24_period_insn))
        for addr in (0x10002054, 0x10002050):
            if addr in self.mmio_regs:
                self._update_tcu_period_from_register(self.mmio_regs[addr])
                break
        next_tcu = payload.get("next_tcu_irq_insn")
        self.next_tcu_irq_insn = None if next_tcu is None else int(next_tcu)
        if next_tcu is None and self.tcu_enabled_mask:
            self._schedule_next_tcu_irq()
        next_irq24 = payload.get("next_irq24_insn")
        self.next_irq24_insn = None if next_irq24 is None else int(next_irq24)
        irq_return = payload.get("interrupt_return_pc")
        self.interrupt_return_pc = None if irq_return is None else int(irq_return)
        irq_suppress = payload.get("interrupt_suppress_pc_once")
        self.interrupt_suppress_pc_once = None if irq_suppress is None else int(irq_suppress)
        self.mmio_delay_branch_count = int(payload.get("mmio_delay_branch_count", self.mmio_delay_branch_count))
        self.scratch_alloc_va = int(payload.get("scratch_alloc_va", self.scratch_alloc_va))

    def regs(self) -> dict[str, str]:
        names = [
            ("zero", UC_MIPS_REG_0),
            ("at", UC_MIPS_REG_1),
            ("v0", UC_MIPS_REG_2),
            ("v1", UC_MIPS_REG_3),
            ("a0", UC_MIPS_REG_4),
            ("a1", UC_MIPS_REG_5),
            ("a2", UC_MIPS_REG_6),
            ("a3", UC_MIPS_REG_7),
            ("t0", UC_MIPS_REG_8),
            ("t1", UC_MIPS_REG_9),
            ("t2", UC_MIPS_REG_10),
            ("t3", UC_MIPS_REG_11),
            ("t4", UC_MIPS_REG_12),
            ("t5", UC_MIPS_REG_13),
            ("t6", UC_MIPS_REG_14),
            ("t7", UC_MIPS_REG_15),
            ("s0", UC_MIPS_REG_16),
            ("s1", UC_MIPS_REG_17),
            ("s2", UC_MIPS_REG_18),
            ("s3", UC_MIPS_REG_19),
            ("s4", UC_MIPS_REG_20),
            ("s5", UC_MIPS_REG_21),
            ("s6", UC_MIPS_REG_22),
            ("s7", UC_MIPS_REG_23),
            ("t8", UC_MIPS_REG_24),
            ("t9", UC_MIPS_REG_25),
            ("k0", UC_MIPS_REG_26),
            ("k1", UC_MIPS_REG_27),
            ("gp", UC_MIPS_REG_28),
            ("sp", UC_MIPS_REG_29),
            ("fp", UC_MIPS_REG_30),
            ("ra", UC_MIPS_REG_31),
            ("pc", UC_MIPS_REG_PC),
        ]
        out = {name: f"0x{self.uc.reg_read(reg) & 0xFFFFFFFF:08x}" for name, reg in names}
        out["cp0_status"] = f"0x{self.uc.reg_read(UC_MIPS_REG_CP0_STATUS) & 0xFFFFFFFF:08x}"
        return out

    def _bda_runtime_snapshot(self) -> dict[str, object]:
        def read_u32_safe(va: int) -> int | None:
            try:
                return self._read_mem_va(va, 4) & 0xFFFFFFFF
            except Exception:
                return None

        imports_base = 0x81C24030
        import_names = [
            ("resource_table", 0x00),
            ("gui_table", 0x04),
            ("secondary_table", 0x08),
            ("stream_table", 0x0C),
            ("memory_table", 0x10),
        ]
        imports: dict[str, str | None] = {}
        for name, off in import_names:
            value = read_u32_safe(imports_base + off)
            imports[name] = None if value is None else f"0x{value:08x}"

        gui_base = read_u32_safe(imports_base + 0x04) or 0
        gui_offsets = {
            "draw_root": 0x00,
            "draw_state": 0x40,
            "set_property": 0x50,
            "resource_bind": 0x94,
            "create_control": 0x1A4,
            "message_box": 0x2B8,
            "event_loop": 0x378,
        }
        gui_table: dict[str, str | None] = {}
        if gui_base:
            for name, off in gui_offsets.items():
                value = read_u32_safe(gui_base + off)
                gui_table[f"{name}+0x{off:x}"] = None if value is None else f"0x{value:08x}"

        return {
            "imports_base": f"0x{imports_base:08x}",
            "imports": imports,
            "gui_table_base": None if not gui_base else f"0x{gui_base:08x}",
            "gui_table": gui_table,
        }

    def _display_event_queue_snapshot(self, queue_va: int = 0x80825840) -> dict[str, object]:
        out: dict[str, object] = {"queue_va": f"0x{queue_va:08x}"}
        if not self._is_mapped_ram_va(queue_va, 0x20):
            out["mapped"] = False
            return out
        out["mapped"] = True
        words = [self._read_u32_va_safe(queue_va + off) for off in range(0, 0x20, 4)]
        out["words_00_1c"] = [None if word is None else f"0x{word:08x}" for word in words]
        buffer_va = words[4] or 0
        capacity = words[5] or 0
        read_index = words[6] or 0
        write_index = words[7] or 0
        out.update(
            {
                "buffer_va": f"0x{buffer_va:08x}",
                "capacity": capacity,
                "read_index": read_index,
                "write_index": write_index,
            }
        )
        entries = []
        max_entries = min(capacity, 16)
        if buffer_va and capacity and self._is_mapped_ram_va(buffer_va, max_entries * 0x1C):
            for idx in range(max_entries):
                entry_va = buffer_va + idx * 0x1C
                data = self._read_block_va_safe(entry_va, 0x1C)
                if data is None:
                    continue
                entry_words = [struct.unpack_from("<I", data, off)[0] for off in range(0, 0x1C, 4)]
                entries.append(
                    {
                        "index": idx,
                        "va": f"0x{entry_va:08x}",
                        "words": [f"0x{word:08x}" for word in entry_words],
                    }
                )
        out["entries"] = entries
        return out

    def mmio_snapshot(self) -> dict[str, object]:
        lcd_regs = {
            f"0x{addr:08x}": f"0x{value:x}"
            for addr, value in sorted(self.mmio_regs.items())
            if 0x10043000 <= addr < 0x10043100
        }
        blit_regs = {
            f"0x{addr:08x}": f"0x{value:x}"
            for addr, value in sorted(self.mmio_regs.items())
            if 0x10021000 <= addr < 0x10021100
        }
        gpio_regs = {
            f"0x{addr:08x}": f"0x{value:x}"
            for addr, value in sorted(self.mmio_regs.items())
            if 0x10010000 <= addr < 0x10010400
        }
        intc_regs = {
            f"0x{addr:08x}": f"0x{value:x}"
            for addr, value in sorted(self.mmio_regs.items())
            if 0x10001000 <= addr < 0x10001100
        }
        tcu_regs = {
            f"0x{addr:08x}": f"0x{value:x}"
            for addr, value in sorted(self.mmio_regs.items())
            if 0x10002000 <= addr < 0x10002100 or 0x10003000 <= addr < 0x10003100
        }
        sadc_regs = {
            f"0x{addr:08x}": f"0x{value:x}"
            for addr, value in sorted(self.mmio_regs.items())
            if SADC_BASE <= addr < SADC_BASE + 0x100
        }
        return {
            "lcd_regs": lcd_regs,
            "blit_regs": blit_regs,
            "gpio_regs": gpio_regs,
            "intc_regs": intc_regs,
            "tcu_regs": tcu_regs,
            "sadc_regs": sadc_regs,
            "touch_controller": {
                "x": self.touch_x,
                "y": self.touch_y,
                "down": self.touch_down,
                "controller_poll_hits": self.touch_controller_poll_hits,
                "next_axis": self.sadc_next_axis,
                "sadc_status_event": f"0x{self.sadc_status_event:02x}",
                "sadc_conversion_events_remaining": self.sadc_conversion_events_remaining,
                "raw_x": self._touch_adc_raw(0),
                "raw_y": self._touch_adc_raw(1),
            },
            "tcu": {
                "enabled_mask": f"0x{self.tcu_enabled_mask:08x}",
                "pending_mask": f"0x{self.tcu_pending_mask:08x}",
                "intc_pending_mask": f"0x{self.intc_pending_mask:08x}",
                "period_insn": self.tcu_period_insn,
                "next_irq_insn": self.next_tcu_irq_insn,
                "interrupt_return_pc": None if self.interrupt_return_pc is None else f"0x{self.interrupt_return_pc:08x}",
                "recent_deliveries": self.interrupt_deliveries[-64:],
            },
            "forced_read_levels": {f"0x{addr:08x}": f"0x{value:08x}" for addr, value in sorted(self.mmio_read_levels.items())},
            "scheduled_pulses": [
                {
                    "addr": f"0x{pulse.addr:08x}",
                    "value": f"0x{pulse.value:08x}",
                    "idle_hit": pulse.idle_hit,
                    "read_count": pulse.read_count,
                    "reads_seen": pulse.reads_seen,
                    "active": pulse.active,
                    "expired": pulse.expired,
                }
                for pulse in self.mmio_pulses
            ],
            "recent_pulse_events": self.mmio_pulse_events[-64:],
            "nand": {
                "image": None if self.nand_image is None else str(self.nand_image),
                "image_size": 0 if self.nand_data is None else len(self.nand_data),
                "page_size": self.nand_page_size,
                "spare_size": self.nand_spare_size,
                "readonly_page_ranges": [
                    [f"0x{start:x}", f"0x{end:x}"] for start, end in self.readonly_nand_page_ranges
                ],
                "cmd": f"0x{self.nand_cmd:02x}",
                "addr_bytes": [f"0x{b:02x}" for b in self.nand_addr_bytes],
                "read_index": self.nand_read_index,
                "data_window_read_count": self.nand_data_window_read_count,
                "loop_accel_count": self.nand_loop_accel_count,
                "recent_loop_events": self.nand_loop_events[-64:],
                "program_buffer_size": len(self.nand_program_buffer),
                "program_page": f"0x{self.nand_program_page:x}",
                "program_column": f"0x{self.nand_program_column:x}",
                "erase_count": self.nand_erase_count,
                "page_override_count": len(self.nand_page_overrides),
                "recent_erase_events": self.nand_erase_events[-64:],
                "recent_program_writes": self.nand_program_writes[-64:],
                "recent_reads": self.nand_reads[-64:],
                "recent_data_window_reads": self.nand_data_window_reads[-256:],
                "recent_latch_writes": self.nand_latch_writes[-256:],
            },
            "block_image": {
                "image": None if self.block_image is None else str(self.block_image),
                "image_size": 0 if self.block_data is None else len(self.block_data),
                "sector_override_count": len(self.block_sector_overrides),
                "recent_events": self.block_events[-64:],
            },
            "resource_cache16": {
                "enabled": self.resource_cache16_accelerator,
                "accel_count": self.resource_cache16_accel_count,
                "recent_events": self.resource_cache16_events[-64:],
            },
            "fat16_cluster_read": {
                "accel_count": self.cluster_read_accel_count,
                "layout": None
                if self.fat16_layout_cache is None
                else {key: f"0x{value:x}" for key, value in self.fat16_layout_cache.items()},
                "recent_events": self.cluster_read_events[-64:],
            },
            "dirent_copy": {
                "accel_count": self.dirent_copy_accel_count,
                "recent_events": self.dirent_copy_events[-64:],
            },
            "dirent_copy_accel_count": self.dirent_copy_accel_count,
            "logo_strip_blit_accel_count": self.logo_strip_blit_accel_count,
            "halfword_copy_accel_count": self.halfword_copy_accel_count,
            "surface": {
                "setpixel_accel_count": self.surface_setpixel_accel_count,
                "hline_accel_count": self.surface_hline_accel_count,
                "color_span_accel_count": self.surface_color_span_accel_count,
                "block_read_accel_count": self.surface_block_read_accel_count,
                "block_write_accel_count": self.surface_block_write_accel_count,
                "pixel_read_count": self.surface_pixel_read_count,
                "event_count": self.surface_event_count,
                "recent_events": self.surface_events[-128:],
                "recent_events_by_mode": {
                    mode: events[-32:] for mode, events in sorted(self.surface_events_by_mode.items())
                },
            },
            "surface_setpixel_accel_count": self.surface_setpixel_accel_count,
            "surface_hline_accel_count": self.surface_hline_accel_count,
            "surface_color_span_accel_count": self.surface_color_span_accel_count,
            "surface_block_read_accel_count": self.surface_block_read_accel_count,
            "surface_block_write_accel_count": self.surface_block_write_accel_count,
            "surface_pixel_read_count": self.surface_pixel_read_count,
            "free_scan_accel_count": self.free_scan_accel_count,
            "raster_loop_accel_count": self.raster_loop_accel_count,
            "glyph_mask_loop_accel_count": self.glyph_mask_loop_accel_count,
            "mmio_delay_branch_count": self.mmio_delay_branch_count,
            "recent_lcd_writes": self.lcd_writes[-64:],
            "display_globals": self._display_globals_snapshot(),
            "scheduler": self.scheduler_snapshot(),
            "tasks": self.task_table_snapshot(),
            "display_event_queue": self._display_event_queue_snapshot(),
            "recent_framebuffer_writes": self.framebuffer_writes[-128:],
            "recent_blit_events": self.blit_events[-64:],
            "bda_runtime": self._bda_runtime_snapshot(),
            "event_queue": self._queue_object_snapshot(self._read_u32_va_safe(0x80473F6C)),
            "recent_event_queue_snapshots": self.event_queue_snapshots[-64:],
            "recent_gui_touch_events": self.gui_touch_event_log[-64:],
            "recent_gui_ring_pump_events": self.gui_ring_pump_events[-64:],
            "recent_gpio_accesses": self.recent_gpio_accesses[-128:],
            "recent_intc_accesses": self.recent_intc_accesses[-128:],
            "recent_udc_accesses": self.recent_udc_accesses[-128:],
            "recent_sadc_accesses": self.recent_sadc_accesses[-128:],
            "idle_loop_hits": self.idle_loop_hits,
            "app_idle_loop_hits": self.app_idle_loop_hits,
        }

    def _display_globals_snapshot(self) -> dict[str, object]:
        def u32(va: int) -> str | None:
            value = self._read_u32_va_safe(va)
            return None if value is None else f"0x{value:08x}"

        addrs = {
            "display_desc_80474030": 0x80474030,
            "display_vtable_8047409c": 0x8047409C,
            "active_object_80474048": 0x80474048,
            "active_object_8047404c": 0x8047404C,
            "active_object_80474050": 0x80474050,
            "tick_80474058": 0x80474058,
            "lcd_width_8033c0b4": 0x8033C0B4,
            "lcd_height_8033c0b8": 0x8033C0B8,
            "lcd_bpp_8033c0bc": 0x8033C0BC,
            "lcd_buf0_8033c0e4": 0x8033C0E4,
            "lcd_buf1_8033c0e8": 0x8033C0E8,
            "draw_rect_80825810": 0x80825810,
            "draw_rect_80825814": 0x80825814,
            "draw_rect_80825818": 0x80825818,
            "draw_rect_8082581c": 0x8082581C,
            "ui_list_80825800": 0x80825800,
            "ui_list_80825804": 0x80825804,
            "ui_list_80825808": 0x80825808,
            "ui_list_80825820": 0x80825820,
            "ui_list_80825824": 0x80825824,
            "ui_list_80825828": 0x80825828,
            "draw_state_80825830": 0x80825830,
            "gui_queue_80825840": 0x80825840,
            "gui_callback_8082584c": 0x8082584C,
            "gui_ring_80825850": 0x80825850,
            "modal_804a65b0": 0x804A65B0,
            "modal_804a65b4": 0x804A65B4,
            "modal_804a65c0": 0x804A65C0,
            "modal_804a65c4": 0x804A65C4,
            "window_pool_804a65e8": 0x804A65E8,
            "window_pool_804a65f8": 0x804A65F8,
            "surface_804a60c0": 0x804A60C0,
        }
        out: dict[str, object] = {name: u32(va) for name, va in addrs.items()}
        display_desc = self._read_u32_va_safe(0x80474030)
        if display_desc is not None:
            display_surface = self._read_u32_va_safe(display_desc)
            out["display_surface_from_desc"] = None if display_surface is None else f"0x{display_surface:08x}"
        modal = self._read_u32_va_safe(0x804A65C0)
        if modal is not None:
            modal_surface = self._read_u32_va_safe(modal + 0x54)
            out["modal_surface_804a65c0_plus54"] = None if modal_surface is None else f"0x{modal_surface:08x}"
        fixed_blocks = {
            "surface_global_804a60c0_words": 0x804A60C0,
            "surface_global_804a6154_words": 0x804A6154,
            "surface_global_804a6170_words": 0x804A6170,
        }
        for fixed_name, fixed_va in fixed_blocks.items():
            if not self._is_mapped_ram_va(fixed_va, 0x80):
                continue
            data = self._read_block_va_safe(fixed_va, 0x80)
            if data is None:
                continue
            words = [struct.unpack_from("<I", data, i)[0] for i in range(0, 0x80, 4)]
            out[fixed_name] = [f"0x{word:08x}" for word in words]
        for name in (
            "display_desc_80474030",
            "display_surface_from_desc",
            "active_object_80474048",
            "active_object_8047404c",
            "active_object_80474050",
            "ui_list_80825800",
            "ui_list_80825808",
            "ui_list_80825820",
            "ui_list_80825828",
            "draw_state_80825830",
            "gui_queue_80825840",
            "modal_804a65b0",
            "modal_804a65c0",
            "modal_surface_804a65c0_plus54",
            "window_pool_804a65f8",
            "surface_804a60c0",
        ):
            value_s = out.get(name)
            if not isinstance(value_s, str):
                continue
            va = int(value_s, 16)
            if not self._is_mapped_ram_va(va, 0x60):
                continue
            data = self._read_block_va_safe(va, 0x60)
            if data is None:
                continue
            words = [struct.unpack_from("<I", data, i)[0] for i in range(0, 0x60, 4)]
            out[f"{name}_words"] = [f"0x{word:08x}" for word in words]
        return out

    def uart_snapshot(self) -> dict[str, object]:
        text = bytes(self.uart_bytes).decode("ascii", errors="replace")
        return {
            "bytes": len(self.uart_bytes),
            "text": text,
            "recent_writes": self.uart_writes[-64:],
        }

    def watch_snapshot(self) -> dict[str, object]:
        ranges = []
        for watch in self.watch_ranges:
            try:
                data = bytes(self.uc.mem_read(watch.phys, watch.size))
                hex_dump = data.hex()
            except Exception as exc:
                hex_dump = f"{type(exc).__name__}: {exc}"
            ranges.append(
                {
                    "name": watch.name,
                    "va": f"0x{watch.va:08x}",
                    "phys": f"0x{watch.phys:08x}",
                    "size": watch.size,
                    "final_hex": hex_dump,
                    "recent_accesses": watch.accesses[-256:],
                }
            )
        return {
            "ranges": ranges,
            "recent_accesses": self.watch_accesses[-256:],
            "pokes": [
                {
                    "va": f"0x{poke.va:08x}",
                    "phys": f"0x{poke.phys:08x}",
                    "size": poke.size,
                    "value": f"0x{poke.value:x}",
                    "idle_hit": poke.idle_hit,
                    "applied": poke.applied,
                }
                for poke in self.scheduled_pokes
            ],
            "poke_events": self.poke_events,
            "calls": [
                {
                    "target": f"0x{call.va:08x}",
                    "args": [f"0x{arg & 0xFFFFFFFF:08x}" for arg in call.args],
                    "idle_hit": call.idle_hit,
                    "return_pc": f"0x{call.return_pc:08x}",
                    "applied": call.applied,
                    "returned": call.returned,
                }
                for call in self.scheduled_calls
            ],
            "call_events": self.call_events,
            "firmware_key_samples": [
                {
                    "code": sample.code,
                    "idle_hit": sample.idle_hit,
                    "applied": sample.applied,
                    "returned": sample.returned,
                }
                for sample in self.firmware_key_samples
            ],
            "firmware_key_events": self.firmware_key_events,
            "touch_samples": [
                {
                    "x": sample.x,
                    "y": sample.y,
                    "down": int(sample.down),
                    "idle_hit": sample.idle_hit,
                    "pc_hit": None if sample.pc_hit is None else f"0x{sample.pc_hit:08x}",
                    "applied": sample.applied,
                    "returned": sample.returned,
                }
                for sample in self.touch_samples
            ],
            "touch_sample_events": self.touch_sample_events,
            "touch_controller_events": [
                {
                    "x": event.x,
                    "y": event.y,
                    "down": int(event.down),
                    "idle_hit": event.idle_hit,
                    "controller_poll_hit": event.idle_hit,
                    "applied": event.applied,
                }
                for event in self.touch_controller_events
            ],
            "touch_controller_event_log": self.touch_controller_event_log,
            "bda_launches": [
                {
                    "path": str(launch.path),
                    "idle_hit": launch.idle_hit,
                    "applied": launch.applied,
                    "returned": launch.returned,
                    "entry_offset": None if launch.entry_offset is None else f"0x{launch.entry_offset:x}",
                    "loaded_size": f"0x{launch.loaded_size:x}",
                }
                for launch in self.bda_launches
            ],
            "bda_launch_events": self.bda_launch_events,
            "gui_key_events": [
                {
                    "code": event.code,
                    "idle_hit": event.idle_hit,
                    "applied": event.applied,
                }
                for event in self.gui_key_events
            ],
            "gui_key_event_log": self.gui_key_event_log,
            "bda_event_poll_hits": self.bda_event_poll_hits,
            "bda_idle_empty_polls": self.bda_idle_empty_polls,
            "bda_idle_stop_polls": self.bda_idle_stop_polls,
            "bda_key_events": [
                {
                    "code": event.code,
                    "event_type": event.event_type,
                    "event_hit": event.event_hit,
                    "applied": event.applied,
                }
                for event in self.bda_key_events
            ],
            "bda_key_event_log": self.bda_key_event_log,
            "bda_events": [
                {
                    "event_type": event.event_type,
                    "event_hit": event.event_hit,
                    "word0": f"0x{event.word0 & 0xFFFFFFFF:08x}",
                    "word2": f"0x{event.word2 & 0xFFFFFFFF:08x}",
                    "word3": f"0x{event.word3 & 0xFFFFFFFF:08x}",
                    "applied": event.applied,
                }
                for event in self.bda_events
            ],
            "bda_event_log": self.bda_event_log,
            "bda_touch_events": [
                {
                    "x": event.x,
                    "y": event.y,
                    "down": int(event.down),
                    "event_type": event.event_type,
                    "event_hit": event.event_hit,
                    "applied": event.applied,
                }
                for event in self.bda_touch_events
            ],
            "bda_touch_event_log": self.bda_touch_event_log,
            "trace_pc": {
                "counts": {f"0x{pc:08x}": count for pc, count in sorted(self.trace_pc_counts.items())},
                "recent_hits": self.trace_pc_hits[-128:],
            },
        }

    def scheduler_snapshot(self) -> dict[str, object]:
        def read_u8(va: int) -> int | None:
            try:
                return self._read_mem_va(va, 1) & 0xFF
            except Exception:
                return None

        def read_u32(va: int) -> int | None:
            try:
                return self._read_mem_va(va, 4) & 0xFFFFFFFF
            except Exception:
                return None

        fields = {
            "tick_count_3f0c": (0x80473F0C, 4),
            "run_enabled_3f09": (0x80473F09, 1),
            "timer_countdown_3f08": (0x80473F08, 1),
            "current_task_id_3f10": (0x80473F10, 1),
            "last_task_id_3f11": (0x80473F11, 1),
            "active_node_3f30": (0x80473F30, 4),
            "current_node_3f50": (0x80473F50, 4),
            "dispatch_delay_3f4d": (0x80473F4D, 1),
            "frame_tick_base_3f20": (0x80473F20, 4),
            "pending_node_count_3f1c": (0x80473F1C, 4),
            "fps_ready_3f5c": (0x80473F5C, 1),
            "ticks_last_frame_3f60": (0x80473F60, 4),
        }
        values: dict[str, str | None] = {}
        for name, (va, size) in fields.items():
            value = read_u8(va) if size == 1 else read_u32(va)
            values[name] = None if value is None else f"0x{value:0{size * 2}x}"
        raw = self._read_block_va_safe(0x80473F00, 0x80)
        return {
            "wait_wake_count": self.wait_wake_count,
            "timer_tick_count": self.timer_tick_count,
            "scheduler_poll_count": self.scheduler_poll_count,
            "scheduler_dispatch_count": self.scheduler_dispatch_count,
            "tick_clamp_enabled": self.scheduler_tick_clamp,
            "fields": values,
            "raw_80473f00_7f": None if raw is None else raw.hex(),
        }

    def input_snapshot(self) -> dict[str, object]:
        def read_u32(va: int) -> int:
            return self._read_mem_va(va, 4) & 0xFFFFFFFF

        def read_block(va: int, size: int) -> bytes:
            phys = va_to_phys(va)
            return bytes(self.uc.mem_read(phys, size))

        out: dict[str, object] = {}
        try:
            state = read_block(0x80473F40, 0x80)
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

        globals_to_watch = {
            "touch_prev_x_80370fc0": 0x80370FC0,
            "touch_prev_y_80370fc4": 0x80370FC4,
            "key_down_flag_8048dd0c": 0x8048DD0C,
            "last_key_code_8048dd10": 0x8048DD10,
            "key_aux_8048dd14": 0x8048DD14,
            "touch_flag_8048dd00": 0x8048DD00,
            "touch_flag_8048dd04": 0x8048DD04,
            "touch_flag_8048dd08": 0x8048DD08,
            "release_state_80370fd0": 0x80370FD0,
            "touch_x_80370fc8": 0x80370FC8,
            "touch_y_80370fcc": 0x80370FCC,
            "touch_aux_80370fd4": 0x80370FD4,
        }
        out["input_globals"] = {
            name: f"0x{read_u32(va):08x}" for name, va in globals_to_watch.items()
        }

        words = [int.from_bytes(state[i : i + 4], "little") for i in range(0, len(state), 4)]
        out["state_va"] = "0x80473f40"
        out["state_words"] = [f"0x{word:08x}" for word in words]
        out["state_bytes"] = state.hex()
        ptrs = []
        for idx, word in enumerate(words):
            if 0x806C0000 <= word < 0x80700000:
                ptrs.append({"offset": f"0x{idx * 4:02x}", "value": f"0x{word:08x}"})
        out["state_pointers"] = ptrs

        nodes = []
        seen: set[int] = set()
        for item in ptrs:
            va = int(item["value"], 16)
            if va in seen:
                continue
            seen.add(va)
            try:
                data = read_block(va, 0x70)
            except Exception:
                continue
            node_words = [int.from_bytes(data[i : i + 4], "little") for i in range(0, 0x30, 4)]
            nodes.append(
                {
                    "va": f"0x{va:08x}",
                    "words_00_2c": [f"0x{word:08x}" for word in node_words],
                    "bytes_30_3f": data[0x30:0x40].hex(),
                    "links_18_1c_20_24": [
                        f"0x{int.from_bytes(data[i:i+4], 'little'):08x}" for i in (0x18, 0x1C, 0x20, 0x24)
                    ],
                    "callback_00": f"0x{int.from_bytes(data[0:4], 'little'):08x}",
                }
            )
        out["pointed_nodes"] = nodes

        try:
            table = read_block(0x806C5D10, 0x100)
            entries = []
            for idx in range(0x40):
                value = int.from_bytes(table[idx * 4 : idx * 4 + 4], "little")
                if value:
                    entries.append({"index": idx, "value": f"0x{value:08x}"})
            out["key_table_va"] = "0x806c5d10"
            out["key_table_nonzero"] = entries
        except Exception as exc:
            out["key_table_error"] = f"{type(exc).__name__}: {exc}"
        return out


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


def parse_firmware_key_sample(text: str) -> FirmwareKeySample:
    if "@" not in text:
        raise argparse.ArgumentTypeError("firmware key sample must be code@idle_hit")
    code_s, hit_s = text.split("@", 1)
    code = int(code_s, 0)
    idle_hit = int(hit_s, 0)
    if not 0 <= code <= 0xFF:
        raise argparse.ArgumentTypeError("firmware key code must fit in one byte")
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("idle_hit must be positive")
    return FirmwareKeySample(code=code, idle_hit=idle_hit)


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


def parse_bda_launch(text: str) -> ScheduledBdaLaunch:
    spec = text
    idle_hit = 1
    if "@" in spec:
        spec, hit_s = spec.rsplit("@", 1)
        idle_hit = int(hit_s, 0)
    path = Path(spec)
    if idle_hit <= 0:
        raise argparse.ArgumentTypeError("idle_hit must be positive")
    return ScheduledBdaLaunch(path=path, idle_hit=idle_hit)


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


def parse_bda_key_event(text: str) -> ScheduledBdaKeyEvent:
    if "@" not in text:
        raise argparse.ArgumentTypeError("BDA key event must be code[:event_type]@event_hit")
    body, hit_s = text.split("@", 1)
    parts = body.split(":")
    if not 1 <= len(parts) <= 2:
        raise argparse.ArgumentTypeError("BDA key event must be code[:event_type]@event_hit")
    code = int(parts[0], 0)
    event_type = int(parts[1], 0) if len(parts) == 2 else 9
    event_hit = int(hit_s, 0)
    if not 0 <= code <= 0xFF:
        raise argparse.ArgumentTypeError("BDA key code must fit in one byte")
    if not 0 <= event_type <= 0xFF:
        raise argparse.ArgumentTypeError("BDA event type must fit in one byte")
    if event_hit <= 0:
        raise argparse.ArgumentTypeError("event_hit must be positive")
    return ScheduledBdaKeyEvent(code=code, event_hit=event_hit, event_type=event_type)


def parse_bda_event(text: str) -> ScheduledBdaEvent:
    if "@" not in text:
        raise argparse.ArgumentTypeError("BDA event must be event_type[:word0[:word2[:word3]]]@event_hit")
    body, hit_s = text.split("@", 1)
    parts = body.split(":")
    if not 1 <= len(parts) <= 4:
        raise argparse.ArgumentTypeError("BDA event must be event_type[:word0[:word2[:word3]]]@event_hit")
    event_type = int(parts[0], 0)
    words = [0, 0, 0]
    for idx, value_s in enumerate(parts[1:]):
        words[idx] = int(value_s, 0)
    event_hit = int(hit_s, 0)
    if not 0 <= event_type <= 0xFF:
        raise argparse.ArgumentTypeError("BDA event type must fit in one byte")
    if event_hit <= 0:
        raise argparse.ArgumentTypeError("event_hit must be positive")
    return ScheduledBdaEvent(
        event_type=event_type,
        word0=words[0],
        word2=words[1],
        word3=words[2],
        event_hit=event_hit,
    )


def parse_bda_touch_event(text: str) -> ScheduledBdaTouchEvent:
    if "@" not in text:
        raise argparse.ArgumentTypeError("BDA touch event must be x:y:down[:event_type]@event_hit")
    body, hit_s = text.split("@", 1)
    parts = body.split(":")
    if not 3 <= len(parts) <= 4:
        raise argparse.ArgumentTypeError("BDA touch event must be x:y:down[:event_type]@event_hit")
    x = int(parts[0], 0)
    y = int(parts[1], 0)
    down = bool(int(parts[2], 0))
    event_type = int(parts[3], 0) if len(parts) == 4 else (4 if down else 5)
    event_hit = int(hit_s, 0)
    if not (0 <= x < 240 and 0 <= y < 320):
        raise argparse.ArgumentTypeError("BDA touch coordinates must be inside 240x320 portrait screen")
    if not 0 <= event_type <= 0xFF:
        raise argparse.ArgumentTypeError("BDA touch event type must fit in one byte")
    if event_hit <= 0:
        raise argparse.ArgumentTypeError("event_hit must be positive")
    return ScheduledBdaTouchEvent(x=x, y=y, down=down, event_type=event_type, event_hit=event_hit)


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


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def write_rgb_png(path: Path, width: int, height: int, rgb: bytes) -> None:
    if len(rgb) != width * height * 3:
        raise ValueError("RGB buffer size does not match output dimensions")
    rows = bytearray()
    row_size = width * 3
    for y in range(height):
        rows.append(0)
        start = y * row_size
        rows.extend(rgb[start : start + row_size])
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def write_rgb_ppm(path: Path, width: int, height: int, rgb: bytes) -> None:
    if len(rgb) != width * height * 3:
        raise ValueError("RGB buffer size does not match output dimensions")
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode("ascii") + rgb)


def orient_rgb(
    rgb: bytes,
    width: int,
    height: int,
    orientation: str,
) -> tuple[int, int, bytes]:
    if orientation == "raw":
        return width, height, rgb
    if orientation not in {"rot180", "cw90", "ccw90", "hflip", "vflip"}:
        raise ValueError(f"unsupported framebuffer orientation: {orientation}")

    src = memoryview(rgb)
    if orientation in {"rot180", "hflip", "vflip"}:
        out = bytearray(width * height * 3)
        for y in range(height):
            for x in range(width):
                if orientation == "rot180":
                    src_x = width - 1 - x
                    src_y = height - 1 - y
                elif orientation == "hflip":
                    src_x = width - 1 - x
                    src_y = y
                else:
                    src_x = x
                    src_y = height - 1 - y
                src_i = (src_y * width + src_x) * 3
                dst_i = (y * width + x) * 3
                out[dst_i : dst_i + 3] = src[src_i : src_i + 3]
        return width, height, bytes(out)

    out_w = height
    out_h = width
    out = bytearray(out_w * out_h * 3)
    for y in range(out_h):
        for x in range(out_w):
            if orientation == "cw90":
                src_x = y
                src_y = height - 1 - x
            else:
                src_x = width - 1 - y
                src_y = x
            src_i = (src_y * width + src_x) * 3
            dst_i = (y * out_w + x) * 3
            out[dst_i : dst_i + 3] = src[src_i : src_i + 3]
    return out_w, out_h, bytes(out)


def dump_rgb565_framebuffer(
    emu: Bbk9588HwEmu,
    path: Path,
    addr: int,
    offset_bytes: int,
    width: int,
    height: int,
    stride_pixels: int,
    pixel_format: str,
    orientation: str,
) -> dict[str, object]:
    if width <= 0 or height <= 0 or stride_pixels < width or offset_bytes < 0:
        raise ValueError("invalid framebuffer dimensions")
    if pixel_format not in {"rgb565", "bgr565", "rgb565-be", "bgr565-be"}:
        raise ValueError(f"unsupported framebuffer format: {pixel_format}")

    phys = (addr & 0x1FFFFFFF if addr >= RAM_BASE else addr) + offset_bytes
    raw = bytes(emu.uc.mem_read(phys, stride_pixels * height * 2))
    rgb = bytearray(width * height * 3)
    nonzero = 0
    unique: set[int] = set()
    min_x = width
    min_y = height
    max_x = -1
    max_y = -1

    out_i = 0
    for y in range(height):
        row = y * stride_pixels * 2
        for x in range(width):
            i = row + x * 2
            if pixel_format.endswith("-be"):
                px = (raw[i] << 8) | raw[i + 1]
            else:
                px = raw[i] | (raw[i + 1] << 8)
            unique.add(px)
            if px:
                nonzero += 1
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
            r = ((px >> 11) & 0x1F) * 255 // 31
            g = ((px >> 5) & 0x3F) * 255 // 63
            b = (px & 0x1F) * 255 // 31
            if pixel_format.startswith("bgr"):
                r, b = b, r
            rgb[out_i] = r
            rgb[out_i + 1] = g
            rgb[out_i + 2] = b
            out_i += 3

    out_width, out_height, out_rgb = orient_rgb(bytes(rgb), width, height, orientation)

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".png":
        write_rgb_png(path, out_width, out_height, out_rgb)
    else:
        write_rgb_ppm(path, out_width, out_height, out_rgb)

    bbox = None if max_x < 0 else [min_x, min_y, max_x, max_y]
    return {
        "path": str(path),
        "addr": f"0x{addr:08x}",
        "offset_bytes": offset_bytes,
        "format": pixel_format,
        "width": width,
        "height": height,
        "stride_pixels": stride_pixels,
        "orientation": orientation,
        "output_width": out_width,
        "output_height": out_height,
        "nonzero_pixels": nonzero,
        "unique_pixel_values": len(unique),
        "nonzero_bbox": bbox,
    }


def scan_rgb565_framebuffers(
    emu: Bbk9588HwEmu,
    width: int,
    height: int,
    stride_pixels: int,
    topn: int = 16,
) -> list[dict[str, object]]:
    row_bytes = stride_pixels * 2
    window_bytes = row_bytes * height
    ranges = [
        (0x00400000, 0x00A00000),
        (0x01F00000, 0x02080000),
    ]
    candidates: list[dict[str, object]] = []
    for start, end in ranges:
        last = min(end, emu.ram_size) - window_bytes
        if last <= start:
            continue
        for phys in range(start, last + 1, 0x1000):
            try:
                data = bytes(emu.uc.mem_read(phys, window_bytes))
            except Exception:
                continue
            nonzero = 0
            unique: set[int] = set()
            for off in range(0, len(data), 2):
                value = data[off] | (data[off + 1] << 8)
                if value:
                    nonzero += 1
                    if len(unique) < 256:
                        unique.add(value)
            if nonzero == 0:
                continue
            candidates.append(
                {
                    "phys": f"0x{phys:08x}",
                    "kseg0": f"0x{phys | 0x80000000:08x}",
                    "kseg1": f"0x{phys | 0xA0000000:08x}",
                    "nonzero_pixels": nonzero,
                    "unique_sample": len(unique),
                }
            )
    candidates.sort(key=lambda row: (int(row["nonzero_pixels"]), int(row["unique_sample"])), reverse=True)
    return candidates[:topn]


def cli_option_provided(argv: list[str], option: str) -> bool:
    return any(arg == option or arg.startswith(option + "=") for arg in argv)


def find_workspace_file(name: str) -> Path:
    matches = sorted(path for path in Path(".").rglob(name) if path.is_file())
    if not matches:
        raise FileNotFoundError(f"could not find {name!r} under current workspace")
    return matches[0]


def apply_preset(ns: argparse.Namespace, argv: list[str]) -> None:
    if ns.preset is None:
        return
    if ns.preset != "direct-bda-msgbox":
        raise ValueError(f"unknown preset: {ns.preset}")

    if not cli_option_provided(argv, "--image"):
        ns.image = find_workspace_file("u_boot_9588_4740.bin")
    if not cli_option_provided(argv, "--base"):
        ns.base = 0x80900000
    if not cli_option_provided(argv, "--pc"):
        ns.pc = 0x80900000
    if not cli_option_provided(argv, "--ram-mb"):
        ns.ram_mb = 160
    if not cli_option_provided(argv, "--profile"):
        ns.profile = "bbk9588-uboot"
    if not cli_option_provided(argv, "--payload"):
        ns.payload = find_workspace_file("C200.bin")
    if not cli_option_provided(argv, "--payload-addr"):
        ns.payload_addr = 0x80004000
    if not cli_option_provided(argv, "--nand-image"):
        ns.nand_image = ns.payload
    if getattr(ns, "no_block_image", False):
        ns.block_image = None
    elif not cli_option_provided(argv, "--block-image"):
        ns.block_image = Path("build") / "bbk9588_fs_fat16.img"
    if not cli_option_provided(argv, "--steps"):
        ns.steps = 27_000_000
    if not cli_option_provided(argv, "--trace-limit"):
        ns.trace_limit = 6200
    if not cli_option_provided(argv, "--idle-stop-hits"):
        ns.idle_stop_hits = 0
    if not cli_option_provided(argv, "--app-idle-stop-hits"):
        ns.app_idle_stop_hits = 0
    if not cli_option_provided(argv, "--fb-addr"):
        ns.fb_addr = 0xA1F82000
    if not cli_option_provided(argv, "--fb-width"):
        ns.fb_width = 240
    if not cli_option_provided(argv, "--fb-height"):
        ns.fb_height = 320
    if ns.bda_text_mode == "native" and not cli_option_provided(argv, "--bda-native-glyph-layout"):
        ns.bda_native_glyph_layout = "rows-lsb-vscale2"
    if not cli_option_provided(argv, "--fb-orientation"):
        ns.fb_orientation = "hflip" if ns.bda_text_mode == "native" else "rot180"
    if not ns.launch_bda:
        ns.launch_bda.append(parse_bda_launch(str(Path("build") / "calc_startup_msgbox_origtitle.bda") + "@2"))

    for spec in ("surfglobal=0x804a60c0:0x140", "shadow=0x80825b90:0x25800"):
        watch = parse_watch_range(spec)
        if all(existing.name != watch.name for existing in ns.watch_va):
            ns.watch_va.append(watch)

    for pc in (0x8012A6A8, 0x80119B50, 0x80119C90, 0x80119CC0, 0x8011A3C4, 0x8011AA1C, 0x8012C90C):
        if pc not in ns.trace_pc:
            ns.trace_pc.append(pc)

    if ns.out_prefix is not None:
        if ns.json_out is None:
            ns.json_out = ns.out_prefix.with_suffix(".json")
        if ns.fb_dump is None:
            ns.fb_dump = ns.out_prefix.with_suffix(".png")
    else:
        if ns.json_out is None:
            ns.json_out = Path("build") / "hwemu_direct_bda_msgbox.json"
        if ns.fb_dump is None:
            ns.fb_dump = Path("build") / "hwemu_direct_bda_msgbox.png"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Trace-run BBK 9588 raw MIPS system images.")
    ap.add_argument(
        "--preset",
        choices=["direct-bda-msgbox"],
        help="Apply a known BBK9588 regression preset while allowing explicit CLI arguments to override it.",
    )
    ap.add_argument("--out-prefix", type=Path, help="Set default JSON/framebuffer outputs for a preset.")
    ap.add_argument("--image", type=Path, default=Path("系统") / "数据" / "C200.bin")
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0x80000000)
    ap.add_argument("--pc", type=lambda x: int(x, 0), default=0x80000000)
    ap.add_argument("--ram-mb", type=int, default=32)
    ap.add_argument("--steps", type=int, default=100000)
    ap.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Stop execution after this many wall-clock seconds and still write the debug report.",
    )
    ap.add_argument("--trace-limit", type=int, default=256)
    ap.add_argument("--disasm-count", type=int, default=24)
    ap.add_argument("--no-recover-jr", action="store_true", help="Disable Unicorn jr-exception recovery.")
    ap.add_argument("--profile", default="none", choices=["none", "bbk9588-uboot"])
    ap.add_argument("--payload", type=Path, help="Optional second-stage image to pre-load into RAM.")
    ap.add_argument("--payload-addr", type=lambda x: int(x, 0), default=0x80004000)
    ap.add_argument("--nand-image", type=Path, help="Optional raw NAND image backing the external NAND data window.")
    ap.add_argument("--nand-page-size", type=int, default=2048)
    ap.add_argument("--nand-spare-size", type=int, default=64)
    ap.add_argument(
        "--readonly-nand-page-range",
        type=parse_page_range,
        action="append",
        default=[],
        help="Skip NAND program commits for a half-open page range start:end. Repeatable.",
    )
    ap.add_argument(
        "--clear-nand-overrides-page-range",
        type=parse_page_range,
        action="append",
        default=[],
        help="After loading a checkpoint, drop NAND page overrides in a half-open page range start:end. Repeatable.",
    )
    ap.add_argument(
        "--block-image",
        type=Path,
        help="Optional logical block device image served through C200's 0x80182bf4 read path.",
    )
    ap.add_argument(
        "--no-block-image",
        action="store_true",
        help="Disable the temporary C200 logical block-device hook and use the NAND/FTL path only.",
    )
    ap.add_argument(
        "--usb-connected",
        action="store_true",
        help="Model USB cable connected. Default is disconnected, so UDC status/interrupt reads stay idle.",
    )
    ap.add_argument(
        "--idle-stop-hits",
        type=int,
        default=256,
        help="Stop after this many hits at the C200 idle loop. Use 0 to disable.",
    )
    ap.add_argument(
        "--app-idle-stop-hits",
        type=int,
        default=0,
        help="Stop after this many hits at the observed app repaint loop at 0x800bd840. Use 0 to disable.",
    )
    ap.add_argument(
        "--bda-idle-stop-polls",
        type=int,
        default=1,
        help="Stop direct-BDA execution after this many empty BDA event polls once no scheduled BDA events remain.",
    )
    ap.add_argument(
        "--watch-va",
        type=parse_watch_range,
        action="append",
        default=[],
        help="Trace RAM reads/writes in a VA range, format addr:size or name=addr:size. Repeatable.",
    )
    ap.add_argument(
        "--trace-pc",
        type=lambda x: int(x, 0),
        action="append",
        default=[],
        help="Count and snapshot register state when execution reaches this virtual PC. Repeatable.",
    )
    ap.add_argument(
        "--stop-pc",
        type=lambda x: int(x, 0),
        action="append",
        default=[],
        help="Stop execution when this virtual PC is reached. Repeatable.",
    )
    ap.add_argument(
        "--watch-input-state",
        action="store_true",
        help="Trace the observed C200 GUI/input state block at 0x80473f40.",
    )
    ap.add_argument(
        "--watch-input-nodes",
        action="store_true",
        help="Trace the observed C200 GUI/input node pool around 0x806c5000.",
    )
    ap.add_argument(
        "--poke-va",
        type=parse_scheduled_poke,
        action="append",
        default=[],
        help="Write RAM at an idle-loop hit, format addr:size:value[@idle_hit]. Repeatable.",
    )
    ap.add_argument(
        "--call-va",
        type=parse_scheduled_call,
        action="append",
        default=[],
        help="Call firmware code at an idle-loop hit, format addr[:a0[:a1[:a2[:a3]]]][@idle_hit]. Experimental.",
    )
    ap.add_argument(
        "--call-stack",
        type=lambda x: int(x, 0),
        default=None,
        help="Scratch stack pointer used by --call-va. Defaults near the top of emulated RAM.",
    )
    ap.add_argument(
        "--fw-key-sample",
        type=parse_firmware_key_sample,
        action="append",
        default=[],
        help=(
            "Run C200's key sampler at an idle-loop hit and force the next "
            "0x8001b464 scanner result, format code@idle_hit. Use code 0 for release."
        ),
    )
    ap.add_argument(
        "--touch-sample",
        type=parse_touch_sample,
        action="append",
        default=[],
        help=(
            "Run C200's touch sampler at an idle-loop hit and force pen state/coords, "
            "format x:y:down@idle_hit or x:y:down@pc:addr on the 240x320 portrait screen."
        ),
    )
    ap.add_argument(
        "--touch-state",
        type=parse_touch_state,
        action="append",
        default=[],
        help="Set the current emulated touch controller state before running, format x:y:down.",
    )
    ap.add_argument(
        "--touch-controller-event",
        type=parse_touch_controller_event,
        action="append",
        default=[],
        help="Set emulated touch controller state at an idle-loop hit, format x:y:down@idle_hit.",
    )
    ap.add_argument(
        "--launch-bda",
        type=parse_bda_launch,
        action="append",
        default=[],
        help=(
            "Load a native BDA tail to 0x81c00020 and jump to it at an idle-loop hit, "
            "format path[@idle_hit]. Diagnostic path toward full app launching."
        ),
    )
    ap.add_argument(
        "--gui-key-event",
        type=parse_gui_key_event,
        action="append",
        default=[],
        help=(
            "Mark the C200 GUI key-table node for a key code as pending at an "
            "idle-loop hit, format code@idle_hit. Experimental."
        ),
    )
    ap.add_argument(
        "--gui-touch-event",
        type=parse_gui_touch_event,
        action="append",
        default=[],
        help=(
            "Send a screen-coordinate touch event to the current C200 active GUI object, "
            "format x:y:down@idle_hit. Use with --gui-ring-pump for modal follow-up events."
        ),
    )
    ap.add_argument(
        "--gui-ring-pump",
        action="store_true",
        help="Consume pending C200 GUI ring records at idle through the firmware 0x800dd4b8 dispatcher.",
    )
    ap.add_argument(
        "--bda-key-event",
        type=parse_bda_key_event,
        action="append",
        default=[],
        help=(
            "Inject a key-like event into the direct-BDA event loop, "
            "format code[:event_type]@event_hit. Event type 9 is key down; 10 is key up."
        ),
    )
    ap.add_argument(
        "--bda-event",
        type=parse_bda_event,
        action="append",
        default=[],
        help=(
            "Inject a raw event into the direct-BDA event loop, "
            "format event_type[:word0[:word2[:word3]]]@event_hit."
        ),
    )
    ap.add_argument(
        "--bda-touch-event",
        type=parse_bda_touch_event,
        action="append",
        default=[],
        help=(
            "Inject a touch event into the direct-BDA event loop and seed touch globals, "
            "format x:y:down[:event_type]@event_hit. Defaults: down -> type 4, up -> type 5."
        ),
    )
    ap.add_argument(
        "--gpio-level",
        type=parse_mmio_level,
        action="append",
        default=[],
        help="Force an MMIO read register value, format addr:value. Useful for GPIO/INTC input experiments.",
    )
    ap.add_argument(
        "--gpio-pulse",
        type=parse_mmio_pulse,
        action="append",
        default=[],
        help="Force an MMIO read register for a limited number of reads, format addr:value@idle_hit[:reads].",
    )
    ap.add_argument(
        "--key-pulse",
        type=parse_key_pulse,
        action="append",
        default=[],
        help="Inject a known active-low key scanner code, format code@idle_hit[:reads]. Known codes: 4,5,6,7,9,10.",
    )
    ap.add_argument("--fb-dump", type=Path, help="Dump RGB565 framebuffer after execution (.png or .ppm).")
    ap.add_argument("--fb-addr", type=lambda x: int(x, 0), default=0xA1F82000)
    ap.add_argument("--fb-offset-bytes", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--fb-width", type=int, default=240)
    ap.add_argument("--fb-height", type=int, default=320)
    ap.add_argument("--fb-stride-pixels", type=int, default=240)
    ap.add_argument("--fb-scan", action="store_true", help="Scan RAM for likely RGB565 framebuffer windows.")
    ap.add_argument(
        "--fb-format",
        default="rgb565",
        choices=["rgb565", "bgr565", "rgb565-be", "bgr565-be"],
        help="Framebuffer pixel interpretation.",
    )
    ap.add_argument(
        "--fb-orientation",
        default="rot180",
        choices=["raw", "rot180", "cw90", "ccw90", "hflip", "vflip"],
        help="Display orientation applied to framebuffer dump.",
    )
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--state-in", type=Path, help="Load a compressed emulator RAM/register checkpoint before running.")
    ap.add_argument("--state-out", type=Path, help="Save a compressed emulator RAM/register checkpoint after running.")
    ap.add_argument("--quiet", action="store_true", help="Do not print the full JSON report to stdout.")
    ap.add_argument(
        "--bda-text-mode",
        default="ascii-hook",
        choices=["ascii-hook", "native"],
        help="Direct-BDA text handling. ascii-hook is temporary visible ASCII rendering; native leaves firmware font code alone.",
    )
    ap.add_argument(
        "--bda-native-glyph-layout",
        default="rows-msb-vscale2",
        choices=[
            "rows-msb-vscale2",
            "rows-lsb-vscale2",
            "rows-msb-vscale2-y0",
            "rows-lsb-vscale2-y0",
            "rows-msb-vscale2-x3",
            "rows-msb-vscale2-hscale2",
            "rows-lsb-vscale2-hscale2",
            "cols-msb-vscale2",
            "cols-lsb-vscale2",
            "cols-msb-vscale2-hscale2",
            "cols-lsb-vscale2-hscale2",
        ],
        help="ASCII glyph buffer packing used only when native text recovery synthesizes missing font glyphs.",
    )
    ap.add_argument(
        "--bda-native-raster-mode",
        default="firmware",
        choices=["firmware", "synth"],
        help="Native text raster handling. firmware runs C200's raster routine; synth is an experimental direct model for ASCII glyphs.",
    )
    ap.add_argument(
        "--scheduler-tick-clamp",
        action="store_true",
        help=(
            "Clamp the C200 scheduler pending-tick byte at 0x80473f08 before "
            "polling. This models timer-pending consumption while the exact "
            "interrupt cadence is still incomplete."
        ),
    )
    ap.add_argument(
        "--fast-hooks",
        action="store_true",
        help=(
            "Use targeted code hooks instead of per-instruction tracing. Much "
            "faster for system boot/menu work, but insn_count and last_pcs are coarse."
        ),
    )
    ap.add_argument(
        "--fast-hook-image-jals",
        action="store_true",
        help="With --fast-hooks, also hook every jal in the loaded image for exact Unicorn branch-exception recovery.",
    )
    ap.add_argument(
        "--fast-hook-image-branches",
        action="store_true",
        help="With --fast-hooks, save pre-instruction register snapshots for recoverable branch/CP0/cache exception PCs.",
    )
    ap.add_argument(
        "--nand-loop-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: collapse known C200 NAND data-port byte-copy loops "
            "into equivalent bulk MMIO reads. Disabled by default."
        ),
    )
    ap.add_argument(
        "--resource-cache16-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: intercept C200 0x8017ca10 resource-cache 16-bit lookups. "
            "Disabled by default because bad cache modeling can corrupt image/resource data."
        ),
    )
    ap.add_argument(
        "--no-raster-copy-accelerator",
        action="store_true",
        help="Diagnostic: disable the 0x800ac388 raster-copy loop accelerator while keeping other fast hooks.",
    )
    ap.add_argument(
        "--no-glyph-mask-accelerator",
        action="store_true",
        help="Diagnostic: disable the 0x8011b428 glyph-mask loop accelerator while keeping other fast hooks.",
    )
    ap.add_argument(
        "--no-surface-pixel-accelerator",
        action="store_true",
        help="Diagnostic: disable the 0x8012bdf4 surface setpixel accelerator while keeping other fast hooks.",
    )
    ap.add_argument(
        "--no-surface-hline-accelerator",
        action="store_true",
        help="Diagnostic: disable the 0x8012bea4 surface hline accelerator while keeping other fast hooks.",
    )
    ap.add_argument(
        "--surface-pixel-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: replace C200 0x8012bdf4 surface setpixel. "
            "Kept for compatibility; the accelerator is enabled by default."
        ),
    )
    ap.add_argument(
        "--surface-hline-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: replace C200 0x8012bea4 surface hline. "
            "Kept for compatibility; the accelerator is enabled by default."
        ),
    )
    ap.add_argument(
        "--font-helper-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: replace selected C200 font helper returns at 0x8012a6a8. "
            "Off by default because it can corrupt GBK glyph selection."
        ),
    )
    ap.add_argument(
        "--repeat-prologue-mode",
        default="off",
        choices=["off", "log", "fix", "stop"],
        help=(
            "Diagnostic mode for repeated stack-prologue observations. "
            "fix keeps legacy compensation; stop halts at the first case."
        ),
    )
    ap.add_argument(
        "--fs-dir-scan-stop-samples",
        type=int,
        default=0,
        help="Diagnostic: stop after collecting this many C200 directory-scan loop samples.",
    )
    ns = ap.parse_args(argv)
    apply_preset(ns, argv)
    watch_ranges = list(ns.watch_va)
    if ns.watch_input_state:
        watch_ranges.append(parse_watch_range("input=0x80473f40:0x80"))
    if ns.watch_input_nodes:
        watch_ranges.append(parse_watch_range("nodes=0x806c5000:0x1000"))

    report: dict[str, object] = {
        "inspect": inspect_image(ns.image, ns.base, ns.disasm_count),
        "payload": None
        if ns.payload is None
        else {
            "path": str(ns.payload),
            "size": ns.payload.stat().st_size,
            "addr": f"0x{ns.payload_addr:08x}",
        },
        "execution": None,
    }

    if Uc is None:
        report["execution"] = {
            "available": False,
            "reason": "Python package 'unicorn' is not installed.",
        }
    else:
        emu = Bbk9588HwEmu(
            image=ns.image,
            base=ns.base,
            pc=ns.pc,
            ram_size=ns.ram_mb * 1024 * 1024,
            trace_limit=ns.trace_limit,
            recover_jr=not ns.no_recover_jr,
            profile=ns.profile,
            payload=ns.payload,
            payload_addr=ns.payload_addr,
            idle_stop_hits=ns.idle_stop_hits,
            app_idle_stop_hits=ns.app_idle_stop_hits,
            bda_idle_stop_polls=ns.bda_idle_stop_polls,
            watch_ranges=watch_ranges,
            scheduled_pokes=ns.poke_va,
            scheduled_calls=ns.call_va,
            call_stack=ns.call_stack,
            mmio_levels=ns.gpio_level,
            mmio_pulses=ns.gpio_pulse + ns.key_pulse,
            firmware_key_samples=ns.fw_key_sample,
            touch_samples=ns.touch_sample,
            bda_launches=ns.launch_bda,
            gui_key_events=ns.gui_key_event,
            gui_touch_events=ns.gui_touch_event,
            touch_controller_events=ns.touch_controller_event,
            bda_key_events=ns.bda_key_event,
            bda_events=ns.bda_event,
            bda_touch_events=ns.bda_touch_event,
            trace_pcs=ns.trace_pc,
            stop_pcs=ns.stop_pc,
            nand_image=ns.nand_image,
            nand_page_size=ns.nand_page_size,
            nand_spare_size=ns.nand_spare_size,
            readonly_nand_page_ranges=ns.readonly_nand_page_range,
            block_image=ns.block_image,
            usb_connected=ns.usb_connected,
            bda_text_mode=ns.bda_text_mode,
            bda_native_glyph_layout=ns.bda_native_glyph_layout,
            bda_native_raster_mode=ns.bda_native_raster_mode,
            scheduler_tick_clamp=ns.scheduler_tick_clamp,
            fs_dir_scan_stop_samples=ns.fs_dir_scan_stop_samples,
            fast_hooks=ns.fast_hooks,
            fast_hook_image_jals=ns.fast_hook_image_jals,
            fast_hook_image_branches=ns.fast_hook_image_branches,
            nand_loop_accelerator=ns.nand_loop_accelerator,
            resource_cache16_accelerator=ns.resource_cache16_accelerator,
            raster_copy_accelerator=not ns.no_raster_copy_accelerator,
            glyph_mask_accelerator=not ns.no_glyph_mask_accelerator,
            surface_pixel_accelerator=not ns.no_surface_pixel_accelerator,
            surface_hline_accelerator=not ns.no_surface_hline_accelerator,
            font_helper_accelerator=ns.font_helper_accelerator,
            gui_ring_pump=ns.gui_ring_pump,
            repeat_prologue_mode=ns.repeat_prologue_mode,
        )
        if ns.state_in:
            emu.load_emulator_state(ns.state_in)
        if ns.clear_nand_overrides_page_range:
            emu.clear_nand_page_overrides(ns.clear_nand_overrides_page_range)
        for x, y, down in ns.touch_state:
            emu.set_touch_controller_state(x, y, down)
        try:
            state = emu.run(ns.steps, max_seconds=ns.max_seconds)
            stop_reason = state.stop_reason or "completed_step_count"
        except Exception as exc:
            state = emu.state
            stop_reason = f"{type(exc).__name__}: {exc}"
        if ns.state_out:
            emu.save_emulator_state(ns.state_out)
        report["execution"] = {
            "available": True,
            "stop_reason": stop_reason,
            "insn_count": state.insn_count,
            "last_pc": f"0x{state.last_pc:08x}",
            "last_pcs": [f"0x{pc:08x}" for pc in state.pcs],
            "last_calls": state.calls,
            "trace_pc_hits": emu.trace_pc_hits[-max(256, ns.trace_limit):],
            "events": state.events,
            "regs": emu.regs(),
            "recoveries": state.recoveries,
            "mmio": [access_to_dict(a) for a in state.mmio],
            "invalid": [access_to_dict(a) for a in state.invalid],
            "mmio_snapshot": emu.mmio_snapshot(),
            "uart": emu.uart_snapshot(),
            "watch": emu.watch_snapshot(),
            "input_state": emu.input_snapshot(),
            "fs_dir_scan": emu.fs_dir_scan_events[-256:],
            "return_epilogues": emu.return_epilogue_events[-64:],
            "repeat_prologues": emu.repeat_prologue_events[-256:],
        }
        if ns.fb_dump:
            try:
                report["execution"]["framebuffer"] = dump_rgb565_framebuffer(
                    emu,
                    ns.fb_dump,
                    ns.fb_addr,
                    ns.fb_offset_bytes,
                    ns.fb_width,
                    ns.fb_height,
                    ns.fb_stride_pixels,
                    ns.fb_format,
                    ns.fb_orientation,
                )
            except Exception as exc:
                report["execution"]["framebuffer"] = {
                    "path": str(ns.fb_dump),
                    "error": f"{type(exc).__name__}: {exc}",
                }
        if ns.fb_scan:
            report["execution"]["framebuffer_scan"] = scan_rgb565_framebuffers(
                emu,
                ns.fb_width,
                ns.fb_height,
                ns.fb_stride_pixels,
            )

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if ns.json_out:
        ns.json_out.write_text(text + "\n", encoding="utf-8")
    if ns.quiet:
        execution = report.get("execution") or {}
        if isinstance(execution, dict):
            framebuffer = execution.get("framebuffer") or {}
            pixels = framebuffer.get("nonzero_pixels") if isinstance(framebuffer, dict) else None
            print(
                f"stop={execution.get('stop_reason')} "
                f"invalid={len(execution.get('invalid', []))} "
                f"pixels={pixels} json={ns.json_out}"
            )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
