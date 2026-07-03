"""Frontend emulator state and input/frame queues for the BBK 9588 web UI."""

from __future__ import annotations

import argparse
import subprocess
import threading
import time
from collections import deque
from pathlib import Path

from bbk9588_hwemu import Bbk9588HwEmu
from hwemu_defs import (
    FirmwareKeySample,
    GPIO_KEY_CODE_BITS,
    ScheduledTouchControllerEvent,
    TOUCH_CALIBRATION_REFERENCE_POINTS,
)
from hwemu_framebuffer import png_bytes_from_rgb, render_rgb565_framebuffer
from hwemu_utils import access_to_dict, find_workspace_file


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
FAT_IMAGE = BUILD / "bbk9588_fs_fat16.img"
COMBINED_NAND_IMAGE = BUILD / "bbk9588_nand_c200_fat_page1c40_gbkshort_usbfix.bin"
FALLBACK_COMBINED_NAND_IMAGE = BUILD / "bbk9588_nand_c200_fat_page1c40.bin"
DEFAULT_READONLY_NAND_RANGE = (0x1C40, 0x28AA7)
AUTO_BOOT_DIALOG_X = 150
AUTO_BOOT_DIALOG_Y = 205
AUTO_BOOT_DIALOG_READY_PCS = {0x800A8130}
AUTO_CALIBRATION_TARGETS = tuple((x, y) for x, y, _raw_x, _raw_y in TOUCH_CALIBRATION_REFERENCE_POINTS)
AUTO_CALIBRATION_PRESS_RANGES = (
    (0x80017C60, 0x80017CD4),
    (0x80017CD8, 0x80017D74),
    (0x80017D78, 0x80017E08),
    (0x80017E28, 0x80018C80),
)
AUTO_CALIBRATION_CAPTURE_RANGES = (
    (0x800190E4, 0x80019248),
    (0x80018F78, 0x800190D8),
    (0x80018E0C, 0x80018F70),
    (0x80018C84, 0x80018DE8),
)
AUTO_CALIBRATION_CAPTURE_PCS = tuple(start for start, _end in AUTO_CALIBRATION_CAPTURE_RANGES)
AUTO_BOOT_TRACE_PCS = [
    0x800087C4,
    0x800080F0,
    0x800081A8,
    0x80008A84,
    0x8005BCD4,
    0x8001A8FC,
    0x8001AC40,
    0x8000B3DC,
    0x800DD380,
    0x800CA8C0,
    0x800CAD20,
    0x800CEE94,
    0x800D099C,
    0x800E0D68,
    *AUTO_CALIBRATION_CAPTURE_PCS,
]
AUTO_BOOT_STAGE_LABELS = {
    0: "calib-1-down",
    1: "calib-1-up",
    2: "calib-2-down",
    3: "calib-2-up",
    4: "calib-3-down",
    5: "calib-3-up",
    6: "calib-4-down",
    7: "calib-4-up",
    8: "wait-dialog",
    9: "dialog-wait-down",
    10: "dialog-down",
    11: "dialog-up",
    12: "done",
}


