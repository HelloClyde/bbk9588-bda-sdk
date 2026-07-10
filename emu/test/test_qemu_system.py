from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import http.client
from unittest import mock
from pathlib import Path

from emu.qemu.system import (
    DEFAULT_C200_BASE,
    DEFAULT_BBK9588_FIRMWARE_PATCHES,
    DEFAULT_QEMU_EXECUTABLE,
    DEFAULT_QEMU_FIRMWARE_PATCHES,
    KNOWN_STALL_REGIONS,
    DEFAULT_QEMU_MACHINE,
    QEMU_BBK_FRAME_FORMAT_RGB565,
    QEMU_BBK_FRAME_HEADER,
    QEMU_BBK_FRAME_MAGIC,
    QemuPayload,
    QemuProcessBackend,
    QemuSystemConfig,
    build_bbk_qemu_config,
    build_qemu_command,
    classify_guest_pc,
    decode_cp0,
    find_qemu,
    find_workspace_file,
    prepare_runtime_nand_image,
    qemu_subprocess_env,
)
from emu.qemu.check_source_tree import inspect_qemu_source
from emu.web.frontend_state import FRONTEND_INPUT_CALIBRATION_TARGETS, FrontendState


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http_json(port: int, method: str, path: str) -> dict[str, object]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    if res.status >= 400:
        raise RuntimeError(f"{method} {path} returned {res.status}: {data[:200]!r}")
    return json.loads(data.decode("utf-8") or "{}")


