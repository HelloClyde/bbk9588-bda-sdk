"""Frontend emulator state and input/frame queues for the BBK 9588 web UI."""

from __future__ import annotations

import argparse
import cProfile
import pstats
import struct
import subprocess
import threading
import time
import traceback
from collections import deque
from itertools import islice
from pathlib import Path

from unicorn.mips_const import (
    UC_MIPS_REG_2,
    UC_MIPS_REG_4,
    UC_MIPS_REG_5,
    UC_MIPS_REG_29,
    UC_MIPS_REG_31,
    UC_MIPS_REG_PC,
)

from emu.core import Bbk9588HwEmu
from emu.core.defs import ScheduledCall
from emu.core.defs import GPIO_KEY_CODE_BITS, RAM_BASE, ScheduledTouchControllerEvent, TOUCH_CALIBRATION_REFERENCE_POINTS
from emu.core.framebuffer import png_bytes_from_rgb, render_rgb565_framebuffer, rgb565_raw_to_info_rgb
from emu.tools.utils import access_to_dict, find_workspace_file


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
FAT_IMAGE = BUILD / "bbk9588_fs_fat16.img"
COMBINED_NAND_IMAGE = BUILD / "bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin"
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
LIVE_FRAMEBUFFER_ADDR = 0xA1F82000
LIVE_FRAMEBUFFER_OFFSET_BYTES = 0
LIVE_FRAMEBUFFER_WIDTH = 240
LIVE_FRAMEBUFFER_HEIGHT = 320
LIVE_FRAMEBUFFER_STRIDE_PIXELS = 240
LIVE_FRAMEBUFFER_FORMAT = "rgb565"
LIVE_FRAMEBUFFER_RAW_BYTES = LIVE_FRAMEBUFFER_STRIDE_PIXELS * LIVE_FRAMEBUFFER_HEIGHT * 2
WS_RAW_FRAME_MAGIC = b"BBKRAW1\0"
WS_RAW_FRAME_FORMAT_RGB565 = 1
WS_RAW_FRAME_HEADER = struct.Struct("<8sIHHHH")
WS_RAW_FRAME_HEADER_SIZE = WS_RAW_FRAME_HEADER.size
DEFERRED_FRAME_ALWAYS_REPLACE_REASONS = frozenset(
    {
        "lcd-mirror",
        "logo-strip-blit",
        "fullscreen-fill",
        "boot-frame-copy",
        "portrait-blit",
        "surface-block-write",
        "surface-transparent-blit",
    }
)


