#!/usr/bin/env python3
"""Early BBK 9588/JZ4740 hardware emulator harness.

This is a hardware-level trace harness, not a BDA API shim. It loads a raw MIPS
system image, maps RAM, executes from reset when Unicorn is available, and logs
unimplemented MMIO accesses. The emulator should grow from concrete traces only.
"""

from __future__ import annotations

import struct
import sys
import time
from pathlib import Path

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


from hwemu_defs import (
    ASCII_5X7_FONT,
    BDA_DISPLAY_CALLBACK_TABLE,
    BDA_ENTRY_SIG,
    BDA_RUNTIME_ENTRY_VA,
    BDA_RUNTIME_TABLE_DST,
    BDA_RUNTIME_TABLE_SRC,
    EXT_BANK_BASE,
    EXT_BANK_KSEG1_BASE,
    EXT_BANK_SIZE,
    GPIO_KEY_CODE_BITS,
    GPIO_KEY_IDLE_LEVELS,
    KSEG1_BASE,
    MMIO_BASE,
    MMIO_SIZE,
    PHYS_MMIO_BASE,
    PHYS_RAM_BASE,
    RAM_BASE,
    SADC_BASE,
    SADC_DATA,
    SADC_STATUS,
    SADC_TOUCH_DATA,
    TOUCH_ADC_SCREEN_X_BIAS,
    TOUCH_ADC_SCREEN_Y_BIAS,
    TOUCH_PEN_GPIO_ADDR,
    TOUCH_PEN_GPIO_BIT,
    TOUCH_PEN_GPIO_LEVELS,
    FirmwareKeySample,
    GuiKeyEvent,
    GuiTouchEvent,
    MmioAccess,
    MmioLevel,
    MmioPulse,
    ScheduledBdaEvent,
    ScheduledBdaKeyEvent,
    ScheduledBdaLaunch,
    ScheduledBdaTouchEvent,
    ScheduledCall,
    ScheduledKeyControllerEvent,
    ScheduledPoke,
    ScheduledTouchControllerEvent,
    StopInputNodeCondition,
    TouchSample,
    TraceState,
    WatchRange,
)
from hwemu_utils import va_to_phys
from hwemu_devices import HwEmuDeviceMixin
from hwemu_engine import HwEmuEngineMixin
from hwemu_fastpaths import HwEmuFastpathMixin
from hwemu_hook_policy import HwEmuHookPolicyMixin
from hwemu_input import HwEmuInputMixin
from hwemu_interrupts import HwEmuInterruptMixin
from hwemu_state import HwEmuStateMixin
from hwemu_surface import HwEmuSurfaceMixin
from hwemu_tasks import HwEmuTaskMixin
from hwemu_trace import HwEmuTraceMixin


