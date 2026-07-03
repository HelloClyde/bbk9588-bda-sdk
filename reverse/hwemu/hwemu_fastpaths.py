"""Behavior-preserving hot-path accelerators for the BBK 9588 emulator."""

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
    UC_MIPS_REG_10,
    UC_MIPS_REG_11,
    UC_MIPS_REG_12,
    UC_MIPS_REG_13,
    UC_MIPS_REG_14,
    UC_MIPS_REG_16,
    UC_MIPS_REG_17,
    UC_MIPS_REG_18,
    UC_MIPS_REG_19,
    UC_MIPS_REG_24,
    UC_MIPS_REG_31,
    UC_MIPS_REG_PC,
)

from hwemu_utils import va_to_phys


class HwEmuFastpathMixin:
    def _handle_block_image_hook(self, pc: int) -> bool:
        if self.block_data is None:
            return False
        if pc == 0x80182D58:
            value = len(self.block_data) & 0xFFFFFFFF
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
        ok = source_offset <= len(self.block_data) and length <= len(self.block_data) - source_offset
        copied = 0
        dest_phys = va_to_phys(dest_va)
        op = "read" if pc == 0x80182A90 else "write"
        preview = ""
        if ok and op == "read":
            data = bytes(self.block_data[source_offset : source_offset + length])
            self.uc.mem_write(dest_phys, data)
            result = 0
            copied = len(data)
            preview = data[:16].hex()
        elif ok:
            data = bytes(self.uc.mem_read(dest_phys, length))
            self.block_data[source_offset : source_offset + length] = data
            first_sector = source_offset // 512
            sector_count = (length + 511) // 512
            for index in range(sector_count):
                sector = first_sector + index
                start = sector * 512
                self.block_sector_overrides[sector] = bytes(self.block_data[start : start + 512])
            result = 0
            copied = len(data)
            preview = data[:16].hex()
        else:
            result = 0xFFFFFFFF
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
        }
        self.block_events.append(row)
        if len(self.block_events) > 128:
            del self.block_events[0]
        self.uc.reg_write(UC_MIPS_REG_2, result)
        self.uc.reg_write(UC_MIPS_REG_PC, ra)
        self._trace_event("block-read-hook", pc=pc, addr=dest_va, value=offset, size=length)
        return True

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

    def _read_backing_sector(self, sector: int) -> bytes | None:
        if sector < 0:
            return None
        if self.block_data is not None:
            offset = sector * 512
            if offset + 512 <= len(self.block_data):
                return bytes(self.block_data[offset : offset + 512])
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
        return bytes(page_data[off : off + 512])

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
        for slot in range(2):
            entry = table + slot * 0x10
            entry_cluster = self._read_u32_va_safe(entry)
            if entry_cluster != cluster:
                continue
            buffer_va = self._read_u32_va_safe(entry + 4) or 0
            if not self._is_mapped_ram_va(buffer_va, length):
                return False
            data = self._read_block_va_safe(buffer_va, length)
            if data is None:
                return False
            self.uc.mem_write(va_to_phys(dest_va), data)
            hits = (self._read_u32_va_safe(entry + 8) or 0) + 1
            self._write_u32_va(entry + 8, hits & 0xFFFFFFFF)
            self.uc.reg_write(UC_MIPS_REG_2, 1)
            self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
            self.cluster_read_accel_count += 1
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
            entry = table + slot * 0x10
            hits = self._read_u32_va_safe(entry + 8)
            if hits is None:
                return False
            if hits <= victim_hits:
                victim_hits = hits
                victim_slot = slot
        cache_mode = "backing-read"
        cache_buffer = 0
        if victim_slot is not None and victim_hits != 1:
            entry = table + victim_slot * 0x10
            cache_buffer = self._read_u32_va_safe(entry + 4) or 0
            if self._is_mapped_ram_va(cache_buffer, length):
                self.uc.mem_write(va_to_phys(cache_buffer), data)
                self._write_u32_va(entry, cluster)
                self._write_u32_va(entry + 8, 1)
                cache_mode = "miss-load"

        self.uc.mem_write(va_to_phys(dest_va), data)
        self.uc.reg_write(UC_MIPS_REG_2, 1)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)

        self.cluster_read_accel_count += 1
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
        for slot in range(8):
            entry = table + slot * 0x10
            entry_sector = self._read_u32_va_safe(entry)
            if entry_sector != sector:
                continue
            buffer_va = self._read_u32_va_safe(entry + 4) or 0
            data_va = (buffer_va + low * 2) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(data_va, 2):
                return False
            value = self._read_mem_va(data_va, 2) & 0xFFFF
            hits = (self._read_u32_va_safe(entry + 8) or 0) + 1
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
            entry = table + slot * 0x10
            hits = self._read_u32_va_safe(entry + 8)
            if hits is None:
                return False
            if hits <= victim_hits:
                victim_hits = hits
                victim_slot = slot
        if victim_slot is None:
            return False
        entry = table + victim_slot * 0x10
        buffer_va = self._read_u32_va_safe(entry + 4) or 0
        dirty = self._read_u32_va_safe(entry + 0x0C) or 0
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
        if pc == 0x80174C9C:
            limit, source_bias, target = 10, 1, 0x80174CBC
        elif pc == 0x80174CC0:
            limit, source_bias, target = 12, 0x0E, 0x80174CE0
        else:
            limit, source_bias, target = 4, 0x1C, 0x80174D04
        index = self.uc.reg_read(UC_MIPS_REG_4) & 0xFFFFFFFF
        entry = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        dst = self.uc.reg_read(UC_MIPS_REG_16) & 0xFFFFFFFF
        out_count = self.uc.reg_read(UC_MIPS_REG_17) & 0xFFFFFFFF
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

    def _handle_portrait_blit_loop(self, pc: int) -> bool:
        if not self.fast_hooks or pc != 0x8012C920:
            return False
        fb = self.uc.reg_read(UC_MIPS_REG_7) & 0xFFFFFFFF
        row = self.uc.reg_read(UC_MIPS_REG_11) & 0xFFFFFFFF
        col = self.uc.reg_read(UC_MIPS_REG_6) & 0xFFFFFFFF
        dest_base = self.uc.reg_read(UC_MIPS_REG_8) & 0xFFFFFFFF
        src_row_index = self.uc.reg_read(UC_MIPS_REG_10) & 0xFFFFFFFF
        src_base = self.uc.reg_read(UC_MIPS_REG_12) & 0xFFFFFFFF
        reverse = self._read_mem_va(0x804A6C64, 1) != 0
        if row >= 320 or col >= 240:
            return False
        if not self._is_mapped_ram_va(fb, 240 * 320 * 2):
            return False
        for y in range(row, 320):
            start_col = col if y == row else 0
            src = (src_base + (src_row_index << 5) + start_col * 2) & 0xFFFFFFFF
            count = 240 - start_col
            byte_count = count * 2
            data = self._read_block_va_safe(src, byte_count)
            if data is None or len(data) != byte_count:
                return False
            if reverse:
                dest = (fb + dest_base * 2) & 0xFFFFFFFF
                data = b"".join(data[i : i + 2] for i in range(byte_count - 2, -2, -2))
            else:
                dest = (fb + (dest_base + start_col) * 2) & 0xFFFFFFFF
            if not self._is_mapped_ram_va(dest, byte_count):
                return False
            self.uc.mem_write(va_to_phys(dest), data)
            self._mark_framebuffer_dirty_if_overlaps(pc, dest, byte_count, "portrait-blit")
            dest_base = (dest_base - 240) & 0xFFFFFFFF
            src_row_index = (src_row_index + 15) & 0xFFFFFFFF
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self._trace_event("portrait-blit-loop", pc=pc, addr=fb, size=(320 - row) * 240, value=src_base)
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

        current_byte = self.uc.reg_read(UC_MIPS_REG_12) & 0xFF
        ptr = glyph_ptr
        out_dest = dest
        written = 0
        for index in range(bit_index, limit):
            if (index & 7) == 0:
                current_byte = self._read_mem_va(ptr, 1) & 0xFF
                ptr = (ptr + 1) & 0xFFFFFFFF
            mask = 0x80 >> (index & 7)
            if current_byte & mask:
                packed = struct.pack("<H", color)
                self.uc.mem_write(va_to_phys(out_dest), packed)
                self._mark_framebuffer_dirty_if_overlaps(pc, out_dest, 2, "glyph-mask")
                written += 1
                if draw_pair:
                    self.uc.mem_write(va_to_phys((out_dest + 2) & 0xFFFFFFFF), packed)
                    self._mark_framebuffer_dirty_if_overlaps(pc, (out_dest + 2) & 0xFFFFFFFF, 2, "glyph-mask-pair")
                    written += 1
            out_dest = (out_dest + 2) & 0xFFFFFFFF

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
            self._write_u32_va(0x804BF464, 0x75200)
        self.uc.reg_write(UC_MIPS_REG_2, 0)
        self.uc.reg_write(UC_MIPS_REG_PC, self.uc.reg_read(UC_MIPS_REG_31) & 0xFFFFFFFF)
        self.ftl_scan_accel_count += 1
        self._trace_event("ftl-scan-init", pc=pc, addr=logical_map, value=first_data_block, size=block_count)
        return True