def deque_tail(items, limit: int) -> list[object]:
    limit = max(0, int(limit))
    if limit == 0:
        return []
    for _ in range(3):
        try:
            length = len(items)
            start = max(0, length - limit)
            return list(islice(items, start, length))
        except RuntimeError:
            time.sleep(0)
    return []


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
        self.crash_snapshot: dict[str, object] | None = None
        self.last_frame: dict[str, object] | None = None
        self.running = False
        self.job_name: str | None = None
        self.job_total_steps = 0
        self.job_done_steps = 0
        self.job_chunk_steps = 0
        self.job_last_slice_steps = 0
        self.job_last_slice_timed_out = False
        self.job_start_insn_count = 0
        self.job_observed_insn_delta = 0
        self.job_started_at: float | None = None
        self.job_finished_at: float | None = None
        self.input_worker_pending = False
        self.input_wake_count = 0
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
        self.cached_ws_frame_bytes: bytes | None = None
        self.cached_ws_frame_time = 0.0
        self.last_queued_frame_seq = -1
        self.frame_push_min_interval = max(0.0, float(getattr(args, "frame_push_min_interval", 0.04)))
        self.frame_push_last_time = 0.0
        self.frame_push_hook_count = 0
        self.frame_push_queued_count = 0
        self.frame_push_throttle_count = 0
        self.frame_push_deferred_count = 0
        self.frame_push_replace_count = 0
        self.frame_push_drop_count = 0
        self.frame_push_error_count = 0
        self.ws_frame_sent_count = 0
        self.ws_frame_sent_bytes = 0
        self.ws_frame_last_seq: int | None = None
        self.ws_frame_last_kind = ""
        self.ws_frame_last_bytes = 0
        self.ws_frame_last_sent_at = 0.0
        self.frame_info_min_interval = max(0.0, float(getattr(args, "frame_info_min_interval", 1.0)))
        self.frame_info_last_time = 0.0
        self.frame_info_update_count = 0
        self.frame_queue_lock = threading.RLock()
        self.frame_queue: deque[bytes] = deque(maxlen=120)
        self.raw_frame_queue: deque[tuple[int, float, bytes | None]] = deque(maxlen=8)
        self.deferred_raw_frame: tuple[float, tuple[int, float, bytes | None]] | None = None
        self.frontend_activity_condition = threading.Condition()
        self.frontend_activity_seq = 0
        self.ws_command_count = 0
        self.ws_last_command_op = ""
        self.ws_last_command_seq: object | None = None
        self.ws_last_command_at = 0.0
        self.ws_reader_alive = False
        self.ws_reader_heartbeat = 0.0
        self.input_lock = threading.RLock()
        self.pending_touches: deque[tuple[int, int, bool]] = deque(maxlen=32)
        self.pending_keys: deque[tuple[int, bool]] = deque(maxlen=32)
        self.reset_at = time.time()
        self.reset()

    def _ensure_fat_image(self) -> Path | None:
        if FAT_IMAGE.exists():
            return FAT_IMAGE
        maker = ROOT / "emu" / "tools" / "make_fat16_image.py"
        system_dir = ROOT / "绯荤粺"
        app_dir = ROOT / "搴旂敤"
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
        emu = self.emu
        if emu is not None:
            try:
                emu.uc.emu_stop()
            except Exception:
                pass
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
            auto_boot_trace_pcs = (
                AUTO_BOOT_TRACE_PCS
                if self.args.auto_calibration and self.args.boot_mode == "c200" and self.args.state_in is None
                else ()
            )
            trace_pcs = tuple(dict.fromkeys([*auto_boot_trace_pcs, *getattr(self.args, "trace_pc", [])]))
            scheduled_calls = []
            for item in getattr(self.args, "scheduled_call", []) or []:
                if isinstance(item, ScheduledCall):
                    scheduled_calls.append(item)
                else:
                    va, args, idle_hit = item
                    scheduled_calls.append(ScheduledCall(va=int(va), args=tuple(args), idle_hit=int(idle_hit)))
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
                readonly_nand_page_ranges=list(getattr(self.args, "readonly_nand_page_range", []) or []),
                scheduler_tick_clamp=self.args.scheduler_tick_clamp,
                fast_hooks=not self.args.slow_global_code_hook,
                nand_loop_accelerator=self.args.nand_loop_accelerator,
                resource_cache16_accelerator=self.args.resource_cache16_accelerator,
                glyph_mask_accelerator=not getattr(self.args, "no_glyph_mask_accelerator", False),
                cp0_status_accelerator=not getattr(self.args, "no_cp0_status_accelerator", False),
                trace_pcs=trace_pcs,
                trace_pc_detail=bool(getattr(self.args, "trace_pc_detail", False)),
                scheduled_calls=scheduled_calls,
                completed_step_timer=bool(getattr(self.args, "completed_step_timer", False)),
                suppress_hot_events=True,
                hot_path_stats=bool(getattr(self.args, "hot_path_stats", False)),
                block_hook=bool(getattr(self.args, "hot_path_stats", False)),
                run_internal_chunk_steps=getattr(self.args, "run_internal_chunk_steps", None),
            )
            self.emu.framebuffer_dirty_callback = self._on_framebuffer_dirty
            if self.args.state_in is not None:
                self.emu.load_emulator_state(self.args.state_in)
            for spec in getattr(self.args, "mem_write_hex", []) or []:
                if ":" not in spec:
                    raise ValueError("--mem-write-hex must be va:hexbytes")
                va_text, hex_text = spec.split(":", 1)
                data = bytes.fromhex(hex_text)
                va = int(va_text, 0)
                self.emu.uc.mem_write(va & 0x1FFFFFFF if va >= 0x80000000 else va, data)
            self.last_error = None
            self.crash_snapshot = None
            self.last_frame = None
            self.running = False
            self.job_name = None
            self.job_total_steps = 0
            self.job_done_steps = 0
            self.job_chunk_steps = 0
            self.job_last_slice_steps = 0
            self.job_last_slice_timed_out = False
            self.job_start_insn_count = 0
            self.job_observed_insn_delta = 0
            self.job_started_at = None
            self.job_finished_at = None
            self.input_worker_pending = False
            self.input_wake_count = 0
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
            self.cached_ws_frame_bytes = None
            self.cached_ws_frame_time = 0.0
            self.last_queued_frame_seq = -1
            self.frame_push_last_time = 0.0
            self.frame_push_hook_count = 0
            self.frame_push_queued_count = 0
            self.frame_push_throttle_count = 0
            self.frame_push_deferred_count = 0
            self.frame_push_replace_count = 0
            self.frame_push_drop_count = 0
            self.frame_push_error_count = 0
            self.ws_frame_sent_count = 0
            self.ws_frame_sent_bytes = 0
            self.ws_frame_last_seq = None
            self.ws_frame_last_kind = ""
            self.ws_frame_last_bytes = 0
            self.ws_frame_last_sent_at = 0.0
            self.frame_info_last_time = 0.0
            self.frame_info_update_count = 0
            self.ws_command_count = 0
            self.ws_last_command_op = ""
            self.ws_last_command_seq = None
            self.ws_last_command_at = 0.0
            with self.frame_queue_lock:
                self.frame_queue.clear()
                self.raw_frame_queue.clear()
                self.deferred_raw_frame = None
            with self.input_lock:
                self.pending_touches.clear()
                self.pending_keys.clear()
            self._publish_snapshot_locked()
            return self.snapshot()

    def _render_current_frame_locked(self) -> bytes:
        assert self.emu is not None
        self.last_frame, rgb = render_rgb565_framebuffer(
            self.emu,
            LIVE_FRAMEBUFFER_ADDR,
            LIVE_FRAMEBUFFER_OFFSET_BYTES,
            LIVE_FRAMEBUFFER_WIDTH,
            LIVE_FRAMEBUFFER_HEIGHT,
            LIVE_FRAMEBUFFER_STRIDE_PIXELS,
            LIVE_FRAMEBUFFER_FORMAT,
            self.args.orientation,
        )
        frame = png_bytes_from_rgb(
            int(self.last_frame["output_width"]),
            int(self.last_frame["output_height"]),
            rgb,
        )
        now = time.time()
        self.frame_info_last_time = now
        self.frame_info_update_count += 1
        self.cached_frame_bytes = frame
        self.cached_frame_time = now
        return frame

    def _capture_framebuffer_raw_locked(self) -> bytes:
        assert self.emu is not None
        phys = (
            LIVE_FRAMEBUFFER_ADDR & 0x1FFFFFFF
            if LIVE_FRAMEBUFFER_ADDR >= RAM_BASE
            else LIVE_FRAMEBUFFER_ADDR
        ) + LIVE_FRAMEBUFFER_OFFSET_BYTES
        return bytes(self.emu.uc.mem_read(phys, LIVE_FRAMEBUFFER_RAW_BYTES))

    def _png_from_raw_frame(self, raw_frame: tuple[int, float, bytes]) -> bytes:
        seq, captured_at, raw = raw_frame
        info, rgb = rgb565_raw_to_info_rgb(
            raw,
            LIVE_FRAMEBUFFER_ADDR,
            LIVE_FRAMEBUFFER_OFFSET_BYTES,
            LIVE_FRAMEBUFFER_WIDTH,
            LIVE_FRAMEBUFFER_HEIGHT,
            LIVE_FRAMEBUFFER_STRIDE_PIXELS,
            LIVE_FRAMEBUFFER_FORMAT,
            self.args.orientation,
        )
        info["dirty_seq"] = seq
        info["captured_at"] = captured_at
        frame = png_bytes_from_rgb(
            int(info["output_width"]),
            int(info["output_height"]),
            rgb,
        )
        now = time.time()
        self.last_frame = info
        self.frame_info_last_time = now
        self.frame_info_update_count += 1
        self.cached_frame_bytes = frame
        self.cached_frame_time = now
        return frame

    def _info_from_raw_frame(self, raw_frame: tuple[int, float, bytes]) -> dict[str, object]:
        seq, captured_at, raw = raw_frame
        width = LIVE_FRAMEBUFFER_WIDTH
        height = LIVE_FRAMEBUFFER_HEIGHT
        stride_pixels = LIVE_FRAMEBUFFER_STRIDE_PIXELS
        nonzero = 0
        unique: set[int] = set()
        min_x = width
        min_y = height
        max_x = -1
        max_y = -1
        required = stride_pixels * height * 2
        if len(raw) < required:
            raise ValueError("raw framebuffer is shorter than expected")
        for y in range(height):
            row = y * stride_pixels * 2
            for x in range(width):
                i = row + x * 2
                px = raw[i] | (raw[i + 1] << 8)
                unique.add(px)
                if px:
                    nonzero += 1
                    if x < min_x:
                        min_x = x
                    if y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y
        if self.args.orientation in {"cw90", "ccw90"}:
            output_width, output_height = height, width
        else:
            output_width, output_height = width, height
        bbox = None if max_x < 0 else [min_x, min_y, max_x, max_y]
        return {
            "addr": f"0x{LIVE_FRAMEBUFFER_ADDR:08x}",
            "offset_bytes": LIVE_FRAMEBUFFER_OFFSET_BYTES,
            "format": LIVE_FRAMEBUFFER_FORMAT,
            "width": width,
            "height": height,
            "stride_pixels": stride_pixels,
            "orientation": self.args.orientation,
            "output_width": output_width,
            "output_height": output_height,
            "nonzero_pixels": nonzero,
            "unique_pixel_values": len(unique),
            "nonzero_bbox": bbox,
            "dirty_seq": seq,
            "captured_at": captured_at,
        }

    def _maybe_update_last_frame_info(self, raw_frame: tuple[int, float, bytes], *, force: bool = False) -> None:
        seq, captured_at, _raw = raw_frame
        now = time.time()
        if (
            force
            or self.last_frame is None
            or now - self.frame_info_last_time >= self.frame_info_min_interval
        ):
            self.last_frame = self._info_from_raw_frame(raw_frame)
            self.frame_info_last_time = now
            self.frame_info_update_count += 1
        elif self.last_frame is not None:
            self.last_frame = dict(self.last_frame)
            self.last_frame["dirty_seq"] = seq
            self.last_frame["captured_at"] = captured_at

    def _ws_payload_from_raw_frame(self, raw_frame: tuple[int, float, bytes]) -> bytes:
        seq, _captured_at, raw = raw_frame
        self._maybe_update_last_frame_info(raw_frame)
        payload = raw[:LIVE_FRAMEBUFFER_RAW_BYTES]
        frame = WS_RAW_FRAME_HEADER.pack(
            WS_RAW_FRAME_MAGIC,
            seq & 0xFFFFFFFF,
            LIVE_FRAMEBUFFER_WIDTH,
            LIVE_FRAMEBUFFER_HEIGHT,
            LIVE_FRAMEBUFFER_STRIDE_PIXELS,
            WS_RAW_FRAME_FORMAT_RGB565,
        ) + payload
        self.cached_ws_frame_bytes = frame
        self.cached_ws_frame_time = time.time()
        return frame

    def _realize_raw_frame(self, raw_frame: tuple[int, float, bytes | None]) -> tuple[int, float, bytes]:
        seq, captured_at, raw = raw_frame
        if raw is None:
            captured_at = time.time()
            raw = self._capture_framebuffer_raw_locked()
        return seq, captured_at, raw

    def _queue_raw_frame_locked(self, seq: int, captured_at: float, *, capture_now: bool = True) -> bool:
        raw = self._capture_framebuffer_raw_locked() if capture_now else None
        with self.frame_queue_lock:
            raw_maxlen = self.raw_frame_queue.maxlen
            if raw_maxlen is not None and len(self.raw_frame_queue) >= raw_maxlen:
                self.raw_frame_queue.popleft()
                self.frame_push_drop_count += 1
            self.raw_frame_queue.append((seq, captured_at, raw))
            self.deferred_raw_frame = None
        self.last_queued_frame_seq = seq
        self.frame_push_last_time = captured_at
        self.frame_push_queued_count += 1
        self._notify_frontend_activity()
        return True

    def _defer_raw_frame_locked(
        self,
        seq: int,
        captured_at: float,
        due_at: float,
        *,
        reason: str = "",
    ) -> bool:
        replace_existing = reason in DEFERRED_FRAME_ALWAYS_REPLACE_REASONS
        with self.frame_queue_lock:
            existing = self.deferred_raw_frame
            if existing is not None and not replace_existing:
                return False
            if existing is not None:
                due_at = existing[0]
            if self.deferred_raw_frame is None:
                self.deferred_raw_frame = (due_at, (seq, captured_at, None))
                self.frame_push_deferred_count += 1
                self._notify_frontend_activity()
                return True
            if replace_existing:
                existing_due_at, _existing = self.deferred_raw_frame
                self.deferred_raw_frame = (existing_due_at, (seq, captured_at, None))
                self.frame_push_replace_count += 1
                self._notify_frontend_activity()
                return True
        return False

    def _queue_dirty_frame_locked(self, *, force: bool = False) -> bool:
        if self.emu is None:
            return False
        seq = int(getattr(self.emu, "framebuffer_dirty_seq", 0))
        if not force and seq == 0:
            return False
        if not force and seq == self.last_queued_frame_seq:
            return False
        try:
            return self._queue_raw_frame_locked(seq, time.time(), capture_now=True)
        except Exception:
            self.frame_push_error_count += 1
            return False

    def _on_framebuffer_dirty(self, seq: int, pc: int, addr: int, size: int, reason: str) -> None:
        if self.emu is None:
            return
        self.frame_push_hook_count += 1
        now = time.time()
        if seq == self.last_queued_frame_seq:
            return
        if now - self.frame_push_last_time < self.frame_push_min_interval:
            self.frame_push_throttle_count += 1
            try:
                self._defer_raw_frame_locked(
                    seq,
                    now,
                    self.frame_push_last_time + self.frame_push_min_interval,
                    reason=reason,
                )
            except Exception:
                self.frame_push_error_count += 1
            return
        try:
            self._queue_raw_frame_locked(seq, now, capture_now=False)
        except Exception:
            self.frame_push_error_count += 1

    def pop_queued_frame(self) -> bytes | None:
        now = time.time()
        with self.frame_queue_lock:
            if self.frame_queue:
                return self.frame_queue.popleft()
            raw_frame = self.raw_frame_queue.popleft() if self.raw_frame_queue else None
            if raw_frame is None and self.deferred_raw_frame is not None:
                due_at, deferred = self.deferred_raw_frame
                if now >= due_at:
                    raw_frame = deferred
                    self.deferred_raw_frame = None
                    self.last_queued_frame_seq = deferred[0]
                    self.frame_push_last_time = now
        if raw_frame is None:
            return None
        try:
            raw_frame = self._realize_raw_frame(raw_frame)
            return self._png_from_raw_frame(raw_frame)
        except Exception:
            self.frame_push_error_count += 1
            return None

    def pop_queued_ws_frame(self) -> bytes | None:
        now = time.time()
        with self.frame_queue_lock:
            if self.frame_queue:
                return self.frame_queue.popleft()
            raw_frame = self.raw_frame_queue.popleft() if self.raw_frame_queue else None
            if raw_frame is None and self.deferred_raw_frame is not None:
                due_at, deferred = self.deferred_raw_frame
                if now >= due_at:
                    raw_frame = deferred
                    self.deferred_raw_frame = None
                    self.last_queued_frame_seq = deferred[0]
                    self.frame_push_last_time = now
        if raw_frame is None:
            return None
        try:
            raw_frame = self._realize_raw_frame(raw_frame)
            return self._ws_payload_from_raw_frame(raw_frame)
        except Exception:
            self.frame_push_error_count += 1
            return None

    def pop_latest_queued_frame(self) -> bytes | None:
        now = time.time()
        with self.frame_queue_lock:
            raw_frame = self.raw_frame_queue.pop() if self.raw_frame_queue else None
            self.raw_frame_queue.clear()
            frame = self.frame_queue.pop() if raw_frame is None and self.frame_queue else None
            self.frame_queue.clear()
            if raw_frame is None and frame is None and self.deferred_raw_frame is not None:
                due_at, deferred = self.deferred_raw_frame
                if now >= due_at:
                    raw_frame = deferred
                    self.deferred_raw_frame = None
                    self.last_queued_frame_seq = deferred[0]
                    self.frame_push_last_time = now
        if raw_frame is None:
            return frame
        try:
            raw_frame = self._realize_raw_frame(raw_frame)
            return self._png_from_raw_frame(raw_frame)
        except Exception:
            self.frame_push_error_count += 1
            return None

    def pop_latest_queued_ws_frame(self) -> bytes | None:
        now = time.time()
        with self.frame_queue_lock:
            raw_frame = self.raw_frame_queue.pop() if self.raw_frame_queue else None
            self.raw_frame_queue.clear()
            frame = self.frame_queue.pop() if raw_frame is None and self.frame_queue else None
            self.frame_queue.clear()
            if raw_frame is None and frame is None and self.deferred_raw_frame is not None:
                due_at, deferred = self.deferred_raw_frame
                if now >= due_at:
                    raw_frame = deferred
                    self.deferred_raw_frame = None
                    self.last_queued_frame_seq = deferred[0]
                    self.frame_push_last_time = now
        if raw_frame is None:
            return frame
        try:
            raw_frame = self._realize_raw_frame(raw_frame)
            return self._ws_payload_from_raw_frame(raw_frame)
        except Exception:
            self.frame_push_error_count += 1
            return None

    def record_ws_frame_sent(self, payload: bytes) -> None:
        seq: int | None = None
        kind = "unknown"
        if payload.startswith(WS_RAW_FRAME_MAGIC) and len(payload) >= WS_RAW_FRAME_HEADER_SIZE:
            try:
                _magic, seq_value, _width, _height, _stride, _format = WS_RAW_FRAME_HEADER.unpack(
                    payload[:WS_RAW_FRAME_HEADER_SIZE]
                )
                seq = int(seq_value)
                kind = "raw-rgb565"
            except Exception:
                kind = "raw-rgb565"
        elif payload.startswith(b"\x89PNG\r\n\x1a\n"):
            kind = "png"
        with self.status_lock:
            self.ws_frame_sent_count += 1
            self.ws_frame_sent_bytes += len(payload)
            self.ws_frame_last_seq = seq
            self.ws_frame_last_kind = kind
            self.ws_frame_last_bytes = len(payload)
            self.ws_frame_last_sent_at = time.time()

    def dump_ws_frame(self) -> bytes:
        with self.lock:
            assert self.emu is not None
            seq = int(getattr(self.emu, "framebuffer_dirty_seq", 0))
            raw_frame = (seq, time.time(), self._capture_framebuffer_raw_locked())
            frame = self._ws_payload_from_raw_frame(raw_frame)
            self._publish_snapshot_locked()
            return frame

    def queued_frame_count(self) -> int:
        with self.frame_queue_lock:
            deferred = 1 if self.deferred_raw_frame is not None else 0
            return len(self.frame_queue) + len(self.raw_frame_queue) + deferred

    def seconds_until_deferred_frame(self) -> float | None:
        with self.frame_queue_lock:
            if self.deferred_raw_frame is None:
                return None
            due_at, _deferred = self.deferred_raw_frame
        return max(0.0, due_at - time.time())

    def cached_frame(self) -> bytes | None:
        return self.cached_frame_bytes

    def cached_ws_frame(self) -> bytes | None:
        return self.cached_ws_frame_bytes

    def _native_bda_event_probe_locked(self) -> dict[str, object]:
        assert self.emu is not None

        def u32(va: int) -> str | None:
            value = self.emu._read_u32_va_safe(va)
            return None if value is None else f"0x{value:08x}"

        def block_words(va: int, size: int) -> list[str] | None:
            data = self.emu._read_block_va_safe(va, size)
            if data is None:
                return None
            return [
                f"0x{struct.unpack_from('<I', data, off)[0]:08x}"
                for off in range(0, len(data) & ~3, 4)
            ]

        return {
            # Shared game BDA event globals observed in Thunder/Tank-style
            # GUI+0x030 -> GUI+0x050/+0x054 polling loops.
            "game_event_word_81c17598": u32(0x81C17598),
            "game_event_word_81c1759c": u32(0x81C1759C),
            "game_event_word_81c175a0": u32(0x81C175A0),
            "game_event_words_81c17590": block_words(0x81C17590, 0x30),
            "thunder_sound_chunk_count_81c16a90": u32(0x81C16A90),
            "thunder_sound_selected_81c16a94": u32(0x81C16A94),
            "thunder_sound_active_81c16d40": u32(0x81C16D40),
            "thunder_sound_ready_81c16d44": u32(0x81C16D44),
            "thunder_plane_index_81c16c14": u32(0x81C16C14),
            "thunder_plane_confirmed_81c16c2c": u32(0x81C16C2C),
            "thunder_transition_flag_81c16c34": u32(0x81C16C34),
            "gui_queue_flags_80825840": u32(0x80825840),
            "gui_ring_buffer_80825850": u32(0x80825850),
            "gui_ring_capacity_80825854": u32(0x80825854),
            "gui_ring_read_80825858": u32(0x80825858),
            "gui_ring_write_8082585c": u32(0x8082585C),
            "active_object_80474048": u32(0x80474048),
            "active_object_8047404c": u32(0x8047404C),
            "active_object_80474050": u32(0x80474050),
            "key_down_codes": sorted(getattr(self.emu, "key_down_codes", [])),
            "key_controller_event_log_tail": list(getattr(self.emu, "key_controller_event_log", [])[-16:]),
            "recent_gpio_accesses_tail": list(getattr(self.emu, "recent_gpio_accesses", [])[-16:]),
            "recent_intc_accesses_tail": list(getattr(self.emu, "recent_intc_accesses", [])[-16:]),
        }

    def _notify_frontend_activity(self) -> None:
        with self.frontend_activity_condition:
            self.frontend_activity_seq += 1
            self.frontend_activity_condition.notify_all()

    def notify_frontend_activity(self) -> None:
        self._notify_frontend_activity()

    def frontend_activity_sequence(self) -> int:
        with self.frontend_activity_condition:
            return self.frontend_activity_seq

    def wait_for_frontend_activity(self, last_seq: int, timeout: float) -> int:
        timeout = max(0.0, float(timeout))
        with self.frontend_activity_condition:
            if self.frontend_activity_seq == last_seq and timeout > 0:
                self.frontend_activity_condition.wait(timeout)
            return self.frontend_activity_seq

    def record_ws_command(self, op: str, command_seq: object | None = None) -> None:
        self.ws_command_count += 1
        self.ws_last_command_op = op
        self.ws_last_command_seq = command_seq
        self.ws_last_command_at = time.time()
        with self.status_lock:
            ws = self.cached_status.get("ws") if isinstance(self.cached_status, dict) else None
            if isinstance(ws, dict):
                ws["command_count"] = self.ws_command_count
                ws["last_op"] = self.ws_last_command_op
                ws["last_seq"] = self.ws_last_command_seq
                ws["last_command_at"] = self.ws_last_command_at

    def set_ws_reader_alive(self, alive: bool) -> None:
        self.ws_reader_alive = bool(alive)
        self.ws_reader_heartbeat = time.time()
        with self.status_lock:
            ws = self.cached_status.get("ws") if isinstance(self.cached_status, dict) else None
            if isinstance(ws, dict):
                ws["reader_alive"] = self.ws_reader_alive
                ws["reader_heartbeat"] = self.ws_reader_heartbeat

    def worker_active(self) -> bool:
        return self._worker_alive()

    def _step_locked(
        self,
        steps: int,
        publish: bool = True,
        max_seconds: float | None = None,
        *,
        clear_stop_reason: bool = True,
    ) -> int:
        assert self.emu is not None
        self.running = True
        if clear_stop_reason:
            self.emu.state.stop_reason = None
        completed_steps = 0
        try:
            self.emu.run(max(1, steps), max_seconds=max_seconds, timeout_is_stop=max_seconds is None)
            completed_steps = int(getattr(self.emu, "last_run_completed_steps", 0))
            self.last_error = None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.emu.state.stop_reason = self.last_error
            self._capture_crash_snapshot_locked(self.last_error, traceback.format_exc())
            self.cancel_run.set()
        finally:
            if publish:
                self._publish_snapshot_locked()
        return completed_steps

    def _capture_crash_snapshot_locked(self, reason: str, traceback_text: str | None = None) -> None:
        if self.crash_snapshot is not None or self.emu is None:
            return
        emu = self.emu
        registers: dict[str, str] = {}
        for name, reg in (
            ("pc", UC_MIPS_REG_PC),
            ("v0", UC_MIPS_REG_2),
            ("a0", UC_MIPS_REG_4),
            ("a1", UC_MIPS_REG_5),
            ("sp", UC_MIPS_REG_29),
            ("ra", UC_MIPS_REG_31),
        ):
            try:
                registers[name] = f"0x{emu.uc.reg_read(reg) & 0xFFFFFFFF:08x}"
            except Exception as exc:
                registers[name] = f"<{type(exc).__name__}: {exc}>"
        self.crash_snapshot = {
            "reason": reason,
            "traceback": traceback_text,
            "captured_at": time.time(),
            "job": {
                "name": self.job_name,
                "total_steps": self.job_total_steps,
                "done_steps": self.job_done_steps,
                "chunk_steps": self.job_chunk_steps,
                "last_slice_steps": self.job_last_slice_steps,
                "last_slice_timed_out": self.job_last_slice_timed_out,
            },
            "pc": f"0x{emu.pc:08x}",
            "last_pc": f"0x{emu.state.last_pc:08x}",
            "insn_count": int(emu.state.insn_count),
            "registers": registers,
            "pending_touches": self._pending_touch_count_locked(),
            "pending_keys": self._pending_key_count_locked(),
            "events": deque_tail(emu.state.events, 64),
            "invalid": [access_to_dict(a) for a in emu.state.invalid[-8:]],
            "scheduler": emu.scheduler_snapshot_compact(),
        }

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

    def _update_job_observed_locked(self) -> int:
        assert self.emu is not None
        self.job_observed_insn_delta = max(0, int(self.emu.state.insn_count) - int(self.job_start_insn_count))
        return self.job_observed_insn_delta

    def _auto_progress_locked(self) -> int:
        assert self.emu is not None
        if self.job_started_at is not None:
            return max(int(self.job_done_steps), self._update_job_observed_locked())
        return int(self.emu.state.insn_count)

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
            self._maybe_enable_completed_step_timer_after_auto_boot_locked()

    def _maybe_enable_completed_step_timer_after_auto_boot_locked(self) -> None:
        if self.emu is None:
            return
        if not bool(getattr(self.args, "completed_step_timer_after_auto_boot", False)):
            return
        if not self.args.auto_calibration or self.args.boot_mode != "c200":
            return
        if self.auto_calibration_stage < 12:
            return
        if getattr(self.emu, "completed_step_timer", False):
            return
        self.emu._set_completed_step_timer_source(
            True,
            pc=self.emu.pc & 0xFFFFFFFF,
            reason="auto-boot",
        )

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
                LIVE_FRAMEBUFFER_ADDR,
                LIVE_FRAMEBUFFER_OFFSET_BYTES,
                LIVE_FRAMEBUFFER_WIDTH,
                LIVE_FRAMEBUFFER_HEIGHT,
                LIVE_FRAMEBUFFER_STRIDE_PIXELS,
                LIVE_FRAMEBUFFER_FORMAT,
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
        self._wake_worker_for_input()
        return self.snapshot()

    def _queue_key(self, code: int, down: bool) -> dict[str, object]:
        with self.input_lock:
            self.pending_keys.append((code & 0xFF, down))
        self._refresh_pending_counts_cached()
        self._wake_worker_for_input()
        return self.snapshot()

    def _wake_worker_for_input(self) -> None:
        worker = self.worker
        emu = self.emu
        if emu is None or worker is None or worker is threading.current_thread() or not worker.is_alive():
            return
        try:
            emu.internal_chunk_stop = True
            emu.uc.emu_stop()
            self.input_wake_count += 1
            with self.status_lock:
                if self.cached_status:
                    self.cached_status["input_wake_count"] = self.input_wake_count
        except Exception:
            pass

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
            self.emu.set_key_controller_state(code, down)

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

    def save_checkpoint(self, path: Path) -> dict[str, object]:
        with self.lock:
            if self.emu is None:
                self.reset()
            assert self.emu is not None
            self.emu.save_emulator_state(path)
            self._publish_snapshot_locked()
            snap = self.snapshot()
            snap["checkpoint"] = str(path)
            return snap

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
            self.job_last_slice_steps = 0
            self.job_last_slice_timed_out = False
            self.job_start_insn_count = int(self.emu.state.insn_count) if self.emu is not None else 0
            self.job_observed_insn_delta = 0
            self.job_started_at = time.time()
            self.job_finished_at = None
            self.running = True
            if self.emu is not None and self.crash_snapshot is None:
                self.emu.state.stop_reason = None
                self.last_error = None
            chunk = max(1, chunk_steps)
            self._publish_snapshot_locked()

        def worker() -> None:
            profiler = cProfile.Profile() if getattr(self.args, "worker_profile_out", None) is not None else None
            if profiler is not None:
                profiler.enable()
            try:
                stop_after_timeout_slice = False
                while not self.cancel_run.is_set():
                    with self.lock:
                        if stop_after_timeout_slice:
                            break
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
                            completed_steps = self._step_locked(
                                slice_now,
                                publish=False,
                                max_seconds=float(getattr(self.args, "worker_slice_seconds", 0.5)),
                                clear_stop_reason=False,
                            )
                            completed_steps = max(0, min(slice_now, int(completed_steps)))
                            self.job_last_slice_steps = completed_steps
                            self.job_last_slice_timed_out = bool(
                                getattr(self.emu, "last_run_timed_out", False)
                            )
                            self.job_done_steps += completed_steps
                            self._update_job_observed_locked()
                            run_remaining -= completed_steps
                            self._queue_dirty_frame_locked()
                            self._publish_snapshot_locked()
                            if self.emu.state.stop_reason or self.last_error:
                                self.cancel_run.set()
                                run_remaining = 0
                            elif completed_steps <= 0:
                                run_remaining = 0
                            elif self.job_last_slice_timed_out:
                                run_remaining = 0
                                if self.job_name == "input" and self.job_total_steps > 0:
                                    stop_after_timeout_slice = True
                        time.sleep(0)
            except Exception as exc:
                with self.lock:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    if self.emu is not None:
                        self.emu.state.stop_reason = self.last_error
                    self._capture_crash_snapshot_locked(self.last_error, traceback.format_exc())
                    self.cancel_run.set()
            finally:
                if profiler is not None:
                    profiler.disable()
                    profile_path = self.args.worker_profile_out
                    profile_path.parent.mkdir(parents=True, exist_ok=True)
                    profiler.dump_stats(str(profile_path))
                    text_path = profile_path.with_suffix(profile_path.suffix + ".txt")
                    with text_path.open("w", encoding="utf-8") as fh:
                        stats = pstats.Stats(profiler, stream=fh).strip_dirs().sort_stats("cumtime")
                        stats.print_stats(120)
                start_input_followup = False
                with self.lock:
                    self.running = False
                    self.job_finished_at = time.time()
                    if (
                        self.input_worker_pending
                        and not self.cancel_run.is_set()
                        and (self._pending_touch_count_locked() or self._pending_key_count_locked())
                    ):
                        self.input_worker_pending = False
                        start_input_followup = True
                    self._publish_snapshot_locked()
                if start_input_followup:
                    followup_steps = max(1, int(self.args.input_steps))
                    followup_chunk = max(1, min(followup_steps, int(self.args.worker_slice_steps)))
                    self.run_start("input", followup_steps, followup_chunk)

        self.worker = threading.Thread(target=worker, name=f"hwemu-{name or 'run'}", daemon=True)
        self.worker.start()
        return self.snapshot()

    def stop(self) -> dict[str, object]:
        self.cancel_run.set()
        emu = self.emu
        if emu is not None:
            try:
                emu.uc.emu_stop()
            except Exception:
                pass
        worker = self.worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=2.0)
        with self.lock:
            self.running = False
            self.input_worker_pending = False
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
            self.emu.set_key_controller_state(code & 0xFF, down)
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
        worker = self.worker
        if worker is not None and worker.is_alive() and worker is not threading.current_thread():
            if self.job_total_steps > 0 and self.job_finished_at is None:
                self.input_worker_pending = True
                with self.status_lock:
                    if self.cached_status:
                        self.cached_status["input_worker_pending"] = True
            return self.snapshot()
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=0.02)
        if self._worker_alive():
            if self.job_total_steps > 0 and self.job_finished_at is None:
                self.input_worker_pending = True
                with self.status_lock:
                    if self.cached_status:
                        self.cached_status["input_worker_pending"] = True
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

    def set_completed_step_timer(self, enabled: bool) -> dict[str, object]:
        with self.lock:
            if self.emu is not None:
                self.emu._set_completed_step_timer_source(
                    bool(enabled),
                    pc=self.emu.pc & 0xFFFFFFFF,
                    reason="command",
                )
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
        if op in {"completed-step-timer", "completed_step_timer", "set-completed-step-timer"}:
            enabled = self._coerce_optional_bool(msg.get("enabled"))
            if enabled is None:
                enabled = not bool(getattr(self.emu, "completed_step_timer", False))
            return self.set_completed_step_timer(enabled)
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
        event_count = 0
        events: list[object] = []
        for _ in range(3):
            try:
                event_count = len(emu.state.events)
                events = deque_tail(emu.state.events, limit)
                break
            except RuntimeError:
                time.sleep(0)
        return {
            "count": event_count,
            "limit": limit,
            "events": events,
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

    def _build_snapshot_locked(self, *, detail: str = "compact") -> dict[str, object]:
        assert self.emu is not None
        state = self.emu.state
        worker_alive = self._worker_alive()
        active = self.running or worker_alive
        now = time.time()
        reset_elapsed = max(0.0, now - self.reset_at)
        job = None
        if self.job_name is not None:
            if self.job_started_at is not None:
                self._update_job_observed_locked()
            started_at = self.job_started_at
            finished_at = self.job_finished_at
            elapsed = None
            if started_at is not None:
                elapsed = (finished_at if finished_at is not None else now) - started_at
            requested_steps_per_second = None
            observed_steps_per_second = None
            if elapsed is not None and elapsed > 0:
                requested_steps_per_second = self.job_done_steps / elapsed
                observed_steps_per_second = self.job_observed_insn_delta / elapsed
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
                "requested_done_steps": self.job_done_steps,
                "chunk_steps": self.job_chunk_steps,
                "last_slice_steps": self.job_last_slice_steps,
                "last_slice_timed_out": self.job_last_slice_timed_out,
                "observed_insn_delta": self.job_observed_insn_delta,
                "active": active,
                "started_at": started_at,
                "finished_at": finished_at,
                "elapsed_seconds": None if elapsed is None else max(0.0, elapsed),
                "steps_per_second": observed_steps_per_second,
                "observed_steps_per_second": observed_steps_per_second,
                "requested_steps_per_second": requested_steps_per_second,
            }
        with self.frame_queue_lock:
            deferred_due_at = None if self.deferred_raw_frame is None else self.deferred_raw_frame[0]
            queued_frames = len(self.frame_queue) + len(self.raw_frame_queue)
            if self.deferred_raw_frame is not None:
                queued_frames += 1
        scheduler = (
            self.emu.scheduler_snapshot()
            if detail == "full"
            else self.emu.scheduler_snapshot_compact()
        )
        events_limit = 16 if detail == "full" else 8
        snapshot = {
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
            "run_requested_steps_per_second": None if job is None else job["requested_steps_per_second"],
            "fast_hooks": not self.args.slow_global_code_hook,
            "run_internal_chunk_steps": getattr(self.emu, "run_internal_chunk_steps", None),
            "completed_step_timer": bool(getattr(self.emu, "completed_step_timer", False)),
            "completed_step_timer_after_auto_boot": bool(
                getattr(self.args, "completed_step_timer_after_auto_boot", False)
            ),
            "resource_cache16": self.args.resource_cache16_accelerator,
            "auto_calibration": self.args.auto_calibration,
            "auto_calibration_stage": self.auto_calibration_stage,
            "auto_calibration_stage_label": AUTO_BOOT_STAGE_LABELS.get(
                self.auto_calibration_stage,
                str(self.auto_calibration_stage),
            ),
            "pending_touches": self._pending_touch_count_locked(),
            "pending_keys": self._pending_key_count_locked(),
            "busy_delay_accel": self.emu.busy_delay_accel_count,
            "busy_delay_static_patch": bool(getattr(self.emu, "busy_delay_static_patch", False)),
            "ftl_scan_accel": self.emu.ftl_scan_accel_count,
            "cache_scan_tail_accel": getattr(self.emu, "cache_scan_tail_accel_count", 0),
            "accelerators": {
                "nand_loop": getattr(self.emu, "nand_loop_accel_count", 0),
                "resource_cache16": getattr(self.emu, "resource_cache16_accel_count", 0),
                "cluster_read": getattr(self.emu, "cluster_read_accel_count", 0),
                "block_io": getattr(self.emu, "block_io_accel_count", 0),
                "block_read_wrapper": getattr(self.emu, "block_read_wrapper_accel_count", 0),
                "file_read_loop": getattr(self.emu, "file_read_loop_accel_count", 0),
                "lfn_copy": getattr(self.emu, "lfn_copy_accel_count", 0),
                "dirent_copy": getattr(self.emu, "dirent_copy_accel_count", 0),
                "bda_cstr_search": getattr(self.emu, "bda_cstr_search_accel_count", 0),
                "free_scan": getattr(self.emu, "free_scan_accel_count", 0),
                "halfword_copy": getattr(self.emu, "halfword_copy_accel_count", 0),
                "raster_copy": getattr(self.emu, "raster_loop_accel_count", 0),
                "glyph_mask": getattr(self.emu, "glyph_mask_loop_accel_count", 0),
                "row_copy_loop": getattr(self.emu, "row_copy_loop_accel_count", 0),
                "cp0_irq_disable": getattr(self.emu, "cp0_irq_disable_accel_count", 0),
                "cp0_status_restore": getattr(self.emu, "cp0_status_restore_accel_count", 0),
                "surface_setpixel": getattr(self.emu, "surface_setpixel_accel_count", 0),
                "surface_hline": getattr(self.emu, "surface_hline_accel_count", 0),
                "surface_color_span": getattr(self.emu, "surface_color_span_accel_count", 0),
                "surface_read_span": getattr(self.emu, "surface_read_span_accel_count", 0),
                "surface_block_read": getattr(self.emu, "surface_block_read_accel_count", 0),
                "surface_block_write": getattr(self.emu, "surface_block_write_accel_count", 0),
                "surface_transparent_blit": getattr(self.emu, "surface_transparent_blit_accel_count", 0),
                "surface_events": getattr(self.emu, "surface_event_count", 0),
                "backing_sector_cache_size": len(getattr(self.emu, "backing_sector_cache", {}) or {}),
                "backing_sector_cache_hits": getattr(self.emu, "backing_sector_cache_hits", 0),
                "backing_sector_cache_misses": getattr(self.emu, "backing_sector_cache_misses", 0),
                "backing_sector_cache_evictions": getattr(self.emu, "backing_sector_cache_evictions", 0),
            },
            "suppressed_hot_events": self.emu.suppressed_hot_event_count,
            "no_event_poll_accel": self.emu.no_event_poll_accel_count,
            "perf": getattr(self.emu, "perf_counters", {}),
            "memcpy_bulk_callers": [
                {
                    "ra": f"0x{ra:08x}",
                    "count": int(row.get("count", 0)),
                    "bytes": int(row.get("bytes", 0)),
                    "last_src": f"0x{int(row.get('last_src', 0)) & 0xFFFFFFFF:08x}",
                    "last_dst": f"0x{int(row.get('last_dst', 0)) & 0xFFFFFFFF:08x}",
                    "last_size": int(row.get("last_size", 0)),
                }
                for ra, row in sorted(
                    getattr(self.emu, "memcpy_bulk_callers", {}).items(),
                    key=lambda item: int(item[1].get("count", 0)),
                    reverse=True,
                )[:12]
            ],
            "store_delay_branch_counts": [
                {"pc": f"0x{pc:08x}", "count": int(count)}
                for pc, count in sorted(
                    getattr(self.emu, "store_delay_branch_counts", {}).items(),
                    key=lambda item: int(item[1]),
                    reverse=True,
                )[:12]
            ],
            "on_code_dispatch_counts": [
                {"pc": f"0x{pc:08x}", "count": int(count)}
                for pc, count in sorted(
                    getattr(self.emu, "on_code_dispatch_counts", {}).items(),
                    key=lambda item: int(item[1]),
                    reverse=True,
                )[:24]
            ],
            "block_dispatch_counts": [
                {"pc": f"0x{pc:08x}", "count": int(count)}
                for pc, count in sorted(
                    getattr(self.emu, "block_dispatch_counts", {}).items(),
                    key=lambda item: int(item[1]),
                    reverse=True,
                )[:24]
            ],
            "trace_pc": {
                "counts": {
                    f"0x{pc:08x}": int(count)
                    for pc, count in sorted(getattr(self.emu, "trace_pc_counts", {}).items())
                },
                "recent_hits": list(getattr(self.emu, "trace_pc_hits", [])[-128:]),
            },
            "job": job,
            "input_worker_pending": self.input_worker_pending,
            "input_wake_count": self.input_wake_count,
            "stop_reason": self.last_error or state.stop_reason,
            "crash_snapshot": self.crash_snapshot,
            "insn_count": state.insn_count,
            "pc": f"0x{self.emu.pc:08x}",
            "last_pc": f"0x{state.last_pc:08x}",
            "idle_loop_hits": self.emu.idle_loop_hits,
            "app_idle_loop_hits": self.emu.app_idle_loop_hits,
            "events": deque_tail(state.events, events_limit),
            "invalid": [access_to_dict(a) for a in state.invalid[-4:]],
            "recoveries": list(state.recoveries[-events_limit:]),
            "scheduler": scheduler,
            "framebuffer": self.last_frame,
            "framebuffer_dirty_seq": getattr(self.emu, "framebuffer_dirty_seq", 0),
            "framebuffer_dirty_last": self.emu._framebuffer_dirty_last_snapshot(),
            "queued_frames": queued_frames,
            "frame_push": {
                "min_interval": self.frame_push_min_interval,
                "hook_count": self.frame_push_hook_count,
                "queued_count": self.frame_push_queued_count,
                "throttle_count": self.frame_push_throttle_count,
                "deferred_count": self.frame_push_deferred_count,
                "replace_count": self.frame_push_replace_count,
                "deferred_due_at": deferred_due_at,
                "drop_count": self.frame_push_drop_count,
                "error_count": self.frame_push_error_count,
                "info_min_interval": self.frame_info_min_interval,
                "info_update_count": self.frame_info_update_count,
                "last_push_at": self.frame_push_last_time,
                "ws_sent_count": self.ws_frame_sent_count,
                "ws_sent_bytes": self.ws_frame_sent_bytes,
                "ws_last_seq": self.ws_frame_last_seq,
                "ws_last_kind": self.ws_frame_last_kind,
                "ws_last_bytes": self.ws_frame_last_bytes,
                "ws_last_sent_at": self.ws_frame_last_sent_at,
            },
            "ws": {
                "command_count": self.ws_command_count,
                "last_op": self.ws_last_command_op,
                "last_seq": self.ws_last_command_seq,
                "last_command_at": self.ws_last_command_at,
                "reader_alive": self.ws_reader_alive,
                "reader_heartbeat": self.ws_reader_heartbeat,
            },
            "status_cached_at": time.time(),
        }
        if detail == "full":
            snapshot["detail"] = "full"
            snapshot["block_events"] = list(getattr(self.emu, "block_events", [])[-64:])
            snapshot["cluster_read_events"] = list(getattr(self.emu, "cluster_read_events", [])[-32:])
            snapshot["file_read_loop_events"] = list(getattr(self.emu, "file_read_loop_events", [])[-32:])
            snapshot["native_bda_event_probe"] = self._native_bda_event_probe_locked()
            snapshot["input"] = self.emu.input_snapshot()
        if detail == "full" or bool(getattr(self.emu, "hot_path_stats", False)):
            snapshot["tasks"] = self.emu.task_table_snapshot()
            snapshot["event_queue"] = self.emu._queue_object_snapshot(self.emu._read_u32_va_safe(0x80473F6C))
            snapshot["display_event_queue"] = self.emu._display_event_queue_snapshot()
            snapshot["recent_event_queue_snapshots"] = self.emu.event_queue_snapshots[-16:]
            snapshot["recent_gui_ring_pump_events"] = self.emu.gui_ring_pump_events[-16:]
        return snapshot

    def _publish_snapshot_locked(self) -> None:
        with self.status_lock:
            self.cached_status = self._build_snapshot_locked()
        self._notify_frontend_activity()

    def snapshot(self, *, detail: str = "compact") -> dict[str, object]:
        if detail == "full":
            with self.lock:
                return self._build_snapshot_locked(detail="full")
        with self.status_lock:
            return dict(self.cached_status)
