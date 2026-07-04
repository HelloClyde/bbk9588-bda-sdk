"""Input, scheduled event, and touchscreen helpers for the BBK 9588 emulator."""

from __future__ import annotations

from unicorn.mips_const import (
    UC_MIPS_REG_2,
    UC_MIPS_REG_4,
    UC_MIPS_REG_5,
    UC_MIPS_REG_6,
    UC_MIPS_REG_7,
    UC_MIPS_REG_29,
    UC_MIPS_REG_31,
    UC_MIPS_REG_PC,
    UC_MIPS_REG_SP,
)

from emu.core.defs import (
    BDA_ENTRY_SIG,
    BDA_RETURN_PC,
    BDA_RUNTIME_ENTRY_VA,
    BDA_RUNTIME_TABLE_DST,
    BDA_RUNTIME_TABLE_SRC,
    GPIO_FLAG_OFFSET,
    GPIO_KEY_CODE_BITS,
    GPIO_KEY_IDLE_LEVELS,
    ScheduledBdaEvent,
    ScheduledBdaKeyEvent,
    ScheduledBdaTouchEvent,
    TOUCH_ADC_SCREEN_X_BIAS,
    TOUCH_ADC_SCREEN_Y_BIAS,
    TOUCH_CALIBRATION_REFERENCE_POINTS,
    TOUCH_PEN_GPIO_ADDR,
    TOUCH_PEN_GPIO_LEVELS,
    gpio_addr_for_port,
    gpio_main_irq_for_port,
    gpio_port_for_addr,
)
from emu.tools.utils import va_to_phys


