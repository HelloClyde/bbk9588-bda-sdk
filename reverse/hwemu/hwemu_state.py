"""State persistence and diagnostic snapshots for the BBK 9588 emulator."""

from __future__ import annotations

import pickle
import struct
import zlib
from pathlib import Path

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
    UC_MIPS_REG_PC,
)

from hwemu_defs import (
    GPIO_KEY_CODE_BITS,
    GPIO_KEY_IDLE_LEVELS,
    KSEG1_BASE,
    PHYS_RAM_BASE,
    SADC_BASE,
    TOUCH_PEN_GPIO_LEVELS,
)
from hwemu_utils import va_to_phys


class HwEmuStateMixin:
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
            "key_down_codes": sorted(self.key_down_codes),
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
            "touch_adc_x": self.touch_adc_x,
            "touch_adc_y": self.touch_adc_y,
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
        self.key_down_codes = {int(code) for code in payload.get("key_down_codes", []) if int(code) in GPIO_KEY_CODE_BITS}
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
        if "touch_adc_x" in payload and "touch_adc_y" in payload:
            self.touch_adc_x = int(payload.get("touch_adc_x", self.touch_adc_x))
            self.touch_adc_y = int(payload.get("touch_adc_y", self.touch_adc_y))
        else:
            self.touch_adc_x, self.touch_adc_y = self._touch_panel_to_adc(self.touch_x, self.touch_y)
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
                "panel_x": self.touch_x,
                "panel_y": self.touch_y,
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
                "read_span_accel_count": self.surface_read_span_accel_count,
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
            "surface_read_span_accel_count": self.surface_read_span_accel_count,
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
            "key_controller_events": [
                {
                    "code": event.code,
                    "down": int(event.down),
                    "idle_hit": event.idle_hit,
                    "applied": event.applied,
                }
                for event in self.key_controller_events
            ],
            "key_controller_event_log": self.key_controller_event_log,
            "key_down_codes": sorted(self.key_down_codes),
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
        active_nodes = []
        seen: set[int] = set()
        for item in ptrs:
            offset = item["offset"]
            va = int(item["value"], 16)
            try:
                data = read_block(va, 0x70)
            except Exception:
                continue
            node_words = [int.from_bytes(data[i : i + 4], "little") for i in range(0, 0x30, 4)]
            callback = int.from_bytes(data[0:4], "little")
            status_bytes = data[0x30:0x40]
            active_nodes.append(
                {
                    "state_offset": offset,
                    "va": f"0x{va:08x}",
                    "callback": f"0x{callback:08x}",
                    "word_08": f"0x{node_words[2]:08x}",
                    "word_0c": f"0x{node_words[3]:08x}",
                    "word_10": f"0x{node_words[4]:08x}",
                    "word_14": f"0x{node_words[5]:08x}",
                    "status_30_3f": status_bytes.hex(),
                    "status_3c": status_bytes[0x0C],
                }
            )
            if va in seen:
                continue
            seen.add(va)
            nodes.append(
                {
                    "va": f"0x{va:08x}",
                    "words_00_2c": [f"0x{word:08x}" for word in node_words],
                    "bytes_30_3f": status_bytes.hex(),
                    "links_18_1c_20_24": [
                        f"0x{int.from_bytes(data[i:i+4], 'little'):08x}" for i in (0x18, 0x1C, 0x20, 0x24)
                    ],
                    "callback_00": f"0x{callback:08x}",
                }
            )
        out["active_node_summary"] = active_nodes
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

