from __future__ import annotations

import argparse
import json
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import http.client
from pathlib import Path

from emu.qemu.system import (
    DEFAULT_C200_BASE,
    DEFAULT_BBK9588_FIRMWARE_PATCHES,
    DEFAULT_QEMU_FIRMWARE_PATCHES,
    DEFAULT_QEMU_MACHINE,
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
from emu.web.frontend_state import AUTO_CALIBRATION_TARGETS, FrontendState


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

    def running(self) -> bool:
        return True

    def snapshot(self) -> dict[str, object]:
        return {"pc": "0x80017ba4"}

    def guest_gui_state_snapshot(self) -> dict[str, object]:
        ready = len(self.touches) >= len(AUTO_CALIBRATION_TARGETS) * 2
        return {
            "active_object_ready": ready,
            "active_object_80474048": "0x80959670" if ready else "0x00000000",
        }

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
    sectors_per_cluster: int = 0x10,
    reserved: int = 1,
    fats: int = 2,
    root_entries: int = 0x100,
    total_sectors: int = 0x9B949,
    sectors_per_fat: int = 0x9C,
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

    def test_classifies_fat16_resource_cache_lookup(self) -> None:
        classified = classify_guest_pc("0x8017ca10")
        self.assertIsInstance(classified, dict)
        assert classified is not None
        self.assertEqual(classified.get("region"), "fat16-resource-cache-lookup")
        self.assertIn("cache miss-load", str(classified.get("description")))

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

    def test_builds_bbk9588_uboot_machine_with_bootloader_addresses(self) -> None:
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

        machine_arg = command[command.index("-M") + 1]
        self.assertIn("bbk9588", machine_arg)
        self.assertIn("firmware-phys=0x900000", machine_arg)
        self.assertIn("reset-pc=0x80900000", machine_arg)
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
        self.assertIn("bbk9588", command)
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

        self.assertIn("bbk9588,input-chardev=bbk9588-input,frame-chardev=bbk9588-frame", command)
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
                "lcd-refresh-period-ms=100",
            ),
        )

        command = build_qemu_command(config)

        self.assertIn(
            "bbk9588,cpu-irq-output=on,progress-trace=on,lcd-refresh-period-ms=100,firmware-phys=0x4000,reset-pc=0x80004000",
            command,
        )

    def test_bbk9588_default_patches_skip_c_device_stubs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "C200.bin"
            image.write_bytes(b"\0" * 0x200000)

            config = build_bbk_qemu_config(image=image, machine="bbk9588")

        self.assertEqual(config.firmware_patches, DEFAULT_BBK9588_FIRMWARE_PATCHES)
        self.assertEqual(config.firmware_patches, ())
        self.assertNotIn("c200-lcd-ready", config.firmware_patches)
        self.assertNotIn("c200-uart-ready", config.firmware_patches)
        self.assertNotIn("c200-cp0-irq-enable-noop", config.firmware_patches)
        self.assertNotIn("c200-no-event-poll-empty", config.firmware_patches)
        self.assertNotIn("c200-wait-noop", config.firmware_patches)

    def test_malta_default_patches_stay_full_compatibility_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "C200.bin"
            image.write_bytes(b"\0" * 0x200000)

            config = build_bbk_qemu_config(image=image, machine="malta")

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
            self.assertIn("hw/mips/bbk9588.c", result["proposed_bbk9588_files"])

    def test_qemu_subprocess_env_adds_msys_paths_for_source_build(self) -> None:
        env = qemu_subprocess_env(r"E:\qemu-src\build-bbk9588-win\qemu-system-mipsel.exe")

        path = env.get("PATH", "").replace("\\", "/").lower()
        self.assertIn("c:/msys64/ucrt64/bin", path)

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
                    "event-loop-synth-events=on",
                    "--qemu-machine-option",
                    "semaphore-fastpath=off",
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
            self.assertIn("semaphore-fastpath=off", summary["qemu_machine_options"])
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
                    "semaphore-fastpath=off",
                    "--qemu-machine-option",
                    "cache-scan-fastpath=off",
                    "--qemu-machine-option",
                    "resource-release-fastpath=off",
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

            config = build_bbk_qemu_config(image=image)

            self.assertEqual(DEFAULT_QEMU_MACHINE, "bbk9588")
            self.assertEqual(config.machine, "bbk9588")
            self.assertEqual(config.firmware_patches, ())
            self.assertNotIn("touch-autocal=on", config.bbk_machine_options)
            assert config.boot_payload is not None
            self.assertEqual(config.boot_payload.path.resolve(), image.resolve())

    def test_bbk9588_launcher_does_not_override_explicit_touch_autocal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "C200.bin"
            image.write_bytes(b"\0" * 0x200000)

            config = build_bbk_qemu_config(
                image=image,
                bbk_machine_options=("touch-autocal=off", "storage-trace=on"),
            )

            self.assertIn("touch-autocal=off", config.bbk_machine_options)
            self.assertIn("storage-trace=on", config.bbk_machine_options)
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

            config = build_bbk_qemu_config(image=image, machine="malta")

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
            nand[page_off : page_off + 512] = _fat16_boot_sector(hidden=0x20, root_entries=0x100)
            (build / "bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin").write_bytes(nand)
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
            self.assertEqual(layout["root_dir_sectors"], 0x10)
            self.assertEqual(layout["root_lba"], 0x159)
            self.assertEqual(layout["first_data_lba"], 0x169)

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

    def test_qemu_storage_seed_sets_default_drive_globals(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        writes32: dict[int, int] = {}
        writes16: dict[int, int] = {}
        writes8: dict[int, int] = {}

        backend._fat16_layout_from_backing = lambda: {  # type: ignore[method-assign]
            "volume_lba": 0x20,
            "bytes_per_sector": 0x200,
            "sectors_per_cluster": 0x10,
            "fat_lba": 0x21,
            "root_lba": 0x159,
            "root_dir_sectors": 0x10,
            "first_data_lba": 0x169,
            "total_sectors": 0x9B949,
        }
        backend._is_guest_ram_va = lambda va, size=1: True  # type: ignore[method-assign]
        backend._write_u32_paused_locked = lambda va, value: writes32.__setitem__(va, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._write_u16_paused_locked = lambda va, value: writes16.__setitem__(va, value & 0xFFFF)  # type: ignore[method-assign]
        backend._write_u8_paused_locked = lambda va, value: writes8.__setitem__(va, value & 0xFF)  # type: ignore[method-assign]

        row = backend._seed_storage_fastpath_globals_paused_locked()

        self.assertTrue(row.get("seeded"), row)
        self.assertEqual(writes32[0x80474228], 0)
        self.assertEqual(writes8[0x8047428D], 1)

    def test_qemu_storage_seed_skips_gdb_writes_when_bbk9588_c_machine_seeded(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend._fat16_layout_from_backing = lambda: {"first_data_lba": 0x169}  # type: ignore[method-assign]
        backend._read_u32_paused_locked = lambda va: {  # type: ignore[method-assign]
            0x804BF434: 1,
            0x80474238: 0x169,
        }.get(va, 0)
        backend._read_u8_paused_locked = lambda va: 1 if va == 0x8047428D else 0  # type: ignore[method-assign]
        backend._write_u32_paused_locked = lambda va, value: self.fail("unexpected GDB u32 seed write")  # type: ignore[method-assign]
        backend._write_u16_paused_locked = lambda va, value: self.fail("unexpected GDB u16 seed write")  # type: ignore[method-assign]
        backend._write_u8_paused_locked = lambda va, value: self.fail("unexpected GDB u8 seed write")  # type: ignore[method-assign]

        row = backend._seed_storage_fastpath_globals_paused_locked()

        self.assertTrue(row.get("seeded"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")
        self.assertEqual(row.get("first_data_lba"), "0x169")

    def test_qemu_resource_pump_rounds_skip_when_bbk9588_c_machine_ready(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend._read_u32_paused_locked = lambda va: 0 if va == 0x804BF440 else 0  # type: ignore[method-assign]
        backend._read_u8_paused_locked = lambda va: 1 if va == 0x804BF444 else 0  # type: ignore[method-assign]
        backend._read_pc_paused_locked = lambda: 0x8005BC70  # type: ignore[method-assign]
        backend._service_resource_pump_paused_locked = lambda **kwargs: self.fail("unexpected Python resource pump")  # type: ignore[method-assign]

        row = backend._service_resource_pump_rounds_paused_locked(rounds=3)

        self.assertTrue(row.get("skipped"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")
        self.assertEqual(row.get("reason"), "qemu-c-resource-refresh-ready")
        self.assertEqual(row.get("handled_count"), 0)
        refresh = row.get("resource_refresh")
        self.assertIsInstance(refresh, dict)
        assert isinstance(refresh, dict)
        self.assertTrue(refresh.get("ready"), refresh)

    def test_qemu_resource_pump_rounds_still_run_for_malta(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="malta"))
        calls: list[dict[str, object]] = []
        backend._read_u32_paused_locked = lambda va: 0  # type: ignore[method-assign]
        backend._read_u8_paused_locked = lambda va: 1 if va == 0x804BF444 else 0  # type: ignore[method-assign]
        backend._read_pc_paused_locked = lambda: 0x80004000  # type: ignore[method-assign]
        backend._prime_resource_refresh_paused_locked = lambda: None  # type: ignore[method-assign]
        backend._service_resource_pump_paused_locked = lambda **kwargs: calls.append(dict(kwargs)) or {  # type: ignore[method-assign]
            "event": "qemu-resource-pump-service",
            "events": [],
            "handled_count": 0,
        }

        row = backend._service_resource_pump_rounds_paused_locked(rounds=1)

        self.assertFalse(row.get("skipped"), row)
        self.assertEqual(len(calls), 1)

    def test_qemu_bbk9588_storage_breakpoints_omit_c_ready_idle_checks(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        pcs = backend._storage_fastpath_pcs_for_machine()

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
        pcs = backend._storage_fastpath_pcs_for_machine()

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

    def test_qemu_bbk9588_storage_fastpath_service_skips_when_c_machine_covers_path(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))
        backend.gdb_sock = object()  # type: ignore[assignment]
        backend._seed_storage_fastpath_globals_paused_locked = lambda: {"seeded": True, "source": "qemu-c-machine"}  # type: ignore[method-assign]
        backend._read_pc_paused_locked = lambda: 0x8000E444  # type: ignore[method-assign]

        row = backend._service_storage_fastpaths_paused_locked()

        self.assertTrue(row.get("skipped"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")
        self.assertEqual(row.get("reason"), "qemu-c-machine-storage-resource-path")
        self.assertEqual(row.get("handled_count"), 0)

    def test_qemu_bbk9588_lcd_mirror_is_handled_by_c_machine(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig(machine="bbk9588"))

        row = backend.enable_lcd_mirror()

        self.assertTrue(row.get("enabled"), row)
        self.assertTrue(row.get("skipped"), row)
        self.assertEqual(row.get("source"), "qemu-c-machine")

    def test_qemu_storage_fastpath_handles_cache_tail_and_block_size(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        regs = {2: 1, 16: 0, 17: 3, 18: 9, 19: 0x12345678, 31: 0x80001234}
        written_regs: dict[int, int] = {}
        written_mem: dict[int, bytes] = {}

        backend._fat16_layout_from_backing = lambda: {"bytes_per_sector": 512}  # type: ignore[method-assign]
        backend._backing_sector_capacity = lambda: 0x75200  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: regs.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: written_regs.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = lambda va, data: written_mem.__setitem__(va, bytes(data))  # type: ignore[method-assign]

        row = backend._handle_storage_fastpath_break_paused_locked(0x8017BEF4)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "cache-scan-tail")
        self.assertEqual(row.get("return_pc"), "0x8017bf2c")
        self.assertEqual(written_regs[17], 9)
        self.assertEqual(written_regs[2], 0x12345678)
        self.assertEqual(written_regs[37], 0x8017BF2C)
        self.assertEqual(written_mem[0x8047425C], (2).to_bytes(4, "little"))

        regs.clear()
        regs[31] = 0x8000ABCD
        written_regs.clear()
        row = backend._handle_storage_fastpath_break_paused_locked(0x80182D58)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "block-size-hook")
        self.assertEqual(written_regs[2], 0x75200 * 512)
        self.assertEqual(written_regs[37], 0x8000ABCD)

    def test_qemu_storage_fastpath_handles_dirent_and_lfn_copy(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        regs = {4: 0x80801000, 5: 0x80802000, 31: 0x80001234}
        memory: dict[int, bytes] = {}
        written_regs: dict[int, int] = {}
        dirent = bytearray(0x20)
        dirent[0:11] = b"FILE    TXT"
        dirent[0x0B] = 0x20
        struct.pack_into("<H", dirent, 0x14, 0x12)
        struct.pack_into("<H", dirent, 0x1A, 0x3456)
        struct.pack_into("<I", dirent, 0x1C, 0x789A)
        memory[0x80801000] = bytes(dirent)

        backend._fat16_layout_from_backing = lambda: {"bytes_per_sector": 512}  # type: ignore[method-assign]
        backend._is_guest_ram_va = lambda va, size=1: va >= 0x80000000 and size >= 0  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: regs.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: written_regs.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = lambda va, size: memory[va][:size]  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = lambda va, data: memory.__setitem__(va, bytes(data))  # type: ignore[method-assign]

        row = backend._handle_storage_fastpath_break_paused_locked(0x80175E40)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("kind"), "dirent-copy")
        self.assertEqual(written_regs[37], 0x80001234)
        copied = memory[0x80802000]
        self.assertEqual(copied[:11], b"FILE    TXT")
        self.assertEqual(struct.unpack_from("<I", copied, 0x14)[0], 0x00123456)
        self.assertEqual(struct.unpack_from("<I", copied, 0x1C)[0], 0x789A)
        self.assertEqual(memory[0x80802000 + 0x2C], (0x00123456).to_bytes(4, "little"))
        self.assertEqual(memory[0x80802000 + 0x30], (0x00123456).to_bytes(4, "little"))

        lfn = bytearray(range(0x20))
        memory[0x80803000] = bytes(lfn)
        regs.clear()
        regs.update({4: 0, 7: 0x80803000, 16: 0x80804000, 17: 5})
        written_regs.clear()

        row = backend._handle_storage_fastpath_break_paused_locked(0x80174C9C)

        self.assertTrue(row.get("handled"), row)
        self.assertTrue(row.get("fused"), row)
        self.assertEqual(memory[0x80804000], bytes(lfn[1:11] + lfn[0x0E:0x1A] + lfn[0x1C:0x20]))
        self.assertEqual(written_regs[16], 0x80804000 + 26)
        self.assertEqual(written_regs[17], 31)
        self.assertEqual(written_regs[37], 0x80174D04)

    def test_qemu_fat16_cluster_read_invalid_cluster_returns_error(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        regs = {4: 0, 5: 0x80960000, 31: 0x8017E058}
        written: dict[int, int] = {}

        backend._fat16_layout_from_backing = lambda: {  # type: ignore[method-assign]
            "sectors_per_cluster": 0x10,
            "bytes_per_sector": 0x200,
            "first_data_lba": 0x169,
        }
        backend._read_register_paused_locked = lambda reg: regs.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: written.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_storage_fastpath_break_paused_locked(0x8017B4E0)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("reason"), "invalid-cluster-return-error")
        self.assertEqual(written[2], 0xFFFFFFFF)
        self.assertEqual(written[37], 0x8017E058)

    def test_qemu_fat16_cluster_read_eof_cluster_returns_zero(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        regs = {4: 0, 5: 0x80960000, 7: 0xFFFFFFFF, 21: 0xFFFFFFFF, 31: 0x8017E058}
        written: dict[int, int] = {}

        backend._fat16_layout_from_backing = lambda: {  # type: ignore[method-assign]
            "sectors_per_cluster": 0x10,
            "bytes_per_sector": 0x200,
            "first_data_lba": 0x169,
        }
        backend._read_register_paused_locked = lambda reg: regs.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: written.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_storage_fastpath_break_paused_locked(0x8017B4E0)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("reason"), "eof-cluster-return-zero")
        self.assertEqual(written[2], 0)
        self.assertEqual(written[37], 0x8017E058)

    def test_qemu_fat16_cluster_read_eof_restores_transient_dlx_header_marker(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        regs = {4: 0, 5: 0x80960000, 7: 0xFFFFFFFF, 21: 0xFFFFFFFF, 31: 0x8017E058}
        written: dict[int, int] = {}
        memory = {0x80960000: bytearray(b"\xE5LX\x07")}

        backend._fat16_layout_from_backing = lambda: {  # type: ignore[method-assign]
            "sectors_per_cluster": 0x10,
            "bytes_per_sector": 0x200,
            "first_data_lba": 0x169,
        }
        backend._is_guest_ram_va = lambda va, size=1: 0x80960000 <= va and va + size <= 0x80960000 + len(memory[0x80960000])  # type: ignore[method-assign]

        def read_mem(va: int, size: int) -> bytes:
            offset = va - 0x80960000
            return bytes(memory[0x80960000][offset : offset + size])

        def write_mem(va: int, data: bytes) -> None:
            offset = va - 0x80960000
            memory[0x80960000][offset : offset + len(data)] = data

        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: regs.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: written.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]

        row = backend._handle_storage_fastpath_break_paused_locked(0x8017B4E0)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("reason"), "eof-cluster-return-zero")
        self.assertEqual(row.get("restored_header"), "DLX")
        self.assertEqual(bytes(memory[0x80960000][:4]), b"DLX\x07")
        self.assertEqual(written[2], 0)

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
        backend._service_storage_fastpaths_paused_locked = lambda **kwargs: self.fail(  # type: ignore[method-assign]
            "unexpected Python storage fastpath service"
        )
        backend._service_resource_pump_rounds_paused_locked = lambda **kwargs: self.fail(  # type: ignore[method-assign]
            "unexpected Python resource pump service"
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
        self.assertTrue(row.get("storage_fastpath_service", {}).get("skipped"), row)
        self.assertTrue(row.get("resource_pump_service", {}).get("skipped"), row)

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

    def test_qemu_event_loop_empty_skips_python_resource_pump_when_bbk9588_c_ready(self) -> None:
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
        backend._pump_resource_state_globals_paused_locked = lambda: self.fail("unexpected Python resource pump")  # type: ignore[method-assign]

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

    def test_qemu_resource_cache16_low_index_returns_default_lba(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0xFFFFFFFF, 4: 1, 31: 0x8017CA64}

        backend._fat16_layout_from_backing = lambda: {  # type: ignore[method-assign]
            "bytes_per_sector": 512,
            "sectors_per_cluster": 16,
            "first_data_lba": 0x169,
        }
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._read_u32_paused_locked = lambda va: {0x804BF434: 1, 0x80474238: 0x169, 0x8047429C: 0x169}.get(va)  # type: ignore[method-assign]

        row = backend._handle_storage_fastpath_break_paused_locked(0x8017CA10)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("reason"), "index-below-data-range-return-default-lba")
        self.assertEqual(row.get("value"), "0x00000169")
        self.assertEqual(registers[2], 0x169)
        self.assertEqual(registers[37], 0x8017CA64)

    def test_qemu_resource_cache16_ignores_uninitialized_cache(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        registers = {2: 0xFFFFFFFF, 4: 2, 31: 0x8017D3C8, 37: 0x8017CA10}

        backend._fat16_layout_from_backing = lambda: {  # type: ignore[method-assign]
            "bytes_per_sector": 512,
            "sectors_per_cluster": 16,
            "first_data_lba": 0x169,
        }
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._read_u32_paused_locked = lambda va: 0 if va == 0x804BF434 else None  # type: ignore[method-assign]

        row = backend._handle_storage_fastpath_break_paused_locked(0x8017CA10)

        self.assertFalse(row.get("handled"), row)
        self.assertEqual(row.get("reason"), "resource-cache16-not-initialized")
        self.assertEqual(registers[2], 0xFFFFFFFF)
        self.assertEqual(registers[37], 0x8017CA10)

    def test_qemu_resource_cache16_miss_initializes_cache_slot_from_backing(self) -> None:
        backend = QemuProcessBackend(QemuSystemConfig())
        backend.qemu_heap_next = 0x80970000
        registers = {2: 0xFFFFFFFF, 4: 0x04, 31: 0x8017D3C8, 37: 0x8017CA10}
        table = 0x8086D180
        table_data = bytearray()
        for _ in range(8):
            table_data += struct.pack("<IIII", 0xFFFFFFFF, 0, 0, 0)
        memory: dict[int, bytearray] = {table: table_data}
        sector = bytearray(b"\xFF" * 512)
        struct.pack_into("<H", sector, 0x04 * 2, 0x1234)

        backend._fat16_layout_from_backing = lambda: {  # type: ignore[method-assign]
            "bytes_per_sector": 512,
            "sectors_per_cluster": 16,
            "first_data_lba": 0x169,
        }

        def read_mem(va: int, size: int) -> bytes:
            for base, block in memory.items():
                if base <= va and va + size <= base + len(block):
                    off = va - base
                    return bytes(block[off : off + size])
            raise KeyError(hex(va))

        def write_mem(va: int, data: bytes) -> None:
            for base, block in memory.items():
                if base <= va and va + len(data) <= base + len(block):
                    off = va - base
                    block[off : off + len(data)] = data
                    return
            memory[va] = bytearray(data)

        def read_u32(va: int) -> int | None:
            if va == 0x804BF434:
                return 1
            if va == 0x80474260:
                return 0x21
            try:
                return struct.unpack("<I", read_mem(va, 4))[0]
            except Exception:
                return None

        backend._is_guest_ram_va = lambda va, size=1: 0x80000000 <= va and va + size <= 0x81000000  # type: ignore[method-assign]
        backend._read_virtual_memory_paused_locked = read_mem  # type: ignore[method-assign]
        backend._write_virtual_memory_paused_locked = write_mem  # type: ignore[method-assign]
        backend._read_register_paused_locked = lambda reg: registers.get(reg, 0)  # type: ignore[method-assign]
        backend._write_register_paused_locked = lambda reg, value: registers.__setitem__(reg, value & 0xFFFFFFFF)  # type: ignore[method-assign]
        backend._read_u32_paused_locked = read_u32  # type: ignore[method-assign]
        backend._write_u32_paused_locked = lambda va, value: write_mem(va, struct.pack("<I", value & 0xFFFFFFFF))  # type: ignore[method-assign]
        backend._read_backing_sector = lambda sector_id: bytes(sector) if sector_id == 0x21 else None  # type: ignore[method-assign]

        row = backend._handle_storage_fastpath_break_paused_locked(0x8017CA10)

        self.assertTrue(row.get("handled"), row)
        self.assertEqual(row.get("mode"), "miss-load")
        self.assertEqual(row.get("value"), "0x1234")
        self.assertEqual(registers[2], 0x1234)
        self.assertEqual(registers[37], 0x8017D3C8)
        self.assertEqual(struct.unpack_from("<I", memory[table], 0)[0], 0x21)
        buffer_va = struct.unpack_from("<I", memory[table], 4)[0]
        self.assertEqual(bytes(memory[buffer_va]), bytes(sector))

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

    def test_frontend_qemu_auto_calibration_releases_last_touch_before_complete(self) -> None:
        state = FrontendState.__new__(FrontendState)
        state.args = argparse.Namespace(auto_calibration=True, boot_mode="c200")
        state.auto_calibration_stage = 0
        state.auto_calibration_last_stage_step = -1
        state.qemu_auto_calibration_last_action_at = 0.0
        state.qemu_auto_calibration_log = []
        state.qemu_storage_bootstrap_done = False
        state.qemu_storage_bootstrap_attempts = 0
        state.qemu_storage_bootstrap_log = []
        backend = _FakeFrontendQemuBackend()

        for _index in range(len(AUTO_CALIBRATION_TARGETS) * 2 + 1):
            state.qemu_auto_calibration_last_action_at = time.time() - 1.0
            state._apply_qemu_auto_calibration_locked(backend)  # type: ignore[arg-type]

        self.assertFalse(backend.completed)
        self.assertEqual(state.auto_calibration_stage, 12)
        self.assertEqual(len(backend.touches), len(AUTO_CALIBRATION_TARGETS) * 2)
        self.assertEqual(backend.touches[-1], (*AUTO_CALIBRATION_TARGETS[-1], False))
        self.assertEqual([down for _x, _y, down in backend.touches], [True, False, True, False, True, False, True, False])

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
            self.assertEqual(touch_result.get("touch_x_addr"), "0x80370fc8")
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
        config = build_bbk_qemu_config(timeout_seconds=1.5)
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
        config = build_bbk_qemu_config(timeout_seconds=1.5)
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
        config = build_bbk_qemu_config(timeout_seconds=1.5)
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
        config = build_bbk_qemu_config(timeout_seconds=1.5)
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
        config = build_bbk_qemu_config(timeout_seconds=1.5)
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

    def test_qemu_gdb_touch_bridge_applies_touch_globals(self) -> None:
        if find_qemu() is None:
            self.skipTest("qemu-system-mipsel is not installed")
        config = build_bbk_qemu_config(timeout_seconds=1.5)
        backend = QemuProcessBackend(config)
        try:
            backend.start()
            self.assertTrue(backend.running())
            time.sleep(1.0)
            result = backend.apply_touch_state(120, 160, True)
            self.assertTrue(result.get("applied"), result)
            self.assertEqual(result.get("source"), "qemu-c-machine-chardev")
            self.assertFalse(result.get("calibration_release_seeded"))
            self.assertEqual(result.get("touch_x_addr"), "0x80370fc8")
            self.assertIsNone(result.get("mailbox"))
            self.assertGreaterEqual(int(result.get("bbk_input_write_count") or 0), 1)
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
            release = backend.apply_touch_state(120, 160, False)
            self.assertTrue(release.get("applied"), release)
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
        config = build_bbk_qemu_config(machine="malta", timeout_seconds=1.5)
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
            storage_service = release.get("storage_fastpath_service")
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
