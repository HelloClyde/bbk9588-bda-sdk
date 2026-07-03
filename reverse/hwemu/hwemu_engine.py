"""Unicorn execution hooks and run loop for the BBK 9588 emulator."""

from __future__ import annotations

import struct
import time

from unicorn import (
    UC_HOOK_BLOCK,
    UC_HOOK_CODE,
    UC_HOOK_MEM_INVALID,
    UC_HOOK_MEM_READ,
    UC_HOOK_MEM_WRITE,
    UC_MEM_FETCH_UNMAPPED,
    UC_MEM_READ,
    UC_MEM_READ_UNMAPPED,
    UC_MEM_WRITE,
    UC_MEM_WRITE_UNMAPPED,
    UcError,
)
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
    UC_MIPS_REG_PC,
    UC_MIPS_REG_SP,
)

from hwemu_defs import (
    EXT_BANK_BASE,
    EXT_BANK_KSEG1_BASE,
    EXT_BANK_SIZE,
    MMIO_BASE,
    MMIO_SIZE,
    PHYS_MMIO_BASE,
    RAM_BASE,
    SADC_BASE,
    SADC_DATA,
    SADC_STATUS,
    SADC_TOUCH_DATA,
    TOUCH_ADC_SCREEN_X_BIAS,
    TOUCH_ADC_SCREEN_Y_BIAS,
    MmioAccess,
    TraceState,
)
from hwemu_fastpaths import PORTRAIT_BLIT_LOOP_PCS
from hwemu_surface import SURFACE_TRANSPARENT_BLIT_PCS
from hwemu_utils import va_to_phys


FS_DIR_SCAN_BRANCH_PCS = (
    0x80173630,
    0x80173640,
    0x80173710,
    0x80173768,
    0x80173F14,
    0x80173F1C,
    0x80173F24,
    0x80173F2C,
)

FS_DIR_SCAN_CAPTURE_PCS = (
    0x80173630,
    0x80173638,
    0x80173764,
    0x8017376C,
    0x80173F2C,
)

FS_DIR_SCAN_RETURN_PCS = frozenset(
    {
        0x801708C4,
        0x8017159C,
        0x801719F4,
        0x80171A5C,
        0x80171F14,
        0x80172174,
        0x80179D90,
        0x8017A564,
        0x8017A76C,
        0x8017E400,
    }
)

LFN_COPY_LOOP_PCS = (0x80174C9C, 0x80174CC0, 0x80174CE4)
GUI_TIMER_TABLE_VA = 0x804A6B40
GUI_TIMER_TABLE_SLOTS = 16
GUI_TIMER_EVENT_OBJECT_OFFSET = 0xF0
GUI_TIMER_EVENT_SLOT_OBJECTS_OFFSET = 0x20
GUI_TIMER_EVENT_SLOT_IDS_OFFSET = 0x60