class HwEmuInputMixin:
    def _apply_stop_input_node_conditions(self, pc: int) -> bool:
        for condition in self.stop_input_nodes:
            if condition.pc is not None and pc != condition.pc:
                continue
            callback = self._read_u32_va_safe(condition.va)
            status_word = self._read_u32_va_safe(condition.va + 0x3C)
            if callback is None or status_word is None:
                continue
            status_3c = status_word & 0xFF
            if callback == condition.callback and status_3c >= condition.min_status_3c:
                self.state.stop_reason = (
                    f"stop_input_node_0x{condition.va:08x}_"
                    f"cb_0x{callback:08x}_status_0x{status_3c:02x}"
                )
                self._trace_event("stop-input-node", pc=pc, addr=condition.va, target=callback, value=status_3c)
                self.uc.emu_stop()
                return True
        return False

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
        if not self.legacy_direct_bda:
            return False
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
        if not self.legacy_direct_bda:
            return
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

    def set_key_controller_state(self, code: int, down: bool, pc: int | None = None) -> bool:
        """Set modeled physical key GPIO state.

        C200's scanner at 0x8001b464 reads active-low GPIO pin registers. Keep
        a persistent pressed-code set and derive GPIO words from the idle level
        plus every currently held key on the same port.
        """
        if code not in GPIO_KEY_CODE_BITS:
            return False
        was_down = code in self.key_down_codes
        if down:
            self.key_down_codes.add(code)
        else:
            self.key_down_codes.discard(code)
        changed = was_down != down

        touched_addrs = {GPIO_KEY_CODE_BITS[code][0]}
        for held_code in self.key_down_codes:
            touched_addrs.add(GPIO_KEY_CODE_BITS[held_code][0])

        row_levels: dict[int, int] = {}
        for addr in touched_addrs:
            gpio = GPIO_KEY_IDLE_LEVELS.get(addr, 0)
            for held_code in self.key_down_codes:
                held_addr, mask = GPIO_KEY_CODE_BITS[held_code]
                if held_addr == addr:
                    gpio &= ~mask
            # GPIOC bit30 is shared with NAND-ready modeling; preserve it high
            # here so a held key on GPIOC does not look like NAND busy.
            if addr == 0x10010200:
                gpio |= 0x40000000
            self.gpio_idle_levels[addr] = gpio & 0xFFFFFFFF
            self.mmio_read_levels.pop(addr, None)
            self._sync_gpio_data_backing(addr)
            row_levels[addr] = gpio & 0xFFFFFFFF

        irq_info: dict[str, str | int] | None = None
        if changed:
            key_addr, key_mask = GPIO_KEY_CODE_BITS[code]
            port = gpio_port_for_addr(key_addr)
            if port is not None:
                flag_addr = gpio_addr_for_port(port, GPIO_FLAG_OFFSET)
                flag_value = (self.mmio_regs.get(flag_addr, 0) | key_mask) & 0xFFFFFFFF
                main_irq = gpio_main_irq_for_port(port)
                self.mmio_regs[flag_addr] = flag_value
                self.intc_pending_mask |= 1 << main_irq
                irq_info = {
                    "port": port,
                    "flag_addr": f"0x{flag_addr:08x}",
                    "flag": f"0x{flag_value:08x}",
                    "main_irq": main_irq,
                    "pending": f"0x{self.intc_pending_mask & 0xFFFFFFFF:08x}",
                }

        if pc is None:
            pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        self._trace_event(
            "key-controller-state",
            pc=pc,
            addr=GPIO_KEY_CODE_BITS[code][0],
            value=code,
            size=int(down),
        )
        self.key_controller_event_log.append(
            {
                "event": "key-controller-state",
                "pc": f"0x{pc:08x}",
                "code": code,
                "down": int(down),
                "pressed": sorted(self.key_down_codes),
                "levels": {f"0x{addr:08x}": f"0x{level:08x}" for addr, level in sorted(row_levels.items())},
                "gpio_irq": irq_info,
            }
        )
        if len(self.key_controller_event_log) > 256:
            del self.key_controller_event_log[0]
        return True

    def _apply_key_controller_events(self, pc: int) -> bool:
        applied = False
        for event in self.key_controller_events:
            if event.applied or event.idle_hit != self.idle_loop_hits:
                continue
            event.applied = True
            if self.set_key_controller_state(event.code, event.down, pc=pc):
                applied = True
                self._trace_event("key-controller-event", pc=pc, value=event.code, size=int(event.down))
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
        raw_x, raw_y = self._touch_panel_to_adc(x, y)
        self._write_touch_latch(raw_x, raw_y, down)
        prev_x = self._read_u32_va_safe(0x80370FC8)
        prev_y = self._read_u32_va_safe(0x80370FCC)
        self._write_u32_va(0x80370FC0, x if prev_x is None else prev_x)
        self._write_u32_va(0x80370FC4, y if prev_y is None else prev_y)
        self._write_u32_va(0x80370FC8, x)
        self._write_u32_va(0x80370FCC, y)
        self._write_mem_va(0x807F7116, 2, x)
        self._write_mem_va(0x807F7118, 2, y)
        self._write_u32_va(0x80370FD0, 0 if down else 1)
        self._write_u32_va(0x80370FD4, 0x7F)
        self._write_u32_va(0x8048DD00, 0 if down else 1)
        self._write_u32_va(0x8048DD04, 1 if down else 0)
        self._write_u32_va(0x8048DD08, 0)

    def _touch_panel_to_adc(self, x: int, y: int) -> tuple[int, int]:
        panel_x = max(0, min(239, int(x) + TOUCH_ADC_SCREEN_X_BIAS))
        panel_y = max(0, min(319, int(y) + TOUCH_ADC_SCREEN_Y_BIAS))
        (x0, y0, raw_x00, raw_y00), (x1, _y0b, raw_x10, raw_y10), (
            _x1b,
            y1,
            raw_x11,
            raw_y11,
        ), (_x0b, _y1b, raw_x01, raw_y01) = TOUCH_CALIBRATION_REFERENCE_POINTS
        tx = (panel_x - x0) / max(1, x1 - x0)
        ty = (panel_y - y0) / max(1, y1 - y0)
        raw_x_top = raw_x00 + (raw_x10 - raw_x00) * tx
        raw_x_bottom = raw_x01 + (raw_x11 - raw_x01) * tx
        raw_y_top = raw_y00 + (raw_y10 - raw_y00) * tx
        raw_y_bottom = raw_y01 + (raw_y11 - raw_y01) * tx
        raw_x = round(raw_x_top + (raw_x_bottom - raw_x_top) * ty)
        raw_y = round(raw_y_top + (raw_y_bottom - raw_y_top) * ty)
        return max(0, min(0xFFF, raw_x)), max(0, min(0xFFF, raw_y))

    def _write_touch_latch(self, raw_x: int, raw_y: int, down: bool, *, mirror_logical: bool = False) -> None:
        raw_x = max(0, min(0xFFF, int(raw_x)))
        raw_y = max(0, min(0xFFF, int(raw_y)))
        self._write_mem_va(0x807F7110, 1, 1 if down else 0)
        self._write_mem_va(0x807F7112, 2, raw_x)
        self._write_mem_va(0x807F7114, 2, raw_y)
        if mirror_logical:
            self._write_mem_va(0x807F7116, 2, raw_x)
            self._write_mem_va(0x807F7118, 2, raw_y)

    def set_touch_controller_state(self, x: int, y: int, down: bool, pc: int | None = None) -> None:
        """Set the modeled touchscreen controller state.

        The frontend passes coordinates in the firmware touchscreen space.
        C200 reads raw 12-bit SADC samples into 0x807f7112/7114, then its
        own calibration matrix converts them to logical coordinates at
        0x807f7116/7118 and 0x80370fc8/0x80370fcc.
        """
        if pc is None:
            pc = self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF
        x = max(0, min(239, x))
        y = max(0, min(319, y))
        raw_x, raw_y = self._touch_panel_to_adc(x, y)
        self.touch_x = x
        self.touch_y = y
        self.touch_adc_x = raw_x
        self.touch_adc_y = raw_y
        self.touch_down = down
        if down:
            self.sadc_next_axis = 0
            self.sadc_conversion_events_remaining = 5
            # C200's SADC ISR masks status with ~control before testing bits.
            # The touch-control register normally has bit 0x10 set, so a pen
            # down must also expose conversion-ready bit 0x04 to reach the
            # coordinate sampling branch at 0x8001ac40.
            self.sadc_status_event = (self.sadc_status_event & ~0x08) | 0x14
        else:
            self.sadc_conversion_events_remaining = 0
            self.sadc_status_event = (self.sadc_status_event & ~0x14) | 0x08
            if 0x80017000 <= pc <= 0x80019300:
                # The calibration path waits on the low-level touch completion
                # flag set by C200's touch release ISR at 0x80017758. Keep this
                # seed scoped to calibration; it is not a raw controller state.
                self._write_mem_va(0x80477D84, 1, 1)
                self._write_u32_va(0x80362794, 0x28)
        self._sync_sadc_status_backing()
        self._write_touch_latch(raw_x, raw_y, down)
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
            self._sync_gpio_data_backing(addr)
            last_addr = addr
            last_gpio = gpio & 0xFFFFFFFF
        self.intc_pending_mask |= 1 << 12
        self._trace_event(
            "touch-controller-state",
            pc=pc,
            addr=last_addr,
            value=last_gpio,
            size=int(down),
            x=x,
            y=y,
            raw_x=raw_x,
            raw_y=raw_y,
        )

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
