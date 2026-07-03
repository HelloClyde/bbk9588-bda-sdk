"""Timer and interrupt helpers for the BBK 9588 emulator."""

from __future__ import annotations

from unicorn.mips_const import (
    UC_MIPS_REG_4,
    UC_MIPS_REG_26,
    UC_MIPS_REG_31,
    UC_MIPS_REG_CP0_STATUS,
    UC_MIPS_REG_PC,
)

from hwemu_defs import GPIO_FLAG_OFFSET, GPIO_PORT_COUNT, gpio_addr_for_port, gpio_main_irq_for_port


class HwEmuInterruptMixin:
    def _gpio_subirq_from_main_irq(self, irq: int) -> int | None:
        port = gpio_main_irq_for_port(0) - irq
        if port < 0 or port >= GPIO_PORT_COUNT:
            return None
        flag_addr = gpio_addr_for_port(port, GPIO_FLAG_OFFSET)
        flags = self.mmio_regs.get(flag_addr, 0) & 0xFFFFFFFF
        if flags == 0:
            self.intc_pending_mask &= ~(1 << irq)
            return None
        bit = flags.bit_length() - 1
        bit_mask = 1 << bit
        new_flags = flags & ~bit_mask
        self.mmio_regs[flag_addr] = new_flags & 0xFFFFFFFF
        if new_flags:
            self.intc_pending_mask |= 1 << irq
        else:
            self.intc_pending_mask &= ~(1 << irq)
        subirq = 0x30 + port * 32 + bit
        self._trace_event(
            "wait-gpio-subirq",
            pc=self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF,
            addr=flag_addr,
            value=subirq,
            size=flags,
        )
        return subirq

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
        self._refresh_gpio_pending()
        pending = self.intc_pending_mask & 0xFFFFFFFF
        while pending:
            irq = pending.bit_length() - 1
            dispatch_irq = self._gpio_subirq_from_main_irq(irq) if 25 <= irq <= 28 else irq
            if dispatch_irq is None:
                self._trace_event("wait-irq-skip-empty-gpio", pc=pc, value=irq)
                pending = self.intc_pending_mask & 0xFFFFFFFF
                continue
            entry = 0x80474684 + dispatch_irq * 8
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
            self._trace_event("wait-irq-skip-default", pc=pc, value=dispatch_irq, target=handler or 0, addr=irq)
            pending = self.intc_pending_mask & 0xFFFFFFFF
        else:
            return False
        arg = self._read_u32_va_safe(entry + 4) or 0
        if not (25 <= irq <= 28):
            self.intc_pending_mask &= ~(1 << irq)
        if irq == 23:
            self.tcu_pending_mask &= ~0x1
        elif irq == 22:
            self.tcu_pending_mask &= ~0x2
        self.uc.reg_write(UC_MIPS_REG_4, arg & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_31, return_pc & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_PC, handler & 0xFFFFFFFF)
        self._trace_event("wait-irq-service", pc=pc, target=handler, value=dispatch_irq, size=arg, addr=irq)
        return True