class Bbk9588HwEmu(
    HwEmuEngineMixin,
    HwEmuHookPolicyMixin,
    HwEmuTraceMixin,
    HwEmuInputMixin,
    HwEmuFastpathMixin,
    HwEmuDeviceMixin,
    HwEmuSurfaceMixin,
    HwEmuInterruptMixin,
    HwEmuTaskMixin,
    HwEmuStateMixin,
):
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
        key_controller_events: list[ScheduledKeyControllerEvent] | None = None,
        bda_key_events: list[ScheduledBdaKeyEvent] | None = None,
        bda_events: list[ScheduledBdaEvent] | None = None,
        bda_touch_events: list[ScheduledBdaTouchEvent] | None = None,
        trace_pcs: list[int] | None = None,
        trace_pc_detail: bool = True,
        stop_pcs: list[int] | None = None,
        stop_input_nodes: list[StopInputNodeCondition] | None = None,
        nand_image: Path | None = None,
        nand_page_size: int = 2048,
        nand_spare_size: int = 64,
        readonly_nand_page_ranges: list[tuple[int, int]] | None = None,
        block_image: Path | None = None,
        usb_connected: bool = False,
        bda_text_mode: str = "native",
        bda_native_glyph_layout: str = "rows-msb-vscale2",
        bda_native_raster_mode: str = "firmware",
        legacy_direct_bda: bool = False,
        scheduler_tick_clamp: bool = False,
        fs_dir_scan_stop_samples: int = 0,
        fast_hooks: bool = False,
        fast_hook_image_jals: bool = False,
        fast_hook_image_branches: bool = False,
        store_delay_branch_hooks: str = "known",
        nand_loop_accelerator: bool = False,
        resource_cache16_accelerator: bool = False,
        raster_copy_accelerator: bool = True,
        glyph_mask_accelerator: bool = True,
        surface_pixel_accelerator: bool = True,
        surface_hline_accelerator: bool = True,
        font_helper_accelerator: bool = False,
        gui_ring_pump: bool = False,
        repeat_prologue_mode: str = "off",
        suppress_hot_events: bool = False,
        block_hook: bool = True,
    ):
        if Uc is None:
            raise RuntimeError("unicorn is not installed")
        direct_bda_requested = bool(
            (bda_launches or [])
            or (bda_key_events or [])
            or (bda_events or [])
            or (bda_touch_events or [])
            or bda_text_mode == "ascii-hook"
            or bda_native_raster_mode == "synth"
        )
        if direct_bda_requested and not legacy_direct_bda:
            raise ValueError("legacy direct-BDA options require legacy_direct_bda=True")
        self.image = image
        self.base = base
        self.pc = pc
        self.ram_size = ram_size
        self.trace_limit = trace_limit
        self.recover_jr = recover_jr
        self.profile = profile
        self.payload = payload
        self.payload_addr = payload_addr
        self.image_size = image.stat().st_size
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
        self.key_controller_events = key_controller_events or []
        self.key_controller_event_log: list[dict[str, str | int]] = []
        self.key_down_codes: set[int] = set()
        self.bda_key_events = bda_key_events or []
        self.bda_key_event_log: list[dict[str, str | int]] = []
        self.bda_events = bda_events or []
        self.bda_event_log: list[dict[str, str | int]] = []
        self.bda_touch_events = bda_touch_events or []
        self.bda_touch_event_log: list[dict[str, str | int]] = []
        self.trace_pcs = set(trace_pcs or [])
        self.trace_pc_detail = trace_pc_detail
        self.stop_pcs = set(stop_pcs or [])
        self.stop_input_nodes = stop_input_nodes or []
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
        self.touch_adc_x = 0
        self.touch_adc_y = 0
        self.touch_down = False
        self.sadc_next_axis = 0
        self.sadc_status_event = 0
        self.sadc_conversion_events_remaining = 0
        self.recent_sadc_accesses: list[dict[str, str | int]] = []
        self.bda_text_mode = bda_text_mode
        self.bda_native_glyph_layout = bda_native_glyph_layout
        self.bda_native_raster_mode = bda_native_raster_mode
        self.legacy_direct_bda = legacy_direct_bda
        self.scheduler_tick_clamp = scheduler_tick_clamp
        self.fs_dir_scan_stop_samples = fs_dir_scan_stop_samples
        self.fast_hooks = fast_hooks
        self.fast_hook_image_jals = fast_hook_image_jals
        self.fast_hook_image_branches = fast_hook_image_branches
        self.store_delay_branch_hooks = store_delay_branch_hooks
        self.store_delay_branch_pcs: set[int] = set()
        self.store_delay_branch_decode_cache: dict[int, object] = {}
        self.mips_reg_map: tuple[int, ...] | None = None
        self.nand_loop_accelerator = nand_loop_accelerator
        self.resource_cache16_accelerator = resource_cache16_accelerator
        self.raster_copy_accelerator = raster_copy_accelerator
        self.glyph_mask_accelerator = glyph_mask_accelerator
        self.surface_pixel_accelerator = surface_pixel_accelerator
        self.surface_hline_accelerator = surface_hline_accelerator
        self.font_helper_accelerator = font_helper_accelerator
        self.gui_ring_pump = gui_ring_pump
        self.suppress_hot_events = suppress_hot_events
        self.block_hook = block_hook
        self.suppressed_hot_event_count = 0
        self.gui_ring_pump_events: list[dict[str, str | int]] = []
        self.nand_loop_accel_count = 0
        self.nand_ready_wait_accel_count = 0
        self.nand_marker_check_accel_count = 0
        self.nand_oob_read_accel_count = 0
        self.ftl_scan_accel_count = 0
        self.no_event_poll_accel_count = 0
        self.busy_delay_accel_count = 0
        self.nand_loop_events: list[dict[str, str | int]] = []
        self.resource_cache16_accel_count = 0
        self.resource_cache16_events: list[dict[str, str | int]] = []
        self.cluster_read_accel_count = 0
        self.cluster_read_events: list[dict[str, str | int]] = []
        self.fat16_layout_cache: dict[str, int] | None = None
        self.nand_fat_sector0_cache: int | None = None
        self.dirent_copy_accel_count = 0
        self.dirent_copy_events: list[dict[str, str | int]] = []
        self.lfn_copy_accel_count = 0
        self.cache_scan_tail_accel_count = 0
        self.logo_strip_blit_accel_count = 0
        self.free_scan_accel_count = 0
        self.surface_setpixel_accel_count = 0
        self.surface_hline_accel_count = 0
        self.surface_color_span_accel_count = 0
        self.surface_read_span_accel_count = 0
        self.surface_block_read_accel_count = 0
        self.surface_block_write_accel_count = 0
        self.surface_transparent_blit_accel_count = 0
        self.surface_pixel_read_count = 0
        self.surface_event_count = 0
        self.surface_events: list[dict[str, str | int]] = []
        self.surface_events_by_mode: dict[str, list[dict[str, str | int]]] = {}
        self.rgb565_color_accel_count = 0
        self.halfword_copy_accel_count = 0
        self.raster_loop_accel_count = 0
        self.glyph_mask_loop_accel_count = 0
        self.repeat_prologue_mode = repeat_prologue_mode
        self.recovery_reg_snapshots: dict[int, dict[str, int]] = {}
        self.recovery_snapshot_pc_cache: dict[int, bool] = {}
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
        self.gui_timer_tick_count = 0
        self.gui_timer_fire_count = 0
        self.gui_timer_events: list[dict[str, str | int]] = []
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
        self.last_run_requested_steps = 0
        self.last_run_completed_steps = 0
        self.last_run_timed_out = False
        self.ce928_entry_context: dict[str, int] | None = None
        self.ce9f0_entry_context: dict[str, int] | None = None
        self.de150_entry_context: dict[str, int] | None = None
        self.de190_entry_context: dict[str, int] | None = None
        self.de1c8_entry_context: dict[str, int] | None = None
        self.bda_billing_entry_context: dict[str, int] | None = None
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
        self.framebuffer_dirty_seq = 0
        self.framebuffer_dirty_last: dict[str, str | int] | None = None
        self.framebuffer_dirty_last_raw: tuple[int, int, int, int, str] | None = None
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
        if va & 0x3:
            return False
        if self.payload is not None and self.payload_addr <= va < self.payload_addr + self.payload_size:
            return True
        if self.payload is None:
            if self.base <= va < self.base + self.image_size:
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
        if not self.legacy_direct_bda or not self.bda_app_active or not self._is_mapped_ram_va(surface, 0xC8):
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
        if not self.legacy_direct_bda or not self.bda_app_active:
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
        self._trim_events()

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
        if not self.legacy_direct_bda:
            return False
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


if __name__ == "__main__":
    from hwemu_cli import main as cli_main

    raise SystemExit(cli_main(sys.argv[1:], Bbk9588HwEmu, Uc))