class HwEmuEngineMixin:
    def _install_hooks(self) -> None:
        if self.fast_hooks:
            if self.fast_hook_image_branches:
                for pc in sorted(self._image_recoverable_branch_pcs()):
                    self.uc.hook_add(UC_HOOK_CODE, self._on_recovery_snapshot_code, begin=pc, end=pc)
            direct_hooks = self._direct_fast_code_hooks()
            for pc, callback in sorted(direct_hooks.items()):
                self.uc.hook_add(UC_HOOK_CODE, callback, begin=pc, end=pc)
            for pc in sorted(self._fast_code_hook_pcs() - set(direct_hooks)):
                self.uc.hook_add(UC_HOOK_CODE, self._on_code, begin=pc, end=pc)
        else:
            self.uc.hook_add(UC_HOOK_CODE, self._on_code)
        if self.block_hook:
            self.uc.hook_add(UC_HOOK_BLOCK, self._on_block)
        self._install_mem_hooks()
        self.uc.hook_add(UC_HOOK_MEM_INVALID, self._on_invalid)

    def _direct_fast_code_hooks(self) -> dict[int, object]:
        if self.profile != "bbk9588-uboot":
            return {}
        blocked = set(self.trace_pcs) | set(self.stop_pcs)
        hooks: dict[int, object] = {}

        def add(pc: int, callback, enabled: bool = True) -> None:
            if enabled and pc not in blocked:
                hooks[pc] = callback

        add(0x800043A0, self._on_busy_delay_code)
        add(0x800098C0, self._on_debug_print_stub_code)
        add(0x80058CB4, self._on_no_event_poll_code)
        add(0x8012BDF4, self._on_surface_setpixel_code, self.surface_pixel_accelerator)
        add(0x8012BEA4, self._on_surface_hline_code, self.surface_hline_accelerator)
        add(0x8012BF64, self._on_surface_color_span_code)
        add(0x8012BFE8, self._on_surface_read_span_code)
        for pc in SURFACE_TRANSPARENT_BLIT_PCS:
            add(pc, self._on_surface_transparent_blit_code)
        for pc in PORTRAIT_BLIT_LOOP_PCS:
            add(pc, self._on_portrait_blit_code)
        add(0x800074A0, self._on_malloc_scan_code)
        add(0x80007900, self._on_zero_fill_delay_loop_code)
        add(0x80173908, self._on_stack_clear32_delay_loop_code)
        add(0x80173C30, self._on_stack_clear32_delay_loop_code)
        add(0x8024227C, self._on_zero_pad_delay_loop_code)
        add(0x81C0756C, self._on_bda_bounded_cstr_search_code)
        for pc in LFN_COPY_LOOP_PCS:
            add(pc, self._on_lfn_copy_code)
        for pc in FS_DIR_SCAN_BRANCH_PCS:
            add(pc, self._on_fs_dir_scan_branch_code)

        # These two store-delay branch sites also carry task context restore
        # side effects in _on_code, so keep them on the full dispatch path.
        full_dispatch_pcs = {0x800081A8, 0x800088AC}
        for pc in self._store_delay_branch_hook_pcs():
            add(pc, self._on_store_delay_branch_code, pc not in hooks and pc not in full_dispatch_pcs)
        return hooks

    def _on_direct_fast_code(self, handler, uc, address: int, size: int, user_data) -> None:
        if self.profile == "bbk9588-uboot" and handler(address):
            return
        self._on_code(uc, address, size, user_data)

    def _on_busy_delay_code(self, uc, address: int, size: int, user_data) -> None:
        count = self.busy_delay_accel_count + 1
        uc.reg_write(UC_MIPS_REG_PC, uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.busy_delay_accel_count = count
        if count <= 16 or count % 4096 == 0:
            cycles = uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            self._trace_event("busy-delay", pc=address, value=cycles, size=count)

    def _on_debug_print_stub_code(self, uc, address: int, size: int, user_data) -> None:
        sp = uc.reg_read(UC_MIPS_REG_SP) & 0xFFFFFFFF
        for offset, reg in (
            (0x04, UC_MIPS_REG_5),
            (0x08, UC_MIPS_REG_6),
            (0x0C, UC_MIPS_REG_7),
        ):
            target = (sp + offset) & 0xFFFFFFFF
            if self._is_mapped_ram_va(target, 4):
                self._write_u32_va(target, uc.reg_read(reg) & 0xFFFFFFFF)
        uc.reg_write(UC_MIPS_REG_2, 0)
        ra = uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
        if self._looks_like_code_return(ra) and self._read_word_at_va(ra) is not None:
            uc.reg_write(UC_MIPS_REG_PC, ra)
            return
        self.state.stop_reason = self.state.stop_reason or f"debug_print_bad_ra_0x{ra:08x}"
        self._trace_event("debug-print-bad-ra", pc=address, target=ra)
        uc.emu_stop()

    def _on_no_event_poll_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_no_event_poll, uc, address, size, user_data)

    def _on_surface_setpixel_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_surface_setpixel, uc, address, size, user_data)

    def _on_surface_hline_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_surface_hline, uc, address, size, user_data)

    def _on_surface_color_span_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_surface_color_span_loop, uc, address, size, user_data)

    def _on_surface_read_span_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_surface_read_span_loop, uc, address, size, user_data)

    def _on_surface_transparent_blit_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_surface_transparent_blit, uc, address, size, user_data)

    def _on_portrait_blit_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_portrait_blit_loop, uc, address, size, user_data)

    def _on_malloc_scan_code(self, uc, address: int, size: int, user_data) -> None:
        if self._handle_interrupt_return(address):
            return
        if self._maybe_deliver_external_interrupt(address):
            return
        if self._handle_malloc_scan_loop(address):
            return
        self._on_code(uc, address, size, user_data)

    def _on_lfn_copy_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_lfn_copy_loop, uc, address, size, user_data)

    def _on_stack_clear32_delay_loop_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_stack_clear32_delay_loop, uc, address, size, user_data)

    def _on_zero_fill_delay_loop_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_zero_fill_delay_loop, uc, address, size, user_data)

    def _on_zero_pad_delay_loop_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_zero_pad_delay_loop, uc, address, size, user_data)

    def _on_bda_bounded_cstr_search_code(self, uc, address: int, size: int, user_data) -> None:
        self._on_direct_fast_code(self._handle_bda_bounded_cstr_search, uc, address, size, user_data)

    def _on_fs_dir_scan_branch_code(self, uc, address: int, size: int, user_data) -> None:
        if address in FS_DIR_SCAN_CAPTURE_PCS:
            self._capture_fs_dir_scan(address)
        if self._handle_fs_dir_scan_branch(address):
            return
        self._on_code(uc, address, size, user_data)

    def _find_fs_dir_scan_frame(self, sp: int) -> tuple[int, int] | None:
        offsets = [0]
        for step in range(4, 0x601, 4):
            offsets.append(-step)
            if step <= 0x200:
                offsets.append(step)
        for delta in offsets:
            frame_sp = (sp + delta) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(frame_sp + 0xEC, 4):
                continue
            saved_ra = self._read_mem_va(frame_sp + 0xEC, 4) & 0xFFFFFFFF
            if saved_ra in FS_DIR_SCAN_RETURN_PCS:
                return frame_sp, saved_ra
        return None

    def _on_store_delay_branch_code(self, uc, address: int, size: int, user_data) -> None:
        if self._handle_interrupt_return(address):
            return
        if self._maybe_deliver_external_interrupt(address):
            return
        if self._handle_branch_with_mmio_delay(address):
            return
        self._on_code(uc, address, size, user_data)

    def _find_gui_timer_event_slot(self, event_obj: int, owner_obj: int, timer_id: int) -> int | None:
        if not self._is_mapped_ram_va(event_obj, GUI_TIMER_EVENT_SLOT_IDS_OFFSET + GUI_TIMER_TABLE_SLOTS * 4):
            return None
        for slot in range(GUI_TIMER_TABLE_SLOTS):
            slot_obj = self._read_u32_va_safe(event_obj + GUI_TIMER_EVENT_SLOT_OBJECTS_OFFSET + slot * 4)
            slot_id = self._read_u32_va_safe(event_obj + GUI_TIMER_EVENT_SLOT_IDS_OFFSET + slot * 4)
            if slot_obj == owner_obj and slot_id == timer_id:
                return slot
        return None

    def _record_gui_timer_event(
        self,
        *,
        kind: str,
        pc: int,
        index: int,
        entry: int,
        owner_obj: int,
        timer_id: int,
        event_obj: int,
        slot: int | None,
        flags: int | None = None,
    ) -> None:
        row: dict[str, str | int] = {
            "kind": kind,
            "pc": f"0x{pc:08x}",
            "index": index,
            "entry": f"0x{entry:08x}",
            "owner_obj": f"0x{owner_obj:08x}",
            "timer_id": f"0x{timer_id:08x}",
            "event_obj": f"0x{event_obj:08x}",
            "slot": -1 if slot is None else slot,
        }
        if flags is not None:
            row["flags"] = f"0x{flags:08x}"
        self.gui_timer_events.append(row)
        if len(self.gui_timer_events) > 128:
            del self.gui_timer_events[0]

    def _is_mapped_ram_va_or_phys(self, address: int, size: int = 1) -> bool:
        if size < 0:
            return False
        phys = va_to_phys(address) if address >= RAM_BASE else address
        return 0 <= phys and phys + size <= self.ram_size

    def _is_known_device_span(self, address: int, size: int = 1) -> bool:
        if size <= 0:
            return False
        start = self._canonical_mmio_address(address)
        end = start + size
        known_ranges = (
            (0x10001000, 0x10001100),  # INTC
            (0x10002000, 0x10002100),  # TCU
            (0x10010000, 0x10010400),  # GPIO
            (SADC_BASE, SADC_BASE + 0x100),
            (0x13040000, 0x13040100),  # USB device controller
            (EXT_BANK_BASE, EXT_BANK_BASE + 0x04),  # NAND data window
            (EXT_BANK_BASE + 0x8000, EXT_BANK_BASE + 0x8100),  # NAND command latch
            (EXT_BANK_BASE + 0x10000, EXT_BANK_BASE + 0x10100),  # NAND address latch
        )
        return any(start < high and end > low for low, high in known_ranges)

    def _fix_repeated_frame_entry(self, pc: int, attr: str, frame_size: int) -> None:
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
        previous = getattr(self, attr, None)
        if (
            isinstance(previous, dict)
            and previous.get("ra") == ra
            and previous.get("sp") == ((sp + frame_size) & 0xFFFFFFFF)
        ):
            self.uc.reg_write(UC_MIPS_REG_29, previous["sp"] & 0xFFFFFFFF)
            setattr(self, attr, None)
            event = "repeat-entry-28-fix" if frame_size == 0x28 else "repeat-entry-frame-fix"
            self._trace_event(event, pc=pc, sp=sp, target=ra, size=frame_size)
            return
        setattr(self, attr, {"sp": sp, "ra": ra})

    def _fix_repeated_0x28_entry(self, pc: int, attr: str) -> None:
        self._fix_repeated_frame_entry(pc, attr, 0x28)

    def _service_gui_timer_entries(self, pc: int) -> None:
        self.gui_timer_tick_count += 1
        for index in range(GUI_TIMER_TABLE_SLOTS):
            entry = self._read_u32_va_safe(GUI_TIMER_TABLE_VA + index * 4) or 0
            if not self._is_mapped_ram_va(entry, 0x10):
                continue
            owner_obj = self._read_u32_va_safe(entry) or 0
            timer_id = self._read_u32_va_safe(entry + 4) or 0
            period = self._read_u32_va_safe(entry + 8) or 0
            counter = self._read_u32_va_safe(entry + 0x0C) or 0
            if not self._is_mapped_ram_va(owner_obj, GUI_TIMER_EVENT_OBJECT_OFFSET + 4):
                continue

            period = max(1, period)
            counter = (counter + 1) & 0xFFFFFFFF
            if counter < period:
                self._write_u32_va(entry + 0x0C, counter)
                continue

            self._write_u32_va(entry + 0x0C, 0)
            event_obj = self._read_u32_va_safe(owner_obj + GUI_TIMER_EVENT_OBJECT_OFFSET) or 0
            slot = self._find_gui_timer_event_slot(event_obj, owner_obj, timer_id)
            if slot is None:
                self._record_gui_timer_event(
                    kind="gui-timer-miss",
                    pc=pc,
                    index=index,
                    entry=entry,
                    owner_obj=owner_obj,
                    timer_id=timer_id,
                    event_obj=event_obj,
                    slot=None,
                )
                continue

            flags = self._read_u32_va_safe(event_obj) or 0
            new_flags = flags | (1 << slot)
            self._write_u32_va(event_obj, new_flags)
            self.gui_timer_fire_count += 1
            self._record_gui_timer_event(
                kind="gui-timer-fire",
                pc=pc,
                index=index,
                entry=entry,
                owner_obj=owner_obj,
                timer_id=timer_id,
                event_obj=event_obj,
                slot=slot,
                flags=new_flags,
            )
            if self.gui_timer_fire_count <= 16 or self.gui_timer_fire_count % 256 == 0:
                self._trace_event("gui-timer-fire", pc=pc, addr=event_obj, value=new_flags, size=slot)

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

    def _snapshot_regs_for_recovery(self) -> dict[str, int]:
        return {name: self.uc.reg_read(reg) & 0xFFFFFFFF for name, reg in self._state_regs()}

    def _restore_regs_for_recovery(self, snapshot: dict[str, int]) -> None:
        for name, reg in self._state_regs():
            if name in snapshot:
                self.uc.reg_write(reg, snapshot[name] & 0xFFFFFFFF)

    def _record_recovery_reg_snapshot(self, address: int) -> None:
        self.recovery_reg_snapshots[address & 0xFFFFFFFF] = self._snapshot_regs_for_recovery()
        if len(self.recovery_reg_snapshots) > 256:
            self.recovery_reg_snapshots.pop(next(iter(self.recovery_reg_snapshots)))

    def _snapshot_recovery_regs_if_needed(self, address: int) -> None:
        pc = address & 0xFFFFFFFF
        cache = getattr(self, "recovery_snapshot_pc_cache", None)
        if cache is None:
            cache = self.recovery_snapshot_pc_cache = {}
        should_snapshot = cache.get(pc)
        if should_snapshot is None:
            word = self._read_word_at_va(pc)
            should_snapshot = word is not None and self._is_recoverable_exception_word(word)
            if len(cache) > 2048:
                cache.clear()
            cache[pc] = should_snapshot
        if should_snapshot:
            self._record_recovery_reg_snapshot(pc)

    def _on_recovery_snapshot_code(self, uc, address: int, size: int, user_data) -> None:
        self._record_recovery_reg_snapshot(address)

    def _on_block(self, uc, address: int, size: int, user_data) -> None:
        self.state.last_pc = address
        self.state.pcs.append(address)
        if len(self.state.pcs) > 64:
            del self.state.pcs[0]
        if self._maybe_deliver_external_interrupt(address):
            self.uc.emu_stop()

    def _on_code(self, uc, address: int, size: int, user_data) -> None:
        if self.legacy_direct_bda:
            self._recover_bda_corrupt_pointer_registers(address)
        if self.profile == "bbk9588-uboot" and self.fast_hooks:
            if address == 0x800043A0 and self._handle_busy_delay(address):
                return
            if address == 0x8012BDF4 and self._handle_surface_setpixel(address):
                return
            if address == 0x8012BF64 and self._handle_surface_color_span_loop(address):
                return
            if address == 0x8012BFE8 and self._handle_surface_read_span_loop(address):
                return
            if address == 0x8012C46C and self._handle_surface_transparent_blit(address):
                return
            if address == 0x8012BEA4 and self._handle_surface_hline(address):
                return
            if address == 0x8012C920 and self._handle_portrait_blit_loop(address):
                return
            if address == 0x80058CB4 and self._handle_no_event_poll(address):
                return
        if self.profile == "bbk9588-uboot" and self.legacy_direct_bda and self._handle_bda_sdkinput_copy_branch(address):
            return
        if self.profile == "bbk9588-uboot" and self.legacy_direct_bda and self._handle_bda_sdkinput_copy_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_nand_data_loop_accelerator(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_nand_ready_wait(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_nand_marker_check(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_nand_oob_read(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_ftl_scan_init(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_busy_delay(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_resource_cache16_hit(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_bda_bounded_cstr_search(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_fat16_cluster_read(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_dirent_copy(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_lfn_copy_loop(address):
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
        if self.profile == "bbk9588-uboot" and self._handle_surface_read_span_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_transparent_blit(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_setpixel(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_hline(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_block_read(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_surface_block_write(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_no_event_poll(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_c200_reset_init_loop(address):
            return
        if self.profile == "bbk9588-uboot" and self._apply_touch_sample(address):
            return
        if self.profile == "bbk9588-uboot" and address == 0x80006BD0:
            dst = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            value = self.uc.reg_read(UC_MIPS_REG_5) & 0xFF
            size_bytes = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
            if size_bytes <= 0x200000 and self._is_mapped_ram_va_or_phys(dst, size_bytes):
                self.uc.mem_write(va_to_phys(dst), bytes([value]) * size_bytes)
                self.uc.reg_write(UC_MIPS_REG_2, dst)
                self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
                self._trace_event("memset-bulk", pc=address, addr=dst, value=value, size=size_bytes)
                return
        if self.profile == "bbk9588-uboot" and address == 0x80006BF8:
            dst = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            src = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
            size_bytes = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
            if (
                size_bytes <= 0x200000
                and self._is_mapped_ram_va_or_phys(dst, size_bytes)
            ):
                data = None
                if self._is_mapped_ram_va_or_phys(src, size_bytes):
                    data = self._read_block_va_safe(src, size_bytes)
                    event_name = "memcpy-bulk"
                else:
                    if not self._is_known_device_span(src, size_bytes):
                        data = b"\xFF" * size_bytes
                        event_name = "memcpy-fill-ff"
                if data is not None:
                    self.uc.mem_write(va_to_phys(dst), data)
                    self.uc.reg_write(UC_MIPS_REG_2, dst)
                    self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
                    self._trace_event(event_name, pc=address, addr=dst, value=src, size=size_bytes)
                    return
        self._compensate_repeated_stack_prologue(address)
        self._preexecute_jr_delay(address)
        if not self.fast_hooks:
            self._trace_call(address)
        self._trace_selected_pc(address)
        if self._apply_stop_input_node_conditions(address):
            return
        if address in self.stop_pcs:
            self.state.stop_reason = f"stop_pc_0x{address:08x}"
            self.uc.emu_stop()
            return
        if self._handle_interrupt_return(address):
            return
        if self._maybe_deliver_external_interrupt(address):
            return
        if (not self.fast_hooks or address in self.store_delay_branch_pcs) and self._handle_branch_with_mmio_delay(address):
            return
        if self.profile == "bbk9588-uboot" and self._handle_malloc_scan_loop(address):
            return
        self._snapshot_recovery_regs_if_needed(address)
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
            self._service_gui_timer_entries(address)
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
        if self.profile == "bbk9588-uboot" and address in FS_DIR_SCAN_CAPTURE_PCS:
            self._capture_fs_dir_scan(address)
        if self.profile == "bbk9588-uboot" and address in FS_DIR_SCAN_BRANCH_PCS and self._handle_fs_dir_scan_branch(address):
            return
        if self.profile == "bbk9588-uboot" and address == 0x80173504:
            self._trace_event(
                "fs-dir-scan-entry",
                pc=address,
                sp=self.uc.reg_read(UC_MIPS_REG_SP) & 0xFFFFFFFF,
                target=self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF,
            )
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
            0x80006688: 0x20,
            0x80006834: 0x20,
            0x8000FEB4: 0x18,
            0x800100C8: 0x28,
            0x801802E8: 0x28,
            0x8017FDCC: 0x30,
            0x8018057C: 0x30,
            0x80184D08: 0x20,
        }:
            frame_size = {
                0x80006688: 0x20,
                0x80006834: 0x20,
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
            self._apply_key_controller_events(address)
            if self._apply_gui_key_events(address):
                return
            if self._apply_gui_touch_events(address):
                return
            self._apply_touch_controller_events(address)
            if self._apply_touch_sample(address):
                return
            if self._apply_firmware_key_sample(address):
                return
            if self.legacy_direct_bda and self._apply_bda_launch(address):
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
            if not self.legacy_direct_bda or not self.bda_app_active:
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
            if self.legacy_direct_bda:
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
            surface = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            red = self.uc.reg_read(UC_MIPS_REG_5) & 0xFF
            green = self.uc.reg_read(UC_MIPS_REG_6) & 0xFF
            blue = self.uc.reg_read(UC_MIPS_REG_7) & 0xFF
            bpp = self._read_u32_va_safe(0x8033C0BC) or 0x10
            if bpp == 0x10:
                value = ((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
                self.uc.reg_write(UC_MIPS_REG_2, value & 0xFFFF)
                self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
                self.rgb565_color_accel_count += 1
                if self.rgb565_color_accel_count <= 16 or self.rgb565_color_accel_count % 4096 == 0:
                    self._trace_event("rgb565-color", pc=address, addr=surface, value=value, size=self.rgb565_color_accel_count)
                return
        if self.profile == "bbk9588-uboot" and self.legacy_direct_bda and address == 0x800D3634 and self.repaint_call_context:
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
        if self.profile == "bbk9588-uboot" and address == 0x800CE928:
            self._fix_repeated_0x28_entry(address, "ce928_entry_context")
        if self.profile == "bbk9588-uboot" and address == 0x800CE9F0:
            self._fix_repeated_0x28_entry(address, "ce9f0_entry_context")
            self.window_close_context = {
                "sp": self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF,
                "ra": self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF,
            }
        if self.profile == "bbk9588-uboot" and address == 0x800CE968:
            # 0x800ce928's fast no-op path returns through
            # "jr ra; addiu sp,sp,0x28". Unicorn can surface the return without
            # the delay-slot stack restore, which corrupts BDA callers that
            # immediately load their saved RA from the stack.
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if self._looks_like_code_return(ra):
                sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
                self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x28) & 0xFFFFFFFF)
                self.uc.reg_write(UC_MIPS_REG_PC, ra)
                self.ce928_entry_context = None
                self._trace_event("ce928-return-fix", pc=address, sp=sp, target=ra)
                return
        if self.profile == "bbk9588-uboot" and address == 0x800CEA30 and self.window_close_context:
            ctx = self.window_close_context
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if ra == 0 and ctx["ra"] not in (0, 4):
                ra = ctx["ra"]
                self.uc.reg_write(UC_MIPS_REG_31, ra)
            if self._looks_like_code_return(ra):
                sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
                self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x28) & 0xFFFFFFFF)
                self.uc.reg_write(UC_MIPS_REG_PC, ra)
                self.window_close_context = None
                self.ce9f0_entry_context = None
                self._trace_event("window-close-return-fix", pc=address, target=ra, sp=sp)
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
        if self.profile == "bbk9588-uboot" and address == 0x800DE150:
            self._fix_repeated_0x28_entry(address, "de150_entry_context")
        if self.profile == "bbk9588-uboot" and address == 0x800DE190:
            self._fix_repeated_0x28_entry(address, "de190_entry_context")
        if self.profile == "bbk9588-uboot" and address == 0x800DE1C8:
            self._fix_repeated_0x28_entry(address, "de1c8_entry_context")
        if self.profile == "bbk9588-uboot" and address in (0x800DE188, 0x800DE1C0, 0x800DE200):
            attr = {
                0x800DE188: "de150_entry_context",
                0x800DE1C0: "de190_entry_context",
                0x800DE200: "de1c8_entry_context",
            }[address]
            ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
            if self._looks_like_code_return(ra):
                sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
                self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x28) & 0xFFFFFFFF)
                self.uc.reg_write(UC_MIPS_REG_PC, ra)
                setattr(self, attr, None)
                self._trace_event("de-event-return-fix", pc=address, sp=sp, target=ra)
                return
        if self.profile == "bbk9588-uboot" and address == 0x81C0FA74:
            if self._read_word_at_va(address) == 0x27BDFFE0:
                self._fix_repeated_frame_entry(address, "bda_billing_entry_context", 0x20)
        if self.profile == "bbk9588-uboot" and address == 0x800B3950:
            self._seed_surface_dirty_rect(self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF, address)
        if self.profile == "bbk9588-uboot" and address in (0x800C0D40, 0x80119B50, 0x8011A3C4):
            self._trace_system_text_entry(address)
        if self.profile == "bbk9588-uboot" and self.legacy_direct_bda and self.bda_text_mode == "ascii-hook" and address == 0x8011A3C4:
            if self._draw_synthetic_glyph_for_bda_text(address):
                return
        if self.profile == "bbk9588-uboot" and self.legacy_direct_bda and self.bda_text_mode == "native" and address == 0x8011A3C4:
            self._trace_bda_native_text_draw(address)
        if self.profile == "bbk9588-uboot" and self.legacy_direct_bda and address == 0x8011B054:
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
        if self.profile == "bbk9588-uboot" and self.legacy_direct_bda and self.bda_text_mode == "native" and address in {
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
        if self.profile == "bbk9588-uboot" and self.legacy_direct_bda and address == 0x8012CCFC:
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
                if display_flags & 0x00000001:
                    event_type = 0x144
                    self._write_u32_va(0x80825840, display_flags & ~0x00000001)
                    self._write_bda_synthetic_event(event, event_type)
                    self.uc.reg_write(UC_MIPS_REG_2, event)
                    self._trace_event("bda-timer-event", pc=address, addr=event, value=event_type, flags=display_flags)
                    return
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
            # epilogue with SP shifted after Unicorn/repeat-prologue recovery.
            # Use only the exact return PCs for this function's known JAL
            # callers, so an unrelated stack word cannot become a fake return.
            sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
            saved_ra = self._read_mem_va(sp + 0xEC, 4) if self._is_mapped_ram_va(sp + 0xEC, 4) else 0
            if saved_ra not in FS_DIR_SCAN_RETURN_PCS:
                frame = self._find_fs_dir_scan_frame(sp)
                if frame is not None:
                    frame_sp, frame_ra = frame
                    self._trace_event("fs-dir-scan-stack-fix", pc=address, sp=sp, value=saved_ra, target=frame_ra, size=(frame_sp - sp) & 0xFFFFFFFF)
                    self.uc.reg_write(UC_MIPS_REG_29, frame_sp)
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

    def _decode_store_delay_branch(self, pc: int):
        cached = self.store_delay_branch_decode_cache.get(pc)
        if cached is False:
            return None
        if cached is not None:
            return cached
        word = self._read_word_at_va(pc)
        delay_word = self._read_word_at_va(pc + 4)
        if word is None or delay_word is None or not self._is_recoverable_branch_word(word):
            self.store_delay_branch_decode_cache[pc] = False
            return None

        delay_opcode = (delay_word >> 26) & 0x3F
        if delay_opcode == 40:
            size, mask, delay_name = 1, 0xFF, "sb"
        elif delay_opcode == 41:
            size, mask, delay_name = 2, 0xFFFF, "sh"
        elif delay_opcode == 43:
            size, mask, delay_name = 4, 0xFFFFFFFF, "sw"
        else:
            self.store_delay_branch_decode_cache[pc] = False
            return None

        regs = self._reg_map()
        delay_rs = (delay_word >> 21) & 0x1F
        delay_rt = (delay_word >> 16) & 0x1F
        delay_imm = delay_word & 0xFFFF
        if delay_imm & 0x8000:
            delay_imm -= 0x10000
        delay_text = f"{delay_name} r{delay_rt},{delay_imm}(r{delay_rs})"

        opcode = (word >> 26) & 0x3F
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        imm = word & 0xFFFF
        if imm & 0x8000:
            imm -= 0x10000
        static_target = 0
        # mode: 0 j, 1 jal, 2 beq, 3 bne, 4 blez, 5 bgtz, 6 bltz, 7 bgez, 8 jr
        if opcode in (2, 3):
            mode = 1 if opcode == 3 else 0
            kind = "jal" if opcode == 3 else "j"
            static_target = (((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)) & 0xFFFFFFFF
        elif opcode == 4:
            mode, kind = 2, "beq"
        elif opcode == 5:
            mode, kind = 3, "bne"
        elif opcode == 6:
            mode, kind = 4, "blez"
        elif opcode == 7:
            mode, kind = 5, "bgtz"
        elif opcode == 1 and rt in (0, 1):
            mode, kind = (6, "bltz") if rt == 0 else (7, "bgez")
        elif opcode == 0 and (word & 0x001FFFFF) == 0x00000008 and (word & 0x3F) == 8:
            mode, kind = 8, "jr"
        else:
            self.store_delay_branch_decode_cache[pc] = False
            return None

        decoded = (
            mode,
            kind,
            regs[rs],
            regs[rt],
            imm,
            static_target,
            regs[delay_rs],
            regs[delay_rt],
            delay_imm,
            size,
            mask,
            delay_text,
        )
        self.store_delay_branch_decode_cache[pc] = decoded
        return decoded

    def _handle_branch_with_mmio_delay(self, pc: int) -> bool:
        decoded = self._decode_store_delay_branch(pc)
        if decoded is None:
            return False
        (
            mode,
            kind,
            branch_rs_reg,
            branch_rt_reg,
            branch_imm,
            static_target,
            delay_rs_reg,
            delay_rt_reg,
            delay_imm,
            size,
            mask,
            delay_text,
        ) = decoded
        va = (self.uc.reg_read(delay_rs_reg) + delay_imm) & 0xFFFFFFFF
        phys = va_to_phys(va)
        value = self.uc.reg_read(delay_rt_reg) & mask
        if mode in (0, 1):
            target = static_target
            taken = True
        elif mode in (2, 3):
            rs_val = self.uc.reg_read(branch_rs_reg) & 0xFFFFFFFF
            rt_val = self.uc.reg_read(branch_rt_reg) & 0xFFFFFFFF
            taken = (rs_val == rt_val) if mode == 2 else (rs_val != rt_val)
            target = (pc + 4 + (branch_imm << 2)) & 0xFFFFFFFF if taken else (pc + 8) & 0xFFFFFFFF
        elif mode in (4, 5, 6, 7):
            rs_raw = self.uc.reg_read(branch_rs_reg) & 0xFFFFFFFF
            rs_val = rs_raw - 0x100000000 if rs_raw & 0x80000000 else rs_raw
            if mode == 4:
                taken = rs_val <= 0
            elif mode == 5:
                taken = rs_val > 0
            elif mode == 6:
                taken = rs_val < 0
            else:
                taken = rs_val >= 0
            target = (pc + 4 + (branch_imm << 2)) & 0xFFFFFFFF if taken else (pc + 8) & 0xFFFFFFFF
        else:
            target = self.uc.reg_read(branch_rs_reg) & 0xFFFFFFFF
            taken = True
        is_mmio = (
            PHYS_MMIO_BASE <= phys < PHYS_MMIO_BASE + MMIO_SIZE
            or EXT_BANK_BASE <= phys < EXT_BANK_BASE + EXT_BANK_SIZE
        )
        is_ram = va >= RAM_BASE and 0 <= phys and phys + size <= self.ram_size
        if not is_mmio and not is_ram:
            return False
        if mode == 1:
            self.uc.reg_write(UC_MIPS_REG_31, (pc + 8) & 0xFFFFFFFF)
        self.uc.mem_write(phys, value.to_bytes(size, "little"))
        if is_mmio:
            self._model_mmio(UC_MEM_WRITE, phys, size, value)
        self.uc.reg_write(UC_MIPS_REG_PC, target)
        self.mmio_delay_branch_count += 1
        if self.mmio_delay_branch_count <= 32 or self.mmio_delay_branch_count % 256 == 0:
            self._trace_event("mmio-delay-branch" if is_mmio else "ram-delay-branch", pc=pc, target=target, value=value, size=size)
        if is_mmio and len(self.state.recoveries) < self.trace_limit:
            self.state.recoveries.append(
                f"{'mmio' if is_mmio else 'ram'}-delay-{kind} pc=0x{pc:08x} target=0x{target:08x} taken={taken} delay={delay_text}"
            )
        return True

    def _handle_branch_with_mmio_delay_legacy(self, pc: int) -> bool:
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
        if is_mmio and len(self.state.recoveries) < self.trace_limit:
            self.state.recoveries.append(
                f"{'mmio' if is_mmio else 'ram'}-delay-{kind} pc=0x{pc:08x} target=0x{target:08x} taken={taken} delay={delay_text}"
            )
        return True

    def _on_mem(self, uc, access: int, address: int, size: int, value: int, user_data) -> None:
        phys_address = va_to_phys(address)
        if (
            self.suppress_hot_events
            and access == UC_MEM_READ
            and size == 4
            and phys_address == 0x10010200
            and not self.mmio_pulses
            and phys_address not in self.mmio_read_levels
        ):
            if self.nand_busy_reads > 0:
                self.nand_busy_reads -= 1
                ready = 0
            else:
                ready = 0x40000000
            self._write_u32_phys(phys_address, ready | self.gpio_idle_levels.get(phys_address, 0))
            self.suppressed_hot_event_count += 1
            return
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
            self._mark_framebuffer_dirty(pc, address, size, "mem-write")
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
            if self.suppress_hot_events:
                self.suppressed_hot_event_count += 1
                return
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
        attr = "touch_adc_x" if axis == 0 else "touch_adc_y"
        if hasattr(self, attr):
            return max(0, min(0xFFF, int(getattr(self, attr))))
        raw_x, raw_y = self._touch_panel_to_adc(self.touch_x, self.touch_y)
        return raw_x if axis == 0 else raw_y

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
        if not self.legacy_direct_bda or not self.bda_app_active or not self._is_bda_runtime_va(pc):
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
        if not self.legacy_direct_bda or not self.bda_app_active or not self._is_bda_runtime_va(pc):
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
        if not self.legacy_direct_bda or not self.bda_app_active or pc != 0x81C0392C:
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
        if not self.legacy_direct_bda or not self.bda_app_active or pc != 0x81C038A0:
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
        if va & 0x3:
            return None
        phys = va & 0x1FFFFFFF if va >= RAM_BASE else va
        try:
            return struct.unpack("<I", self.uc.mem_read(phys, 4))[0]
        except Exception:
            return None

    def _reg_map(self) -> tuple[int, ...]:
        if self.mips_reg_map is not None:
            return self.mips_reg_map
        self.mips_reg_map = (
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
        )
        return self.mips_reg_map

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
        if not self._is_recoverable_exception_word(word):
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
            if not self._looks_like_code_return(target) or self._read_word_at_va(target) is None:
                bad_sp = self.uc.reg_read(UC_MIPS_REG_SP) & 0xFFFFFFFF
                self._trace_event("bad-jr-target", pc=pc, sp=bad_sp, target=target)
                if self.profile == "bbk9588-uboot" and pc == 0x801737E4:
                    sp = bad_sp
                    found = 0
                    for offset in range(0, 0x220, 4):
                        addr = (sp + offset) & 0xFFFFFFFF
                        if not self._is_mapped_ram_va(addr, 4):
                            continue
                        value = self._read_mem_va(addr, 4) & 0xFFFFFFFF
                        if self._looks_like_code_return(value) and self._read_word_at_va(value) is not None:
                            self._trace_event("fs-dir-scan-bad-jr-stack-candidate", pc=pc, sp=sp, addr=addr, value=value, size=offset)
                            found += 1
                            if found >= 12:
                                break
                self.uc.reg_write(UC_MIPS_REG_PC, pc)
                self.state.stop_reason = self.state.stop_reason or f"bad_jr_target_0x{target:08x}"
                if len(self.state.recoveries) < self.trace_limit:
                    self.state.recoveries.append(
                        f"bad-jr-target pc=0x{pc:08x} target=0x{target:08x} exc={exc}"
                    )
                return True
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

    def run(self, steps: int, max_seconds: float | None = None, timeout_is_stop: bool = True) -> TraceState:
        self.uc.reg_write(UC_MIPS_REG_PC, self.pc)
        # Stack is normally set by the reset code. Seed it only on the first
        # run so a long-lived emulator can continue in small frontend steps.
        if self.state.insn_count == 0:
            self.uc.reg_write(UC_MIPS_REG_SP, RAM_BASE + min(self.ram_size, 0x400000) - 0x100)
        self.last_run_requested_steps = max(0, int(steps))
        self.last_run_completed_steps = 0
        self.last_run_timed_out = False
        remaining = steps
        deadline = None if max_seconds is None or max_seconds <= 0 else time.monotonic() + max_seconds
        if self.fast_hooks:
            chunk_size = 100_000 if deadline is not None else 2_000_000
        else:
            chunk_size = steps
        try:
            while remaining > 0:
                if deadline is not None and time.monotonic() >= deadline:
                    if timeout_is_stop:
                        self.state.stop_reason = self.state.stop_reason or "max_seconds"
                    break
                start_pc = self.uc.reg_read(UC_MIPS_REG_PC)
                before = self.state.insn_count
                count = min(remaining, chunk_size)
                try:
                    self.internal_chunk_stop = False
                    timeout_us = 0
                    if deadline is not None:
                        timeout_us = max(1, int(max(0.0, deadline - time.monotonic()) * 1_000_000))
                    self.uc.emu_start(start_pc, 0, timeout=timeout_us, count=count)
                    ran = max(1, self.state.insn_count - before)
                    timed_out = deadline is not None and time.monotonic() >= deadline
                    if timed_out:
                        self.last_run_timed_out = True
                    if self.fast_hooks and not self.internal_chunk_stop and not timed_out:
                        completed = count
                    else:
                        completed = min(count, ran)
                    remaining -= completed
                    self.last_run_completed_steps += completed
                    if timed_out:
                        if timeout_is_stop:
                            self.state.stop_reason = self.state.stop_reason or "max_seconds"
                        break
                    if self.state.stop_reason:
                        break
                except UcError as exc:
                    ran = max(1, self.state.insn_count - before)
                    completed = min(count, ran)
                    remaining -= completed
                    self.last_run_completed_steps += completed
                    timed_out = deadline is not None and time.monotonic() >= deadline
                    if timed_out:
                        self.last_run_timed_out = True
                        if timeout_is_stop:
                            self.state.stop_reason = self.state.stop_reason or "max_seconds"
                        break
                    if not self._recover_exception(exc):
                        raise
                    if self.state.stop_reason:
                        break
        finally:
            self.pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        return self.state

