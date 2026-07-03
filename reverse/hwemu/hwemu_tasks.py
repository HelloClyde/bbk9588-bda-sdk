"""Task table and context-switch helpers for the BBK 9588 emulator."""

from __future__ import annotations

import struct

from unicorn.mips_const import (
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
    UC_MIPS_REG_29,
    UC_MIPS_REG_30,
    UC_MIPS_REG_31,
    UC_MIPS_REG_CP0_STATUS,
    UC_MIPS_REG_HI,
    UC_MIPS_REG_LO,
    UC_MIPS_REG_PC,
)

from hwemu_defs import RAM_BASE


class HwEmuTaskMixin:
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

