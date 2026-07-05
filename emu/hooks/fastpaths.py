"""Behavior-preserving hot-path accelerators for the BBK 9588 emulator."""

from __future__ import annotations

# 本文件实现“加速等效 hook”。这些 hook 不模拟单个硬件寄存器，也不是纯观测；
# 它们在已知固件 PC 上接管热点函数/循环，用 Python 一次完成与固件路径等价的
# 内存、寄存器和 PC 更新。边界条件不确定时必须返回 False，交回原固件执行。
#
# 主要覆盖：
# - 块设备、FAT16、目录项、长文件名、资源缓存等系统固件 I/O 热点。
# - memset/memcpy、byte/halfword/row/raster/glyph copy 等内存搬运热点。
# - boot/logo/fullscreen/portrait blit 等图形热点，并同步 framebuffer dirty。
# - busy delay、no-event poll、malloc/free scan 等确定性轮询/扫描热点。

import struct

from unicorn.mips_const import (
    UC_MIPS_REG_2,
    UC_MIPS_REG_3,
    UC_MIPS_REG_4,
    UC_MIPS_REG_5,
    UC_MIPS_REG_6,
    UC_MIPS_REG_7,
    UC_MIPS_REG_8,
    UC_MIPS_REG_10,
    UC_MIPS_REG_11,
    UC_MIPS_REG_12,
    UC_MIPS_REG_13,
    UC_MIPS_REG_14,
    UC_MIPS_REG_16,
    UC_MIPS_REG_17,
    UC_MIPS_REG_18,
    UC_MIPS_REG_19,
    UC_MIPS_REG_20,
    UC_MIPS_REG_21,
    UC_MIPS_REG_22,
    UC_MIPS_REG_23,
    UC_MIPS_REG_24,
    UC_MIPS_REG_30,
    UC_MIPS_REG_31,
    UC_MIPS_REG_PC,
    UC_MIPS_REG_SP,
)

from emu.tools.utils import va_to_phys

PORTRAIT_BLIT_LOOP_PCS = frozenset(
    {
        0x8012C914,
        0x8012C920,
        0x8012C928,
        0x8012C92C,
        0x8012C930,
        0x8012C934,
        0x8012C938,
        0x8012C93C,
        0x8012C940,
        0x8012C944,
        0x8012C948,
        0x8012C94C,
        0x8012C954,
        0x8012C958,
        0x8012C95C,
        0x8012C960,
    }
)


