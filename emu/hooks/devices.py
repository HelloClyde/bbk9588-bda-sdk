"""MMIO device models for the BBK 9588/JZ4740 emulator."""

from __future__ import annotations

# 本文件是硬件级模拟 hook 的主体，配合 `engine._on_mem()` 响应 MMIO 读写。
# 它关注设备寄存器语义，而不是固件函数调用：
# - GPIO/INTC/TCU/SADC/UDC/UART：维护寄存器状态、pending IRQ、触摸/按键电平。
# - NAND 控制器：按命令/地址/数据窗口模拟读页、写页、擦除和 OOB 访问。
# - NAND 循环加速：仍属于硬件数据窗口的等效快速路径，只在读写窗口语义明确时
#   批量搬运数据；未知情况回落到逐次 MMIO。

from unicorn import UC_MEM_READ, UC_MEM_WRITE
from unicorn.mips_const import (
    UC_MIPS_REG_2,
    UC_MIPS_REG_3,
    UC_MIPS_REG_4,
    UC_MIPS_REG_5,
    UC_MIPS_REG_7,
    UC_MIPS_REG_16,
    UC_MIPS_REG_17,
    UC_MIPS_REG_18,
    UC_MIPS_REG_31,
    UC_MIPS_REG_PC,
)

from emu.core.defs import (
    GPIO_BASE,
    GPIO_DATA_OFFSET,
    GPIO_FLAG_IRQ_INFO,
    GPIO_FLAG_CLEAR_OFFSET,
    GPIO_FLAG_OFFSET,
    GPIO_PORT_COUNT,
    GPIO_PORT_STRIDE,
    SADC_BASE,
    SADC_STATUS,
    TOUCH_PEN_GPIO_ADDR,
    gpio_addr_for_port,
    gpio_main_irq_for_port,
)
from emu.tools.utils import va_to_phys


GPIO_DYNAMIC_BACKING_ADDRS = tuple(
    gpio_addr_for_port(port, GPIO_DATA_OFFSET)
    for port in range(GPIO_PORT_COUNT)
    if gpio_addr_for_port(port, GPIO_DATA_OFFSET) != TOUCH_PEN_GPIO_ADDR
)