def _http_bytes(port: int, path: str) -> tuple[int, bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    return res.status, data


class _FakeFrontendQemuBackend:
    def __init__(self) -> None:
        self.config = argparse.Namespace(machine="bbk9588")
        self.touches: list[tuple[int, int, bool]] = []
        self.completed = False
        self.trace_calls: list[str] = []

    def running(self) -> bool:
        return True

    def snapshot(self) -> dict[str, object]:
        return {"pc": "0x80017ba4", "running": True}

    def guest_queue_snapshot(self, global_va: int = 0x80473F6C) -> dict[str, object]:
        return {"global_addr": f"0x{global_va:08x}"}

    def guest_display_queue_snapshot(self, queue_va: int = 0x80825840) -> dict[str, object]:
        return {"queue_va": f"0x{queue_va:08x}"}

    def guest_gui_state_snapshot(self) -> dict[str, object]:
        ready = len(self.touches) >= len(FRONTEND_INPUT_CALIBRATION_TARGETS) * 2
        return {
            "active_object_ready": ready,
            "active_object_80474048": "0x80959670" if ready else "0x00000000",
        }

    def guest_scheduler_state_snapshot(self) -> dict[str, object]:
        return {"available": True}

    def guest_touch_device_snapshot(self) -> dict[str, object]:
        return {"available": True}

    def guest_runtime_table_snapshot(self) -> dict[str, object]:
        return {"available": True}

    def guest_display_surface_snapshot(self) -> dict[str, object]:
        return {"available": True}

    def guest_surface_trace_snapshot(self) -> dict[str, object]:
        self.trace_calls.append("surface")
        return {"available": True}

    def guest_storage_trace_snapshot(self) -> dict[str, object]:
        self.trace_calls.append("storage")
        return {"available": True}

    def guest_msc_trace_snapshot(self) -> dict[str, object]:
        self.trace_calls.append("msc")
        return {"available": True}

    def guest_fs_probe_trace_snapshot(self) -> dict[str, object]:
        self.trace_calls.append("fs_probe")
        return {"available": True}

    def guest_progress_trace_snapshot(self) -> dict[str, object]:
        self.trace_calls.append("progress")
        return {"available": True}

    def apply_touch_state(self, x: int, y: int, down: bool) -> dict[str, object]:
        self.touches.append((x, y, down))
        return {"applied": True, "source": "qemu-c-machine-chardev"}

    def enable_lcd_mirror(self) -> dict[str, object]:
        return {"source": "qemu-c-machine", "skipped": True}

    def settle_initial_gui(self) -> dict[str, object]:
        self.completed = True
        return {"source": "qemu-c-machine", "skipped_python_services": True}


def _fat16_boot_sector(
    *,
    hidden: int,
    sectors_per_cluster: int = 0x20,
    reserved: int = 1,
    fats: int = 2,
    root_entries: int = 0x200,
    total_sectors: int = 0xF7AE0,
    sectors_per_fat: int = 0x7C,
) -> bytes:
    boot = bytearray(512)
    boot[0:3] = b"\xeb<\x90"
    boot[3:11] = b"MSDOS5.0"
    struct.pack_into("<H", boot, 0x0B, 512)
    boot[0x0D] = sectors_per_cluster
    struct.pack_into("<H", boot, 0x0E, reserved)
    boot[0x10] = fats
    struct.pack_into("<H", boot, 0x11, root_entries)
    struct.pack_into("<H", boot, 0x13, 0)
    boot[0x15] = 0xF8
    struct.pack_into("<H", boot, 0x16, sectors_per_fat)
    struct.pack_into("<I", boot, 0x1C, hidden)
    struct.pack_into("<I", boot, 0x20, total_sectors)
    boot[0x36:0x3B] = b"FAT16"
    boot[510:512] = b"\x55\xaa"
    return bytes(boot)


class QemuSystemCommandTests(unittest.TestCase):
    LEGACY_PYTHON_GDB_HOOK_TEST_FRAGMENTS = (
        "_gdb_",
        "dirent_path_match",
        "event_loop_empty",
        "fast_forward",
        "fastpath",
        "fat16_cluster_read",
        "file_read_context",
        "first_path_segment",
        "frontend_qemu_backend_status_and_stop",
        "probe_resource_path",
        "resource_" + "cache16",
        "resource_object",
        "resource_open",
        "settle_initial_gui",
        "storage_seed",
        "synthetic_desktop",
    )

    def setUp(self) -> None:
        method = self._testMethodName
        if any(fragment in method for fragment in self.LEGACY_PYTHON_GDB_HOOK_TEST_FRAGMENTS):
            self.skipTest("legacy Python/GDB hook or fastpath test; current default path is QEMU C machine modeling")

    def test_decode_cp0_interrupt_state(self) -> None:
        decoded = decode_cp0(status=0x10000403, cause=0x00800400, epc=0x800043CC)

        self.assertEqual(decoded["exception"], "interrupt")
        self.assertTrue(decoded["ie"])
        self.assertTrue(decoded["exl"])
        self.assertEqual(decoded["pending_interrupts"], "0x04")
        self.assertEqual(decoded["interrupt_mask"], "0x04")
        self.assertFalse(decoded["cpu_interrupts_enabled"])
        self.assertEqual(decoded["pending_enabled_interrupts"], "0x00")
        self.assertEqual(decoded["epc"], "0x800043cc")

        accepting = decode_cp0(status=0x10000401, cause=0x00800400, epc=0x800043CC)
        self.assertTrue(accepting["cpu_interrupts_enabled"])
        self.assertEqual(accepting["pending_enabled_interrupts"], "0x04")

    def test_classifies_touch_mode_flag_getter(self) -> None:
        classified = classify_guest_pc("0x8005c384")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "touch-controller-mode-flag")

    def test_classifies_touch_gpio_level_helper(self) -> None:
        classified = classify_guest_pc("0x80059f6c")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "touch-gpio-level-helper")

    def test_classifies_uart_status_wait(self) -> None:
        classified = classify_guest_pc("0x80005cdc")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "uart-status-wait")

    def test_classifies_usb_udc_service(self) -> None:
        classified = classify_guest_pc("0x8000e658")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "usb-udc-service")

    def test_classifies_irq24_udc_service_loop(self) -> None:
        classified = classify_guest_pc("0x8000985c")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "irq24-udc-service-loop")

    def test_classifies_semaphore_wait_and_release(self) -> None:
        wait = classify_guest_pc("0x8000ba84")
        release = classify_guest_pc("0x8000bb98")
        self.assertIsInstance(wait, dict)
        self.assertIsInstance(release, dict)
        assert wait is not None
        assert release is not None
        self.assertEqual(wait.get("region"), "c200-semaphore-wait")
        self.assertEqual(release.get("region"), "c200-semaphore-release")

    def test_classifies_heap_lock_paths(self) -> None:
        free = classify_guest_pc("0x80006818")
        alloc = classify_guest_pc("0x8000766c")
        self.assertIsInstance(free, dict)
        self.assertIsInstance(alloc, dict)
        assert free is not None
        assert alloc is not None
        self.assertEqual(free.get("region"), "heap-free-with-semaphore")
        self.assertEqual(alloc.get("region"), "heap-alloc-with-semaphore")

    def test_classifies_low_power_wait(self) -> None:
        classified = classify_guest_pc("0x8005bcd8")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "low-power-wait")

    def test_classifies_resource_object_release(self) -> None:
        classified = classify_guest_pc("0x80170c90")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "resource-object-release")

    def test_classifies_resource_release_locked_wrapper(self) -> None:
        classified = classify_guest_pc("0x8017a94c")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "resource-release-locked-wrapper")

    def test_classifies_firmware_fat16_resource_cache_lookup_as_diagnostic(self) -> None:
        classified = classify_guest_pc("0x8017ca10")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "firmware-fat16-resource-cache-lookup")
        description = str(classified.get("description"))
        self.assertIn("diagnostic PC classification", description)
        self.assertNotIn("cache miss-load", description)
        self.assertNotIn("bridge", description.lower())

    def test_classifies_exception_report_tcu_restore(self) -> None:
        classified = classify_guest_pc("0x80004a48")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "c200-exception-report-tcu-restore")

    def test_classifies_gui_event_and_irq_return_paths(self) -> None:
        cases = {
            "0x80005208": "c200-irq-handler-return",
            "0x8001aa18": "touch-irq-ack-return",
            "0x800dc588": "gui-event-poller",
            "0x8012bbb8": "gui-tick-event-service",
            "0x8012ccfc": "event-loop-empty-return",
        }
        for pc, region in cases.items():
            with self.subTest(pc=pc):
                classified = classify_guest_pc(pc)
                self.assertIsInstance(classified, dict)
                assert classified is not None
                self.assertEqual(classified.get("region"), region)

    def test_known_stall_descriptions_do_not_claim_ready_magic(self) -> None:
        descriptions = "\n".join(row[3] for row in KNOWN_STALL_REGIONS)

        self.assertNotIn("stub now supplies this ready bit", descriptions)
        self.assertNotIn("graphics stub supplies this ready bit", descriptions)
        self.assertIn("command completion", descriptions)
        self.assertIn("the bbk9588 LCD status model sets this from controller/frame activity", descriptions)
        self.assertNotIn("optional lcd-status only as a diagnostic override", descriptions)
        self.assertNotIn("optional graphics-status only as a diagnostic override", descriptions)
        self.assertNotIn("cache miss-load", descriptions)
        self.assertNotIn("semaphore-fastpath", descriptions)
        self.assertNotIn("fastpaths serve", descriptions)
        self.assertNotIn("file reads through GDB", descriptions)

    def test_builds_c200_loader_with_physical_load_and_virtual_pc(self) -> None:
        image = Path("C200.bin")
        config = QemuSystemConfig(boot_payload=QemuPayload(image, 0x4000), boot_pc=0x80004000)

        command = build_qemu_command(config)

        self.assertIn("qemu-system-mipsel", command[0])
        self.assertIn("-accel", command)
        self.assertIn("tcg,thread=multi,tb-size=256", command)
        image_qemu = str(image.resolve()).replace("\\", "/")
        self.assertIn(f"loader,file={image_qemu},addr=0x4000,force-raw=on", command)
        self.assertIn("loader,addr=0x80004000,cpu-num=0", command)

    def test_builds_bbk9588_machine_with_raw_kernel_loader(self) -> None:
        image = Path("C200.bin")
        config = QemuSystemConfig(
            boot_payload=QemuPayload(image, 0x4000),
            boot_pc=0x80004000,
            machine="bbk9588",
        )

        command = build_qemu_command(config)

        self.assertIn("-M", command)
        self.assertIn("bbk9588,firmware-phys=0x4000,reset-pc=0x80004000", command)
        self.assertIn("-kernel", command)
        self.assertIn(str(image.resolve()), command)
        self.assertNotIn("loader,addr=0x80004000,cpu-num=0", command)

    def test_builds_bbk9588_nand_machine_with_raw_first_stage_by_default(self) -> None:
        nand = Path("build") / "bbk9588_nand_loader0_uboot40_fat_page1c40_root512_ftloob.bin"

        config = build_bbk_qemu_config(
            nand_image=nand,
            machine="bbk9588",
        )

        command = build_qemu_command(config)

        machine_arg = command[command.index("-M") + 1]
        self.assertIn("bbk9588", machine_arg)
        self.assertIn("bootrom-nand=on", machine_arg)
        self.assertNotIn("bootrom-page=0x0", machine_arg)
        self.assertNotIn("bootrom-size=0x2000", machine_arg)
        self.assertNotIn("bootrom-fat-kernel=on", machine_arg)
        self.assertNotIn("legacy-storage-bridge=on", machine_arg)
        self.assertNotIn("tcu-period-ms=", machine_arg)
        self.assertIn("firmware-phys=0x0", machine_arg)
        self.assertIn("reset-pc=0x80000004", machine_arg)
        self.assertIn("-drive", command)
        self.assertNotIn("-kernel", command)
        self.assertFalse(any("C200.bin" in arg for arg in command), command)
        self.assertFalse(any("u_boot_9588_4740.bin" in arg for arg in command), command)
        self.assertFalse(any(arg.startswith("loader,file=") for arg in command), command)

    def test_bbk9588_bootrom_source_does_not_load_fat_kernel(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")
        start = source.index("static bool bbk9588_bootrom_load_from_nand")
        end = source.index("static uint16_t bbk9588_lduw_le", start)
        bootrom_load = source[start:end]
        helper_start = source.index("static bool bbk9588_bootrom_nand_page_valid")
        helper_end = source.index("static bool bbk9588_bootrom_load_raw_payload", helper_start)
        bootrom_helpers = source[helper_start:helper_end]

        self.assertIn("bbk9588_bootrom_load_first_stage", bootrom_load)
        self.assertIn("BBK9588_BOOTROM_BACKUP_NAND_ADDR", bootrom_load)
        self.assertIn("bbk9588_bootrom_nand_page_valid", bootrom_helpers)
        self.assertIn("bbk9588_bootrom_nand_area_has_valid_page", bootrom_helpers)
        self.assertIn("spare_off + 2", bootrom_helpers)
        self.assertIn("spare_off + 3", bootrom_helpers)
        self.assertIn("spare_off + 4", bootrom_helpers)
        self.assertIn("!bbk9588_bootrom_nand_area_has_valid_page", bootrom_helpers)
        self.assertNotIn("bootrom-fat-kernel", source)
        self.assertNotIn("BOOTROM_KERNEL_PATH", source)
        self.assertNotIn("bootrom_fat_kernel", source)
        self.assertNotIn("bbk9588_bootrom_load_fat_kernel", source)
        self.assertNotIn("FAT kernel", source)
        self.assertNotIn("bbk9588_find_fat16_layout", bootrom_load)
        self.assertNotIn("BBK9588_BOOTROM_MAGIC", source)
        self.assertNotIn('"BBKUBOOT"', source)
        self.assertNotIn("bbk9588_bootrom_load_legacy_payload", source)
        self.assertNotIn("memcmp(header", source)
        self.assertIn("bbk9588_bootrom_load_raw_payload", source)

    def test_qemu_bbk9588_bootrom_tries_backup_when_normal_area_is_erased(self) -> None:
        qemu = find_qemu()
        if qemu is None:
            self.skipTest("qemu-system-mipsel is not installed")

        page_size = 2048
        spare_size = 64
        stride = page_size + spare_size
        backup_page = 0x2000 // page_size
        backup_pages = 0x2000 // page_size

        with tempfile.TemporaryDirectory() as tmp:
            nand = Path(tmp) / "nand-backup-only.bin"
            image = bytearray(b"\xff" * ((backup_page + backup_pages) * stride))
            stage = bytearray(b"\x00" * 0x2000)
            struct.pack_into("<I", stage, 4, 0x1000FFFF)  # branch to self at reset PC.
            for page in range(backup_pages):
                src = page * page_size
                dst = (backup_page + page) * stride
                image[dst : dst + page_size] = stage[src : src + page_size]
                image[dst + page_size + 2 : dst + page_size + 5] = b"\x00\x00\x00"
            nand.write_bytes(image)

            config = build_bbk_qemu_config(
                nand_image=nand,
                executable=qemu,
                boot_mode="nand",
                serial="none",
                monitor="none",
                timeout_seconds=1.5,
            )
            backend = QemuProcessBackend(config)
            try:
                backend.start()
                deadline = time.time() + 3.0
                while time.time() < deadline:
                    if any("from NAND backup address 0x00002000" in line for line in backend.stderr_tail):
                        break
                    time.sleep(0.05)
                self.assertTrue(
                    any("from NAND backup address 0x00002000" in line for line in backend.stderr_tail),
                    backend.stderr_tail,
                )
            finally:
                backend.stop()

    def test_qemu_bbk9588_bootrom_tries_backup_when_normal_oob_is_invalid(self) -> None:
        qemu = find_qemu()
        if qemu is None:
            self.skipTest("qemu-system-mipsel is not installed")

        page_size = 2048
        spare_size = 64
        stride = page_size + spare_size
        backup_page = 0x2000 // page_size
        boot_pages = 0x2000 // page_size

        with tempfile.TemporaryDirectory() as tmp:
            nand = Path(tmp) / "nand-invalid-normal-oob.bin"
            image = bytearray(b"\xff" * ((backup_page + boot_pages) * stride))
            stage = bytearray(b"\x00" * 0x2000)
            struct.pack_into("<I", stage, 4, 0x1000FFFF)  # branch to self at reset PC.
            for page in range(boot_pages):
                src = page * page_size
                normal_dst = page * stride
                backup_dst = (backup_page + page) * stride

                image[normal_dst : normal_dst + page_size] = stage[src : src + page_size]
                image[backup_dst : backup_dst + page_size] = stage[src : src + page_size]
                image[backup_dst + page_size + 3] = 0
            nand.write_bytes(image)

            config = build_bbk_qemu_config(
                nand_image=nand,
                executable=qemu,
                boot_mode="nand",
                serial="none",
                monitor="none",
                timeout_seconds=1.5,
            )
            backend = QemuProcessBackend(config)
            try:
                backend.start()
                deadline = time.time() + 3.0
                while time.time() < deadline:
                    if any("from NAND backup address 0x00002000" in line for line in backend.stderr_tail):
                        break
                    time.sleep(0.05)
                self.assertTrue(
                    any("from NAND backup address 0x00002000" in line for line in backend.stderr_tail),
                    backend.stderr_tail,
                )
            finally:
                backend.stop()

    def test_bbk9588_source_removes_legacy_storage_bridge_and_fat_scan(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn("static bool bbk9588_msc_read_oob_lba_sector", source)
        self.assertIn("static bool bbk9588_msc_write_oob_lba_sector", source)
        self.assertNotIn("bbk9588_read_ftl_logical_sector", source)
        self.assertNotIn("bbk9588_write_ftl_logical_sector", source)
        self.assertNotIn("legacy-storage-bridge", source)
        self.assertNotIn("legacy_storage_bridge", source)
        self.assertNotIn("Bbk9588Fat16Layout", source)
        self.assertNotIn("fat16_layout", source)
        self.assertNotIn("bbk9588_find_fat16_layout", source)
        self.assertNotIn("bbk9588_fat16_layout_from_sector", source)
        self.assertNotIn("bbk9588_read_logical_sector", source)
        self.assertNotIn("bbk9588_write_logical_sector", source)
        self.assertNotIn("bbk9588_storage_read_fat_sector", source)
        self.assertNotIn("bbk9588_storage_read_cluster", source)
        self.assertNotIn("bbk9588_storage_write_cluster", source)
        self.assertNotIn("bbk9588_storage_first_dirent_for_pattern", source)
        self.assertNotIn("logical FAT" + " sector reads", source)
        self.assertNotIn("bbk9588-cluster" + "-cache", source)
        self.assertIn("Trace bbk9588 NAND/MSC page and DMA diagnostics", source)
        self.assertNotIn("bbk9588-diagnostic-guest-object-snapshot", source)
        self.assertNotIn("bbk9588-diagnostic-guest-storage-snapshot", source)
        self.assertNotIn("0x00b714cc", source)
        self.assertNotIn("0x0095a26c", source)
        self.assertNotIn("0x003695b8", source)
        self.assertNotIn("bbk9588-msc-read", source)
        self.assertNotIn("at_icon", source)
        self.assertNotIn("bbk9588-guest-cache", source)
        self.assertNotIn("bbk9588-guest-storage-cache", source)

    def test_release_readme_documents_frontend_calibration_as_explicit_helper(self) -> None:
        readme = (
            Path(__file__).resolve().parents[1]
            / "packaging"
            / "RELEASE_README.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("--no-auto-calibration", readme)
        self.assertNotIn("auto-calibration", readme)
        self.assertIn("--frontend-input-calibration", readme)
        self.assertIn("默认关闭", readme)
        self.assertIn("Web smoke test", readme)

    def test_qemu_python_backing_fat_caches_are_diagnostic_named(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "system.py"
        ).read_text(encoding="utf-8")

        self.assertIn("Diagnostic-only backing image caches", source)
        self.assertIn("diagnostic_fat16_layout_cache", source)
        self.assertIn("diagnostic_fat16_long_name_alias_cache", source)
        self.assertIn("diagnostic_nand_fat_sector0_cache", source)
        self.assertIn("diagnostic_backing_sector_cache", source)
        self.assertNotIn("self.fat16_layout_cache", source)
        self.assertNotIn("self.fat16_long_name_alias_cache", source)
        self.assertNotIn("self.nand_fat_sector0_cache", source)
        self.assertNotIn("self.backing_sector_cache", source)

    def test_bbk9588_event_queue_source_is_diagnostic_mirror_only(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn("static void bbk9588_event_queue_mirror_header", source)
        self.assertIn("static void bbk9588_event_queue_mirror_slot", source)
        self.assertIn("static void bbk9588_event_queue_mirror_all", source)
        self.assertNotIn("bbk9588_event_queue_pop_to_record", source)
        self.assertNotIn("record + 0x04 + word * 4", source)

    def test_bbk9588_fs_probe_helper_is_storage_trace_gated(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "target"
            / "mips"
            / "tcg"
            / "op_helper.c"
        ).read_text(encoding="utf-8")
        start = source.index("void helper_bbk9588_fs_probe")
        end = source.index("target_ulong helper_rotx", start)
        helper = source[start:end]

        self.assertIn("!env->bbk9588_storage_trace", helper)
        self.assertIn("bbk9588_probe_write_u32(BBK9588_FS_PROBE_VA + 0x00", helper)

    def test_bbk9588_progress_trace_timer_not_named_legacy_python_resource_hook(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn("progress_trace_timer", source)
        self.assertIn("progress_trace_period_ms", source)
        self.assertIn('"progress-trace-period-ms"', source)
        self.assertIn("Trace bbk9588 CPU/IRQ/runtime progress into diagnostic guest RAM", source)
        self.assertIn("bbk9588_progress_trace_schedule(board);", source)
        self.assertNotIn("CPU/IRQ/resource progress", source)
        self.assertNotIn("legacy_python_resource_hook_timer", source)
        self.assertNotIn("legacy_python_resource_hook_period_ms", source)
        self.assertNotIn('"resource-pump-period-ms"', source)

    def test_bbk9588_tcu_period_property_is_diagnostic_performance_only(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")
        start = source.index('oc, "tcu-period-ms"')
        end = source.index('oc, "progress-trace-period-ms"', start)
        property_block = source[start:end]

        self.assertIn("Diagnostic/performance TCU sampling period", property_block)
        self.assertIn("hardware correctness must not depend", property_block)
        self.assertNotIn("TCU compare interrupt period", property_block)

    def test_bbk9588_source_has_no_synthetic_irq24_timer(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertNotIn("irq24_timer", source)
        self.assertNotIn("irq24_period_ms", source)
        self.assertNotIn('"irq24-period-ms"', source)
        self.assertNotIn("bbk9588_irq24_schedule", source)
        self.assertNotIn("bbk9588_irq24_raise_pending", source)
        self.assertNotIn("bbk9588_irq24_timer_cb", source)

    def test_bbk9588_touch_diagnostics_do_not_expose_machine_frontend_input_calibration(self) -> None:
        root = Path(__file__).resolve().parents[1]
        stale_token = "touch_" + "autocal"
        c_source = (
            root / "qemu" / "source-overlay" / "hw" / "mips" / "bbk9588.c"
        ).read_text(encoding="utf-8")
        system_source = (root / "qemu" / "system.py").read_text(encoding="utf-8")
        probe_source = (root / "test" / "run_qemu_system_probe.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(stale_token, c_source)
        self.assertNotIn(stale_token, system_source)
        self.assertNotIn(stale_token, probe_source)
        self.assertNotIn('"touch-' + 'autocal"', c_source)
        self.assertIn('"reserved_04"', system_source)
        self.assertIn('"reserved_08"', system_source)
        self.assertIn('"reserved_0c"', system_source)
        self.assertIn('"reserved_04"', probe_source)
        self.assertIn('"reserved_08"', probe_source)
        self.assertIn('"reserved_0c"', probe_source)

    def test_bbk9588_touch_trace_is_explicit_diagnostic(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        start = source.index("static void bbk9588_touch_trace_update")
        end = source.index("static void bbk9588_sadc_touch_fifo_clear", start)
        touch_trace = source[start:end]

        self.assertIn("bool touch_trace_enabled;", source)
        self.assertIn("board->touch_trace_enabled = false;", source)
        self.assertIn('object_class_property_add_bool(oc, "touch-trace"', source)
        self.assertIn("bbk9588_get_touch_trace", source)
        self.assertIn("bbk9588_set_touch_trace", source)
        self.assertIn("!board || !board->touch_trace_enabled ||", touch_trace)
        self.assertIn("BBK9588_TOUCH_TRACE_VA", touch_trace)

    def test_builds_bbk9588_uboot_machine_with_raw_first_stage_by_default(self) -> None:
        nand = Path("build") / "bbk9588_nand_uboot40_fat_page1c40_root512_ftloob.bin"

        config = build_bbk_qemu_config(
            boot_mode="uboot",
            nand_image=nand,
            machine="bbk9588",
        )

        command = build_qemu_command(config)

        machine_arg = command[command.index("-M") + 1]
        self.assertIn("bbk9588", machine_arg)
        self.assertIn("bootrom-nand=on", machine_arg)
        self.assertNotIn("bootrom-page=0x40", machine_arg)
        self.assertNotIn("bootrom-size=0x80000", machine_arg)
        self.assertIn("firmware-phys=0x0", machine_arg)
        self.assertIn("reset-pc=0x80000004", machine_arg)
        self.assertIn("-drive", command)
        self.assertNotIn("-kernel", command)
        self.assertFalse(any("C200.bin" in arg for arg in command), command)
        self.assertFalse(any("u_boot_9588_4740.bin" in arg for arg in command), command)
        self.assertFalse(any(arg.startswith("loader,file=") for arg in command), command)

    def test_builds_bbk9588_uboot_machine_with_explicit_diagnostic_bootrom_copy(self) -> None:
        nand = Path("build") / "bbk9588_nand_uboot40_fat_page1c40_root512_ftloob.bin"

        config = build_bbk_qemu_config(
            boot_mode="uboot",
            nand_image=nand,
            machine="bbk9588",
            bbk_machine_options=(
                "bootrom-page=0x40",
                "bootrom-size=0x80000",
                "firmware-phys=0x900000",
                "reset-pc=0x80900000",
            ),
        )

        command = build_qemu_command(config)

        machine_arg = command[command.index("-M") + 1]
        self.assertIn("bootrom-nand=on", machine_arg)
        self.assertIn("bootrom-page=0x40", machine_arg)
        self.assertIn("bootrom-size=0x80000", machine_arg)
        self.assertIn("firmware-phys=0x900000", machine_arg)
        self.assertIn("reset-pc=0x80900000", machine_arg)
        self.assertNotIn("-kernel", command)

    def test_builds_bbk9588_uboot_machine_with_explicit_direct_bootloader_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot = root / "u_boot_9588_4740.bin"
            boot.write_bytes(b"\0" * 4)

            config = build_bbk_qemu_config(
                boot_mode="uboot",
                image=boot,
                machine="bbk9588",
            )

        command = build_qemu_command(config)

        machine_arg = command[command.index("-M") + 1]
        self.assertIn("bbk9588", machine_arg)
        self.assertIn("firmware-phys=0x900000", machine_arg)
        self.assertIn("reset-pc=0x80900000", machine_arg)
        self.assertIn("-kernel", command)
        self.assertIn(str(boot.resolve()), command)
        self.assertFalse(any("C200.bin" in arg for arg in command), command)
        self.assertFalse(any(arg.startswith("loader,file=") for arg in command), command)

    def test_builds_bbk9588_uboot_machine_with_explicit_legacy_c200_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot = root / "u_boot_9588_4740.bin"
            payload = root / "C200.bin"
            boot.write_bytes(b"\0" * 4)
            payload.write_bytes(b"\0" * 4)

            config = build_bbk_qemu_config(
                boot_mode="uboot",
                image=boot,
                payload=payload,
                machine="bbk9588",
            )

        command = build_qemu_command(config)

        self.assertIn("-kernel", command)
        self.assertIn(str(boot.resolve()), command)
        payload_qemu = str(payload.resolve()).replace("\\", "/")
        self.assertIn(f"loader,file={payload_qemu},addr=0x4000,force-raw=on", command)

    def test_builds_bbk9588_machine_with_nand_mtd_drive(self) -> None:
        image = Path("C200.bin")
        nand = Path("build") / "bbk9588_nand.bin"
        config = QemuSystemConfig(
            boot_payload=QemuPayload(image, 0x4000),
            boot_pc=0x80004000,
            machine="bbk9588",
            nand_image=nand,
        )

        command = build_qemu_command(config)

        nand_qemu = str(nand.resolve()).replace("\\", "/")
        self.assertNotIn("-initrd", command)
        machine_arg = command[command.index("-M") + 1]
        self.assertTrue(machine_arg.startswith("bbk9588,"), machine_arg)
        self.assertIn("-drive", command)
        self.assertIn(f"if=mtd,index=0,format=raw,file={nand_qemu}", command)

    def test_builds_bbk9588_machine_with_input_chardev(self) -> None:
        image = Path("C200.bin")
        config = QemuSystemConfig(
            boot_payload=QemuPayload(image, 0x4000),
            boot_pc=0x80004000,
            machine="bbk9588",
            bbk_input="socket,id=bbk9588-input,host=127.0.0.1,port=12345,server=on,wait=off,nodelay=on",
            bbk_frame="socket,id=bbk9588-frame,host=127.0.0.1,port=12346,server=on,wait=off,nodelay=on",
        )

        command = build_qemu_command(config)

        machine_arg = command[command.index("-M") + 1]
        self.assertIn("input-chardev=bbk9588-input", machine_arg)
        self.assertIn("frame-chardev=bbk9588-frame", machine_arg)
        self.assertIn("-chardev", command)
        self.assertIn(
            "socket,id=bbk9588-input,host=127.0.0.1,port=12345,server=on,wait=off,nodelay=on",
            command,
        )
        self.assertIn(
            "socket,id=bbk9588-frame,host=127.0.0.1,port=12346,server=on,wait=off,nodelay=on",
            command,
        )

    def test_builds_bbk9588_machine_with_extra_machine_options(self) -> None:
        image = Path("C200.bin")
        config = QemuSystemConfig(
            boot_payload=QemuPayload(image, 0x4000),
            boot_pc=0x80004000,
            machine="bbk9588",
            bbk_machine_options=(
                "cpu-irq-output=on",
                "progress-trace=on",
                "progress-trace-period-ms=100",
                "tcu-period-ms=1",
                "lcd-refresh-period-ms=100",
            ),
        )

        command = build_qemu_command(config)

        self.assertIn(
            "bbk9588,cpu-irq-output=on,progress-trace=on,progress-trace-period-ms=100,tcu-period-ms=1,lcd-refresh-period-ms=100,firmware-phys=0x4000,reset-pc=0x80004000",
            command,
        )

    def test_bbk9588_default_patches_skip_c_device_stubs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "C200.bin"
            image.write_bytes(b"\0" * 0x200000)

            config = build_bbk_qemu_config(boot_mode="c200", image=image, machine="bbk9588")

        self.assertEqual(config.firmware_patches, DEFAULT_BBK9588_FIRMWARE_PATCHES)
        self.assertEqual(config.firmware_patches, ())
        self.assertNotIn("c200-lcd-ready", config.firmware_patches)
        self.assertNotIn("c200-uart-ready", config.firmware_patches)
        self.assertNotIn("c200-cp0-irq-enable-noop", config.firmware_patches)
        self.assertNotIn("c200-no-event-poll-empty", config.firmware_patches)
        self.assertNotIn("c200-wait-noop", config.firmware_patches)

    def test_bbk9588_rejects_removed_legacy_machine_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "C200.bin"
            image.write_bytes(b"\0" * 0x200000)

            with self.assertRaisesRegex(ValueError, "removed bbk9588 machine option"):
                build_bbk_qemu_config(
                    boot_mode="c200",
                    image=image,
                    machine="bbk9588",
                    bbk_machine_options=("semaphore-fastpath=off",),
                )

    def test_malta_default_patches_stay_full_compatibility_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "C200.bin"
            image.write_bytes(b"\0" * 0x200000)

            config = build_bbk_qemu_config(boot_mode="c200", image=image, machine="malta")

        self.assertEqual(config.firmware_patches, DEFAULT_QEMU_FIRMWARE_PATCHES)
        self.assertIn("c200-lcd-ready", config.firmware_patches)

    def test_builds_command_with_gdb_stub_when_requested(self) -> None:
        image = Path("C200.bin")
        config = QemuSystemConfig(
            boot_payload=QemuPayload(image, 0x4000),
            boot_pc=0x80004000,
            gdb="tcp:127.0.0.1:1234",
        )

        command = build_qemu_command(config)

        self.assertIn("-gdb", command)
        self.assertIn("tcp:127.0.0.1:1234", command)

    def test_builds_command_with_qemu_plugin_when_requested(self) -> None:
        image = Path("C200.bin")
        plugin = Path("build") / "bbk9588_qemu_fastpath.dll"
        config = QemuSystemConfig(
            boot_payload=QemuPayload(image, 0x4000),
            boot_pc=0x80004000,
            plugins=(plugin,),
        )

        command = build_qemu_command(config)

        plugin_qemu = str(plugin.resolve()).replace("\\", "/")
        self.assertIn("-plugin", command)
        self.assertIn(f"file={plugin_qemu}", command)

    def test_bbk9588_guest_ips_uses_qemu_tb_counter_and_frame_metrics_packet(self) -> None:
        root = Path(__file__).resolve().parents[1]
        board = (root / "qemu" / "source-overlay" / "hw" / "mips" / "bbk9588.c").read_text(encoding="utf-8")
        cpu_h = (root / "qemu" / "source-overlay" / "target" / "mips" / "cpu.h").read_text(encoding="utf-8")
        translate = (root / "qemu" / "source-overlay" / "target" / "mips" / "tcg" / "translate.c").read_text(encoding="utf-8")
        system = (root / "qemu" / "system.py").read_text(encoding="utf-8")

        self.assertIn("#define BBK9588_PERF_MAGIC         0x504b4242u", board)
        self.assertIn("#define BBK9588_PERF_FORMAT_GUEST_INSNS 0x00004950u", board)
        self.assertIn("bbk9588_perf_maybe_send_metrics(board, now);", board)
        self.assertIn("bbk9588_guest_insn_count_enabled", cpu_h)
        self.assertIn("uint64_t bbk9588_guest_insn_count;", cpu_h)
        self.assertIn("static void gen_bbk9588_guest_insn_count", translate)
        self.assertIn("tcg_gen_addi_i64(count, count, ctx->base.num_insns);", translate)
        self.assertIn("QEMU_BBK_PERF_MAGIC = 0x504B4242", system)
        self.assertIn("QEMU_BBK_PERF_PAYLOAD = struct.Struct(\"<QQ\")", system)

    def test_qemu_source_tree_check_rejects_binary_install_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "qemu-system-mipsel.exe").write_bytes(b"binary")

            result = inspect_qemu_source(root)

            self.assertFalse(result["is_qemu_source"], result)
            self.assertIn("configure", result["missing_required_paths"])
            self.assertIn("hw/mips/meson.build", result["missing_required_paths"])

    def test_qemu_source_tree_check_accepts_qemu_source_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "configure").write_text("#!/bin/sh\n", encoding="utf-8")
            (root / "meson.build").write_text("project('qemu')\n", encoding="utf-8")
            (root / "hw" / "mips").mkdir(parents=True)
            (root / "hw" / "mips" / "meson.build").write_text("", encoding="utf-8")
            (root / "hw" / "mips" / "Kconfig").write_text("", encoding="utf-8")
            (root / "target" / "mips").mkdir(parents=True)

            result = inspect_qemu_source(root)

            self.assertTrue(result["is_qemu_source"], result)
            self.assertEqual(result["missing_required_paths"], [])
            self.assertIn("hw/mips/bbk9588.c", result["missing_overlay_paths"])

    def test_install_qemu_overlay_refreshes_destination_mtime_for_ninja(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qemu_source = root / "qemu-src"
            overlay = root / "overlay"
            script = (
                Path(__file__).resolve().parents[1]
                / "qemu"
                / "scripts"
                / "install_qemu_overlay.py"
            )
            src = overlay / "hw" / "mips" / "bbk9588.c"
            dst = qemu_source / "hw" / "mips" / "bbk9588.c"
            old_time = time.time() - 86400

            qemu_source.mkdir()
            (qemu_source / "configure").write_text("#!/bin/sh\n", encoding="utf-8")
            (qemu_source / "meson.build").write_text("project('qemu')\n", encoding="utf-8")
            src.parent.mkdir(parents=True)
            src.write_text("overlay content\n", encoding="utf-8")
            os.utime(src, (old_time, old_time))

            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--qemu-source",
                    str(qemu_source),
                    "--overlay",
                    str(overlay),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(dst.read_text(encoding="utf-8"), "overlay content\n")
            self.assertGreater(dst.stat().st_mtime, src.stat().st_mtime + 1.0)

    def test_bbk9588_intc_tcu_source_follows_jz4740_register_semantics(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")
        tcu_write_start = source.index("static void bbk9588_tcu_write")
        tcu_write_end = source.index("static bool bbk9588_tcu_write_uses_full_reg", tcu_write_start)
        tcu_write = source[tcu_write_start:tcu_write_end]
        tcu_read_start = source.index("static uint32_t bbk9588_tcu_read")
        tcu_read_end = source.index("static uint32_t bbk9588_jz_lcd_read", tcu_read_start)
        tcu_read = source[tcu_read_start:tcu_read_end]
        sync_start = source.index("static void bbk9588_sync_tcu_irq_sources")
        sync_end = source.index("static bool bbk9588_jz_lcd_irq_pending", sync_start)
        sync_tcu = source[sync_start:sync_end]
        schedule_start = source.index("static void bbk9588_tcu_schedule")
        schedule_end = source.index("static void bbk9588_tcu_timer_cb", schedule_start)
        schedule_tcu = source[schedule_start:schedule_end]

        self.assertIn("#define BBK9588_TCU_CHANNELS       8u", source)
        self.assertIn("#define BBK9588_TCU_TSR_OFF        0x1cu", source)
        self.assertIn("#define BBK9588_TCU_TSSR_OFF       0x2cu", source)
        self.assertIn("#define BBK9588_TCU_TSCR_OFF       0x3cu", source)
        self.assertIn("#define BBK9588_TCU_HALF_SHIFT     16u", source)
        self.assertIn("#define BBK9588_TCU_FLAG_MASK", source)
        self.assertIn("#define BBK9588_INTC_ICSR_OFF      0x00u", source)
        self.assertIn("#define BBK9588_INTC_ICMR_OFF      0x04u", source)
        self.assertIn("#define BBK9588_INTC_ICMSR_OFF     0x08u", source)
        self.assertIn("#define BBK9588_INTC_ICMCR_OFF     0x0cu", source)
        self.assertIn("#define BBK9588_INTC_ICPR_OFF      0x10u", source)
        self.assertIn("#define BBK9588_INTC_IRQ_LCD       30u", source)
        self.assertIn("#define BBK9588_INTC_IRQ_GPIO3     25u", source)
        self.assertIn("#define BBK9588_INTC_IRQ_UDC       24u", source)
        self.assertIn("#define BBK9588_INTC_IRQ_TCU0      23u", source)
        self.assertIn("#define BBK9588_INTC_IRQ_TCU1      22u", source)
        self.assertIn("#define BBK9588_INTC_IRQ_TCU2      21u", source)
        self.assertIn("#define BBK9588_INTC_IRQ_DMA       20u", source)
        self.assertIn("#define BBK9588_SYSCTRL_WAKE_PROXY_IRQ BBK9588_INTC_IRQ_TCU1", source)
        self.assertIn("#define BBK9588_DMAC_AUDIO_PARENT_IRQ BBK9588_DMAC_IRQ", source)
        self.assertIn("#define BBK9588_INTC_SOURCE_MASK", source)
        self.assertIn("#define BBK9588_INTC_RESET_MASK    0xffffffffu", source)
        self.assertIn("static uint32_t bbk9588_mmio_extract32", source)
        self.assertIn("case BBK9588_INTC_ICSR_OFF: /* ICSR: raw source status before masking */", source)
        self.assertIn("case BBK9588_INTC_ICMR_OFF: /* ICMR is read/write; ICMSR/ICMCR are convenience aliases. */", source)
        self.assertIn("case BBK9588_INTC_ICMSR_OFF:", source)
        self.assertIn("case BBK9588_INTC_ICMCR_OFF:", source)
        self.assertIn("case BBK9588_INTC_ICPR_OFF: /* ICPR: active sources after masking */", source)
        self.assertIn("return BBK9588_INTC_IRQ_TCU0;", source)
        self.assertIn("return BBK9588_INTC_IRQ_TCU1;", source)
        self.assertIn("return BBK9588_INTC_IRQ_TCU2;", source)
        self.assertIn("unmasked_pending = (board->intc_pending_mask & BBK9588_INTC_SOURCE_MASK) &", source)
        self.assertIn("/* ICPR is read-only on JZ4740; sources are cleared at devices. */", source)
        self.assertIn("board->intc_mask = BBK9588_INTC_RESET_MASK;", source)
        self.assertIn("board->tcu_irq_mask = 0;", source)
        self.assertIn("uint32_t tcu_stop_mask;", source)
        self.assertIn("board->tcu_stop_mask = 0;", source)
        self.assertIn("uint32_t tcu_half_compare[BBK9588_TCU_CHANNELS];", source)
        self.assertIn("uint32_t tcu_half_channel_period_ms[BBK9588_TCU_CHANNELS];", source)
        self.assertIn("int64_t tcu_half_deadline_ms[BBK9588_TCU_CHANNELS];", source)
        self.assertNotIn("if (!board->cpu_irq_output_enabled) {\n        timer_del(board->tcu_irq_timer);", source)
        self.assertNotIn("if (!board->cpu_irq_output_enabled) {\n        return;\n    }\n    for (ch = 0; ch < BBK9588_TCU_CHANNELS; ch++)", source)
        self.assertIn("if (board->cpu_irq_output_enabled) {\n            bbk9588_wake_cpu(board);", source)
        self.assertIn("bbk9588_intc_read(board, offset & ~3)", source)
        self.assertIn("bbk9588_tcu_read(s, offset & ~3)", source)
        self.assertIn("bbk9588_intc_write(board, aligned_offset, intc_value);", source)
        self.assertIn("bbk9588_tcu_write_uses_full_reg(aligned_offset)", source)
        self.assertIn("bbk9588_tcu_write(s, aligned_offset, tcu_value);", source)
        self.assertIn("uint32_t tcu_counter_anchor[BBK9588_TCU_CHANNELS];", source)
        self.assertIn("bool tcu_counter_latched[BBK9588_TCU_CHANNELS];", source)
        self.assertIn("static void bbk9588_tcu_write_counter(Bbk9588MmioState *s", source)
        self.assertIn("s->tcu_counter[channel] = value;", source)
        self.assertIn("s->tcu_counter_anchor[channel] = bbk9588_tcu_virtual_ticks();", source)
        self.assertIn("s->tcu_counter_latched[channel] = true;", source)
        self.assertIn("s->tcu_counter_latched[channel] = false;", source)
        self.assertIn("static uint32_t bbk9588_tcu_compare_period_ms(uint32_t compare)", source)
        self.assertIn("static void bbk9588_tcu_update_compare(Bbk9588MachineState *board", source)
        self.assertIn("board->tcu_half_compare[channel] = compare;", source)
        self.assertIn("board->tcu_half_channel_period_ms[channel] = period_ms;", source)
        self.assertIn("board->tcu_half_deadline_ms[channel] = 0;", source)
        self.assertIn("channel_flags = bit | (bit << BBK9588_TCU_HALF_SHIFT)", sync_tcu)
        self.assertIn("~(board->tcu_irq_mask & channel_flags)", sync_tcu)
        self.assertIn("(board->tcu_stop_mask & bit)", schedule_tcu)
        self.assertIn("uint32_t half_bit = bit << BBK9588_TCU_HALF_SHIFT;", schedule_tcu)
        self.assertIn("newly_pending |= half_bit;", schedule_tcu)
        self.assertIn("board->tcu_half_deadline_ms[ch]", schedule_tcu)
        self.assertIn("case BBK9588_TCU_TSSR_OFF:", tcu_write)
        self.assertIn("board->tcu_stop_mask |= value;", tcu_write)
        self.assertIn("case BBK9588_TCU_TSCR_OFF:", tcu_write)
        self.assertIn("board->tcu_stop_mask &= ~value;", tcu_write)
        self.assertIn("board->tcu_pending_mask |= value & BBK9588_TCU_FLAG_MASK;", tcu_write)
        self.assertIn("board->tcu_irq_mask |= value & BBK9588_TCU_FLAG_MASK;", tcu_write)
        self.assertIn("bbk9588_tcu_write_counter(s, channel, value);", tcu_write)
        self.assertIn("bbk9588_tcu_update_compare(board, channel, reg, value);", tcu_write)
        self.assertIn("offset == BBK9588_TCU_TSR_OFF", tcu_read)
        self.assertIn("value = board->tcu_stop_mask;", tcu_read)
        self.assertIn("if (reg == BBK9588_TCU_TDFR_OFF)", tcu_read)
        self.assertIn("if (reg == BBK9588_TCU_TDHR_OFF)", tcu_read)
        self.assertIn("value = board->tcu_half_compare[ch];", tcu_read)
        self.assertNotIn("if (reg == BBK9588_TCU_TDFR_OFF || reg == BBK9588_TCU_TDHR_OFF)", tcu_read)

    def test_bbk9588_sysctrl_source_uses_register_reset_state(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn("#define BBK9588_SYSCTRL_CPCCR_OFF  0x00u", source)
        self.assertIn("#define BBK9588_SYSCTRL_LCR_OFF    0x04u", source)
        self.assertIn("#define BBK9588_SYSCTRL_CPPCR_OFF  0x10u", source)
        self.assertIn("#define BBK9588_SYSCTRL_CLKGR_OFF  0x20u", source)
        self.assertIn("#define BBK9588_SYSCTRL_SCR_OFF    0x24u", source)
        self.assertIn("#define BBK9588_SYSCTRL_I2SCDR_OFF 0x60u", source)
        self.assertIn("#define BBK9588_SYSCTRL_LPCDR_OFF  0x64u", source)
        self.assertIn("#define BBK9588_SYSCTRL_MSCCDR_OFF 0x68u", source)
        self.assertIn("#define BBK9588_SYSCTRL_UHCCDR_OFF 0x6cu", source)
        self.assertIn("#define BBK9588_SYSCTRL_SSICDR_OFF 0x74u", source)
        self.assertIn("#define BBK9588_SYSCTRL_CPCCR_RESET 0x00000008u", source)
        self.assertIn("#define BBK9588_SYSCTRL_LCR_RESET   0x000000f8u", source)
        self.assertIn("#define BBK9588_SYSCTRL_LCR_RW_MASK 0x000000ffu", source)
        self.assertIn("#define BBK9588_SYSCTRL_CPPCR_RESET 0x28080011u", source)
        self.assertIn("#define BBK9588_SYSCTRL_CPPCR_RW_MASK 0xffff03ffu", source)
        self.assertIn("#define BBK9588_SYSCTRL_CPPCR_PLLS  0x00000400u", source)
        self.assertIn("#define BBK9588_SYSCTRL_CPPCR_PLLEN 0x00000100u", source)
        self.assertIn("#define BBK9588_SYSCTRL_CLKGR_RESET 0x00000000u", source)
        self.assertIn("#define BBK9588_SYSCTRL_CLKGR_RW_MASK 0x0000ffffu", source)
        self.assertIn("#define BBK9588_SYSCTRL_SCR_RESET   0x00001500u", source)
        self.assertIn("#define BBK9588_SYSCTRL_SCR_RW_MASK 0x0000ffd0u", source)
        self.assertIn("#define BBK9588_SYSCTRL_I2SCDR_RESET 0x00000004u", source)
        self.assertIn("#define BBK9588_SYSCTRL_I2SCDR_RW_MASK 0x000001ffu", source)
        self.assertIn("#define BBK9588_SYSCTRL_LPCDR_RW_MASK 0x800007ffu", source)
        self.assertIn("#define BBK9588_SYSCTRL_MSCCDR_RW_MASK 0x0000001fu", source)
        self.assertIn("#define BBK9588_SYSCTRL_UHCCDR_RW_MASK 0x0000000fu", source)
        self.assertIn("#define BBK9588_SYSCTRL_SSICDR_RW_MASK 0x8000000fu", source)
        self.assertIn("static bool bbk9588_sysctrl_word_access", source)
        self.assertIn("static bool bbk9588_sysctrl_word_only_reg", source)
        self.assertIn("static uint32_t bbk9588_sysctrl_cppcr_value", source)
        self.assertIn("static uint32_t bbk9588_sysctrl_write_value", source)
        self.assertIn("case BBK9588_SYSCTRL_CPCCR_OFF: /* CPCCR */", source)
        self.assertIn("case BBK9588_SYSCTRL_LCR_OFF: /* LCR */", source)
        self.assertIn("case BBK9588_SYSCTRL_CPPCR_OFF: /* CPPCR */", source)
        self.assertIn("case BBK9588_SYSCTRL_CLKGR_OFF: /* CLKGR */", source)
        self.assertIn("case BBK9588_SYSCTRL_SCR_OFF: /* SCR */", source)
        self.assertIn("case BBK9588_SYSCTRL_I2SCDR_OFF: /* I2SCDR */", source)
        self.assertIn("case BBK9588_SYSCTRL_LPCDR_OFF: /* LPCDR */", source)
        self.assertIn("case BBK9588_SYSCTRL_MSCCDR_OFF: /* MSCCDR */", source)
        self.assertIn("case BBK9588_SYSCTRL_UHCCDR_OFF: /* UHCCDR */", source)
        self.assertIn("case BBK9588_SYSCTRL_SSICDR_OFF: /* SSICDR */", source)
        self.assertIn("value |= BBK9588_SYSCTRL_CPPCR_PLLS;", source)
        self.assertIn("bbk9588_sysctrl_word_only_reg(aligned_offset) &&", source)
        self.assertIn("!bbk9588_sysctrl_word_access(offset, size)", source)
        self.assertIn("s->regs[index] = old_reg;\n            return;", source)
        self.assertIn("reg = bbk9588_sysctrl_write_value(s, aligned_offset, reg);", source)
        self.assertIn("s->regs[BBK9588_SYSCTRL_CPCCR_OFF / sizeof(uint32_t)]", source)
        self.assertIn("s->regs[BBK9588_SYSCTRL_CPPCR_OFF / sizeof(uint32_t)]", source)
        self.assertIn("s->regs[BBK9588_SYSCTRL_I2SCDR_OFF / sizeof(uint32_t)]", source)
        self.assertIn("s->regs[BBK9588_SYSCTRL_SSICDR_OFF / sizeof(uint32_t)]", source)
        self.assertNotIn("return 0x00000008;", source)
        self.assertNotIn("post-boot divider", source)

    def test_bbk9588_lcd_source_follows_jz4740_register_semantics(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn("#define BBK9588_JZ_LCD_CTRL_ENA       0x00000008u", source)
        self.assertIn("#define BBK9588_JZ_LCD_CTRL_OFUM      0x00000800u", source)
        self.assertIn("#define BBK9588_JZ_LCD_CTRL_IFUM0     0x00000400u", source)
        self.assertIn("#define BBK9588_JZ_LCD_CTRL_IFUM1     0x00000200u", source)
        self.assertIn("#define BBK9588_JZ_LCD_CTRL_RW_MASK   0x3fff3fffu", source)
        self.assertIn("#define BBK9588_JZ_LCD_CFG_RW_MASK    0x80ffffbfu", source)
        self.assertIn("#define BBK9588_JZ_LCD_VSYNC_RW_MASK  0x000007ffu", source)
        self.assertIn("#define BBK9588_JZ_LCD_TIMING_RW_MASK 0x07ff07ffu", source)
        self.assertIn("#define BBK9588_JZ_LCD_REV_RW_MASK    0x07ff0000u", source)
        self.assertIn("#define BBK9588_JZ_LCD_IRQ         BBK9588_INTC_IRQ_LCD", source)
        self.assertIn("#define BBK9588_JZ_LCD_STATE_EOF      0x00000020u", source)
        self.assertIn("#define BBK9588_JZ_LCD_STATE_SOF      0x00000010u", source)
        self.assertIn("#define BBK9588_JZ_LCD_STATE_OUF      0x00000008u", source)
        self.assertIn("#define BBK9588_JZ_LCD_STATE_IFU0     0x00000004u", source)
        self.assertIn("#define BBK9588_JZ_LCD_STATE_IFU1     0x00000002u", source)
        self.assertIn("#define BBK9588_JZ_LCD_DA_ALIGN_MASK  0x0000000fu", source)
        self.assertIn("#define BBK9588_JZ_LCD_CMD_PAL        0x10000000u", source)
        self.assertIn("#define BBK9588_JZ_LCD_CMD_LEN_MASK   0x00ffffffu", source)
        self.assertIn("#define BBK9588_JZ_LCD_CMD_RW_MASK", source)
        self.assertIn("#define BBK9588_JZ_LCD_CTRL_OFF       0x30u", source)
        self.assertIn("#define BBK9588_JZ_LCD_STATE_OFF      0x34u", source)
        self.assertIn("#define BBK9588_JZ_LCD_IID_OFF        0x38u", source)
        self.assertIn("#define BBK9588_JZ_LCD_DA0_OFF        0x40u", source)
        self.assertIn("#define BBK9588_JZ_LCD_SA0_OFF        0x44u", source)
        self.assertIn("#define BBK9588_JZ_LCD_CMD1_OFF       0x5cu", source)
        self.assertIn("#define BBK9588_JZ_LCD_DESC_BYTES     16u", source)
        self.assertIn("#define BBK9588_JZ_LCD_DESC_SOURCE_OFF 0x04u", source)
        self.assertIn("{ \"bbk9588.display0\", 0xb3050000, 0x1000, BBK9588_MMIO_GRAPHICS }", source)
        self.assertIn("static bool bbk9588_is_jz_lcd_window", source)
        self.assertIn("static bool bbk9588_jz_lcd_irq_pending", source)
        self.assertIn("static void bbk9588_jz_lcd_latch_iid", source)
        self.assertIn("!bbk9588_jz_lcd_irq_pending(board)", source)
        self.assertIn("((state & BBK9588_JZ_LCD_STATE_OUF) &&\n            (ctrl & BBK9588_JZ_LCD_CTRL_OFUM))", source)
        self.assertIn("((state & BBK9588_JZ_LCD_STATE_IFU0) &&\n            (ctrl & BBK9588_JZ_LCD_CTRL_IFUM0))", source)
        self.assertIn("((state & BBK9588_JZ_LCD_STATE_IFU1) &&\n            (ctrl & BBK9588_JZ_LCD_CTRL_IFUM1))", source)
        self.assertIn("board->intc_pending_mask &= ~(1u << BBK9588_JZ_LCD_IRQ);", source)
        self.assertIn("case BBK9588_JZ_LCD_STATE_OFF:", source)
        self.assertIn("case BBK9588_JZ_LCD_CFG_OFF:", source)
        self.assertIn("case BBK9588_JZ_LCD_VSYNC_OFF:", source)
        self.assertIn("case BBK9588_JZ_LCD_HSYNC_OFF:", source)
        self.assertIn("case BBK9588_JZ_LCD_PS_OFF:", source)
        self.assertIn("case BBK9588_JZ_LCD_REV_OFF:", source)
        self.assertIn("s->regs[index] = value & BBK9588_JZ_LCD_CFG_RW_MASK;", source)
        self.assertIn("s->regs[index] = value & BBK9588_JZ_LCD_VSYNC_RW_MASK;", source)
        self.assertIn("s->regs[index] = value & BBK9588_JZ_LCD_TIMING_RW_MASK;", source)
        self.assertIn("s->regs[index] = value & BBK9588_JZ_LCD_REV_RW_MASK;", source)
        self.assertIn("case BBK9588_JZ_LCD_DA0_OFF:", source)
        self.assertIn("case BBK9588_JZ_LCD_DA1_OFF:", source)
        self.assertIn("case BBK9588_JZ_LCD_SA0_OFF:", source)
        self.assertIn("case BBK9588_JZ_LCD_CMD1_OFF:", source)
        self.assertIn("board->jz_lcd_cmd[channel ? 1 : 0] = command;", source)
        fetch_start = source.index("static bool bbk9588_jz_lcd_fetch_descriptor")
        fetch_end = source.index("static void bbk9588_jz_lcd_finish_channel", fetch_start)
        fetch_source = source[fetch_start:fetch_end]
        self.assertIn("BBK9588_JZ_LCD_CMD_RW_MASK", fetch_source)
        self.assertIn("bbk9588_jz_lcd_latch_iid(board, BBK9588_JZ_LCD_STATE_SOF,", fetch_source)
        self.assertNotIn("board->jz_lcd_iid = fid;", fetch_source)
        self.assertIn("static void bbk9588_jz_lcd_finish_channel", source)
        self.assertIn("bbk9588_jz_lcd_latch_iid(\n            board, BBK9588_JZ_LCD_STATE_EOF,", source)
        self.assertIn("cmd & ~BBK9588_JZ_LCD_CMD_LEN_MASK", source)
        self.assertIn("static void bbk9588_jz_lcd_signal_frame_done", source)
        self.assertIn("bbk9588_jz_lcd_signal_frame_done(board);", source)
        self.assertIn("bbk9588_jz_lcd_fetch_descriptor(s, 0)", source)
        self.assertIn("board->jz_lcd_mmio = s;", source)
        self.assertIn("bbk9588_jz_lcd_read(s, offset & ~3)", source)
        self.assertIn("s->regs[index] = value & BBK9588_JZ_LCD_CTRL_RW_MASK;", source)
        self.assertIn("s->regs[index] = value & ~BBK9588_JZ_LCD_DA_ALIGN_MASK;", source)
        self.assertIn("bbk9588_jz_lcd_write(s, aligned_offset, old_reg, reg);", source)
        self.assertIn("offset == BBK9588_JZ_LCD_DA1_OFF", source)
        self.assertIn("bbk9588_lcd_candidate_desc_va(value, &desc_va)", source)
        self.assertIn("bbk9588_guest_ram_va_valid(candidate,\n                                       BBK9588_JZ_LCD_DESC_BYTES)", source)
        self.assertIn("BBK9588_JZ_LCD_DESC_SOURCE_OFF", source)
        self.assertIn("board->lcd_status = 0;", source)
        self.assertNotIn("graphics_status", source)
        self.assertNotIn('oc, "graphics-status"', source)
        self.assertNotIn('oc, "lcd-status"', source)
        self.assertNotIn("return s->regs[index] | 0x00000800;", source)
        self.assertNotIn("board->lcd_irq_status |\n                   BBK9588_LCD_STATUS_READY", source)

    def test_bbk9588_sadc_source_follows_jz4740_register_semantics(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn("#define BBK9588_SADC_CONFIG_RESET  0x0002002cu", source)
        self.assertIn("#define BBK9588_SADC_DEFAULT_BATTERY_RAW 0x0e68u", source)
        self.assertIn("#define BBK9588_SADC_DATA_MASK     0x0fffu", source)
        self.assertIn("#define BBK9588_SADC_ADENA_OFF     0x00u", source)
        self.assertIn("#define BBK9588_SADC_ADTCH_OFF     0x18u", source)
        self.assertIn("#define BBK9588_SADC_ADSDAT_OFF    0x20u", source)
        self.assertIn("#define BBK9588_SADC_CONFIG_XYZ_MASK 0x00006000u", source)
        self.assertIn("#define BBK9588_SADC_CONFIG_XYZ_SHIFT 13u", source)
        self.assertIn("#define BBK9588_SADC_CONFIG_XYZ_XY 0u", source)
        self.assertIn("#define BBK9588_SADC_CONFIG_XYZ_ZS 1u", source)
        self.assertIn("#define BBK9588_SADC_CONFIG_XYZ_Z12 2u", source)
        self.assertIn("#define BBK9588_SADC_FIFO_DEPTH    2u", source)
        self.assertIn("#define BBK9588_SADC_STATE_DTCH     0x04u", source)
        self.assertIn("#define BBK9588_SADC_STATE_PENU     0x08u", source)
        self.assertIn("#define BBK9588_SADC_STATE_PEND     0x10u", source)
        self.assertIn("#define BBK9588_SADC_TOUCH_TYPE0    0x00008000u", source)
        self.assertIn("#define BBK9588_SADC_TOUCH_TYPE1    0x80000000u", source)
        self.assertIn("#define BBK9588_SADC_TOUCH_ZS_RAW   0x0800u", source)
        self.assertIn("QEMUTimer *sadc_timer;", source)
        self.assertIn("uint8_t sadc_pending_enable;", source)
        self.assertIn("static uint32_t bbk9588_sadc_pack_touch_pair", source)
        self.assertIn("if (type0) {\n        value |= BBK9588_SADC_TOUCH_TYPE0;", source)
        self.assertIn("if (type1) {\n        value |= BBK9588_SADC_TOUCH_TYPE1;", source)
        self.assertIn("static unsigned bbk9588_sadc_touch_xyz_mode", source)
        self.assertIn("return (board->sadc_status_event & ~board->sadc_control &", source)
        self.assertIn("static uint32_t bbk9588_sadc_touch_fifo_pop", source)
        self.assertIn("if (board->sadc_touch_fifo_count == 0) {\n        return 0;", source)
        self.assertIn("static void bbk9588_sadc_complete_cpu_samples", source)
        self.assertIn("static uint32_t bbk9588_sadc_touch_delay_ms", source)
        self.assertIn("static void bbk9588_sadc_schedule_conversion", source)
        self.assertIn("static void bbk9588_sadc_timer_cb", source)
        self.assertIn("board->sadc_pending_enable |= requested;", source)
        self.assertIn("uint8_t previous_pending = board->sadc_pending_enable;", source)
        self.assertIn("uint8_t new_cpu_channels = requested & cpu_channels & ~previous_pending;", source)
        self.assertIn("if (previous_pending && !new_cpu_channels) {", source)
        self.assertIn("delay_ms = new_cpu_channels ? 1u :", source)
        self.assertIn("uint64_t scaled = (uint64_t)ticks * 128u;", source)
        self.assertIn("(scaled + 11999u) / 12000u", source)
        self.assertIn("timer_mod(board->sadc_timer,\n              qemu_clock_get_ms(QEMU_CLOCK_REALTIME) + delay_ms);", source)
        self.assertIn("board->sadc_pending_enable = 0;", source)
        self.assertIn("timer_new_ms(QEMU_CLOCK_REALTIME,\n                                     bbk9588_sadc_timer_cb, board)", source)
        self.assertIn("case BBK9588_SADC_CONFIG_XYZ_ZS:", source)
        self.assertIn("case BBK9588_SADC_CONFIG_XYZ_Z12:", source)
        self.assertIn("case BBK9588_SADC_CONFIG_XYZ_XY:", source)
        self.assertIn("bbk9588_sadc_pack_touch_pair(board->touch_raw_x,\n                                         board->touch_raw_y,\n                                         false, false)", source)
        self.assertIn("bbk9588_sadc_pack_touch_pair(BBK9588_SADC_TOUCH_ZS_RAW, 0,\n                                         false, false)", source)
        self.assertIn("bbk9588_sadc_pack_touch_pair(BBK9588_SADC_TOUCH_Z1_RAW,\n                                         BBK9588_SADC_TOUCH_Z2_RAW,\n                                         true, true)", source)
        self.assertIn("case BBK9588_SADC_ADENA_OFF: /* ADENA */", source)
        self.assertIn("case BBK9588_SADC_ADCFG_OFF: /* ADCFG */", source)
        self.assertIn("case BBK9588_SADC_ADCTRL_OFF: /* ADCTRL */", source)
        self.assertIn("case BBK9588_SADC_ADSTATE_OFF: /* ADSTATE */", source)
        self.assertIn("case BBK9588_SADC_ADTCH_OFF: /* ADTCH */", source)
        self.assertIn("case BBK9588_SADC_ADBDAT_OFF: /* ADBDAT */", source)
        self.assertIn("case BBK9588_SADC_ADSDAT_OFF: /* ADSDAT */", source)
        self.assertIn("if (board->sadc_touch_fifo_count > 0) {\n            value = bbk9588_sadc_touch_fifo_pop(board);", source)
        self.assertIn("bbk9588_sadc_schedule_conversion(board, requested);", source)
        self.assertIn("timer_del(board->sadc_timer);", source)
        self.assertIn("board->sadc_enable &= ~BBK9588_SADC_ADENA_PBATEN;", source)
        self.assertIn("board->sadc_battery_data = 0;", source)
        self.assertIn('oc, "sadc-battery-raw"', source)
        self.assertIn("bbk9588_sadc_queue_touch_sample(board);", source)
        self.assertIn("board->sadc_config = BBK9588_SADC_CONFIG_RESET;", source)
        self.assertIn("board->sadc_pending_enable = 0;", source)
        self.assertIn("board->sadc_battery_raw = BBK9588_SADC_DEFAULT_BATTERY_RAW;", source)
        self.assertNotIn("return BBK9588_SADC_TOUCH_TYPE1 |", source)
        self.assertNotIn("value = BBK9588_SADC_BATTERY_RAW;", source)

    def test_bbk9588_gpio_source_follows_jz4740_port_register_semantics(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")
        gpio_start = source.index("static uint32_t bbk9588_gpio_idle_level")
        gpio_end = source.index("static uint32_t bbk9588_sadc_read", gpio_start)
        gpio = source[gpio_start:gpio_end]
        read_start = source.index("static uint64_t bbk9588_mmio_read")
        write_start = source.index("static void bbk9588_mmio_write", read_start)
        mmio_read = source[read_start:write_start]
        write_end = source.index("static const MemoryRegionOps", write_start)
        mmio_write = source[write_start:write_end]
        map_start = source.index("static void bbk9588_map_mmio_window")
        map_end = source.index("static void bbk9588_cpu_reset", map_start)
        map_window = source[map_start:map_end]
        key_start = source.index("static bool bbk9588_key_gpio_bits")
        key_end = source.index("static void bbk9588_key_apply_host_input", key_start)
        key_gpio = source[key_start:key_end]

        self.assertIn("#define BBK9588_GPIO_PORTS          4u", source)
        self.assertIn("#define BBK9588_GPIO_PORT_STRIDE    0x100u", source)
        self.assertIn("#define BBK9588_GPIO_PIN_OFF        0x00u", source)
        self.assertIn("#define BBK9588_GPIO_DAT_OFF        0x10u", source)
        self.assertIn("#define BBK9588_GPIO_DATS_OFF       0x14u", source)
        self.assertIn("#define BBK9588_GPIO_FLGC_OFF       BBK9588_GPIO_DATS_OFF", source)
        self.assertIn("#define BBK9588_GPIO_DATC_OFF       0x18u", source)
        self.assertIn("#define BBK9588_GPIO_IM_OFF         0x20u", source)
        self.assertIn("#define BBK9588_GPIO_IM_RESET       0xffffffffu", source)
        self.assertIn("#define BBK9588_GPIO_FLG_OFF        0x80u", source)
        self.assertIn("#define BBK9588_GPIO_PORT_B_OFF     0x100u", source)
        self.assertIn("#define BBK9588_GPIO_IRQ_PORT_B     BBK9588_INTC_IRQ_GPIO1", source)
        self.assertIn("#define BBK9588_NAND_READY_IRQ      BBK9588_GPIO_IRQ_PORT_C", source)

        self.assertIn("static bool bbk9588_gpio_decode_offset", gpio)
        self.assertIn("static void bbk9588_gpio_apply_write", gpio)
        self.assertIn("case BBK9588_GPIO_DATS_OFF:", gpio)
        self.assertIn("case BBK9588_GPIO_DATC_OFF:", gpio)
        self.assertIn("case BBK9588_GPIO_IMS_OFF:", gpio)
        self.assertIn("case BBK9588_GPIO_IMC_OFF:", gpio)
        self.assertIn("case BBK9588_GPIO_FUNS_OFF:", gpio)
        self.assertIn("case BBK9588_GPIO_FUNC_OFF:", gpio)
        self.assertIn("case BBK9588_GPIO_DIRS_OFF:", gpio)
        self.assertIn("case BBK9588_GPIO_DIRC_OFF:", gpio)
        self.assertIn("case BBK9588_GPIO_TRGS_OFF:", gpio)
        self.assertIn("case BBK9588_GPIO_TRGC_OFF:", gpio)
        self.assertIn("bbk9588_gpio_clear_flag(s->board, offset, value);", gpio)
        self.assertIn("BBK9588_GPIO_PORT_B_OFF + BBK9588_GPIO_FLGC_OFF", gpio)
        self.assertIn("BBK9588_GPIO_IRQ_PORT_B", gpio)

        self.assertIn("BBK9588_GPIO_PIN_OFF", mmio_read)
        self.assertIn("BBK9588_GPIO_FLG_OFF", mmio_read)
        self.assertIn("bbk9588_gpio_apply_write(s, aligned_offset, lane_value);", mmio_write)
        self.assertIn("BBK9588_GPIO_IM_RESET", map_window)
        self.assertIn("port < BBK9588_GPIO_PORTS", map_window)

        self.assertIn("*offset = BBK9588_GPIO_PORT_B_OFF;", key_gpio)
        self.assertIn("case BBK9588_GPIO_PORT_C_OFF:", key_gpio)
        self.assertIn("main_irq = BBK9588_GPIO_IRQ_PORT_D;", key_gpio)
        self.assertNotIn("case 0x100:", key_gpio)
        self.assertNotIn("main_irq = 27;", key_gpio)

    def test_bbk9588_rtc_source_follows_jz4740_register_semantics(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn('#include "system/rtc.h"', source)
        self.assertIn('#include "qemu/cutils.h"', source)
        self.assertIn("#define BBK9588_RTC_RTCCR_RESET    0x00000081u", source)
        self.assertIn("#define BBK9588_RTC_RTCCR_WRDY     0x00000080u", source)
        self.assertIn("#define BBK9588_RTC_RTCCR_1HZ      0x00000040u", source)
        self.assertIn("#define BBK9588_RTC_RTCCR_1HZIE    0x00000020u", source)
        self.assertIn("#define BBK9588_RTC_IRQ            BBK9588_INTC_IRQ_RTC", source)
        self.assertIn("#define BBK9588_RTC_HCR_PD         0x00000001u", source)
        self.assertIn("#define BBK9588_RTC_HWFCR_MASK     0x0000ffe0u", source)
        self.assertIn("#define BBK9588_RTC_HRCR_MASK      0x00000fe0u", source)
        self.assertIn("#define BBK9588_RTC_HWRSR_PPR      0x00000010u", source)
        self.assertIn("#define BBK9588_RTC_HWRSR_HR       0x00000020u", source)
        self.assertIn("#define BBK9588_RTC_HWRSR_PIN      0x00000002u", source)
        self.assertIn("#define BBK9588_RTC_HWRSR_ALM      0x00000001u", source)
        self.assertIn("BBK9588_MMIO_RTC", source)
        self.assertIn('{ "bbk9588.rtc",      0xb0003000, 0x1000, BBK9588_MMIO_RTC }', source)
        self.assertIn("static uint32_t bbk9588_rtc_read", source)
        self.assertIn("static uint32_t bbk9588_rtc_host_seconds", source)
        self.assertIn("static uint32_t bbk9588_rtc_latch_flags", source)
        self.assertIn("static bool bbk9588_rtc_irq_pending", source)
        self.assertIn("static void bbk9588_rtc_schedule", source)
        self.assertIn("static void bbk9588_rtc_timer_cb", source)
        self.assertIn("static void bbk9588_rtc_enter_hibernate", source)
        self.assertIn("static void bbk9588_rtc_write_while_hibernating", source)
        self.assertIn("QEMUTimer *rtc_timer;", source)
        self.assertIn("uint32_t rtc_1hz_latched_seconds;", source)
        self.assertIn("bool rtc_alarm_latched;", source)
        self.assertIn("case 0x00: /* RTCCR */", source)
        self.assertIn("case 0x04: /* RTCSR */", source)
        self.assertIn("case 0x20: /* HCR */", source)
        self.assertIn("case 0x30: /* HWRSR */", source)
        self.assertIn("case 0x34: /* HSPR */", source)
        self.assertIn("board->intc_pending_mask |= 1u << BBK9588_RTC_IRQ;", source)
        self.assertIn("board->rtc_hwrsr |= BBK9588_RTC_HWRSR_ALM;", source)
        self.assertIn("board->rtc_hcr &= ~BBK9588_RTC_HCR_PD;", source)
        self.assertIn("board->rtc_hwrsr &= ~(BBK9588_RTC_HWRSR_ALM |", source)
        self.assertIn("if (board->rtc_hcr & BBK9588_RTC_HCR_PD)", source)
        self.assertIn("bbk9588_mmio_extract32(bbk9588_rtc_read(board, offset & ~3)", source)
        self.assertIn("bbk9588_rtc_write(board, aligned_offset, reg);", source)
        self.assertIn("qemu_get_timedate(&tm, 0);", source)
        self.assertIn("seconds = mktimegm(&tm);", source)
        self.assertIn("board->rtc_base_seconds = bbk9588_rtc_host_seconds();", source)
        self.assertIn("board->rtc_base_ns = qemu_clock_get_ns(rtc_clock);", source)
        self.assertIn("seconds != board->rtc_1hz_latched_seconds", source)
        self.assertIn("board->rtc_1hz_latched_seconds = seconds;", source)
        self.assertIn("!board->rtc_alarm_latched", source)
        self.assertIn("board->rtc_alarm_latched = true;", source)
        self.assertIn("board->rtc_alarm_latched = false;", source)
        self.assertIn("board->rtc_1hz_latched_seconds = board->rtc_base_seconds;", source)
        self.assertIn("timer_new_ns(rtc_clock, bbk9588_rtc_timer_cb, board)", source)
        self.assertIn("bbk9588_rtc_schedule(board);", source)
        self.assertIn("timer_mod(board->rtc_timer, next_ns);", source)
        self.assertIn("board->rtc_hwrsr = BBK9588_RTC_HWRSR_PPR;", source)
        rtc_source = source[
            source.index("static uint32_t bbk9588_rtc_seconds"):
            source.index("static uint32_t bbk9588_jz_lcd_read")
        ]
        self.assertNotIn("BBK9588_RTC_DEFAULT_SECONDS", source)
        self.assertNotIn("qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)", rtc_source)
        self.assertNotIn("seconds != board->rtc_base_seconds", rtc_source)
        self.assertNotIn('"ready-status"', source)

    def test_bbk9588_dmac_source_follows_jz4740_channel_semantics(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn("#define BBK9588_DMAC_CHANNELS      6u", source)
        self.assertIn("#define BBK9588_DMAC_CTRL_OFF      0x300u", source)
        self.assertIn("#define BBK9588_DMAC_IRQP_OFF      0x304u", source)
        self.assertIn("#define BBK9588_DMAC_DRT_AUTO      8u", source)
        self.assertIn("#define BBK9588_DMAC_DTC_MASK      0x00ffffffu", source)
        self.assertIn("#define BBK9588_DMAC_DCS_NDES      0x80000000u", source)
        self.assertIn("#define BBK9588_DMAC_DCS_TT        0x00000008u", source)
        self.assertIn("#define BBK9588_DMAC_DCS_CT        0x00000002u", source)
        self.assertIn("#define BBK9588_DMAC_DCM_SAI       0x00800000u", source)
        self.assertIn("#define BBK9588_DMAC_DCM_DAI       0x00400000u", source)
        self.assertIn("#define BBK9588_DMAC_DCM_V         0x00000010u", source)
        self.assertIn("#define BBK9588_DMAC_DCM_VM        0x00000008u", source)
        self.assertIn("#define BBK9588_DMAC_DCM_VIE       0x00000004u", source)
        self.assertIn("#define BBK9588_DMAC_DCM_TIE       0x00000002u", source)
        self.assertIn("#define BBK9588_DMAC_DCM_LINK      0x00000001u", source)
        self.assertIn("#define BBK9588_DMAC_DRT_MASK      0x0000001fu", source)
        self.assertIn("#define BBK9588_DMAC_DCS_CDOA_MASK 0x00ff0000u", source)
        self.assertIn("#define BBK9588_DMAC_DDA_DBA_MASK  0xfffff000u", source)
        self.assertIn("#define BBK9588_DMAC_DDA_DOA_MASK  0x00000ff0u", source)
        self.assertIn("#define BBK9588_DMAC_DDA_ALIGN_MASK 0x0000000fu", source)
        self.assertIn("#define BBK9588_DMAC_DESC_BYTES    16u", source)
        self.assertIn("#define BBK9588_DMAC_DESC_DCM_OFF  0x00u", source)
        self.assertIn("#define BBK9588_DMAC_DESC_DSA_OFF  0x04u", source)
        self.assertIn("#define BBK9588_DMAC_DESC_DTA_OFF  0x08u", source)
        self.assertIn("#define BBK9588_DMAC_DESC_DTC_OFF  0x0cu", source)
        self.assertIn("static bool bbk9588_dmac_channel_offset", source)
        self.assertIn("static void bbk9588_dmac_sync_irq_sources", source)
        self.assertIn("static void bbk9588_dmac_set_terminal_count", source)
        self.assertIn("static void bbk9588_dmac_fetch_descriptor", source)
        self.assertIn("static void bbk9588_dmac_finish_transfer", source)
        self.assertIn("bbk9588_dmac_descriptor_next(desc_addr, desc_dtc)", source)
        self.assertIn("command = bbk9588_phys_read_le32(desc_addr + BBK9588_DMAC_DESC_DCM_OFF);", source)
        self.assertIn("bbk9588_phys_read_le32(desc_addr + BBK9588_DMAC_DESC_DSA_OFF)", source)
        self.assertIn("bbk9588_phys_write_le32(desc_addr + BBK9588_DMAC_DESC_DCM_OFF,\n                                command & ~BBK9588_DMAC_DCM_V);", source)
        self.assertIn("static bool bbk9588_dmac_channel_enabled", source)
        self.assertIn("static void bbk9588_dmac_try_msc_transfer", source)
        self.assertIn("static void bbk9588_dmac_try_auto_ram_transfer", source)
        self.assertIn("request != BBK9588_DMAC_DRT_AUTO", source)
        self.assertIn("bbk9588_dmac_unit_bytes(command)", source)
        self.assertIn("bbk9588_dmac_ram_range_valid(source, bytes)", source)
        self.assertIn("s->regs[source_index] = source + bytes;", source)
        self.assertIn("s->regs[target_index] = target + bytes;", source)
        self.assertIn("s->regs[BBK9588_DMAC_IRQP_OFF / sizeof(uint32_t)] =\n        irqp & BBK9588_DMAC_CHANNEL_MASK;", source)
        self.assertIn("~(BBK9588_DMAC_CTRL_AR | BBK9588_DMAC_CTRL_HLT)", source)
        self.assertIn("DIRQP is a pending-status register.", source)
        self.assertIn("bbk9588_dmac_sync_irq_sources(s);", source)
        self.assertIn("aligned_offset == BBK9588_DMAC_CTRL_OFF", source)
        self.assertIn("bbk9588_dmac_try_msc_transfer(s, channel);", source)
        self.assertIn("bbk9588_dmac_try_auto_ram_transfer(s, channel);", source)
        self.assertIn("aligned_offset == BBK9588_DMAC_DOORBELL_SET_OFF", source)
        self.assertIn("s->regs[BBK9588_DMAC_DOORBELL_OFF / sizeof(uint32_t)] |=", source)
        self.assertIn("s->regs[index] = reg & BBK9588_DMAC_DTC_MASK;", source)
        self.assertIn("s->regs[index] = reg & BBK9588_DMAC_DRT_MASK;", source)
        self.assertIn("s->regs[index] = reg & ~BBK9588_DMAC_DDA_ALIGN_MASK;", source)
        self.assertIn("bbk9588_dmac_finish_transfer(s, channel, command);", source)
        self.assertNotIn("bbk9588_dmac_sync_audio_irq", source)
        self.assertNotIn("s->regs[index] = reg & BBK9588_DMAC_CHANNEL_MASK;", source)
        self.assertNotIn("BBK9588_DMAC_CTRL_AR |\n                                    BBK9588_DMAC_CTRL_HLT |", source)
        self.assertNotIn("(offset == 0x08 || offset == 0x28)", source)
        self.assertNotIn("s->regs[index] = reg & 0x1fu;", source)

    def test_bbk9588_msc_dma_uses_msc_owned_oob_lba_map(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")
        start = source.index("static void bbk9588_msc_complete_dma")
        end = source.index("static void bbk9588_dmac_try_msc_transfer", start)
        msc_complete = source[start:end]

        self.assertIn("msc_oob_lba_map_valid", source)
        self.assertIn("static void bbk9588_msc_oob_lba_map_clear", source)
        self.assertIn("static void bbk9588_msc_build_oob_lba_map", source)
        self.assertIn("static uint32_t bbk9588_msc_oob_lba_to_physical_page", source)
        self.assertIn("static bool bbk9588_msc_read_oob_lba_sector", source)
        self.assertIn("static bool bbk9588_msc_write_oob_lba_sector", source)
        self.assertIn("#define BBK9588_NAND_PAGES_PER_BLOCK 64u", source)
        self.assertIn("#define BBK9588_NAND_BLOCKS        4096u", source)
        self.assertIn("#define BBK9588_NAND_TOTAL_SIZE", source)
        self.assertIn("page_count / BBK9588_NAND_PAGES_PER_BLOCK", source)
        self.assertIn("block_count > BBK9588_NAND_BLOCKS", source)
        self.assertIn("BBK9588_NAND_PAGES_PER_BLOCK * stride", source)
        self.assertIn("bbk9588_msc_oob_lba_to_physical_page(", source)
        self.assertIn("bbk9588_msc_read_oob_lba_sector(", msc_complete)
        self.assertIn("bbk9588_msc_write_oob_lba_sector(", msc_complete)
        self.assertNotIn("initial_data", source)
        self.assertNotIn("initial_size", source)
        self.assertNotIn("bbk9588_nand_build_ftl_map", source)
        self.assertNotIn("bbk9588_nand_build_oob_logical_map", source)
        self.assertNotIn("bbk9588_nand_translate_oob_mapped_page", source)
        self.assertNotIn("oob_logical_to_physical_block", source)
        self.assertNotIn("bbk9588_nand_translate_data_page", source)
        self.assertNotIn("bbk9588_read_ftl_logical_sector", source)
        self.assertNotIn("bbk9588_write_ftl_logical_sector", source)
        self.assertNotIn("bbk9588_find_fat16_layout", msc_complete)
        self.assertNotIn("bbk9588_read_logical_sector", msc_complete)
        self.assertNotIn("bbk9588_write_logical_sector", msc_complete)
        self.assertNotIn("enum { pages_per_block = 64 }", source)
        self.assertNotIn("last_oob_page", source)
        self.assertNotIn("0x809066c0u", source)
        self.assertNotIn("0x8090674cu", source)

    def test_bbk9588_msc_source_follows_jz4740_register_reset_state(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")
        prepare_start = source.index("static void bbk9588_msc_prepare_response")
        prepare_end = source.index("static uint32_t bbk9588_msc_read_response", prepare_start)
        prepare = source[prepare_start:prepare_end]
        read_start = source.index("static uint64_t bbk9588_mmio_read")
        write_start = source.index("static void bbk9588_mmio_write", read_start)
        mmio_read = source[read_start:write_start]
        write_end = source.index("static const MemoryRegionOps", write_start)
        mmio_write = source[write_start:write_end]
        map_start = source.index("static void bbk9588_map_mmio_window")
        map_end = source.index("static void bbk9588_cpu_reset", map_start)
        map_window = source[map_start:map_end]

        self.assertIn("#define BBK9588_MSC_STRPCL_OFF     0x1000u", source)
        self.assertIn("#define BBK9588_MSC_STAT_OFF       0x1004u", source)
        self.assertIn("#define BBK9588_MSC_RESTO_OFF      0x1010u", source)
        self.assertIn("#define BBK9588_MSC_RDTO_OFF       0x1014u", source)
        self.assertIn("#define BBK9588_MSC_IMASK_OFF      0x1024u", source)
        self.assertIn("#define BBK9588_MSC_IREG_OFF       0x1028u", source)
        self.assertIn("#define BBK9588_MSC_CMD_OFF        0x102cu", source)
        self.assertIn("#define BBK9588_MSC_ARG_OFF        0x1030u", source)
        self.assertIn("#define BBK9588_MSC_RES_OFF        0x1034u", source)
        self.assertIn("#define BBK9588_MSC_STAT_RESET     0x00000040u", source)
        self.assertIn("#define BBK9588_MSC_RESTO_RESET    0x00000040u", source)
        self.assertIn("#define BBK9588_MSC_RDTO_RESET     0x0000ffffu", source)
        self.assertIn("#define BBK9588_MSC_IMASK_RESET    0x000000ffu", source)
        self.assertIn("static bool bbk9588_is_msc_window", source)

        self.assertIn("bbk9588_is_msc_window(s)", prepare)
        self.assertIn("BBK9588_MSC_CMD_OFF", prepare)
        self.assertIn("BBK9588_MSC_ARG_OFF", prepare)
        self.assertIn("BBK9588_MSC_IREG_OFF", prepare)

        self.assertIn("bbk9588_is_msc_window(s)", mmio_read)
        self.assertIn("offset == BBK9588_MSC_RES_OFF", mmio_read)
        self.assertIn("offset == BBK9588_MSC_IREG_OFF", mmio_read)
        self.assertIn("offset == BBK9588_MSC_STAT_OFF", mmio_read)

        self.assertIn("bbk9588_is_msc_window(s)", mmio_write)
        self.assertIn("offset == BBK9588_MSC_STRPCL_OFF", mmio_write)
        self.assertIn("offset == BBK9588_MSC_IREG_OFF", mmio_write)
        self.assertIn("BBK9588_MSC_STAT_OFF / sizeof(uint32_t)", mmio_write)
        self.assertNotIn("offset == 0x1000", mmio_write)
        self.assertNotIn("offset == 0x1028", mmio_write)
        self.assertNotIn("s->regs[0x1004 / sizeof(uint32_t)]", mmio_write)

        self.assertIn("bbk9588_is_msc_window(s)", map_window)
        self.assertIn("BBK9588_MSC_STAT_RESET", map_window)
        self.assertIn("BBK9588_MSC_RESTO_RESET", map_window)
        self.assertIn("BBK9588_MSC_RDTO_RESET", map_window)
        self.assertIn("BBK9588_MSC_IMASK_RESET", map_window)

    def test_bbk9588_nand_geometry_detection_uses_raw_oob_stride(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")
        start = source.index("static void bbk9588_nand_detect_geometry")
        end = source.index("static const Bbk9588MmioWindow", start)
        detect = source[start:end]

        self.assertIn("nand->size % BBK9588_NAND_STRIDE == 0", detect)
        self.assertIn("nand->page_stride = BBK9588_NAND_STRIDE;", detect)
        self.assertIn("nand->page_stride = BBK9588_NAND_PAGE_SIZE;", detect)
        self.assertNotIn("oob_map_valid", detect)
        self.assertNotIn("oob_logical_to_physical_block", source)
        self.assertIn("msc_oob_lba_map_valid", source)
        self.assertIn("#define BBK9588_NAND_TOTAL_PAGES", source)
        self.assertIn("#define BBK9588_NAND_TOTAL_SIZE", source)
        self.assertNotIn("last_oob_page", source)
        self.assertNotIn("0x809066c0u", source)
        self.assertNotIn("0x8090674cu", source)
        self.assertNotIn("ftl_map_valid", source)
        self.assertNotIn("ftl_logical_to_physical", source)
        self.assertNotIn("FAT16", detect)
        self.assertNotIn("fat16_layout", detect)
        self.assertNotIn("bbk9588_nand_geometry_score", source)
        self.assertNotIn("bbk9588_nand_sector_looks_fat16", source)

    def test_bbk9588_nand_program_erase_do_not_protect_fat_page_ranges(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")
        program_start = source.index("static void bbk9588_nand_commit_program")
        program_end = source.index("static void bbk9588_nand_commit_erase", program_start)
        append_start = source.index("static void bbk9588_nand_append_program_data")
        append_end = source.index("static void bbk9588_nand_backend_update", append_start)
        erase_start = source.index("static void bbk9588_nand_commit_erase")
        erase_end = source.index("static uint32_t bbk9588_nand_read_data", erase_start)
        program = source[program_start:program_end]
        append = source[append_start:append_end]
        erase = source[erase_start:erase_end]

        self.assertIn("uint32_t program_start;", source)
        self.assertIn("nand->program_start = nand->program_column;", append)
        self.assertIn("write_start = MIN(nand->program_start", program)
        self.assertIn("column = write_start;", program)
        self.assertIn("nand->program_len - column", program)
        self.assertIn("nand->data[page_offset + column + i] &=", program)
        self.assertIn("memset(nand->data + offset, 0xff, len);", erase)
        self.assertNotIn("column = 0;", program)
        self.assertNotIn("BBK9588_NAND_READ_SOURCE_INITIAL", source)
        self.assertNotIn("initial_data", source)
        self.assertNotIn("g_memdup2(nand->data", source)
        self.assertNotIn("NAND_FAT_PROTECT", source)
        self.assertNotIn("nand-fat-protect", source)
        self.assertNotIn("nand_fat_protect", source)
        self.assertNotIn("bbk9588_nand_page_is_fat_protected", source)
        self.assertNotIn("bbk9588-nand-program-protect", source)
        self.assertNotIn("bbk9588-nand-erase-protect", source)

    def test_bbk9588_nand_controller_source_follows_jz4740_ecc_register_semantics(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")
        helper_start = source.index("static uint32_t bbk9588_nand_nfcsr_write_value")
        helper_end = source.index("static void bbk9588_nand_begin_program", helper_start)
        helpers = source[helper_start:helper_end]
        read_start = source.index("static uint64_t bbk9588_mmio_read")
        write_start = source.index("static void bbk9588_mmio_write")
        read_body = source[read_start:write_start]
        write_end = source.index("if (s->window->kind == BBK9588_MMIO_DMAC", write_start)
        write_body = source[write_start:write_end]

        self.assertIn("#define BBK9588_NAND_NFCSR_RW_MASK     0x000000ffu", source)
        self.assertIn("#define BBK9588_NAND_NFECCR_RW_MASK    0x0000000du", source)
        self.assertIn("#define BBK9588_NAND_NFECCR_ERST       0x00000002u", source)
        self.assertIn("#define BBK9588_BCH_STATUS_W0C_MASK    0x0000001fu", source)
        self.assertIn("return value & BBK9588_NAND_NFCSR_RW_MASK;", helpers)
        self.assertIn("~BBK9588_NAND_NFECCR_ERST", helpers)
        self.assertIn("nand->bch_status &= value | ~BBK9588_BCH_STATUS_W0C_MASK;", source)
        self.assertIn("case BBK9588_NAND_NFINTS_OFF:", helpers)
        self.assertIn("bbk9588_nand_bch_ack_status(board, value);", helpers)
        self.assertIn("bbk9588_nand_control_read(board, s, aligned_offset)", read_body)
        self.assertIn("bbk9588_nand_control_write(board, s, aligned_offset, reg);", write_body)
        self.assertNotIn("offset == 0x100 && board->nand_dev", write_body)
        self.assertNotIn("offset == 0x114) {\n        bbk9588_nand_bch_ack_status", write_body)

    def test_bbk9588_uart_source_follows_jz4740_16550_semantics(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn("#define BBK9588_UART_FIFO_SIZE     16u", source)
        self.assertIn("#define BBK9588_UART_IER_OFF       0x04u", source)
        self.assertIn("#define BBK9588_UART_IIR_OFF       0x08u", source)
        self.assertIn("#define BBK9588_UART_FCR_OFF       0x08u", source)
        self.assertIn("#define BBK9588_UART_LSR_OFF       0x14u", source)
        self.assertIn("#define BBK9588_UART_LSR_RESET", source)
        self.assertIn("#define BBK9588_UART_LCR_DLAB      0x80u", source)
        self.assertIn("bool uart_thr_irq_latched;", source)
        self.assertIn("static void bbk9588_uart_latch_thr_irq", source)
        self.assertIn("static uint8_t bbk9588_uart_iir_value", source)
        self.assertIn("static bool bbk9588_uart_irq_pending", source)
        self.assertIn("static unsigned bbk9588_uart_rx_trigger_level", source)
        self.assertIn("board->uart_thr_irq_latched &&", source)
        self.assertIn("case BBK9588_UART_RBR_OFF:", source)
        self.assertIn("board->uart_lcr & BBK9588_UART_LCR_DLAB", source)
        self.assertIn("case BBK9588_UART_IER_OFF:", source)
        self.assertIn("case BBK9588_UART_FCR_OFF:", source)
        self.assertIn("value & BBK9588_UART_FCR_TFRT", source)
        self.assertIn("case BBK9588_UART_LSR_OFF:", source)
        self.assertIn("(value & 0x0fu) == BBK9588_UART_IIR_TDR", source)
        self.assertIn("board->uart_thr_irq_latched = false;", source)
        self.assertIn("board->uart_fcr = value & (BBK9588_UART_FCR_FME |", source)
        self.assertIn("board->uart_status = BBK9588_UART_LSR_RESET;", source)
        self.assertNotIn('oc, "uart-status"', source)
        self.assertNotIn("UART status bits ORed", source)
        self.assertNotIn("if (offset == 0x00 || offset == 0x04)", source)

    def test_bbk9588_udc_source_follows_jz4740_no_host_register_semantics(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "qemu"
            / "source-overlay"
            / "hw"
            / "mips"
            / "bbk9588.c"
        ).read_text(encoding="utf-8")

        self.assertIn("#define BBK9588_UDC_IRQ            BBK9588_INTC_IRQ_UDC", source)
        self.assertIn("#define BBK9588_UDC_POWER_RESET    0x20u", source)
        self.assertIn("#define BBK9588_UDC_INTRINE_RESET  0xffffu", source)
        self.assertIn("#define BBK9588_UDC_INTROUTE_RESET 0xfffeu", source)
        self.assertIn("#define BBK9588_UDC_INTRUSBE_RESET 0x06u", source)
        self.assertIn("#define BBK9588_UDC_INTRIN_ENDPOINT_MASK 0x000fu", source)
        self.assertIn("#define BBK9588_UDC_INTROUT_ENDPOINT_MASK 0x0006u", source)
        self.assertIn("#define BBK9588_UDC_EPINFO_VALUE   0x23u", source)
        self.assertIn("static bool bbk9588_udc_irq_pending", source)
        self.assertIn("static bool bbk9588_udc_in_ep_valid", source)
        self.assertIn("static bool bbk9588_udc_out_ep_valid", source)
        self.assertIn("static uint8_t bbk9588_udc_read_byte", source)
        self.assertIn("static void bbk9588_udc_write", source)
        self.assertIn("board->udc_intr_in & board->udc_intr_in_enable &\n             BBK9588_UDC_INTRIN_ENDPOINT_MASK", source)
        self.assertIn("board->udc_intr_out & board->udc_intr_out_enable &\n             BBK9588_UDC_INTROUT_ENDPOINT_MASK", source)
        self.assertIn("case BBK9588_UDC_POWER_OFF:", source)
        self.assertIn("case BBK9588_UDC_INTRINE_OFF:", source)
        self.assertIn("case BBK9588_UDC_INTROUTE_OFF:", source)
        self.assertIn("case BBK9588_UDC_INTRUSBE_OFF:", source)
        self.assertIn("case BBK9588_UDC_EPINFO_OFF:", source)
        self.assertIn("return bbk9588_udc_in_ep_valid(ep) ?", source)
        self.assertIn("return bbk9588_udc_out_ep_valid(ep) ?", source)
        self.assertIn("if (bbk9588_udc_in_ep_valid(ep)) {", source)
        self.assertIn("if (bbk9588_udc_out_ep_valid(ep)) {", source)
        self.assertIn("board->udc_power = BBK9588_UDC_POWER_RESET;", source)
        self.assertIn("BBK9588_UDC_INTRINE_RESET & BBK9588_UDC_INTRIN_ENDPOINT_MASK", source)
        self.assertIn("BBK9588_UDC_INTROUTE_RESET & BBK9588_UDC_INTROUT_ENDPOINT_MASK", source)
        self.assertIn("board->udc_intr_usb_enable = BBK9588_UDC_INTRUSBE_RESET;", source)
        self.assertIn("return bbk9588_udc_read(board, offset, size);", source)
        self.assertIn("bbk9588_udc_write(board, offset, value, size);", source)
        self.assertNotIn("qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) / (NANOSECONDS_PER_SECOND / 64u)", source)

    def test_qemu_subprocess_env_adds_msys_paths_for_source_build(self) -> None:
        env = qemu_subprocess_env(r"E:\qemu-src\build-bbk9588-win\qemu-system-mipsel.exe")

        path = env.get("PATH", "").replace("\\", "/").lower()
        self.assertIn("c:/msys64/ucrt64/bin", path)

    def test_qemu_process_backend_uses_below_normal_priority_on_windows(self) -> None:
        calls: dict[str, object] = {}

        class FakeProcess:
            stdout: list[str] = []
            stderr: list[str] = []
            returncode: int | None = None

            def poll(self) -> int | None:
                return self.returncode

            def terminate(self) -> None:
                self.returncode = 0

            def wait(self, timeout: float | None = None) -> int:
                self.returncode = 0
                return 0

            def kill(self) -> None:
                self.returncode = -9

        def fake_popen(*args: object, **kwargs: object) -> FakeProcess:
            calls["kwargs"] = kwargs
            return FakeProcess()

        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / "C200.bin"
            payload.write_bytes(b"\0" * 16)
            config = QemuSystemConfig(
                monitor="none",
                gdb="none",
                bbk_input="none",
                bbk_frame="none",
                boot_payload=QemuPayload(payload, 0x4000),
                boot_pc=0x80004000,
            )
            backend = QemuProcessBackend(config)
            with mock.patch.object(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x4000, create=True):
                with mock.patch.object(subprocess, "Popen", side_effect=fake_popen):
                    backend.start()
                    backend.stop()

        kwargs = calls.get("kwargs")
        self.assertIsInstance(kwargs, dict)
        assert isinstance(kwargs, dict)
        self.assertEqual(kwargs.get("creationflags"), 0x4000)

    def test_cli_dry_run_emits_nand_first_stage_command_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nand = Path(tmp) / "nand.bin"
            nand.write_bytes(b"\xff" * 0x1000)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.qemu_app",
                    "--nand-image",
                    str(nand),
                    "--machine",
                    "bbk9588",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        command = json.loads(completed.stdout)["command"]
        machine_arg = command[command.index("-M") + 1]
        self.assertIn("bootrom-nand=on", machine_arg)
        self.assertNotIn("bootrom-page=0x0", machine_arg)
        self.assertNotIn("bootrom-size=0x2000", machine_arg)
        self.assertNotIn("bootrom-fat-kernel=on", machine_arg)
        self.assertIn("firmware-phys=0x0", machine_arg)
        self.assertIn("reset-pc=0x80000004", machine_arg)
        self.assertIn("-drive", command)
        self.assertNotIn("-kernel", command)
        self.assertFalse(any("C200.bin" in arg for arg in command), command)
        self.assertFalse(any("u_boot_9588_4740.bin" in arg for arg in command), command)
        self.assertFalse(any(arg.startswith("loader,file=") for arg in command), command)

    def test_cli_dry_run_emits_uboot_nand_first_stage_command_when_requested(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "emu.qemu_app",
                "--boot-mode",
                "uboot",
                "--machine",
                "bbk9588",
                "--dry-run",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        command = json.loads(completed.stdout)["command"]
        machine_arg = command[command.index("-M") + 1]
        self.assertIn("bootrom-nand=on", machine_arg)
        self.assertNotIn("bootrom-page=0x40", machine_arg)
        self.assertNotIn("bootrom-size=0x80000", machine_arg)
        self.assertIn("firmware-phys=0x0", machine_arg)
        self.assertIn("reset-pc=0x80000004", machine_arg)
        self.assertNotIn("-kernel", command)
        self.assertFalse(any("C200.bin" in arg for arg in command), command)
        self.assertFalse(any("u_boot_9588_4740.bin" in arg for arg in command), command)
        self.assertFalse(any(arg.startswith("loader,file=") for arg in command), command)

    def test_public_cli_help_marks_machine_options_and_firmware_patches_diagnostic(self) -> None:
        qemu_app_help = subprocess.run(
            [sys.executable, "-m", "emu.qemu_app", "--help"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        frontend_help = subprocess.run(
            [sys.executable, "-m", "emu.web.frontend", "--help"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(qemu_app_help.returncode, 0, qemu_app_help.stderr)
        self.assertEqual(frontend_help.returncode, 0, frontend_help.stderr)
        combined_help = qemu_app_help.stdout + frontend_help.stdout
        self.assertIn("diagnostic bbk9588 -M option", combined_help)
        self.assertIn("progress-trace=on", combined_help)
        self.assertIn("Legacy diagnostic QEMU-only firmware patch", combined_help)
        self.assertNotIn("synthetic-wait-wake", combined_help)

    def test_cli_dry_run_emits_uboot_payload_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boot = root / "u_boot_9588_4740.bin"
            payload = root / "C200.bin"
            boot.write_bytes(b"\0" * 4)
            payload.write_bytes(b"\0" * 4)

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.qemu_app",
                    "--boot-mode",
                    "uboot",
                    "--image",
                    str(boot),
                    "--payload",
                    str(payload),
                    "--machine",
                    "malta",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        command = json.loads(completed.stdout)["command"]
        boot_qemu = str(boot.resolve()).replace("\\", "/")
        self.assertIn(f"loader,file={boot_qemu},addr=0x900000,force-raw=on", command)
        payload_qemu = str(payload.resolve()).replace("\\", "/")
        self.assertIn(f"loader,file={payload_qemu},addr=0x4000,force-raw=on", command)
        self.assertIn("loader,addr=0x80900000,cpu-num=0", command)

    def test_make_combined_nand_places_loader_backup_and_raw_uboot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            loader = root / "loader_9588_4740.bin"
            uboot = root / "u_boot_9588_4740.bin"
            fat = root / "fat.img"
            out = root / "nand.bin"
            loader_bytes = b"LOADER-FIRST-STAGE" * 140
            uboot_bytes = b"UBOOT-PAYLOAD-0123456789"
            fat_bytes = b"FATDATA-0123456789"
            loader.write_bytes(loader_bytes)
            uboot.write_bytes(uboot_bytes)
            fat.write_bytes(fat_bytes)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "tools" / "make_combined_nand.py"),
                    "--loader-image",
                    str(loader),
                    "--loader-page-base",
                    "0",
                    "--uboot-image",
                    str(uboot),
                    "--uboot-page-base",
                    "8",
                    "--uboot-loader-copy-bytes",
                    "0",
                    "--uboot-load-phys",
                    "0x900000",
                    "--uboot-entry",
                    "0x80900000",
                    "--fat-image",
                    str(fat),
                    "--fat-page-base",
                    "12",
                    "--output",
                    str(out),
                    "--page-size",
                    "2048",
                    "--spare-size",
                    "64",
                    "--free-blocks",
                    "0",
                    "--pages-per-block",
                    "4",
                    "--physical-blocks",
                    "4",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = out.read_bytes()

        page_size = 2048
        spare_size = 64
        stride = page_size + spare_size

        def page_data(page: int) -> bytes:
            off = page * stride
            return data[off : off + page_size]

        def page_spare(page: int) -> bytes:
            off = page * stride + page_size
            return data[off : off + spare_size]

        self.assertEqual(len(data), 4 * 4 * stride)
        self.assertEqual((page_data(0) + page_data(1))[: len(loader_bytes)], loader_bytes)
        self.assertEqual((page_data(4) + page_data(5))[: len(loader_bytes)], loader_bytes)
        self.assertNotEqual(page_data(8)[:8], b"BBKUBOOT")
        self.assertEqual(page_data(8)[: len(uboot_bytes)], uboot_bytes)
        self.assertEqual(page_spare(0)[2:5], b"\x00\x00\x00")
        self.assertEqual(page_spare(1)[2:5], b"\x00\x00\x00")
        self.assertEqual(page_spare(4)[2:5], b"\x00\x00\x00")
        self.assertEqual(page_spare(5)[2:5], b"\x00\x00\x00")
        self.assertEqual(page_spare(8)[2:5], b"\x00\x00\x00")
        self.assertEqual(page_spare(9)[2:5], b"\x00\x00\x00")
        self.assertEqual(page_data(12)[: len(fat_bytes)], fat_bytes)

    def test_make_combined_nand_can_write_legacy_uboot_header_when_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uboot = root / "u_boot_9588_4740.bin"
            fat = root / "fat.img"
            out = root / "nand.bin"
            uboot_bytes = b"UBOOT-PAYLOAD-0123456789"
            fat.write_bytes(b"FATDATA")
            uboot.write_bytes(uboot_bytes)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "tools" / "make_combined_nand.py"),
                    "--uboot-image",
                    str(uboot),
                    "--uboot-page-base",
                    "4",
                    "--legacy-uboot-header",
                    "--fat-image",
                    str(fat),
                    "--fat-page-base",
                    "8",
                    "--output",
                    str(out),
                    "--page-size",
                    "2048",
                    "--spare-size",
                    "64",
                    "--pages-per-block",
                    "4",
                    "--physical-blocks",
                    "3",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = out.read_bytes()

        stride = 2048 + 64
        header = data[4 * stride : 4 * stride + 2048]
        self.assertEqual(header[:8], b"BBKUBOOT")
        self.assertEqual(struct.unpack_from("<IIII", header, 8), (1, 0x900000, 0x80900000, len(uboot_bytes)))
        payload = data[5 * stride : 5 * stride + len(uboot_bytes)]
        self.assertEqual(payload, uboot_bytes)

    def test_make_fat16_image_places_uboot_kernel_file_under_system_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            system = root / "系统"
            data_dir = system / "数据"
            apps = root / "应用"
            data_dir.mkdir(parents=True)
            apps.mkdir()
            kernel = data_dir / "kj409588.bin"
            kernel.write_bytes(b"KJ-KERNEL")
            out = root / "fat.img"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve().parents[1] / "tools" / "make_fat16_image.py"),
                    "--output",
                    str(out),
                    "--free-clusters",
                    "0",
                    "--volume-sectors",
                    "0",
                    str(system),
                    str(apps),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            image = out.read_bytes()

        boot_off = next(
            off
            for off in range(0, min(len(image), 0x20000), 512)
            if image[off + 54 : off + 62] == b"FAT16   " and image[off + 510 : off + 512] == b"\x55\xaa"
        )
        bytes_per_sector = struct.unpack_from("<H", image, boot_off + 11)[0]
        sectors_per_cluster = image[boot_off + 13]
        reserved = struct.unpack_from("<H", image, boot_off + 14)[0]
        fat_copies = image[boot_off + 16]
        root_entries = struct.unpack_from("<H", image, boot_off + 17)[0]
        sectors_per_fat = struct.unpack_from("<H", image, boot_off + 22)[0]
        root_dir_sectors = (root_entries * 32 + bytes_per_sector - 1) // bytes_per_sector
        self.assertEqual(root_entries, 512)
        self.assertEqual(root_dir_sectors, 32)
        root_off = boot_off + (reserved + fat_copies * sectors_per_fat) * bytes_per_sector
        first_data_off = root_off + root_dir_sectors * bytes_per_sector
        cluster_size = bytes_per_sector * sectors_per_cluster

        def cluster_off(cluster: int) -> int:
            return first_data_off + (cluster - 2) * cluster_size

        def short_dir_name(name: str) -> bytes:
            return name.encode("gbk").ljust(8, b" ") + b"   "

        def entries_at(off: int, size: int) -> dict[bytes, tuple[int, int, int]]:
            entries: dict[bytes, tuple[int, int, int]] = {}
            for entry_off in range(off, off + size, 32):
                entry = image[entry_off : entry_off + 32]
                if not entry or entry[0] == 0:
                    break
                if entry[0] == 0xE5 or entry[11] == 0x0F:
                    continue
                cluster = struct.unpack_from("<H", entry, 26)[0]
                size_bytes = struct.unpack_from("<I", entry, 28)[0]
                entries[bytes(entry[:11])] = (entry[11], cluster, size_bytes)
            return entries

        root_entries_by_short = entries_at(root_off, root_dir_sectors * bytes_per_sector)
        self.assertNotIn(b"KJ409588BIN", root_entries_by_short)
        system_attr, system_cluster, _ = root_entries_by_short[short_dir_name("系统")]
        self.assertEqual(system_attr & 0x10, 0x10)

        system_entries = entries_at(cluster_off(system_cluster), cluster_size)
        data_attr, data_cluster, _ = system_entries[short_dir_name("数据")]
        self.assertEqual(data_attr & 0x10, 0x10)

        data_entries = entries_at(cluster_off(data_cluster), cluster_size)
        kernel_attr, _, kernel_size = data_entries[b"KJ409588BIN"]
        self.assertEqual(kernel_attr & 0x20, 0x20)
        self.assertEqual(kernel_size, len(b"KJ-KERNEL"))

    def test_probe_dry_run_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 4)
            out_dir = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--image",
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_probe_test",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["dry_run"])
            self.assertIn("-M", summary["command"])
            machine_arg = summary["command"][summary["command"].index("-M") + 1]
            self.assertTrue(machine_arg.startswith("bbk9588"), machine_arg)
            self.assertNotIn("touch-autocal=on", machine_arg)
            self.assertIn("-kernel", summary["command"])
            self.assertIn(str(image.resolve()), summary["command"])

    def test_probe_input_event_queue_dry_run_keeps_command_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 4)
            out_dir = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--image",
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_probe_input_queue_test",
                    "--input-event-queue-probe",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["dry_run"])
            self.assertNotIn("input_event_queue_probe", summary)
            self.assertIn("-M", summary["command"])
            machine_arg = summary["command"][summary["command"].index("-M") + 1]
            self.assertTrue(machine_arg.startswith("bbk9588"), machine_arg)
            self.assertNotIn("touch-autocal=on", machine_arg)

    def test_probe_msc_dma_write_dry_run_keeps_command_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 4)
            out_dir = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--image",
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_probe_msc_dma_write_test",
                    "--msc-dma-write-probe",
                    "--msc-dma-write-lba",
                    "0x40",
                    "--qemu-machine-option",
                    "storage-trace=on",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["dry_run"])
            self.assertNotIn("msc_dma_write_probe", summary)
            self.assertIn("storage-trace=on", summary["qemu_machine_options"])

    def test_msc_dma_write_probe_code_returns_to_ra(self) -> None:
        from emu.test import run_qemu_system_probe as probe

        code = probe._build_msc_dma_write_probe_code(0x40)

        self.assertGreater(len(code), 32)
        self.assertEqual(code[-8:], struct.pack("<II", 0x03E00008, 0))

    def test_probe_uart_register_dry_run_keeps_command_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 4)
            out_dir = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--image",
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_probe_uart_register_test",
                    "--uart-register-probe",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["dry_run"])
            self.assertNotIn("uart_register_probe", summary)

    def test_uart_register_probe_code_returns_to_ra(self) -> None:
        from emu.test import run_qemu_system_probe as probe

        code = probe._build_uart_register_probe_code()

        self.assertGreater(len(code), 32)
        self.assertEqual(code[-8:], struct.pack("<II", 0x03E00008, 0))

    def test_sadc_battery_probe_code_returns_to_ra(self) -> None:
        from emu.test import run_qemu_system_probe as probe

        code = probe._build_sadc_battery_probe_code()

        self.assertGreater(len(code), 32)
        self.assertEqual(code[-8:], struct.pack("<II", 0x03E00008, 0))

    def test_rtc_hibernate_probe_code_returns_to_ra(self) -> None:
        from emu.test import run_qemu_system_probe as probe

        code = probe._build_rtc_hibernate_probe_code()

        self.assertGreater(len(code), 32)
        self.assertEqual(code[-8:], struct.pack("<II", 0x03E00008, 0))

    def test_rtc_alarm_irq_probe_code_returns_to_ra(self) -> None:
        from emu.test import run_qemu_system_probe as probe

        code = probe._build_rtc_alarm_irq_probe_code()

        self.assertGreater(len(code), 32)
        self.assertEqual(code[-8:], struct.pack("<II", 0x03E00008, 0))

    def test_probe_lcd_frame_done_dry_run_keeps_command_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 4)
            out_dir = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--image",
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_probe_lcd_frame_done_test",
                    "--lcd-frame-done-probe",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["dry_run"])
            self.assertNotIn("lcd_frame_done_probe", summary)
            self.assertIn("-M", summary["command"])

    def test_lcd_frame_done_probe_code_returns_to_ra(self) -> None:
        from emu.test import run_qemu_system_probe as probe

        ack_code = probe._build_lcd_status_ack_probe_code()
        read_code = probe._build_lcd_status_read_probe_code()

        self.assertGreater(len(ack_code), 24)
        self.assertGreater(len(read_code), 16)
        self.assertEqual(ack_code[-8:], struct.pack("<II", 0x03E00008, 0))
        self.assertEqual(read_code[-8:], struct.pack("<II", 0x03E00008, 0))

    def test_probe_touch_move_sadc_dry_run_keeps_command_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 4)
            out_dir = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--image",
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_probe_touch_move_sadc_test",
                    "--touch-move-sadc-probe",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["dry_run"])
            self.assertNotIn("touch_move_sadc_probe", summary)
            self.assertIn("-M", summary["command"])

    def test_probe_key_gpio_dry_run_keeps_command_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 4)
            out_dir = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--image",
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_probe_key_gpio_test",
                    "--key-gpio-probe",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["dry_run"])
            self.assertNotIn("key_gpio_probe", summary)
            self.assertIn("-M", summary["command"])

    def test_key_gpio_probe_code_returns_to_ra(self) -> None:
        from emu.test import run_qemu_system_probe as probe

        code = probe._build_key_gpio_ack_probe_code()

        self.assertGreater(len(code), 40)
        self.assertEqual(code[-8:], struct.pack("<II", 0x03E00008, 0))

    def test_probe_semaphore_flow_dry_run_keeps_command_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 4)
            out_dir = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--image",
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_probe_semaphore_flow_test",
                    "--semaphore-flow-probe",
                    "--qemu-machine-option",
                    "progress-trace=on",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["dry_run"])
            self.assertNotIn("semaphore_flow_probe", summary)
            self.assertIn("progress-trace=on", summary["qemu_machine_options"])
            self.assertIn("-M", summary["command"])
            self.assertTrue(
                any(str(part).startswith("bbk9588") for part in summary["command"])
            )

    def test_probe_alarm_ui_dry_run_keeps_command_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 4)
            out_dir = root / "out"

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--image",
                    str(image),
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_probe_alarm_ui_test",
                    "--alarm-ui-probe",
                    "--qemu-machine-option",
                    "progress-trace=on",
                    "--qemu-firmware-patch",
                    "none",
                    "--dry-run",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["dry_run"])
            self.assertNotIn("alarm_ui_probe", summary)
            self.assertIn("-M", summary["command"])
            self.assertTrue(
                any(
                    str(part).startswith("bbk9588")
                    and "progress-trace=on" in str(part)
                    for part in summary["command"]
                ),
                summary["command"],
            )

    def test_probe_resource_path_has_no_guest_exception(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "emu.test.run_qemu_system_probe",
                    "--timeout",
                    "5",
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "qemu_guest_exception_guard_test",
                    "--qemu-machine-option",
                    "progress-trace=on",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stdout)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"], summary)
            self.assertNotIn("guest_exceptions", summary)

    def test_default_c200_config_uses_bbk9588_machine_without_patches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 0x200000)

            config = build_bbk_qemu_config(boot_mode="c200", image=image)

            self.assertEqual(DEFAULT_QEMU_MACHINE, "bbk9588")
            self.assertEqual(config.machine, "bbk9588")
            self.assertEqual(config.firmware_patches, ())
            self.assertNotIn("tcu-period-ms=1", config.bbk_machine_options)
            self.assertNotIn("touch-autocal=on", config.bbk_machine_options)
            assert config.boot_payload is not None
            self.assertEqual(config.boot_payload.path.resolve(), image.resolve())

    def test_bbk9588_launcher_preserves_explicit_machine_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 0x200000)

            config = build_bbk_qemu_config(
                boot_mode="c200",
                image=image,
                bbk_machine_options=("storage-trace=on", "progress-trace=on"),
            )

            self.assertIn("storage-trace=on", config.bbk_machine_options)
            self.assertIn("progress-trace=on", config.bbk_machine_options)
            self.assertNotIn("touch-autocal=on", config.bbk_machine_options)

    def test_malta_c200_config_uses_qemu_only_patch_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            original = bytearray(b"\0" * 0x129100)
            original[0xE314 : 0xE318] = bytes.fromhex("0c00028c")
            original[0xE338 : 0xE33C] = bytes.fromhex("0c00028c")
            original[0x1320 : 0x1324] = bytes.fromhex("044c428c")
            original[0x1328 : 0x132C] = bytes.fromhex("1010638c")
            image.write_bytes(original)

            config = build_bbk_qemu_config(boot_mode="c200", image=image, machine="malta")

            assert config.boot_payload is not None
            patched = config.boot_payload.path
            self.assertRegex(
                patched.name,
                r"^C200_[0-9a-f]{12}_patches_[0-9a-f]{12}\.bin$",
            )
            self.assertNotEqual(patched.resolve(), image.resolve())
            data = patched.read_bytes()
            self.assertEqual(data[0x1248 : 0x124C], bytes.fromhex("0800e003"))
            self.assertEqual(data[0x124C : 0x1250], b"\0\0\0\0")
            self.assertEqual(data[0xE314 : 0xE318], bytes.fromhex("80000234"))
            self.assertEqual(data[0xE338 : 0xE33C], bytes.fromhex("80000234"))
            self.assertEqual(data[0x1320 : 0x1324], bytes.fromhex("21100000"))
            self.assertEqual(data[0x1328 : 0x132C], bytes.fromhex("21180000"))
            self.assertEqual(data[0xA3FA4 : 0xA3FA8], b"\0\0\0\0")
            self.assertEqual(data[0xA40B4 : 0xA40B8], b"\0\0\0\0")
            self.assertEqual(data[0xA4134 : 0xA4138], b"\0\0\0\0")
            self.assertEqual(data[0x128CFC : 0x128D00], bytes.fromhex("21280000"))
            self.assertEqual(data[0xC05C : 0xC060], bytes.fromhex("00080234"))
            self.assertEqual(data[0xC060 : 0xC064], b"\0\0\0\0")
            self.assertEqual(data[0x13BA4 : 0x13BA8], bytes.fromhex("0008033c"))
            self.assertEqual(data[0x55F68 : 0x55F6C], bytes.fromhex("7f80023c"))
            self.assertEqual(data[0x55F6C : 0x55F70], bytes.fromhex("10714290"))
            self.assertEqual(data[0x55F70 : 0x55F74], bytes.fromhex("0800e003"))
            self.assertEqual(data[0x55F74 : 0x55F78], b"\0\0\0\0")
            self.assertEqual(data[0x1C9C : 0x1CA0], bytes.fromhex("20000234"))
            self.assertEqual(data[0x1CD8 : 0x1CDC], bytes.fromhex("40000234"))
            self.assertEqual(data[0x1CDC : 0x1CE0], b"\0\0\0\0")
            self.assertEqual(data[0x1D2C : 0x1D30], bytes.fromhex("20000234"))
            self.assertEqual(data[0x1D30 : 0x1D34], b"\0\0\0\0")
            self.assertEqual(data[0x57CD4 : 0x57CD8], b"\0\0\0\0")
            self.assertEqual(data[0x57DE8 : 0x57DEC], b"\0\0\0\0")
            self.assertEqual(data[0x03A0 : 0x03A4], bytes.fromhex("0800e003"))
            self.assertEqual(data[0x03A4 : 0x03A8], b"\0\0\0\0")
            self.assertEqual(data[0x54CB4 : 0x54CB8], bytes.fromhex("21100000"))
            self.assertEqual(data[0x54CB8 : 0x54CBC], bytes.fromhex("0800e003"))
            self.assertEqual(data[0x54CBC : 0x54CC0], b"\0\0\0\0")
            self.assertEqual(image.read_bytes(), bytes(original))

    def test_workspace_file_lookup_ignores_generated_build_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build" / "qemu_payloads").mkdir(parents=True)
            (root / "build" / "qemu_payloads" / "C200.bin").write_bytes(b"generated")
            (root / "system").mkdir()
            source = root / "system" / "C200.bin"
            source.write_bytes(b"source")
            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                self.assertEqual(find_workspace_file("C200.bin"), Path("system") / "C200.bin")
            finally:
                os.chdir(old_cwd)

    def test_qemu_storage_layout_prefers_combined_nand_backing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build"
            build.mkdir()
            (build / "bbk9588_fs_fat16.img").write_bytes(_fat16_boot_sector(hidden=0, root_entries=0x400))
            nand = bytearray(b"\xFF" * ((0x20 // 4 + 1) * (2048 + 64)))
            page = 0x20 // 4
            page_off = page * (2048 + 64)
            nand[page_off : page_off + 512] = _fat16_boot_sector(hidden=0x20, root_entries=0x200)
            (build / "bbk9588_nand_c200_fat_page1c40_root512_ftloob.bin").write_bytes(nand)
            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                backend = QemuProcessBackend(QemuSystemConfig())
                layout = backend._fat16_layout_from_backing()
            finally:
                os.chdir(old_cwd)
            self.assertIsInstance(layout, dict)
            assert layout is not None
            self.assertEqual(layout["volume_lba"], 0x20)
            self.assertEqual(layout["root_dir_sectors"], 0x20)
            self.assertEqual(layout["root_lba"], 0x119)
            self.assertEqual(layout["first_data_lba"], 0x139)

    def test_runtime_nand_image_is_disposable_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "nand.bin"
            original = b"\xEB\x3C\x90" + b"\xFF" * 509
            source.write_bytes(original)

            runtime = prepare_runtime_nand_image(source)
            try:
                self.assertNotEqual(runtime, source.resolve())
                self.assertEqual(runtime.read_bytes(), original)
                runtime.write_bytes(b"\x00" * len(original))
                self.assertEqual(source.read_bytes(), original)
            finally:
                runtime.unlink(missing_ok=True)

    def test_qemu_legacy_python_storage_hook_seed_is_disabled(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        backend._write_u32_paused_locked = lambda va, value: self.fail("unexpected GDB u32 seed write")  # type: ignore[method-assign]
        backend._write_u16_paused_locked = lambda va, value: self.fail("unexpected GDB u16 seed write")  # type: ignore[method-assign]
        backend._write_u8_paused_locked = lambda va, value: self.fail("unexpected GDB u8 seed write")  # type: ignore[method-assign]

        row = backend._seed_legacy_python_storage_hook_globals_paused_locked()

        self.assertFalse(row.get("seeded"), row)
        self.assertTrue(row.get("disabled"), row)
        self.assertEqual(row.get("event"), "qemu-legacy-python-storage-hook-seed")
        self.assertIn("removed from the hardware-model path", str(row.get("reason")))

    def test_qemu_bbk9588_legacy_python_storage_hook_seed_does_not_write_guest_memory(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend._write_u32_paused_locked = lambda va, value: self.fail("unexpected GDB u32 seed write")  # type: ignore[method-assign]
        backend._write_u16_paused_locked = lambda va, value: self.fail("unexpected GDB u16 seed write")  # type: ignore[method-assign]
        backend._write_u8_paused_locked = lambda va, value: self.fail("unexpected GDB u8 seed write")  # type: ignore[method-assign]

        row = backend._seed_legacy_python_storage_hook_globals_paused_locked()

        self.assertFalse(row.get("seeded"), row)
        self.assertTrue(row.get("disabled"), row)

    def test_qemu_legacy_python_resource_hook_rounds_skip_when_bbk9588_c_machine_ready(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend._read_u32_paused_locked = lambda va: 0 if va == 0x804BF440 else 0  # type: ignore[method-assign]
        backend._read_u8_paused_locked = lambda va: 1 if va == 0x804BF444 else 0  # type: ignore[method-assign]
        backend._read_pc_paused_locked = lambda: 0x8005BC70  # type: ignore[method-assign]
        backend._service_legacy_python_resource_hook_paused_locked = lambda **kwargs: self.fail("unexpected legacy Python resource hook")  # type: ignore[method-assign]

        row = backend._service_legacy_python_resource_hook_rounds_paused_locked(rounds=3)

        self.assertTrue(row.get("skipped"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")
        self.assertEqual(row.get("reason"), "qemu-c-resource-refresh-ready")
        self.assertEqual(row.get("handled_count"), 0)
        refresh = row.get("resource_refresh")
        self.assertIsInstance(refresh, dict)
        assert isinstance(refresh, dict)
        self.assertTrue(refresh.get("ready"), refresh)

    def test_qemu_legacy_python_resource_hook_rounds_skip_bbk9588_without_priming_refresh(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend._read_u32_paused_locked = lambda va: 0  # type: ignore[method-assign]
        backend._read_u8_paused_locked = lambda va: 0  # type: ignore[method-assign]
        backend._read_pc_paused_locked = lambda: 0x8005BC70  # type: ignore[method-assign]
        backend._prime_resource_refresh_paused_locked = lambda: self.fail("unexpected Python refresh prime")  # type: ignore[method-assign]
        backend._service_legacy_python_resource_hook_paused_locked = lambda **kwargs: self.fail("unexpected legacy Python resource hook")  # type: ignore[method-assign]

        row = backend._service_legacy_python_resource_hook_rounds_paused_locked(rounds=3)

        self.assertTrue(row.get("skipped"), row)
        self.assertTrue(row.get("disabled"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")
        self.assertEqual(row.get("reason"), "bbk9588-c-machine-default-path")
        self.assertEqual(row.get("handled_count"), 0)

    def test_qemu_snapshot_uses_legacy_python_hook_status_names(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend.refresh = lambda: None  # type: ignore[method-assign]
        backend.legacy_python_storage_hook_count = 2
        backend.legacy_python_storage_hook_events = [{"event": "qemu-legacy-python-storage-hook"}]

        row = backend.snapshot()

        self.assertEqual(row.get("legacy_python_storage_hook_count"), 2)
        self.assertEqual(row.get("legacy_python_storage_hook_events"), [{"event": "qemu-legacy-python-storage-hook"}])
        self.assertNotIn("storage_" + "fastpath_count", row)
        self.assertNotIn("storage_" + "fastpath_events", row)

    def test_qemu_performance_metrics_compute_rates(self) -> None:
        class _RunningProc:
            pid = 12345

            def poll(self) -> None:
                return None

        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend.proc = _RunningProc()  # type: ignore[assignment]
        backend.started_at = 90.0
        backend.frame_chardev_count = 10

        with mock.patch("emu.qemu.system._process_cpu_time_seconds", return_value=1.0):
            backend._update_performance_metrics_locked(100.0, 10.0)
        backend.frame_chardev_count = 16
        with mock.patch("emu.qemu.system._process_cpu_time_seconds", return_value=1.6):
            row = backend._update_performance_metrics_locked(101.0, 11.0)

        self.assertEqual(row.get("frame_chardev_fps"), 6.0)
        self.assertEqual(row.get("qemu_cpu_one_core_percent"), 60.0)
        self.assertFalse(row.get("guest_ips_available"), row)
        self.assertIsNone(row.get("guest_ips"))

    def test_qemu_performance_metrics_compute_guest_ips_from_perf_packets(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))

        backend._record_guest_insn_count_locked(1_000, 1000, 10.0)
        backend._record_guest_insn_count_locked(3_500, 2000, 11.0)
        row = backend._update_performance_metrics_locked(11.5, 1.5)

        self.assertTrue(row.get("guest_ips_available"), row)
        self.assertEqual(row.get("guest_ips"), 2500.0)
        self.assertEqual(row.get("guest_ips_source"), "bbk9588-frame-chardev")
        self.assertEqual(row.get("guest_insn_count"), 3500)
        self.assertEqual(row.get("guest_insn_packet_count"), 2)

    def test_qemu_frame_reader_notifies_frontend_immediately(self) -> None:
        payload = b"\x00\x00" * (240 * 320)
        packet = QEMU_BBK_FRAME_HEADER.pack(
            QEMU_BBK_FRAME_MAGIC,
            17,
            240,
            320,
            480,
            QEMU_BBK_FRAME_FORMAT_RGB565,
            len(payload),
        ) + payload

        class FrameSocket:
            def recv(self, size: int) -> bytes:
                nonlocal packet
                chunk, packet = packet[:size], packet[size:]
                return chunk

        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend.bbk_frame_sock = FrameSocket()  # type: ignore[assignment]
        notifications: list[float] = []
        backend.set_frame_ready_callback(lambda: notifications.append(time.time()))

        backend._frame_reader()

        self.assertEqual(backend.frame_chardev_count, 1)
        self.assertEqual(backend.latest_frame_chardev[0] if backend.latest_frame_chardev else None, 17)
        self.assertEqual(len(notifications), 1)

    def test_bbk9588_pen_up_preserves_unread_touch_sample(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = (root / "emu/qemu/source-overlay/hw/mips/bbk9588.c").read_text(encoding="utf-8")
        touch_set_state = source.split("static void bbk9588_touch_set_state(", 2)[2].split(
            "static uint32_t bbk9588_gpio_idle_level", 1
        )[0]

        self.assertNotIn("bbk9588_sadc_touch_fifo_clear(board);", touch_set_state)
        self.assertIn("board->sadc_status_event & ~BBK9588_SADC_STATE_PEND", touch_set_state)
        self.assertNotIn(
            "BBK9588_SADC_STATE_PEND | BBK9588_SADC_STATE_DTCH",
            touch_set_state,
        )
        self.assertIn("board->sadc_conversion_events_remaining = 5;", touch_set_state)
        self.assertIn("bool touch_move_pending;", source)
        self.assertIn("bool was_down = board->touch_down;", touch_set_state)
        self.assertIn("} else if (position_changed) {", touch_set_state)
        self.assertIn("board->touch_move_pending = true;", touch_set_state)
        self.assertIn("bool irq_needs_sync = was_down != down;", touch_set_state)
        self.assertNotIn("irq_needs_sync = true;", touch_set_state)
        initial_down = touch_set_state.split("if (!was_down) {", 1)[1].split(
            "} else if (position_changed) {", 1
        )[0]
        move = touch_set_state.split("} else if (position_changed) {", 1)[1].split(
            "    } else if (was_down) {", 1
        )[0]
        self.assertIn("board->sadc_conversion_events_remaining = 5;", initial_down)
        self.assertIn("BBK9588_SADC_STATE_PEND", initial_down)
        self.assertNotIn("board->sadc_conversion_events_remaining = 5;", move)
        self.assertNotIn("BBK9588_SADC_STATE_PEND", move)
        self.assertIn("bbk9588_sadc_queue_next_touch_sample(board);", move)

        queue_next = source.split(
            "static bool bbk9588_sadc_queue_next_touch_sample(", 1
        )[1].split("static void bbk9588_sadc_sync_irq", 1)[0]
        self.assertIn("board->sadc_status_event & BBK9588_SADC_STATE_DTCH", queue_next)
        self.assertIn("board->sadc_touch_fifo_count != 0", queue_next)
        self.assertIn("board->sadc_pending_enable & BBK9588_SADC_ADENA_TCHEN", queue_next)
        self.assertIn("bbk9588_sadc_touch_delay_ms(board, true)", queue_next)
        self.assertIn("bbk9588_sadc_touch_delay_ms(board, false)", queue_next)

        adtch_read = source.split(
            "case BBK9588_SADC_ADTCH_OFF: /* ADTCH */", 1
        )[1].split("case BBK9588_SADC_ADBDAT_OFF", 1)[0]
        self.assertIn("board->sadc_touch_fifo_count > 0", adtch_read)
        self.assertNotIn("sadc_status_event & BBK9588_SADC_STATE_DTCH", adtch_read)

        adtch_write = source.split(
            "} else if (offset == BBK9588_SADC_ADTCH_OFF) { /* ADTCH */", 1
        )[1].split("} else if (offset == BBK9588_SADC_ADBDAT_OFF)", 1)[0]
        self.assertIn("bbk9588_sadc_touch_fifo_clear(board);", adtch_write)
        self.assertNotIn("sadc_status_event", adtch_write)

    def test_frontend_coalesces_touch_moves_to_animation_frames(self) -> None:
        root = Path(__file__).resolve().parents[2]
        frontend = (root / "emu/web/frontend.py").read_text(encoding="utf-8")

        self.assertIn("function queueTouchMove(clientX, clientY, source = 'pointer')", frontend)
        self.assertIn("const minTouchMoveIntervalMs = 1000 / 30;", frontend)
        self.assertIn("const touchMoveBackpressureMs = 100;", frontend)
        self.assertIn("let touchMoveAwaitingFrame = false;", frontend)
        self.assertIn("function schedulePendingTouchMove()", frontend)
        self.assertIn("const rateDelay = minTouchMoveIntervalMs - elapsed;", frontend)
        self.assertIn("const frameDelay = touchMoveAwaitingFrame ? touchMoveBackpressureMs - elapsed : 0;", frontend)
        self.assertIn("pendingTouchMoveTimer = setTimeout(() => {", frontend)
        self.assertIn("pendingTouchMoveFrame = requestAnimationFrame(() => {", frontend)
        self.assertIn("function flushPendingTouchMove()", frontend)
        self.assertIn("function noteScreenFrame()", frontend)
        self.assertIn(
            "queueTouchMove(ev.clientX, ev.clientY, ev.pointerType || 'pointer');",
            frontend,
        )
        self.assertIn("flushPendingTouchMove();\n  const elapsed", frontend)

    def test_qemu_legacy_python_resource_hook_rounds_still_run_for_malta(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="malta"))
        calls: list[dict[str, object]] = []
        backend._read_u32_paused_locked = lambda va: 0  # type: ignore[method-assign]
        backend._read_u8_paused_locked = lambda va: 1 if va == 0x804BF444 else 0  # type: ignore[method-assign]
        backend._read_pc_paused_locked = lambda: 0x80004000  # type: ignore[method-assign]
        backend._prime_resource_refresh_paused_locked = lambda: None  # type: ignore[method-assign]
        backend._service_legacy_python_resource_hook_paused_locked = lambda **kwargs: calls.append(dict(kwargs)) or {  # type: ignore[method-assign]
            "event": "qemu-legacy-python-resource-hook-service",
            "events": [],
            "handled_count": 0,
        }

        row = backend._service_legacy_python_resource_hook_rounds_paused_locked(rounds=1)

        self.assertFalse(row.get("skipped"), row)
        self.assertEqual(len(calls), 1)

    def test_qemu_bbk9588_storage_breakpoints_omit_c_ready_idle_checks(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        pcs = backend._legacy_python_storage_hook_pcs_for_machine()

        self.assertEqual(pcs, ())
        self.assertNotIn(0x8000BA84, pcs)
        self.assertNotIn(0x8000BB98, pcs)
        self.assertNotIn(0x80007648, pcs)
        self.assertNotIn(0x800067F4, pcs)
        self.assertNotIn(0x8000F7F8, pcs)
        self.assertNotIn(0x8000F8A0, pcs)
        self.assertNotIn(0x8000F0B0, pcs)
        self.assertNotIn(0x80182D6C, pcs)
        self.assertEqual(backend._scheduler_dispatch_pcs_for_machine(), ())
        self.assertEqual(backend._resource_trace_pcs_for_machine(), ())
        self.assertEqual(backend._resource_trace_service_pcs_for_machine(), ())

    def test_qemu_malta_storage_breakpoints_keep_ready_idle_checks(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="malta"))
        pcs = backend._legacy_python_storage_hook_pcs_for_machine()

        self.assertIn(0x8000BA84, pcs)
        self.assertIn(0x8000BB98, pcs)
        self.assertIn(0x80007648, pcs)
        self.assertIn(0x800067F4, pcs)
        self.assertIn(0x8000F7F8, pcs)
        self.assertIn(0x8000F8A0, pcs)
        self.assertIn(0x8000F0B0, pcs)
        self.assertIn(0x80182D6C, pcs)
        self.assertEqual(backend._scheduler_dispatch_pcs_for_machine(), (0x8000818C,))
        self.assertIn(0x8000818C, backend._resource_trace_pcs_for_machine())
        self.assertIn(0x8000BA84, backend._resource_trace_service_pcs_for_machine())

    def test_qemu_bbk9588_legacy_python_storage_hook_service_is_disabled(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend._seed_legacy_python_storage_hook_globals_paused_locked = lambda: self.fail("unexpected seed call")  # type: ignore[method-assign]

        row = backend._service_legacy_python_storage_hooks_paused_locked()

        self.assertTrue(row.get("disabled"), row)
        self.assertFalse(row.get("events"), row)
        self.assertEqual(row.get("handled_count"), 0)
        self.assertEqual(row.get("event"), "qemu-legacy-python-storage-hook-service")

    def test_qemu_bbk9588_lcd_mirror_is_handled_by_c_machine(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))

        row = backend.enable_lcd_mirror()

        self.assertTrue(row.get("enabled"), row)
        self.assertTrue(row.get("skipped"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")

    def test_qemu_touch_device_snapshot_requires_touch_trace_option(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend._read_guest_ram_snapshot_locked = lambda *_args: self.fail("unexpected touch trace read")  # type: ignore[method-assign]

        row = backend.guest_touch_device_snapshot()

        self.assertFalse(row.get("available"), row)
        self.assertTrue(row.get("disabled"), row)
        self.assertIn("touch-trace", str(row.get("reason")))

    def test_qemu_touch_device_snapshot_reads_when_touch_trace_enabled(self) -> None:
        class _RunningProc:
            def poll(self) -> None:
                return None

        backend = QemuProcessBackend(
            QemuSystemConfig(machine="bbk9588", bbk_machine_options=("touch-trace=on",))
        )
        backend.proc = _RunningProc()  # type: ignore[assignment]
        trace = bytearray(0x144)
        struct.pack_into("<I", trace, 0, 0x54434B42)
        backend._read_guest_ram_snapshot_locked = lambda _addr, size: bytes(trace[:size])  # type: ignore[method-assign]

        row = backend.guest_touch_device_snapshot()

        self.assertTrue(row.get("available"), row)
        self.assertEqual(row.get("magic"), "0x54434b42")

    def test_qemu_legacy_python_storage_hook_breaks_are_disabled(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        backend._write_register_paused_locked = lambda reg, value: self.fail("unexpected GDB register write")  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = lambda va, data: self.fail("unexpected GDB memory write")  # type: ignore[method-assign]
        pcs = (
            0x8017BEF4,
            0x80182D58,
            0x80175E40,
            0x80174C9C,
            0x8017B4E0,
            0x8017CA10,
        )

        for pc in pcs:
            with self.subTest(pc=f"0x{pc:08x}"):
                row = backend._handle_legacy_python_storage_hook_break_paused_locked(pc)
                self.assertFalse(row.get("handled"), row)
                self.assertTrue(row.get("disabled"), row)
                self.assertEqual(row.get("pc"), f"0x{pc:08x}")
    def test_qemu_native_root_dirent_scan_skips_lfn_and_converts_entry(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        lfn = bytearray(0x20)
        lfn[0] = 0x41
        lfn[0x0B] = 0x0F
        dirent = bytearray(0x20)
        dirent[0:11] = b"MENU    BIN"
        dirent[0x0B] = 0x20
        struct.pack_into("<H", dirent, 0x14, 0x0001)
        struct.pack_into("<H", dirent, 0x1A, 0x2345)
        struct.pack_into("<I", dirent, 0x1C, 0x6789)
        sector = bytes(lfn + dirent + bytes(512 - 0x40))

        backend._fat16_layout_from_backing = lambda: {"root_lba": 0x159, "root_dir_sectors": 1}  # type: ignore[method-assign]
        backend._read_backing_sector = lambda sector_id: sector if sector_id == 0x159 else None  # type: ignore[method-assign]

        row = backend._first_root_dirent_from_backing()

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.get("name_hex"), b"MENU    BIN".hex())
        self.assertEqual(row.get("offset"), 0x20)
        self.assertEqual(row.get("cluster"), 0x00012345)
        self.assertEqual(row.get("size"), 0x6789)
        firmware = row.get("firmware")
        self.assertIsInstance(firmware, bytes)
        self.assertEqual(struct.unpack_from("<I", firmware, 0x14)[0], 0x00012345)

    def test_qemu_gui_timer_service_sets_event_flag(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="malta"))
        blocks: dict[int, bytearray] = {}
        writes: dict[int, bytes] = {}
        table = bytearray(0x40)
        struct.pack_into("<I", table, 0, 0x80801000)
        blocks[0x804A6B40] = table
        entry = bytearray(0x10)
        struct.pack_into("<IIII", entry, 0, 0x80802000, 7, 2, 1)
        blocks[0x80801000] = entry
        owner = bytearray(0xF4)
        struct.pack_into("<I", owner, 0xF0, 0x80803000)
        blocks[0x80802000] = owner
        event = bytearray(0xA0)
        struct.pack_into("<I", event, 0x20 + 3 * 4, 0x80802000)
        struct.pack_into("<I", event, 0x60 + 3 * 4, 7)
        blocks[0x80803000] = event

        def read_mem(va: int, size: int) -> bytes:
            for base, data in blocks.items():
                if base <= va and va + size <= base + len(data):
                    offset = va - base
                    return bytes(data[offset : offset + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            writes[va] = bytes(data)
            for base, block in blocks.items():
                if base <= va and va + len(data) <= base + len(block):
                    offset = va - base
                    block[offset : offset + len(data)] = data
                    return

        backend._is_guest_ram_va = lambda va, size=1: va >= 0x80000000 and size >= 0  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]

        result = backend._service_gui_timer_entries_paused_locked()

        self.assertEqual(result.get("fired"), 1, result)
        self.assertEqual(struct.unpack("<I", writes[0x8080100C])[0], 0)
        self.assertEqual(struct.unpack("<I", writes[0x80803000])[0], 1 << 3)
        self.assertEqual(backend.gui_timer_fire_count, 1)

    def test_bbk9588_gui_timer_service_uses_c_machine(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))

        result = backend._service_gui_timer_entries_paused_locked()

        self.assertTrue(result.get("skipped"), result)
        self.assertEqual(result.get("source"), "qemu-c-machine")
        self.assertEqual(result.get("reason"), "qemu-c-machine-gui-timer-service")

    def test_qemu_task_context_trace_reads_target_context(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        blocks: dict[int, bytearray] = {}
        globals_block = bytearray(0x80)
        struct.pack_into("<I", globals_block, 0x30, 0x806C5530)
        struct.pack_into("<I", globals_block, 0x50, 0x806C5370)
        globals_block[0x10] = 0x3F
        globals_block[0x11] = 0x09
        struct.pack_into("<I", globals_block, 0x1C, 4)
        blocks[0x80473F00] = globals_block
        target_node = bytearray(0x80)
        struct.pack_into("<I", target_node, 0, 0x8078D600)
        target_node[0x35] = 9
        target_node[0x36] = 1
        target_node[0x50:0x56] = b"task9\0"
        blocks[0x806C5530] = target_node
        current_node = bytearray(0x80)
        struct.pack_into("<I", current_node, 0, 0x806C5000)
        current_node[0x35] = 0x3F
        blocks[0x806C5370] = current_node
        ctx = bytearray(0x7C)
        struct.pack_into("<I", ctx, 0x70, 0x80173504)
        blocks[0x8078D600] = ctx
        regs = {29: 0x8078C000, 31: 0x800080F8}

        def read_mem(va: int, size: int) -> bytes:
            for base, data in blocks.items():
                if base <= va and va + size <= base + len(data):
                    offset = va - base
                    return bytes(data[offset : offset + size])
            raise KeyError(hex(va))

        backend._is_guest_ram_va = lambda va, size=1: va >= 0x80000000 and size >= 0  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: regs[reg]  # type: ignore[method-assign]

        row = backend._task_context_trace_row_paused_locked(0x800A7C18)

        self.assertEqual(row.get("kind"), "task-context-switch-save")
        self.assertEqual(row.get("target_node"), "0x806c5530")
        self.assertEqual(row.get("current_node"), "0x806c5370")
        self.assertEqual(row.get("target_ctx_sp"), "0x8078d600")
        self.assertEqual(row.get("target_pc"), "0x80173504")
        self.assertEqual(row.get("target_task", {}).get("name"), "task9")

    def test_qemu_scheduled_fs_scan_service_runs_only_for_fs_task(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        memory: dict[int, bytearray] = {
            0x806C5D10 + 9 * 4: bytearray(struct.pack("<I", 0x806C5530)),
            0x806C5530: bytearray(0x80),
            0x8078D600: bytearray(0x80),
            0x80473F08: bytearray(0x50),
            0x8024A998: bytearray(range(0x100)),
        }
        memory[0x80473F08][0x01] = 1
        memory[0x80473F08][0x08] = 0x3F
        memory[0x80473F08][0x09] = 0x3F
        memory[0x80473F08][0x30] = 1
        memory[0x80473F08][0x39] = 1
        struct.pack_into("<I", memory[0x806C5530], 0, 0x8078D600)
        memory[0x806C5530][0x35] = 9
        memory[0x806C5530][0x36] = 1
        memory[0x806C5530][0x50:0x56] = b"task9\0"
        struct.pack_into("<I", memory[0x8078D600], 0x70, 0x80173504)
        calls: list[tuple[float, int]] = []

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._service_fs_scan_probe_paused_locked = lambda *, timeout, max_hits: calls.append((timeout, max_hits)) or {  # type: ignore[method-assign]
            "event": "qemu-fs-scan-probe",
            "native_fs_scan_fallback": {"available": True, "applied": True},
            "result_dirent": {"name_hex": "4141412020202020202020"},
        }

        row = backend._service_scheduled_fs_scan_task_paused_locked(9, timeout=1.25, max_hits=99)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(calls, [(1.25, 99)])
        self.assertEqual(row.get("context", {}).get("target_pc"), "0x80173504")
        self.assertEqual(row.get("context", {}).get("pc_candidates", {}).get("ctx_70"), "0x80173504")
        self.assertEqual(row.get("native_fs_scan_fallback", {}).get("applied"), True)

        struct.pack_into("<I", memory[0x8078D600], 0x70, 0x800080F0)
        struct.pack_into("<I", memory[0x8078D600], 0x74, 0x80173504)
        calls.clear()
        row = backend._service_scheduled_fs_scan_task_paused_locked(9)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(calls, [(2.0, 512)])

        struct.pack_into("<I", memory[0x8078D600], 0x74, 0x800080F0)
        calls.clear()
        row = backend._service_scheduled_fs_scan_task_paused_locked(9)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("trigger"), "scheduler-selected-task")
        self.assertEqual(calls, [(2.0, 512)])

        memory[0x80473F08][0x39] = 2
        calls.clear()
        row = backend._service_scheduled_fs_scan_task_paused_locked(9)

        self.assertFalse(row.get("handled"), row)
        self.assertEqual(row.get("reason"), "task-context-is-not-fs-scan")
        self.assertEqual(calls, [])

    def test_qemu_scheduler_ready_seed_marks_task_ready(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        scheduler = bytearray(0x3A)
        scheduler[0x01] = 1
        scheduler[0x08] = 0x3F
        scheduler[0x09] = 0x3F
        scheduler[0x30] = 0x80
        struct.pack_into("<I", scheduler, 0x28, 0x806C5370)
        memory: dict[int, bytearray] = {
            0x80473F08: scheduler,
            0x806C5D10 + 9 * 4: bytearray(struct.pack("<I", 0x806C5530)),
            0x806C5530: bytearray(0x80),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: va >= 0x80000000 and size >= 0  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]

        row = backend._seed_scheduler_ready_task_paused_locked(9)

        self.assertTrue(row.get("seeded"), row)
        self.assertEqual(row.get("group_after"), "0x82")
        self.assertEqual(read_mem(0x80473F38, 1), b"\x82")
        self.assertEqual(read_mem(0x80473F41, 1), b"\x02")
        self.assertEqual(read_mem(0x80473F08, 1), b"\x01")

    def test_qemu_bbk9588_scheduler_ready_seed_is_handled_by_c_machine(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))

        row = backend._seed_scheduler_ready_task_paused_locked(9)

        self.assertTrue(row.get("seeded"), row)
        self.assertTrue(row.get("skipped"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")

    def test_qemu_bbk9588_scheduler_tick_clamp_is_handled_by_c_machine(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))

        row = backend._clamp_scheduler_tick_paused_locked()

        self.assertTrue(row.get("clamped"), row)
        self.assertTrue(row.get("skipped"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")

    def test_qemu_bbk9588_settle_initial_gui_skips_python_services(self) -> None:
        class DummyProc:
            def poll(self) -> None:
                return None

        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend.proc = DummyProc()  # type: ignore[assignment]
        backend.gdb_sock = None
        backend.snapshot = lambda: {"pc": "0x8000985c"}  # type: ignore[method-assign]
        backend._pause_for_gdb_locked = lambda: self.fail("unexpected GDB pause")  # type: ignore[method-assign]
        backend._service_legacy_python_storage_hooks_paused_locked = lambda **kwargs: self.fail(  # type: ignore[method-assign]
            "unexpected legacy Python storage hook service"
        )
        backend._service_legacy_python_resource_hook_rounds_paused_locked = lambda **kwargs: self.fail(  # type: ignore[method-assign]
            "unexpected legacy Python resource hook service"
        )
        backend._seed_scheduler_ready_task_paused_locked = lambda task: self.fail(  # type: ignore[method-assign]
            "unexpected Python scheduler ready seed"
        )
        backend._clamp_scheduler_tick_paused_locked = lambda: self.fail(  # type: ignore[method-assign]
            "unexpected Python scheduler tick clamp"
        )
        backend._service_system_boot_file_probes_paused_locked = lambda **kwargs: self.fail(  # type: ignore[method-assign]
            "unexpected Python boot file probes"
        )
        backend._service_fs_scan_probe_paused_locked = lambda **kwargs: self.fail(  # type: ignore[method-assign]
            "unexpected Python fs scan probe"
        )
        backend._pump_gui_event_poller_paused_locked = lambda: self.fail("unexpected Python event poller")  # type: ignore[method-assign]
        backend._pump_gui_idle_dispatcher_paused_locked = lambda: self.fail("unexpected Python idle dispatcher")  # type: ignore[method-assign]

        row = backend.settle_initial_gui()

        self.assertEqual(row.get("source"), "qemu-c-machine")
        self.assertTrue(row.get("skipped_python_services"), row)
        self.assertEqual(row.get("reason"), "bbk9588-c-machine-default-path")
        self.assertNotIn("system_boot_file_probes", row)
        self.assertNotIn("event_poller", row)
        self.assertEqual(row.get("final_pc"), "0x8000985c")
        self.assertTrue(row.get("legacy_python_storage_hook", {}).get("skipped"), row)
        self.assertTrue(row.get("legacy_python_resource_hook", {}).get("skipped"), row)

    def test_qemu_bbk9588_python_guest_services_are_disabled(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend.proc = object()  # type: ignore[assignment]
        backend.gdb_sock = object()  # type: ignore[assignment]
        backend._is_guest_ram_va = lambda va, size=1: True  # type: ignore[method-assign]
        backend._read_u32_paused_locked = lambda va: self.fail("unexpected guest read")  # type: ignore[method-assign]
        backend._read_u8_paused_locked = lambda va: self.fail("unexpected guest read")  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda regno: self.fail("unexpected register read")  # type: ignore[method-assign]
        backend._write_u8_paused_locked = lambda va, value: self.fail("unexpected guest write")  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = lambda va, data: self.fail("unexpected guest write")  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda regno, value: self.fail("unexpected register write")  # type: ignore[method-assign]
        backend._call_guest_function_stepped_paused_locked = lambda *args, **kwargs: self.fail("unexpected guest call")  # type: ignore[method-assign]

        rows = [
            backend._service_fs_scan_probe_paused_locked(),
            backend._service_scheduled_fs_scan_task_paused_locked(),
            backend._service_task_context_trace_paused_locked(),
            backend._service_fs_trace_paused_locked(),
            backend._service_event_loop_trace_paused_locked(),
            backend._prepare_backing_file_path_probe_paused_locked(event="qemu-file-open-probe"),
            backend._service_first_file_open_probe_paused_locked(),
            backend._service_first_file_high_level_open_probe_paused_locked(),
            backend._pump_gui_idle_dispatcher_paused_locked(),
            backend._settle_gui_modal_close_paused_locked(),
            backend._pump_gui_event_poller_paused_locked(),
            backend._settle_gui_repaint_paused_locked(),
        ]

        self.assertIsNone(backend._prime_resource_refresh_paused_locked())
        for row in rows:
            self.assertTrue(row.get("disabled"), row)
            self.assertTrue(row.get("skipped"), row)
            self.assertEqual(row.get("source"), "qemu-c-machine")
            self.assertEqual(row.get("reason"), "bbk9588-c-machine-default-path")
            self.assertFalse(row.get("handled"), row)

    def test_qemu_scheduler_ready_sanitize_clears_missing_task_nodes(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="malta"))
        memory: dict[int, bytearray] = {
            0x80473F38: bytearray(b"\x82"),
            0x80473F40: bytearray(b"\x01\x06"),
            0x806C5D10: bytearray(struct.pack("<I", 0x806C5300)),
            0x806C5D10 + 9 * 4: bytearray(struct.pack("<I", 0x806C5530)),
            0x806C5300: bytearray(0x80),
            0x806C5530: bytearray(0x80),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: 0x806C0000 <= va and va + size <= 0x80700000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]

        row = backend._sanitize_scheduler_ready_bits_paused_locked()

        self.assertTrue(row.get("changed"), row)
        self.assertEqual(row.get("cleared_tasks"), ["0x0a"])
        self.assertEqual(read_mem(0x80473F38, 1), b"\x82")
        self.assertEqual(read_mem(0x80473F40, 2), b"\x01\x02")

    def test_bbk9588_scheduler_ready_sanitize_uses_c_machine(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))

        row = backend._sanitize_scheduler_ready_bits_paused_locked()

        self.assertFalse(row.get("changed"), row)
        self.assertTrue(row.get("skipped"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")
        self.assertEqual(row.get("reason"), "qemu-c-machine-scheduler-ready-sanitize")

    def test_qemu_scheduler_dispatch_task_node_returns_on_missing_node(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0, 37: 0x8000818C}

        backend._is_guest_ram_va = lambda va, size=1: False  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_scheduler_dispatch_task_node_paused_locked(0x8000818C)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("reason"), "missing-task-node-return-dispatcher")
        self.assertEqual(registers[37], 0x800081B8)

    def test_qemu_scheduler_dispatch_snapshot_computes_next_task(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        fields = bytearray(0x50)
        fields[0x01] = 1
        fields[0x08] = 0x3F
        fields[0x09] = 0x3F
        fields[0x30] = 1
        fields[0x39] = 1
        order = bytearray(range(0x100))
        memory: dict[int, bytearray] = {
            0x80473F08: fields,
            0x8024A998: order,
            0x806C5D10 + 9 * 4: bytearray(struct.pack("<I", 0x806C5530)),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]

        row = backend._scheduler_dispatch_snapshot_paused_locked()

        self.assertTrue(row.get("computed"), row)
        self.assertEqual(row.get("next_task"), "0x09")
        self.assertEqual(row.get("target_node"), "0x806c5530")

    def test_qemu_event_loop_empty_return_uses_scratch_event(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0x000000FF, 4: 0x8024A22C}
        memory: dict[int, bytearray] = {
            0x80473F6C: bytearray(struct.pack("<I", 0x806C5160)),
            0x804BF440: bytearray(struct.pack("<I", 0x00080000)),
            0x807F7300: bytearray(b"\xAA" * 0x1C),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va < 0x81000000 and size >= 0  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        first = backend._handle_event_loop_empty_return_paused_locked(0x8012CCFC)
        self.assertTrue(first.get("handled"), first)
        self.assertEqual(first.get("event_code"), "0x00000006")
        self.assertEqual(registers[2], 0x807F7300)
        self.assertEqual(registers[5], 6)
        self.assertEqual(registers[37], 0x8012CD00)
        words = struct.unpack("<7I", read_mem(0x807F7300, 0x1C))
        self.assertEqual(words[1], 6)
        self.assertEqual(backend.event_loop_empty_fix_count, 1)
        self.assertEqual(backend.event_loop_synth_event_count, 1)

        registers[2] = 0x000000FF
        second = backend._handle_event_loop_empty_return_paused_locked(0x8012CCFC)
        self.assertTrue(second.get("handled"), second)
        self.assertEqual(second.get("event_code"), "0x00000007")
        self.assertEqual(registers[5], 7)
        self.assertEqual(registers[37], 0x8012CD00)
        words = struct.unpack("<7I", read_mem(0x807F7300, 0x1C))
        self.assertEqual(words[1], 7)
        self.assertEqual(backend.event_loop_empty_fix_count, 2)
        self.assertEqual(backend.event_loop_synth_event_count, 2)

        registers[2] = 0x000000FF
        third = backend._handle_event_loop_empty_return_paused_locked(0x8012CCFC)
        self.assertTrue(third.get("handled"), third)
        self.assertEqual(third.get("event_code"), "0x00000004")
        self.assertEqual(registers[5], 4)
        self.assertEqual(
            third.get("resource_state_pump"),
            {
                "stage": "initialized-resource-flag",
                "flags_before": "0x00080000",
                "flags_after": "0x00000004",
                "byte_804bf444_before": "0x00",
                "byte_804bf444_after": "0x00",
            },
        )
        words = struct.unpack("<7I", read_mem(0x807F7300, 0x1C))
        self.assertEqual(words[1], 4)
        self.assertEqual(struct.unpack("<I", read_mem(0x804BF440, 4))[0], 0x00000004)
        self.assertEqual(backend.event_loop_empty_fix_count, 3)
        self.assertEqual(backend.event_loop_synth_event_count, 3)

        registers[2] = 0x000000FF
        fourth = backend._handle_event_loop_empty_return_paused_locked(0x8012CCFC)
        self.assertTrue(fourth.get("handled"), fourth)
        self.assertNotIn("stop_service", fourth)
        self.assertEqual(fourth.get("event_code"), "0x00000004")
        self.assertEqual(registers[5], 4)
        self.assertEqual(
            fourth.get("resource_state_pump"),
            {
                "stage": "arm-resource-refresh",
                "flags_before": "0x00000004",
                "flags_after": "0x00000000",
                "byte_804bf444_before": "0x00",
                "byte_804bf444_after": "0x01",
            },
        )
        self.assertEqual(struct.unpack("<I", read_mem(0x804BF440, 4))[0], 0x00000000)
        self.assertEqual(read_mem(0x804BF444, 1), b"\x01")
        self.assertEqual(backend.event_loop_empty_fix_count, 4)
        self.assertEqual(backend.event_loop_synth_event_count, 4)

        registers[2] = 0x000000FF
        fifth = backend._handle_event_loop_empty_return_paused_locked(0x8012CCFC)
        self.assertTrue(fifth.get("handled"), fifth)
        self.assertNotIn("stop_service", fifth)
        self.assertEqual(fifth.get("event_code"), "0x00000004")
        self.assertEqual(registers[5], 4)
        self.assertEqual(
            fifth.get("resource_state_pump"),
            {
                "stage": "resource-refresh-ready",
                "flags_before": "0x00000000",
                "flags_after": "0x00000000",
                "byte_804bf444_before": "0x01",
                "byte_804bf444_after": "0x01",
            },
        )
        self.assertEqual(backend.event_loop_empty_fix_count, 5)
        self.assertEqual(backend.event_loop_synth_event_count, 5)

        registers[2] = 0x000000FF
        sixth = backend._handle_event_loop_empty_return_paused_locked(0x8012CCFC)
        self.assertTrue(sixth.get("handled"), sixth)
        self.assertNotIn("stop_service", sixth)
        self.assertEqual(sixth.get("event_code"), "0x00000003")
        self.assertEqual(registers[5], 3)
        self.assertEqual(backend.event_loop_empty_fix_count, 6)
        self.assertEqual(backend.event_loop_synth_event_count, 6)

        registers[2] = 0x000000FF
        seventh = backend._handle_event_loop_empty_return_paused_locked(0x8012CCFC)
        self.assertTrue(seventh.get("handled"), seventh)
        self.assertTrue(seventh.get("stop_service"), seventh)
        self.assertEqual(seventh.get("event_code"), "0x00000000")
        self.assertEqual(registers[5], 0)
        words = struct.unpack("<7I", read_mem(0x807F7300, 0x1C))
        self.assertEqual(words[1], 0)
        self.assertEqual(backend.event_loop_empty_fix_count, 7)
        self.assertEqual(backend.event_loop_synth_event_count, 6)

    def test_qemu_event_loop_empty_skips_legacy_python_resource_hook_when_bbk9588_c_ready(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend.event_loop_synth_event_count = 2
        registers = {2: 0x000000FF, 4: 0x8024A22C}
        memory: dict[int, bytearray] = {
            0x80473F6C: bytearray(struct.pack("<I", 0x806C5160)),
            0x804BF440: bytearray(struct.pack("<I", 0)),
            0x804BF444: bytearray(b"\x01"),
            0x807F7300: bytearray(b"\xAA" * 0x1C),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va < 0x81000000 and size >= 0  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._pump_resource_state_globals_paused_locked = lambda: self.fail("unexpected legacy Python resource hook")  # type: ignore[method-assign]

        row = backend._handle_event_loop_empty_return_paused_locked(0x8012CCFC)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("event_code"), "0x00000004")
        self.assertNotIn("resource_state_pump", row)
        skipped = row.get("resource_state_pump_skipped")
        self.assertIsInstance(skipped, dict)
        assert isinstance(skipped, dict)
        self.assertEqual(skipped.get("source"), "qemu-c-machine")
        self.assertEqual(registers[5], 4)

    def test_qemu_resource_trace_row_reads_service_globals(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0x12345678, 4: 0x804BF43C, 5: 0, 6: 0x807F7300, 7: 7, 29: 0x8033AE50, 31: 0x8012CEBC}
        memory: dict[int, bytearray] = {
            0x804BF43C: bytearray(struct.pack("<IIII", 0x806C7000, 0x00000001, 0x00000002, 0x00000003)),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]

        row = backend._resource_trace_row_paused_locked(0x8017B198)

        self.assertEqual(row.get("pc"), "0x8017b198")
        regs = row.get("regs")
        self.assertIsInstance(regs, dict)
        assert isinstance(regs, dict)
        self.assertEqual(regs.get("a0"), "0x804bf43c")
        globals_ = row.get("globals")
        self.assertIsInstance(globals_, dict)
        assert isinstance(globals_, dict)
        self.assertEqual(globals_.get("resource_queue_804bf43c"), "0x806c7000")
        self.assertEqual(globals_.get("resource_flags_804bf440"), "0x00000001")
        self.assertIn("desktop_resource_mgr_80478358", globals_)
        self.assertIn("desktop_resource_count_8047835c", globals_)

    def test_qemu_resource_trace_pcs_cover_dir_scan_consumers(self) -> None:
        pcs = set(QemuProcessBackend._resource_trace_pcs())

        self.assertIn(0x80171620, pcs)
        self.assertIn(0x801716FC, pcs)
        self.assertIn(0x801717F4, pcs)
        self.assertIn(0x80171800, pcs)
        self.assertIn(0x801718A0, pcs)
        self.assertIn(0x801718B4, pcs)
        self.assertIn(0x801718BC, pcs)
        self.assertIn(0x80173920, pcs)
        self.assertIn(0x8017395C, pcs)
        self.assertIn(0x8001E8B4, pcs)
        self.assertIn(0x8001E8C0, pcs)
        self.assertIn(0x8000FC74, pcs)
        self.assertIn(0x800100DC, pcs)
        self.assertIn(0x8001028C, pcs)
        self.assertIn(0x8001032C, pcs)
        self.assertIn(0x800E1A94, pcs)
        self.assertIn(0x800E1BF0, pcs)
        self.assertIn(0x800E1C68, pcs)
        self.assertIn(0x800E1C84, pcs)
        self.assertIn(0x800E3C68, pcs)
        self.assertIn(0x800E447C, pcs)
        self.assertIn(0x800E5C44, pcs)
        self.assertIn(0x800E5C58, pcs)
        self.assertIn(0x800DFC68, pcs)
        self.assertIn(0x8001E900, pcs)
        self.assertIn(0x80172630, pcs)
        self.assertIn(0x80172670, pcs)
        self.assertIn(0x8017268C, pcs)
        self.assertIn(0x801726F4, pcs)
        self.assertIn(0x80172700, pcs)
        self.assertIn(0x8017E000, pcs)
        self.assertIn(0x801813E0, pcs)
        self.assertIn(0x80181400, pcs)

    def test_qemu_resource_trace_branch_handles_dirent_attribute_delay_slot(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0x10, 20: 0, 29: 0x8078DA90, 37: 0x80173928}
        memory = {0x8078DA90 + 0x7C: bytearray(struct.pack("<I", 0x000030F4))}

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]

        row = backend._handle_resource_trace_branch_paused_locked(0x80173928)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("return_pc"), "0x80173930")
        self.assertEqual(registers[20], 0x000030F4)
        self.assertEqual(registers[37], 0x80173930)

        registers[2] = 0
        row = backend._handle_resource_trace_branch_paused_locked(0x80173928)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("return_pc"), "0x80173e84")
        self.assertEqual(registers[37], 0x80173E84)

    def test_qemu_resource_trace_branch_returns_ready_for_desktop_resource_buffer(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        data_va = 0x80960200
        registers = {2: 0, 19: data_va, 31: 0x801754E4, 37: 0x801705EC}
        memory = {data_va: bytearray(b"\xE5LX\x07")}

        def read_mem(va: int, size: int) -> bytes:
            offset = va - data_va
            return bytes(memory[data_va][offset : offset + size])

        def write_mem(va: int, data: bytes) -> None:
            offset = va - data_va
            memory[data_va][offset : offset + len(data)] = data

        backend._is_guest_ram_va = lambda va, size=1: data_va <= va and va + size <= data_va + len(memory[data_va])  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_resource_trace_branch_paused_locked(0x801705EC)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("reason"), "desktop-resource-buffer-ready")
        self.assertEqual(row.get("restored_header"), "DLX")
        self.assertEqual(registers[2], 1)
        self.assertEqual(registers[37], 0x801754E4)
        self.assertEqual(bytes(memory[data_va][:3]), b"DLX")

    def test_qemu_resource_trace_callsite_returns_ready_for_desktop_resource_buffer(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        data_va = 0x80960200
        registers = {2: 0, 19: data_va, 37: 0x801754DC}
        memory = {data_va: bytearray(b"\xE5M6\x36")}

        def read_mem(va: int, size: int) -> bytes:
            offset = va - data_va
            return bytes(memory[data_va][offset : offset + size])

        def write_mem(va: int, data: bytes) -> None:
            offset = va - data_va
            memory[data_va][offset : offset + len(data)] = data

        backend._is_guest_ram_va = lambda va, size=1: data_va <= va and va + size <= data_va + len(memory[data_va])  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_resource_trace_branch_paused_locked(0x801754DC)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("reason"), "desktop-resource-buffer-ready-at-callsite")
        self.assertEqual(row.get("restored_header"), "BM")
        self.assertEqual(registers[2], 1)
        self.assertEqual(registers[37], 0x801754E4)
        self.assertEqual(bytes(memory[data_va][:3]), b"BM6")

    def test_qemu_semaphore_wait_fastpath_forces_empty_acquire(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0, 4: 0x806C5230, 6: 0x8033AE20, 31: 0x8000F838}
        memory: dict[int, bytearray] = {
            0x806C5230: bytearray(b"\x03\x00\x00\x00" + struct.pack("<I", 0)),
            0x8033AE20: bytearray(b"\xAA"),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va < 0x81000000 and size >= 0  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_semaphore_wait_paused_locked(0x8000BA84)

        self.assertTrue(row.get("handled"), row)
        self.assertTrue(row.get("forced_empty_acquire"), row)
        self.assertEqual(read_mem(0x8033AE20, 1), b"\x00")
        self.assertEqual(registers[2], 0)
        self.assertEqual(registers[37], 0x8000F838)

    def test_qemu_semaphore_release_fastpath_increments_count(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0xFFFFFFFF, 4: 0x806C5230, 31: 0x8017FC94}
        memory: dict[int, bytearray] = {
            0x806C5230: bytearray(b"\x03\x00\x00\x00" + struct.pack("<I", 0)),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va < 0x81000000 and size >= 0  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_semaphore_release_paused_locked(0x8000BB98)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("count_after"), "0x00000001")
        self.assertEqual(read_mem(0x806C5234, 4), struct.pack("<I", 1))
        self.assertEqual(registers[2], 0)
        self.assertEqual(registers[37], 0x8017FC94)

    def test_qemu_storage_ready_check_fastpath_returns_ready(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0xFFFFFFFF, 31: 0x80170310}
        memory: dict[int, bytearray] = {
            0x80477CE0: bytearray(struct.pack("<I", 0x806C5230)),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_storage_ready_check_paused_locked(0x8000F7F8)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "storage-ready-check")
        self.assertEqual(row.get("storage_object_80477ce0"), "0x806c5230")
        self.assertEqual(registers[2], 0)
        self.assertEqual(registers[37], 0x80170310)

    def test_qemu_storage_idle_check_fastpath_returns_not_busy(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0xFFFFFFFF, 31: 0x80170600}
        memory: dict[int, bytearray] = {
            0x80477CE0: bytearray(struct.pack("<I", 0x806C5230)),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_storage_idle_check_paused_locked(0x8000F8A0)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "storage-idle-check")
        self.assertEqual(row.get("storage_object_80477ce0"), "0x806c5230")
        self.assertEqual(row.get("value"), "0x00000000")
        self.assertEqual(registers[2], 0)
        self.assertEqual(registers[37], 0x80170600)

    def test_qemu_storage_idle_check_fastpath_reports_resource_refresh_ready(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0, 31: 0x801705FC}
        memory: dict[int, bytearray] = {
            0x80477CE0: bytearray(struct.pack("<I", 0x806C5230)),
            0x804BF440: bytearray(struct.pack("<I", 0)),
            0x804BF444: bytearray(b"\x01"),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_storage_idle_check_paused_locked(0x8000F8A0)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("resource_flags_804bf440"), "0x00000000")
        self.assertEqual(row.get("resource_byte_804bf444"), "0x01")
        self.assertEqual(row.get("value"), "0x00000001")
        self.assertEqual(registers[2], 1)
        self.assertEqual(registers[37], 0x801705FC)

    def test_qemu_heap_alloc_fastpath_returns_zeroed_guest_buffer(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        backend.qemu_heap_next = 0x80960000
        registers = {2: 0, 4: 0x21, 31: 0x801735B8}
        memory: dict[int, bytearray] = {}

        def write_mem(va: int, data: bytes) -> None:
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_heap_alloc_paused_locked(0x80007648)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "heap-alloc")
        self.assertEqual(row.get("ptr"), "0x80960000")
        self.assertEqual(registers[2], 0x80960000)
        self.assertEqual(registers[37], 0x801735B8)
        self.assertEqual(bytes(memory[0x80960000]), bytes(0x30))
        self.assertEqual(backend.qemu_heap_next, 0x80960030)

    def test_qemu_heap_free_fastpath_noops(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0xFFFFFFFF, 4: 0x80960000, 31: 0x8017379C}
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_heap_free_paused_locked(0x800067F4)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "heap-free")
        self.assertEqual(registers[2], 0)
        self.assertEqual(registers[37], 0x8017379C)

    def test_qemu_raw_sector_read_fastpath_reads_backing_sector(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0xFFFFFFFF, 4: 3, 5: 0x8078D280, 31: 0x801706E8}
        dest = bytearray(b"\xAA" * 512)
        memory: dict[int, bytearray] = {0x8078D280: dest}
        sector = bytes((i & 0xFF) for i in range(512))

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va < 0x81000000 and size >= 0  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._read_backing_sector = lambda value: sector if value == 3 else None  # type: ignore[method-assign]

        row = backend._handle_raw_sector_read_paused_locked(0x8000F0B0)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "raw-sector-read")
        self.assertEqual(read_mem(0x8078D280, 16), sector[:16])
        self.assertEqual(registers[2], 0)
        self.assertEqual(registers[37], 0x801706E8)

    def test_qemu_cached_sector_read_fastpath_reads_block_offset(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0xFFFFFFFF, 4: 0x8078D800, 5: 2, 6: 1, 7: 2, 31: 0x80182B38}
        dest = bytearray(b"\xAA" * 1024)
        memory: dict[int, bytearray] = {
            0x8078D800: dest,
            0x804BF480: bytearray(struct.pack("<I", 0x800)),
        }
        sectors = {9: b"\x09" * 512, 10: b"\x0A" * 512}

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va < 0x81000000 and size >= 0  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._read_backing_sector = lambda value: sectors.get(value)  # type: ignore[method-assign]

        row = backend._handle_cached_sector_read_paused_locked(0x80182D6C)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("start_sector"), "0x9")
        self.assertEqual(read_mem(0x8078D800, 512), b"\x09" * 512)
        self.assertEqual(read_mem(0x8078DA00, 512), b"\x0A" * 512)
        self.assertEqual(registers[2], 0)
        self.assertEqual(registers[37], 0x80182B38)

    def test_qemu_dir_sector_read_fastpath_reads_backing_sector(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0xFFFFFFFF, 4: 0, 5: 0x159, 6: 0x80960000, 31: 0x80173628}
        dest = bytearray(b"\xAA" * 512)
        sector = bytes((0x80 + i) & 0xFF for i in range(512))
        memory: dict[int, bytearray] = {0x80960000: dest}

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._read_backing_sector = lambda sector_id: sector if sector_id == 0x159 else None  # type: ignore[method-assign]

        row = backend._handle_dir_sector_read_paused_locked(0x80175D9C)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "dir-sector-read")
        self.assertEqual(dest, bytearray(sector))
        self.assertEqual(registers[2], 0)
        self.assertEqual(registers[37], 0x80173628)

    def test_qemu_legacy_python_storage_hook_cache16_breaks_are_disabled(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        backend._write_register_paused_locked = lambda reg, value: self.fail("unexpected GDB register write")  # type: ignore[method-assign]
        backend._write_u32_paused_locked = lambda va, value: self.fail("unexpected GDB memory write")  # type: ignore[method-assign]

        row = backend._handle_legacy_python_storage_hook_break_paused_locked(0x8017CA10)

        self.assertFalse(row.get("handled"), row)
        self.assertTrue(row.get("disabled"), row)
        self.assertEqual(row.get("pc"), "0x8017ca10")
    def test_qemu_fs_dir_scan_branch_path_matches_expected_translation(self) -> None:
        cases = [
            (0x80173630, {21: 4, 22: 4}, {4: 0x12345678, 37: 0x80173F2C}),
            (0x80173640, {3: 1}, {4: 0xE5, 37: 0x80173F14}),
            (0x80173710, {2: 0xAA, 3: 0xAA}, {2: 0xCAFEBABE, 37: 0x8017375C}),
            (0x80173768, {3: 1, 17: 0x80960020}, {17: 0x80960040, 37: 0x80173630}),
            (0x80173F14, {3: 0xE5, 4: 0xE5}, {2: 0x2E, 37: 0x8017375C}),
            (0x80173F1C, {2: 0x11, 3: 0x22, 18: 0x80960000}, {2: 0x80960020, 37: 0x80173704}),
            (0x80173F24, {2: 0x12345678}, {18: 0x5678, 37: 0x80173764}),
            (0x80173F2C, {4: 0}, {2: 0x87654321, 37: 0x80173638}),
        ]
        for pc, initial, expected in cases:
            with self.subTest(pc=f"0x{pc:08x}"):
                backend = QemuProcessBackend(QemuSystemConfig())
                registers = {
                    2: 0,
                    3: 0,
                    4: 0,
                    17: 0x80960000,
                    18: 0,
                    21: 0,
                    22: 1,
                    29: 0x8078D000,
                    37: pc,
                }
                registers.update(initial)
                stack_words = {
                    0x8078D000 + 0x88: 0xCAFEBABE,
                    0x8078D000 + 0x90: 0x87654321,
                    0x8078D000 + 0x9C: 0x12345678,
                }

                backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
                backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
                backend._read_u32_paused_locked = lambda va: stack_words.get(va)  # type: ignore[method-assign]

                row = backend._handle_fs_dir_scan_branch_paused_locked(pc)

                self.assertTrue(row.get("handled"), row)
                self.assertEqual(row.get("kind"), "fs-dir-scan-branch")
                for reg, value in expected.items():
                    self.assertEqual(registers[reg], value)

    def test_qemu_dirent_path_match_returns_consumed_path_pointer(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {
            4: 0,
            5: 1,
            6: 0x8078A000,
            7: 0x80960020,
            29: 0x8078D000,
            31: 0x80173754,
            37: 0x801747C4,
        }
        memory: dict[int, bytearray] = {
            0x8078D010: bytearray(struct.pack("<I", 0x80961000)),
            0x80961000: bytearray(b"\\*.*\0" + bytes(0x80)),
            0x80960020: bytearray(bytes.fromhex("d3a6d3c3202020202020201000000000215c215c00000000215cf43000000000")),
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    off = va - base
                    return bytes(data[off : off + size])
            raise KeyError(hex(va))

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._read_u8_paused_locked = lambda va: read_mem(va, 1)[0]  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_dirent_path_match_paused_locked(0x801747C4)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "dirent-path-match")
        self.assertEqual(row.get("matched"), True)
        self.assertEqual(registers[2], 0x80961004)
        self.assertEqual(registers[37], 0x80173754)

    def test_qemu_resource_dir_scan_fast_forward_targets_later_loaded_dirent(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        base = 0x809650A0
        registers = {
            7: base + 0x1E0,
            17: base + 0x1E0,
            18: 0x1E0,
            19: 0x8096462C,
        }
        cluster = bytearray(0x2000)
        cedic = bytearray(0x20)
        cedic[:11] = b"CEDIC   DAT"
        cedic[0x0B] = 0x20
        systp = bytearray(0x20)
        systp[:11] = b"SYSTP   CFG"
        systp[0x0B] = 0x20
        cluster[0x1E0 : 0x200] = cedic
        for offset in range(0x200, 0x780, 0x20):
            cluster[offset] = 0xE5
        cluster[0x780 : 0x7A0] = systp
        memory: dict[int, bytearray] = {
            base: cluster,
            0x8096462C: bytearray(b"\\SysTp.cfg\0" + bytes(0x80)),
        }

        def read_mem(va: int, size: int) -> bytes:
            for item_base, data in memory.items():
                if item_base <= va and va + size <= item_base + len(data):
                    offset = va - item_base
                    return bytes(data[offset : offset + size])
            raise KeyError(hex(va))

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._read_u8_paused_locked = lambda va: read_mem(va, 1)[0]  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._fat16_long_name_aliases_by_raw = lambda: {}  # type: ignore[method-assign]

        row = backend._prepare_resource_dir_scan_fast_forward_paused_locked(0x80173A90)

        self.assertTrue(row.get("applied"), row)
        self.assertEqual(row.get("found_offset"), "0x780")
        self.assertEqual(registers[7], base + 0x780)
        self.assertEqual(registers[17], base + 0x780)
        self.assertEqual(registers[18], 0x780)

    def test_qemu_resource_dir_branch_uses_current_dirent_cluster(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        sp = 0x8078D7F8
        dirent_va = 0x80967A60
        registers = {
            2: 0x10,
            4: dirent_va,
            20: 2,
            29: sp,
            37: 0x80173928,
        }
        desktop = bytearray(0x20)
        desktop[:11] = b"DESKTOP    "
        desktop[0x0B] = 0x10
        struct.pack_into("<H", desktop, 0x1A, 3)
        stack = bytearray(0x100)
        struct.pack_into("<I", stack, 0x7C, 2)
        memory: dict[int, bytearray] = {
            dirent_va: desktop,
            sp: stack,
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    offset = va - base
                    return bytes(data[offset : offset + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    offset = va - base
                    block[offset : offset + len(data)] = data
                    return
            raise KeyError(hex(va))

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_resource_trace_branch_paused_locked(0x80173928)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("stacked_s4"), "0x00000002")
        self.assertEqual(row.get("loaded_s4"), "0x00000003")
        self.assertEqual(row.get("synced_dir_cluster"), True)
        self.assertEqual(registers[20], 3)
        self.assertEqual(struct.unpack_from("<I", memory[sp], 0x7C)[0], 3)

    def test_qemu_resource_open_return_can_succeed_from_system_backing_file(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        path = b"A:\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1a.dlx\x00"
        path_va = 0x80966D50
        registers = {2: 0xFFFFFFFF, 17: path_va}
        memory = {path_va: bytearray(path + bytes(0x200))}
        entry = {"path": b"\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1a.dlx", "cluster": 4, "size": 8}

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    offset = va - base
                    return bytes(data[offset : offset + size])
            raise KeyError(hex(va))

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._read_u8_paused_locked = lambda va: read_mem(va, 1)[0]  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._find_path_from_backing = lambda raw: entry if bytes(raw).rstrip(b"\0").lower().endswith(b"c200dts1a.dlx") else None  # type: ignore[method-assign]
        backend._system_boot_file_paths_from_backing = lambda: [entry["path"]]  # type: ignore[method-assign]
        backend._read_backing_file_bytes = lambda item: b"DLX\x00data" if item is entry else None  # type: ignore[method-assign]

        row = backend._prepare_resource_open_success_from_backing_paused_locked(0x80172700)

        self.assertTrue(row.get("applied"), row)
        self.assertEqual(registers[2], 0)
        self.assertEqual(row.get("cluster"), "0x00000004")
        self.assertEqual(row.get("read_size"), 8)

    def test_qemu_resource_object_count_uses_previous_system_dlx_path(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        path_va = 0x8078DC00
        current_path_va = path_va + 0x32
        registers = {2: 0xFFFFFFFF, 16: current_path_va}
        dlx_block = bytearray(0x78)
        dlx_block[:6] = b"DLX\x07\x01\x03"
        struct.pack_into("<I", dlx_block, 12, 0x78)
        dlx = bytes(dlx_block)
        memory = {
            path_va: bytearray(
                b"a:\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1a.dlx\x00"
                + bytes(current_path_va - path_va - len(b"a:\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1a.dlx\x00"))
                + b"a:\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1b.dlx\x00"
                + bytes(0x200)
            ),
            0x8047835C: bytearray(4),
        }
        entry = {"path": b"\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1a.dlx", "cluster": 4, "size": len(dlx)}

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    offset = va - base
                    return bytes(data[offset : offset + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    offset = va - base
                    block[offset : offset + len(data)] = data
                    return
            raise KeyError(hex(va))

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._find_path_from_backing = lambda raw: entry if bytes(raw).rstrip(b"\0").lower().endswith(b"c200dts1a.dlx") else None  # type: ignore[method-assign]
        backend._read_backing_file_bytes = lambda item: dlx if item is entry else None  # type: ignore[method-assign]

        row = backend._prepare_resource_object_count_from_backing_paused_locked(0x8001E8D0)

        self.assertTrue(row.get("applied"), row)
        self.assertEqual(registers[2], 7)
        self.assertEqual(struct.unpack("<I", memory[0x8047835C])[0], 7)
        self.assertEqual(row.get("count"), 7)

    def test_qemu_synthetic_desktop_resource_manager_builds_countable_list(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        backend.qemu_heap_next = 0x80960000
        path_va = 0x8078DC00
        current_path_va = path_va + 0x32
        registers = {16: current_path_va}
        dlx_block = bytearray(0x78)
        dlx_block[:6] = b"DLX\x03\x01\x03"
        struct.pack_into("<I", dlx_block, 12, 0x78)
        dlx = bytes(dlx_block)
        memory: dict[int, bytearray] = {
            path_va: bytearray(
                b"a:\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1a.dlx\x00"
                + bytes(current_path_va - path_va - len(b"a:\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1a.dlx\x00"))
                + b"a:\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1b.dlx\x00"
                + bytes(0x200)
            ),
            0x80478358: bytearray(8),
            0x80960000: bytearray(0x1000),
        }
        entry = {"path": b"\\\xcf\xb5\xcd\xb3\\Desktop\\c200dts1a.dlx", "cluster": 4, "size": len(dlx)}

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    offset = va - base
                    return bytes(data[offset : offset + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    offset = va - base
                    block[offset : offset + len(data)] = data
                    return
            if 0x80960000 <= va and va + len(data) <= 0x80961000:
                offset = va - 0x80960000
                memory[0x80960000][offset : offset + len(data)] = data
                return
            raise KeyError(hex(va))

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x80A00000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._find_path_from_backing = lambda raw: entry if bytes(raw).rstrip(b"\0").lower().endswith(b"c200dts1a.dlx") else None  # type: ignore[method-assign]
        backend._read_backing_file_bytes = lambda item: dlx if item is entry else None  # type: ignore[method-assign]

        row = backend._prepare_synthetic_desktop_resource_manager_paused_locked(0x8001E8C0)

        self.assertTrue(row.get("applied"), row)
        manager = struct.unpack_from("<I", memory[0x80478358], 0)[0]
        self.assertEqual(manager, 0x80960000)
        self.assertEqual(struct.unpack_from("<I", memory[0x80478358], 4)[0], 3)
        self.assertEqual(registers.get(5), manager)
        state = struct.unpack("<I", read_mem(manager + 0x84, 4))[0]
        head = struct.unpack("<I", read_mem(state + 0x38, 4))[0]
        self.assertEqual(struct.unpack("<I", read_mem(state + 4, 4))[0], 3)
        self.assertEqual(struct.unpack("<I", read_mem(head + 0x0C, 4))[0], 1)
        self.assertEqual(struct.unpack("<I", read_mem(head + 0x10, 4))[0], 1)
        self.assertNotEqual(struct.unpack("<I", read_mem(head + 0x18, 4))[0], 0)

    def test_qemu_file_read_context_sync_uses_file_cluster(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        obj = 0x80964C70
        ctx = 0x806C5098
        registers = {16: obj, 22: ctx}
        memory: dict[int, bytearray] = {
            obj: bytearray(0x58),
            ctx: bytearray(struct.pack("<II", 0x236, 0x60) + bytes(0x38)),
        }
        struct.pack_into("<I", memory[obj], 0x18, 0x2312)
        struct.pack_into("<I", memory[obj], 0x20, 0x47)
        memory[obj][0x0F] = 0x20

        def read_mem(va: int, size: int) -> bytes:
            for base, data in memory.items():
                if base <= va and va + size <= base + len(data):
                    offset = va - base
                    return bytes(data[offset : offset + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    offset = va - base
                    block[offset : offset + len(data)] = data
                    return
            raise KeyError(hex(va))

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]

        row = backend._prepare_file_read_context_paused_locked(0x801716FC)

        self.assertTrue(row.get("applied"), row)
        self.assertEqual(struct.unpack_from("<I", memory[ctx], 0)[0], 0x2312)
        self.assertEqual(struct.unpack_from("<I", memory[ctx], 4)[0], 0)

    def test_qemu_first_root_directory_scan_pattern_uses_backing_dirent(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        firmware = bytearray(0x20)
        firmware[:11] = bytes.fromhex("d3a6d3c320202020202020")
        firmware[0x0B] = 0x10
        backend._first_root_dirent_from_backing = lambda: {"firmware": bytes(firmware)}  # type: ignore[method-assign]

        self.assertEqual(
            backend._first_root_directory_scan_pattern_from_backing(),
            b"\\" + bytes.fromhex("d3a6d3c3") + b"\\*.*\x00",
        )

    def test_qemu_first_child_directory_scan_pattern_uses_backing_tree(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        root = bytearray(0x20)
        root[:11] = b"ROOTDIR    "
        root[0x0B] = 0x10
        struct.pack_into("<I", root, 0x14, 0x30F4)
        dot = bytearray(0x20)
        dot[:11] = b".          "
        dot[0x0B] = 0x10
        dotdot = bytearray(0x20)
        dotdot[:11] = b"..         "
        dotdot[0x0B] = 0x10
        lfn = bytearray(0x20)
        lfn[0] = 0x41
        lfn[0x0B] = 0x0F
        child = bytearray(0x20)
        child[:11] = b"CHILD      "
        child[0x0B] = 0x10
        struct.pack_into("<I", child, 0x14, 0x30F5)
        cluster = bytes(dot + dotdot + lfn + child + bytes(512 - 0x80))

        backend._first_root_dirent_from_backing = lambda: {  # type: ignore[method-assign]
            "firmware": bytes(root),
            "cluster": 0x30F4,
        }
        backend._fat16_cluster_data_from_backing = lambda cluster_id: cluster if cluster_id == 0x30F4 else None  # type: ignore[method-assign]

        self.assertEqual(
            backend._first_child_directory_scan_pattern_from_backing(),
            b"\\ROOTDIR\\CHILD\\*.*\x00",
        )

    def test_qemu_first_child_directory_scan_pattern_requires_child_directory(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        root = bytearray(0x20)
        root[:11] = b"ROOTDIR    "
        root[0x0B] = 0x10
        struct.pack_into("<I", root, 0x14, 0x30F4)
        file_entry = bytearray(0x20)
        file_entry[:11] = b"README  TXT"
        file_entry[0x0B] = 0x20
        cluster = bytes(file_entry + bytes(512 - 0x20))

        backend._first_root_dirent_from_backing = lambda: {  # type: ignore[method-assign]
            "firmware": bytes(root),
            "cluster": 0x30F4,
        }
        backend._fat16_cluster_data_from_backing = lambda cluster_id: cluster if cluster_id == 0x30F4 else None  # type: ignore[method-assign]

        self.assertIsNone(backend._first_child_directory_scan_pattern_from_backing())

    def test_qemu_first_file_path_from_backing_descends_directories(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        root_dir = bytearray(0x20)
        root_dir[:11] = b"ROOTDIR    "
        root_dir[0x0B] = 0x10
        struct.pack_into("<H", root_dir, 0x1A, 0x30F4)
        root_file = bytearray(0x20)
        root_file[:11] = b"LATER   BIN"
        root_file[0x0B] = 0x20
        struct.pack_into("<H", root_file, 0x1A, 0x4000)
        child_file = bytearray(0x20)
        child_file[:11] = b"FIRST   BIN"
        child_file[0x0B] = 0x20
        struct.pack_into("<H", child_file, 0x1A, 0x30F5)
        struct.pack_into("<I", child_file, 0x1C, 0x1234)
        root_data = bytes(root_dir + root_file + bytes(512 - 0x40))
        child_data = bytes(child_file + bytes(512 - 0x20))

        backend._root_directory_data_from_backing = lambda: root_data  # type: ignore[method-assign]
        backend._fat16_cluster_data_from_backing = lambda cluster_id: child_data if cluster_id == 0x30F4 else None  # type: ignore[method-assign]

        row = backend._first_file_path_from_backing()

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.get("path"), b"\\ROOTDIR\\FIRST.BIN\x00")
        self.assertEqual(row.get("cluster"), 0x30F5)
        self.assertEqual(row.get("size"), 0x1234)

    def test_qemu_find_system_paths_from_backing_uses_lfn_aliases(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())

        def entry(short: bytes, attr: int, cluster: int, size: int = 0) -> bytes:
            item = bytearray(0x20)
            item[:11] = short
            item[0x0B] = attr
            struct.pack_into("<H", item, 0x1A, cluster)
            struct.pack_into("<I", item, 0x1C, size)
            return bytes(item)

        root = entry(b"SYSTEM     ", 0x10, 2) + bytes(512 - 0x20)
        system_dir = (
            entry(b"DATA       ", 0x10, 3)
            + entry(b"DESKTOP    ", 0x10, 4)
            + bytes(512 - 0x40)
        )
        data_dir = entry(b"SYSTP   CFG", 0x20, 5, 71) + bytes(512 - 0x20)
        desktop_dir = entry(b"C200DT~1DLX", 0x20, 6, 513548) + bytes(512 - 0x20)

        backend._root_directory_data_from_backing = lambda: root  # type: ignore[method-assign]
        backend._fat16_cluster_data_from_backing = lambda cluster_id: {  # type: ignore[method-assign]
            2: system_dir,
            3: data_dir,
            4: desktop_dir,
        }.get(cluster_id)
        backend._fat16_long_name_aliases_by_raw = lambda: {  # type: ignore[method-assign]
            b"SYSTEM     ": ["系统".encode("gbk")],
            b"DATA       ": ["数据".encode("gbk")],
            b"C200DT~1DLX": [b"c200dts1a.dlx"],
        }

        systp = backend._find_path_from_backing("\\系统\\数据\\SysTp.cfg")
        drive_systp = backend._find_path_from_backing("A:\\系统\\数据\\SysTp.cfg")
        desktop = backend._find_path_from_backing("\\系统\\Desktop\\c200dts1a.dlx")

        self.assertIsNotNone(systp)
        assert systp is not None
        self.assertEqual(systp.get("cluster"), 5)
        self.assertEqual(systp.get("size"), 71)
        self.assertEqual(systp.get("name_hex"), b"SYSTP   CFG".hex())
        self.assertIsNotNone(drive_systp)
        assert drive_systp is not None
        self.assertEqual(drive_systp.get("cluster"), 5)
        self.assertIsNotNone(desktop)
        assert desktop is not None
        self.assertEqual(desktop.get("cluster"), 6)
        self.assertEqual(desktop.get("size"), 513548)
        self.assertEqual(desktop.get("name_hex"), b"C200DT~1DLX".hex())

    def test_qemu_system_boot_file_probe_reads_backing_without_firmware_call(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        entry = {
            "path": "\\系统\\数据\\SysTp.cfg".encode("gbk") + b"\x00",
            "cluster": 5,
            "size": 8,
        }

        backend._system_boot_file_entries_from_backing = lambda: [entry]  # type: ignore[method-assign]
        backend._fat16_cluster_data_from_backing = lambda cluster_id: b"SysTpOK!" if cluster_id == 5 else None  # type: ignore[method-assign]

        row = backend._service_system_boot_file_probes_paused_locked()

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("read_count"), 1)
        files = row.get("files")
        self.assertIsInstance(files, list)
        assert isinstance(files, list)
        self.assertEqual(files[0].get("event"), "qemu-system-file-backing-read-probe")
        self.assertEqual(files[0].get("read_size"), 8)
        self.assertNotIn("call", files[0])

    def test_qemu_first_path_segment_bounds_skips_drive_prefix(self) -> None:
        path = "A:\\系统\\数据\\SysTp.cfg".encode("gbk")

        start, end = QemuProcessBackend._first_path_segment_bounds(path)

        self.assertEqual(path[start:end], "系统".encode("gbk"))

    def test_frontend_qemu_frontend_input_calibration_releases_last_touch_before_complete(self) -> None:
        state = FrontendState.__new__(FrontendState)
        state.args = argparse.Namespace(frontend_input_calibration=True, boot_mode="c200")
        state.frontend_input_calibration_stage = 0
        state.frontend_input_calibration_last_stage_step = -1
        state.qemu_frontend_input_calibration_last_action_at = 0.0
        state.qemu_frontend_input_calibration_log = []
        backend = _FakeFrontendQemuBackend()

        for _index in range(len(FRONTEND_INPUT_CALIBRATION_TARGETS) * 2 + 1):
            state.qemu_frontend_input_calibration_last_action_at = time.time() - 1.0
            state._apply_frontend_input_calibration_locked(backend)  # type: ignore[arg-type]

        self.assertFalse(backend.completed)
        self.assertEqual(state.frontend_input_calibration_stage, 12)
        self.assertEqual(len(backend.touches), len(FRONTEND_INPUT_CALIBRATION_TARGETS) * 2)
        self.assertEqual(backend.touches[-1], (*FRONTEND_INPUT_CALIBRATION_TARGETS[-1], False))
        self.assertEqual([down for _x, _y, down in backend.touches], [True, False, True, False, True, False, True, False])

    def test_frontend_input_calibration_does_not_complete_on_gui_probe_error(self) -> None:
        class GuiErrorBackend(_FakeFrontendQemuBackend):
            def guest_gui_state_snapshot(self) -> dict[str, object]:
                raise TimeoutError("guest probe timed out")

        state = FrontendState.__new__(FrontendState)
        state.args = argparse.Namespace(frontend_input_calibration=True, boot_mode="c200")
        state.frontend_input_calibration_stage = 0
        state.frontend_input_calibration_last_stage_step = -1
        state.qemu_frontend_input_calibration_last_action_at = 0.0
        state.qemu_frontend_input_calibration_log = []
        backend = GuiErrorBackend()

        for _index in range(len(FRONTEND_INPUT_CALIBRATION_TARGETS) * 2 + 1):
            state.qemu_frontend_input_calibration_last_action_at = time.time() - 1.0
            state._apply_frontend_input_calibration_locked(backend)  # type: ignore[arg-type]

        self.assertEqual(state.frontend_input_calibration_stage, len(FRONTEND_INPUT_CALIBRATION_TARGETS) * 2)
        self.assertEqual(len(backend.touches), len(FRONTEND_INPUT_CALIBRATION_TARGETS) * 2)
        self.assertEqual(state.qemu_frontend_input_calibration_log[-1]["event"], "qemu-frontend-input-calibration-status-deferred")
        self.assertIn("TimeoutError", str(state.qemu_frontend_input_calibration_log[-1].get("error")))

    def test_frontend_input_calibration_can_start_without_cached_pc(self) -> None:
        class UnknownPcBackend(_FakeFrontendQemuBackend):
            def snapshot(self) -> dict[str, object]:
                return {"running": True}

        state = FrontendState.__new__(FrontendState)
        state.args = argparse.Namespace(frontend_input_calibration=True, boot_mode="nand")
        state.frontend_input_calibration_stage = 0
        state.frontend_input_calibration_last_stage_step = -1
        state.qemu_frontend_input_calibration_last_action_at = 0.0
        state.qemu_frontend_input_calibration_log = []
        backend = UnknownPcBackend()

        for _index in range(2):
            state.qemu_frontend_input_calibration_last_action_at = time.time() - 1.0
            state._apply_frontend_input_calibration_locked(backend)  # type: ignore[arg-type]

        self.assertEqual(state.frontend_input_calibration_stage, 2)
        self.assertEqual(backend.touches[:2], [
            (*FRONTEND_INPUT_CALIBRATION_TARGETS[0], True),
            (*FRONTEND_INPUT_CALIBRATION_TARGETS[0], False),
        ])

    def test_frontend_full_status_keeps_heavy_traces_explicit(self) -> None:
        state = FrontendState(
            argparse.Namespace(
                frontend_input_calibration=False,
                boot_mode="nand",
                nand_image=None,
                orientation="rot180",
                frame_push_min_interval=0.04,
                frame_info_min_interval=1.0,
            )
        )
        backend = _FakeFrontendQemuBackend()
        state.qemu_backend = backend  # type: ignore[assignment]

        full = state.snapshot(detail="full")

        self.assertEqual(full.get("detail"), "full")
        self.assertIn("guest_gui_state", full)
        self.assertIn("guest_display_surface", full)
        self.assertNotIn("guest_storage_trace", full)
        self.assertNotIn("guest_fs_probe_trace", full)
        legacy_hooks = full.get("legacy_python_hooks")
        self.assertIsInstance(legacy_hooks, dict)
        assert isinstance(legacy_hooks, dict)
        self.assertFalse(legacy_hooks.get("enabled"), legacy_hooks)
        self.assertNotIn("resource_cache_enabled", legacy_hooks)
        self.assertNotIn("fast_" + "hooks", full)
        self.assertNotIn("resource_" + "cache16", full)
        self.assertNotIn("qemu_" + "storage_" + "bootstrap_log", full)
        self.assertEqual(backend.trace_calls, [])

        traces = state.snapshot(detail="traces")

        self.assertEqual(traces.get("detail"), "traces")
        self.assertIn("guest_display_surface", traces)
        self.assertIn("guest_storage_trace", traces)
        self.assertIn("guest_fs_probe_trace", traces)
        self.assertEqual(
            backend.trace_calls,
            ["surface", "storage", "msc", "fs_probe", "progress"],
        )

    def test_frontend_websocket_recovers_from_stale_half_open_connection(self) -> None:
        root = Path(__file__).resolve().parents[2]
        frontend = (root / "emu/web/frontend.py").read_text(encoding="utf-8")
        server = (root / "emu/web/frontend_server.py").read_text(encoding="utf-8")

        self.assertIn("const wsIdleReconnectMs = 5000;", frontend)
        self.assertIn("startWsWatchdog();", frontend)
        self.assertIn("wsLastMessageAt = performance.now();", frontend)
        self.assertIn("function commandFetchFallback(msg)", frontend)
        self.assertIn("function wsIsStale()", frontend)
        self.assertIn("function dropWs(reason = 'stale websocket')", frontend)
        self.assertIn("if (wsIsStale()) {", frontend)
        self.assertIn("return commandFetchFallback(msg);", frontend)
        self.assertIn("return wsOpenPromise.then(sock => {", frontend)
        self.assertIn("ws.close(4000, 'stale websocket');", frontend)
        self.assertIn("self.connection.shutdown(socket.SHUT_RDWR)", server)
        self.assertIn("self.connection.close()", server)

    def test_frontend_screen_png_reuses_same_chardev_frame(self) -> None:
        class FrameBackend:
            latest_frame_chardev = (42, time.time() - 1.0, b"\x00\x00" * (240 * 320))

        state = FrontendState(
            argparse.Namespace(
                frontend_input_calibration=False,
                boot_mode="nand",
                nand_image=None,
                orientation="rot180",
                frame_push_min_interval=0.08,
                frame_info_min_interval=1.0,
            )
        )
        state.qemu_backend = FrameBackend()  # type: ignore[assignment]
        state._ensure_qemu_started_locked = lambda: state.qemu_backend  # type: ignore[method-assign]

        with mock.patch("emu.web.frontend_state.png_bytes_from_rgb", return_value=b"png-frame") as encode_png:
            first = state.dump_frame()
            second = state.dump_frame()

        self.assertEqual(first, b"png-frame")
        self.assertEqual(second, b"png-frame")
        self.assertEqual(encode_png.call_count, 1)
        self.assertEqual(state.cached_frame_seq, 42)

    def test_frontend_ws_frame_cursor_is_per_connection(self) -> None:
        class FrameBackend:
            latest_frame_chardev = (17, time.time(), b"\x00\x00" * (240 * 320))

        state = FrontendState.__new__(FrontendState)
        state.lock = threading.RLock()
        state.frontend_activity_condition = threading.Condition()
        state.frontend_activity_seq = 0
        state.qemu_backend = FrameBackend()
        state.qemu_last_ws_frame_seq = None
        state.cached_ws_frame_bytes = None
        state.cached_ws_frame_time = 0.0
        state.frame_push_min_interval = 0.0
        state.frame_push_last_time = 0.0
        state.frame_push_throttle_count = 0
        state.frame_push_error_count = 0
        state.frame_push_replace_count = 0
        state.frame_push_last_source_lag_ms = None
        state.frame_push_max_source_lag_ms = 0.0
        state.frame_push_queued_count = 0
        state.last_error = None

        client_a = state.latest_ws_frame_after(None)
        client_b = state.latest_ws_frame_after(None)

        self.assertIsNotNone(client_a)
        self.assertIsNotNone(client_b)
        self.assertEqual(client_a, client_b)
        self.assertEqual(state.frame_push_queued_count, 1)

        state.qemu_backend.latest_frame_chardev = (19, time.time(), b"\x01\x00" * (240 * 320))
        next_a = state.latest_ws_frame_after(17)
        next_b = state.latest_ws_frame_after(17)

        self.assertEqual(next_a, next_b)
        self.assertEqual(next_a[0] if next_a else None, 19)
        self.assertEqual(state.frame_push_queued_count, 2)
        self.assertEqual(state.frame_push_replace_count, 1)

    def test_frontend_performance_metrics_compute_web_and_png_rates(self) -> None:
        state = FrontendState(
            argparse.Namespace(
                frontend_input_calibration=False,
                boot_mode="nand",
                nand_image=None,
                orientation="rot180",
                frame_push_min_interval=0.08,
                frame_info_min_interval=1.0,
            )
        )
        state.ws_frame_sent_count = 5
        state.frame_push_queued_count = 5
        state.screen_png_count = 2
        state._frontend_performance_snapshot_locked(100.0, 10.0)
        state.ws_frame_sent_count = 8
        state.frame_push_queued_count = 8
        state.screen_png_count = 4

        row = state._frontend_performance_snapshot_locked(101.0, 11.0)

        self.assertEqual(row.get("websocket_fps"), 3.0)
        self.assertEqual(row.get("screen_png_fps"), 2.0)
        self.assertEqual(row.get("websocket_average_fps"), 0.73)
        self.assertEqual(row.get("websocket_transport_fps"), 3.0)
        self.assertEqual(row.get("screen_png_count"), 4)

    def test_frontend_status_displays_performance_metrics(self) -> None:
        root = Path(__file__).resolve().parents[2]
        frontend = (root / "emu/web/frontend.py").read_text(encoding="utf-8")

        self.assertIn("function firstNumber(...values)", frontend)
        self.assertIn("function formatRate(value, unit, fallback = 'n/a')", frontend)
        self.assertIn("function formatPercent(value, fallback = 'n/a')", frontend)
        self.assertIn("const minKeyHoldMs = 100;", frontend)
        self.assertIn("function beginKeyButton(btn)", frontend)
        self.assertIn("function endKeyButton(btn, phase)", frontend)
        self.assertIn(
            "['qemu fps', formatRate(firstNumber(qemuPerf.frame_chardev_fps, qemuPerf.frame_chardev_average_fps), 'fps')]",
            frontend,
        )
        self.assertIn("['web fps', formatRate(frontendPerf.websocket_fps, 'fps')]", frontend)
        self.assertIn("['web tx', formatRate(frontendPerf.websocket_transport_fps, 'fps')]", frontend)
        self.assertIn("['ws clients', s.frame_push?.ws_connections ?? 0]", frontend)
        self.assertIn("['png fps', formatRate(frontendPerf.screen_png_fps, 'fps')]", frontend)
        self.assertIn(
            "['qemu cpu', formatPercent(firstNumber(qemuPerf.qemu_cpu_one_core_percent, qemuPerf.qemu_cpu_host_percent))]",
            frontend,
        )
        self.assertIn("['guest ips', formatGuestIps(qemuPerf)]", frontend)

    def test_frontend_qemu_storage_service_error_uses_legacy_hook_terms(self) -> None:
        state = FrontendState(
            argparse.Namespace(
                nand_image=None,
                image=None,
                payload=None,
                boot_mode="nand",
                orientation="rot180",
                qemu=DEFAULT_QEMU_EXECUTABLE,
                qemu_machine=DEFAULT_QEMU_MACHINE,
                qemu_cpu="24Kf",
                qemu_accel="tcg",
                qemu_gdb="none",
                qemu_timeout=5.0,
                qemu_machine_option=[],
                qemu_extra_arg=[],
                qemu_firmware_patch=None,
                ram_mb=160,
                frontend_input_calibration=False,
                frame_push_min_interval=0.08,
                frame_info_min_interval=1.0,
            )
        )

        result = state.command({"op": "qemu-storage-service"})

        self.assertIn("legacy Python/GDB storage hooks", str(result.get("error")))
        self.assertNotIn("fastpath", str(result.get("error")).lower())

    def test_frontend_intrusive_diagnostics_are_disabled_by_default(self) -> None:
        fail = self.fail

        class _Backend:
            def watch_guest_write_once(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                fail("unexpected watch_guest_write_once call")

            def trace_guest_breakpoints_once(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                fail("unexpected trace_guest_breakpoints_once call")

        state = FrontendState.__new__(FrontendState)
        state.args = argparse.Namespace()
        state.qemu_backend = _Backend()

        watch = state.command({"op": "qemu-watch-write", "addr": "0x80000000", "size": 4})
        trace = state.command({"op": "qemu-trace-breakpoints", "pcs": ["0x80000000"]})

        self.assertIn("disabled by default", str(watch.get("error")))
        self.assertIn("--allow-gdb-diagnostics", str(watch.get("error")))
        self.assertIn("disabled by default", str(trace.get("error")))
        self.assertIn("--allow-gdb-diagnostics", str(trace.get("error")))

    def test_frontend_intrusive_diagnostics_require_explicit_flag(self) -> None:
        class _Backend:
            def watch_guest_write_once(self, *args: object, **_kwargs: object) -> dict[str, object]:
                return {"called": "watch", "addr": args[0], "size": args[1]}

            def trace_guest_breakpoints_once(self, pcs: object, **kwargs: object) -> dict[str, object]:
                return {"called": "trace", "pcs": pcs, "max_hits": kwargs.get("max_hits")}

        state = FrontendState.__new__(FrontendState)
        state.args = argparse.Namespace(allow_gdb_diagnostics=True)
        state.qemu_backend = _Backend()

        watch = state.command({"op": "qemu-watch-write", "addr": "0x80000000", "size": 4, "timeout": 0.1})
        trace = state.command({"op": "qemu-trace-breakpoints", "pcs": ["0x80000004"], "max_hits": 2})

        self.assertEqual(watch.get("called"), "watch")
        self.assertEqual(watch.get("addr"), 0x80000000)
        self.assertEqual(watch.get("size"), 4)
        self.assertEqual(trace.get("called"), "trace")
        self.assertEqual(trace.get("pcs"), (0x80000004,))
        self.assertEqual(trace.get("max_hits"), 2)

    def test_frontend_nand_image_catalog_marks_selected_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nand = Path(tmp) / "custom_nand.bin"
            nand.write_bytes(b"\xff" * 4096)
            state = FrontendState.__new__(FrontendState)
            state.args = argparse.Namespace(nand_image=nand)

            catalog = state.nand_image_catalog()

        self.assertEqual(catalog["current_path"], str(nand.resolve()))
        images = catalog.get("images")
        self.assertIsInstance(images, list)
        assert isinstance(images, list)
        selected = [item for item in images if item.get("current")]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].get("path"), str(nand.resolve()))
        self.assertEqual(selected[0].get("size"), 4096)

    def test_frontend_qemu_backend_status_and_stop(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        port = _find_free_port()
        proc = subprocess.Popen(
            [
                sys.executable,
                "emu/app.py",
                "--backend",
                "qemu",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--boot-mode",
                "c200",
                "--quiet",
            ],
            cwd=Path(__file__).resolve().parents[2],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            deadline = time.time() + 20
            status: dict[str, object] | None = None
            while time.time() < deadline:
                if proc.poll() is not None:
                    stdout, stderr = proc.communicate(timeout=1)
                    self.fail(f"frontend exited early rc={proc.returncode}\nstdout={stdout}\nstderr={stderr}")
                try:
                    status = _http_json(port, "GET", "/api/status?detail=full")
                    qemu = status.get("qemu") if isinstance(status.get("qemu"), dict) else {}
                    if isinstance(status.get("pc"), str) and isinstance(qemu.get("pc"), str):
                        break
                except Exception:
                    pass
                time.sleep(0.1)
            self.assertIsNotNone(status)
            assert status is not None
            self.assertEqual(status.get("backend"), "qemu")
            self.assertIsInstance(status.get("pc"), str)
            self.assertIsInstance(status.get("qemu_pc_classification"), dict)
            self.assertTrue(status.get("qemu_pc_region"))
            self.assertIn("qemu", status)
            qemu = status["qemu"]
            self.assertIsInstance(qemu, dict)
            self.assertTrue(qemu.get("running"), qemu)
            self.assertIsInstance(qemu.get("pc"), str)
            self.assertIsInstance(qemu.get("pc_classification"), dict)
            self.assertTrue(qemu.get("gdb_connected"), qemu)
            sample = qemu.get("register_sample")
            self.assertIsInstance(sample, dict)
            assert isinstance(sample, dict)
            self.assertNotEqual(sample.get("pc"), "0x80004000")
            screen_status, png = _http_bytes(port, "/screen.png")
            self.assertEqual(screen_status, 200)
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            after_screen = _http_json(port, "GET", "/api/status?detail=full")
            framebuffer = after_screen.get("framebuffer")
            self.assertIsInstance(framebuffer, dict)
            assert isinstance(framebuffer, dict)
            self.assertEqual(framebuffer.get("backend"), "qemu")
            self.assertEqual(framebuffer.get("source"), "qemu-frame-chardev")
            after_qemu = after_screen.get("qemu")
            self.assertIsInstance(after_qemu, dict)
            assert isinstance(after_qemu, dict)
            self.assertGreaterEqual(int(after_qemu.get("frame_chardev_count") or 0), 1)
            self.assertGreaterEqual(int(after_qemu.get("gdb_read_count") or 0), 1)
            event_queue = after_screen.get("event_queue")
            self.assertIsInstance(event_queue, dict)
            assert isinstance(event_queue, dict)
            self.assertEqual(event_queue.get("global_addr"), "0x80473f6c")
            self.assertIn("global_value", event_queue)
            display_queue = after_screen.get("display_event_queue")
            self.assertIsInstance(display_queue, dict)
            assert isinstance(display_queue, dict)
            self.assertEqual(display_queue.get("queue_va"), "0x80825840")
            gui_state = after_screen.get("guest_gui_state")
            self.assertIsInstance(gui_state, dict)
            assert isinstance(gui_state, dict)
            self.assertIn("active_object_80474048", gui_state)
            self.assertIn("gui_busy_count_80825800", gui_state)
            self.assertIn("gui_busy_count_80825820", gui_state)
            self.assertIn("touch_mode_flag_8048daf4", gui_state)
            self.assertIn("fs_volume_count_80474254", gui_state)
            self.assertIn("resource_cache_enabled_804bf434", gui_state)
            key_reply = _http_json(port, "POST", "/api/key?code=7&down=1")
            self.assertEqual(key_reply.get("backend"), "qemu")
            self.assertTrue(key_reply.get("input_accepted"), key_reply.get("qemu_input_result"))
            input_result = key_reply.get("qemu_input_result")
            self.assertIsInstance(input_result, dict)
            assert isinstance(input_result, dict)
            self.assertTrue(input_result.get("applied"), input_result)
            key_release = _http_json(port, "POST", "/api/key?code=7&down=0")
            self.assertEqual(key_release.get("backend"), "qemu")
            self.assertTrue(key_release.get("input_accepted"), key_release.get("qemu_input_result"))
            release_result = key_release.get("qemu_input_result")
            self.assertIsInstance(release_result, dict)
            assert isinstance(release_result, dict)
            self.assertFalse(release_result.get("down"), release_result)
            self.assertEqual(release_result.get("source"), "qemu-c-machine-chardev")
            touch_reply = _http_json(port, "POST", "/api/touch?x=120&y=160&down=1")
            self.assertEqual(touch_reply.get("backend"), "qemu")
            self.assertTrue(touch_reply.get("input_accepted"), touch_reply.get("qemu_input_result"))
            touch_result = touch_reply.get("qemu_input_result")
            self.assertIsInstance(touch_result, dict)
            assert isinstance(touch_result, dict)
            self.assertTrue(touch_result.get("applied"), touch_result)
            self.assertEqual(touch_result.get("source"), "qemu-c-machine-chardev")
            self.assertNotIn("touch_x_addr", touch_result)
            self.assertNotIn("firmware_touch_x_addr", touch_result)
            gui_handler = touch_result.get("gui_handler")
            self.assertIsInstance(gui_handler, dict)
            assert isinstance(gui_handler, dict)
            self.assertTrue(gui_handler.get("skipped"), gui_handler)
            self.assertEqual(gui_handler.get("source"), "qemu-c-machine")
            stopped = _http_json(port, "POST", "/api/stop")
            self.assertEqual(stopped.get("backend"), "qemu")
            self.assertFalse(stopped.get("running"))
        finally:
            try:
                _http_json(port, "POST", "/api/shutdown")
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
            try:
                proc.communicate(timeout=1)
            except Exception:
                pass

    def test_qemu_gdb_virtual_memory_bridge_reads_boot_payload(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        config = build_bbk_qemu_config(boot_mode="c200", gdb="auto", timeout_seconds=1.5)
        backend = QemuProcessBackend(config)
        try:
            backend.start()
            self.assertTrue(backend.running())
            assert config.boot_payload is not None
            expected = config.boot_payload.path.read_bytes()[:4]
            data = backend.read_virtual_memory(DEFAULT_C200_BASE, 4)
            self.assertEqual(data, expected)
            snap = backend.snapshot()
            self.assertGreaterEqual(int(snap.get("gdb_read_count") or 0), 1)
            self.assertIsNone(snap.get("last_gdb_error"))
        finally:
            backend.stop()

    def test_qemu_gdb_register_bridge_reads_and_writes_registers(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        config = build_bbk_qemu_config(
            boot_mode="c200",
            timeout_seconds=1.5,
            bbk_machine_options=("cpu-irq-output=off",),
        )
        backend = QemuProcessBackend(config)
        try:
            backend.start()
            self.assertTrue(backend.running())
            time.sleep(0.5)
            pc = backend.read_pc()
            self.assertTrue(0x80000000 <= pc < 0x81000000, f"pc=0x{pc:08x}")
            original_v0 = backend.read_register(2)
            try:
                checked = backend.write_registers_checked({2: 0x12345678, 37: pc})
                self.assertEqual(checked["2"], "0x12345678")
                self.assertEqual(checked["37"], f"0x{pc:08x}")
            finally:
                backend.write_register(2, original_v0)
            snap = backend.snapshot()
            self.assertGreaterEqual(int(snap.get("gdb_register_read_count") or 0), 3)
            self.assertGreaterEqual(int(snap.get("gdb_register_write_count") or 0), 2)
        finally:
            backend.stop()

    def test_qemu_gdb_stepped_guest_call_invokes_tick_getter(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        config = build_bbk_qemu_config(boot_mode="c200", timeout_seconds=1.5)
        backend = QemuProcessBackend(config)
        try:
            backend.start()
            self.assertTrue(backend.running())
            time.sleep(0.5)
            expected = int.from_bytes(backend.read_virtual_memory(0x80474058, 4), "little")
            result = backend.call_guest_function_stepped(0x800DE144, return_pc=DEFAULT_C200_BASE, max_steps=4)
            self.assertTrue(result.get("returned"), result)
            self.assertEqual(result.get("final_pc"), f"0x{DEFAULT_C200_BASE:08x}")
            returned_tick = int(str(result.get("v0")), 16)
            self.assertGreaterEqual(returned_tick, expected)
            snap = backend.snapshot()
            self.assertGreaterEqual(int(snap.get("gdb_step_count") or 0), 1)
            self.assertGreaterEqual(int(snap.get("guest_call_count") or 0), 1)
        finally:
            backend.stop()

    def test_qemu_gdb_guest_queue_snapshot_reads_global_pointer(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        config = build_bbk_qemu_config(boot_mode="c200", timeout_seconds=1.5)
        backend = QemuProcessBackend(config)
        try:
            backend.start()
            self.assertTrue(backend.running())
            snapshot = backend.guest_queue_snapshot(0x80473F6C)
            self.assertEqual(snapshot.get("global_addr"), "0x80473f6c")
            self.assertIn("global_value", snapshot)
            self.assertNotIn("error", snapshot)
            qemu = backend.snapshot()
            self.assertGreaterEqual(int(qemu.get("gdb_read_count") or 0), 1)
        finally:
            backend.stop()

    def test_qemu_gdb_gui_state_snapshot_reads_active_object_globals(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        config = build_bbk_qemu_config(boot_mode="c200", timeout_seconds=1.5)
        backend = QemuProcessBackend(config)
        try:
            backend.start()
            self.assertTrue(backend.running())
            time.sleep(1.0)
            gui = backend.guest_gui_state_snapshot()
            self.assertIn("active_object_80474048", gui)
            self.assertIn("touch_mode_flag_8048daf4", gui)
            self.assertIn("active_object_ready", gui)
            qemu = backend.snapshot()
            self.assertGreaterEqual(int(qemu.get("gdb_read_count") or 0), 1)
        finally:
            backend.stop()

    def test_qemu_gdb_gui_key_bridge_applies_key_state(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        config = build_bbk_qemu_config(boot_mode="c200", timeout_seconds=1.5)
        backend = QemuProcessBackend(config)
        try:
            backend.start()
            self.assertTrue(backend.running())
            time.sleep(1.0)
            result = backend.apply_gui_key_event(7)
            self.assertTrue(result.get("applied"), result)
            self.assertEqual(result.get("source"), "qemu-c-machine-chardev")
            self.assertTrue(result.get("down"), result)
            self.assertIsNone(result.get("mailbox"))
            self.assertGreaterEqual(int(result.get("bbk_input_write_count") or 0), 1)
            time.sleep(0.08)
            gpio_down = struct.unpack("<I", backend.read_virtual_memory(0xB0010100, 4))[0]
            self.assertEqual(gpio_down & 0x08000000, 0)
            gpio_flag = struct.unpack("<I", backend.read_virtual_memory(0xB0010180, 4))[0]
            intc_pending = struct.unpack("<I", backend.read_virtual_memory(0xB0001010, 4))[0]
            self.assertIsInstance(gpio_flag, int)
            self.assertIsInstance(intc_pending, int)
            backend.write_virtual_memory(0xB0010114, struct.pack("<I", 0x08000000))
            gpio_flag_cleared = struct.unpack("<I", backend.read_virtual_memory(0xB0010180, 4))[0]
            self.assertEqual(gpio_flag_cleared & 0x08000000, 0)
            surface = backend.guest_display_surface_snapshot()
            self.assertIn(surface.get("mirror_enabled_80474040"), {"0x00000000", "0x00000001"})
            mirror_config = surface.get("lcd_mirror_config")
            self.assertIsInstance(mirror_config, dict)
            assert isinstance(mirror_config, dict)
            if surface.get("mirror_enabled_80474040") == "0x00000001":
                self.assertEqual(mirror_config.get("width"), 240)
                self.assertEqual(mirror_config.get("height"), 320)
                self.assertEqual(mirror_config.get("fb"), "0xa1f82000")
            qemu = backend.snapshot()
            self.assertGreaterEqual(int(qemu.get("bbk_input_write_count") or 0), 1)
            self.assertTrue(qemu.get("guest_input_events"))
            release = backend.apply_gui_key_event(7, False)
            self.assertTrue(release.get("applied"), release)
            self.assertFalse(release.get("down"), release)
            self.assertEqual(release.get("source"), "qemu-c-machine-chardev")
            time.sleep(0.08)
            gpio_up = struct.unpack("<I", backend.read_virtual_memory(0xB0010100, 4))[0]
            self.assertEqual(gpio_up & 0x08000000, 0x08000000)
        finally:
            backend.stop()

    def test_bbk9588_touch_refuses_guest_ram_fallback_without_chardev(self) -> None:
        class _RunningProc:
            def poll(self) -> None:
                return None

        config = QemuSystemConfig(machine="bbk9588")
        backend = QemuProcessBackend(config)
        backend.proc = _RunningProc()  # type: ignore[assignment]
        backend.gdb_sock = object()  # type: ignore[assignment]
        backend.bbk_input_sock = None

        def fail_gdb(*_args: object) -> object:
            self.fail("unexpected GDB touch fallback access")

        def fail_write(*_args: object) -> None:
            self.fail("unexpected guest-RAM touch fallback write")

        backend._pause_for_gdb_locked = fail_gdb  # type: ignore[method-assign]
        backend._resume_after_gdb_locked = fail_gdb  # type: ignore[method-assign]
        backend._read_pc_paused_locked = fail_gdb  # type: ignore[method-assign]
        backend._read_u32_paused_locked = fail_gdb  # type: ignore[method-assign]
        backend._read_u8_paused_locked = fail_gdb  # type: ignore[method-assign]
        backend._read_u16_paused_locked = fail_gdb  # type: ignore[method-assign]
        backend._write_u8_paused_locked = fail_write  # type: ignore[method-assign]
        backend._write_u16_paused_locked = fail_write  # type: ignore[method-assign]
        backend._write_u32_paused_locked = fail_write  # type: ignore[method-assign]

        result = backend.apply_touch_state(120, 160, True)

        self.assertFalse(result.get("applied"), result)
        self.assertFalse(result.get("firmware_globals_written"), result)
        self.assertIsNone(result.get("mailbox"))
        self.assertIn("refusing guest-RAM mailbox/global fallback", str(result.get("error")))

    def test_bbk9588_key_refuses_guest_ram_fallback_without_chardev(self) -> None:
        class _RunningProc:
            def poll(self) -> None:
                return None

        config = QemuSystemConfig(machine="bbk9588")
        backend = QemuProcessBackend(config)
        backend.proc = _RunningProc()  # type: ignore[assignment]
        backend.gdb_sock = object()  # type: ignore[assignment]
        backend.bbk_input_sock = None

        def fail_gdb(*_args: object) -> object:
            self.fail("unexpected GDB key fallback access")

        backend._pause_for_gdb_locked = fail_gdb  # type: ignore[method-assign]
        backend._resume_after_gdb_locked = fail_gdb  # type: ignore[method-assign]
        backend._read_u32_paused_locked = fail_gdb  # type: ignore[method-assign]
        backend._read_u8_paused_locked = fail_gdb  # type: ignore[method-assign]
        backend._write_u8_paused_locked = fail_gdb  # type: ignore[method-assign]

        result = backend.apply_gui_key_event(7, True)

        self.assertFalse(result.get("applied"), result)
        self.assertIsNone(result.get("mailbox"))
        self.assertIn("refusing guest-RAM mailbox/global fallback", str(result.get("error")))

    def test_qemu_bbk9588_touch_uses_chardev_without_guest_ram_global_writes(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        config = build_bbk_qemu_config(boot_mode="c200", gdb="auto", timeout_seconds=1.5)
        backend = QemuProcessBackend(config)
        try:
            backend.start()
            self.assertTrue(backend.running())
            time.sleep(1.0)
            gdb_writes_before = backend.gdb_write_count
            register_writes_before = backend.gdb_register_write_count
            result = backend.apply_touch_state(120, 160, True)
            self.assertTrue(result.get("applied"), result)
            self.assertEqual(result.get("source"), "qemu-c-machine-chardev")
            self.assertFalse(result.get("calibration_release_seeded"))
            self.assertFalse(result.get("firmware_globals_written"), result)
            self.assertNotIn("touch_x_addr", result)
            self.assertNotIn("touch_y_addr", result)
            self.assertNotIn("firmware_touch_x_addr", result)
            self.assertNotIn("firmware_touch_y_addr", result)
            self.assertNotIn("latch_addr", result)
            self.assertNotIn("diagnostic_latch_addr", result)
            self.assertIsNone(result.get("mailbox"))
            self.assertGreaterEqual(int(result.get("bbk_input_write_count") or 0), 1)
            self.assertEqual(backend.gdb_write_count, gdb_writes_before)
            self.assertEqual(backend.gdb_register_write_count, register_writes_before)
            gui_handler = result.get("gui_handler")
            self.assertIsInstance(gui_handler, dict)
            assert isinstance(gui_handler, dict)
            self.assertTrue(gui_handler.get("skipped"), gui_handler)
            self.assertEqual(gui_handler.get("source"), "qemu-c-machine")
            time.sleep(0.08)
            touch_globals_x = backend.read_virtual_memory(0x80370FC8, 4)
            touch_globals_y = backend.read_virtual_memory(0x80370FCC, 4)
            self.assertIn(touch_globals_x, {b"\xff\xff\x00\x00", (120).to_bytes(4, "little")})
            self.assertIn(touch_globals_y, {b"\xff\xff\x00\x00", (160).to_bytes(4, "little")})
            gpio = struct.unpack("<I", backend.read_virtual_memory(0xB0010100, 4))[0]
            self.assertEqual(gpio & 0x00040000, 0)
            sadc_status = backend.read_virtual_memory(0xB007000C, 1)[0]
            intc_pending = struct.unpack("<I", backend.read_virtual_memory(0xB0001010, 4))[0]
            if sadc_status & 0x14:
                self.assertEqual(sadc_status & 0x14, 0x14)
                self.assertEqual(intc_pending & (1 << 12), 1 << 12)
            else:
                self.assertEqual(intc_pending & (1 << 12), 0)
            gdb_writes_before_release = backend.gdb_write_count
            register_writes_before_release = backend.gdb_register_write_count
            release = backend.apply_touch_state(120, 160, False)
            self.assertTrue(release.get("applied"), release)
            self.assertFalse(release.get("firmware_globals_written"), release)
            self.assertEqual(backend.gdb_write_count, gdb_writes_before_release)
            self.assertEqual(backend.gdb_register_write_count, register_writes_before_release)
            time.sleep(0.08)
            released_gpio = struct.unpack("<I", backend.read_virtual_memory(0xB0010100, 4))[0]
            self.assertEqual(released_gpio & 0x00040000, 0x00040000)
            released_status = backend.read_virtual_memory(0xB007000C, 1)[0]
            released_intc_pending = struct.unpack("<I", backend.read_virtual_memory(0xB0001010, 4))[0]
            if released_status & 0x08:
                self.assertEqual(released_status & 0x08, 0x08)
            else:
                self.assertEqual(released_intc_pending & (1 << 12), 0)
            qemu = backend.snapshot()
            self.assertGreaterEqual(int(qemu.get("bbk_input_write_count") or 0), 1)
            self.assertTrue(qemu.get("guest_input_events"))
        finally:
            backend.stop()

    def test_qemu_gdb_touch_bridge_calls_gui_handler_after_active_object(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        config = build_bbk_qemu_config(boot_mode="c200", machine="malta", timeout_seconds=1.5)
        backend = QemuProcessBackend(config)
        try:
            backend.start()
            self.assertTrue(backend.running())
            time.sleep(0.8)
            gui: dict[str, object] = {}
            for x, y in ((10, 10), (230, 10), (230, 310), (10, 310)):
                self.assertTrue(backend.apply_touch_state(x, y, True).get("applied"))
                time.sleep(0.45)
                release = backend.apply_touch_state(x, y, False)
                self.assertTrue(release.get("applied"), release)
                time.sleep(0.45)
                gui = backend.guest_gui_state_snapshot()
                if gui.get("active_object_ready"):
                    break
            self.assertTrue(gui.get("active_object_ready"), gui)

            result = backend.apply_touch_state(150, 205, True)
            self.assertTrue(result.get("applied"), result)
            gui_handler = result.get("gui_handler")
            self.assertIsInstance(gui_handler, dict)
            assert isinstance(gui_handler, dict)
            self.assertTrue(gui_handler.get("called"), gui_handler)
            handler_active = gui_handler.get("active")
            call = gui_handler.get("call")
            self.assertIsInstance(call, dict)
            assert isinstance(call, dict)
            self.assertTrue(call.get("returned"), call)
            self.assertEqual(call.get("mode"), "continue")
            self.assertEqual(call.get("final_pc"), "0x80008a8c")
            gui_ring_pump = result.get("gui_ring_pump")
            self.assertIsInstance(gui_ring_pump, dict)
            assert isinstance(gui_ring_pump, dict)
            self.assertTrue(gui_ring_pump.get("pumped"), gui_ring_pump)
            self.assertTrue(gui_ring_pump.get("called"), gui_ring_pump)
            self.assertEqual(gui_ring_pump.get("queue"), "0x80825840")
            self.assertEqual(gui_ring_pump.get("call", {}).get("final_pc"), "0x80008a8c")
            gui_idle_pump = result.get("gui_idle_pump")
            self.assertIsInstance(gui_idle_pump, dict)
            assert isinstance(gui_idle_pump, dict)
            self.assertTrue(gui_idle_pump.get("returned"), gui_idle_pump)
            self.assertEqual(gui_idle_pump.get("call", {}).get("final_pc"), "0x80008a8c")

            release = backend.apply_touch_state(150, 205, False)
            self.assertTrue(release.get("applied"), release)
            self.assertEqual(release.get("touch_capture_active"), handler_active)
            release_handler = release.get("gui_handler")
            self.assertIsInstance(release_handler, dict)
            assert isinstance(release_handler, dict)
            self.assertEqual(release_handler.get("active"), handler_active)
            modal_close = release.get("gui_modal_close_settle")
            self.assertIsInstance(modal_close, dict)
            assert isinstance(modal_close, dict)
            if modal_close.get("attempted"):
                self.assertTrue(modal_close.get("closed"), modal_close)
                self.assertEqual(modal_close.get("modal_after"), "0x00000000")
                self.assertEqual(modal_close.get("remove_call", {}).get("final_pc"), "0x80008a8c")
                self.assertEqual(modal_close.get("close_call", {}).get("final_pc"), "0x80008a8c")
            else:
                self.assertEqual(modal_close.get("reason"), "no-blocking-busy-node")
            event_poller = release.get("gui_event_poller")
            self.assertIsInstance(event_poller, dict)
            assert isinstance(event_poller, dict)
            self.assertTrue(event_poller.get("drained"), event_poller)
            self.assertEqual(event_poller.get("flags_after"), "0x00000000")
            self.assertTrue(event_poller.get("events"), event_poller)
            storage_service = release.get("legacy_python_storage_hook")
            self.assertIsInstance(storage_service, dict)
            assert isinstance(storage_service, dict)
            self.assertIn("seed", storage_service)
            repaint_settle = release.get("gui_repaint_settle")
            self.assertIsInstance(repaint_settle, dict)
            assert isinstance(repaint_settle, dict)
            self.assertTrue(repaint_settle.get("settled"), repaint_settle)
            self.assertEqual(repaint_settle.get("final_flags"), "0x00000000")
            self.assertTrue(repaint_settle.get("rounds"), repaint_settle)
        finally:
            backend.stop()

    def test_comparison_benchmark_quick_mode(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            completed = subprocess.run(
                [
                    sys.executable,
                    "emu/test/run_qemu_comparison_benchmark.py",
                    "--out-dir",
                    str(out_dir),
                    "--prefix",
                    "comparison_quick_test",
                    "--qemu-timeout",
                    "1.5",
                ],
                cwd=Path(__file__).resolve().parents[2],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            output = json.loads(completed.stdout)
            summary = json.loads(Path(output["summary"]).read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["qemu_process"]["pc_progressed"])
            pcs = summary["qemu_process"]["sampled_pcs"]
            self.assertTrue(all(pc != "0x80012314" for pc in pcs), pcs)


if __name__ == "__main__":
    unittest.main()
