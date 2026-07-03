"""Surface, LCD mirror, and framebuffer dirty helpers for the BBK 9588 emulator."""

from __future__ import annotations

import struct

from unicorn.mips_const import (
    UC_MIPS_REG_2,
    UC_MIPS_REG_4,
    UC_MIPS_REG_5,
    UC_MIPS_REG_6,
    UC_MIPS_REG_7,
    UC_MIPS_REG_16,
    UC_MIPS_REG_17,
    UC_MIPS_REG_18,
    UC_MIPS_REG_19,
    UC_MIPS_REG_20,
    UC_MIPS_REG_21,
    UC_MIPS_REG_29,
    UC_MIPS_REG_31,
    UC_MIPS_REG_PC,
)

from hwemu_utils import va_to_phys


class HwEmuSurfaceMixin:
    def _lcd_mirror_config(self) -> tuple[int, int, int, bool] | None:
        if (self._read_u32_va_safe(0x80474040) or 0) == 0:
            return None
        width = self._read_mem_va(0x804A6B88, 2) & 0xFFFF
        height = self._read_mem_va(0x804A6B8C, 2) & 0xFFFF
        fb = self._read_u32_va_safe(0x804A6C60) or 0
        if width == 0 or height == 0 or fb == 0:
            return None
        reverse = bool(self._read_mem_va(0x804A6C64, 1) & 0xFF)
        return width, height, fb, reverse

    def _mirror_lcd_pixel_if_enabled(self, x: int, y: int, color: int) -> None:
        config = self._lcd_mirror_config()
        if config is None:
            return
        self._mirror_lcd_pixel_with_config(config, self.uc.reg_read(UC_MIPS_REG_PC) & 0xFFFFFFFF, x, y, color)

    def _mirror_lcd_pixel_with_config(
        self,
        config: tuple[int, int, int, bool],
        pc: int,
        x: int,
        y: int,
        color: int,
    ) -> None:
        width, height, fb, reverse = config
        mx = int(x)
        my = height - int(y) - 1
        if reverse:
            mx = width - mx - 1
        if mx < 0 or my < 0 or mx >= width or my >= height:
            return
        dest = (fb + ((my * width + mx) << 1)) & 0xFFFFFFFF
        if self._is_mapped_ram_va(dest, 2):
            self.uc.mem_write(va_to_phys(dest), struct.pack("<H", color & 0xFFFF))
            self._mark_framebuffer_dirty(pc, dest, 2, "lcd-mirror")

    def _mirror_lcd_span_bytes_with_config(
        self,
        config: tuple[int, int, int, bool],
        pc: int,
        x: int,
        y: int,
        data: bytes,
    ) -> None:
        width, height, fb, reverse = config
        count = len(data) // 2
        if count <= 0:
            return
        my = height - int(y) - 1
        if my < 0 or my >= height:
            return
        x0 = int(x)
        start = max(0, -x0)
        end = min(count, width - x0)
        if start >= end:
            return
        span = data[start * 2 : end * 2]
        if reverse:
            dest_x = width - x0 - end
            span = b"".join(span[i : i + 2] for i in range(len(span) - 2, -2, -2))
        else:
            dest_x = x0 + start
        dest = (fb + ((my * width + dest_x) << 1)) & 0xFFFFFFFF
        if self._is_mapped_ram_va(dest, len(span)):
            self.uc.mem_write(va_to_phys(dest), span)
            self._mark_framebuffer_dirty(pc, dest, len(span), "lcd-mirror")

    def _mirror_lcd_hline_with_config(
        self,
        config: tuple[int, int, int, bool],
        pc: int,
        x: int,
        y: int,
        width: int,
        color: int,
    ) -> None:
        if width <= 0:
            return
        self._mirror_lcd_span_bytes_with_config(
            config,
            pc,
            x,
            y,
            struct.pack("<H", color & 0xFFFF) * width,
        )

    def _mark_framebuffer_dirty(self, pc: int, addr: int, size: int, reason: str) -> None:
        self.framebuffer_dirty_seq = (self.framebuffer_dirty_seq + 1) & 0xFFFFFFFF
        self.framebuffer_dirty_last_raw = (
            self.framebuffer_dirty_seq,
            pc & 0xFFFFFFFF,
            addr & 0xFFFFFFFF,
            size,
            reason,
        )

    def _framebuffer_dirty_last_snapshot(self) -> dict[str, str | int] | None:
        raw = getattr(self, "framebuffer_dirty_last_raw", None)
        if raw is None:
            return self.framebuffer_dirty_last
        seq, pc, addr, size, reason = raw
        return {
            "seq": seq,
            "pc": f"0x{pc:08x}",
            "addr": f"0x{addr:08x}",
            "size": size,
            "reason": reason,
        }

    def _mark_framebuffer_dirty_if_overlaps(self, pc: int, addr: int, size: int, reason: str) -> None:
        if size <= 0:
            return
        start = addr & 0xFFFFFFFF
        end = (start + size - 1) & 0xFFFFFFFF
        ranges = (
            (0xA1F80000, 0xA1FA8000 - 1),
            (0x01F80000, 0x01FA8000 - 1),
            (0x81F80000, 0x81FA8000 - 1),
        )
        if any(start <= hi and end >= lo for lo, hi in ranges):
            self._mark_framebuffer_dirty(pc, addr, size, reason)

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
        if self.suppress_hot_events:
            self.suppressed_hot_event_count += 1
            return
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

    def _surface_pitch_buffer(self, surface: int) -> tuple[int, int] | None:
        if not self._is_mapped_ram_va(surface, 0x48):
            return None
        try:
            desc = self.uc.mem_read(va_to_phys(surface + 0x18), 0x30)
        except Exception:
            return None
        pitch = struct.unpack_from("<I", desc, 0)[0]
        buffer_va = struct.unpack_from("<I", desc, 0x2C)[0]
        if pitch == 0 or buffer_va == 0:
            return None
        return pitch, buffer_va

    def _handle_surface_setpixel(self, pc: int) -> bool:
        if not self.fast_hooks or not self.surface_pixel_accelerator or pc != 0x8012BDF4:
            return False
        surface = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        x = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        y = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        color = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFF
        if x & 0x80000000 or y & 0x80000000:
            return False
        surface_desc = self._surface_pitch_buffer(surface)
        if surface_desc is None:
            return False
        pitch, buffer_va = surface_desc
        dest = (buffer_va + y * pitch + x * 2) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(dest, 2):
            return False
        mirror_config = self._lcd_mirror_config()
        if mirror_config is not None:
            self._mirror_lcd_pixel_with_config(mirror_config, pc, x, y, color)
        self.uc.mem_write(va_to_phys(dest), struct.pack("<H", color))
        self._mark_framebuffer_dirty(pc, dest, 2, "surface-setpixel")
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
        if not self._is_mapped_ram_va(sp + 0x38, 2):
            return False
        surface_desc = self._surface_pitch_buffer(surface)
        if surface_desc is None:
            return False
        pitch, buffer_va = surface_desc
        color = self._read_mem_va(sp + 0x38, 2) & 0xFFFF
        dest = (buffer_va + y * pitch + x0 * 2) & 0xFFFFFFFF
        byte_count = width * 2
        if not self._is_mapped_ram_va(dest, byte_count):
            return False
        mirror_config = self._lcd_mirror_config()
        if mirror_config is not None:
            self._mirror_lcd_hline_with_config(mirror_config, pc, x0, y, width, color)
        self.uc.mem_write(va_to_phys(dest), struct.pack("<H", color) * width)
        self._mark_framebuffer_dirty(pc, dest, byte_count, "surface-hline")
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
        if count > 0x400:
            return False
        surface_desc = self._surface_pitch_buffer(surface)
        if surface_desc is None:
            return False
        pitch, buffer_va = surface_desc
        x = (x_base + index) & 0xFFFFFFFF
        if x > 0xFFFF or y > 0xFFFF:
            return False
        src_size = count * 2
        dest = (buffer_va + y * pitch + x * 2) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(src_va, src_size) or not self._is_mapped_ram_va(dest, src_size):
            return False
        colors = self._read_block_va_safe(src_va, src_size)
        if len(colors) != src_size:
            return False
        self.uc.mem_write(va_to_phys(dest), colors)
        self._mark_framebuffer_dirty(pc, dest, src_size, "surface-color-span")
        mirror_config = self._lcd_mirror_config()
        if mirror_config is not None:
            self._mirror_lcd_span_bytes_with_config(mirror_config, pc, x, y, colors)

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

    def _handle_surface_read_span_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8012BFE8:
            return False
        surface = self.uc.reg_read(UC_MIPS_REG_21) & 0xFFFFFFFF  # s5
        x_base = self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF  # s3
        y = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF  # s2
        index = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF  # s1
        width = self.uc.reg_read(UC_MIPS_REG_20) & 0xFFFFFFFF  # s4
        dst_va = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF  # s0
        if index >= width:
            return False
        count = width - index
        if count > 0x400:
            return False
        surface_desc = self._surface_pitch_buffer(surface)
        if surface_desc is None:
            return False
        pitch, buffer_va = surface_desc
        x = (x_base + index) & 0xFFFFFFFF
        if x > 0xFFFF or y > 0xFFFF:
            return False
        size = count * 2
        src_va = (buffer_va + y * pitch + x * 2) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(src_va, size) or not self._is_mapped_ram_va(dst_va, size):
            return False
        data = self._read_block_va_safe(src_va, size)
        if len(data) != size:
            return False
        self.uc.mem_write(va_to_phys(dst_va), data)

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
        last = struct.unpack_from("<H", data, size - 2)[0]
        self.uc.reg_write(UC_MIPS_REG_2, last)
        self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x30) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_31, ra)
        self.uc.reg_write(UC_MIPS_REG_PC, ra)
        self.surface_read_span_accel_count += 1
        self._record_surface_event(
            "read-span",
            pc,
            surface=surface,
            buffer=buffer_va,
            x=x,
            y=y,
            width=count,
            height=1,
            pitch=pitch,
            addr=dst_va,
        )
        return True

    def _surface_block_args(self, pc: int) -> tuple[int, int, int, int, int, int, int, int, int] | None:
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
        surface_desc = self._surface_pitch_buffer(surface)
        if surface_desc is None:
            return None
        pitch, surface_buffer = surface_desc
        if width * 2 > pitch:
            return None
        if not self._is_mapped_ram_va(buffer_va, (height - 1) * stride + width * 2):
            return None
        source_end = surface_buffer + (y + height - 1) * pitch + (x + width) * 2
        if not self._is_mapped_ram_va(surface_buffer + y * pitch + x * 2, width * 2):
            return None
        if not self._is_mapped_ram_va(source_end - width * 2, width * 2):
            return None
        return surface, x, y, width, height, buffer_va, stride, pitch, surface_buffer

    def _handle_surface_block_read(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8012C3D0:
            return False
        args = self._surface_block_args(pc)
        if args is None:
            return False
        surface, x, y, width, height, buffer_va, stride, pitch, surface_buffer = args
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
        surface, x, y, width, height, buffer_va, stride, pitch, surface_buffer = args
        row_bytes = width * 2
        mirror_config = self._lcd_mirror_config()
        for row in range(height):
            src = buffer_va + row * stride
            dst = surface_buffer + (y + row) * pitch + x * 2
            data = self._read_block_va_safe(src, row_bytes)
            if data is None:
                return False
            self.uc.mem_write(va_to_phys(dst), data)
            if mirror_config is not None:
                self._mirror_lcd_span_bytes_with_config(mirror_config, pc, x, y + row, data)
        self._mark_framebuffer_dirty(pc, surface_buffer + y * pitch + x * 2, row_bytes * height, "surface-block-write")
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