class HwEmuDeviceMixin:
    # 这里的 helper 都服务于 MMIO 硬件模型。`_handle_nand_*_accelerator`
    # 虽然由 code hook 触发，但加速的是固件反复读写 NAND 数据窗口这一硬件交互。
    def _sync_sadc_status_backing(self) -> None:
        self._write_mmio_value(SADC_STATUS, 4, self.sadc_status_event & 0xFF)

    def _sync_gpio_data_backing(self, address: int) -> None:
        if address not in GPIO_DYNAMIC_BACKING_ADDRS:
            return
        value = self.mmio_regs.get(address, self.gpio_idle_levels.get(address, 0))
        self._write_u32_phys(address, value & 0xFFFFFFFF)

    def _sync_dynamic_gpio_data_backing(self) -> None:
        for address in GPIO_DYNAMIC_BACKING_ADDRS:
            self._sync_gpio_data_backing(address)

    def _refresh_gpio_pending(self) -> None:
        for flag_addr, main_bit in GPIO_FLAG_IRQ_INFO:
            if self.mmio_regs.get(flag_addr, 0) & 0xFFFFFFFF:
                self.intc_pending_mask |= main_bit
            else:
                self.intc_pending_mask &= ~main_bit

    def _clear_gpio_flags(self, address: int, value: int) -> bool:
        if not (GPIO_BASE <= address < GPIO_BASE + GPIO_PORT_COUNT * GPIO_PORT_STRIDE):
            return False
        if ((address - GPIO_BASE) % GPIO_PORT_STRIDE) != GPIO_FLAG_CLEAR_OFFSET:
            return False
        port = (address - GPIO_BASE) // GPIO_PORT_STRIDE
        flag_addr = gpio_addr_for_port(port, GPIO_FLAG_OFFSET)
        old_value = self.mmio_regs.get(flag_addr, 0) & 0xFFFFFFFF
        new_value = old_value & ~(value & 0xFFFFFFFF)
        self.mmio_regs[flag_addr] = new_value & 0xFFFFFFFF
        main_bit = 1 << gpio_main_irq_for_port(port)
        if new_value:
            self.intc_pending_mask |= main_bit
        else:
            self.intc_pending_mask &= ~main_bit
        self._trace_event(
            "gpio-flag-clear",
            pc=self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF,
            addr=flag_addr,
            value=value & 0xFFFFFFFF,
            size=new_value & 0xFFFFFFFF,
        )
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
            cache = getattr(self, "backing_sector_cache", None)
            if cache is not None:
                cache.clear()
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
        # 硬件数据窗口加速 hook：把固件逐字节/逐字读取 NAND DATA 的循环合并成
        # 一次批量读，并保持 NAND 当前页、列和读指针状态。
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

    def _handle_nand_ready_wait(self, pc: int) -> bool:
        # NAND ready 等待加速：当前 NAND 模型是同步完成，固件 ready helper 可直接返回。
        if not self.fast_hooks or pc != 0x801838FC:
            return False
        ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, ra)
        self.nand_ready_wait_accel_count += 1
        if self.nand_ready_wait_accel_count <= 16 or self.nand_ready_wait_accel_count % 4096 == 0:
            self._trace_event("nand-ready-wait", pc=pc, target=ra, value=0)
        return True

    def _handle_nand_marker_check(self, pc: int) -> bool:
        # NAND 坏块/OOB 标记检查加速：直接读取镜像或 overlay 中的 OOB marker。
        if not self.fast_hooks or pc != 0x80183958:
            return False
        block = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        pages_per_block = self._read_u32_va_safe(0x804BF4B8) or 0
        if pages_per_block == 0 or pages_per_block > 0x400:
            return False
        page = block * pages_per_block + pages_per_block - 1
        column = self._read_u32_va_safe(0x804BF4AC) or 0
        column &= 0xFFFF
        stride = self.nand_page_size + self.nand_spare_size
        marker = 0xFF
        source = "erased"
        override = self.nand_page_overrides.get(page)
        if override is not None and column < len(override):
            marker = override[column]
            source = "overlay"
        elif self.nand_data is not None:
            offset = page * stride + column
            if 0 <= offset < len(self.nand_data):
                marker = self.nand_data[offset]
                source = "image"
        self.nand_current_page = page
        self.nand_current_column = column
        self.nand_current_offset = page * stride + column
        self.nand_reads.append(
            {
                "page": f"0x{page:x}",
                "column": f"0x{column:x}",
                "offset": f"0x{self.nand_current_offset:x}",
                "source": source,
                "marker_check": 1,
            }
        )
        if len(self.nand_reads) > 128:
            del self.nand_reads[0]
        self.uc.reg_write(UC_MIPS_REG_2, 0 if marker == 0xFF else 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.nand_marker_check_accel_count += 1
        if self.nand_marker_check_accel_count <= 16 or self.nand_marker_check_accel_count % 4096 == 0:
            self._trace_event("nand-marker-check", pc=pc, addr=page, value=marker, size=column)
        return True

    def _handle_nand_oob_read(self, pc: int) -> bool:
        # NAND OOB 读取加速：等价完成固件 OOB read helper 的内存写回。
        if not self.fast_hooks or pc != 0x80184300:
            return False
        page = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        dest = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        count = self._read_u32_va_safe(0x804BF4B0) or 0
        column = self._read_u32_va_safe(0x804BF4AC) or 0
        column &= 0xFFFF
        if count == 0 or count > 0x800 or not self._is_mapped_ram_va(dest, count):
            return False
        stride = self.nand_page_size + self.nand_spare_size
        source = "erased"
        data = b"\xFF" * count
        override = self.nand_page_overrides.get(page)
        if override is not None:
            data = override[column : column + count]
            if len(data) < count:
                data += b"\xFF" * (count - len(data))
            source = "overlay"
        elif self.nand_data is not None:
            offset = page * stride + column
            if 0 <= offset < len(self.nand_data):
                data = bytes(self.nand_data[offset : offset + count])
                if len(data) < count:
                    data += b"\xFF" * (count - len(data))
                source = "image"
        self.uc.mem_write(va_to_phys(dest), data)
        self.nand_current_page = page
        self.nand_current_column = column
        self.nand_current_offset = page * stride + column
        self.nand_reads.append(
            {
                "page": f"0x{page:x}",
                "column": f"0x{column:x}",
                "offset": f"0x{self.nand_current_offset:x}",
                "source": source,
                "oob_read": 1,
                "size": count,
            }
        )
        if len(self.nand_reads) > 128:
            del self.nand_reads[0]
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.nand_oob_read_accel_count += 1
        if self.nand_oob_read_accel_count <= 16 or self.nand_oob_read_accel_count % 4096 == 0:
            self._trace_event("nand-oob-read", pc=pc, addr=page, value=dest, size=count)
        return True

    def _handle_nand_program_loop_accelerator(self, pc: int) -> bool:
        # NAND program 数据循环加速：把固件写 DATA 窗口的循环收集到 program buffer。
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
        # NAND program 分支延迟槽变体：处理已经在 v0 中取出的当前字节，再批量追加尾部。
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
        # MMIO 硬件模型入口。读写副作用在这里落地：寄存器镜像、IRQ pending、
        # NAND latch、UART 输出、SADC 触摸状态等都从这个函数更新。
        if self.profile != "bbk9588-uboot":
            return

        if access == UC_MEM_WRITE:
            mask = (1 << (size * 8)) - 1
            self.mmio_regs[address] = value & mask
            if size == 4:
                self._sync_gpio_data_backing(address)
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
                    self._sync_sadc_status_backing()
                    return
                if (
                    address == SADC_BASE + 0x08
                    and self.touch_down
                    and (value & 0x10)
                    and self.sadc_conversion_events_remaining > 0
                ):
                    self.sadc_status_event |= 0x04
                    self.intc_pending_mask |= 1 << 12
                    self._sync_sadc_status_backing()
                self._write_mmio_value(address, size, value)
            if size == 4 and self._clear_gpio_flags(address, value):
                return
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
                    self._advance_next_tcu_irq_after_service()
                if ack & (1 << 24):
                    self._advance_next_irq24_after_service()
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
                self._advance_next_tcu_irq_after_service()
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
                self._refresh_gpio_pending()
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
