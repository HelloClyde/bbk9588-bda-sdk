"""Trace/event recording helpers for the BBK 9588 emulator."""

from __future__ import annotations

import struct

from unicorn.mips_const import (
    UC_MIPS_REG_2,
    UC_MIPS_REG_3,
    UC_MIPS_REG_4,
    UC_MIPS_REG_5,
    UC_MIPS_REG_6,
    UC_MIPS_REG_7,
    UC_MIPS_REG_8,
    UC_MIPS_REG_9,
    UC_MIPS_REG_16,
    UC_MIPS_REG_17,
    UC_MIPS_REG_18,
    UC_MIPS_REG_20,
    UC_MIPS_REG_25,
    UC_MIPS_REG_29,
    UC_MIPS_REG_31,
)

from hwemu_utils import va_to_phys


class HwEmuTraceMixin:
    def _trace_event(self, kind: str, **values: int) -> None:
        if self.suppress_hot_events and kind in {
            "memset-bulk",
            "memcpy-bulk",
            "malloc-scan-loop",
            "malloc-scan-hit-loop",
            "byte-copy-loop",
            "halfword-copy-loop",
            "halfword-copy-delay-loop",
            "block-image-hook",
            "fat16-cluster-read",
            "fat16-cluster-read-cache-hit",
            "fs-dir-scan-entry",
            "lfn-copy-loop",
            "nand-loop-accelerate",
            "ram-delay-branch",
            "stack-clear32-delay-loop",
            "zero-pad-delay-loop",
            "lcd-getter",
            "periodic-irq24-pending",
            "busy-delay",
            "mmio-delay-branch",
            "wait-wake",
        }:
            self.suppressed_hot_event_count += 1
            return
        row = {"kind": kind}
        row.update({k: f"0x{v & 0xFFFFFFFF:08x}" for k, v in values.items()})
        self.state.events.append(row)
        self._trim_events()

    def _trim_events(self) -> None:
        limit = max(128, self.trace_limit)
        while len(self.state.events) > limit:
            self.state.events.popleft()

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
        if not self.trace_pc_detail:
            return
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
