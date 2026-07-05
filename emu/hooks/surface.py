"""Surface, LCD mirror, and framebuffer dirty helpers for the BBK 9588 emulator."""

from __future__ import annotations

# 本文件负责图形/Surface 相关 hook：
# - `_handle_surface_*` 和 blit/copy handler 是固件绘图函数的加速等效实现。
# - LCD mirror 和 framebuffer dirty 是模拟器前端需要的观测/同步层。
# - 这些 hook 不模拟 LCD 控制器寄存器；LCD/MMIO 状态仍由设备模型处理。
# - 所有绘图加速必须保持 surface buffer、镜像 framebuffer 和返回寄存器一致。

import struct
import time

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
    UC_MIPS_REG_22,
    UC_MIPS_REG_23,
    UC_MIPS_REG_29,
    UC_MIPS_REG_30,
    UC_MIPS_REG_31,
    UC_MIPS_REG_PC,
)

from emu.tools.utils import va_to_phys

IMMEDIATE_FRAME_DIRTY_REASONS = frozenset(
    {
        "logo-strip-blit",
        "fullscreen-fill",
        "boot-frame-copy",
        "portrait-blit",
        "surface-hline",
        "surface-color-span",
        "surface-block-write",
        "surface-transparent-blit",
    }
)

SURFACE_TRANSPARENT_BLIT_PCS = frozenset(
    {
        0x8012C46C,
        0x8012C4C0,
        0x8012C4C8,
        0x8012C4D0,
        0x8012C4D4,
        0x8012C4D8,
        0x8012C4DC,
        0x8012C4E0,
        0x8012C4E4,
        0x8012C4E8,
        0x8012C4F0,
        0x8012C4F8,
        0x8012C4FC,
        0x8012C504,
        0x8012C508,
        0x8012C510,
    }
)


