#!/usr/bin/env python3
"""Exercise the BBK 9588 frontend through HTTP and WebSocket like a user."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from typing import Callable

from emu.core.framebuffer import png_bytes_from_rgb, rgb565_raw_to_info_rgb
from emu.web.frontend_ws import WebSocketFrameReader, encode_ws_frame


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
DEFAULT_NAND = BUILD / "bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin"
WS_RAW_FRAME_MAGIC = b"BBKRAW1\0"
WS_RAW_FRAME_HEADER_SIZE = 20
WS_RAW_FRAME_FORMAT_RGB565 = 1


def ws_raw_frame_seq(payload: bytes) -> int | None:
    if payload.startswith(WS_RAW_FRAME_MAGIC) and len(payload) >= WS_RAW_FRAME_HEADER_SIZE:
        return int.from_bytes(payload[8:12], "little")
    return None


def find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def http_json(host: str, port: int, method: str, path: str, body: dict[str, object] | None = None) -> dict[str, object]:
    conn = http.client.HTTPConnection(host, port, timeout=30)
    raw = b"" if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, body=raw, headers=headers)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    if res.status >= 400:
        raise RuntimeError(f"{method} {path} returned HTTP {res.status}: {data[:200]!r}")
    return json.loads(data.decode("utf-8") or "{}")


def http_bytes(host: str, port: int, path: str) -> tuple[int, bytes]:
    conn = http.client.HTTPConnection(host, port, timeout=30)
    conn.request("GET", path)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    return res.status, data


def ws_frame_payload_to_png(payload: bytes, orientation: str) -> tuple[bytes, str]:
    if payload.startswith(WS_RAW_FRAME_MAGIC) and len(payload) >= WS_RAW_FRAME_HEADER_SIZE:
        seq = int.from_bytes(payload[8:12], "little")
        width = int.from_bytes(payload[12:14], "little")
        height = int.from_bytes(payload[14:16], "little")
        stride = int.from_bytes(payload[16:18], "little")
        pixel_format = int.from_bytes(payload[18:20], "little")
        raw = payload[WS_RAW_FRAME_HEADER_SIZE:]
        if pixel_format != WS_RAW_FRAME_FORMAT_RGB565:
            raise ValueError(f"unsupported raw WS frame format {pixel_format}")
        info, rgb = rgb565_raw_to_info_rgb(
            raw,
            0xA1F82000,
            0,
            width,
            height,
            stride,
            "rgb565",
            orientation,
        )
        info["dirty_seq"] = seq
        return png_bytes_from_rgb(int(info["output_width"]), int(info["output_height"]), rgb), "raw-rgb565"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return payload, "png"
    raise ValueError(f"unknown WS frame payload signature {payload[:12].hex()}")


class WebSocketClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = socket.create_connection((host, port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET /ws HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).encode("ascii")
        self.sock.sendall(request)
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            response += chunk
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"websocket handshake failed: {response[:200]!r}")
        self.sock.settimeout(0.25)
        self.reader = WebSocketFrameReader(self.sock)
        self.last_status: dict[str, object] = {}
        self.last_frame: bytes | None = None
        self.last_frame_payload: bytes | None = None
        self.last_frame_orientation = "rot180"
        self.last_frame_wire_kind = ""
        self.last_frame_seq: int | None = None
        self.frames = 0

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def send_json(self, msg: dict[str, object]) -> None:
        payload = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        self.sock.sendall(encode_ws_frame(0x1, payload, mask=os.urandom(4)))

    def send_command_async(self, msg: dict[str, object]) -> int:
        command = dict(msg)
        command_seq = int(time.time() * 1_000_000)
        command["command_seq"] = command_seq
        self.send_json(command)
        return command_seq

    def send_command(self, msg: dict[str, object], timeout: float = 3.0) -> dict[str, object] | None:
        command_seq = self.send_command_async(msg)
        return self.wait_for_command_seq(command_seq, timeout)

    def recv_one(self) -> tuple[str, object] | None:
        try:
            frame = self.reader.read_frame()
        except TimeoutError:
            return None
        except socket.timeout:
            return None
        if frame is None:
            return None
        opcode, payload = frame
        if opcode == 0x1:
            status = json.loads(payload.decode("utf-8"))
            if isinstance(status, dict):
                self.last_status = status
            return "json", status
        if opcode == 0x2:
            orientation = str(self.last_status.get("orientation") or "rot180")
            if payload.startswith(WS_RAW_FRAME_MAGIC) and len(payload) >= WS_RAW_FRAME_HEADER_SIZE:
                self.last_frame_wire_kind = "raw-rgb565"
                self.last_frame_seq = ws_raw_frame_seq(payload)
            elif payload.startswith(b"\x89PNG\r\n\x1a\n"):
                self.last_frame_wire_kind = "png"
                self.last_frame_seq = None
            else:
                self.last_frame_wire_kind = "unknown"
                self.last_frame_seq = None
            self.last_frame_payload = payload
            self.last_frame_orientation = orientation
            self.last_frame = None
            self.frames += 1
            return "frame", payload
        if opcode == 0x8:
            return "close", payload
        return "other", payload

    def current_frame_png(self) -> bytes | None:
        if self.last_frame is not None:
            return self.last_frame
        if self.last_frame_payload is None:
            return None
        self.last_frame, self.last_frame_wire_kind = ws_frame_payload_to_png(
            self.last_frame_payload,
            self.last_frame_orientation,
        )
        return self.last_frame

    def pump(self, seconds: float) -> None:
        deadline = time.time() + seconds
        while time.time() < deadline:
            self.recv_one()

    def wait_for(
        self,
        predicate: Callable[[dict[str, object]], bool],
        timeout: float,
        *,
        poll_status: Callable[[], dict[str, object]] | None = None,
    ) -> dict[str, object]:
        deadline = time.time() + timeout
        last_poll = 0.0
        while time.time() < deadline:
            self.recv_one()
            if predicate(self.last_status):
                return self.last_status
            now = time.time()
            if poll_status is not None and now - last_poll >= 2.0:
                self.last_status = poll_status()
                last_poll = now
                if predicate(self.last_status):
                    return self.last_status
        return self.last_status

    def wait_for_new_status(
        self,
        predicate: Callable[[dict[str, object]], bool],
        timeout: float,
        *,
        poll_status: Callable[[], dict[str, object]] | None = None,
    ) -> dict[str, object]:
        deadline = time.time() + timeout
        last_poll = 0.0
        while time.time() < deadline:
            item = self.recv_one()
            if item is not None and item[0] == "json" and predicate(self.last_status):
                return self.last_status
            now = time.time()
            if poll_status is not None and now - last_poll >= 2.0:
                polled = poll_status()
                last_poll = now
                if predicate(polled):
                    self.last_status = polled
                    return polled
        return self.last_status

    def wait_for_frame_after(self, previous_seq: int | None, timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            item = self.recv_one()
            if item is None or item[0] != "frame":
                continue
            if previous_seq is None:
                return True
            if self.last_frame_seq is None:
                return True
            if self.last_frame_seq != previous_seq:
                return True
        return False

    def wait_for_command_seq(self, command_seq: int, timeout: float) -> dict[str, object] | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            item = self.recv_one()
            if item is None or item[0] != "json":
                continue
            if self.last_status.get("_ws_command_seq") == command_seq:
                return self.last_status
        return None

    def wait_for_command_seen(
        self,
        command_seq: int,
        timeout: float,
        *,
        poll_status: Callable[[], dict[str, object]] | None = None,
    ) -> dict[str, object] | None:
        def seen(status: dict[str, object]) -> bool:
            ws = status.get("ws") if isinstance(status, dict) else None
            return isinstance(ws, dict) and ws.get("last_seq") == command_seq

        deadline = time.time() + timeout
        last_poll = 0.0
        while time.time() < deadline:
            item = self.recv_one()
            if item is not None and item[0] == "json" and seen(self.last_status):
                return self.last_status
            now = time.time()
            if poll_status is not None and now - last_poll >= 0.15:
                self.last_status = poll_status()
                last_poll = now
                if seen(self.last_status):
                    return self.last_status
        return self.last_status if seen(self.last_status) else None

    def wait_for_queue_drained(
        self,
        queue_name: str,
        timeout: float,
        *,
        poll_status: Callable[[], dict[str, object]] | None = None,
    ) -> dict[str, object]:
        def drained(status: dict[str, object]) -> bool:
            return int(status.get(queue_name) or 0) == 0

        deadline = time.time() + timeout
        last_poll = 0.0
        while time.time() < deadline:
            item = self.recv_one()
            if item is not None and item[0] == "json" and drained(self.last_status):
                return self.last_status
            now = time.time()
            if poll_status is not None and now - last_poll >= 0.15:
                self.last_status = poll_status()
                last_poll = now
                if drained(self.last_status):
                    return self.last_status
        return self.last_status


def start_frontend(args: argparse.Namespace, port: int) -> subprocess.Popen[bytes]:
    cmd = [
        sys.executable,
        str(ROOT / "emu" / "app.py"),
        "--host",
        args.host,
        "--port",
        str(port),
        "--worker-slice-seconds",
        str(args.worker_slice_seconds),
        "--frame-push-min-interval",
        str(args.frame_push_min_interval),
        "--quiet",
    ]
    nand_image = getattr(args, "nand_image", None)
    if nand_image is not None:
        cmd += ["--nand-image", str(nand_image)]
    if bool(getattr(args, "completed_step_timer", False)):
        cmd.append("--completed-step-timer")
    if bool(getattr(args, "completed_step_timer_after_auto_boot", False)):
        cmd.append("--completed-step-timer-after-auto-boot")
    if bool(getattr(args, "scheduler_tick_clamp", False)):
        cmd.append("--scheduler-tick-clamp")
    if bool(getattr(args, "no_cp0_status_accelerator", False)):
        cmd.append("--no-cp0-status-accelerator")
    if bool(getattr(args, "no_glyph_mask_accelerator", False)):
        cmd.append("--no-glyph-mask-accelerator")
    for pc in getattr(args, "trace_pc", []) or []:
        cmd += ["--trace-pc", f"0x{int(pc) & 0xFFFFFFFF:x}"]
    if bool(getattr(args, "trace_pc_detail", False)):
        cmd.append("--trace-pc-detail")
    state_in = getattr(args, "state_in", None)
    if state_in is not None:
        cmd += ["--state-in", str(state_in)]
    for spec in getattr(args, "mem_write_hex", []) or []:
        cmd += ["--mem-write-hex", str(spec)]
    for call in getattr(args, "scheduled_call", []) or []:
        if hasattr(call, "va"):
            call_va = int(call.va)
            call_args = tuple(call.args)
            idle_hit = int(call.idle_hit)
        else:
            call_va, call_args, idle_hit = call
            call_va = int(call_va)
            call_args = tuple(call_args)
            idle_hit = int(idle_hit)
        arg_count = len(call_args)
        while arg_count > 0 and int(call_args[arg_count - 1]) == 0:
            arg_count -= 1
        args_text = ":".join(f"0x{value & 0xFFFFFFFF:x}" for value in call_args[:arg_count])
        call_text = f"0x{call_va:x}"
        if args_text:
            call_text += f":{args_text}"
        call_text += f"@{idle_hit}"
        cmd += ["--scheduled-call", call_text]
    profile_out = getattr(args, "frontend_profile_out", None)
    if profile_out is not None:
        cmd += ["--profile-out", str(profile_out)]
    worker_profile_out = getattr(args, "worker_profile_out", None)
    if worker_profile_out is not None:
        cmd += ["--worker-profile-out", str(worker_profile_out)]
    if bool(getattr(args, "hot_path_stats", False)):
        cmd.append("--hot-path-stats")
    return subprocess.Popen(
        cmd,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_http(host: str, port: int, timeout: float) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            http_json(host, port, "GET", "/api/status")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"frontend did not become ready: {last_error}")


def summarize_status(status: dict[str, object]) -> dict[str, object]:
    fb = status.get("framebuffer") if isinstance(status.get("framebuffer"), dict) else {}
    job = status.get("job") if isinstance(status.get("job"), dict) else {}
    scheduler = status.get("scheduler") if isinstance(status.get("scheduler"), dict) else {}
    return {
        "running": status.get("running"),
        "pc": status.get("pc"),
        "stop_reason": status.get("stop_reason"),
        "auto_calibration_stage": status.get("auto_calibration_stage"),
        "auto_calibration_stage_label": status.get("auto_calibration_stage_label"),
        "pending_touches": status.get("pending_touches"),
        "pending_keys": status.get("pending_keys"),
        "input_wake_count": status.get("input_wake_count"),
        "nonzero_pixels": fb.get("nonzero_pixels"),
        "unique_pixel_values": fb.get("unique_pixel_values"),
        "job": {
            "name": job.get("name"),
            "status": job.get("status"),
            "done_steps": job.get("done_steps"),
            "observed_insn_delta": job.get("observed_insn_delta"),
            "steps_per_second": job.get("steps_per_second"),
            "requested_steps_per_second": job.get("requested_steps_per_second"),
        },
        "accelerators": status.get("accelerators"),
        "perf": status.get("perf"),
        "memcpy_bulk_callers": status.get("memcpy_bulk_callers"),
        "store_delay_branch_counts": status.get("store_delay_branch_counts"),
        "on_code_dispatch_counts": status.get("on_code_dispatch_counts"),
        "block_dispatch_counts": status.get("block_dispatch_counts"),
        "recoveries": status.get("recoveries"),
        "trace_pc": status.get("trace_pc"),
        "scheduler": scheduler,
        "tasks": status.get("tasks"),
        "event_queue": status.get("event_queue"),
        "display_event_queue": status.get("display_event_queue"),
        "recent_event_queue_snapshots": status.get("recent_event_queue_snapshots"),
        "recent_gui_ring_pump_events": status.get("recent_gui_ring_pump_events"),
        "frame_push": status.get("frame_push"),
        "ws": status.get("ws"),
    }


def looks_like_menu(status: dict[str, object]) -> bool:
    fb = status.get("framebuffer") if isinstance(status.get("framebuffer"), dict) else {}
    return (
        int(status.get("auto_calibration_stage") or 0) >= 12
        and int(fb.get("nonzero_pixels") or 0) >= 25000
        and int(fb.get("unique_pixel_values") or 0) >= 2500
    )


def looks_like_menu_family(status: dict[str, object]) -> bool:
    fb = status.get("framebuffer") if isinstance(status.get("framebuffer"), dict) else {}
    nonzero = int(fb.get("nonzero_pixels") or 0)
    unique = int(fb.get("unique_pixel_values") or 0)
    return int(status.get("auto_calibration_stage") or 0) >= 12 and nonzero >= 25000 and unique >= 2500


def write_png(path: Path, data: bytes | None) -> str | None:
    if not data:
        return None
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def fetch_screen_digest(host: str, port: int) -> tuple[int, bytes, str]:
    status_code, png = http_bytes(host, port, "/screen.png")
    digest = hashlib.sha256(png).hexdigest() if status_code == 200 else ""
    return status_code, png, digest


def wait_screen_digest(
    host: str,
    port: int,
    predicate: Callable[[str], bool],
    timeout: float,
) -> tuple[int, bytes, str]:
    deadline = time.time() + timeout
    last: tuple[int, bytes, str] = (0, b"", "")
    while time.time() < deadline:
        last = fetch_screen_digest(host, port)
        if predicate(last[2]):
            return last
        time.sleep(0.4)
    return last


def current_ws_screen_digest(ws: WebSocketClient) -> tuple[int, bytes, str]:
    png = ws.current_frame_png() or b""
    digest = hashlib.sha256(png).hexdigest() if png else ""
    return (200 if png else 0), png, digest


def wait_ws_screen_digest(
    ws: WebSocketClient,
    predicate: Callable[[str], bool],
    timeout: float,
) -> tuple[int, bytes, str]:
    last = current_ws_screen_digest(ws)
    if predicate(last[2]):
        return last
    deadline = time.time() + timeout
    while time.time() < deadline:
        item = ws.recv_one()
        if item is None:
            continue
        kind, payload = item
        if kind != "frame":
            continue
        png = ws.current_frame_png() or b""
        digest = hashlib.sha256(png).hexdigest() if png else ""
        last = (200 if png else 0), png, digest
        if predicate(digest):
            return last
    return last


def tap(
    ws: WebSocketClient,
    x: int,
    y: int,
    *,
    poll_status: Callable[[], dict[str, object]] | None = None,
) -> None:
    base = {
        "op": "touch",
        "display_x": x,
        "display_y": y,
        "display_width": 240,
        "display_height": 320,
        "advance": False,
        "run": True,
    }
    down = dict(base)
    down["down"] = True
    down["phase"] = "down"
    down_seq = ws.send_command_async(down)
    ws.wait_for_command_seen(down_seq, 3, poll_status=poll_status)
    ws.wait_for_queue_drained("pending_touches", 5, poll_status=poll_status)
    up = dict(base)
    up["down"] = False
    up["phase"] = "up"
    up_seq = ws.send_command_async(up)
    ws.wait_for_command_seen(up_seq, 3, poll_status=poll_status)
    ws.wait_for_queue_drained("pending_touches", 5, poll_status=poll_status)


def key_press(
    ws: WebSocketClient,
    code: int,
    *,
    poll_status: Callable[[], dict[str, object]] | None = None,
) -> None:
    down_seq = ws.send_command_async({"op": "key", "code": code, "down": True, "advance": False, "run": True})
    ws.wait_for_command_seen(down_seq, 3, poll_status=poll_status)
    ws.wait_for_queue_drained("pending_keys", 5, poll_status=poll_status)
    up_seq = ws.send_command_async({"op": "key", "code": code, "down": False, "advance": False, "run": True})
    ws.wait_for_command_seen(up_seq, 3, poll_status=poll_status)
    ws.wait_for_queue_drained("pending_keys", 5, poll_status=poll_status)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a user-like web frontend smoke test over HTTP and WebSocket.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="Use 0 to start a private frontend on a free port.")
    ap.add_argument("--use-existing", action="store_true", help="Connect to an already running frontend instead of starting one.")
    ap.add_argument("--nand-image", type=Path, default=None, help="Override app.py's default NAND image.")
    ap.add_argument("--out-dir", type=Path, default=BUILD)
    ap.add_argument("--prefix", default="hwemu_frontend_web_smoke")
    ap.add_argument("--boot-timeout", type=int, default=480)
    ap.add_argument("--chunk-steps", type=int, default=250000)
    ap.add_argument("--worker-slice-seconds", type=float, default=0.25)
    ap.add_argument("--frame-push-min-interval", type=float, default=0.04)
    ap.add_argument("--completed-step-timer", action="store_true", default=False)
    ap.add_argument("--completed-step-timer-after-auto-boot", action="store_true", default=False)
    ap.add_argument("--no-cp0-status-accelerator", action="store_true", default=False)
    ap.add_argument("--no-glyph-mask-accelerator", action="store_true", default=False)
    ap.add_argument(
        "--interaction-frame-timeout",
        type=float,
        default=1.0,
        help="Maximum seconds to wait for a new WS frame after a tap when status alone is not enough.",
    )
    ns = ap.parse_args(argv)

    ns.out_dir.mkdir(parents=True, exist_ok=True)
    port = ns.port or find_free_port(ns.host)
    proc: subprocess.Popen[bytes] | None = None
    ws: WebSocketClient | None = None
    failures: list[str] = []
    interactions: list[dict[str, object]] = []
    screenshots: dict[str, dict[str, object]] = {}
    logs: dict[str, object] = {}
    menu_elapsed_seconds: float | None = None
    start = time.time()
    try:
        if not ns.use_existing:
            proc = start_frontend(ns, port)
        wait_http(ns.host, port, 30)
        html_status, html = http_bytes(ns.host, port, "/")
        if html_status != 200 or b"<canvas" not in html:
            failures.append("frontend HTML did not load or canvas was missing")

        ws = WebSocketClient(ns.host, port)
        ws.pump(0.2)
        interactions.append({"step": "connect", "status": summarize_status(ws.last_status), "frames": ws.frames})

        reset_started = time.time()
        reset_reply = ws.send_command({"op": "reset"}, timeout=5)
        interactions.append(
            {
                "step": "reset",
                "elapsed_seconds": round(time.time() - reset_started, 3),
                "status": summarize_status(reset_reply or ws.last_status),
            }
        )

        auto_started = time.time()
        auto_reply = ws.send_command({"op": "auto-calibration", "enabled": True}, timeout=3)
        interactions.append(
            {
                "step": "enable-auto-calibration",
                "elapsed_seconds": round(time.time() - auto_started, 3),
                "status": summarize_status(auto_reply or ws.last_status),
            }
        )

        ws.send_json({"op": "run-start", "name": "web-human-smoke", "steps": 0, "chunk": ns.chunk_steps})
        menu_status = ws.wait_for(
            looks_like_menu,
            ns.boot_timeout,
            poll_status=lambda: http_json(ns.host, port, "GET", "/api/status"),
        )
        menu_elapsed_seconds = time.time() - start
        interactions.append(
            {
                "step": "wait-menu",
                "elapsed_seconds": round(menu_elapsed_seconds, 3),
                "status": summarize_status(menu_status),
                "frames": ws.frames,
            }
        )
        boot_ok = looks_like_menu(menu_status)
        if not boot_ok:
            failures.append("cold boot did not reach a menu-looking framebuffer through the web worker")
            ws.send_json({"op": "stop"})
            ws.pump(1.0)
            stopped = http_json(ns.host, port, "GET", "/api/status")
            interactions.append({"step": "stop-after-boot-failure", "status": summarize_status(stopped)})
            logs = http_json(ns.host, port, "GET", "/api/logs?limit=80")
        else:
            status_code, menu_png, menu_digest = current_ws_screen_digest(ws)
            home_digests = {menu_digest} if menu_digest else set()
            if status_code == 200:
                digest = write_png(ns.out_dir / f"{ns.prefix}_menu.png", menu_png)
                screenshots["menu"] = {"path": str(ns.out_dir / f"{ns.prefix}_menu.png"), "sha256": digest}

            category_points = [
                ("exam", 24, 286),
                ("recite", 72, 286),
                ("dictionary", 120, 286),
                ("entertainment", 168, 286),
                ("tools", 210, 287),
            ]
            home_points = [(38, 306), (202, 306)]
            changed_categories = 0
            poll_status = lambda: http_json(ns.host, port, "GET", "/api/status")
            for name, x, y in category_points:
                step_started = time.time()
                before_seq = ws.last_frame_seq
                tap(ws, x, y, poll_status=poll_status)
                frame_advanced = ws.wait_for_frame_after(before_seq, ns.interaction_frame_timeout)
                status_code, png, digest = current_ws_screen_digest(ws)
                changed = bool(digest and digest != menu_digest)
                changed_categories += 1 if changed or frame_advanced else 0
                out_path = ns.out_dir / f"{ns.prefix}_tap_{name}.png"
                if status_code == 200:
                    out_path.write_bytes(png)
                    screenshots[f"tap_{name}"] = {"path": str(out_path), "sha256": digest}
                tap_status = http_json(ns.host, port, "GET", "/api/status")
                interactions.append(
                    {
                        "step": f"tap-{name}",
                        "elapsed_seconds": round(time.time() - step_started, 3),
                        "display": [x, y],
                        "frame_advanced": frame_advanced,
                        "frame_seq": ws.last_frame_seq,
                        "changed_from_menu": changed,
                        "png": str(out_path) if status_code == 200 else None,
                        "sha256": digest,
                        "status": summarize_status(tap_status),
                    }
                )
                if not changed and not frame_advanced:
                    interactions.append(
                        {
                            "step": f"tap-{name}-unchanged",
                            "note": "category tap did not produce a new WS frame or distinct menu baseline digest",
                            "status": summarize_status(http_json(ns.host, port, "GET", "/api/status")),
                        }
                    )
                    continue
                returned_home = False
                home_digest = ""
                for index, (home_x, home_y) in enumerate(home_points, 1):
                    home_started = time.time()
                    before_seq = ws.last_frame_seq
                    tap(ws, home_x, home_y, poll_status=poll_status)
                    home_status = http_json(ns.host, port, "GET", "/api/status")
                    home_like = looks_like_menu_family(home_status)
                    frame_advanced = False
                    if not home_like:
                        frame_advanced = ws.wait_for_frame_after(before_seq, ns.interaction_frame_timeout)
                        home_status = http_json(ns.host, port, "GET", "/api/status")
                        home_like = looks_like_menu_family(home_status)
                    _home_status, _home_png, home_digest = current_ws_screen_digest(ws)
                    returned = bool(home_digest and home_digest in home_digests) or home_like
                    interactions.append(
                        {
                            "step": f"home-after-{name}-{index}",
                            "elapsed_seconds": round(time.time() - home_started, 3),
                            "display": [home_x, home_y],
                            "frame_advanced": frame_advanced,
                            "frame_seq": ws.last_frame_seq,
                            "returned_to_menu": returned,
                            "sha256": home_digest,
                            "status": summarize_status(home_status),
                        }
                    )
                    if returned:
                        if home_digest:
                            home_digests.add(home_digest)
                        returned_home = True
                        break
                if not returned_home:
                    cancel_started = time.time()
                    before_seq = ws.last_frame_seq
                    key_press(ws, 9, poll_status=poll_status)
                    cancel_status = http_json(ns.host, port, "GET", "/api/status")
                    frame_advanced = False
                    if not looks_like_menu_family(cancel_status):
                        frame_advanced = ws.wait_for_frame_after(before_seq, ns.interaction_frame_timeout)
                        cancel_status = http_json(ns.host, port, "GET", "/api/status")
                    _home_status, _home_png, home_digest = current_ws_screen_digest(ws)
                    returned = bool(home_digest and home_digest in home_digests) or looks_like_menu_family(cancel_status)
                    interactions.append(
                        {
                            "step": f"cancel-after-{name}",
                            "elapsed_seconds": round(time.time() - cancel_started, 3),
                            "frame_advanced": frame_advanced,
                            "frame_seq": ws.last_frame_seq,
                            "returned_to_menu": returned,
                            "sha256": home_digest,
                            "status": summarize_status(cancel_status),
                        }
                    )
                    if returned and home_digest:
                        home_digests.add(home_digest)
                    returned_home = returned
                if not returned_home:
                    interactions.append(
                        {
                            "step": f"return-after-{name}-not-menu-like",
                            "note": "continuing category coverage from current screen",
                            "status": summarize_status(http_json(ns.host, port, "GET", "/api/status")),
                        }
                    )
            if changed_categories == 0:
                failures.append("bottom category taps did not advance framebuffer frames")

            for code, name in [(4, "up"), (5, "down"), (6, "left"), (7, "right"), (9, "cancel"), (10, "ok")]:
                key_press(ws, code, poll_status=poll_status)
                status = ws.wait_for(
                    lambda s: int(s.get("pending_keys") or 0) == 0,
                    8,
                    poll_status=poll_status,
                )
                interactions.append({"step": f"key-{name}", "code": code, "status": summarize_status(status)})
                if int(status.get("pending_keys") or 0) != 0:
                    failures.append(f"key {name} left pending_keys={status.get('pending_keys')}")

            stop_seq = int(time.time() * 1000)
            ws.send_json({"op": "stop", "command_seq": stop_seq})
            stop_reply = ws.wait_for_command_seq(stop_seq, 5)
            stopped = stop_reply or ws.last_status
            if stop_reply is None or stopped.get("running"):
                interactions.append(
                    {
                        "step": "ws-stop-timeout",
                        "command_seq": stop_seq,
                        "reply_seen": stop_reply is not None,
                        "status": summarize_status(stopped),
                    }
                )
                stopped = http_json(ns.host, port, "POST", "/api/command", {"op": "stop"})
                deadline = time.time() + 5
                while stopped.get("running") and time.time() < deadline:
                    time.sleep(0.2)
                    stopped = http_json(ns.host, port, "GET", "/api/status")
            interactions.append({"step": "stop", "status": summarize_status(stopped)})
            if stopped.get("running"):
                failures.append("stop command left frontend running")

            logs = http_json(ns.host, port, "GET", "/api/logs?limit=80")
    finally:
        if ws is not None:
            ws.close()
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        elapsed = time.time() - start

    summary = {
        "ok": not failures,
        "host": ns.host,
        "port": port,
        "used_existing": ns.use_existing,
        "elapsed_seconds": round(elapsed, 3),
        "menu_elapsed_seconds": None if menu_elapsed_seconds is None else round(menu_elapsed_seconds, 3),
        "failures": failures,
        "screenshots": screenshots,
        "last_frame_wire_kind": None if ws is None else ws.last_frame_wire_kind,
        "interactions": interactions,
        "log_count": logs.get("count"),
        "recent_logs": logs.get("events", []),
    }
    json_path = ns.out_dir / f"{ns.prefix}_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report_path = ns.out_dir / f"{ns.prefix}_report.md"
    lines = [
        "# Frontend Web Smoke Report",
        "",
        f"- Result: {'PASS' if summary['ok'] else 'FAIL'}",
        f"- URL: http://{ns.host}:{port}/",
        f"- Elapsed seconds: {summary['elapsed_seconds']}",
        f"- Menu elapsed seconds: {summary['menu_elapsed_seconds']}",
        f"- Frames received over WS: {ws.frames if ws is not None else 0}",
        f"- Last WS frame wire kind: {None if ws is None else ws.last_frame_wire_kind}",
        f"- Failures: {len(failures)}",
        "",
        "## Interactions",
    ]
    for item in interactions:
        extras: list[str] = []
        if "elapsed_seconds" in item:
            extras.append(f"elapsed={item['elapsed_seconds']}s")
        if "frame_advanced" in item:
            extras.append(f"frame_advanced={item['frame_advanced']}")
        if "frame_seq" in item:
            extras.append(f"frame_seq={item['frame_seq']}")
        prefix = "" if not extras else f" ({', '.join(extras)})"
        lines.append(f"- {item['step']}{prefix}: `{json.dumps(item.get('status', {}), ensure_ascii=False)}`")
    if failures:
        lines += ["", "## Failures"]
        lines += [f"- {failure}" for failure in failures]
    lines += [
        "",
        "## Notes",
        "- This smoke drives the frontend through HTTP and WebSocket, not direct Python state calls.",
        "- Touches use rendered display coordinates and rely on the frontend orientation mapping.",
        "- Category coverage is raw-frame-sequence based; screenshots are converted only when recorded.",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"ok": summary["ok"], "summary": str(json_path), "report": str(report_path), "failures": failures}, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