class HwEmuFastpathMixin:
    # 本 mixin 的 `_handle_*` 都由 `engine.py` 的 code hook 调用。命名里带
    # `block`/`fat`/`surface` 的函数常常模拟的是“固件函数效果”，不是物理硬件
    # 总线；真正的硬件 MMIO 模型在 `devices.py` 和 `engine._on_mem()`。
    def _read_c_string_bytes_va_safe(self, va: int, limit: int = 4096) -> bytes | None:
        if not self._is_mapped_ram_va(va, 1):
            return None
        out = bytearray()
        for offset in range(max(0, limit)):
            data = self._read_block_va_safe((va + offset) & 0xFFFFFFFF, 1)
            if data is None:
                return None
            value = data[0]
            if value == 0:
                return bytes(out)
            out.append(value)
        return None

    def _handle_bda_bounded_cstr_search(self, pc: int) -> bool:
        """加速等效 hook：替代 native BDA runtime 的有界 C 字符串搜索 helper。"""
        if not self.fast_hooks or pc not in (0x81C0756C, 0x81C1281C):
            return False
        haystack_va = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        needle_va = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        limit = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        if limit == 0 or limit > 0x02000000:
            return False
        if not self._is_mapped_ram_va(haystack_va, limit):
            return False
        needle = self._read_c_string_bytes_va_safe(needle_va, 4096)
        if needle is None:
            return False

        if not needle:
            result = haystack_va
        else:
            haystack = self._read_block_va_safe(haystack_va, limit)
            if haystack is None:
                return False
            index = haystack.find(needle)
            result = 0 if index < 0 else (haystack_va + index) & 0xFFFFFFFF

        count = getattr(self, "bda_cstr_search_accel_count", 0) + 1
        self.bda_cstr_search_accel_count = count
        self.uc.reg_write(UC_MIPS_REG_2, result)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        if count <= 16 or count % 1024 == 0:
            self._trace_event(
                "bda-cstr-search",
                pc=pc,
                addr=haystack_va,
                value=needle_va,
                size=limit,
                result=result,
            )
        return True

    def _backing_sector_capacity(self) -> int | None:
        if self.block_data is not None:
            return len(self.block_data) // 512
        if self.nand_data is None:
            return None
        sector0 = self._nand_fat_sector0_index()
        if sector0 is None:
            return None
        sectors_per_page = self.nand_page_size // 512
        stride = self.nand_page_size + self.nand_spare_size
        if sectors_per_page <= 0 or stride <= 0:
            return None
        total_sectors = (len(self.nand_data) // stride) * sectors_per_page
        if total_sectors <= sector0:
            return None
        return total_sectors - sector0

    def _handle_block_image_hook(self, pc: int) -> bool:
        if self.block_data is None and self.nand_data is None:
            return False
        if pc == 0x80182D58:
            capacity = self._backing_sector_capacity()
            if capacity is None:
                return False
            value = (capacity * 512) & 0xFFFFFFFF
            self.uc.reg_write(UC_MIPS_REG_2, value)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self._trace_event("block-size-hook", pc=pc, value=value)
            return True
        if pc not in (0x80182A90, 0x80182BF4):
            return False

        dest_va = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        offset = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        raw_length = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        source_offset = offset * 512
        length = raw_length * 512
        ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF
        capacity = self._backing_sector_capacity()
        ok = capacity is not None and offset <= capacity and raw_length <= capacity - offset
        copied = 0
        dest_phys = va_to_phys(dest_va)
        op = "read" if pc == 0x80182A90 else "write"
        preview = ""
        sp = self.uc.reg_read(UC_MIPS_REG_SP) & 0xFFFFFFFF
        caller_ra = self._read_u32_va_safe((sp + 0x2C) & 0xFFFFFFFF)
        if ok and op == "read" and self.block_data is not None:
            data = bytes(self.block_data[source_offset : source_offset + length])
            self.uc.mem_write(dest_phys, data)
            result = 0
            copied = len(data)
            preview = data[:16].hex()
        elif ok and op == "read":
            chunks = [self._read_backing_sector(offset + index) for index in range(raw_length)]
            if all(chunk is not None for chunk in chunks):
                data = b"".join(chunk for chunk in chunks if chunk is not None)
                self.uc.mem_write(dest_phys, data)
                result = 0
                copied = len(data)
                preview = data[:16].hex()
            else:
                result = 0xFFFFFFFF
        elif ok and op == "write":
            data = bytes(self.uc.mem_read(dest_phys, length))
            preview = data[:16].hex()
            wrote = 0
            for index in range(raw_length):
                sector_data = data[index * 512 : (index + 1) * 512]
                if len(sector_data) != 512 or not self._write_backing_sector(offset + index, sector_data):
                    break
                wrote += 1
            if wrote == raw_length:
                result = 0
                copied = len(data)
                self._invalidate_backing_cache_entries(offset, raw_length)
            else:
                result = 0xFFFFFFFF
        else:
            result = 0xFFFFFFFF
        self.block_io_accel_count += 1
        row: dict[str, str | int] = {
            "pc": f"0x{pc:08x}",
            "op": op,
            "dest_va": f"0x{dest_va:08x}",
            "dest_phys": f"0x{dest_phys:08x}",
            "offset": f"0x{offset:x}",
            "source_offset": f"0x{source_offset:x}",
            "raw_length": raw_length,
            "length": length,
            "copied": copied,
            "preview": preview,
            "result": f"0x{result:08x}",
            "ra": f"0x{ra:08x}",
            "caller_ra": "" if caller_ra is None else f"0x{caller_ra:08x}",
            "count": self.block_io_accel_count,
        }
        self.block_events.append(row)
        if len(self.block_events) > 128:
            del self.block_events[0]
        self.uc.reg_write(UC_MIPS_REG_2, result)
        self.uc.reg_write(UC_MIPS_REG_PC, ra)
        self._trace_event("block-image-hook", pc=pc, addr=dest_va, value=offset, size=length)
        return True

    def _handle_block_read_wrapper(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8017FBC0:
            return False
        if self.block_data is None and self.nand_data is None:
            return False

        mode = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        offset = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        raw_length = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        dest_va = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        ra = self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF

        # 0x8017FBC0 has more paths for mode 1 and uninitialized backing.
        # Accelerate only the direct block-read case; everything else stays
        # with the firmware implementation.
        if mode != 0:
            return False
        if self._read_u32_va_safe(0x804BF454) in (None, 0):
            return False
        if raw_length == 0:
            self.uc.reg_write(UC_MIPS_REG_2, 0)
            self.uc.reg_write(UC_MIPS_REG_PC, ra)
            self.block_read_wrapper_accel_count += 1
            return True

        length = raw_length * 512
        if length <= 0 or length > 0x02000000 or not self._is_mapped_ram_va_or_phys(dest_va, length):
            return False
        capacity = self._backing_sector_capacity()
        if capacity is None or offset > capacity or raw_length > capacity - offset:
            return False

        chunks = [self._read_backing_sector(offset + index) for index in range(raw_length)]
        if not all(chunk is not None for chunk in chunks):
            return False
        data = b"".join(chunk for chunk in chunks if chunk is not None)
        if len(data) != length:
            return False

        dest_phys = va_to_phys(dest_va)
        self.uc.mem_write(dest_phys, data)
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, ra)
        self.block_read_wrapper_accel_count += 1
        count = self.block_read_wrapper_accel_count
        if not self.suppress_hot_events or count <= 16 or count % 1024 == 0:
            row: dict[str, str | int] = {
                "pc": f"0x{pc:08x}",
                "op": "read-wrapper",
                "dest_va": f"0x{dest_va:08x}",
                "dest_phys": f"0x{dest_phys:08x}",
                "offset": f"0x{offset:x}",
                "raw_length": raw_length,
                "length": length,
                "copied": len(data),
                "preview": data[:16].hex(),
                "result": "0x00000000",
                "ra": f"0x{ra:08x}",
                "count": count,
            }
            self.block_events.append(row)
            if len(self.block_events) > 128:
                del self.block_events[0]
        self._trace_event("block-read-wrapper-hook", pc=pc, addr=dest_va, value=offset, size=length)
        return True

    def _handle_file_read_sector_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8017A3A0:
            return False
        if self.block_data is None and self.nand_data is None:
            return False

        drive_mode = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF  # s1
        remaining = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF  # s2
        sector = self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF  # s3
        sector_offset = self.uc.reg_read(UC_MIPS_REG_20) & 0xFFFFFFFF  # s4
        sector_index = self.uc.reg_read(UC_MIPS_REG_21) & 0xFFFFFFFF  # s5
        dest_va = self.uc.reg_read(UC_MIPS_REG_22) & 0xFFFFFFFF  # s6
        sectors_per_cluster = self.uc.reg_read(UC_MIPS_REG_30) & 0xFFFFFFFF  # fp
        sp = self.uc.reg_read(UC_MIPS_REG_SP) & 0xFFFFFFFF

        if drive_mode != 0 or sector_offset != 0:
            return False
        if remaining < 1024 or sectors_per_cluster <= 1 or sectors_per_cluster > 256:
            return False
        if sector_index >= sectors_per_cluster:
            return False

        current_cluster = self._read_u32_va_safe((sp + 0x210) & 0xFFFFFFFF)
        copied_so_far = self._read_u32_va_safe((sp + 0x214) & 0xFFFFFFFF)
        last_cluster = self._read_u32_va_safe((sp + 0x21C) & 0xFFFFFFFF)
        if current_cluster is None or copied_so_far is None or last_cluster is None:
            return False
        # The last cluster can contain a partial final sector. Leave it to the
        # firmware path so the original end-of-file arithmetic stays in charge.
        if current_cluster == last_cluster:
            return False

        sectors_to_cluster_end = sectors_per_cluster - sector_index
        sectors_to_copy = min(sectors_to_cluster_end, remaining // 512)
        if sectors_to_copy < 2:
            return False
        length = sectors_to_copy * 512
        if not self._is_mapped_ram_va_or_phys(dest_va, length):
            return False
        capacity = self._backing_sector_capacity()
        if capacity is None or sector > capacity or sectors_to_copy > capacity - sector:
            return False

        chunks = [self._read_backing_sector(sector + index) for index in range(sectors_to_copy)]
        if not all(chunk is not None for chunk in chunks):
            return False
        data = b"".join(chunk for chunk in chunks if chunk is not None)
        if len(data) != length:
            return False

        dest_phys = va_to_phys(dest_va)
        self.uc.mem_write(dest_phys, data)
        remaining_after = (remaining - length) & 0xFFFFFFFF
        copied_after = (copied_so_far + length) & 0xFFFFFFFF
        sector_after = (sector + sectors_to_copy) & 0xFFFFFFFF
        sector_index_after = (sector_index + sectors_to_copy) & 0xFFFFFFFF
        dest_after = (dest_va + length) & 0xFFFFFFFF

        self._write_u32_va((sp + 0x214) & 0xFFFFFFFF, copied_after)
        self.uc.reg_write(UC_MIPS_REG_18, remaining_after)
        self.uc.reg_write(UC_MIPS_REG_19, sector_after)
        self.uc.reg_write(UC_MIPS_REG_20, 0)
        self.uc.reg_write(UC_MIPS_REG_21, sector_index_after)
        self.uc.reg_write(UC_MIPS_REG_22, dest_after)
        self.file_read_loop_accel_count += 1
        row: dict[str, str | int] = {
            "pc": f"0x{pc:08x}",
            "dest_va": f"0x{dest_va:08x}",
            "sector": f"0x{sector:x}",
            "sectors": sectors_to_copy,
            "length": length,
            "remaining_before": remaining,
            "remaining_after": remaining_after,
            "cluster_index": current_cluster,
            "sector_index_before": sector_index,
            "sector_index_after": sector_index_after,
            "count": self.file_read_loop_accel_count,
        }
        self.file_read_loop_events.append(row)
        if len(self.file_read_loop_events) > 128:
            del self.file_read_loop_events[0]
        self._trace_event("file-read-sector-loop", pc=pc, addr=dest_va, value=sector, size=length)

        if remaining_after == 0:
            self.uc.reg_write(UC_MIPS_REG_PC, 0x8017A478)
        elif sector_index_after == sectors_per_cluster:
            self.uc.reg_write(UC_MIPS_REG_PC, 0x8017A41C)
        else:
            self.uc.reg_write(UC_MIPS_REG_PC, 0x8017A3A0)
        return True

    def _invalidate_backing_cache_entries(self, first_sector: int, sector_count: int) -> None:
        if sector_count <= 0:
            return
        last_sector = first_sector + sector_count - 1
        for slot in range(8):
            entry = 0x8086D180 + slot * 0x10
            sector = self._read_u32_va_safe(entry)
            if sector is None or not (first_sector <= sector <= last_sector):
                continue
            self._write_u32_va(entry, 0xFFFFFFFF)
            self._write_u32_va(entry + 8, 0)
            self._write_u32_va(entry + 0x0C, 0)

        # The cluster cache is keyed by cluster, not sector. A write is rare
        # compared with reads, so a full invalidation is simpler and safer.
        for slot in range(4):
            entry = 0x8086D200 + slot * 0x10
            if self._read_u32_va_safe(entry) is None:
                continue
            self._write_u32_va(entry, 0)
            self._write_u32_va(entry + 8, 0)
            self._write_u32_va(entry + 0x0C, 0)

    def _fat16_layout_from_block_image(self) -> dict[str, int] | None:
        if self.block_data is None:
            return None
        if self.fat16_layout_cache is not None:
            return self.fat16_layout_cache

        candidates = [0x20, 0]
        candidates.extend(lba for lba in range(1, min(0x100, len(self.block_data) // 512)) if lba not in candidates)
        for volume_lba in candidates:
            offset = volume_lba * 512
            if offset + 512 > len(self.block_data):
                continue
            boot = self.block_data[offset : offset + 512]
            if boot[510:512] != b"\x55\xaa":
                continue
            bytes_per_sector = struct.unpack_from("<H", boot, 0x0B)[0]
            sectors_per_cluster = boot[0x0D]
            reserved_sectors = struct.unpack_from("<H", boot, 0x0E)[0]
            fat_count = boot[0x10]
            root_entries = struct.unpack_from("<H", boot, 0x11)[0]
            total_sectors_16 = struct.unpack_from("<H", boot, 0x13)[0]
            sectors_per_fat_16 = struct.unpack_from("<H", boot, 0x16)[0]
            total_sectors_32 = struct.unpack_from("<I", boot, 0x20)[0]
            if bytes_per_sector != 512 or sectors_per_cluster == 0 or fat_count == 0 or sectors_per_fat_16 == 0:
                continue
            total_sectors = total_sectors_16 or total_sectors_32
            root_dir_sectors = ((root_entries * 32) + (bytes_per_sector - 1)) // bytes_per_sector
            fat_lba = volume_lba + reserved_sectors
            root_lba = fat_lba + fat_count * sectors_per_fat_16
            first_data_lba = root_lba + root_dir_sectors
            if first_data_lba >= total_sectors + volume_lba:
                continue
            self.fat16_layout_cache = {
                "volume_lba": volume_lba,
                "bytes_per_sector": bytes_per_sector,
                "sectors_per_cluster": sectors_per_cluster,
                "fat_lba": fat_lba,
                "root_lba": root_lba,
                "root_dir_sectors": root_dir_sectors,
                "first_data_lba": first_data_lba,
                "total_sectors": total_sectors,
            }
            return self.fat16_layout_cache
        return None

    def _fat16_layout_from_backing(self) -> dict[str, int] | None:
        if self.block_data is not None:
            return self._fat16_layout_from_block_image()
        if self.fat16_layout_cache is not None:
            return self.fat16_layout_cache

        candidates = [0x20, 0]
        candidates.extend(lba for lba in range(1, 0x100) if lba not in candidates)
        for volume_lba in candidates:
            boot = self._read_backing_sector(volume_lba)
            if boot is None or len(boot) < 512 or boot[510:512] != b"\x55\xaa":
                continue
            bytes_per_sector = struct.unpack_from("<H", boot, 0x0B)[0]
            sectors_per_cluster = boot[0x0D]
            reserved_sectors = struct.unpack_from("<H", boot, 0x0E)[0]
            fat_count = boot[0x10]
            root_entries = struct.unpack_from("<H", boot, 0x11)[0]
            total_sectors_16 = struct.unpack_from("<H", boot, 0x13)[0]
            sectors_per_fat_16 = struct.unpack_from("<H", boot, 0x16)[0]
            total_sectors_32 = struct.unpack_from("<I", boot, 0x20)[0]
            if bytes_per_sector != 512 or sectors_per_cluster == 0 or fat_count == 0 or sectors_per_fat_16 == 0:
                continue
            total_sectors = total_sectors_16 or total_sectors_32
            root_dir_sectors = ((root_entries * 32) + (bytes_per_sector - 1)) // bytes_per_sector
            fat_lba = volume_lba + reserved_sectors
            root_lba = fat_lba + fat_count * sectors_per_fat_16
            first_data_lba = root_lba + root_dir_sectors
            if first_data_lba >= total_sectors + volume_lba:
                continue
            self.fat16_layout_cache = {
                "volume_lba": volume_lba,
                "bytes_per_sector": bytes_per_sector,
                "sectors_per_cluster": sectors_per_cluster,
                "fat_lba": fat_lba,
                "root_lba": root_lba,
                "root_dir_sectors": root_dir_sectors,
                "first_data_lba": first_data_lba,
                "total_sectors": total_sectors,
            }
            return self.fat16_layout_cache
        return None

    def _nand_fat_sector0_index(self) -> int | None:
        if self.nand_data is None:
            return None
        if self.nand_fat_sector0_cache is not None:
            return self.nand_fat_sector0_cache
        stride = self.nand_page_size + self.nand_spare_size
        if stride <= 0:
            return None
        page_count = len(self.nand_data) // stride
        for page in range(page_count):
            page_off = page * stride
            body = self.nand_data[page_off : page_off + self.nand_page_size]
            for sector_in_page in range(self.nand_page_size // 512):
                off = sector_in_page * 512
                sector = body[off : off + 512]
                if len(sector) < 512 or sector[510:512] != b"\x55\xaa":
                    continue
                if sector[54:59] != b"FAT16" and sector[82:87] != b"FAT16":
                    continue
                hidden = struct.unpack_from("<I", sector, 28)[0]
                absolute_sector = page * (self.nand_page_size // 512) + sector_in_page
                sector0 = absolute_sector - hidden
                if sector0 >= 0:
                    self.nand_fat_sector0_cache = sector0
                    return sector0
        return None

    def _cached_backing_sector(self, sector: int) -> bytes | None:
        cache = getattr(self, "backing_sector_cache", None)
        if cache is None:
            return None
        data = cache.get(sector)
        if data is None:
            self.backing_sector_cache_misses = getattr(self, "backing_sector_cache_misses", 0) + 1
            return None
        self.backing_sector_cache_hits = getattr(self, "backing_sector_cache_hits", 0) + 1
        # dicts preserve insertion order; reinsert the hit to keep a tiny LRU.
        try:
            del cache[sector]
            cache[sector] = data
        except Exception:
            pass
        return data

    def _remember_backing_sector(self, sector: int, data: bytes) -> bytes:
        data = bytes(data[:512])
        if len(data) < 512:
            data = data.ljust(512, b"\x00")
        cache = getattr(self, "backing_sector_cache", None)
        if cache is None:
            return data
        cache[sector] = data
        limit = max(0, int(getattr(self, "backing_sector_cache_limit", 0)))
        while limit and len(cache) > limit:
            try:
                cache.pop(next(iter(cache)))
                self.backing_sector_cache_evictions = getattr(self, "backing_sector_cache_evictions", 0) + 1
            except StopIteration:
                break
        return data

    def _read_backing_sector(self, sector: int) -> bytes | None:
        if sector < 0:
            return None
        cached = self._cached_backing_sector(sector)
        if cached is not None:
            return cached
        override = self.block_sector_overrides.get(sector)
        if override is not None:
            if len(override) >= 512:
                return self._remember_backing_sector(sector, override[:512])
            return self._remember_backing_sector(sector, bytes(override).ljust(512, b"\x00"))
        if self.block_data is not None:
            offset = sector * 512
            if offset + 512 <= len(self.block_data):
                return self._remember_backing_sector(sector, self.block_data[offset : offset + 512])
            return None
        sector0 = self._nand_fat_sector0_index()
        if sector0 is None or self.nand_data is None:
            return None
        relative = sector0 + sector
        sectors_per_page = self.nand_page_size // 512
        if relative < 0 or sectors_per_page <= 0:
            return None
        page = relative // sectors_per_page
        sector_in_page = relative % sectors_per_page
        override = self.nand_page_overrides.get(page)
        if override is not None:
            page_data = override[: self.nand_page_size]
        else:
            stride = self.nand_page_size + self.nand_spare_size
            offset = page * stride
            if offset + self.nand_page_size > len(self.nand_data):
                return None
            page_data = self.nand_data[offset : offset + self.nand_page_size]
        off = sector_in_page * 512
        if off + 512 > len(page_data):
            return None
        return self._remember_backing_sector(sector, page_data[off : off + 512])

    def _write_backing_sector(self, sector: int, data: bytes) -> bool:
        if sector < 0 or len(data) != 512:
            return False
        if self.block_data is not None:
            offset = sector * 512
            if offset + 512 > len(self.block_data):
                return False
            data_bytes = self._remember_backing_sector(sector, data)
            self.block_data[offset : offset + 512] = data_bytes
            self.block_sector_overrides[sector] = data_bytes
            return True

        sector0 = self._nand_fat_sector0_index()
        if sector0 is None or self.nand_data is None:
            return False
        relative = sector0 + sector
        sectors_per_page = self.nand_page_size // 512
        if relative < 0 or sectors_per_page <= 0:
            return False
        page = relative // sectors_per_page
        sector_in_page = relative % sectors_per_page
        stride = self.nand_page_size + self.nand_spare_size
        page_offset = page * stride
        override = self.nand_page_overrides.get(page)
        if override is not None:
            page_data = bytearray(override)
        elif page_offset + stride <= len(self.nand_data):
            page_data = bytearray(self.nand_data[page_offset : page_offset + stride])
        elif page_offset + self.nand_page_size <= len(self.nand_data):
            page_data = bytearray(self.nand_data[page_offset : page_offset + self.nand_page_size])
        else:
            page_data = bytearray(b"\xFF" * stride)
        if len(page_data) < stride:
            page_data.extend(b"\xFF" * (stride - len(page_data)))
        off = sector_in_page * 512
        if off + 512 > self.nand_page_size:
            return False
        data_bytes = self._remember_backing_sector(sector, data)
        page_data[off : off + 512] = data_bytes
        self.block_sector_overrides[sector] = data_bytes
        self.nand_page_overrides[page] = bytes(page_data)
        if not self._is_readonly_nand_page(page):
            end_offset = page_offset + len(page_data)
            if end_offset > len(self.nand_data):
                self.nand_data.extend(b"\xFF" * (end_offset - len(self.nand_data)))
            self.nand_data[page_offset:end_offset] = page_data
        return True

    def _handle_fat16_cluster_read(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8017B4E0:
            return False
        layout = self._fat16_layout_from_backing()
        if layout is None:
            return False

        cluster = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        dest_va = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        if cluster < 2 or cluster >= 0xFFF8:
            return False

        sectors_per_read = self._read_mem_va(0x80474254, 1) & 0xFF if self._is_mapped_ram_va(0x80474254, 1) else 1
        if sectors_per_read == 0 or sectors_per_read > layout["sectors_per_cluster"]:
            sectors_per_read = layout["sectors_per_cluster"]
        length = sectors_per_read * layout["bytes_per_sector"]
        if length <= 0 or length > 0x20000 or not self._is_mapped_ram_va(dest_va, length):
            return False

        table = 0x8086D200 + ((cluster & 1) * 0x20)
        table_data = self._read_block_va_safe(table, 2 * 0x10)
        if table_data is None or len(table_data) != 2 * 0x10:
            return False
        for slot in range(2):
            entry = table + slot * 0x10
            entry_offset = slot * 0x10
            entry_cluster = struct.unpack_from("<I", table_data, entry_offset)[0]
            if entry_cluster != cluster:
                continue
            buffer_va = struct.unpack_from("<I", table_data, entry_offset + 4)[0]
            if not self._is_mapped_ram_va(buffer_va, length):
                return False
            data = self._read_block_va_safe(buffer_va, length)
            if data is None:
                return False
            self.uc.mem_write(va_to_phys(dest_va), data)
            hits = struct.unpack_from("<I", table_data, entry_offset + 8)[0] + 1
            self._write_u32_va(entry + 8, hits & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_2, 1)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self.cluster_read_accel_count += 1
            if (
                not self.suppress_hot_events
                or self.cluster_read_accel_count <= 16
                or self.cluster_read_accel_count % 1024 == 0
            ):
                row: dict[str, str | int] = {
                    "pc": f"0x{pc:08x}",
                    "cluster": f"0x{cluster:x}",
                    "dest_va": f"0x{dest_va:08x}",
                    "slot": slot,
                    "buffer": f"0x{buffer_va:08x}",
                    "length": length,
                    "preview": data[:16].hex(),
                    "count": self.cluster_read_accel_count,
                    "mode": "cache-hit",
                }
                self.cluster_read_events.append(row)
                if len(self.cluster_read_events) > 128:
                    del self.cluster_read_events[0]
            self._trace_event("fat16-cluster-read-cache-hit", pc=pc, addr=dest_va, value=cluster, size=length)
            return True

        lba = layout["first_data_lba"] + (cluster - 2) * layout["sectors_per_cluster"]
        chunks: list[bytes] = []
        for sector_index in range(sectors_per_read):
            sector_data = self._read_backing_sector(lba + sector_index)
            if sector_data is None:
                return False
            chunks.append(sector_data)
        data = b"".join(chunks)[:length]
        victim_slot: int | None = None
        victim_hits = 0xFFFFFFFF
        for slot in range(2):
            entry_offset = slot * 0x10
            hits = struct.unpack_from("<I", table_data, entry_offset + 8)[0]
            if hits <= victim_hits:
                victim_hits = hits
                victim_slot = slot
        cache_mode = "backing-read"
        cache_buffer = 0
        if victim_slot is not None and victim_hits != 1:
            entry = table + victim_slot * 0x10
            entry_offset = victim_slot * 0x10
            cache_buffer = struct.unpack_from("<I", table_data, entry_offset + 4)[0]
            if self._is_mapped_ram_va(cache_buffer, length):
                self.uc.mem_write(va_to_phys(cache_buffer), data)
                self._write_u32_va(entry, cluster)
                self._write_u32_va(entry + 8, 1)
                cache_mode = "miss-load"

        self.uc.mem_write(va_to_phys(dest_va), data)
        self.uc.reg_write(UC_MIPS_REG_2, 1)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)

        self.cluster_read_accel_count += 1
        if (
            not self.suppress_hot_events
            or self.cluster_read_accel_count <= 16
            or self.cluster_read_accel_count % 1024 == 0
        ):
            row: dict[str, str | int] = {
                "pc": f"0x{pc:08x}",
                "cluster": f"0x{cluster:x}",
                "dest_va": f"0x{dest_va:08x}",
                "lba": f"0x{lba:x}",
                "sectors": sectors_per_read,
                "length": length,
                "preview": data[:16].hex(),
                "count": self.cluster_read_accel_count,
                "mode": cache_mode,
            }
            if victim_slot is not None:
                row["slot"] = victim_slot
            if cache_buffer:
                row["buffer"] = f"0x{cache_buffer:08x}"
            self.cluster_read_events.append(row)
            if len(self.cluster_read_events) > 128:
                del self.cluster_read_events[0]
        self._trace_event("fat16-cluster-read", pc=pc, addr=dest_va, value=cluster, size=length)
        return True

    def _handle_resource_cache16_hit(self, pc: int) -> bool:
        if not self.fast_hooks or not self.resource_cache16_accelerator or pc != 0x8017CA10:
            return False
        if not self._read_u32_va_safe(0x804BF434):
            return False
        index = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        if index < 2:
            return False
        limit = self._read_u32_va_safe(0x80474264)
        if limit is not None and index >= ((limit + 2) & 0xFFFFFFFF):
            return False
        base_sector = self._read_u32_va_safe(0x80474260)
        if base_sector is None:
            return False
        sector = ((index >> 8) + base_sector) & 0xFFFFFFFF
        low = index & 0xFF
        table = 0x8086D180
        table_data = self._read_block_va_safe(table, 8 * 0x10)
        if table_data is None or len(table_data) != 8 * 0x10:
            return False
        for slot in range(8):
            entry = table + slot * 0x10
            entry_offset = slot * 0x10
            entry_sector = struct.unpack_from("<I", table_data, entry_offset)[0]
            if entry_sector != sector:
                continue
            buffer_va = struct.unpack_from("<I", table_data, entry_offset + 4)[0]
            data_va = (buffer_va + low * 2) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(data_va, 2):
                return False
            value_data = self._read_block_va_safe(data_va, 2)
            if value_data is None or len(value_data) != 2:
                return False
            value = struct.unpack_from("<H", value_data)[0]
            hits = struct.unpack_from("<I", table_data, entry_offset + 8)[0] + 1
            self._write_u32_va(entry + 8, hits & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_2, value)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self.resource_cache16_accel_count += 1
            if self.resource_cache16_accel_count <= 32 or self.resource_cache16_accel_count % 4096 == 0:
                row = {
                    "pc": f"0x{pc:08x}",
                    "index": f"0x{index:x}",
                    "sector": f"0x{sector:x}",
                    "slot": slot,
                    "buffer": f"0x{buffer_va:08x}",
                    "value": f"0x{value:04x}",
                    "count": self.resource_cache16_accel_count,
                }
                self.resource_cache16_events.append(row)
                if len(self.resource_cache16_events) > 128:
                    del self.resource_cache16_events[0]
            return True
        backing_sector = self._read_backing_sector(sector)
        if backing_sector is None:
            return False
        victim_slot: int | None = None
        victim_hits = 0xFFFFFFFF
        for slot in range(8):
            entry_offset = slot * 0x10
            hits = struct.unpack_from("<I", table_data, entry_offset + 8)[0]
            if hits <= victim_hits:
                victim_hits = hits
                victim_slot = slot
        if victim_slot is None:
            return False
        entry = table + victim_slot * 0x10
        entry_offset = victim_slot * 0x10
        buffer_va = struct.unpack_from("<I", table_data, entry_offset + 4)[0]
        dirty = struct.unpack_from("<I", table_data, entry_offset + 0x0C)[0]
        if dirty:
            # The firmware flushes dirty cache slots before reuse. Do not
            # shortcut that path until the writeback side is modeled.
            return False
        if not self._is_mapped_ram_va(buffer_va, 0x200):
            return False
        self.uc.mem_write(va_to_phys(buffer_va), backing_sector[:0x200])
        value = struct.unpack_from("<H", backing_sector, low * 2)[0]
        self._write_u32_va(entry, sector)
        self._write_u32_va(entry + 8, 1)
        self._write_u32_va(entry + 0x0C, 0)
        self.uc.reg_write(UC_MIPS_REG_2, value)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.resource_cache16_accel_count += 1
        if self.resource_cache16_accel_count <= 32 or self.resource_cache16_accel_count % 4096 == 0:
            row = {
                "pc": f"0x{pc:08x}",
                "index": f"0x{index:x}",
                "sector": f"0x{sector:x}",
                "slot": victim_slot,
                "buffer": f"0x{buffer_va:08x}",
                "value": f"0x{value:04x}",
                "count": self.resource_cache16_accel_count,
                "mode": "miss-load",
            }
            self.resource_cache16_events.append(row)
            if len(self.resource_cache16_events) > 128:
                del self.resource_cache16_events[0]
        return True

    def _handle_dirent_copy(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x80175E40:
            return False
        src = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        dst = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(src, 0x20) or not self._is_mapped_ram_va(dst, 0x20):
            return False
        data = self._read_block_va_safe(src, 0x20)
        if data is None:
            return False
        out = bytearray(0x20)
        out[0:8] = data[0:8]
        out[8:11] = data[8:11]
        out[0x0B] = data[0x0B]
        out[0x0C] = data[0x0C]
        out[0x0D] = data[0x0D]
        out[0x0E:0x10] = data[0x0E:0x10]
        out[0x10:0x12] = data[0x10:0x12]
        out[0x12:0x14] = data[0x12:0x14]
        high_cluster = struct.unpack_from("<H", data, 0x14)[0]
        low_cluster = struct.unpack_from("<H", data, 0x1A)[0]
        struct.pack_into("<I", out, 0x14, ((high_cluster << 16) | low_cluster) & 0xFFFFFFFF)
        out[0x18:0x1A] = data[0x16:0x18]
        out[0x1A:0x1C] = data[0x18:0x1A]
        out[0x1C:0x20] = data[0x1C:0x20]
        if out[0] == 5:
            out[0] = 0xE5
        self.uc.mem_write(va_to_phys(dst), bytes(out))
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.dirent_copy_accel_count += 1
        if (
            not self.suppress_hot_events
            or self.dirent_copy_accel_count <= 16
            or self.dirent_copy_accel_count % 1024 == 0
        ):
            row = {
                "pc": f"0x{pc:08x}",
                "src": f"0x{src:08x}",
                "dst": f"0x{dst:08x}",
                "name_hex": bytes(out[:11]).hex(),
                "attr": f"0x{out[0x0B]:02x}",
                "cluster": f"0x{struct.unpack_from('<I', out, 0x14)[0]:08x}",
                "size": f"0x{struct.unpack_from('<I', out, 0x1C)[0]:08x}",
                "first_byte": f"0x{out[0]:02x}",
                "count": self.dirent_copy_accel_count,
            }
            self.dirent_copy_events.append(row)
            if len(self.dirent_copy_events) > 128:
                del self.dirent_copy_events[0]
        return True

    def _handle_lfn_copy_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc not in (0x80174C9C, 0x80174CC0, 0x80174CE4):
            return False
        index = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        entry = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        dst = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        out_count = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        if pc == 0x80174C9C and index == 0:
            total = 26
            if not self._is_mapped_ram_va(entry, 0x20) or not self._is_mapped_ram_va(dst, total):
                return False
            if entry < (dst + total) and dst < (entry + 0x20):
                return False
            data = self._read_block_va_safe(entry, 0x20)
            if data is None or len(data) != 0x20:
                return False
            out = data[1:11] + data[0x0E:0x1A] + data[0x1C:0x20]
            self.uc.mem_write(va_to_phys(dst), out)
            self.uc.reg_write(UC_MIPS_REG_2, 0)
            self.uc.reg_write(UC_MIPS_REG_3, out[-1])
            self.uc.reg_write(UC_MIPS_REG_4, 4)
            self.uc.reg_write(UC_MIPS_REG_16, (dst + total) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_17, (out_count + total) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80174D04)
            self.lfn_copy_accel_count += 1
            self.lfn_copy_fused_accel_count = getattr(self, "lfn_copy_fused_accel_count", 0) + 1
            if self.lfn_copy_accel_count <= 16 or self.lfn_copy_accel_count % 1024 == 0:
                self._trace_event("lfn-copy-fused", pc=pc, addr=dst, value=entry, size=total)
            return True
        if pc == 0x80174C9C:
            limit, source_bias, target = 10, 1, 0x80174CBC
        elif pc == 0x80174CC0:
            limit, source_bias, target = 12, 0x0E, 0x80174CE0
        else:
            limit, source_bias, target = 4, 0x1C, 0x80174D04
        if index >= limit:
            self.uc.reg_write(UC_MIPS_REG_PC, target)
            return True
        count = limit - index
        src = (entry + source_bias + index) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(src, count) or not self._is_mapped_ram_va(dst, count):
            return False
        data = self._read_block_va_safe(src, count)
        if data is None or len(data) != count:
            return False
        self.uc.mem_write(va_to_phys(dst), data)
        self.uc.reg_write(UC_MIPS_REG_4, limit)
        self.uc.reg_write(UC_MIPS_REG_16, (dst + count) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_17, (out_count + count) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_PC, target)
        self.lfn_copy_accel_count += 1
        if self.lfn_copy_accel_count <= 16 or self.lfn_copy_accel_count % 1024 == 0:
            self._trace_event("lfn-copy-loop", pc=pc, addr=dst, value=entry, size=count)
        return True

    def _handle_stack_clear32_delay_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc not in (0x80173908, 0x80173C30):
            return False
        index_after_increment = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        if index_after_increment == 0 or index_after_increment > 0x20:
            return False
        dest = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        remaining = 0x21 - index_after_increment
        if remaining <= 0 or remaining > 0x20 or not self._is_mapped_ram_va(dest, remaining):
            return False
        self.uc.mem_write(va_to_phys(dest), b"\x00" * remaining)
        self.uc.reg_write(UC_MIPS_REG_2, 0x20)
        self.uc.reg_write(UC_MIPS_REG_3, 0)
        self.uc.reg_write(UC_MIPS_REG_4, (dest + remaining - 1) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_18, 0x20)
        self.uc.reg_write(UC_MIPS_REG_PC, (pc + 8) & 0xFFFFFFFF)
        self._trace_event("stack-clear32-delay-loop", pc=pc, addr=dest, size=remaining)
        return True

    def _handle_zero_fill_delay_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x80007900:
            return False
        total = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        index_after_increment = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        dest = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        if total == 0 or index_after_increment == 0 or index_after_increment > total or total > 0x10000:
            return False
        remaining = total - index_after_increment + 1
        if remaining <= 0 or not self._is_mapped_ram_va(dest, remaining):
            return False
        self.uc.mem_write(va_to_phys(dest), b"\x00" * remaining)
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_3, (dest + remaining - 1) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_6, total)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x80007908)
        self._trace_event("zero-fill-delay-loop", pc=pc, addr=dest, size=remaining)
        return True

    def _handle_zero_pad_delay_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8024227C:
            return False
        remaining_after_current = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        if remaining_after_current > 0x10000:
            return False
        dest = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        remaining = remaining_after_current + 1
        if not self._is_mapped_ram_va(dest, remaining):
            return False
        self.uc.mem_write(va_to_phys(dest), b"\x00" * remaining)
        self.uc.reg_write(UC_MIPS_REG_4, (dest + remaining_after_current) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_6, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x80242284)
        self._trace_event("zero-pad-delay-loop", pc=pc, addr=dest, size=remaining)
        return True

    def _handle_logo_strip_blit(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8001DF78:
            return False
        src = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF  # s0
        dst = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF  # s1
        width = 240
        height = 28
        row_bytes = width * 2
        if not self._is_mapped_ram_va(src, row_bytes * height):
            return False
        if not self._is_mapped_ram_va((dst - row_bytes * height + 2) & 0xFFFFFFFF, row_bytes * height):
            return False
        for row in range(height):
            data = self._read_block_va_safe(src + row * row_bytes, row_bytes)
            if data is None:
                return False
            out = bytearray(row_bytes)
            for x in range(width):
                out[x * 2 : x * 2 + 2] = data[(width - 1 - x) * 2 : (width - x) * 2]
            row_start = (dst - row * row_bytes - row_bytes + 2) & 0xFFFFFFFF
            self.uc.mem_write(va_to_phys(row_start), bytes(out))
            self._mark_framebuffer_dirty_if_overlaps(pc, row_start, row_bytes, "logo-strip-blit")
        self.uc.reg_write(UC_MIPS_REG_PC, 0x8001DF5C)
        self.logo_strip_blit_accel_count += 1
        return True

    def _handle_fullscreen_fill_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x800133EC:
            return False
        count = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        dst = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
        color = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFF
        if count == 0 or count > 240 * 320:
            return False
        if not self._is_mapped_ram_va(dst, count * 2):
            return False
        self.uc.mem_write(va_to_phys(dst), struct.pack("<H", color) * count)
        self._mark_framebuffer_dirty_if_overlaps(pc, dst, count * 2, "fullscreen-fill")
        self.uc.reg_write(UC_MIPS_REG_2, (dst + count * 2) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_3, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x800133FC)
        self._trace_event("fullscreen-fill-loop", pc=pc, addr=dst, size=count, value=color)
        return True

    def _handle_boot_frame_copy_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc not in (0x800128F4, 0x800128F8):
            return False
        row = self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF
        col = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        src = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        dest_ptr = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        row_base = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        if row >= 320 or col >= 240:
            return False
        if not self._is_mapped_ram_va(src, (320 * 240 - (row * 240 + col)) * 2):
            return False
        first_loaded = pc == 0x800128F8
        while row < 320:
            remaining_cols = 240 - col
            if remaining_cols <= 0:
                row += 1
                if row >= 320:
                    break
                row_base = (row_base - 0x1E0) & 0xFFFFFFFF
                dest_ptr = row_base
                col = 0
                continue
            read_src = src
            if first_loaded:
                first = struct.pack("<H", self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFF)
                read_src = (src + 2) & 0xFFFFFFFF
                tail_bytes = (remaining_cols - 1) * 2
                tail = b""
                if tail_bytes:
                    tail = self._read_block_va_safe(read_src, tail_bytes)
                    if tail is None or len(tail) != tail_bytes:
                        return False
                data = first + tail
                first_loaded = False
            else:
                data = self._read_block_va_safe(read_src, remaining_cols * 2)
                if data is None or len(data) != remaining_cols * 2:
                    return False
            out = bytearray(len(data))
            for i in range(remaining_cols):
                src_off = i * 2
                dst_off = (remaining_cols - 1 - i) * 2
                out[dst_off : dst_off + 2] = data[src_off : src_off + 2]
            row_dst = (dest_ptr - remaining_cols * 2) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(row_dst, remaining_cols * 2):
                return False
            self.uc.mem_write(va_to_phys(row_dst), bytes(out))
            self._mark_framebuffer_dirty_if_overlaps(pc, row_dst, remaining_cols * 2, "boot-frame-copy")
            src = (src + remaining_cols * 2) & 0xFFFFFFFF
            dest_ptr = row_dst
            col = 240
            row += 1
            if row >= 320:
                break
            row_base = (row_base - 0x1E0) & 0xFFFFFFFF
            dest_ptr = row_base
            col = 0
        self.uc.reg_write(UC_MIPS_REG_4, dest_ptr)
        self.uc.reg_write(UC_MIPS_REG_5, 240)
        self.uc.reg_write(UC_MIPS_REG_6, src)
        self.uc.reg_write(UC_MIPS_REG_7, row_base)
        self.uc.reg_write(UC_MIPS_REG_8, 320)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x80012920)
        self._trace_event("boot-frame-copy-loop", pc=pc, addr=dest_ptr, size=240 * 320, value=src)
        return True

    def _handle_malloc_scan_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x800074A0:
            return False
        count = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        index = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        s0 = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        request = (self.uc.reg_read(UC_MIPS_REG_4) + 3) & ~3
        if count == 0 or index >= count or request > 0x200000:
            return False
        found = None
        remaining = count - index
        scan = s0
        if remaining <= 128:
            low = (s0 - 8 * (remaining - 1) + 4) & 0xFFFFFFFF
            length = 8 * (remaining - 1) + 4
            high = (low + length) & 0xFFFFFFFF
            if high >= low and self._is_mapped_ram_va(low, length):
                data = self._read_block_va_safe(low, length)
                if data is not None and len(data) == length:
                    for offset_index in range(remaining):
                        current = index + offset_index
                        scan = (s0 - 8 * offset_index) & 0xFFFFFFFF
                        data_offset = 8 * (remaining - 1 - offset_index)
                        size_word = struct.unpack_from("<I", data, data_offset)[0]
                        if (size_word & 1) == 0 and size_word >= request:
                            found = (current, scan, size_word)
                            break
                    if found is None:
                        scan = (s0 - 8 * remaining) & 0xFFFFFFFF
                else:
                    return False
            else:
                remaining = 0
        else:
            remaining = 0
        if remaining == 0:
            scan = s0
            for current in range(index, count):
                size_word = self._read_u32_va_safe(scan + 4)
                if size_word is None:
                    return False
                if (size_word & 1) == 0 and size_word >= request:
                    found = (current, scan, size_word)
                    break
                scan = (scan - 8) & 0xFFFFFFFF
        if found is None:
            self.uc.reg_write(UC_MIPS_REG_5, count)
            self.uc.reg_write(UC_MIPS_REG_16, scan)
            self.uc.reg_write(UC_MIPS_REG_6, request)
            self.uc.reg_write(UC_MIPS_REG_2, request)
            self.uc.reg_write(UC_MIPS_REG_3, 0)
            self.uc.reg_write(UC_MIPS_REG_24, count)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x800074D4)
            self._trace_event("malloc-scan-loop", pc=pc, addr=s0, value=count - index, size=request)
            return True
        current, scan, size_word = found
        self.uc.reg_write(UC_MIPS_REG_5, current)
        self.uc.reg_write(UC_MIPS_REG_16, scan)
        self.uc.reg_write(UC_MIPS_REG_6, size_word)
        self.uc.reg_write(UC_MIPS_REG_17, request)
        self.uc.reg_write(UC_MIPS_REG_2, request | 1)
        self.uc.reg_write(UC_MIPS_REG_3, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x8000755C)
        self._trace_event("malloc-scan-hit-loop", pc=pc, addr=scan, value=size_word, size=request)
        return True

    def _handle_byte_copy_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8017B45C:
            return False
        count = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        src = self.uc.reg_read(UC_MIPS_REG_5) & 0xFFFFFFFF
        dst = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        original_dst = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        if count == 0 or count > 0x10000:
            return False
        if not self._is_mapped_ram_va(src, count) or not self._is_mapped_ram_va(dst, count):
            return False
        data = self._read_block_va_safe(src, count)
        if data is None:
            return False
        self.uc.mem_write(va_to_phys(dst), data)
        self._mark_framebuffer_dirty_if_overlaps(pc, dst, count, "byte-copy")
        self.uc.reg_write(UC_MIPS_REG_5, (src + count) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_6, 0)
        self.uc.reg_write(UC_MIPS_REG_3, (dst + count) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_2, original_dst)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self._trace_event("byte-copy-loop", pc=pc, addr=dst, size=count, value=src)
        return True

    def _handle_row_copy_loop_800b36d0(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x800B36D0:
            return False
        rows = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        dst = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        src_base = self.uc.reg_read(UC_MIPS_REG_22) & 0xFFFFFFFF
        src_off = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        row_bytes = self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF
        src_stride = self.uc.reg_read(UC_MIPS_REG_20) & 0xFFFFFFFF
        if rows == 0:
            self.uc.reg_write(UC_MIPS_REG_PC, 0x800B36F0)
            self.state.insn_count += 1
            self.row_copy_loop_accel_count += 1
            return True
        if rows > 0x1000 or row_bytes == 0 or row_bytes > 0x10000:
            return False
        total_src_span = src_off + (rows - 1) * src_stride + row_bytes
        total_dst_span = rows * row_bytes
        src_start = (src_base + src_off) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(src_base, total_src_span):
            return False
        if not self._is_mapped_ram_va(dst, total_dst_span):
            return False
        src_data = self._read_block_va_safe(src_base, total_src_span)
        if src_data is None:
            return False
        out = bytearray(total_dst_span)
        for row in range(rows):
            src_pos = src_off + row * src_stride
            dst_pos = row * row_bytes
            out[dst_pos : dst_pos + row_bytes] = src_data[src_pos : src_pos + row_bytes]
        self.uc.mem_write(va_to_phys(dst), bytes(out))
        self._mark_framebuffer_dirty_if_overlaps(pc, dst, total_dst_span, "row-copy-loop")
        self.uc.reg_write(UC_MIPS_REG_16, 0)
        self.uc.reg_write(UC_MIPS_REG_17, (dst + total_dst_span) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_18, (src_off + rows * src_stride) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_2, dst)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x800B36F0)
        self.row_copy_loop_accel_count += 1
        self._trace_event("row-copy-loop", pc=pc, addr=dst, value=src_start, size=total_dst_span)
        return True

    def _handle_portrait_blit_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc not in PORTRAIT_BLIT_LOOP_PCS:
            return False
        fb = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        src_base = self.uc.reg_read(UC_MIPS_REG_12) & 0xFFFFFFFF
        if not self._is_mapped_ram_va(fb, 240 * 320 * 2):
            fb = self._read_u32_va_safe(0x804A6C60) or 0
        if not self._is_mapped_ram_va(src_base, 240 * 320 * 2):
            src_base = 0x80825B90
        reverse = self._read_mem_va(0x804A6C64, 1) != 0
        if not self._is_mapped_ram_va(fb, 240 * 320 * 2):
            return False
        if not self._is_mapped_ram_va(src_base, 240 * 320 * 2):
            return False
        byte_count = 240 * 2
        frame_bytes = 240 * 320 * 2
        src_data = self._read_block_va_safe(src_base, frame_bytes)
        if src_data is None or len(src_data) != frame_bytes:
            return False
        frame = bytearray(frame_bytes)
        for y in range(320):
            row = src_data[y * byte_count : (y + 1) * byte_count]
            if reverse:
                row = memoryview(row).cast("H")[::-1].tobytes()
            dest_off = (319 - y) * byte_count
            frame[dest_off : dest_off + byte_count] = row
        self.uc.mem_write(va_to_phys(fb), bytes(frame))
        self._mark_framebuffer_dirty_if_overlaps(pc, fb, 240 * 320 * 2, "portrait-blit")
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self._trace_event("portrait-blit-loop", pc=pc, addr=fb, size=320 * 240, value=src_base)
        return True

    def _handle_cache_scan_tail(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8017BEF4:
            return False
        if self._fat16_layout_from_backing() is None:
            return False
        if (self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF) == 0:
            return False
        mode = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        scanned = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        limit = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        if mode != 0 or scanned >= limit or limit > 0x20000:
            return False
        self._write_u32_va(0x8047425C, 2)
        self.uc.reg_write(UC_MIPS_REG_17, limit)
        self.uc.reg_write(UC_MIPS_REG_2, self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x8017BF2C)
        self.cache_scan_tail_accel_count += 1
        self._trace_event("cache-scan-tail", pc=pc, size=limit - scanned, value=limit)
        return True

    def _handle_fat_free_scan_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x80172840:
            return False
        mode = self.uc.reg_read(UC_MIPS_REG_19) & 0xFFFFFFFF
        if mode != 0:
            return False
        current = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        limit = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        free_count = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        last_value = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFFFFFF
        if current > limit or limit - current > 0x200000:
            return False
        base_sector = self._read_u32_va_safe(0x80474260)
        if base_sector is None:
            return False
        if (last_value & 0xFFFF) == 0:
            free_count = (free_count + 1) & 0xFFFFFFFF
        if current == limit:
            remaining_free = 0
        else:
            start_byte = current * 2
            end_byte = limit * 2
            if start_byte > end_byte:
                return False
            remaining = bytearray()
            sector = base_sector + (start_byte // 512)
            offset = start_byte % 512
            while len(remaining) < (end_byte - start_byte):
                sector_data = self._read_backing_sector(sector)
                if sector_data is None:
                    return False
                chunk = sector_data[offset:]
                need = (end_byte - start_byte) - len(remaining)
                remaining += chunk[:need]
                sector += 1
                offset = 0
            table = bytes(remaining)
            remaining_free = sum(
                1 for index in range(0, len(table), 2) if table[index] == 0 and table[index + 1] == 0
            )
        if current > limit or limit - current > 0x200000:
            return False
        free_count = (free_count + remaining_free) & 0xFFFFFFFF
        self.uc.reg_write(UC_MIPS_REG_16, limit)
        self.uc.reg_write(UC_MIPS_REG_17, free_count)
        self.uc.reg_write(UC_MIPS_REG_4, 0)
        self.uc.reg_write(UC_MIPS_REG_3, free_count)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x801727E0)
        self._trace_event("fat-free-scan-loop", pc=pc, addr=current, value=limit, size=free_count)
        return True

    def _handle_free_scan_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x80006658:
            return False
        target = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        count = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF
        index = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
        scan = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        if target == 0 or count == 0 or index >= count or count > 0x10000:
            return False

        start_index = index
        found_index: int | None = None
        found_scan = scan
        while index < count:
            value = self._read_u32_va_safe(scan)
            if value is None:
                return False
            if value == target:
                found_index = index
                found_scan = scan
                break
            index += 1
            scan = (scan - 8) & 0xFFFFFFFF

        if found_index is None:
            self.uc.reg_write(UC_MIPS_REG_17, count)
            self.uc.reg_write(UC_MIPS_REG_16, scan)
            self.uc.reg_write(UC_MIPS_REG_5, count)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80006678)
            self._trace_event("free-scan-loop", pc=pc, addr=target, value=count - start_index, size=count)
        else:
            self.uc.reg_write(UC_MIPS_REG_17, found_index)
            self.uc.reg_write(UC_MIPS_REG_16, found_scan)
            self.uc.reg_write(UC_MIPS_REG_5, count)
            self.uc.reg_write(UC_MIPS_REG_PC, 0x80006690)
            self._trace_event(
                "free-scan-hit-loop",
                pc=pc,
                addr=target,
                value=found_index - start_index,
                size=count,
            )
        self.free_scan_accel_count += 1
        return True

    def _handle_halfword_copy_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc not in (0x8012B034, 0x8012B064, 0x8012B070):
            return False
        if pc == 0x8012B070:
            remaining = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF  # a3, already decremented by the loop body
            if remaining > 0x20000:
                return False
            dst = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF  # a0
            src = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF  # v1, already advanced past the pending store
            current = self.uc.reg_read(UC_MIPS_REG_2) & 0xFFFF  # v0
            total_size = (remaining + 1) * 2
            if not self._is_mapped_ram_va(dst, total_size):
                return False
            if remaining and not self._is_mapped_ram_va(src, remaining * 2):
                return False
            out = bytearray(current.to_bytes(2, "little"))
            if remaining:
                rest = self._read_block_va_safe(src, remaining * 2)
                if len(rest) != remaining * 2:
                    return False
                out.extend(rest)
                last = struct.unpack_from("<H", rest, len(rest) - 2)[0]
            else:
                last = current
            self.uc.mem_write(va_to_phys(dst), bytes(out))
            self._mark_framebuffer_dirty_if_overlaps(pc, dst, total_size, "halfword-copy-delay")
            self.uc.reg_write(UC_MIPS_REG_2, last)
            self.uc.reg_write(UC_MIPS_REG_3, (src + remaining * 2) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_4, (dst + total_size) & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_7, 0)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self.halfword_copy_accel_count += 1
            if self.halfword_copy_accel_count <= 32 or self.halfword_copy_accel_count % 4096 == 0:
                self._trace_event("halfword-copy-delay-loop", pc=pc, addr=dst, value=src, size=total_size)
            return True
        count = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF  # a3
        if count == 0 or count > 0x20000:
            return False
        dst = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF  # a0
        src = self.uc.reg_read(UC_MIPS_REG_3) & 0xFFFFFFFF  # v1
        size = count * 2
        if not self._is_mapped_ram_va(src, size):
            return False
        if pc == 0x8012B064:
            if not self._is_mapped_ram_va(dst, size):
                return False
            data = self._read_block_va_safe(src, size)
            if len(data) != size:
                return False
            self.uc.mem_write(va_to_phys(dst), data)
            self._mark_framebuffer_dirty_if_overlaps(pc, dst, size, "halfword-copy")
            final_dst = (dst + size) & 0xFFFFFFFF
        else:
            low_dst = (dst - (count - 1) * 2) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(low_dst, size):
                return False
            data = self._read_block_va_safe(src, size)
            if len(data) != size:
                return False
            out = bytearray(size)
            for i in range(count):
                out[(count - 1 - i) * 2 : (count - i) * 2] = data[i * 2 : i * 2 + 2]
            self.uc.mem_write(va_to_phys(low_dst), bytes(out))
            self._mark_framebuffer_dirty_if_overlaps(pc, low_dst, size, "halfword-copy-reverse")
            final_dst = (dst - size) & 0xFFFFFFFF
        last = struct.unpack_from("<H", data, size - 2)[0]
        self.uc.reg_write(UC_MIPS_REG_2, last)
        self.uc.reg_write(UC_MIPS_REG_3, (src + size) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_4, final_dst)
        self.uc.reg_write(UC_MIPS_REG_7, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.halfword_copy_accel_count += 1
        if self.halfword_copy_accel_count <= 32 or self.halfword_copy_accel_count % 4096 == 0:
            self._trace_event("halfword-copy-loop", pc=pc, addr=dst, value=src, size=size)
        return True

    def _handle_raster_copy_loop(self, pc: int) -> bool:
        if not self.fast_hooks or not self.raster_copy_accelerator or pc != 0x800AC388:
            return False
        count = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        fixed = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        step = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        src_base = self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF
        dest = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        if count == 0 or count > 4096 or not self._is_mapped_ram_va(dest, count * 2):
            return False

        out = bytearray()
        last_src = src_base
        last_value = 0
        current = fixed
        for _ in range(count):
            signed_index = struct.unpack("<i", struct.pack("<I", current & 0xFFFFFFFF))[0] >> 16
            src = (src_base + signed_index * 2) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(src, 2):
                return False
            last_src = src
            last_value = self._read_mem_va(src, 2) & 0xFFFF
            out.extend(struct.pack("<H", last_value))
            current = (current + step) & 0xFFFFFFFF
        self.uc.mem_write(va_to_phys(dest), bytes(out))
        self._mark_framebuffer_dirty_if_overlaps(pc, dest, count * 2, "raster-copy")
        self.uc.reg_write(UC_MIPS_REG_2, last_src)
        self.uc.reg_write(UC_MIPS_REG_3, last_value)
        self.uc.reg_write(UC_MIPS_REG_4, 0)
        self.uc.reg_write(UC_MIPS_REG_6, (dest + count * 2) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_7, current)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x800AC3AC)
        self.raster_loop_accel_count += 1
        if self.raster_loop_accel_count <= 32 or self.raster_loop_accel_count % 4096 == 0:
            self._trace_event("raster-copy-loop", pc=pc, addr=dest, value=src_base, size=count)
        return True

    def _handle_glyph_mask_loop(self, pc: int) -> bool:
        if not self.fast_hooks or not self.glyph_mask_accelerator or pc != 0x8011B428:
            return False
        bit_index = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        limit = self.uc.reg_read(UC_MIPS_REG_13) & 0xFFFFFFFF
        glyph_ptr = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        dest = self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF
        color = self.uc.reg_read(UC_MIPS_REG_14) & 0xFFFF
        draw_pair = self.uc.reg_read(UC_MIPS_REG_18) & 0xFFFFFFFF
        if limit <= bit_index or limit - bit_index > 4096:
            return False
        count = limit - bit_index
        if not self._is_mapped_ram_va(dest, count * 2 + 2):
            return False
        byte_count = ((limit + 7) >> 3) - (bit_index >> 3)
        if byte_count <= 0 or byte_count > 1024 or not self._is_mapped_ram_va(glyph_ptr, byte_count):
            return False

        dest_size = count * 2 + (2 if draw_pair else 0)
        glyph_end = glyph_ptr + byte_count
        dest_end = dest + dest_size
        if glyph_ptr < dest_end and dest < glyph_end:
            return False
        dest_data = self._read_block_va_safe(dest, dest_size)
        glyph_data = self._read_block_va_safe(glyph_ptr, byte_count)
        if dest_data is None or glyph_data is None or len(dest_data) != dest_size or len(glyph_data) != byte_count:
            return False

        current_byte = self.uc.reg_read(UC_MIPS_REG_12) & 0xFF
        ptr = glyph_ptr
        out_dest = dest
        written = 0
        packed = struct.pack("<H", color)
        out = bytearray(dest_data)
        glyph_offset = 0
        for index in range(bit_index, limit):
            if (index & 7) == 0:
                if glyph_offset >= len(glyph_data):
                    return False
                current_byte = glyph_data[glyph_offset]
                glyph_offset += 1
                ptr = (ptr + 1) & 0xFFFFFFFF
            mask = 0x80 >> (index & 7)
            if current_byte & mask:
                byte_offset = (out_dest - dest) & 0xFFFFFFFF
                if byte_offset + 2 > len(out):
                    return False
                out[byte_offset : byte_offset + 2] = packed
                written += 1
                if draw_pair:
                    pair_offset = byte_offset + 2
                    if pair_offset + 2 > len(out):
                        return False
                    out[pair_offset : pair_offset + 2] = packed
                    written += 1
            out_dest = (out_dest + 2) & 0xFFFFFFFF

        if written:
            self.uc.mem_write(va_to_phys(dest), bytes(out))
            self._mark_framebuffer_dirty_if_overlaps(pc, dest, dest_size, "glyph-mask")

        self.uc.reg_write(UC_MIPS_REG_2, current_byte)
        self.uc.reg_write(UC_MIPS_REG_4, 0)
        self.uc.reg_write(UC_MIPS_REG_6, ptr)
        self.uc.reg_write(UC_MIPS_REG_7, limit)
        self.uc.reg_write(UC_MIPS_REG_8, out_dest)
        self.uc.reg_write(UC_MIPS_REG_12, current_byte)
        self.uc.reg_write(UC_MIPS_REG_PC, 0x8011B47C)
        self.glyph_mask_loop_accel_count += 1
        if self.glyph_mask_loop_accel_count <= 32 or self.glyph_mask_loop_accel_count % 4096 == 0:
            self._trace_event("glyph-mask-loop", pc=pc, addr=dest, value=glyph_ptr, size=count, color=color, written=written)
        return True

    def _handle_no_event_poll(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x80058CB4:
            return False
        data = self._read_block_va_safe(0x8048D924, 0x70)
        if data is None or len(data) != 0x70:
            return False
        for offset in (0x00, 0x08, 0x0C, 0x10, 0x14, 0x20, 0x24, 0x3C, 0x6C):
            if struct.unpack_from("<I", data, offset)[0] != 0:
                return False
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.no_event_poll_accel_count += 1
        if self.no_event_poll_accel_count <= 16 or self.no_event_poll_accel_count % 4096 == 0:
            self._trace_event("no-event-poll", pc=pc, value=self.no_event_poll_accel_count)
        return True

    def _handle_busy_delay(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x800043A0:
            return False
        cycles = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.busy_delay_accel_count += 1
        if self.busy_delay_accel_count <= 16 or self.busy_delay_accel_count % 4096 == 0:
            self._trace_event("busy-delay", pc=pc, value=cycles, size=self.busy_delay_accel_count)
        return True

    def _handle_ftl_scan_init(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x80181B6C:
            return False
        logical_map = self._read_u32_va_safe(0x804BF468) or 0
        status_map = self._read_u32_va_safe(0x804BF46C) or 0
        spare_map = self._read_u32_va_safe(0x804BF470) or 0
        block_count = self._read_u32_va_safe(0x804BF474) or 0
        pages_per_block = self._read_u32_va_safe(0x804BF478) or 0
        if (
            block_count == 0
            or block_count > 0x4000
            or pages_per_block == 0
            or not self._is_mapped_ram_va(logical_map, block_count * 2)
            or not self._is_mapped_ram_va(status_map, block_count)
            or not self._is_mapped_ram_va(spare_map, block_count)
        ):
            return False

        first_data_block = 0x71 if block_count == 0x800 and pages_per_block == 0x40 else 0
        entries = bytearray(block_count * 2)
        for logical in range(block_count):
            physical = (first_data_block + logical) & 0xFFFF
            struct.pack_into("<H", entries, logical * 2, physical)
        self.uc.mem_write(va_to_phys(logical_map), bytes(entries))
        self.uc.mem_write(va_to_phys(status_map), b"\x04" * block_count)
        self.uc.mem_write(va_to_phys(spare_map), b"\xFF" * block_count)
        self._write_u32_va(0x804BF48C, 0)
        self._write_u32_va(0x804BF490, 0)
        self._write_u32_va(0x804BF494, 0)
        if block_count == 0x800 and pages_per_block == 0x40:
            capacity = self._backing_sector_capacity()
            self._write_u32_va(0x804BF464, (capacity or 0x75200) & 0xFFFFFFFF)
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.ftl_scan_accel_count += 1
        self._trace_event("ftl-scan-init", pc=pc, addr=logical_map, value=first_data_block, size=block_count)
        return True
