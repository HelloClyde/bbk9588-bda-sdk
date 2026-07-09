"""QEMU-backed frontend state for the BBK 9588 web UI."""

from __future__ import annotations

import argparse
import struct
import threading
import time
from collections import deque
from itertools import islice
from pathlib import Path

from emu.core.framebuffer import png_bytes_from_rgb, rgb565_raw_to_info_rgb
from emu.qemu.system import (
    DEFAULT_QEMU_EXECUTABLE,
    DEFAULT_QEMU_MACHINE,
    QemuProcessBackend,
    TOUCH_CALIBRATION_REFERENCE_POINTS,
    build_bbk_qemu_config,
    classify_guest_pc,
)


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
COMBINED_NAND_IMAGE = BUILD / "bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin"
FALLBACK_COMBINED_NAND_IMAGE = BUILD / "bbk9588_nand_c200_fat_page1c40.bin"

AUTO_BOOT_DIALOG_X = 150
AUTO_BOOT_DIALOG_Y = 205
AUTO_CALIBRATION_TARGETS = tuple((x, y) for x, y, _raw_x, _raw_y in TOUCH_CALIBRATION_REFERENCE_POINTS)
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

KNOWN_FRONTEND_KEY_CODES = {4, 5, 6, 7, 9, 10}


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
        self.status_lock = threading.RLock()
        self.frontend_activity_condition = threading.Condition()
        self.input_lock = threading.RLock()

        self.qemu_backend: QemuProcessBackend | None = None
        self.qemu_worker: threading.Thread | None = None
        self.cancel_run = threading.Event()

        self.last_error: str | None = None
        self.crash_snapshot: dict[str, object] | None = None
        self.last_frame: dict[str, object] | None = None
        self.running = False
        self.reset_at = time.time()

        self.job_name: str | None = None
        self.job_total_steps = 0
        self.job_done_steps = 0
        self.job_chunk_steps = 0
        self.job_last_slice_steps = 0
        self.job_last_slice_timed_out = False
        self.job_started_at: float | None = None
        self.job_finished_at: float | None = None

        self.input_worker_pending = False
        self.input_wake_count = 0
        self.last_input_event: dict[str, object] | None = None
        self.pending_touches: deque[tuple[int, int, bool]] = deque(maxlen=32)
        self.pending_keys: deque[tuple[int, bool]] = deque(maxlen=32)

        self.auto_calibration_stage = 0
        self.auto_calibration_last_stage_step = -1
        self.qemu_auto_calibration_last_action_at = 0.0
        self.qemu_auto_calibration_log: list[dict[str, object]] = []
        self.qemu_storage_bootstrap_done = False
        self.qemu_storage_bootstrap_attempts = 0
        self.qemu_storage_bootstrap_log: list[dict[str, object]] = []

        self.frame_push_min_interval = max(0.0, float(getattr(args, "frame_push_min_interval", 0.04)))
        self.frame_info_min_interval = max(0.0, float(getattr(args, "frame_info_min_interval", 1.0)))
        self.frame_push_last_time = 0.0
        self.frame_push_hook_count = 0
        self.frame_push_queued_count = 0
        self.frame_push_throttle_count = 0
        self.frame_push_deferred_count = 0
        self.frame_push_replace_count = 0
        self.frame_push_drop_count = 0
        self.frame_push_error_count = 0
        self.frame_info_last_time = 0.0
        self.frame_info_update_count = 0

        self.cached_status: dict[str, object] = {}
        self.cached_frame_bytes: bytes | None = None
        self.cached_frame_time = 0.0
        self.cached_ws_frame_bytes: bytes | None = None
        self.cached_ws_frame_time = 0.0
        self.qemu_last_ws_frame_seq: int | None = None

        self.ws_frame_sent_count = 0
        self.ws_frame_sent_bytes = 0
        self.ws_frame_last_seq: int | None = None
        self.ws_frame_last_kind = ""
        self.ws_frame_last_bytes = 0
        self.ws_frame_last_sent_at = 0.0
        self.ws_command_count = 0
        self.ws_last_command_op = ""
        self.ws_last_command_seq: object | None = None
        self.ws_last_command_at = 0.0
        self.ws_reader_alive = False
        self.ws_reader_heartbeat = 0.0
        self.frontend_activity_seq = 0

        self.reset()

    def _default_nand_image(self) -> Path | None:
        if self.args.nand_image is not None:
            return self.args.nand_image
        if COMBINED_NAND_IMAGE.exists():
            return COMBINED_NAND_IMAGE
        if FALLBACK_COMBINED_NAND_IMAGE.exists():
            return FALLBACK_COMBINED_NAND_IMAGE
        return None

    def _reset_runtime_fields_locked(self) -> None:
        self.last_error = None
        self.crash_snapshot = None
        self.last_frame = {
            "backend": "qemu",
            "available": False,
            "reason": "no frame captured yet",
            "output_width": LIVE_FRAMEBUFFER_WIDTH,
            "output_height": LIVE_FRAMEBUFFER_HEIGHT,
        }
        self.running = False
        self.job_name = "qemu"
        self.job_total_steps = 0
        self.job_done_steps = 0
        self.job_chunk_steps = 0
        self.job_last_slice_steps = 0
        self.job_last_slice_timed_out = False
        self.job_started_at = time.time()
        self.job_finished_at = None
        self.input_worker_pending = False
        self.input_wake_count = 0
        self.last_input_event = None
        self.auto_calibration_stage = 0
        self.auto_calibration_last_stage_step = -1
        self.qemu_auto_calibration_last_action_at = 0.0
        self.qemu_auto_calibration_log = []
        self.qemu_storage_bootstrap_done = False
        self.qemu_storage_bootstrap_attempts = 0
        self.qemu_storage_bootstrap_log = []
        self.reset_at = time.time()
        self.cached_frame_bytes = None
        self.cached_frame_time = 0.0
        self.cached_ws_frame_bytes = None
        self.cached_ws_frame_time = 0.0
        self.qemu_last_ws_frame_seq = None
        self.frame_push_last_time = 0.0
        self.frame_push_hook_count = 0
        self.frame_push_queued_count = 0
        self.frame_push_throttle_count = 0
        self.frame_push_deferred_count = 0
        self.frame_push_replace_count = 0
        self.frame_push_drop_count = 0
        self.frame_push_error_count = 0
        self.frame_info_last_time = 0.0
        self.frame_info_update_count = 0
        self.ws_frame_sent_count = 0
        self.ws_frame_sent_bytes = 0
        self.ws_frame_last_seq = None
        self.ws_frame_last_kind = ""
        self.ws_frame_last_bytes = 0
        self.ws_frame_last_sent_at = 0.0
        with self.input_lock:
            self.pending_touches.clear()
            self.pending_keys.clear()

    def reset(self) -> dict[str, object]:
        old_backend = self.qemu_backend
        if old_backend is not None:
            old_backend.stop()
        self.cancel_run.set()
        if self.qemu_worker is not None and self.qemu_worker.is_alive() and self.qemu_worker is not threading.current_thread():
            self.qemu_worker.join(timeout=2.0)

        with self.lock:
            BUILD.mkdir(parents=True, exist_ok=True)
            self.cancel_run.clear()
            self._reset_runtime_fields_locked()
            config = build_bbk_qemu_config(
                boot_mode=getattr(self.args, "boot_mode", "uboot"),
                executable=getattr(self.args, "qemu", DEFAULT_QEMU_EXECUTABLE),
                ram_mb=int(getattr(self.args, "ram_mb", 160)),
                machine=getattr(self.args, "qemu_machine", DEFAULT_QEMU_MACHINE),
                cpu=getattr(self.args, "qemu_cpu", "24Kf"),
                accel=getattr(self.args, "qemu_accel", "tcg,thread=multi,tb-size=256"),
                display="none",
                serial="mon:stdio",
                monitor="none",
                gdb=getattr(self.args, "qemu_gdb", "none"),
                timeout_seconds=float(getattr(self.args, "qemu_timeout", 5.0)),
                nand_image=self._default_nand_image(),
                bbk_machine_options=tuple(getattr(self.args, "qemu_machine_option", []) or ()),
                extra_args=tuple(getattr(self.args, "qemu_extra_arg", []) or ()),
                firmware_patches=getattr(self.args, "qemu_firmware_patch", None),
            )
            self.qemu_backend = QemuProcessBackend(config)
            try:
                self.qemu_backend.start()
                self.running = self.qemu_backend.running()
                self._start_qemu_tick_worker_locked()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.job_finished_at = time.time()
                self.running = False
            self._publish_snapshot_locked()
            return self.snapshot()

    def _start_qemu_tick_worker_locked(self) -> None:
        if self.qemu_worker is not None and self.qemu_worker.is_alive():
            return

        def worker() -> None:
            while not self.cancel_run.is_set():
                try:
                    with self.lock:
                        backend = self.qemu_backend
                        if backend is None or not backend.running():
                            break
                        self._apply_qemu_auto_calibration_locked(backend)
                except Exception as exc:
                    with self.lock:
                        self.qemu_auto_calibration_log.append(
                            {"event": "qemu-auto-worker-error", "error": f"{type(exc).__name__}: {exc}"}
                        )
                        del self.qemu_auto_calibration_log[:-16]
                self._notify_frontend_activity()
                time.sleep(0.5)

        self.qemu_worker = threading.Thread(target=worker, name="bbk9588-qemu-frontend-tick", daemon=True)
        self.qemu_worker.start()

    def _ensure_qemu_started_locked(self) -> QemuProcessBackend:
        if self.qemu_backend is None:
            self.reset()
        assert self.qemu_backend is not None
        if not self.qemu_backend.running() and self.qemu_backend.snapshot().get("returncode") is not None:
            self.qemu_backend.start()
            self._start_qemu_tick_worker_locked()
        self.running = self.qemu_backend.running()
        return self.qemu_backend

    def _ws_payload_from_raw_frame(self, seq: int, raw: bytes) -> bytes:
        if len(raw) < LIVE_FRAMEBUFFER_RAW_BYTES:
            raise ValueError(f"short RGB565 frame: {len(raw)} bytes")
        payload = raw[:LIVE_FRAMEBUFFER_RAW_BYTES]
        return WS_RAW_FRAME_HEADER.pack(
            WS_RAW_FRAME_MAGIC,
            int(seq) & 0xFFFFFFFF,
            LIVE_FRAMEBUFFER_WIDTH,
            LIVE_FRAMEBUFFER_HEIGHT,
            LIVE_FRAMEBUFFER_STRIDE_PIXELS,
            WS_RAW_FRAME_FORMAT_RGB565,
        ) + payload

    def _latest_qemu_raw_frame_locked(self) -> tuple[int, float, bytes] | None:
        backend = self.qemu_backend
        if backend is None:
            return None
        latest = backend.latest_frame_chardev
        if latest is not None:
            return latest
        return None

    def pop_queued_frame(self) -> bytes | None:
        return None

    def pop_latest_queued_frame(self) -> bytes | None:
        return self.pop_queued_frame()

    def pop_queued_ws_frame(self) -> bytes | None:
        with self.lock:
            latest = self._latest_qemu_raw_frame_locked()
            if latest is None:
                return None
            seq, captured_at, raw = latest
            if self.qemu_last_ws_frame_seq == seq:
                return None
            try:
                payload = self._ws_payload_from_raw_frame(seq, raw)
            except Exception as exc:
                self.frame_push_error_count += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                return None
            self.qemu_last_ws_frame_seq = seq
            self.cached_ws_frame_bytes = payload
            self.cached_ws_frame_time = captured_at
            self.frame_push_queued_count += 1
            self.frame_push_last_time = time.time()
            self._notify_frontend_activity()
            return payload

    def pop_latest_queued_ws_frame(self) -> bytes | None:
        return self.pop_queued_ws_frame()

    def dump_ws_frame(self) -> bytes:
        with self.lock:
            backend = self._ensure_qemu_started_locked()
            latest = self._latest_qemu_raw_frame_locked()
            if latest is not None:
                seq, captured_at, raw = latest
                payload = self._ws_payload_from_raw_frame(seq, raw)
                self.cached_ws_frame_bytes = payload
                self.cached_ws_frame_time = captured_at
                self.qemu_last_ws_frame_seq = seq
                return payload
            raw, source = backend.read_display_rgb565_frame()
            seq = int(backend.frame_chardev_count or time.time() * 1000)
            payload = self._ws_payload_from_raw_frame(seq, raw)
            self.cached_ws_frame_bytes = payload
            self.cached_ws_frame_time = time.time()
            self.qemu_last_ws_frame_seq = seq
            self.last_frame = self._frame_info_from_raw(raw, source)
            return payload

    def cached_frame(self) -> bytes | None:
        return self.cached_frame_bytes

    def cached_ws_frame(self) -> bytes | None:
        return self.cached_ws_frame_bytes

    def record_ws_frame_sent(self, payload: bytes) -> None:
        self.ws_frame_sent_count += 1
        self.ws_frame_sent_bytes += len(payload)
        self.ws_frame_last_bytes = len(payload)
        self.ws_frame_last_sent_at = time.time()
        if payload.startswith(WS_RAW_FRAME_MAGIC) and len(payload) >= WS_RAW_FRAME_HEADER_SIZE:
            self.ws_frame_last_kind = "raw-rgb565"
            self.ws_frame_last_seq = int.from_bytes(payload[8:12], "little")
        elif payload.startswith(b"\x89PNG\r\n\x1a\n"):
            self.ws_frame_last_kind = "png"
            self.ws_frame_last_seq = None
        else:
            self.ws_frame_last_kind = "unknown"
            self.ws_frame_last_seq = None

    def seconds_until_deferred_frame(self) -> float | None:
        return None

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
        deadline = time.time() + max(0.0, timeout)
        with self.frontend_activity_condition:
            while self.frontend_activity_seq == last_seq:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self.frontend_activity_condition.wait(timeout=remaining)
            return self.frontend_activity_seq

    def record_ws_command(self, op: str, command_seq: object | None = None) -> None:
        self.ws_command_count += 1
        self.ws_last_command_op = str(op)
        self.ws_last_command_seq = command_seq
        self.ws_last_command_at = time.time()
        self._notify_frontend_activity()

    def set_ws_reader_alive(self, alive: bool) -> None:
        self.ws_reader_alive = bool(alive)
        self.ws_reader_heartbeat = time.time()
        self._notify_frontend_activity()

    def worker_active(self) -> bool:
        backend = self.qemu_backend
        return False if backend is None else backend.running()

    def step(self, steps: int) -> dict[str, object]:
        return self.run_start("qemu-step", max(0, int(steps)), max(0, int(steps)))

    def boot(self) -> dict[str, object]:
        return self.run_start("boot", 0, 0)

    def save_checkpoint(self, path: Path) -> dict[str, object]:
        return {"error": "QEMU process backend does not support Python checkpoints", "path": str(path)}

    def run_start(self, name: str, total_steps: int, chunk_steps: int) -> dict[str, object]:
        with self.lock:
            try:
                backend = self._ensure_qemu_started_locked()
                self.running = backend.running()
                self.job_name = name or "qemu"
                self.job_total_steps = max(0, int(total_steps))
                self.job_done_steps = 0
                self.job_chunk_steps = max(0, int(chunk_steps))
                self.job_last_slice_steps = 0
                self.job_last_slice_timed_out = False
                self.job_started_at = self.job_started_at or time.time()
                self.job_finished_at = None
                self._start_qemu_tick_worker_locked()
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.running = False
            self._publish_snapshot_locked()
            return self.snapshot()

    def stop(self) -> dict[str, object]:
        self.cancel_run.set()
        with self.lock:
            backend = self.qemu_backend
            if backend is not None:
                backend.stop()
            self.running = False
            self.job_finished_at = time.time()
            self._publish_snapshot_locked()
            return self.snapshot()

    @staticmethod
    def _coerce_optional_bool(value: object) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on", "down"}:
            return True
        if text in {"0", "false", "no", "off", "up"}:
            return False
        return None

    def _touch_coordinates_from_message(self, msg: dict[str, object]) -> tuple[int, int]:
        if "display_x" in msg or "display_y" in msg:
            return display_to_touch_point(
                int(msg.get("display_x", 0)),
                int(msg.get("display_y", 0)),
                int(msg.get("display_width", 240)),
                int(msg.get("display_height", 320)),
                getattr(self.args, "orientation", "rot180"),
            )
        return int(msg.get("x", 0)), int(msg.get("y", 0))

    def key(self, code: int, down: bool = True, advance: bool | None = None) -> dict[str, object]:
        code = int(code)
        if code not in KNOWN_FRONTEND_KEY_CODES:
            return {"error": f"unknown key code {code}", "known": sorted(KNOWN_FRONTEND_KEY_CODES)}
        with self.lock:
            backend = self._ensure_qemu_started_locked()
            result = backend.apply_gui_key_event(code, bool(down))
            event = {
                "kind": "key",
                "code": code,
                "down": bool(down),
                "accepted": bool(result.get("applied")),
                "result": result,
                "at": time.time(),
            }
            self.last_input_event = event
            self.input_wake_count += 1
            with self.input_lock:
                self.pending_keys.clear()
            self._publish_snapshot_locked()
            snapshot = self.snapshot()
            snapshot["input_accepted"] = event["accepted"]
            snapshot["qemu_input_result"] = result
            if advance is not None:
                snapshot["warning"] = "advance is ignored by the QEMU process backend"
            return snapshot

    def touch(self, x: int, y: int, down: bool, advance: bool | None = None) -> dict[str, object]:
        x = max(0, min(239, int(x)))
        y = max(0, min(319, int(y)))
        with self.lock:
            backend = self._ensure_qemu_started_locked()
            result = backend.apply_touch_state(x, y, bool(down))
            event = {
                "kind": "touch",
                "x": x,
                "y": y,
                "down": bool(down),
                "accepted": bool(result.get("applied")),
                "result": result,
                "at": time.time(),
            }
            self.last_input_event = event
            self.input_wake_count += 1
            with self.input_lock:
                self.pending_touches.clear()
            self._publish_snapshot_locked()
            snapshot = self.snapshot()
            snapshot["input_accepted"] = event["accepted"]
            snapshot["qemu_input_result"] = result
            if advance is not None:
                snapshot["warning"] = "advance is ignored by the QEMU process backend"
            return snapshot

    def set_auto_calibration(self, enabled: bool) -> dict[str, object]:
        self.args.auto_calibration = bool(enabled)
        with self.lock:
            self._publish_snapshot_locked()
            return self.snapshot()

    def command(self, msg: dict[str, object]) -> dict[str, object]:
        op = str(msg.get("op", "status"))
        if op == "reset":
            return self.reset()
        if op in {"run-start", "run_start"}:
            return self.run_start(str(msg.get("name", "run")), int(msg.get("steps", 0)), int(msg.get("chunk", 100000)))
        if op == "stop":
            return self.stop()
        if op == "step":
            return self.step(int(msg.get("steps", 250000)))
        if op in {"auto-calibration", "auto_calibration", "set-auto-calibration"}:
            enabled = self._coerce_optional_bool(msg.get("enabled"))
            if enabled is None:
                enabled = not bool(getattr(self.args, "auto_calibration", False))
            return self.set_auto_calibration(enabled)
        if op in {"qemu-storage-service", "qemu_storage_service"}:
            return {"error": "qemu-storage-service is disabled; Python/GDB fastpath services were removed"}
        if op in {"qemu-task-trace", "qemu_task_trace", "qemu-fs-trace", "qemu_fs_trace", "qemu-event-loop-trace", "qemu_event_loop_trace", "qemu-resource-trace", "qemu_resource_trace"}:
            return {"error": f"{op} is disabled; use QEMU machine/device instrumentation instead of Python/GDB services"}
        if op in {"qemu-read-memory", "qemu_read_memory"}:
            if self.qemu_backend is None:
                return {"error": "QEMU backend is not initialized"}
            addr = int(str(msg.get("addr", 0)), 0)
            size = max(0, min(int(msg.get("size", 0x80)), 0x1000))
            if size == 0:
                return {"addr": f"0x{addr & 0xFFFFFFFF:08x}", "size": 0, "hex": ""}
            try:
                data = self.qemu_backend.read_guest_memory(addr, size)
            except Exception as exc:
                return {"error": f"{type(exc).__name__}: {exc}"}
            out: dict[str, object] = {"addr": f"0x{addr & 0xFFFFFFFF:08x}", "size": len(data), "hex": data.hex()}
            raw = data.split(b"\x00", 1)[0]
            for encoding in ("gbk", "ascii"):
                try:
                    out[encoding] = raw.decode(encoding)
                except UnicodeDecodeError:
                    pass
            return out
        if op in {"qemu-watch-write", "qemu_watch_write"}:
            if self.qemu_backend is None:
                return {"error": "QEMU backend is not initialized"}
            addr = int(str(msg.get("addr", 0)), 0)
            size = int(msg.get("size", 4))
            timeout = float(msg.get("timeout", 10.0))
            trigger_touch = None
            values = msg.get("trigger_touch")
            if isinstance(values, (list, tuple)) and len(values) >= 2:
                trigger_touch = (int(values[0]), int(values[1]))
            ignore_pcs = ()
            raw_ignore = msg.get("ignore_pcs")
            if isinstance(raw_ignore, (list, tuple)):
                ignore_pcs = tuple(int(str(value), 0) for value in raw_ignore)
            return self.qemu_backend.watch_guest_write_once(
                addr,
                size,
                timeout,
                trigger_touch,
                float(msg.get("trigger_hold_seconds", 0.0)),
                ignore_pcs,
                int(msg.get("max_hits", 1)),
            )
        if op in {"qemu-trace-breakpoints", "qemu_trace_breakpoints"}:
            if self.qemu_backend is None:
                return {"error": "QEMU backend is not initialized"}
            pcs_raw = msg.get("pcs", [])
            if not isinstance(pcs_raw, (list, tuple)):
                return {"error": "pcs must be a list"}
            pcs = tuple(int(str(value), 0) for value in pcs_raw)
            trigger_touch = None
            values = msg.get("trigger_touch")
            if isinstance(values, (list, tuple)) and len(values) >= 2:
                trigger_touch = (int(values[0]), int(values[1]))
            sample_rect = None
            rect = msg.get("sample_rect")
            if isinstance(rect, (list, tuple)) and len(rect) >= 4:
                sample_rect = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
            return self.qemu_backend.trace_guest_breakpoints_once(
                pcs,
                timeout=float(msg.get("timeout", 5.0)),
                max_hits=int(msg.get("max_hits", 32)),
                trigger_touch=trigger_touch,
                trigger_hold_seconds=float(msg.get("trigger_hold_seconds", 0.0)),
                sample_rect=sample_rect,
                dedupe_blits=self._coerce_optional_bool(msg.get("dedupe_blits")) is True,
            )
        if op == "key":
            out = self.key(
                int(msg.get("code", 0)),
                self._coerce_optional_bool(msg.get("down")) is not False,
                self._coerce_optional_bool(msg.get("advance")),
            )
            if self._coerce_optional_bool(msg.get("run")) is True:
                run_status = self.run_start("qemu-input", 0, 0)
                for key_name in ("input_accepted", "qemu_input_result", "warning"):
                    if key_name in out:
                        run_status[key_name] = out[key_name]
                return run_status
            return out
        if op == "touch":
            x, y = self._touch_coordinates_from_message(msg)
            out = self.touch(
                x,
                y,
                self._coerce_optional_bool(msg.get("down")) is not False,
                self._coerce_optional_bool(msg.get("advance")),
            )
            if isinstance(self.last_input_event, dict):
                self.last_input_event["source"] = msg.get("source") or "message"
                self.last_input_event["phase"] = msg.get("phase")
                if "display_x" in msg or "display_y" in msg:
                    self.last_input_event["display_x"] = int(msg.get("display_x", 0))
                    self.last_input_event["display_y"] = int(msg.get("display_y", 0))
                    self.last_input_event["display_width"] = int(msg.get("display_width", 240))
                    self.last_input_event["display_height"] = int(msg.get("display_height", 320))
            if self._coerce_optional_bool(msg.get("run")) is True:
                run_status = self.run_start("qemu-input", 0, 0)
                for key_name in ("input_accepted", "qemu_input_result", "warning"):
                    if key_name in out:
                        run_status[key_name] = out[key_name]
                return run_status
            return out
        return self.snapshot()

    def logs(self, limit: int = 512) -> dict[str, object]:
        backend = self.qemu_backend
        if backend is None:
            return {"count": 0, "limit": limit, "events": []}
        snap = backend.snapshot()
        lines = [
            *[{"stream": "stdout", "text": line} for line in snap.get("stdout_tail", [])],
            *[{"stream": "stderr", "text": line} for line in snap.get("stderr_tail", [])],
        ]
        limit = max(1, min(5000, int(limit)))
        return {"count": len(lines), "limit": limit, "events": lines[-limit:]}

    def clear_logs(self) -> dict[str, object]:
        with self.lock:
            backend = self.qemu_backend
            removed = 0
            if backend is not None:
                snap = backend.snapshot()
                removed = len(snap.get("stdout_tail", [])) + len(snap.get("stderr_tail", []))
                backend.stdout_tail.clear()
                backend.stderr_tail.clear()
            self._publish_snapshot_locked()
            return {"cleared": removed}

    def _frame_info_from_raw(self, raw: bytes, source: str) -> dict[str, object]:
        info, _rgb = rgb565_raw_to_info_rgb(
            raw,
            LIVE_FRAMEBUFFER_ADDR,
            LIVE_FRAMEBUFFER_OFFSET_BYTES,
            LIVE_FRAMEBUFFER_WIDTH,
            LIVE_FRAMEBUFFER_HEIGHT,
            LIVE_FRAMEBUFFER_STRIDE_PIXELS,
            LIVE_FRAMEBUFFER_FORMAT,
            getattr(self.args, "orientation", "rot180"),
        )
        info["backend"] = "qemu"
        info["source"] = source
        info["available"] = True
        return info

    def dump_frame(self) -> bytes:
        cached = self.cached_frame_bytes
        now = time.time()
        if cached is not None and now - self.cached_frame_time < 0.25:
            return cached
        with self.lock:
            try:
                backend = self._ensure_qemu_started_locked()
                try:
                    raw, source = backend.read_display_rgb565_frame()
                except Exception:
                    raw = backend.read_physical_memory(LIVE_FRAMEBUFFER_ADDR & 0x1FFFFFFF, LIVE_FRAMEBUFFER_RAW_BYTES)
                    source = "hmp-pmemsave"
                self.last_frame, rgb = rgb565_raw_to_info_rgb(
                    raw,
                    LIVE_FRAMEBUFFER_ADDR,
                    LIVE_FRAMEBUFFER_OFFSET_BYTES,
                    LIVE_FRAMEBUFFER_WIDTH,
                    LIVE_FRAMEBUFFER_HEIGHT,
                    LIVE_FRAMEBUFFER_STRIDE_PIXELS,
                    LIVE_FRAMEBUFFER_FORMAT,
                    getattr(self.args, "orientation", "rot180"),
                )
                self.last_frame["backend"] = "qemu"
                self.last_frame["source"] = source
                self.last_frame["available"] = True
                frame = png_bytes_from_rgb(int(self.last_frame["output_width"]), int(self.last_frame["output_height"]), rgb)
            except Exception as exc:
                self.last_frame = {
                    "backend": "qemu",
                    "available": False,
                    "reason": f"{type(exc).__name__}: {exc}",
                    "output_width": LIVE_FRAMEBUFFER_WIDTH,
                    "output_height": LIVE_FRAMEBUFFER_HEIGHT,
                }
                rgb = bytes([0x12, 0x16, 0x1C]) * (LIVE_FRAMEBUFFER_WIDTH * LIVE_FRAMEBUFFER_HEIGHT)
                frame = png_bytes_from_rgb(LIVE_FRAMEBUFFER_WIDTH, LIVE_FRAMEBUFFER_HEIGHT, rgb)
            self.cached_frame_bytes = frame
            self.cached_frame_time = now
            self._publish_snapshot_locked()
            return frame

    def dump_qemu_guest_rgb565(
        self,
        addr: int,
        *,
        width: int = 240,
        height: int = 320,
        stride_pixels: int | None = None,
        orientation: str = "raw",
    ) -> bytes:
        if width <= 0 or height <= 0 or width > 1024 or height > 1024:
            raise ValueError("invalid RGB565 dimensions")
        stride = stride_pixels if stride_pixels is not None else width
        if stride < width or stride > 4096:
            raise ValueError("invalid RGB565 stride")
        if orientation not in {"raw", "rot180", "cw90", "ccw90", "hflip", "vflip"}:
            raise ValueError("invalid RGB565 orientation")
        with self.lock:
            backend = self._ensure_qemu_started_locked()
            raw = backend.read_guest_memory(int(addr), stride * height * 2)
        info, rgb = rgb565_raw_to_info_rgb(raw, int(addr), 0, width, height, stride, "rgb565", orientation)
        return png_bytes_from_rgb(int(info["output_width"]), int(info["output_height"]), rgb)

    def dump_qemu_guest_memory(self, addr: int, size: int) -> bytes:
        if size <= 0 or size > 4 * 1024 * 1024:
            raise ValueError("invalid memory dump size")
        with self.lock:
            backend = self._ensure_qemu_started_locked()
            return backend.read_guest_memory(int(addr), int(size))

    def _pending_touch_count_locked(self) -> int:
        with self.input_lock:
            return len(self.pending_touches)

    def _pending_key_count_locked(self) -> int:
        with self.input_lock:
            return len(self.pending_keys)

    def _build_snapshot_locked(self, *, detail: str = "compact") -> dict[str, object]:
        backend = self.qemu_backend
        if backend is not None:
            self._apply_qemu_auto_calibration_locked(backend)
        qemu = {} if backend is None else backend.snapshot()
        qemu_sample = qemu.get("register_sample") if isinstance(qemu.get("register_sample"), dict) else {}
        qemu_pc = qemu.get("pc") or (qemu_sample.get("pc") if isinstance(qemu_sample, dict) else None)
        qemu_cp0 = qemu.get("cp0") or (qemu_sample.get("cp0") if isinstance(qemu_sample, dict) else None)
        qemu_pc_classification = qemu.get("pc_classification") if isinstance(qemu.get("pc_classification"), dict) else classify_guest_pc(qemu_pc)
        qemu_pc_region = qemu_pc_classification.get("region") if isinstance(qemu_pc_classification, dict) else None
        active = bool(qemu.get("running"))
        now = time.time()
        reset_elapsed = max(0.0, now - self.reset_at)
        elapsed = qemu.get("elapsed_seconds")
        job = {
            "name": self.job_name or "qemu",
            "mode": "process",
            "status": "running" if active else "stopped",
            "total_steps": self.job_total_steps,
            "done_steps": self.job_done_steps,
            "requested_done_steps": self.job_done_steps,
            "chunk_steps": self.job_chunk_steps,
            "last_slice_steps": self.job_last_slice_steps,
            "last_slice_timed_out": self.job_last_slice_timed_out,
            "observed_insn_delta": 0,
            "active": active,
            "started_at": self.job_started_at,
            "finished_at": self.job_finished_at,
            "elapsed_seconds": elapsed,
            "steps_per_second": None,
            "observed_steps_per_second": None,
            "requested_steps_per_second": None,
        }
        snapshot: dict[str, object] = {
            "backend": "qemu",
            "running": active,
            "boot_mode": getattr(self.args, "boot_mode", "uboot"),
            "orientation": getattr(self.args, "orientation", "rot180"),
            "reset_at": self.reset_at,
            "reset_elapsed_seconds": reset_elapsed,
            "emulator_elapsed_seconds": elapsed if isinstance(elapsed, (int, float)) else reset_elapsed,
            "run_started_at": self.job_started_at,
            "run_finished_at": self.job_finished_at,
            "run_elapsed_seconds": elapsed,
            "run_steps_per_second": None,
            "run_requested_steps_per_second": None,
            "fast_hooks": False,
            "resource_cache16": False,
            "auto_calibration": bool(getattr(self.args, "auto_calibration", False)),
            "auto_calibration_stage": self.auto_calibration_stage,
            "auto_calibration_stage_label": AUTO_BOOT_STAGE_LABELS.get(self.auto_calibration_stage, str(self.auto_calibration_stage)),
            "pending_touches": self._pending_touch_count_locked(),
            "pending_keys": self._pending_key_count_locked(),
            "job": job,
            "input_worker_pending": False,
            "input_wake_count": self.input_wake_count,
            "last_input_event": self.last_input_event,
            "stop_reason": self.last_error or qemu.get("last_error"),
            "crash_snapshot": self.crash_snapshot,
            "insn_count": 0,
            "pc": qemu_pc,
            "last_pc": qemu_pc,
            "cp0": qemu_cp0,
            "qemu_pc_region": qemu_pc_region,
            "idle_loop_hits": 0,
            "app_idle_loop_hits": 0,
            "events": [],
            "invalid": [],
            "recoveries": [],
            "scheduler": {},
            "framebuffer": self.last_frame,
            "framebuffer_dirty_seq": 0,
            "framebuffer_dirty_last": None,
            "queued_frames": 0,
            "frame_push": {
                "min_interval": self.frame_push_min_interval,
                "hook_count": self.frame_push_hook_count,
                "queued_count": self.frame_push_queued_count,
                "throttle_count": self.frame_push_throttle_count,
                "deferred_count": self.frame_push_deferred_count,
                "replace_count": self.frame_push_replace_count,
                "deferred_due_at": None,
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
            "qemu": qemu,
            "qemu_pc_classification": qemu_pc_classification,
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
            if backend is not None:
                snapshot["event_queue"] = backend.guest_queue_snapshot(0x80473F6C)
                snapshot["display_event_queue"] = backend.guest_display_queue_snapshot(0x80825840)
                snapshot["guest_gui_state"] = backend.guest_gui_state_snapshot()
                snapshot["qemu_scheduler_state"] = backend.guest_scheduler_state_snapshot()
                snapshot["guest_touch_device"] = backend.guest_touch_device_snapshot()
                snapshot["guest_runtime_tables"] = backend.guest_runtime_table_snapshot()
                snapshot["guest_surface_trace"] = backend.guest_surface_trace_snapshot()
                snapshot["guest_storage_trace"] = backend.guest_storage_trace_snapshot()
                snapshot["guest_msc_trace"] = backend.guest_msc_trace_snapshot()
                snapshot["guest_fs_probe_trace"] = backend.guest_fs_probe_trace_snapshot()
                snapshot["guest_progress_trace"] = backend.guest_progress_trace_snapshot()
                snapshot["guest_display_surface"] = backend.guest_display_surface_snapshot()
                snapshot["recent_event_queue_snapshots"] = []
            snapshot["qemu_auto_calibration_log"] = list(self.qemu_auto_calibration_log)
            snapshot["qemu_storage_bootstrap_log"] = list(self.qemu_storage_bootstrap_log)
            snapshot["qemu_limitations"] = [
                "QEMU bbk9588 models the default process, frame chardev, input chardev, timers, interrupts, GPIO/SADC touch state, and NAND-backed storage paths.",
                "Remaining work belongs in the QEMU SoC model, not in Python firmware hooks.",
            ]
        return snapshot

    def _publish_snapshot_locked(self) -> None:
        with self.status_lock:
            self.cached_status = self._build_snapshot_locked()
        self._notify_frontend_activity()

    def snapshot(self, *, detail: str = "compact") -> dict[str, object]:
        with self.lock:
            snapshot = self._build_snapshot_locked(detail=detail)
        with self.status_lock:
            self.cached_status = dict(snapshot)
        return snapshot

    def _apply_qemu_auto_calibration_locked(self, backend: QemuProcessBackend) -> None:
        """Feed cold-boot calibration touches through the QEMU input chardev."""

        if not getattr(self.args, "auto_calibration", False) or getattr(self.args, "boot_mode", "uboot") not in {"c200", "uboot"}:
            return
        if not backend.running():
            return
        if backend.config.machine.lower() == "bbk9588":
            self.qemu_storage_bootstrap_done = True
        elif not self.qemu_storage_bootstrap_done and self.qemu_storage_bootstrap_attempts < 4:
            self.qemu_storage_bootstrap_attempts += 1
            self.qemu_storage_bootstrap_log.append(
                {
                    "event": "qemu-storage-bootstrap",
                    "disabled": True,
                    "reason": "Python/GDB services were removed from the hardware-model path",
                    "handled_count": 0,
                }
            )
            del self.qemu_storage_bootstrap_log[:-16]
            if self.qemu_storage_bootstrap_attempts >= 4:
                self.qemu_storage_bootstrap_done = True
        if self.auto_calibration_stage >= 12:
            return
        now = time.time()
        if now - self.qemu_auto_calibration_last_action_at < 0.45:
            return
        qemu = backend.snapshot()
        pc_s = qemu.get("pc")
        try:
            pc = int(str(pc_s), 16)
        except Exception:
            pc = 0
        qemu_sample = qemu.get("register_sample") if isinstance(qemu.get("register_sample"), dict) else {}
        ra_s = qemu_sample.get("ra") if isinstance(qemu_sample, dict) else None
        try:
            ra = int(str(ra_s), 16)
        except Exception:
            ra = 0

        point_count = len(AUTO_CALIBRATION_TARGETS)
        gui: dict[str, object] = {}
        try:
            gui = backend.guest_gui_state_snapshot()
        except Exception as exc:
            gui = {"error": f"{type(exc).__name__}: {exc}"}

        if self.auto_calibration_stage >= point_count * 2:
            active = int(str(gui.get("active_object_80474048") or "0x0"), 16) if "error" not in gui else 0
            active_ready = bool(gui.get("active_object_ready"))
            modal = int(str(gui.get("modal_804a65c0") or "0x0"), 16) if "error" not in gui else 0
            if active == 0x80959670 or active_ready or "error" in gui:
                self.auto_calibration_stage = 12
                self.auto_calibration_last_stage_step += 1
                self.qemu_auto_calibration_last_action_at = now
                self.qemu_auto_calibration_log.append(
                    {
                        "event": "qemu-auto-calibration-complete",
                        "pc": f"0x{pc:08x}",
                        "ra": f"0x{ra:08x}",
                        "active": gui.get("active_object_80474048"),
                        "reason": "main-menu-active" if active == 0x80959670 else "calibration-touches-complete",
                    }
                )
                del self.qemu_auto_calibration_log[:-16]
                return
            if modal and self.auto_calibration_stage == point_count * 2:
                result = backend.apply_touch_state(AUTO_BOOT_DIALOG_X, AUTO_BOOT_DIALOG_Y, True)
                self.auto_calibration_stage = point_count * 2 + 1
                self.auto_calibration_last_stage_step += 1
                self.qemu_auto_calibration_last_action_at = now
                self.qemu_auto_calibration_log.append(
                    {
                        "event": "qemu-auto-dialog-touch",
                        "stage": self.auto_calibration_stage,
                        "down": True,
                        "x": AUTO_BOOT_DIALOG_X,
                        "y": AUTO_BOOT_DIALOG_Y,
                        "pc": f"0x{pc:08x}",
                        "modal": f"0x{modal:08x}",
                        "result": result,
                    }
                )
                del self.qemu_auto_calibration_log[:-16]
                return
            if modal and self.auto_calibration_stage == point_count * 2 + 1:
                result = backend.apply_touch_state(AUTO_BOOT_DIALOG_X, AUTO_BOOT_DIALOG_Y, False)
                self.auto_calibration_stage = point_count * 2 + 2
                self.auto_calibration_last_stage_step += 1
                self.qemu_auto_calibration_last_action_at = now
                self.qemu_auto_calibration_log.append(
                    {
                        "event": "qemu-auto-dialog-touch",
                        "stage": self.auto_calibration_stage,
                        "down": False,
                        "x": AUTO_BOOT_DIALOG_X,
                        "y": AUTO_BOOT_DIALOG_Y,
                        "pc": f"0x{pc:08x}",
                        "modal": f"0x{modal:08x}",
                        "result": result,
                    }
                )
                del self.qemu_auto_calibration_log[:-16]
            return

        if "error" not in gui:
            active = int(str(gui.get("active_object_80474048") or "0x0"), 16)
            modal = int(str(gui.get("modal_804a65c0") or "0x0"), 16)
            active_ready = bool(gui.get("active_object_ready"))
            if active_ready or modal:
                if active == 0x80959670:
                    self.auto_calibration_stage = 12
                    self.auto_calibration_last_stage_step += 1
                    self.qemu_auto_calibration_last_action_at = now
                    self.qemu_auto_calibration_log.append(
                        {
                            "event": "qemu-auto-calibration-complete",
                            "pc": f"0x{pc:08x}",
                            "ra": f"0x{ra:08x}",
                            "active": gui.get("active_object_80474048"),
                            "reason": "active-gui-before-next-calibration-touch",
                        }
                    )
                else:
                    self.qemu_auto_calibration_last_action_at = now
                    self.qemu_auto_calibration_log.append(
                        {
                            "event": "qemu-auto-calibration-abort-active-gui",
                            "stage": self.auto_calibration_stage,
                            "pc": f"0x{pc:08x}",
                            "ra": f"0x{ra:08x}",
                            "active": gui.get("active_object_80474048"),
                            "modal": gui.get("modal_804a65c0"),
                        }
                    )
                del self.qemu_auto_calibration_log[:-16]
                return

        in_touch_boot = 0x80017B74 <= pc <= 0x80019300 or 0x80017B74 <= ra <= 0x80019300
        if not in_touch_boot and pc != 0:
            return
        point_index = self.auto_calibration_stage // 2
        down = self.auto_calibration_stage % 2 == 0
        x, y = AUTO_CALIBRATION_TARGETS[point_index]
        result = backend.apply_touch_state(x, y, down)
        self.auto_calibration_stage += 1
        self.auto_calibration_last_stage_step += 1
        self.qemu_auto_calibration_last_action_at = now
        self.qemu_auto_calibration_log.append(
            {
                "event": "qemu-auto-calibration-touch",
                "stage": self.auto_calibration_stage,
                "point": point_index + 1,
                "down": down,
                "x": x,
                "y": y,
                "pc": f"0x{pc:08x}",
                "ra": f"0x{ra:08x}",
                "result": result,
            }
        )
        del self.qemu_auto_calibration_log[:-16]