class HwEmuSurfaceMixin:
    # Surface hook 由 `engine.py` 在固定绘图 PC 上调用。它们的作用是跳过
    # 固件逐像素循环，同时保留画面结果和前端刷新通知。
    def _perf_add(self, name: str, elapsed: float, *, size: int = 0, count: int = 1) -> None:
        stats = getattr(self, "perf_counters", None)
        if stats is None:
            stats = {}
            self.perf_counters = stats
        row = stats.get(name)
        if row is None:
            row = {"count": 0, "seconds": 0.0, "bytes": 0}
            stats[name] = row
        row["count"] = int(row.get("count", 0)) + int(count)
        row["seconds"] = float(row.get("seconds", 0.0)) + float(elapsed)
        row["bytes"] = int(row.get("bytes", 0)) + int(size)

    @staticmethod
    def _reverse_rgb565_pairs(data: bytes) -> bytes:
        return memoryview(data).cast("H")[::-1].tobytes()

    def _lcd_mirror_config(self) -> tuple[int, int, int, bool] | None:
        if (self._read_u32_va_safe(0x80474040) or 0) == 0:
            return None
        config = self._read_block_va_safe(0x804A6B88, 0xE0)
        if config is None or len(config) != 0xE0:
            return None
        width = struct.unpack_from("<H", config, 0x00)[0]
        height = struct.unpack_from("<H", config, 0x04)[0]
        fb = struct.unpack_from("<I", config, 0xD8)[0]
        if width == 0 or height == 0 or fb == 0:
            return None
        reverse = bool(config[0xDC])
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
        mark_dirty: bool = True,
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
            span = self._reverse_rgb565_pairs(span)
        else:
            dest_x = x0 + start
        dest = (fb + ((my * width + dest_x) << 1)) & 0xFFFFFFFF
        if self._is_mapped_ram_va(dest, len(span)):
            self.uc.mem_write(va_to_phys(dest), span)
            if mark_dirty:
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

    def _mirror_lcd_row_spans_with_config(
        self,
        config: tuple[int, int, int, bool],
        pc: int,
        x: int,
        y: int,
        spans: list[tuple[int, bytes]],
    ) -> None:
        if not spans:
            return
        if len(spans) == 1:
            start_px, span = spans[0]
            self._mirror_lcd_span_bytes_with_config(config, pc, x + start_px, y, span, mark_dirty=False)
            return

        width, height, fb, reverse = config
        my = height - int(y) - 1
        if my < 0 or my >= height:
            return
        row_dest = (fb + my * width * 2) & 0xFFFFFFFF
        row_bytes = width * 2
        if not self._is_mapped_ram_va(row_dest, row_bytes):
            return
        row_data = self._read_block_va_safe(row_dest, row_bytes)
        if row_data is None or len(row_data) != row_bytes:
            return
        merged = bytearray(row_data)
        x_base = int(x)
        changed = False
        for start_px, span in spans:
            count = len(span) // 2
            if count <= 0:
                continue
            x0 = x_base + start_px
            start = max(0, -x0)
            end = min(count, width - x0)
            if start >= end:
                continue
            clipped = span[start * 2 : end * 2]
            if reverse:
                dest_x = width - x0 - end
                clipped = self._reverse_rgb565_pairs(clipped)
            else:
                dest_x = x0 + start
            off = dest_x * 2
            merged[off : off + len(clipped)] = clipped
            changed = True
        if changed:
            self.uc.mem_write(va_to_phys(row_dest), bytes(merged))

    def _write_surface_row_spans(self, dest_row: int, row_bytes: int, spans: list[tuple[int, bytes]]) -> bool:
        if not spans:
            return True
        if len(spans) == 1:
            start_byte, span = spans[0]
            self.uc.mem_write(va_to_phys(dest_row + start_byte), span)
            return True

        if not self._is_mapped_ram_va(dest_row, row_bytes):
            return False
        row_data = self._read_block_va_safe(dest_row, row_bytes)
        if row_data is None or len(row_data) != row_bytes:
            return False
        merged = bytearray(row_data)
        for start_byte, span in spans:
            merged[start_byte : start_byte + len(span)] = span
        self.uc.mem_write(va_to_phys(dest_row), bytes(merged))
        return True

    def _mark_framebuffer_dirty(self, pc: int, addr: int, size: int, reason: str) -> None:
        # 观测/前端同步 hook：记录 framebuffer 被改动的位置，必要时立即推送画面。
        self.framebuffer_dirty_seq = (self.framebuffer_dirty_seq + 1) & 0xFFFFFFFF
        self.framebuffer_dirty_last_raw = (
            self.framebuffer_dirty_seq,
            pc & 0xFFFFFFFF,
            addr & 0xFFFFFFFF,
            size,
            reason,
        )
        callback = getattr(self, "framebuffer_dirty_callback", None)
        if reason == "lcd-mirror":
            pass
        elif reason not in IMMEDIATE_FRAME_DIRTY_REASONS:
            callback = None
        if callback is not None:
            try:
                callback(self.framebuffer_dirty_seq, pc & 0xFFFFFFFF, addr & 0xFFFFFFFF, size, reason)
            except Exception as exc:
                self._trace_event("frame-dirty-callback-error", pc=pc, addr=addr, size=size, value=type(exc).__name__)

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
        # 绘图加速 hook：等价实现固件 setpixel 函数。
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
        return_pc = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
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
        if return_pc in SURFACE_TRANSPARENT_BLIT_PCS and self._handle_surface_transparent_blit(return_pc):
            return True
        self.uc.reg_write(UC_MIPS_REG_PC, return_pc)
        return True

    def _handle_surface_hline(self, pc: int) -> bool:
        # 绘图加速 hook：等价实现固件水平线绘制函数。
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
        # 绘图循环加速 hook：批量写入一段 RGB565 像素。
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
        # 绘图读回加速 hook：批量从 surface 读取一段 RGB565 像素。
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
        # 块读取加速 hook：等价实现 surface rectangle read。
        if not self.fast_hooks or pc != 0x8012C3D0:
            return False
        args = self._surface_block_args(pc)
        if args is None:
            return False
        surface, x, y, width, height, buffer_va, stride, pitch, surface_buffer = args
        row_bytes = width * 2
        src0 = surface_buffer + y * pitch + x * 2
        if stride == row_bytes and pitch == row_bytes:
            data = self._read_block_va_safe(src0, row_bytes * height)
            if data is None:
                return False
            self.uc.mem_write(va_to_phys(buffer_va), data)
        else:
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
        # 块写入加速 hook：等价实现 surface rectangle write，并标记画面 dirty。
        if not self.fast_hooks or pc != 0x8012C1BC:
            return False
        args = self._surface_block_args(pc)
        if args is None:
            return False
        surface, x, y, width, height, buffer_va, stride, pitch, surface_buffer = args
        row_bytes = width * 2
        mirror_config = self._lcd_mirror_config()
        dest0 = surface_buffer + y * pitch + x * 2
        if mirror_config is None and stride == row_bytes and pitch == row_bytes:
            data = self._read_block_va_safe(buffer_va, row_bytes * height)
            if data is None:
                return False
            self.uc.mem_write(va_to_phys(dest0), data)
        else:
            for row in range(height):
                src = buffer_va + row * stride
                dst = surface_buffer + (y + row) * pitch + x * 2
                data = self._read_block_va_safe(src, row_bytes)
                if data is None:
                    return False
                self.uc.mem_write(va_to_phys(dst), data)
                if mirror_config is not None:
                    self._mirror_lcd_span_bytes_with_config(mirror_config, pc, x, y + row, data)
        self._mark_framebuffer_dirty(pc, dest0, row_bytes * height, "surface-block-write")
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

    def _handle_surface_transparent_blit(self, pc: int) -> bool:
        # 透明 blit 加速 hook：跳过透明色像素，批量写非透明 span。
        if not self.fast_hooks or pc not in SURFACE_TRANSPARENT_BLIT_PCS:
            return False
        perf_start = time.perf_counter()
        sp = self.uc.reg_read(UC_MIPS_REG_29) & 0xFFFFFFFF
        at_entry = pc == 0x8012C46C
        if at_entry:
            surface = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
            x = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
            y = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
            width = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
            height = self._read_u32_va_safe(sp + 0x10)
            src_va = self._read_u32_va_safe(sp + 0x14)
            stride = self._read_u32_va_safe(sp + 0x18)
            transparent = self._read_u32_va_safe(sp + 0x1C)
        else:
            surface = self.uc.reg_read(UC_MIPS_REG_30) & 0xFFFFFFFF
            x = self.uc.reg_read(UC_MIPS_REG_23) & 0xFFFFFFFF
            y = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
            width = self.uc.reg_read(UC_MIPS_REG_22) & 0xFFFFFFFF
            height = self.uc.reg_read(UC_MIPS_REG_20) & 0xFFFFFFFF
            src_va = self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF
            stride = self._read_u32_va_safe(sp + 0x58)
            transparent = self.uc.reg_read(UC_MIPS_REG_21) & 0xFFFFFFFF
        if height is None or src_va is None or stride is None or transparent is None:
            return False
        if width == 0 or height == 0 or width > 4096 or height > 4096:
            return False
        if stride < width * 2 or stride > 0x20000:
            return False
        if x & 0x80000000 or y & 0x80000000:
            return False
        surface_desc = self._surface_pitch_buffer(surface)
        if surface_desc is None:
            return False
        pitch, surface_buffer = surface_desc
        row_bytes = width * 2
        if row_bytes > pitch:
            return False
        if not self._is_mapped_ram_va(src_va, (height - 1) * stride + row_bytes):
            return False
        first_dest = surface_buffer + y * pitch + x * 2
        last_dest = surface_buffer + (y + height - 1) * pitch + x * 2
        if not self._is_mapped_ram_va(first_dest, row_bytes) or not self._is_mapped_ram_va(last_dest, row_bytes):
            return False

        transparent &= 0xFFFF
        mirror_config = self._lcd_mirror_config()
        pixels_written = 0
        dirty = False
        transparent_bytes = struct.pack("<H", transparent)
        full_row_count = 0
        span_row_count = 0
        source_size = (height - 1) * stride + row_bytes
        source_blob = None
        if source_size <= 0x400000:
            source_blob = self._read_block_va_safe(src_va, source_size)
            if source_blob is not None and len(source_blob) != source_size:
                source_blob = None
        for row in range(height):
            row_offset = row * stride
            if source_blob is None:
                src = src_va + row_offset
                data = self._read_block_va_safe(src, row_bytes)
                if data is None or len(data) != row_bytes:
                    return False
            else:
                data = source_blob[row_offset : row_offset + row_bytes]
            dest_row = surface_buffer + (y + row) * pitch + x * 2
            if data.find(transparent_bytes) < 0:
                self.uc.mem_write(va_to_phys(dest_row), data)
                if mirror_config is not None:
                    self._mirror_lcd_span_bytes_with_config(mirror_config, pc, x, y + row, data, mark_dirty=False)
                pixels_written += width
                dirty = True
                full_row_count += 1
                continue

            row_spans: list[tuple[int, bytes]] = []
            mirror_spans: list[tuple[int, bytes]] = []
            span_start = 0
            search = 0
            while search < row_bytes:
                hit = data.find(transparent_bytes, search)
                if hit < 0:
                    hit = row_bytes
                elif hit & 1:
                    search = hit + 1
                    continue
                if hit > span_start:
                    span = data[span_start:hit]
                    row_spans.append((span_start, span))
                    if mirror_config is not None:
                        mirror_spans.append((span_start // 2, span))
                    pixels_written += (hit - span_start) // 2
                    dirty = True
                if hit >= row_bytes:
                    break
                search = hit + 2
                span_start = search
            if row_spans and not self._write_surface_row_spans(dest_row, row_bytes, row_spans):
                return False
            if mirror_config is not None and mirror_spans:
                self._mirror_lcd_row_spans_with_config(mirror_config, pc, x, y + row, mirror_spans)
            if row_spans:
                span_row_count += 1

        if dirty:
            if mirror_config is not None:
                mirror_width, mirror_height, mirror_fb, _mirror_reverse = mirror_config
                self._mark_framebuffer_dirty(pc, mirror_fb, mirror_width * mirror_height * 2, "surface-transparent-blit")
            else:
                dirty_addr = surface_buffer + y * pitch + x * 2
                dirty_size = (height - 1) * pitch + row_bytes
                self._mark_framebuffer_dirty(pc, dirty_addr, dirty_size, "surface-transparent-blit")

        if at_entry:
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        else:
            restore_slots = (
                (UC_MIPS_REG_16, 0x18),
                (UC_MIPS_REG_17, 0x1C),
                (UC_MIPS_REG_18, 0x20),
                (UC_MIPS_REG_19, 0x24),
                (UC_MIPS_REG_20, 0x28),
                (UC_MIPS_REG_21, 0x2C),
                (UC_MIPS_REG_22, 0x30),
                (UC_MIPS_REG_23, 0x34),
                (UC_MIPS_REG_30, 0x38),
            )
            for reg, off in restore_slots:
                value = self._read_u32_va_safe(sp + off)
                if value is None:
                    return False
                self.uc.reg_write(reg, value)
            ra = self._read_u32_va_safe(sp + 0x3C)
            if ra is None or not (0x80000000 <= ra <= 0x81FFFFFF):
                return False
            self.uc.reg_write(UC_MIPS_REG_31, ra)
            self.uc.reg_write(UC_MIPS_REG_29, (sp + 0x40) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_PC, ra)
        self.surface_transparent_blit_accel_count += 1
        self._record_surface_event(
            "transparent-blit",
            pc,
            surface=surface,
            buffer=surface_buffer,
            x=x,
            y=y,
            width=width,
            height=height,
            pitch=pitch,
            color=transparent,
            addr=src_va,
        )
        if self.surface_transparent_blit_accel_count <= 32 or self.surface_transparent_blit_accel_count % 4096 == 0:
            self._trace_event(
                "surface-transparent-blit",
                pc=pc,
                addr=src_va,
                value=(x & 0xFFFF) | ((y & 0xFFFF) << 16),
                size=pixels_written,
                width=width,
                height=height,
            )
        self._perf_add(
            "surface_transparent_blit",
            time.perf_counter() - perf_start,
            size=width * height * 2,
        )
        if full_row_count:
            self._perf_add("surface_transparent_blit_full_rows", 0.0, count=full_row_count, size=full_row_count * row_bytes)
        if span_row_count:
            self._perf_add("surface_transparent_blit_span_rows", 0.0, count=span_row_count, size=span_row_count * row_bytes)
        if source_blob is not None:
            self._perf_add("surface_transparent_blit_source_bulk", 0.0, size=source_size)
        return True