def display_to_raw_point(
    display_x: int,
    display_y: int,
    display_width: int,
    display_height: int,
    orientation: str,
    raw_width: int = 240,
    raw_height: int = 320,
) -> tuple[int, int]:
    """Map a rendered canvas pixel back to the 9588 raw touchscreen space."""
    display_width = max(1, int(display_width))
    display_height = max(1, int(display_height))
    if orientation in {"cw90", "ccw90"}:
        oriented_width, oriented_height = raw_height, raw_width
    else:
        oriented_width, oriented_height = raw_width, raw_height

    x = max(0, min(display_width - 1, int(display_x)))
    y = max(0, min(display_height - 1, int(display_y)))
    x = max(0, min(oriented_width - 1, x * oriented_width // display_width))
    y = max(0, min(oriented_height - 1, y * oriented_height // display_height))

    if orientation == "rot180":
        raw_x = raw_width - 1 - x
        raw_y = raw_height - 1 - y
    elif orientation == "hflip":
        raw_x = raw_width - 1 - x
        raw_y = y
    elif orientation == "vflip":
        raw_x = x
        raw_y = raw_height - 1 - y
    elif orientation == "cw90":
        raw_x = y
        raw_y = raw_height - 1 - x
    elif orientation == "ccw90":
        raw_x = raw_width - 1 - y
        raw_y = x
    else:
        raw_x = x
        raw_y = y
    return max(0, min(raw_width - 1, raw_x)), max(0, min(raw_height - 1, raw_y))


def raw_to_display_point(
    raw_x: int,
    raw_y: int,
    orientation: str,
    raw_width: int = 240,
    raw_height: int = 320,
) -> tuple[int, int]:
    x = max(0, min(raw_width - 1, int(raw_x)))
    y = max(0, min(raw_height - 1, int(raw_y)))
    if orientation == "rot180":
        return raw_width - 1 - x, raw_height - 1 - y
    if orientation == "hflip":
        return raw_width - 1 - x, y
    if orientation == "vflip":
        return x, raw_height - 1 - y
    if orientation == "cw90":
        return raw_height - 1 - y, x
    if orientation == "ccw90":
        return y, raw_width - 1 - x
    return x, y


def display_to_touch_point(
    display_x: int,
    display_y: int,
    display_width: int,
    display_height: int,
    orientation: str,
    touch_width: int = 240,
    touch_height: int = 320,
) -> tuple[int, int]:
    """Map visible canvas coordinates to C200's touchscreen coordinate space."""
    return display_to_panel_point(
        display_x,
        display_y,
        display_width,
        display_height,
        touch_width,
        touch_height,
    )


def display_to_panel_point(
    display_x: int,
    display_y: int,
    display_width: int,
    display_height: int,
    panel_width: int = 240,
    panel_height: int = 320,
) -> tuple[int, int]:
    """Map visible canvas coordinates to physical touch-panel coordinates."""
    display_width = max(1, int(display_width))
    display_height = max(1, int(display_height))
    x = max(0, min(display_width - 1, int(display_x)))
    y = max(0, min(display_height - 1, int(display_y)))
    panel_x = x * panel_width // display_width
    panel_y = y * panel_height // display_height
    return max(0, min(panel_width - 1, panel_x)), max(0, min(panel_height - 1, panel_y))


class FrontendState:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.lock = threading.RLock()
        self.emu: Bbk9588HwEmu | None = None
        self.last_error: str | None = None
        self.last_frame: dict[str, object] | None = None
        self.running = False
        self.job_name: str | None = None
        self.job_total_steps = 0
        self.job_done_steps = 0
        self.job_chunk_steps = 0
        self.job_started_at: float | None = None
        self.job_finished_at: float | None = None
        self.auto_calibration_stage = 0
        self.auto_calibration_last_stage_step = -1
        self.auto_calibration_capture_count = 0
        self.auto_dialog_press_trace_count = 0
        self.auto_dialog_press_poll_target = 0
        self.auto_dialog_frame_cache_seq = -1
        self.auto_dialog_frame_cache_result: bool | None = None
        self.cancel_run = threading.Event()
        self.worker: threading.Thread | None = None
        self.status_lock = threading.RLock()
        self.cached_status: dict[str, object] = {}
        self.cached_frame_bytes: bytes | None = None
        self.cached_frame_time = 0.0
        self.last_queued_frame_seq = -1
        self.frame_queue_lock = threading.RLock()
        self.frame_queue: deque[bytes] = deque(maxlen=120)
        self.input_lock = threading.RLock()
        self.pending_touches: deque[tuple[int, int, bool]] = deque(maxlen=32)
        self.pending_keys: deque[tuple[int, bool]] = deque(maxlen=32)
        self.reset_at = time.time()
        self.reset()

    def _ensure_fat_image(self) -> Path | None:
        if FAT_IMAGE.exists():
            return FAT_IMAGE
        maker = ROOT / "reverse" / "hwemu" / "make_fat16_image.py"
        system_dir = ROOT / "系统"
        app_dir = ROOT / "应用"
        if not system_dir.exists() or not app_dir.exists():
            return None
        BUILD.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["python", str(maker), "--output", str(FAT_IMAGE), str(system_dir), str(app_dir)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return FAT_IMAGE

    def reset(self) -> dict[str, object]:
        self.cancel_run.set()
        worker = self.worker
        if worker is not None and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=2.0)
        with self.lock:
            BUILD.mkdir(parents=True, exist_ok=True)
            c200 = find_workspace_file("C200.bin")
            if self.args.boot_mode == "uboot":
                image = find_workspace_file("u_boot_9588_4740.bin")
                base = 0x80900000
                pc = 0x80900000
                payload = c200
                payload_addr = 0x80004000
            else:
                image = c200
                base = 0x80004000
                pc = 0x80004000
                payload = None
                payload_addr = 0x80004000
            default_nand = (
                COMBINED_NAND_IMAGE
                if COMBINED_NAND_IMAGE.exists()
                else FALLBACK_COMBINED_NAND_IMAGE
                if FALLBACK_COMBINED_NAND_IMAGE.exists()
                else c200
            )
            nand_image = self.args.nand_image or default_nand
            block_image = self._ensure_fat_image() if self.args.block_image else None
            self.emu = Bbk9588HwEmu(
                image=image,
                base=base,
                pc=pc,
                ram_size=self.args.ram_mb * 1024 * 1024,
                trace_limit=self.args.trace_limit,
                recover_jr=True,
                profile="bbk9588-uboot",
                payload=payload,
                payload_addr=payload_addr,
                idle_stop_hits=0,
                app_idle_stop_hits=0,
                nand_image=nand_image,
                block_image=block_image,
                readonly_nand_page_ranges=[DEFAULT_READONLY_NAND_RANGE],
                bda_text_mode="native",
                bda_native_glyph_layout="rows-lsb-vscale2",
                bda_native_raster_mode="firmware",
                scheduler_tick_clamp=self.args.scheduler_tick_clamp,
                fast_hooks=not self.args.slow_global_code_hook,
                nand_loop_accelerator=self.args.nand_loop_accelerator,
                resource_cache16_accelerator=self.args.resource_cache16_accelerator,
                trace_pcs=AUTO_BOOT_TRACE_PCS,
                trace_pc_detail=False,
                suppress_hot_events=True,
                block_hook=False,
            )
            if self.args.state_in is not None:
                self.emu.load_emulator_state(self.args.state_in)
            self.last_error = None
            self.last_frame = None
            self.running = False
            self.job_name = None
            self.job_total_steps = 0
            self.job_done_steps = 0
            self.job_chunk_steps = 0
            self.job_started_at = None
            self.job_finished_at = None
            self.reset_at = time.time()
            self.auto_calibration_stage = 0
            self.auto_calibration_last_stage_step = -1
            self.auto_calibration_capture_count = 0
            self.auto_dialog_press_trace_count = 0
            self.auto_dialog_press_poll_target = 0
            self.auto_dialog_frame_cache_seq = -1
            self.auto_dialog_frame_cache_result = None
            self.cached_frame_bytes = None
            self.cached_frame_time = 0.0
            self.last_queued_frame_seq = -1
            with self.frame_queue_lock:
                self.frame_queue.clear()
            with self.input_lock:
                self.pending_touches.clear()
                self.pending_keys.clear()
            self._publish_snapshot_locked()
            return self.snapshot()

    def _render_current_frame_locked(self) -> bytes:
        assert self.emu is not None
        self.last_frame, rgb = render_rgb565_framebuffer(
            self.emu,
            0xA1F82000,
            0,
            240,
            320,
            240,
            "rgb565",
            self.args.orientation,
        )
        frame = png_bytes_from_rgb(
            int(self.last_frame["output_width"]),
            int(self.last_frame["output_height"]),
            rgb,
        )
        self.cached_frame_bytes = frame
        self.cached_frame_time = time.time()
        return frame

    def _queue_dirty_frame_locked(self, *, force: bool = False) -> bool:
        if self.emu is None:
            return False
        seq = int(getattr(self.emu, "framebuffer_dirty_seq", 0))
        if not force and seq == 0:
            return False
        if not force and seq == self.last_queued_frame_seq:
            return False
        frame = self._render_current_frame_locked()
        self.last_queued_frame_seq = seq
        with self.frame_queue_lock:
            self.frame_queue.append(frame)
        return True

    def pop_queued_frame(self) -> bytes | None:
        with self.frame_queue_lock:
            if not self.frame_queue:
                return None
            return self.frame_queue.popleft()

    def queued_frame_count(self) -> int:
        with self.frame_queue_lock:
            return len(self.frame_queue)

    def cached_frame(self) -> bytes | None:
        return self.cached_frame_bytes

    def worker_active(self) -> bool:
        return self._worker_alive()

    def _step_locked(self, steps: int, publish: bool = True, max_seconds: float | None = None) -> None:
        assert self.emu is not None
        self.running = True
        self.emu.state.stop_reason = None
        try:
            self.emu.run(max(1, steps), max_seconds=max_seconds, timeout_is_stop=max_seconds is None)
            self.last_error = None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.emu.state.stop_reason = self.last_error
            self.cancel_run.set()
        finally:
            if not publish:
                return
            self._publish_snapshot_locked()

    def _pending_touch_count_locked(self) -> int:
        with self.input_lock:
            return len(self.pending_touches)

    def _pending_key_count_locked(self) -> int:
        with self.input_lock:
            return len(self.pending_keys)

    def _refresh_pending_counts_cached(self) -> None:
        with self.status_lock:
            if not self.cached_status:
                return
            self.cached_status["pending_touches"] = self._pending_touch_count_locked()
            self.cached_status["pending_keys"] = self._pending_key_count_locked()

    def _auto_progress_locked(self) -> int:
        assert self.emu is not None
        return int(self.job_done_steps) + int(self.emu.state.insn_count)

    def _apply_auto_calibration_locked(self) -> None:
        """Feed cold-boot waits with modeled controller-level touchscreen input."""
        if not self.args.auto_calibration or self.args.boot_mode != "c200" or self.emu is None:
            return
        if self._pending_touch_count_locked():
            return
        pc = self.emu.pc & 0xFFFFFFFF
        progress = self._auto_progress_locked()
        stage = self.auto_calibration_stage
        in_touch_wait_helper = 0x80017B74 <= pc <= 0x80017BE4
        if 0 < stage < len(AUTO_CALIBRATION_TARGETS) * 2 and stage % 2 == 0:
            if self._auto_dialog_ready_locked(pc, progress):
                self.auto_calibration_stage = len(AUTO_CALIBRATION_TARGETS) * 2
                self.auto_calibration_last_stage_step = progress
                stage = self.auto_calibration_stage
        if stage < len(AUTO_CALIBRATION_TARGETS) * 2:
            point_index = stage // 2
            target_x, target_y = AUTO_CALIBRATION_TARGETS[point_index]
            if stage % 2 == 0:
                if self._auto_calibration_press_ready_locked(point_index, pc, in_touch_wait_helper):
                    self.auto_calibration_capture_count = self._auto_calibration_capture_count_locked(point_index)
                    self.emu.set_touch_controller_state(target_x, target_y, True, pc=pc)
                    self.auto_calibration_stage = stage + 1
                    self.auto_calibration_last_stage_step = progress
                return
            if (
                self._auto_calibration_capture_seen_locked(point_index, pc)
                or progress != self.auto_calibration_last_stage_step
            ):
                self.emu.set_touch_controller_state(target_x, target_y, False, pc=pc)
                self.auto_calibration_stage = stage + 1
                self.auto_calibration_last_stage_step = progress
            return
        dialog_x, dialog_y = AUTO_BOOT_DIALOG_X, AUTO_BOOT_DIALOG_Y
        if stage == 8 and self._auto_dialog_ready_locked(pc, progress):
            base_poll = self.emu.touch_controller_poll_hits
            self.emu.touch_controller_events.append(
                ScheduledTouchControllerEvent(
                    x=dialog_x,
                    y=dialog_y,
                    down=True,
                    idle_hit=base_poll + 20,
                )
            )
            self.auto_calibration_stage = 9
            self.auto_calibration_last_stage_step = progress
            self.auto_dialog_press_poll_target = base_poll + 20
            self.auto_dialog_press_trace_count = self._auto_dialog_handler_count_locked()
        elif (
            stage == 9
            and self.emu.touch_controller_poll_hits >= self.auto_dialog_press_poll_target
            and self.emu.touch_down
            and self.emu.touch_x == dialog_x
            and self.emu.touch_y == dialog_y
        ):
            self.auto_calibration_stage = 10
            self.auto_calibration_last_stage_step = progress
        elif stage == 10 and (
            self._auto_dialog_press_handled_locked()
            or progress - self.auto_calibration_last_stage_step >= 500_000
        ):
            if not self._auto_dialog_press_handled_locked():
                self.emu._trace_event("auto-dialog-release-timeout", pc=pc, value=progress)
            self.emu.set_touch_controller_state(dialog_x, dialog_y, False, pc=pc)
            self.auto_calibration_stage = 11
            self.auto_calibration_last_stage_step = progress
        elif stage == 11 and progress != self.auto_calibration_last_stage_step:
            self.auto_calibration_stage = 12
            self.auto_calibration_last_stage_step = progress

    def _auto_calibration_press_ready_locked(self, point_index: int, pc: int, in_touch_wait_helper: bool) -> bool:
        start, end = AUTO_CALIBRATION_PRESS_RANGES[point_index]
        return in_touch_wait_helper or start <= pc <= end

    def _auto_calibration_capture_count_locked(self, point_index: int) -> int:
        assert self.emu is not None
        return int(self.emu.trace_pc_counts.get(AUTO_CALIBRATION_CAPTURE_PCS[point_index], 0))

    def _auto_calibration_capture_seen_locked(self, point_index: int, pc: int) -> bool:
        start, end = AUTO_CALIBRATION_CAPTURE_RANGES[point_index]
        if start <= pc <= end:
            return True
        return self._auto_calibration_capture_count_locked(point_index) > self.auto_calibration_capture_count

    def _auto_dialog_ready_locked(self, pc: int, progress: int) -> bool:
        assert self.emu is not None
        if not self._auto_dialog_frame_like_locked():
            return False
        if pc in AUTO_BOOT_DIALOG_READY_PCS or 0x800A7F00 <= pc <= 0x800A8200:
            return True
        if (
            self.emu.touch_controller_poll_hits >= 20
            and progress != self.auto_calibration_last_stage_step
        ):
            return True
        return False

    def _auto_dialog_frame_like_locked(self) -> bool:
        assert self.emu is not None
        seq = int(getattr(self.emu, "framebuffer_dirty_seq", 0))
        if self.auto_dialog_frame_cache_result is not None and self.auto_dialog_frame_cache_seq == seq:
            return self.auto_dialog_frame_cache_result
        try:
            frame, _rgb = render_rgb565_framebuffer(
                self.emu,
                0xA1F82000,
                0,
                240,
                320,
                240,
                "rgb565",
                self.args.orientation,
            )
        except Exception:
            self.auto_dialog_frame_cache_seq = seq
            self.auto_dialog_frame_cache_result = False
            return False
        nonzero = int(frame.get("nonzero_pixels") or 0)
        unique = int(frame.get("unique_pixel_values") or 0)
        result = 10000 <= nonzero <= 22000 and 10 <= unique <= 220
        self.auto_dialog_frame_cache_seq = seq
        self.auto_dialog_frame_cache_result = result
        return result

    def _auto_dialog_handler_count_locked(self) -> int:
        assert self.emu is not None
        return int(self.emu.trace_pc_counts.get(0x800E0D68, 0))

    def _auto_dialog_press_handled_locked(self) -> bool:
        assert self.emu is not None
        return self._auto_dialog_handler_count_locked() >= self.auto_dialog_press_trace_count + 3

    def _queue_touch(self, x: int, y: int, down: bool) -> dict[str, object]:
        with self.input_lock:
            self.pending_touches.append((max(0, min(239, x)), max(0, min(319, y)), down))
        self._refresh_pending_counts_cached()
        return self.snapshot()

    def _queue_key(self, code: int, down: bool) -> dict[str, object]:
        with self.input_lock:
            self.pending_keys.append((code & 0xFF, down))
        self._refresh_pending_counts_cached()
        return self.snapshot()

    def _apply_pending_input_locked(self) -> None:
        assert self.emu is not None
        with self.input_lock:
            touch = self.pending_touches.popleft() if self.pending_touches else None
            key = self.pending_keys.popleft() if self.pending_keys else None
        if touch is not None:
            x, y, down = touch
            self.emu.set_touch_controller_state(x, y, down)
        if key is not None:
            code, down = key
            hit = self.emu.idle_loop_hits + 1
            if self.args.key_input_mode in {"hardware", "both"}:
                self.emu.set_key_controller_state(code, down)
            if self.args.key_input_mode in {"sampler", "both"}:
                self.emu.firmware_key_samples.append(FirmwareKeySample(code=code if down else 0, idle_hit=hit))

    def step(self, steps: int) -> dict[str, object]:
        with self.lock:
            if self.emu is None:
                self.reset()
            self._apply_pending_input_locked()
            self._apply_auto_calibration_locked()
            self._step_locked(steps)
            self.running = self._worker_alive()
            self._publish_snapshot_locked()
            return self.snapshot()

    def boot(self) -> dict[str, object]:
        return self.step(self.args.boot_steps)

    def _worker_alive(self) -> bool:
        return self.worker is not None and self.worker is not threading.current_thread() and self.worker.is_alive()

    def run_start(self, name: str, total_steps: int, chunk_steps: int) -> dict[str, object]:
        with self.lock:
            if self._worker_alive():
                return self.snapshot()
            self.cancel_run.clear()
            self.job_name = name or "run"
            self.job_total_steps = max(0, total_steps)
            self.job_done_steps = 0
            self.job_chunk_steps = max(1, chunk_steps)
            self.job_started_at = time.time()
            self.job_finished_at = None
            self.running = True
            chunk = max(1, chunk_steps)
            self._publish_snapshot_locked()

        def worker() -> None:
            try:
                while not self.cancel_run.is_set():
                    with self.lock:
                        remaining = self.job_total_steps - self.job_done_steps if self.job_total_steps else chunk
                        if self.emu is None or (self.job_total_steps and remaining <= 0):
                            break
                        run_remaining = min(chunk, remaining) if self.job_total_steps else chunk
                    while run_remaining > 0 and not self.cancel_run.is_set():
                        with self.lock:
                            if self.emu is None:
                                run_remaining = 0
                                break
                            slice_now = min(run_remaining, max(1, self.args.worker_slice_steps))
                            self._apply_pending_input_locked()
                            self._apply_auto_calibration_locked()
                            self._step_locked(
                                slice_now,
                                publish=False,
                                max_seconds=float(getattr(self.args, "worker_slice_seconds", 0.5)),
                            )
                            self.job_done_steps += slice_now
                            run_remaining -= slice_now
                            self._queue_dirty_frame_locked()
                            self._publish_snapshot_locked()
                        time.sleep(0)
            except Exception as exc:
                with self.lock:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    if self.emu is not None:
                        self.emu.state.stop_reason = self.last_error
                    self.cancel_run.set()
            finally:
                with self.lock:
                    self.running = False
                    self.job_finished_at = time.time()
                    self._publish_snapshot_locked()

        self.worker = threading.Thread(target=worker, name=f"hwemu-{name or 'run'}", daemon=True)
        self.worker.start()
        return self.snapshot()

    def stop(self) -> dict[str, object]:
        self.cancel_run.set()
        worker = self.worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=2.0)
        with self.lock:
            self.running = False
            if self.job_name is not None and self.job_finished_at is None:
                self.job_finished_at = time.time()
            self._publish_snapshot_locked()
            return self.snapshot()

    def _coerce_optional_bool(self, value: object) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"", "0", "false", "no", "off"}
        return bool(value)

    def _touch_coordinates_from_message(self, msg: dict[str, object]) -> tuple[int, int]:
        if "display_x" in msg or "display_y" in msg:
            return display_to_touch_point(
                int(msg.get("display_x", 0)),
                int(msg.get("display_y", 0)),
                int(msg.get("display_width", 240)),
                int(msg.get("display_height", 320)),
                self.args.orientation,
            )
        return int(msg.get("x", 0)), int(msg.get("y", 0))

    def key(self, code: int, down: bool = True, advance: bool | None = None) -> dict[str, object]:
        if code not in GPIO_KEY_CODE_BITS:
            return {"error": f"unknown key code {code}", "known": sorted(GPIO_KEY_CODE_BITS)}
        if advance is None:
            advance = not self._worker_alive()
        if not advance:
            return self._queue_key(code, down)
        with self.lock:
            assert self.emu is not None
            hit = self.emu.idle_loop_hits + 1
            if self.args.key_input_mode in {"hardware", "both"}:
                self.emu.set_key_controller_state(code & 0xFF, down)
            if self.args.key_input_mode in {"sampler", "both"}:
                self.emu.firmware_key_samples.append(FirmwareKeySample(code=(code & 0xFF) if down else 0, idle_hit=hit))
        return self.step(self.args.input_steps)

    def touch(self, x: int, y: int, down: bool, advance: bool | None = None) -> dict[str, object]:
        if advance is None:
            advance = not self._worker_alive()
        if not advance:
            return self._queue_touch(x, y, down)
        with self.lock:
            assert self.emu is not None
            self.emu.set_touch_controller_state(
                max(0, min(239, x)),
                max(0, min(319, y)),
                down,
            )
        return self.step(self.args.input_steps)

    def _run_input_worker_if_idle(self) -> dict[str, object]:
        if self._worker_alive():
            return self.snapshot()
        steps = max(1, int(self.args.input_steps))
        chunk = max(1, min(steps, int(self.args.worker_slice_steps)))
        return self.run_start("input", steps, chunk)

    def set_auto_calibration(self, enabled: bool) -> dict[str, object]:
        with self.lock:
            self.args.auto_calibration = bool(enabled)
            if not enabled:
                self.auto_dialog_press_trace_count = 0
                self.auto_dialog_press_poll_target = 0
            self._publish_snapshot_locked()
        return self.snapshot()

    def command(self, msg: dict[str, object]) -> dict[str, object]:
        op = str(msg.get("op", "status"))
        if op == "reset":
            return self.reset()
        if op in {"run-start", "run_start"}:
            return self.run_start(
                str(msg.get("name", "run")),
                int(msg.get("steps", 0)),
                int(msg.get("chunk", 100000)),
            )
        if op == "stop":
            return self.stop()
        if op == "step":
            return self.step(int(msg.get("steps", 250000)))
        if op in {"auto-calibration", "auto_calibration", "set-auto-calibration"}:
            enabled = self._coerce_optional_bool(msg.get("enabled"))
            if enabled is None:
                enabled = not bool(self.args.auto_calibration)
            return self.set_auto_calibration(enabled)
        if op == "key":
            out = self.key(
                int(msg.get("code", 0)),
                self._coerce_optional_bool(msg.get("down")) is not False,
                self._coerce_optional_bool(msg.get("advance")),
            )
            if self._coerce_optional_bool(msg.get("run")) is True:
                return self._run_input_worker_if_idle()
            return out
        if op == "touch":
            x, y = self._touch_coordinates_from_message(msg)
            out = self.touch(
                x,
                y,
                self._coerce_optional_bool(msg.get("down")) is not False,
                self._coerce_optional_bool(msg.get("advance")),
            )
            if self._coerce_optional_bool(msg.get("run")) is True:
                return self._run_input_worker_if_idle()
            return out
        return self.snapshot()

    def logs(self, limit: int = 512) -> dict[str, object]:
        emu = self.emu
        if emu is None:
            return {"count": 0, "limit": limit, "events": []}
        limit = max(1, min(5000, limit))
        events: list[dict[str, str]] = []
        for _ in range(3):
            try:
                events = list(emu.state.events)
                break
            except RuntimeError:
                time.sleep(0)
        return {
            "count": len(events),
            "limit": limit,
            "events": events[-limit:],
        }

    def clear_logs(self) -> dict[str, object]:
        with self.lock:
            assert self.emu is not None
            removed = len(self.emu.state.events)
            self.emu.state.events.clear()
            self._publish_snapshot_locked()
            return {"cleared": removed}

    def dump_frame(self) -> bytes:
        now = time.time()
        cached = self.cached_frame_bytes
        if cached is not None and now - self.cached_frame_time < 0.25:
            return cached
        with self.lock:
            self._render_current_frame_locked()
            self._publish_snapshot_locked()
            return self.cached_frame_bytes

    def _build_snapshot_locked(self) -> dict[str, object]:
        assert self.emu is not None
        state = self.emu.state
        worker_alive = self._worker_alive()
        active = self.running or worker_alive
        now = time.time()
        reset_elapsed = max(0.0, now - self.reset_at)
        job = None
        if self.job_name is not None:
            started_at = self.job_started_at
            finished_at = self.job_finished_at
            elapsed = None
            if started_at is not None:
                elapsed = (finished_at if finished_at is not None else now) - started_at
            steps_per_second = None
            if elapsed is not None and elapsed > 0:
                steps_per_second = self.job_done_steps / elapsed
            continuous = self.job_total_steps == 0
            if active:
                job_status = "running"
            elif not continuous and self.job_done_steps >= self.job_total_steps:
                job_status = "completed"
            elif finished_at is not None:
                job_status = "stopped"
            else:
                job_status = "idle"
            job = {
                "name": self.job_name,
                "mode": "continuous" if continuous else "finite",
                "status": job_status,
                "total_steps": self.job_total_steps,
                "done_steps": self.job_done_steps,
                "chunk_steps": self.job_chunk_steps,
                "active": active,
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed_seconds": None if elapsed is None else max(0.0, elapsed),
                "steps_per_second": steps_per_second,
            }
        return {
            "running": active,
            "boot_mode": self.args.boot_mode,
            "orientation": self.args.orientation,
            "reset_at": self.reset_at,
            "reset_elapsed_seconds": reset_elapsed,
            "emulator_elapsed_seconds": reset_elapsed,
            "run_started_at": self.job_started_at,
            "run_finished_at": self.job_finished_at,
            "run_elapsed_seconds": None if job is None else job["elapsed_seconds"],
            "run_steps_per_second": None if job is None else job["steps_per_second"],
            "fast_hooks": not self.args.slow_global_code_hook,
            "resource_cache16": self.args.resource_cache16_accelerator,
            "key_input_mode": self.args.key_input_mode,
            "auto_calibration": self.args.auto_calibration,
            "auto_calibration_stage": self.auto_calibration_stage,
            "auto_calibration_stage_label": AUTO_BOOT_STAGE_LABELS.get(
                self.auto_calibration_stage,
                str(self.auto_calibration_stage),
            ),
            "pending_touches": self._pending_touch_count_locked(),
            "pending_keys": self._pending_key_count_locked(),
            "busy_delay_accel": self.emu.busy_delay_accel_count,
            "ftl_scan_accel": self.emu.ftl_scan_accel_count,
            "cache_scan_tail_accel": getattr(self.emu, "cache_scan_tail_accel_count", 0),
            "suppressed_hot_events": self.emu.suppressed_hot_event_count,
            "no_event_poll_accel": self.emu.no_event_poll_accel_count,
            "job": job,
            "stop_reason": self.last_error or state.stop_reason,
            "insn_count": state.insn_count,
            "pc": f"0x{self.emu.pc:08x}",
            "last_pc": f"0x{state.last_pc:08x}",
            "idle_loop_hits": self.emu.idle_loop_hits,
            "app_idle_loop_hits": self.emu.app_idle_loop_hits,
            "events": list(state.events)[-16:],
            "invalid": [access_to_dict(a) for a in state.invalid[-4:]],
            "scheduler": self.emu.scheduler_snapshot(),
            "framebuffer": self.last_frame,
            "framebuffer_dirty_seq": getattr(self.emu, "framebuffer_dirty_seq", 0),
            "framebuffer_dirty_last": self.emu._framebuffer_dirty_last_snapshot(),
            "queued_frames": self.queued_frame_count(),
            "status_cached_at": time.time(),
        }

    def _publish_snapshot_locked(self) -> None:
        with self.status_lock:
            self.cached_status = self._build_snapshot_locked()

    def snapshot(self) -> dict[str, object]:
        with self.status_lock:
            return dict(self.cached_status)


