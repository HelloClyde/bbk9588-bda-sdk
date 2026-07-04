#!/usr/bin/env python3
"""Run hardware-emulator refactor regression checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
HWEMU = Path("reverse") / "hwemu" / "bbk9588_hwemu.py"

PY_COMPILE_FILES = [
    Path("reverse") / "hwemu" / name
    for name in (
        "hwemu_defs.py",
        "hwemu_utils.py",
        "hwemu_engine.py",
        "hwemu_hook_policy.py",
        "hwemu_framebuffer.py",
        "hwemu_surface.py",
        "hwemu_input.py",
        "hwemu_fastpaths.py",
        "hwemu_devices.py",
        "hwemu_interrupts.py",
        "hwemu_tasks.py",
        "hwemu_trace.py",
        "hwemu_state.py",
        "hwemu_cli.py",
        "bbk9588_hwemu.py",
        "hwemu_frontend_ws.py",
        "hwemu_frontend_server.py",
        "hwemu_frontend_state.py",
        "hwemu_frontend.py",
        "run_bda_smoke.py",
        "run_cold_boot_to_menu_smoke.py",
        "run_frontend_web_smoke.py",
        "run_thunder_web_smoke.py",
        "run_system_menu_smoke.py",
        "run_time_dialog_to_menu_smoke.py",
    )
]


def find_c200() -> Path:
    matches = sorted(ROOT.rglob("C200.bin"))
    if not matches:
        raise FileNotFoundError("C200.bin not found under workspace")
    return matches[0]


def first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def run_command(name: str, cmd: list[str], timeout: int) -> dict[str, object]:
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    elapsed = time.perf_counter() - start
    row: dict[str, object] = {
        "name": name,
        "command": cmd,
        "returncode": proc.returncode,
        "elapsed_seconds": round(elapsed, 3),
        "stdout_tail": proc.stdout[-4000:],
        "ok": proc.returncode == 0,
    }
    return row


def load_execution(json_path: Path) -> dict[str, object]:
    report = json.loads(json_path.read_text(encoding="utf-8"))
    execution = report.get("execution")
    if not isinstance(execution, dict):
        raise ValueError(f"{json_path} has no execution object")
    return execution


def add_cli_short_boot(rows: list[dict[str, object]], c200: Path, nand_image: Path, timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_cli_short_boot.json"
    png_out = BUILD / "hwemu_regression_cli_short_boot.png"
    state_out = BUILD / "hwemu_regression_cli_short_boot.pkl"
    cmd = [
        sys.executable,
        str(HWEMU),
        "--profile",
        "bbk9588-uboot",
        "--image",
        str(c200),
        "--base",
        "0x80004000",
        "--pc",
        "0x80004000",
        "--ram-mb",
        "160",
        "--json-out",
        str(json_out),
        "--fb-dump",
        str(png_out),
        "--state-out",
        str(state_out),
        "--max-seconds",
        "8",
        "--steps",
        "500000",
        "--fast-hooks",
        "--nand-loop-accelerator",
        "--resource-cache16-accelerator",
        "--no-block-image",
        "--nand-image",
        str(nand_image),
        "--trace-limit",
        "256",
        "--fb-width",
        "240",
        "--fb-height",
        "320",
        "--quiet",
    ]
    row = run_command("old-cli-short-boot", cmd, timeout)
    row.update({"json": str(json_out), "png": str(png_out), "state_out": str(state_out)})
    failures: list[str] = []
    if row["ok"]:
        execution = load_execution(json_out)
        row["stop_reason"] = execution.get("stop_reason")
        row["invalid_count"] = len(execution.get("invalid", []))
        if row["invalid_count"] != 0:
            failures.append("invalid memory accesses were recorded")
        if not state_out.is_file() or state_out.stat().st_size <= 0:
            failures.append("state checkpoint was not written")
    else:
        failures.append("old CLI entry returned nonzero")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_key_pulse_parse(rows: list[dict[str, object]], c200: Path, timeout: int) -> None:
    cmd = [
        sys.executable,
        str(HWEMU),
        "--profile",
        "bbk9588-uboot",
        "--image",
        str(c200),
        "--base",
        "0x80004000",
        "--pc",
        "0x80004000",
        "--ram-mb",
        "160",
        "--steps",
        "1",
        "--max-seconds",
        "1",
        "--fast-hooks",
        "--no-json-out",
        "--quiet",
        "--key-pulse",
        "7@1:1",
    ]
    row = run_command("key-pulse-parse", cmd, timeout)
    if not row["ok"]:
        row["failures"] = ["--key-pulse command returned nonzero"]
    rows.append(row)


def add_frontend_state_defaults(rows: list[dict[str, object]], timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_frontend_state.json"
    script = f"""
import argparse, json, sys
from pathlib import Path
root = Path(r'{ROOT}')
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_frontend import FrontendState
args = argparse.Namespace(
    host='127.0.0.1',
    port=9588,
    ram_mb=160,
    trace_limit=5000,
    boot_steps=30_000_000,
    input_steps=500_000,
    worker_slice_steps=250_000,
    worker_slice_seconds=0.5,
    frame_push_min_interval=0.08,
    boot_mode='c200',
    state_in=None,
    nand_image=None,
    nand_loop_accelerator=True,
    resource_cache16_accelerator=True,
    auto_calibration=False,
    slow_global_code_hook=False,
    block_image=False,
    scheduler_tick_clamp=False,
    key_input_mode='hardware',
    orientation='rot180',
    quiet=True,
)
state = FrontendState(args)
snap = state.snapshot()
full_snap = state.snapshot(detail='full')
for idx in range(20):
    state.emu.state.events.append({{'kind': 'event-tail-probe', 'idx': str(idx)}})
with state.lock:
    state._publish_snapshot_locked()
event_tail_snap = state.snapshot()
logs_tail = state.logs(5)
toggle_snap = state.command({{'op': 'auto-calibration', 'enabled': True}})
hook_pcs = state.emu._fast_code_hook_pcs()
legacy_calibration_pcs = [0x80017CB4, 0x80017D54, 0x80017DE8, 0x80018C58, 0x80018DAC]
out = {{
    'key_input_mode': snap.get('key_input_mode'),
    'auto_calibration_initial': snap.get('auto_calibration'),
    'auto_calibration_after_toggle': toggle_snap.get('auto_calibration'),
    'busy_delay_static_patch': snap.get('busy_delay_static_patch'),
    'busy_delay_hook_registered': 0x800043A0 in hook_pcs,
    'legacy_calibration_hooks_registered': [pc for pc in legacy_calibration_pcs if pc in hook_pcs],
    'reset_elapsed_seconds': snap.get('reset_elapsed_seconds'),
    'run_elapsed_seconds': snap.get('run_elapsed_seconds'),
    'worker_slice_steps': args.worker_slice_steps,
    'nand_loop_accelerator': args.nand_loop_accelerator,
    'trace_pc_detail': state.emu.trace_pc_detail,
    'running': snap.get('running'),
    'compact_scheduler_has_raw': 'raw_80473f00_7f' in (snap.get('scheduler') or {{}}),
    'full_scheduler_has_raw': 'raw_80473f00_7f' in (full_snap.get('scheduler') or {{}}),
    'compact_timer_events': len((snap.get('scheduler') or {{}}).get('gui_timer_events') or []),
    'full_detail': full_snap.get('detail'),
    'event_tail_len': len(event_tail_snap.get('events') or []),
    'event_tail_first_idx': (event_tail_snap.get('events') or [{{}}])[0].get('idx'),
    'event_tail_last_idx': (event_tail_snap.get('events') or [{{}}])[-1].get('idx'),
    'logs_count': logs_tail.get('count'),
    'logs_len': len(logs_tail.get('events') or []),
    'logs_first_idx': (logs_tail.get('events') or [{{}}])[0].get('idx'),
    'logs_last_idx': (logs_tail.get('events') or [{{}}])[-1].get('idx'),
}}
Path(r'{json_out}').write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("frontend-state-defaults", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        if data.get("key_input_mode") != "hardware":
            failures.append(f"key_input_mode is {data.get('key_input_mode')}, expected hardware")
        if data.get("worker_slice_steps") != 250_000:
            failures.append(f"worker_slice_steps is {data.get('worker_slice_steps')}, expected 250000")
        if data.get("nand_loop_accelerator") is not True:
            failures.append("nand_loop_accelerator should default to enabled for frontend cold boot")
        if data.get("auto_calibration_initial") is not False:
            failures.append("frontend auto-calibration should default to disabled")
        if data.get("auto_calibration_after_toggle") is not True:
            failures.append("frontend auto-calibration command did not enable the runtime switch")
        if data.get("busy_delay_static_patch") is not True:
            failures.append("frontend fast-hooks should statically patch the busy-delay helper")
        if data.get("busy_delay_hook_registered") is not False:
            failures.append("busy-delay helper should not also be registered as a code hook after static patch")
        if data.get("legacy_calibration_hooks_registered"):
            failures.append(
                "legacy calibration observation hooks should not be registered by default: "
                + ",".join(f"0x{pc:08x}" for pc in data.get("legacy_calibration_hooks_registered", []))
            )
        if data.get("trace_pc_detail") is not False:
            failures.append("frontend should count trace PCs without detailed register snapshots")
        if not isinstance(data.get("reset_elapsed_seconds"), (int, float)):
            failures.append("reset_elapsed_seconds missing from frontend snapshot")
        if data.get("run_elapsed_seconds") is not None:
            failures.append("run_elapsed_seconds should be None before a run starts")
        if data.get("running") is not False:
            failures.append("frontend should not be running immediately after reset")
        if data.get("compact_scheduler_has_raw") is not False:
            failures.append("compact frontend snapshot should omit raw scheduler bytes")
        if data.get("compact_timer_events") != 0:
            failures.append("compact frontend snapshot should omit gui_timer_events")
        if data.get("full_scheduler_has_raw") is not True:
            failures.append("full frontend snapshot should include raw scheduler bytes")
        if data.get("full_detail") != "full":
            failures.append("full frontend snapshot should be marked detail=full")
        if data.get("event_tail_len") != 8 or data.get("event_tail_first_idx") != "12" or data.get("event_tail_last_idx") != "19":
            failures.append(
                "compact frontend snapshot should keep only the last 8 events, got "
                f"len={data.get('event_tail_len')} first={data.get('event_tail_first_idx')} last={data.get('event_tail_last_idx')}"
            )
        if data.get("logs_count") != 20 or data.get("logs_len") != 5 or data.get("logs_first_idx") != "15" or data.get("logs_last_idx") != "19":
            failures.append(
                "frontend logs(limit) should report full count and return only the requested tail, got "
                f"count={data.get('logs_count')} len={data.get('logs_len')} first={data.get('logs_first_idx')} last={data.get('logs_last_idx')}"
            )
    else:
        failures.append("frontend state defaults command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_frontend_touch_mapping(rows: list[dict[str, object]], timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_frontend_touch_mapping.json"
    script = f"""
import argparse, json, sys
from pathlib import Path
root = Path(r'{ROOT}')
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_frontend import FrontendState, display_to_panel_point, display_to_raw_point, display_to_touch_point, raw_to_display_point

logical_cases = {{
    'raw_topleft': display_to_raw_point(0, 0, 240, 320, 'raw'),
    'rot180_topleft': display_to_raw_point(0, 0, 240, 320, 'rot180'),
    'rot180_bottomright': display_to_raw_point(239, 319, 240, 320, 'rot180'),
    'rot180_scaled_bottomright': display_to_raw_point(479, 639, 480, 640, 'rot180'),
    'hflip_topleft': display_to_raw_point(0, 0, 240, 320, 'hflip'),
    'vflip_topleft': display_to_raw_point(0, 0, 240, 320, 'vflip'),
    'cw90_topleft': display_to_raw_point(0, 0, 320, 240, 'cw90'),
    'ccw90_bottomright': display_to_raw_point(319, 239, 320, 240, 'ccw90'),
}}
panel_cases = {{
    'visible_topleft': display_to_panel_point(0, 0, 240, 320),
    'visible_bottomright': display_to_panel_point(239, 319, 240, 320),
    'visible_scaled_bottomright': display_to_panel_point(479, 639, 480, 640),
}}
touch_cases = {{
    'rot180_visible_topleft': display_to_touch_point(0, 0, 240, 320, 'rot180'),
    'rot180_visible_bottomright': display_to_touch_point(239, 319, 240, 320, 'rot180'),
    'rot180_scaled_bottomright': display_to_touch_point(479, 639, 480, 640, 'rot180'),
}}
logical_to_visible_cases = {{
    'rot180_calib_left': raw_to_display_point(10, 10, 'rot180'),
    'rot180_dialog_no': raw_to_display_point(150, 205, 'rot180'),
}}
args = argparse.Namespace(
    host='127.0.0.1',
    port=9588,
    ram_mb=160,
    trace_limit=5000,
    boot_steps=30_000_000,
    input_steps=500_000,
    worker_slice_steps=250_000,
    worker_slice_seconds=0.5,
    frame_push_min_interval=0.08,
    boot_mode='c200',
    state_in=None,
    nand_image=None,
    nand_loop_accelerator=True,
    resource_cache16_accelerator=True,
    auto_calibration=True,
    slow_global_code_hook=False,
    block_image=False,
    scheduler_tick_clamp=False,
    key_input_mode='hardware',
    orientation='rot180',
    quiet=True,
)
state = FrontendState(args)
before_global_x = state.emu._read_u32_va_safe(0x80370FC8)
before_global_y = state.emu._read_u32_va_safe(0x80370FCC)
state.emu.set_touch_controller_state(120, 160, True)
after_global_x = state.emu._read_u32_va_safe(0x80370FC8)
after_global_y = state.emu._read_u32_va_safe(0x80370FCC)
touch_raw_x = state.emu._touch_adc_raw(0)
touch_raw_y = state.emu._touch_adc_raw(1)
state.command({{
    'op': 'touch',
    'display_x': 0,
    'display_y': 0,
    'display_width': 240,
    'display_height': 320,
    'down': True,
    'advance': False,
}})
state.command({{
    'op': 'touch',
    'display_x': 239,
    'display_y': 319,
    'display_width': 240,
    'display_height': 320,
    'down': False,
    'advance': False,
}})
with state.input_lock:
    queued = list(state.pending_touches)
out = {{
    'logical_cases': {{name: list(value) for name, value in logical_cases.items()}},
    'panel_cases': {{name: list(value) for name, value in panel_cases.items()}},
    'touch_cases': {{name: list(value) for name, value in touch_cases.items()}},
    'logical_to_visible_cases': {{name: list(value) for name, value in logical_to_visible_cases.items()}},
    'queued': [list(item) for item in queued],
    'pending_touches': state.snapshot().get('pending_touches'),
    'orientation': state.snapshot().get('orientation'),
    'hardware_touch_globals_unchanged': before_global_x == after_global_x and before_global_y == after_global_y,
    'hardware_touch_raw': [touch_raw_x, touch_raw_y],
}}
Path(r'{json_out}').write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("frontend-touch-mapping", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        expected_cases = {
            "raw_topleft": [0, 0],
            "rot180_topleft": [239, 319],
            "rot180_bottomright": [0, 0],
            "rot180_scaled_bottomright": [0, 0],
            "hflip_topleft": [239, 0],
            "vflip_topleft": [0, 319],
            "cw90_topleft": [0, 319],
            "ccw90_bottomright": [0, 319],
        }
        for name, expected in expected_cases.items():
            if data.get("logical_cases", {}).get(name) != expected:
                failures.append(f"{name} mapped to {data.get('logical_cases', {}).get(name)}, expected {expected}")
        expected_panel_cases = {
            "visible_topleft": [0, 0],
            "visible_bottomright": [239, 319],
            "visible_scaled_bottomright": [239, 319],
        }
        for name, expected in expected_panel_cases.items():
            if data.get("panel_cases", {}).get(name) != expected:
                failures.append(f"{name} mapped to {data.get('panel_cases', {}).get(name)}, expected {expected}")
        expected_touch_cases = {
            "rot180_visible_topleft": [0, 0],
            "rot180_visible_bottomright": [239, 319],
            "rot180_scaled_bottomright": [239, 319],
        }
        for name, expected in expected_touch_cases.items():
            if data.get("touch_cases", {}).get(name) != expected:
                failures.append(f"{name} mapped to {data.get('touch_cases', {}).get(name)}, expected {expected}")
        expected_logical_to_visible = {
            "rot180_calib_left": [229, 309],
            "rot180_dialog_no": [89, 114],
        }
        for name, expected in expected_logical_to_visible.items():
            if data.get("logical_to_visible_cases", {}).get(name) != expected:
                failures.append(
                    f"{name} mapped to {data.get('logical_to_visible_cases', {}).get(name)}, expected {expected}"
                )
        if data.get("queued") != [[0, 0, True], [239, 319, False]]:
            failures.append(f"display touch command queued {data.get('queued')}")
        if data.get("hardware_touch_globals_unchanged") is not True:
            failures.append("hardware touch path wrote high-level firmware touch globals directly")
        if data.get("hardware_touch_raw") != [2031, 1895]:
            failures.append(f"hardware touch raw ADC is {data.get('hardware_touch_raw')}, expected [2031, 1895]")
        if data.get("pending_touches") != 2:
            failures.append(f"pending_touches is {data.get('pending_touches')}, expected 2")
        if data.get("orientation") != "rot180":
            failures.append(f"frontend orientation is {data.get('orientation')}, expected rot180")
    else:
        failures.append("frontend touch mapping command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_frontend_ws_codec(rows: list[dict[str, object]], timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_frontend_ws_codec.json"
    script = f"""
import json, sys
from pathlib import Path
root = Path(r'{ROOT}')
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_frontend_ws import WebSocketFrameReader, encode_ws_frame, read_ws_frame, recv_ws_text, websocket_accept_key

class ChunkSocket:
    def __init__(self, data, chunks):
        self.data = bytearray(data)
        self.chunks = list(chunks)
        self.index = 0

    def recv(self, size):
        if not self.data:
            return b''
        chunk_size = self.chunks[self.index % len(self.chunks)]
        self.index += 1
        take = min(size, chunk_size, len(self.data))
        out = bytes(self.data[:take])
        del self.data[:take]
        return out

class TimeoutOnceSocket(ChunkSocket):
    def __init__(self, data, chunks):
        super().__init__(data, chunks)
        self.timed_out = False

    def recv(self, size):
        if self.index == 1 and not self.timed_out:
            self.timed_out = True
            raise TimeoutError()
        return super().recv(size)

masked_text = encode_ws_frame(0x1, b'hello', mask=b'\\x01\\x02\\x03\\x04')
binary_126 = encode_ws_frame(0x2, b'a' * 130)
binary_127 = encode_ws_frame(0x2, b'b' * 66000)
opcode_126, payload_126 = read_ws_frame(ChunkSocket(binary_126, [1, 2, 3, 5, 8]))
opcode_127, payload_127 = read_ws_frame(ChunkSocket(binary_127, [1, 1, 2, 3, 7, 4096]))
timeout_reader = WebSocketFrameReader(TimeoutOnceSocket(masked_text, [1, 1, 2, 1, 3]))
try:
    timeout_reader.recv_text()
    timeout_preserved = False
except TimeoutError:
    timeout_preserved = timeout_reader.recv_text() == 'hello'
out = {{
    'accept': websocket_accept_key('dGhlIHNhbXBsZSBub25jZQ=='),
    'masked_text': recv_ws_text(ChunkSocket(masked_text, [1, 1, 2, 1, 3])),
    'timeout_preserved': timeout_preserved,
    'binary_126_len_marker': binary_126[1],
    'binary_126_opcode': opcode_126,
    'binary_126_len': len(payload_126),
    'binary_127_len_marker': binary_127[1],
    'binary_127_opcode': opcode_127,
    'binary_127_len': len(payload_127),
}}
Path(r'{json_out}').write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("frontend-ws-codec", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        if data.get("accept") != "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=":
            failures.append(f"accept key was {data.get('accept')}")
        if data.get("masked_text") != "hello":
            failures.append(f"masked client text decoded as {data.get('masked_text')}")
        if data.get("timeout_preserved") is not True:
            failures.append("timeout-safe WebSocket reader did not preserve a partial frame")
        if data.get("binary_126_len_marker") != 126:
            failures.append(f"126-length frame marker was {data.get('binary_126_len_marker')}")
        if data.get("binary_126_opcode") != 2 or data.get("binary_126_len") != 130:
            failures.append(f"126-length binary frame decoded as {data.get('binary_126_opcode')}:{data.get('binary_126_len')}")
        if data.get("binary_127_len_marker") != 127:
            failures.append(f"127-length frame marker was {data.get('binary_127_len_marker')}")
        if data.get("binary_127_opcode") != 2 or data.get("binary_127_len") != 66_000:
            failures.append(f"127-length binary frame decoded as {data.get('binary_127_opcode')}:{data.get('binary_127_len')}")
    else:
        failures.append("frontend WS codec command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_frontend_http_ws_smoke(rows: list[dict[str, object]], timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_frontend_http_ws.json"
    script = f"""
import argparse, base64, json, os, socket, sys, threading, time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_frontend import FrontendState, Handler

def make_args():
    return argparse.Namespace(
        host='127.0.0.1',
        port=0,
        ram_mb=160,
        trace_limit=5000,
        boot_steps=30_000_000,
        input_steps=15_000,
        worker_slice_steps=15_000,
        worker_slice_seconds=0.5,
        frame_push_min_interval=0.08,
        boot_mode='c200',
        state_in=None,
        nand_image=None,
        nand_loop_accelerator=True,
        resource_cache16_accelerator=True,
        auto_calibration=True,
        slow_global_code_hook=False,
        block_image=False,
        scheduler_tick_clamp=False,
        key_input_mode='hardware',
        orientation='rot180',
        quiet=True,
    )

def recv_exact(sock, size):
    out = bytearray()
    while len(out) < size:
        chunk = sock.recv(size - len(out))
        if not chunk:
            raise EOFError('socket closed')
        out.extend(chunk)
    return bytes(out)

def recv_ws_frame(sock):
    first = recv_exact(sock, 2)
    opcode = first[0] & 0x0f
    length = first[1] & 0x7f
    if length == 126:
        length = int.from_bytes(recv_exact(sock, 2), 'big')
    elif length == 127:
        length = int.from_bytes(recv_exact(sock, 8), 'big')
    masked = bool(first[1] & 0x80)
    mask = recv_exact(sock, 4) if masked else b''
    payload = bytearray(recv_exact(sock, length))
    if masked:
        for idx, value in enumerate(payload):
            payload[idx] = value ^ mask[idx % 4]
    return opcode, bytes(payload)

def send_ws_text(sock, text):
    payload = text.encode('utf-8')
    mask = os.urandom(4)
    header = bytearray([0x81])
    if len(payload) < 126:
        header.append(0x80 | len(payload))
    elif len(payload) < 65536:
        header.extend((0x80 | 126, (len(payload) >> 8) & 0xff, len(payload) & 0xff))
    else:
        header.append(0x80 | 127)
        header.extend(len(payload).to_bytes(8, 'big'))
    masked = bytes(value ^ mask[idx % 4] for idx, value in enumerate(payload))
    sock.sendall(bytes(header) + mask + masked)

RAW_MAGIC = b'BBKRAW1\\x00'
def describe_binary_frame(payload):
    if payload.startswith(RAW_MAGIC) and len(payload) >= 20:
        return {{
            'kind': 'raw-rgb565',
            'bytes': len(payload),
            'signature': payload[:8].hex(),
            'seq': int.from_bytes(payload[8:12], 'little'),
            'width': int.from_bytes(payload[12:14], 'little'),
            'height': int.from_bytes(payload[14:16], 'little'),
            'stride': int.from_bytes(payload[16:18], 'little'),
            'format': int.from_bytes(payload[18:20], 'little'),
        }}
    if payload.startswith(b'\\x89PNG\\r\\n\\x1a\\n'):
        return {{
            'kind': 'png',
            'bytes': len(payload),
            'signature': payload[:8].hex(),
        }}
    return {{
        'kind': 'unknown',
        'bytes': len(payload),
        'signature': payload[:8].hex(),
    }}

state = FrontendState(make_args())
Handler.state = state
httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
port = httpd.server_address[1]
thread = threading.Thread(target=httpd.serve_forever, daemon=True)
thread.start()
sock = None
try:
    conn = HTTPConnection('127.0.0.1', port, timeout=5)
    conn.request('GET', '/api/status')
    resp = conn.getresponse()
    status_body = resp.read()
    http_status = resp.status
    status_json = json.loads(status_body.decode('utf-8'))
    conn.request('GET', '/')
    html_resp = conn.getresponse()
    html_text = html_resp.read().decode('utf-8', errors='replace')
    html_status = html_resp.status
    conn.close()

    key = base64.b64encode(os.urandom(16)).decode('ascii')
    sock = socket.create_connection(('127.0.0.1', port), timeout=5)
    sock.settimeout(5)
    request = (
        f'GET /ws HTTP/1.1\\r\\n'
        f'Host: 127.0.0.1:{{port}}\\r\\n'
        f'Upgrade: websocket\\r\\n'
        f'Connection: Upgrade\\r\\n'
        f'Sec-WebSocket-Key: {{key}}\\r\\n'
        f'Sec-WebSocket-Version: 13\\r\\n\\r\\n'
    )
    sock.sendall(request.encode('ascii'))
    response = bytearray()
    while b'\\r\\n\\r\\n' not in response:
        response.extend(sock.recv(4096))
    handshake_ok = b' 101 ' in response.split(b'\\r\\n', 1)[0]

    initial_ws = None
    initial_frame = None
    deadline = time.time() + 5
    while time.time() < deadline and (initial_ws is None or initial_frame is None):
        opcode, payload = recv_ws_frame(sock)
        if opcode == 0x1:
            initial_ws = json.loads(payload.decode('utf-8'))
        elif opcode == 0x2:
            initial_frame = describe_binary_frame(payload)
    send_ws_text(sock, json.dumps({{'op': 'key', 'code': 7, 'down': True, 'advance': False}}))
    queued_ws = None
    deadline = time.time() + 5
    while time.time() < deadline:
        opcode, payload = recv_ws_frame(sock)
        if opcode != 0x1:
            continue
        item = json.loads(payload.decode('utf-8'))
        if item.get('pending_keys') == 1:
            queued_ws = item
            break
    send_ws_text(sock, json.dumps({{'op': 'run-start', 'name': 'ws-smoke', 'steps': 15000, 'chunk': 15000}}))
    run_done_ws = None
    deadline = time.time() + 15
    while time.time() < deadline:
        opcode, payload = recv_ws_frame(sock)
        if opcode != 0x1:
            continue
        item = json.loads(payload.decode('utf-8'))
        job = item.get('job') or {{}}
        if job.get('name') == 'ws-smoke' and job.get('done_steps', 0) >= 15000 and not item.get('running'):
            run_done_ws = item
            break
    send_ws_text(sock, json.dumps({{
        'op': 'touch',
        'display_x': 120,
        'display_y': 160,
        'display_width': 240,
        'display_height': 320,
        'down': True,
        'advance': False,
        'run': True,
    }}))
    input_run_done_ws = None
    deadline = time.time() + 15
    while time.time() < deadline:
        opcode, payload = recv_ws_frame(sock)
        if opcode != 0x1:
            continue
        item = json.loads(payload.decode('utf-8'))
        job = item.get('job') or {{}}
        if job.get('name') == 'input' and job.get('done_steps', 0) >= 15000 and not item.get('running'):
            input_run_done_ws = item
            break
    send_ws_text(sock, json.dumps({{
        'op': 'touch',
        'display_x': 120,
        'display_y': 160,
        'display_width': 240,
        'display_height': 320,
        'down': False,
        'advance': False,
        'run': True,
    }}))
    input_release_done_ws = None
    deadline = time.time() + 15
    while time.time() < deadline:
        opcode, payload = recv_ws_frame(sock)
        if opcode != 0x1:
            continue
        item = json.loads(payload.decode('utf-8'))
        job = item.get('job') or {{}}
        if job.get('name') == 'input' and job.get('done_steps', 0) >= 15000 and not item.get('running'):
            input_release_done_ws = item
            break
    sock.sendall(b'\\x88\\x00')
    run_job = None if run_done_ws is None else run_done_ws.get('job')
    input_job = None if input_run_done_ws is None else input_run_done_ws.get('job')
    input_release_job = None if input_release_done_ws is None else input_release_done_ws.get('job')
    out = {{
        'http_status': http_status,
        'http_html_status': html_status,
        'http_html_boot_continuous': "name:'boot', steps:0" in html_text,
        'http_html_auto_boot_toggle': 'id="autoBoot"' in html_text and '自动冷启动输入' in html_text,
        'http_html_no_known_mojibake': not any(token in html_text for token in ('鍋', '杩', '閸', '鏉')),
        'http_key_input_mode': status_json.get('key_input_mode'),
        'http_reset_elapsed_seconds_type': type(status_json.get('reset_elapsed_seconds')).__name__,
        'ws_handshake_ok': handshake_ok,
        'ws_initial_running': None if initial_ws is None else initial_ws.get('running'),
        'ws_initial_frame_kind': None if initial_frame is None else initial_frame.get('kind'),
        'ws_initial_frame_bytes': None if initial_frame is None else initial_frame.get('bytes'),
        'ws_initial_frame_signature': None if initial_frame is None else initial_frame.get('signature'),
        'ws_initial_frame_width': None if initial_frame is None else initial_frame.get('width'),
        'ws_initial_frame_height': None if initial_frame is None else initial_frame.get('height'),
        'ws_initial_frame_stride': None if initial_frame is None else initial_frame.get('stride'),
        'ws_initial_frame_format': None if initial_frame is None else initial_frame.get('format'),
        'ws_pending_keys_after_key': None if queued_ws is None else queued_ws.get('pending_keys'),
        'ws_key_input_mode': None if queued_ws is None else queued_ws.get('key_input_mode'),
        'ws_run_done_steps': None if run_job is None else run_job.get('done_steps'),
        'ws_run_chunk_steps': None if run_job is None else run_job.get('chunk_steps'),
        'ws_run_last_slice_steps': None if run_job is None else run_job.get('last_slice_steps'),
        'ws_run_last_slice_timed_out': None if run_job is None else run_job.get('last_slice_timed_out'),
        'ws_run_elapsed_seconds_type': None if run_done_ws is None else type(run_done_ws.get('run_elapsed_seconds')).__name__,
        'ws_run_running': None if run_done_ws is None else run_done_ws.get('running'),
        'ws_run_insn_count': None if run_done_ws is None else run_done_ws.get('insn_count'),
        'ws_input_done_steps': None if input_job is None else input_job.get('done_steps'),
        'ws_input_chunk_steps': None if input_job is None else input_job.get('chunk_steps'),
        'ws_input_last_slice_steps': None if input_job is None else input_job.get('last_slice_steps'),
        'ws_input_last_slice_timed_out': None if input_job is None else input_job.get('last_slice_timed_out'),
        'ws_input_running': None if input_run_done_ws is None else input_run_done_ws.get('running'),
        'ws_input_pending_touches': None if input_run_done_ws is None else input_run_done_ws.get('pending_touches'),
        'ws_input_release_done_steps': None if input_release_job is None else input_release_job.get('done_steps'),
        'ws_input_release_chunk_steps': None if input_release_job is None else input_release_job.get('chunk_steps'),
        'ws_input_release_last_slice_steps': None if input_release_job is None else input_release_job.get('last_slice_steps'),
        'ws_input_release_last_slice_timed_out': None if input_release_job is None else input_release_job.get('last_slice_timed_out'),
        'ws_input_release_running': None if input_release_done_ws is None else input_release_done_ws.get('running'),
        'ws_input_release_pending_touches': None if input_release_done_ws is None else input_release_done_ws.get('pending_touches'),
        'port': port,
    }}
    Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
finally:
    if sock is not None:
        try:
            sock.close()
        except Exception:
            pass
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)
"""
    row = run_command("frontend-http-ws-smoke", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        if data.get("http_status") != 200:
            failures.append(f"/api/status returned HTTP {data.get('http_status')}")
        if data.get("http_html_status") != 200:
            failures.append(f"/ returned HTTP {data.get('http_html_status')}")
        if data.get("http_html_boot_continuous") is not True:
            failures.append("frontend boot button is not configured for continuous background run")
        if data.get("http_html_auto_boot_toggle") is not True:
            failures.append("frontend HTML is missing the auto boot input toggle")
        if data.get("http_html_no_known_mojibake") is not True:
            failures.append("frontend HTML still contains known mojibake strings")
        if data.get("http_key_input_mode") != "hardware":
            failures.append(f"HTTP key_input_mode is {data.get('http_key_input_mode')}")
        if data.get("http_reset_elapsed_seconds_type") not in {"int", "float"}:
            failures.append("HTTP status did not expose reset_elapsed_seconds")
        if data.get("ws_handshake_ok") is not True:
            failures.append("WebSocket handshake failed")
        if data.get("ws_initial_running") is not False:
            failures.append("initial WebSocket status should be stopped")
        if data.get("ws_initial_frame_kind") != "raw-rgb565":
            failures.append(f"WebSocket initial frame kind is {data.get('ws_initial_frame_kind')}, expected raw-rgb565")
        if not isinstance(data.get("ws_initial_frame_bytes"), int) or data.get("ws_initial_frame_bytes") <= 20:
            failures.append("WebSocket did not deliver an initial binary framebuffer frame")
        if data.get("ws_initial_frame_signature") != "42424b5241573100":
            failures.append(f"WebSocket initial frame signature is {data.get('ws_initial_frame_signature')}")
        if data.get("ws_initial_frame_width") != 240 or data.get("ws_initial_frame_height") != 320:
            failures.append(
                f"WebSocket initial raw frame dimensions are {data.get('ws_initial_frame_width')}x{data.get('ws_initial_frame_height')}"
            )
        if data.get("ws_initial_frame_stride") != 240:
            failures.append(f"WebSocket initial raw frame stride is {data.get('ws_initial_frame_stride')}")
        if data.get("ws_initial_frame_format") != 1:
            failures.append(f"WebSocket initial raw frame format is {data.get('ws_initial_frame_format')}")
        if data.get("ws_pending_keys_after_key") != 1:
            failures.append(f"WebSocket key command left pending_keys={data.get('ws_pending_keys_after_key')}")
        if data.get("ws_key_input_mode") != "hardware":
            failures.append(f"WebSocket key_input_mode is {data.get('ws_key_input_mode')}")
        if data.get("ws_run_done_steps") != 15_000:
            failures.append(f"WebSocket run-start completed {data.get('ws_run_done_steps')} steps")
        if data.get("ws_run_chunk_steps") != 15_000:
            failures.append(f"WebSocket run-start chunk is {data.get('ws_run_chunk_steps')}")
        if not isinstance(data.get("ws_run_last_slice_steps"), int) or not (0 < data.get("ws_run_last_slice_steps") <= 15_000):
            failures.append(f"WebSocket run-start last slice is {data.get('ws_run_last_slice_steps')}")
        if data.get("ws_run_last_slice_timed_out") is not False:
            failures.append("WebSocket run-start unexpectedly timed out")
        if data.get("ws_run_elapsed_seconds_type") not in {"int", "float"}:
            failures.append("WebSocket run-start did not expose run_elapsed_seconds")
        if data.get("ws_run_running") is not False:
            failures.append("WebSocket run-start did not report stopped after finite job")
        if not isinstance(data.get("ws_run_insn_count"), int):
            failures.append("WebSocket run-start did not expose emulator instruction count")
        if data.get("ws_input_done_steps") != 15_000:
            failures.append(f"WebSocket input auto-run completed {data.get('ws_input_done_steps')} steps")
        if data.get("ws_input_chunk_steps") != 15_000:
            failures.append(f"WebSocket input auto-run chunk is {data.get('ws_input_chunk_steps')}")
        if not isinstance(data.get("ws_input_last_slice_steps"), int) or not (0 < data.get("ws_input_last_slice_steps") <= 15_000):
            failures.append(f"WebSocket input auto-run last slice is {data.get('ws_input_last_slice_steps')}")
        if data.get("ws_input_last_slice_timed_out") is not False:
            failures.append("WebSocket input auto-run unexpectedly timed out")
        if data.get("ws_input_running") is not False:
            failures.append("WebSocket input auto-run did not report stopped")
        if data.get("ws_input_pending_touches") != 0:
            failures.append(f"WebSocket input auto-run left pending_touches={data.get('ws_input_pending_touches')}")
        if data.get("ws_input_release_done_steps") != 15_000:
            failures.append(f"WebSocket input release auto-run completed {data.get('ws_input_release_done_steps')} steps")
        if data.get("ws_input_release_chunk_steps") != 15_000:
            failures.append(f"WebSocket input release auto-run chunk is {data.get('ws_input_release_chunk_steps')}")
        if not isinstance(data.get("ws_input_release_last_slice_steps"), int) or not (0 < data.get("ws_input_release_last_slice_steps") <= 15_000):
            failures.append(f"WebSocket input release last slice is {data.get('ws_input_release_last_slice_steps')}")
        if data.get("ws_input_release_last_slice_timed_out") is not False:
            failures.append("WebSocket input release unexpectedly timed out")
        if data.get("ws_input_release_running") is not False:
            failures.append("WebSocket input release auto-run did not report stopped")
        if data.get("ws_input_release_pending_touches") != 0:
            failures.append(
                f"WebSocket input release auto-run left pending_touches={data.get('ws_input_release_pending_touches')}"
            )
    else:
        failures.append("frontend HTTP/WS smoke command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_frontend_deferred_frame(rows: list[dict[str, object]], timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_frontend_deferred_frame.json"
    script = f"""
import argparse, json, sys, time
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_frontend import FrontendState

args = argparse.Namespace(
    host='127.0.0.1',
    port=0,
    ram_mb=160,
    trace_limit=1000,
    boot_steps=30_000_000,
    input_steps=500_000,
    worker_slice_steps=250_000,
    worker_slice_seconds=0.25,
    frame_push_min_interval=0.05,
    frame_info_min_interval=1.0,
    boot_mode='c200',
    state_in=None,
    nand_image=None,
    readonly_nand_page_range=[],
    nand_loop_accelerator=True,
    resource_cache16_accelerator=True,
    auto_calibration=False,
    slow_global_code_hook=False,
    block_image=False,
    scheduler_tick_clamp=False,
    key_input_mode='hardware',
    orientation='rot180',
    quiet=True,
)
state = FrontendState(args)
capture_count = [0]
def fake_capture():
    capture_count[0] += 1
    color = b'\\x00\\xf8' if capture_count[0] % 2 else b'\\xe0\\x07'
    return color * (240 * 320)
state._capture_framebuffer_raw_locked = fake_capture
now = time.time()
state.frame_push_last_time = now
state.last_queued_frame_seq = 1
activity_before_defer = state.frontend_activity_sequence()
state._on_framebuffer_dirty(2, 0x8012bea4, 0xa1f82000, 320, 'surface-hline')
activity_after_defer = state.frontend_activity_sequence()
capture_after_defer = capture_count[0]
state._on_framebuffer_dirty(3, 0x8012bea4, 0xa1f82000, 153600, 'portrait-blit')
activity_after_replace = state.frontend_activity_sequence()
capture_after_replace = capture_count[0]
deferred_delay_after_defer = state.seconds_until_deferred_frame()
wait_after_defer = state.wait_for_frontend_activity(activity_after_replace, 0.001)
queued_before_due = state.queued_frame_count()
early_frame = state.pop_latest_queued_frame()
capture_after_early_pop = capture_count[0]
time.sleep(0.07)
before_due_pop = time.time()
due_frame = state.pop_latest_queued_frame()
capture_after_due_pop = capture_count[0]
last_push_after_due = state.frame_push_last_time
last_seq_after_due = state.last_queued_frame_seq
queued_after_due = state.queued_frame_count()
activity_before_immediate = state.frontend_activity_sequence()
state.frame_push_last_time = 0
state._on_framebuffer_dirty(4, 0x8012bea4, 0xa1f82000, 320, 'surface-hline')
activity_after_immediate = state.frontend_activity_sequence()
immediate_queued = state.queued_frame_count()
capture_after_immediate_queue = capture_count[0]
immediate_ws_frame = state.pop_latest_queued_ws_frame()
capture_after_immediate_pop = capture_count[0]
activity_before_lcd_small = state.frontend_activity_sequence()
state.frame_push_last_time = 0
state.emu._mark_framebuffer_dirty(0x8012bea4, 0xa1f82000, 2, 'lcd-mirror')
activity_after_lcd_small = state.frontend_activity_sequence()
lcd_small_queued = state.queued_frame_count()
capture_after_lcd_small_queue = capture_count[0]
lcd_small_ws_frame = state.pop_latest_queued_ws_frame()
capture_after_lcd_small_pop = capture_count[0]
out = {{
    'queued_before_due': queued_before_due,
    'early_frame_is_none': early_frame is None,
    'due_frame_png': bool(due_frame and due_frame.startswith(b'\\x89PNG\\r\\n\\x1a\\n')),
    'last_push_updated': last_push_after_due >= before_due_pop,
    'last_push_after_due': last_push_after_due,
    'last_seq_after_due': last_seq_after_due,
    'queued_after_due': queued_after_due,
    'capture_count': capture_count[0],
    'capture_after_defer': capture_after_defer,
    'capture_after_replace': capture_after_replace,
    'capture_after_early_pop': capture_after_early_pop,
    'capture_after_due_pop': capture_after_due_pop,
    'capture_after_immediate_pop': capture_after_immediate_pop,
    'frame_push_deferred_count': state.frame_push_deferred_count,
    'frame_push_replace_count': state.frame_push_replace_count,
    'frame_push_throttle_count': state.frame_push_throttle_count,
    'frame_push_error_count': state.frame_push_error_count,
    'activity_before_defer': activity_before_defer,
    'activity_after_defer': activity_after_defer,
    'activity_after_replace': activity_after_replace,
    'deferred_delay_after_defer': deferred_delay_after_defer,
    'wait_after_defer': wait_after_defer,
    'activity_before_immediate': activity_before_immediate,
    'activity_after_immediate': activity_after_immediate,
    'immediate_queued': immediate_queued,
    'immediate_ws_frame_raw': bool(immediate_ws_frame and immediate_ws_frame.startswith(b'BBKRAW1\\x00')),
    'capture_after_immediate_queue': capture_after_immediate_queue,
    'activity_before_lcd_small': activity_before_lcd_small,
    'activity_after_lcd_small': activity_after_lcd_small,
    'lcd_small_queued': lcd_small_queued,
    'lcd_small_ws_frame_raw': bool(lcd_small_ws_frame and lcd_small_ws_frame.startswith(b'BBKRAW1\\x00')),
    'capture_after_lcd_small_queue': capture_after_lcd_small_queue,
    'capture_after_lcd_small_pop': capture_after_lcd_small_pop,
}}
state.stop()
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("frontend-deferred-frame", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        if data.get("queued_before_due") != 1:
            failures.append(f"deferred frame queue count before due is {data.get('queued_before_due')}")
        if data.get("early_frame_is_none") is not True:
            failures.append("deferred frame was sent before its throttle interval elapsed")
        if data.get("due_frame_png") is not True:
            failures.append("deferred frame did not become a PNG after its throttle interval")
        if data.get("last_seq_after_due") != 3:
            failures.append(f"deferred send left last_queued_frame_seq={data.get('last_seq_after_due')}")
        if data.get("last_push_updated") is not True:
            failures.append("deferred send did not update last_push_at")
        if data.get("queued_after_due") != 0:
            failures.append(f"deferred frame was not drained: queued_after_due={data.get('queued_after_due')}")
        if int(data.get("frame_push_deferred_count") or 0) != 1:
            failures.append(f"deferred counter is {data.get('frame_push_deferred_count')}, expected 1")
        if int(data.get("frame_push_replace_count") or 0) != 1:
            failures.append(f"replace counter is {data.get('frame_push_replace_count')}, expected 1")
        if int(data.get("frame_push_throttle_count") or 0) != 2:
            failures.append(f"throttle counter is {data.get('frame_push_throttle_count')}, expected 2")
        if int(data.get("capture_after_defer") or 0) != 0:
            failures.append(f"deferred frame captured too early: {data.get('capture_after_defer')}")
        if int(data.get("capture_after_replace") or 0) != 0:
            failures.append(f"deferred replacement captured too early: {data.get('capture_after_replace')}")
        if int(data.get("capture_after_early_pop") or 0) != 0:
            failures.append(f"early deferred pop captured too early: {data.get('capture_after_early_pop')}")
        if int(data.get("capture_after_due_pop") or 0) != 1:
            failures.append(f"due deferred pop captured {data.get('capture_after_due_pop')} frames, expected 1")
        if int(data.get("capture_count") or 0) != 3:
            failures.append(f"total frame capture count is {data.get('capture_count')}, expected 3")
        if int(data.get("capture_after_immediate_pop") or 0) != 2:
            failures.append(
                f"immediate frame capture count is {data.get('capture_after_immediate_pop')}, expected 2"
            )
        if int(data.get("capture_after_lcd_small_pop") or 0) != 3:
            failures.append(
                f"small lcd frame capture count is {data.get('capture_after_lcd_small_pop')}, expected 3"
            )
        if int(data.get("frame_push_error_count") or 0) != 0:
            failures.append(f"frame push recorded errors: {data.get('frame_push_error_count')}")
        if int(data.get("activity_after_defer") or 0) <= int(data.get("activity_before_defer") or 0):
            failures.append(
                "deferred dirty frame did not notify frontend activity "
                f"({data.get('activity_before_defer')} -> {data.get('activity_after_defer')})"
            )
        if data.get("deferred_delay_after_defer") is None:
            failures.append("deferred dirty frame did not expose a due delay")
        if int(data.get("activity_after_replace") or 0) <= int(data.get("activity_after_defer") or 0):
            failures.append(
                "deferred dirty frame replacement did not notify frontend activity "
                f"({data.get('activity_after_defer')} -> {data.get('activity_after_replace')})"
            )
        if data.get("wait_after_defer") != data.get("activity_after_replace"):
            failures.append(
                "frontend activity wait changed without a new event "
                f"({data.get('activity_after_replace')} -> {data.get('wait_after_defer')})"
            )
        if int(data.get("activity_after_immediate") or 0) <= int(data.get("activity_before_immediate") or 0):
            failures.append(
                "immediate dirty frame did not notify frontend activity "
                f"({data.get('activity_before_immediate')} -> {data.get('activity_after_immediate')})"
            )
        if data.get("immediate_queued") != 1:
            failures.append(f"immediate dirty frame queue count is {data.get('immediate_queued')}")
        if data.get("immediate_ws_frame_raw") is not True:
            failures.append("immediate dirty frame was not delivered as raw WebSocket RGB565")
        if int(data.get("capture_after_immediate_queue") or 0) != int(data.get("capture_after_due_pop") or 0):
            failures.append("immediate dirty frame captured before the WebSocket sender popped it")
        if int(data.get("activity_after_lcd_small") or 0) <= int(data.get("activity_before_lcd_small") or 0):
            failures.append(
                "small lcd mirror dirty frame did not notify frontend activity "
                f"({data.get('activity_before_lcd_small')} -> {data.get('activity_after_lcd_small')})"
            )
        if data.get("lcd_small_queued") != 1:
            failures.append(f"small lcd dirty frame queue count is {data.get('lcd_small_queued')}")
        if data.get("lcd_small_ws_frame_raw") is not True:
            failures.append("small lcd dirty frame was not delivered as raw WebSocket RGB565")
        if int(data.get("capture_after_lcd_small_queue") or 0) != int(data.get("capture_after_immediate_pop") or 0):
            failures.append("small lcd dirty frame captured before the WebSocket sender popped it")
    else:
        failures.append("frontend deferred frame command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_frontend_input_worker_timeout(rows: list[dict[str, object]], timeout: int) -> None:
    state_in = first_existing(
        [
            BUILD / "hwemu_menu_ready_stage_probe.pkl",
            BUILD / "hwemu_known_delay_menu_smoke_release.pkl",
            BUILD / "hwemu_refactor_menu_smoke_release.pkl",
        ]
    )
    json_out = BUILD / "hwemu_regression_frontend_input_worker_timeout.json"
    failures: list[str] = []
    if state_in is None:
        rows.append(
            {
                "name": "frontend-input-worker-timeout",
                "ok": False,
                "failures": ["missing a known menu checkpoint"],
            }
        )
        return
    script = f"""
import argparse, json, sys, time
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_frontend import FrontendState

args = argparse.Namespace(
    host='127.0.0.1',
    port=0,
    ram_mb=160,
    trace_limit=1000,
    boot_steps=30_000_000,
    input_steps=10_000_000,
    worker_slice_steps=10_000_000,
    worker_slice_seconds=0.001,
    frame_push_min_interval=0.08,
    boot_mode='c200',
    state_in=Path({str(state_in)!r}),
    nand_image=None,
    nand_loop_accelerator=True,
    resource_cache16_accelerator=True,
    auto_calibration=False,
    slow_global_code_hook=False,
    block_image=False,
    scheduler_tick_clamp=False,
    key_input_mode='hardware',
    orientation='rot180',
    quiet=True,
)
state = FrontendState(args)
state.command({{'op': 'key', 'code': 7, 'down': True, 'advance': False, 'run': True}})
deadline = time.time() + 2.0
while state.worker_active() and time.time() < deadline:
    time.sleep(0.02)
snap = state.snapshot()
job = snap.get('job') or {{}}
input_timeout_worker_active = state.worker_active()

wake_before = int(snap.get('input_wake_count') or 0)
state.args.worker_slice_steps = 250_000
state.args.worker_slice_seconds = 0.25
state.run_start('wake-probe', 0, 250_000)
time.sleep(0.05)
wake_worker_active_before = state.worker_active()
state.key(7, True, advance=False)
wake_snap = state.snapshot()
deadline = time.time() + 1.5
while time.time() < deadline:
    wake_snap = state.snapshot()
    if int(wake_snap.get('input_wake_count') or 0) > wake_before and int(wake_snap.get('pending_keys') or 0) == 0:
        break
    time.sleep(0.02)
wake_job = wake_snap.get('job') or {{}}

out = {{
    'worker_active': input_timeout_worker_active,
    'running': snap.get('running'),
    'pending_keys': snap.get('pending_keys'),
    'pending_touches': snap.get('pending_touches'),
    'input_worker_pending': snap.get('input_worker_pending'),
    'stop_reason': snap.get('stop_reason'),
    'job_name': job.get('name'),
    'job_status': job.get('status'),
    'job_total_steps': job.get('total_steps'),
    'job_done_steps': job.get('done_steps'),
    'job_last_slice_timed_out': job.get('last_slice_timed_out'),
    'observed_insn_delta': job.get('observed_insn_delta'),
    'queued_frames': snap.get('queued_frames'),
    'frame_push': snap.get('frame_push'),
    'pc': snap.get('pc'),
    'wake_worker_active_before': wake_worker_active_before,
    'wake_before': wake_before,
    'wake_after': wake_snap.get('input_wake_count'),
    'wake_pending_keys': wake_snap.get('pending_keys'),
    'wake_job_name': wake_job.get('name'),
    'wake_job_done_steps': wake_job.get('done_steps'),
    'wake_job_last_slice_timed_out': wake_job.get('last_slice_timed_out'),
}}
state.stop()
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("frontend-input-worker-timeout", [sys.executable, "-c", script], timeout)
    row.update({"state_in": str(state_in), "json": str(json_out)})
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        if data.get("worker_active") is not False or data.get("running") is not False:
            failures.append("input worker remained active after its timeout slice")
        if data.get("job_name") != "input":
            failures.append(f"last job is {data.get('job_name')}, expected input")
        if data.get("job_status") != "stopped":
            failures.append(f"input job status is {data.get('job_status')}, expected stopped")
        if data.get("job_last_slice_timed_out") is not True:
            failures.append("input job did not record a timeout slice")
        if not isinstance(data.get("job_done_steps"), int) or int(data.get("job_done_steps") or 0) >= 10_000_000:
            failures.append(f"input job faked completion: done_steps={data.get('job_done_steps')}")
        if data.get("pending_keys") != 0:
            failures.append(f"input job left pending_keys={data.get('pending_keys')}")
        if data.get("stop_reason") is not None:
            failures.append(f"input timeout slice set stop_reason={data.get('stop_reason')}")
        if data.get("wake_worker_active_before") is not True:
            failures.append("wake probe worker was not active before queued input")
        if int(data.get("wake_after") or 0) <= int(data.get("wake_before") or 0):
            failures.append(
                f"queued input did not wake active worker ({data.get('wake_before')} -> {data.get('wake_after')})"
            )
        if data.get("wake_pending_keys") != 0:
            failures.append(f"wake probe left pending_keys={data.get('wake_pending_keys')}")
        if data.get("wake_job_name") != "wake-probe":
            failures.append(f"wake probe job name is {data.get('wake_job_name')}")
    else:
        failures.append("frontend input worker timeout command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_frontend_direct_idle_trace(rows: list[dict[str, object]], timeout: int) -> None:
    state_in = first_existing(
        [
            BUILD / "hwemu_menu_ready_stage_probe.pkl",
            BUILD / "hwemu_known_delay_menu_smoke_release.pkl",
            BUILD / "hwemu_refactor_menu_smoke_release.pkl",
        ]
    )
    json_out = BUILD / "hwemu_regression_frontend_direct_idle_trace.json"
    failures: list[str] = []
    if state_in is None:
        rows.append(
            {
                "name": "frontend-direct-idle-trace",
                "ok": False,
                "failures": ["missing a known menu checkpoint"],
            }
        )
        return
    script = f"""
import argparse, json, sys
from collections import Counter
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_frontend import FrontendState

args = argparse.Namespace(
    host='127.0.0.1',
    port=0,
    ram_mb=160,
    trace_limit=1000,
    boot_steps=30_000_000,
    input_steps=500_000,
    worker_slice_steps=250_000,
    worker_slice_seconds=0.25,
    frame_push_min_interval=0.08,
    boot_mode='c200',
    state_in=Path({str(state_in)!r}),
    nand_image=None,
    readonly_nand_page_range=[],
    nand_loop_accelerator=True,
    resource_cache16_accelerator=True,
    auto_calibration=False,
    slow_global_code_hook=False,
    block_image=False,
    scheduler_tick_clamp=False,
    key_input_mode='hardware',
    orientation='rot180',
    quiet=True,
)
state = FrontendState(args)
counts = Counter()
original = state.emu._record_recovery_reg_snapshot
def wrapped(pc):
    counts[pc & 0xffffffff] += 1
    return original(pc)
state.emu._record_recovery_reg_snapshot = wrapped
state.step(250_000)
out = {{
    'pc': state.snapshot().get('pc'),
    'idle_trace_count': state.emu.trace_pc_counts.get(0x80008A84, 0),
    'wait_trace_count': state.emu.trace_pc_counts.get(0x8005BCD4, 0),
    'timer_trace_count': state.emu.trace_pc_counts.get(0x800087C4, 0),
    'scheduler_trace_count': state.emu.trace_pc_counts.get(0x800080F0, 0),
    'idle_recovery_snapshots': counts.get(0x80008A84, 0),
    'wait_recovery_snapshots': counts.get(0x8005BCD4, 0),
    'timer_recovery_snapshots': counts.get(0x800087C4, 0),
    'scheduler_recovery_snapshots': counts.get(0x800080F0, 0),
    'total_recovery_snapshots': sum(counts.values()),
}}
state.stop()
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("frontend-direct-idle-trace", [sys.executable, "-c", script], timeout)
    row.update({"state_in": str(state_in), "json": str(json_out)})
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        if int(data.get("idle_trace_count") or 0) <= 0:
            failures.append("direct idle hook did not preserve trace count for 0x80008a84")
        if int(data.get("wait_trace_count") or 0) <= 0:
            failures.append("direct wait hook did not preserve trace count for 0x8005bcd4")
        if int(data.get("timer_trace_count") or 0) <= 0:
            failures.append("direct timer hook did not preserve trace count for 0x800087c4")
        if int(data.get("scheduler_trace_count") or 0) <= 0:
            failures.append("direct scheduler hook did not preserve trace count for 0x800080f0")
        if int(data.get("idle_recovery_snapshots") or 0) != 0:
            failures.append(
                f"direct idle hook still captured recovery snapshots: {data.get('idle_recovery_snapshots')}"
            )
        if int(data.get("wait_recovery_snapshots") or 0) != 0:
            failures.append(
                f"direct wait hook still captured recovery snapshots: {data.get('wait_recovery_snapshots')}"
            )
        if int(data.get("timer_recovery_snapshots") or 0) != 0:
            failures.append(
                f"direct timer hook still captured recovery snapshots: {data.get('timer_recovery_snapshots')}"
            )
        if int(data.get("scheduler_recovery_snapshots") or 0) != 0:
            failures.append(
                "direct scheduler hook still captured recovery snapshots: "
                f"{data.get('scheduler_recovery_snapshots')}"
            )
    else:
        failures.append("frontend direct idle trace command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_glyph_mask_fastpath(rows: list[dict[str, object]], c200: Path, timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_glyph_mask_fastpath.json"
    script = f"""
import json, struct, sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from bbk9588_hwemu import Bbk9588HwEmu
from hwemu_utils import va_to_phys
from unicorn.mips_const import (
    UC_MIPS_REG_2,
    UC_MIPS_REG_4,
    UC_MIPS_REG_6,
    UC_MIPS_REG_7,
    UC_MIPS_REG_8,
    UC_MIPS_REG_12,
    UC_MIPS_REG_13,
    UC_MIPS_REG_14,
    UC_MIPS_REG_18,
    UC_MIPS_REG_PC,
)

emu = Bbk9588HwEmu(
    image=Path({str(c200)!r}),
    base=0x80004000,
    pc=0x80004000,
    ram_size=160 * 1024 * 1024,
    trace_limit=64,
    recover_jr=False,
    profile='bbk9588-uboot',
    fast_hooks=True,
)

def reference(case):
    bit_index = case['bit_index']
    limit = case['limit']
    glyph_ptr = case['glyph_ptr']
    dest = case['dest']
    color = case['color']
    draw_pair = case['draw_pair']
    out = bytearray(case['dest_seed'])
    packed = struct.pack('<H', color)
    current_byte = case['current'] & 0xff
    ptr = glyph_ptr
    out_dest = dest
    glyph_offset = 0
    written = 0
    for index in range(bit_index, limit):
        if (index & 7) == 0:
            current_byte = case['glyph_bytes'][glyph_offset]
            glyph_offset += 1
            ptr = (ptr + 1) & 0xffffffff
        mask = 0x80 >> (index & 7)
        if current_byte & mask:
            off = (out_dest - dest) & 0xffffffff
            out[off:off + 2] = packed
            written += 1
            if draw_pair:
                out[off + 2:off + 4] = packed
                written += 1
        out_dest = (out_dest + 2) & 0xffffffff
    return {{
        'dest': bytes(out),
        'current_byte': current_byte,
        'ptr': ptr,
        'out_dest': out_dest,
        'written': written,
    }}

def run_case(index, bit_index, limit, glyph_bytes, current, color, draw_pair):
    count = limit - bit_index
    dest_size = count * 2 + (2 if draw_pair else 0)
    dest = 0xa1f82000 + index * 0x1000
    glyph_ptr = 0x80700000 + index * 0x100
    seed = bytes(((0x20 + index + i) & 0xff) for i in range(dest_size))
    emu.uc.mem_write(va_to_phys(dest), seed)
    emu.uc.mem_write(va_to_phys(glyph_ptr), bytes(glyph_bytes))
    emu.uc.reg_write(UC_MIPS_REG_7, bit_index)
    emu.uc.reg_write(UC_MIPS_REG_13, limit)
    emu.uc.reg_write(UC_MIPS_REG_6, glyph_ptr)
    emu.uc.reg_write(UC_MIPS_REG_8, dest)
    emu.uc.reg_write(UC_MIPS_REG_14, color)
    emu.uc.reg_write(UC_MIPS_REG_18, 1 if draw_pair else 0)
    emu.uc.reg_write(UC_MIPS_REG_12, current)
    dirty_before = emu.framebuffer_dirty_seq
    ok = emu._handle_glyph_mask_loop(0x8011B428)
    actual = bytes(emu.uc.mem_read(va_to_phys(dest), dest_size))
    expected = reference({{
        'bit_index': bit_index,
        'limit': limit,
        'glyph_ptr': glyph_ptr,
        'dest': dest,
        'color': color,
        'draw_pair': draw_pair,
        'current': current,
        'glyph_bytes': bytes(glyph_bytes),
        'dest_seed': seed,
    }})
    regs = {{
        'v0': emu.uc.reg_read(UC_MIPS_REG_2) & 0xffffffff,
        'a0': emu.uc.reg_read(UC_MIPS_REG_4) & 0xffffffff,
        'a2': emu.uc.reg_read(UC_MIPS_REG_6) & 0xffffffff,
        'a3': emu.uc.reg_read(UC_MIPS_REG_7) & 0xffffffff,
        't0': emu.uc.reg_read(UC_MIPS_REG_8) & 0xffffffff,
        't4': emu.uc.reg_read(UC_MIPS_REG_12) & 0xffffffff,
        'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
    }}
    return {{
        'name': f'case-{{index}}',
        'ok': ok,
        'dest_matches': actual == expected['dest'],
        'regs': regs,
        'expected': {{
            'current_byte': expected['current_byte'],
            'ptr': expected['ptr'],
            'out_dest': expected['out_dest'],
            'written': expected['written'],
        }},
        'dirty_delta': (emu.framebuffer_dirty_seq - dirty_before) & 0xffffffff,
        'dest_size': dest_size,
        'limit': limit,
    }}

cases = [
    run_case(0, 0, 8, [0b10100101], 0x00, 0x1234, False),
    run_case(1, 3, 14, [0b01010101, 0x00], 0b11100000, 0xabcd, True),
    run_case(2, 0, 8, [0x00], 0xff, 0x0f0f, True),
]
out = {{
    'cases': cases,
    'accel_count': emu.glyph_mask_loop_accel_count,
    'dirty_seq': emu.framebuffer_dirty_seq,
}}
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("glyph-mask-fastpath", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        for case in data.get("cases") or []:
            name = case.get("name")
            regs = case.get("regs") or {}
            expected = case.get("expected") or {}
            if case.get("ok") is not True:
                failures.append(f"{name} fast hook did not run")
            if case.get("dest_matches") is not True:
                failures.append(f"{name} destination bytes differ from reference")
            if regs.get("v0") != expected.get("current_byte") or regs.get("t4") != expected.get("current_byte"):
                failures.append(f"{name} current byte registers differ from reference")
            if regs.get("a0") != 0:
                failures.append(f"{name} did not clear a0")
            if regs.get("a2") != expected.get("ptr"):
                failures.append(f"{name} glyph pointer differs from reference")
            if regs.get("a3") != case.get("limit"):
                failures.append(f"{name} a3 is {regs.get('a3')}, expected {case.get('limit')}")
            if regs.get("t0") != expected.get("out_dest"):
                failures.append(f"{name} destination pointer differs from reference")
            if regs.get("pc") != 0x8011B47C:
                failures.append(f"{name} PC is 0x{int(regs.get('pc') or 0):08x}")
            expected_dirty = 1 if int(expected.get("written") or 0) else 0
            if case.get("dirty_delta") != expected_dirty:
                failures.append(f"{name} dirty delta is {case.get('dirty_delta')}, expected {expected_dirty}")
        if int(data.get("accel_count") or 0) != 3:
            failures.append(f"glyph accel count is {data.get('accel_count')}, expected 3")
    else:
        failures.append("glyph mask fastpath command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_lfn_copy_fastpath(rows: list[dict[str, object]], c200: Path, timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_lfn_copy_fastpath.json"
    script = f"""
import json, sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from bbk9588_hwemu import Bbk9588HwEmu
from hwemu_utils import va_to_phys
from unicorn.mips_const import (
    UC_MIPS_REG_2,
    UC_MIPS_REG_3,
    UC_MIPS_REG_4,
    UC_MIPS_REG_7,
    UC_MIPS_REG_16,
    UC_MIPS_REG_17,
    UC_MIPS_REG_PC,
)

emu = Bbk9588HwEmu(
    image=Path({str(c200)!r}),
    base=0x80004000,
    pc=0x80004000,
    ram_size=160 * 1024 * 1024,
    trace_limit=64,
    recover_jr=False,
    profile='bbk9588-uboot',
    fast_hooks=True,
)

entry = 0x80701000
dst = 0x80702000
entry_data = bytes(range(0x20))
emu.uc.mem_write(va_to_phys(entry), entry_data)
emu.uc.mem_write(va_to_phys(dst), b'\\xaa' * 32)
emu.uc.reg_write(UC_MIPS_REG_4, 0)
emu.uc.reg_write(UC_MIPS_REG_7, entry)
emu.uc.reg_write(UC_MIPS_REG_16, dst)
emu.uc.reg_write(UC_MIPS_REG_17, 5)
fused_ok = emu._handle_lfn_copy_loop(0x80174C9C)
fused_out = bytes(emu.uc.mem_read(va_to_phys(dst), 32))
expected = entry_data[1:11] + entry_data[0x0E:0x1A] + entry_data[0x1C:0x20]
fused_regs = {{
    'v0': emu.uc.reg_read(UC_MIPS_REG_2) & 0xffffffff,
    'v1': emu.uc.reg_read(UC_MIPS_REG_3) & 0xffffffff,
    'a0': emu.uc.reg_read(UC_MIPS_REG_4) & 0xffffffff,
    's0': emu.uc.reg_read(UC_MIPS_REG_16) & 0xffffffff,
    's1': emu.uc.reg_read(UC_MIPS_REG_17) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
}}

seg_dst = 0x80703000
emu.uc.mem_write(va_to_phys(seg_dst), b'\\xbb' * 16)
emu.uc.reg_write(UC_MIPS_REG_4, 3)
emu.uc.reg_write(UC_MIPS_REG_7, entry)
emu.uc.reg_write(UC_MIPS_REG_16, seg_dst)
emu.uc.reg_write(UC_MIPS_REG_17, 9)
segment_ok = emu._handle_lfn_copy_loop(0x80174CC0)
segment_out = bytes(emu.uc.mem_read(va_to_phys(seg_dst), 16))
segment_expected = entry_data[0x0E + 3 : 0x0E + 12]
segment_regs = {{
    'a0': emu.uc.reg_read(UC_MIPS_REG_4) & 0xffffffff,
    's0': emu.uc.reg_read(UC_MIPS_REG_16) & 0xffffffff,
    's1': emu.uc.reg_read(UC_MIPS_REG_17) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
}}

emu.uc.reg_write(UC_MIPS_REG_4, 0)
emu.uc.reg_write(UC_MIPS_REG_7, entry)
emu.uc.reg_write(UC_MIPS_REG_16, entry + 2)
emu.uc.reg_write(UC_MIPS_REG_17, 0)
overlap_ok = emu._handle_lfn_copy_loop(0x80174C9C)

out = {{
    'fused_ok': fused_ok,
    'fused_matches': fused_out[:26] == expected and fused_out[26:] == b'\\xaa' * 6,
    'fused_regs': fused_regs,
    'expected_last': expected[-1],
    'segment_ok': segment_ok,
    'segment_matches': segment_out[:9] == segment_expected and segment_out[9:] == b'\\xbb' * 7,
    'segment_regs': segment_regs,
    'overlap_ok': overlap_ok,
    'lfn_copy_accel_count': emu.lfn_copy_accel_count,
    'lfn_copy_fused_accel_count': getattr(emu, 'lfn_copy_fused_accel_count', 0),
}}
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("lfn-copy-fastpath", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        regs = data.get("fused_regs") or {}
        seg_regs = data.get("segment_regs") or {}
        if data.get("fused_ok") is not True:
            failures.append("fused LFN copy did not run")
        if data.get("fused_matches") is not True:
            failures.append("fused LFN output bytes differ from reference")
        if regs.get("v0") != 0:
            failures.append(f"fused LFN v0 is {regs.get('v0')}, expected 0")
        if regs.get("v1") != data.get("expected_last"):
            failures.append(f"fused LFN v1 is {regs.get('v1')}, expected {data.get('expected_last')}")
        if regs.get("a0") != 4:
            failures.append(f"fused LFN a0 is {regs.get('a0')}, expected 4")
        if regs.get("s0") != 0x80702000 + 26:
            failures.append(f"fused LFN s0 is {regs.get('s0')}")
        if regs.get("s1") != 31:
            failures.append(f"fused LFN s1 is {regs.get('s1')}, expected 31")
        if regs.get("pc") != 0x80174D04:
            failures.append(f"fused LFN PC is 0x{int(regs.get('pc') or 0):08x}")
        if data.get("segment_ok") is not True or data.get("segment_matches") is not True:
            failures.append("segment LFN fallback output differs from reference")
        if seg_regs.get("a0") != 12 or seg_regs.get("s0") != 0x80703000 + 9 or seg_regs.get("s1") != 18:
            failures.append(f"segment LFN fallback regs are {seg_regs}")
        if seg_regs.get("pc") != 0x80174CE0:
            failures.append(f"segment LFN fallback PC is 0x{int(seg_regs.get('pc') or 0):08x}")
        if data.get("overlap_ok") is not False:
            failures.append("overlapping LFN source/destination should fall back to native path")
        if int(data.get("lfn_copy_fused_accel_count") or 0) != 1:
            failures.append(f"fused LFN count is {data.get('lfn_copy_fused_accel_count')}, expected 1")
        if int(data.get("lfn_copy_accel_count") or 0) != 2:
            failures.append(f"LFN accel count is {data.get('lfn_copy_accel_count')}, expected 2")
    else:
        failures.append("LFN copy fastpath command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_resource_cache16_fastpath(rows: list[dict[str, object]], c200: Path, timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_resource_cache16_fastpath.json"
    script = f"""
import json, struct, sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from bbk9588_hwemu import Bbk9588HwEmu
from hwemu_utils import va_to_phys
from unicorn.mips_const import UC_MIPS_REG_2, UC_MIPS_REG_4, UC_MIPS_REG_31, UC_MIPS_REG_PC

emu = Bbk9588HwEmu(
    image=Path({str(c200)!r}),
    base=0x80004000,
    pc=0x80004000,
    ram_size=160 * 1024 * 1024,
    trace_limit=64,
    recover_jr=False,
    profile='bbk9588-uboot',
    fast_hooks=True,
    resource_cache16_accelerator=True,
)
table = 0x8086D180
base_sector = 0x100
emu._write_u32_va(0x804BF434, 1)
emu._write_u32_va(0x80474264, 0x4000)
emu._write_u32_va(0x80474260, base_sector)

def write_entry(slot, sector, buffer, hits, dirty=0):
    entry = table + slot * 0x10
    emu._write_u32_va(entry, sector)
    emu._write_u32_va(entry + 4, buffer)
    emu._write_u32_va(entry + 8, hits)
    emu._write_u32_va(entry + 0x0C, dirty)

hit_index = 0x0234
hit_sector = base_sector + (hit_index >> 8)
hit_buffer = 0x80704000
emu.uc.mem_write(va_to_phys(hit_buffer), b'\\x00' * 0x200)
emu.uc.mem_write(va_to_phys(hit_buffer + ((hit_index & 0xff) * 2)), struct.pack('<H', 0xbeef))
for slot in range(8):
    write_entry(slot, 0xffffffff - slot, 0x80705000 + slot * 0x200, 20 + slot)
write_entry(3, hit_sector, hit_buffer, 7)
emu.uc.reg_write(UC_MIPS_REG_4, hit_index)
emu.uc.reg_write(UC_MIPS_REG_31, 0x80012344)
hit_ok = emu._handle_resource_cache16_hit(0x8017CA10)
hit_regs = {{
    'v0': emu.uc.reg_read(UC_MIPS_REG_2) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
}}
hit_counter = emu._read_u32_va_safe(table + 3 * 0x10 + 8)

miss_index = 0x0540
miss_sector = base_sector + (miss_index >> 8)
miss_backing = bytearray((i & 0xff) for i in range(0x200))
struct.pack_into('<H', miss_backing, (miss_index & 0xff) * 2, 0xcafe)
def backing_reader(sector):
    return bytes(miss_backing) if sector == miss_sector else None
emu._read_backing_sector = backing_reader
for slot in range(8):
    buffer = 0x80708000 + slot * 0x200
    emu.uc.mem_write(va_to_phys(buffer), b'\\xdd' * 0x200)
    write_entry(slot, 0x200 + slot, buffer, 30 - slot)
emu.uc.reg_write(UC_MIPS_REG_4, miss_index)
emu.uc.reg_write(UC_MIPS_REG_31, 0x80012388)
miss_ok = emu._handle_resource_cache16_hit(0x8017CA10)
victim_entry = table + 7 * 0x10
victim_buffer = 0x80708000 + 7 * 0x200
miss_regs = {{
    'v0': emu.uc.reg_read(UC_MIPS_REG_2) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
}}
miss_entry = {{
    'sector': emu._read_u32_va_safe(victim_entry),
    'hits': emu._read_u32_va_safe(victim_entry + 8),
    'dirty': emu._read_u32_va_safe(victim_entry + 0x0C),
    'buffer_loaded': bytes(emu.uc.mem_read(va_to_phys(victim_buffer), 0x200)) == bytes(miss_backing),
}}

dirty_index = 0x0630
dirty_sector = base_sector + (dirty_index >> 8)
dirty_backing = bytes([0x11] * 0x200)
def dirty_backing_reader(sector):
    return dirty_backing if sector == dirty_sector else None
emu._read_backing_sector = dirty_backing_reader
for slot in range(8):
    write_entry(slot, 0x300 + slot, 0x8070a000 + slot * 0x200, 10 - slot, 0)
write_entry(7, 0x307, 0x8070a000 + 7 * 0x200, 0, 1)
emu.uc.reg_write(UC_MIPS_REG_4, dirty_index)
emu.uc.reg_write(UC_MIPS_REG_31, 0x800123cc)
dirty_ok = emu._handle_resource_cache16_hit(0x8017CA10)

out = {{
    'hit_ok': hit_ok,
    'hit_regs': hit_regs,
    'hit_counter': hit_counter,
    'miss_ok': miss_ok,
    'miss_regs': miss_regs,
    'miss_entry': miss_entry,
    'dirty_ok': dirty_ok,
    'resource_cache16_accel_count': emu.resource_cache16_accel_count,
}}
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("resource-cache16-fastpath", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        hit_regs = data.get("hit_regs") or {}
        miss_regs = data.get("miss_regs") or {}
        miss_entry = data.get("miss_entry") or {}
        if data.get("hit_ok") is not True:
            failures.append("resource cache16 hit did not run")
        if hit_regs.get("v0") != 0xBEEF or hit_regs.get("pc") != 0x80012344:
            failures.append(f"resource cache16 hit regs are {hit_regs}")
        if data.get("hit_counter") != 8:
            failures.append(f"resource cache16 hit counter is {data.get('hit_counter')}, expected 8")
        if data.get("miss_ok") is not True:
            failures.append("resource cache16 miss did not run")
        if miss_regs.get("v0") != 0xCAFE or miss_regs.get("pc") != 0x80012388:
            failures.append(f"resource cache16 miss regs are {miss_regs}")
        if miss_entry.get("sector") != 0x105 or miss_entry.get("hits") != 1 or miss_entry.get("dirty") != 0:
            failures.append(f"resource cache16 miss entry is {miss_entry}")
        if miss_entry.get("buffer_loaded") is not True:
            failures.append("resource cache16 miss did not load the selected cache buffer")
        if data.get("dirty_ok") is not False:
            failures.append("resource cache16 dirty victim should fall back to native path")
        if int(data.get("resource_cache16_accel_count") or 0) != 2:
            failures.append(f"resource cache16 accel count is {data.get('resource_cache16_accel_count')}, expected 2")
    else:
        failures.append("resource cache16 fastpath command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_fat16_cluster_cache_fastpath(rows: list[dict[str, object]], c200: Path, timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_fat16_cluster_cache_fastpath.json"
    script = f"""
import json, sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from bbk9588_hwemu import Bbk9588HwEmu
from hwemu_utils import va_to_phys
from unicorn.mips_const import UC_MIPS_REG_2, UC_MIPS_REG_4, UC_MIPS_REG_5, UC_MIPS_REG_31, UC_MIPS_REG_PC

emu = Bbk9588HwEmu(
    image=Path({str(c200)!r}),
    base=0x80004000,
    pc=0x80004000,
    ram_size=160 * 1024 * 1024,
    trace_limit=64,
    recover_jr=False,
    profile='bbk9588-uboot',
    fast_hooks=True,
)
emu.fat16_layout_cache = {{
    'volume_lba': 0,
    'bytes_per_sector': 512,
    'sectors_per_cluster': 1,
    'fat_lba': 1,
    'root_lba': 2,
    'root_dir_sectors': 1,
    'first_data_lba': 0x40,
    'total_sectors': 0x200,
}}
emu._fat16_layout_from_backing = lambda: emu.fat16_layout_cache
emu.uc.mem_write(va_to_phys(0x80474254), b'\\x01')

table_even = 0x8086D200
table_odd = 0x8086D220
def write_entry(entry, cluster, buffer, hits, dirty=0):
    emu._write_u32_va(entry, cluster)
    emu._write_u32_va(entry + 4, buffer)
    emu._write_u32_va(entry + 8, hits)
    emu._write_u32_va(entry + 0x0C, dirty)

hit_cluster = 4
hit_dest = 0x80710000
hit_buffer = 0x80711000
hit_data = bytes((0x20 + i) & 0xff for i in range(512))
emu.uc.mem_write(va_to_phys(hit_buffer), hit_data)
write_entry(table_even, 0xaaaa, 0x80712000, 9)
write_entry(table_even + 0x10, hit_cluster, hit_buffer, 6)
emu.uc.reg_write(UC_MIPS_REG_4, hit_cluster)
emu.uc.reg_write(UC_MIPS_REG_5, hit_dest)
emu.uc.reg_write(UC_MIPS_REG_31, 0x80045678)
hit_ok = emu._handle_fat16_cluster_read(0x8017B4E0)
hit_out = bytes(emu.uc.mem_read(va_to_phys(hit_dest), 512))
hit_regs = {{
    'v0': emu.uc.reg_read(UC_MIPS_REG_2) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
}}
hit_counter = emu._read_u32_va_safe(table_even + 0x10 + 8)

miss_cluster = 5
miss_dest = 0x80713000
miss_buffer0 = 0x80714000
miss_buffer1 = 0x80715000
miss_data = bytes((0x80 + i) & 0xff for i in range(512))
def backing_reader(sector):
    expected = emu.fat16_layout_cache['first_data_lba'] + (miss_cluster - 2)
    return miss_data if sector == expected else None
emu._read_backing_sector = backing_reader
emu.uc.mem_write(va_to_phys(miss_buffer0), b'\\x00' * 512)
emu.uc.mem_write(va_to_phys(miss_buffer1), b'\\x11' * 512)
write_entry(table_odd, 0x1111, miss_buffer0, 4)
write_entry(table_odd + 0x10, 0x2222, miss_buffer1, 2)
emu.uc.reg_write(UC_MIPS_REG_4, miss_cluster)
emu.uc.reg_write(UC_MIPS_REG_5, miss_dest)
emu.uc.reg_write(UC_MIPS_REG_31, 0x800456a0)
miss_ok = emu._handle_fat16_cluster_read(0x8017B4E0)
miss_out = bytes(emu.uc.mem_read(va_to_phys(miss_dest), 512))
miss_cache = bytes(emu.uc.mem_read(va_to_phys(miss_buffer1), 512))
miss_regs = {{
    'v0': emu.uc.reg_read(UC_MIPS_REG_2) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
}}
miss_entry = {{
    'cluster': emu._read_u32_va_safe(table_odd + 0x10),
    'hits': emu._read_u32_va_safe(table_odd + 0x10 + 8),
}}

nocache_cluster = 7
nocache_dest = 0x80716000
nocache_buffer0 = 0x80717000
nocache_buffer1 = 0x80718000
nocache_data = bytes((0x44 + i) & 0xff for i in range(512))
def nocache_reader(sector):
    expected = emu.fat16_layout_cache['first_data_lba'] + (nocache_cluster - 2)
    return nocache_data if sector == expected else None
emu._read_backing_sector = nocache_reader
emu.uc.mem_write(va_to_phys(nocache_buffer0), b'\\x22' * 512)
emu.uc.mem_write(va_to_phys(nocache_buffer1), b'\\x33' * 512)
write_entry(table_odd, 0x3333, nocache_buffer0, 9)
write_entry(table_odd + 0x10, 0x4444, nocache_buffer1, 1)
emu.uc.reg_write(UC_MIPS_REG_4, nocache_cluster)
emu.uc.reg_write(UC_MIPS_REG_5, nocache_dest)
emu.uc.reg_write(UC_MIPS_REG_31, 0x800456d0)
nocache_ok = emu._handle_fat16_cluster_read(0x8017B4E0)
nocache_out = bytes(emu.uc.mem_read(va_to_phys(nocache_dest), 512))
nocache_cache = bytes(emu.uc.mem_read(va_to_phys(nocache_buffer1), 512))
nocache_entry = {{
    'cluster': emu._read_u32_va_safe(table_odd + 0x10),
    'hits': emu._read_u32_va_safe(table_odd + 0x10 + 8),
}}

out = {{
    'hit_ok': hit_ok,
    'hit_matches': hit_out == hit_data,
    'hit_regs': hit_regs,
    'hit_counter': hit_counter,
    'miss_ok': miss_ok,
    'miss_matches': miss_out == miss_data and miss_cache == miss_data,
    'miss_regs': miss_regs,
    'miss_entry': miss_entry,
    'nocache_ok': nocache_ok,
    'nocache_matches': nocache_out == nocache_data and nocache_cache == b'\\x33' * 512,
    'nocache_entry': nocache_entry,
    'cluster_read_accel_count': emu.cluster_read_accel_count,
}}
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("fat16-cluster-cache-fastpath", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        hit_regs = data.get("hit_regs") or {}
        miss_regs = data.get("miss_regs") or {}
        miss_entry = data.get("miss_entry") or {}
        nocache_entry = data.get("nocache_entry") or {}
        if data.get("hit_ok") is not True or data.get("hit_matches") is not True:
            failures.append("FAT16 cluster cache hit did not copy expected bytes")
        if hit_regs.get("v0") != 1 or hit_regs.get("pc") != 0x80045678:
            failures.append(f"FAT16 cluster hit regs are {hit_regs}")
        if data.get("hit_counter") != 7:
            failures.append(f"FAT16 cluster hit counter is {data.get('hit_counter')}, expected 7")
        if data.get("miss_ok") is not True or data.get("miss_matches") is not True:
            failures.append("FAT16 cluster cache miss-load did not copy expected bytes")
        if miss_regs.get("v0") != 1 or miss_regs.get("pc") != 0x800456A0:
            failures.append(f"FAT16 cluster miss regs are {miss_regs}")
        if miss_entry.get("cluster") != 5 or miss_entry.get("hits") != 1:
            failures.append(f"FAT16 cluster miss entry is {miss_entry}")
        if data.get("nocache_ok") is not True or data.get("nocache_matches") is not True:
            failures.append("FAT16 cluster victim_hits=1 path changed cache unexpectedly")
        if nocache_entry.get("cluster") != 0x4444 or nocache_entry.get("hits") != 1:
            failures.append(f"FAT16 cluster no-cache entry is {nocache_entry}")
        if int(data.get("cluster_read_accel_count") or 0) != 3:
            failures.append(f"FAT16 cluster accel count is {data.get('cluster_read_accel_count')}, expected 3")
    else:
        failures.append("FAT16 cluster cache fastpath command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_block_read_wrapper_fastpath(rows: list[dict[str, object]], c200: Path, timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_block_read_wrapper_fastpath.json"
    script = f"""
import json, sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from bbk9588_hwemu import Bbk9588HwEmu
from hwemu_utils import va_to_phys
from unicorn.mips_const import (
    UC_MIPS_REG_2,
    UC_MIPS_REG_4,
    UC_MIPS_REG_5,
    UC_MIPS_REG_6,
    UC_MIPS_REG_7,
    UC_MIPS_REG_31,
    UC_MIPS_REG_PC,
)

emu = Bbk9588HwEmu(
    image=Path({str(c200)!r}),
    base=0x80004000,
    pc=0x80004000,
    ram_size=160 * 1024 * 1024,
    trace_limit=64,
    recover_jr=False,
    profile='bbk9588-uboot',
    fast_hooks=True,
)
sector_count = 64
emu.block_data = bytearray(sector_count * 512)
for sector in range(sector_count):
    emu.block_data[sector * 512 : (sector + 1) * 512] = bytes([sector & 0xff]) * 512
emu._write_u32_va(0x804BF454, 1)

dest = 0x80712000
emu.uc.mem_write(va_to_phys(dest), b'\\xaa' * (4 * 512))
emu.uc.reg_write(UC_MIPS_REG_4, 0)
emu.uc.reg_write(UC_MIPS_REG_5, 10)
emu.uc.reg_write(UC_MIPS_REG_6, 3)
emu.uc.reg_write(UC_MIPS_REG_7, dest)
emu.uc.reg_write(UC_MIPS_REG_31, 0x80045678)
read_ok = emu._handle_block_read_wrapper(0x8017FBC0)
read_data = bytes(emu.uc.mem_read(va_to_phys(dest), 3 * 512))
read_regs = {{
    'v0': emu.uc.reg_read(UC_MIPS_REG_2) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
}}

emu.uc.reg_write(UC_MIPS_REG_4, 0)
emu.uc.reg_write(UC_MIPS_REG_5, 11)
emu.uc.reg_write(UC_MIPS_REG_6, 0)
emu.uc.reg_write(UC_MIPS_REG_7, dest)
emu.uc.reg_write(UC_MIPS_REG_31, 0x80045690)
zero_ok = emu._handle_block_read_wrapper(0x8017FBC0)
zero_regs = {{
    'v0': emu.uc.reg_read(UC_MIPS_REG_2) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
}}

counter_after_fast = emu.block_read_wrapper_accel_count
emu.uc.reg_write(UC_MIPS_REG_4, 1)
emu.uc.reg_write(UC_MIPS_REG_5, 10)
emu.uc.reg_write(UC_MIPS_REG_6, 1)
emu.uc.reg_write(UC_MIPS_REG_7, dest)
mode1_ok = emu._handle_block_read_wrapper(0x8017FBC0)

emu._write_u32_va(0x804BF454, 0)
emu.uc.reg_write(UC_MIPS_REG_4, 0)
uninit_ok = emu._handle_block_read_wrapper(0x8017FBC0)

emu._write_u32_va(0x804BF454, 1)
emu.uc.reg_write(UC_MIPS_REG_5, sector_count)
emu.uc.reg_write(UC_MIPS_REG_6, 1)
past_end_ok = emu._handle_block_read_wrapper(0x8017FBC0)

out = {{
    'read_ok': read_ok,
    'read_matches': read_data == (b'\\x0a' * 512 + b'\\x0b' * 512 + b'\\x0c' * 512),
    'read_regs': read_regs,
    'zero_ok': zero_ok,
    'zero_regs': zero_regs,
    'mode1_ok': mode1_ok,
    'uninit_ok': uninit_ok,
    'past_end_ok': past_end_ok,
    'counter_after_fast': counter_after_fast,
    'block_read_wrapper_accel_count': emu.block_read_wrapper_accel_count,
    'block_events_tail': emu.block_events[-4:],
}}
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("block-read-wrapper-fastpath", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        read_regs = data.get("read_regs") or {}
        zero_regs = data.get("zero_regs") or {}
        if data.get("read_ok") is not True or data.get("read_matches") is not True:
            failures.append("block read wrapper did not copy expected sectors")
        if read_regs.get("v0") != 0 or read_regs.get("pc") != 0x80045678:
            failures.append(f"block read wrapper regs are {read_regs}")
        if data.get("zero_ok") is not True:
            failures.append("zero-length block read wrapper did not return successfully")
        if zero_regs.get("v0") != 0 or zero_regs.get("pc") != 0x80045690:
            failures.append(f"zero-length wrapper regs are {zero_regs}")
        if data.get("mode1_ok") is not False:
            failures.append("mode 1 wrapper path should fall back to firmware")
        if data.get("uninit_ok") is not False:
            failures.append("uninitialized wrapper path should fall back to firmware")
        if data.get("past_end_ok") is not False:
            failures.append("out-of-range wrapper path should fall back to firmware")
        if int(data.get("counter_after_fast") or 0) != 2:
            failures.append(f"wrapper count after fast cases is {data.get('counter_after_fast')}, expected 2")
        if int(data.get("block_read_wrapper_accel_count") or 0) != 2:
            failures.append(
                f"wrapper accel count is {data.get('block_read_wrapper_accel_count')}, expected 2"
            )
    else:
        failures.append("block read wrapper fastpath command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_file_read_sector_loop_fastpath(rows: list[dict[str, object]], c200: Path, timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_file_read_sector_loop_fastpath.json"
    script = f"""
import json, sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from bbk9588_hwemu import Bbk9588HwEmu
from hwemu_utils import va_to_phys
from unicorn.mips_const import (
    UC_MIPS_REG_17,
    UC_MIPS_REG_18,
    UC_MIPS_REG_19,
    UC_MIPS_REG_20,
    UC_MIPS_REG_21,
    UC_MIPS_REG_22,
    UC_MIPS_REG_30,
    UC_MIPS_REG_PC,
    UC_MIPS_REG_SP,
)

emu = Bbk9588HwEmu(
    image=Path({str(c200)!r}),
    base=0x80004000,
    pc=0x80004000,
    ram_size=160 * 1024 * 1024,
    trace_limit=64,
    recover_jr=False,
    profile='bbk9588-uboot',
    fast_hooks=True,
)
sector_count = 128
emu.block_data = bytearray(sector_count * 512)
for sector in range(sector_count):
    emu.block_data[sector * 512 : (sector + 1) * 512] = bytes([sector & 0xff]) * 512

def setup_common(dest, sp, *, remaining, sector, sector_index, current_cluster, last_cluster):
    emu.uc.mem_write(va_to_phys(dest), b'\\xaa' * 8192)
    emu.uc.mem_write(va_to_phys(sp), b'\\x00' * 0x260)
    emu.uc.reg_write(UC_MIPS_REG_17, 0)
    emu.uc.reg_write(UC_MIPS_REG_18, remaining)
    emu.uc.reg_write(UC_MIPS_REG_19, sector)
    emu.uc.reg_write(UC_MIPS_REG_20, 0)
    emu.uc.reg_write(UC_MIPS_REG_21, sector_index)
    emu.uc.reg_write(UC_MIPS_REG_22, dest)
    emu.uc.reg_write(UC_MIPS_REG_30, 8)
    emu.uc.reg_write(UC_MIPS_REG_SP, sp)
    emu._write_u32_va(sp + 0x210, current_cluster)
    emu._write_u32_va(sp + 0x214, 100)
    emu._write_u32_va(sp + 0x21C, last_cluster)

dest1 = 0x80720000
sp1 = 0x80730000
setup_common(dest1, sp1, remaining=4096, sector=10, sector_index=2, current_cluster=3, last_cluster=5)
boundary_ok = emu._handle_file_read_sector_loop(0x8017A3A0)
boundary_data = bytes(emu.uc.mem_read(va_to_phys(dest1), 6 * 512))
boundary_regs = {{
    's2': emu.uc.reg_read(UC_MIPS_REG_18) & 0xffffffff,
    's3': emu.uc.reg_read(UC_MIPS_REG_19) & 0xffffffff,
    's5': emu.uc.reg_read(UC_MIPS_REG_21) & 0xffffffff,
    's6': emu.uc.reg_read(UC_MIPS_REG_22) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
    'copied': emu._read_u32_va_safe(sp1 + 0x214),
}}

dest2 = 0x80724000
sp2 = 0x80734000
setup_common(dest2, sp2, remaining=1024, sector=20, sector_index=1, current_cluster=4, last_cluster=6)
done_ok = emu._handle_file_read_sector_loop(0x8017A3A0)
done_data = bytes(emu.uc.mem_read(va_to_phys(dest2), 2 * 512))
done_regs = {{
    's2': emu.uc.reg_read(UC_MIPS_REG_18) & 0xffffffff,
    'pc': emu.uc.reg_read(UC_MIPS_REG_PC) & 0xffffffff,
    'copied': emu._read_u32_va_safe(sp2 + 0x214),
}}

dest3 = 0x80728000
sp3 = 0x80738000
setup_common(dest3, sp3, remaining=4096, sector=30, sector_index=2, current_cluster=5, last_cluster=5)
last_cluster_ok = emu._handle_file_read_sector_loop(0x8017A3A0)
emu.uc.reg_write(UC_MIPS_REG_17, 1)
mode1_ok = emu._handle_file_read_sector_loop(0x8017A3A0)

out = {{
    'boundary_ok': boundary_ok,
    'boundary_matches': boundary_data == b''.join(bytes([sector]) * 512 for sector in range(10, 16)),
    'boundary_regs': boundary_regs,
    'done_ok': done_ok,
    'done_matches': done_data == b'\\x14' * 512 + b'\\x15' * 512,
    'done_regs': done_regs,
    'last_cluster_ok': last_cluster_ok,
    'mode1_ok': mode1_ok,
    'file_read_loop_accel_count': emu.file_read_loop_accel_count,
    'events_tail': emu.file_read_loop_events[-4:],
}}
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("file-read-sector-loop-fastpath", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        boundary_regs = data.get("boundary_regs") or {}
        done_regs = data.get("done_regs") or {}
        if data.get("boundary_ok") is not True or data.get("boundary_matches") is not True:
            failures.append("file read sector loop did not copy expected cluster-boundary bytes")
        expected_boundary = {
            "s2": 1024,
            "s3": 16,
            "s5": 8,
            "s6": 0x80720000 + 6 * 512,
            "pc": 0x8017A41C,
            "copied": 100 + 6 * 512,
        }
        for key, expected in expected_boundary.items():
            if boundary_regs.get(key) != expected:
                failures.append(f"boundary reg {key} is {boundary_regs.get(key)}, expected {expected}")
        if data.get("done_ok") is not True or data.get("done_matches") is not True:
            failures.append("file read sector loop did not copy expected final bytes")
        if done_regs.get("s2") != 0 or done_regs.get("pc") != 0x8017A478 or done_regs.get("copied") != 1124:
            failures.append(f"done regs are {done_regs}")
        if data.get("last_cluster_ok") is not False:
            failures.append("last-cluster sector loop should fall back to firmware")
        if data.get("mode1_ok") is not False:
            failures.append("nonzero drive-mode sector loop should fall back to firmware")
        if int(data.get("file_read_loop_accel_count") or 0) != 2:
            failures.append(f"file read loop accel count is {data.get('file_read_loop_accel_count')}, expected 2")
    else:
        failures.append("file read sector loop fastpath command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_frontend_plain_mmio_fastpath(rows: list[dict[str, object]], timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_frontend_plain_mmio_fastpath.json"
    script = f"""
import argparse, json, sys
from pathlib import Path
from unicorn import UC_MEM_READ, UC_MEM_WRITE
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_frontend import FrontendState
from hwemu_defs import SADC_DATA, SADC_STATUS

args = argparse.Namespace(
    host='127.0.0.1',
    port=0,
    ram_mb=160,
    trace_limit=1000,
    boot_steps=30_000_000,
    input_steps=500_000,
    worker_slice_steps=250_000,
    worker_slice_seconds=0.25,
    frame_push_min_interval=0.08,
    boot_mode='c200',
    state_in=None,
    nand_image=None,
    readonly_nand_page_range=[],
    nand_loop_accelerator=True,
    resource_cache16_accelerator=True,
    auto_calibration=False,
    slow_global_code_hook=False,
    block_image=False,
    scheduler_tick_clamp=False,
    key_input_mode='hardware',
    orientation='rot180',
    quiet=True,
)
state = FrontendState(args)
emu = state.emu
calls = []
original = emu._model_mmio
def wrapped(access, address, size, value):
    calls.append((access, address, size, value))
    return original(access, address, size, value)
emu._model_mmio = wrapped
mem_write_log = []
original_mem_write = emu.uc.mem_write
def counted_mem_write(address, data):
    mem_write_log.append((address, len(data), bytes(data).hex()))
    return original_mem_write(address, data)
emu.uc.mem_write = counted_mem_write

before_suppressed = emu.suppressed_hot_event_count
emu.mmio_backing_u32_values.pop(0x10010200, None)
emu.nand_busy_reads = 0
mem_write_log.clear()
emu._on_mem(emu.uc, UC_MEM_READ, 0x10010200, 4, 0, None)
nand_ready_first_writes = len(mem_write_log)
nand_ready_first_backing = int.from_bytes(emu.uc.mem_read(0x10010200, 4), "little")
emu._on_mem(emu.uc, UC_MEM_READ, 0x10010200, 4, 0, None)
nand_ready_repeat_writes = len(mem_write_log) - nand_ready_first_writes
emu.nand_busy_reads = 1
emu._on_mem(emu.uc, UC_MEM_READ, 0x10010200, 4, 0, None)
nand_ready_changed_writes = len(mem_write_log) - nand_ready_first_writes - nand_ready_repeat_writes
nand_ready_busy_backing = int.from_bytes(emu.uc.mem_read(0x10010200, 4), "little")
emu._on_mem(emu.uc, UC_MEM_WRITE, 0x10000020, 4, 0x12345678, None)
after_plain_write_calls = len(calls)
after_plain_write_suppressed = emu.suppressed_hot_event_count
emu._on_mem(emu.uc, UC_MEM_READ, 0x10000020, 4, 0, None)
after_plain_read_calls = len(calls)
after_plain_read_suppressed = emu.suppressed_hot_event_count
emu.gpio_idle_levels[0x10010100] = 0x78040000
emu._on_mem(emu.uc, UC_MEM_READ, 0x10010100, 4, 0, None)
after_gpio_read_calls = len(calls)
after_gpio_read_suppressed = emu.suppressed_hot_event_count
gpio_read_backing = int.from_bytes(emu.uc.mem_read(0x10010100, 4), "little")
emu.set_key_controller_state(7, True)
gpio_key_down_backing = int.from_bytes(emu.uc.mem_read(0x10010100, 4), "little")
emu.set_key_controller_state(7, False)
gpio_key_up_backing = int.from_bytes(emu.uc.mem_read(0x10010100, 4), "little")
emu.sadc_status_event = 0x84
emu._on_mem(emu.uc, UC_MEM_READ, SADC_STATUS, 1, 0, None)
after_sadc_status_calls = len(calls)
after_sadc_status_suppressed = emu.suppressed_hot_event_count
sadc_status_backing = int.from_bytes(emu.uc.mem_read(SADC_STATUS, 1), "little")
emu._on_mem(emu.uc, UC_MEM_READ, SADC_DATA, 2, 0, None)
after_sadc_data_calls = len(calls)
emu._on_mem(emu.uc, UC_MEM_READ, 0x10030014, 1, 0, None)
after_uart_read_calls = len(calls)
uart_phys_backing = int.from_bytes(emu.uc.mem_read(0x10030014, 4), "little")
uart_alias_backing = int.from_bytes(emu.uc.mem_read(0xB0030014, 4), "little")
static_spans = emu._static_readonly_mmio_spans()
dynamic_spans = emu._dynamic_readonly_mmio_spans()
static_backing = {{
    f'0x{{addr:08x}}': int.from_bytes(emu.uc.mem_read(addr, 4), "little")
    for addr in (0x10003000, 0x10021004, 0x10030014, 0x1004300C, 0x13010114, 0x13020008, 0x13020028)
}}
static_alias_backing = {{
    f'0x{{addr:08x}}': int.from_bytes(emu.uc.mem_read(addr, 4), "little")
    for addr in (0xB0003000, 0xB0021004, 0xB0030014, 0xB004300C, 0xB3010114, 0xB3020008, 0xB3020028)
}}
bch_calls_before = len(calls)
emu.uc.mem_write(0x13010114, (0).to_bytes(4, "little"))
emu.uc.mem_write(0xB3010114, (0).to_bytes(4, "little"))
emu._on_mem(emu.uc, UC_MEM_READ, 0xB3010114, 4, 0, None)
bch_calls_after = len(calls)
bch_after_ack_phys = int.from_bytes(emu.uc.mem_read(0x13010114, 4), "little")
bch_after_ack_alias = int.from_bytes(emu.uc.mem_read(0xB3010114, 4), "little")
emu._on_mem(emu.uc, UC_MEM_WRITE, 0x10030014, 4, 0x0, None)
after_uart_write_calls = len(calls)
emu._on_mem(emu.uc, UC_MEM_WRITE, 0x1004300C, 4, 0x0, None)
after_static_status_write_calls = len(calls)
uart_phys_after_write = int.from_bytes(emu.uc.mem_read(0x10030014, 4), "little")
emu.sadc_status_event = 0
emu._sync_sadc_status_backing()
emu.set_touch_controller_state(20, 20, True)
gpio_touch_down_backing = int.from_bytes(emu.uc.mem_read(0x10010100, 4), "little")
sadc_down_backing = int.from_bytes(emu.uc.mem_read(SADC_STATUS, 4), "little") & 0xFF
sadc_down_alias_backing = int.from_bytes(emu.uc.mem_read(0xB007000C, 4), "little") & 0xFF
calls_before_sadc_ack = len(calls)
emu.mmio_regs[0x10070008] = 0x10
emu._on_mem(emu.uc, UC_MEM_WRITE, SADC_STATUS, 1, 0x04, None)
after_sadc_ack_calls = len(calls)
sadc_after_ack_backing = int.from_bytes(emu.uc.mem_read(SADC_STATUS, 4), "little") & 0xFF
emu.set_touch_controller_state(20, 20, False)
gpio_touch_up_backing = int.from_bytes(emu.uc.mem_read(0x10010100, 4), "little")
sadc_up_backing = int.from_bytes(emu.uc.mem_read(SADC_STATUS, 4), "little") & 0xFF

out = {{
    'plain_reg': '0x10000020',
    'nand_ready_first_writes': nand_ready_first_writes,
    'nand_ready_repeat_writes': nand_ready_repeat_writes,
    'nand_ready_changed_writes': nand_ready_changed_writes,
    'nand_ready_first_backing': nand_ready_first_backing,
    'nand_ready_busy_backing': nand_ready_busy_backing,
    'plain_mirror_value': emu.mmio_regs.get(0x10000020),
    'calls_after_plain_write': after_plain_write_calls,
    'calls_after_plain_read': after_plain_read_calls,
    'calls_after_gpio_read': after_gpio_read_calls,
    'calls_after_sadc_status': after_sadc_status_calls,
    'calls_after_sadc_data': after_sadc_data_calls,
    'calls_after_uart_read': after_uart_read_calls,
    'calls_after_uart_write': after_uart_write_calls,
    'calls_after_static_status_write': after_static_status_write_calls,
    'gpio_read_backing': gpio_read_backing,
    'gpio_key_down_backing': gpio_key_down_backing,
    'gpio_key_up_backing': gpio_key_up_backing,
    'gpio_touch_down_backing': gpio_touch_down_backing,
    'gpio_touch_up_backing': gpio_touch_up_backing,
    'sadc_status_backing': sadc_status_backing,
    'uart_phys_backing': uart_phys_backing,
    'uart_alias_backing': uart_alias_backing,
    'uart_phys_after_write': uart_phys_after_write,
    'sadc_down_backing': sadc_down_backing,
    'sadc_down_alias_backing': sadc_down_alias_backing,
    'calls_before_sadc_ack': calls_before_sadc_ack,
    'calls_after_sadc_ack': after_sadc_ack_calls,
    'sadc_after_ack_backing': sadc_after_ack_backing,
    'sadc_up_backing': sadc_up_backing,
    'static_backing': static_backing,
    'static_alias_backing': static_alias_backing,
    'bch_calls_before': bch_calls_before,
    'bch_calls_after': bch_calls_after,
    'bch_after_ack_phys': bch_after_ack_phys,
    'bch_after_ack_alias': bch_after_ack_alias,
    'static_spans': [[a, b] for a, b in static_spans],
    'dynamic_spans': [[a, b] for a, b in dynamic_spans],
    'suppressed_before': before_suppressed,
    'suppressed_after_plain_write': after_plain_write_suppressed,
    'suppressed_after_plain_read': after_plain_read_suppressed,
    'suppressed_after_gpio_read': after_gpio_read_suppressed,
    'suppressed_after_sadc_status': after_sadc_status_suppressed,
    'uart_call': calls[-1] if calls else None,
}}
state.stop()
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("frontend-plain-mmio-fastpath", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        if int(data.get("nand_ready_first_writes") or 0) != 2:
            failures.append(
                f"NAND-ready first read wrote {data.get('nand_ready_first_writes')} backing copies, expected 2"
            )
        if int(data.get("nand_ready_repeat_writes") or 0) != 0:
            failures.append(
                f"NAND-ready repeated read wrote backing {data.get('nand_ready_repeat_writes')} times"
            )
        if int(data.get("nand_ready_changed_writes") or 0) != 2:
            failures.append(
                f"NAND-ready value change wrote {data.get('nand_ready_changed_writes')} backing copies, expected 2"
            )
        if int(data.get("nand_ready_first_backing") or 0) != 0x48000000:
            failures.append(f"NAND-ready backing is {data.get('nand_ready_first_backing')}, expected 0x48000000")
        if int(data.get("nand_ready_busy_backing") or 0) != 0x08000000:
            failures.append(f"NAND-busy backing is {data.get('nand_ready_busy_backing')}, expected 0x08000000")
        if int(data.get("plain_mirror_value") or 0) != 0x12345678:
            failures.append(f"plain MMIO write mirror is {data.get('plain_mirror_value')}, expected 0x12345678")
        if int(data.get("calls_after_plain_write") or 0) != 0:
            failures.append("plain MMIO write went through _model_mmio")
        if int(data.get("calls_after_plain_read") or 0) != 0:
            failures.append("plain MMIO read went through _model_mmio")
        if int(data.get("calls_after_gpio_read") or 0) != 0:
            failures.append("GPIO read fastpath went through _model_mmio")
        if int(data.get("gpio_read_backing") or 0) != 0x78040000:
            failures.append(f"GPIO read backing is {data.get('gpio_read_backing')}, expected 0x78040000")
        if int(data.get("gpio_key_down_backing") or 0) != 0x70040000:
            failures.append(f"GPIO key-down backing is {data.get('gpio_key_down_backing')}, expected 0x70040000")
        if int(data.get("gpio_key_up_backing") or 0) != 0x78040000:
            failures.append(f"GPIO key-up backing is {data.get('gpio_key_up_backing')}, expected 0x78040000")
        if int(data.get("calls_after_sadc_status") or 0) != 0:
            failures.append("SADC status fastpath went through _model_mmio")
        if int(data.get("sadc_status_backing") or 0) != 0x84:
            failures.append(f"SADC status backing is {data.get('sadc_status_backing')}, expected 0x84")
        if int(data.get("calls_after_sadc_data") or 0) != 1:
            failures.append("SADC data read should remain on _model_mmio")
        if int(data.get("calls_after_uart_read") or 0) != 2:
            failures.append("semantic UART status read did not add exactly one _model_mmio call")
        if int(data.get("calls_after_uart_write") or 0) != 4:
            failures.append("UART status write did not stay on the semantic _model_mmio path")
        if int(data.get("calls_after_static_status_write") or 0) != 5:
            failures.append("static status write did not stay on the semantic _model_mmio path")
        if int(data.get("sadc_down_backing") or 0) != 0x14:
            failures.append(f"SADC down backing is {data.get('sadc_down_backing')}, expected 0x14")
        if int(data.get("sadc_down_alias_backing") or 0) != 0x14:
            failures.append(f"SADC down alias backing is {data.get('sadc_down_alias_backing')}, expected 0x14")
        if int(data.get("gpio_touch_down_backing") or 0) != 0x78000000:
            failures.append(f"GPIO touch-down backing is {data.get('gpio_touch_down_backing')}, expected 0x78000000")
        if int(data.get("calls_after_sadc_ack") or 0) != int(data.get("calls_before_sadc_ack") or 0) + 1:
            failures.append("SADC status ack write did not stay on _model_mmio")
        if int(data.get("sadc_after_ack_backing") or 0) != 0x14:
            failures.append(f"SADC ack backing is {data.get('sadc_after_ack_backing')}, expected 0x14")
        if int(data.get("sadc_up_backing") or 0) != 0x08:
            failures.append(f"SADC up backing is {data.get('sadc_up_backing')}, expected 0x08")
        if int(data.get("gpio_touch_up_backing") or 0) != 0x78040000:
            failures.append(f"GPIO touch-up backing is {data.get('gpio_touch_up_backing')}, expected 0x78040000")
        if int(data.get("uart_phys_backing") or 0) != 0x60:
            failures.append(f"UART status physical backing is {data.get('uart_phys_backing')}, expected 0x60")
        if int(data.get("uart_alias_backing") or 0) != 0x60:
            failures.append(f"UART status alias backing is {data.get('uart_alias_backing')}, expected 0x60")
        if int(data.get("uart_phys_after_write") or 0) != 0x60:
            failures.append(f"UART status backing changed after write: {data.get('uart_phys_after_write')}")
        if int(data.get("bch_calls_after") or 0) != int(data.get("bch_calls_before") or 0) + 1:
            failures.append("BCH status read did not stay on the semantic _model_mmio path")
        if int(data.get("bch_after_ack_phys") or 0) != 0x0D:
            failures.append(f"BCH status physical backing is {data.get('bch_after_ack_phys')}, expected 0x0d")
        if int(data.get("bch_after_ack_alias") or 0) != 0x0D:
            failures.append(f"BCH status alias backing is {data.get('bch_after_ack_alias')}, expected 0x0d")
        static_spans = data.get("static_spans") or []
        if [0x10030014, 0x10030017] not in static_spans:
            failures.append("UART status physical read hole missing")
        if [0xB0030014, 0xB0030017] not in static_spans:
            failures.append("UART status alias read hole missing")
        dynamic_spans = data.get("dynamic_spans") or []
        if [0x1007000C, 0x1007000F] not in dynamic_spans:
            failures.append("SADC status physical read hole missing")
        if [0xB007000C, 0xB007000F] not in dynamic_spans:
            failures.append("SADC status alias read hole missing")
        for addr in (0x10010000, 0x10010100, 0x10010300):
            if [addr, addr + 3] not in dynamic_spans:
                failures.append(f"GPIO data read hole missing for 0x{addr:08x}")
            alias = 0xB0000000 + (addr - 0x10000000)
            if [alias, alias + 3] not in dynamic_spans:
                failures.append(f"GPIO data alias read hole missing for 0x{addr:08x}")
        if [0x10010200, 0x10010203] in dynamic_spans:
            failures.append("GPIO C/NAND-ready data register must remain hooked")
        expected_static = {
            "0x10003000": 0x80,
            "0x10021004": 0x800,
            "0x10030014": 0x60,
            "0x1004300c": 0x80,
            "0x13010114": 0x0D,
            "0x13020008": 0,
            "0x13020028": 0,
        }
        semantic_static = {"0x13010114", "0x13020008", "0x13020028"}
        static_backing = data.get("static_backing") or {}
        for key, expected in expected_static.items():
            if int(static_backing.get(key) or 0) != expected:
                failures.append(f"static backing {key} is {static_backing.get(key)}, expected {expected}")
            addr = int(key, 16)
            if key in semantic_static:
                if [addr, addr + 3] in static_spans:
                    failures.append(f"write-sensitive static read should stay hooked for {key}")
            elif [addr, addr + 3] not in static_spans:
                failures.append(f"static read hole missing for {key}")
        expected_alias = {
            "0xb0003000": 0x80,
            "0xb0021004": 0x800,
            "0xb0030014": 0x60,
            "0xb004300c": 0x80,
            "0xb3010114": 0x0D,
            "0xb3020008": 0,
            "0xb3020028": 0,
        }
        semantic_static_alias = {"0xb3010114", "0xb3020008", "0xb3020028"}
        static_alias_backing = data.get("static_alias_backing") or {}
        for key, expected in expected_alias.items():
            if int(static_alias_backing.get(key) or 0) != expected:
                failures.append(f"static alias backing {key} is {static_alias_backing.get(key)}, expected {expected}")
            addr = int(key, 16)
            if key in semantic_static_alias:
                if [addr, addr + 3] in static_spans:
                    failures.append(f"write-sensitive static alias read should stay hooked for {key}")
            elif [addr, addr + 3] not in static_spans:
                failures.append(f"static alias read hole missing for {key}")
        if int(data.get("suppressed_after_plain_write") or 0) <= int(data.get("suppressed_before") or 0):
            failures.append("plain MMIO write did not increment suppressed hot-event count")
        if int(data.get("suppressed_after_plain_read") or 0) <= int(data.get("suppressed_after_plain_write") or 0):
            failures.append("plain MMIO read did not increment suppressed hot-event count")
        if int(data.get("suppressed_after_gpio_read") or 0) <= int(data.get("suppressed_after_plain_read") or 0):
            failures.append("GPIO read did not increment suppressed hot-event count")
        if int(data.get("suppressed_after_sadc_status") or 0) <= int(data.get("suppressed_after_gpio_read") or 0):
            failures.append("SADC status read did not increment suppressed hot-event count")
    else:
        failures.append("frontend plain MMIO fastpath command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_frontend_cold_menu_smoke(rows: list[dict[str, object]], timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_frontend_cold_menu.json"
    script = f"""
import argparse, hashlib, json, sys, time
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_frontend import FrontendState, display_to_touch_point

args = argparse.Namespace(
    host='127.0.0.1',
    port=0,
    ram_mb=160,
    trace_limit=1000,
    boot_steps=30_000_000,
    input_steps=500_000,
    worker_slice_steps=250_000,
    worker_slice_seconds=0.5,
    frame_push_min_interval=0.08,
    boot_mode='c200',
    state_in=None,
    nand_image=None,
    nand_loop_accelerator=True,
    resource_cache16_accelerator=True,
    auto_calibration=True,
    slow_global_code_hook=False,
    block_image=False,
    scheduler_tick_clamp=False,
    key_input_mode='hardware',
    orientation='rot180',
    quiet=True,
)
state = FrontendState(args)
started = time.perf_counter()
state.run_start('cold-menu-smoke', 15_000_000, 250_000)
deadline = time.time() + 45
snap = state.snapshot()
while time.time() < deadline:
    while state.pop_queued_frame() is not None:
        pass
    snap = state.snapshot()
    job = snap.get('job') or {{}}
    framebuffer = snap.get('framebuffer') or {{}}
    if (
        int(snap.get('auto_calibration_stage') or 0) >= 12
        and int(framebuffer.get('nonzero_pixels') or 0) >= 25_000
        and int(framebuffer.get('unique_pixel_values') or 0) >= 200
    ):
        break
    time.sleep(0.05)
state.stop()
before_png = state.dump_frame()
snap = state.snapshot()
job = snap.get('job') or {{}}
framebuffer = snap.get('framebuffer') or {{}}
state.key(7, True, advance=True)
state.key(7, False, advance=True)
after_png = state.dump_frame()
after_snap = state.snapshot()
after_framebuffer = after_snap.get('framebuffer') or {{}}
touch_irq_before = state.emu.trace_pc_counts.get(0x8001A8FC, 0)
touch_adc_before = state.emu.trace_pc_counts.get(0x8001AC40, 0)
touch_queue_before = state.emu.trace_pc_counts.get(0x8000B3DC, 0)
touch_gui_before = state.emu.trace_pc_counts.get(0x800DD380, 0)
touch_display = (210, 287)
touch_point = display_to_touch_point(touch_display[0], touch_display[1], 240, 320, 'rot180')
state.command({{
    'op': 'touch',
    'display_x': touch_display[0],
    'display_y': touch_display[1],
    'display_width': 240,
    'display_height': 320,
    'down': True,
    'advance': True,
}})
state.command({{
    'op': 'touch',
    'display_x': touch_display[0],
    'display_y': touch_display[1],
    'display_width': 240,
    'display_height': 320,
    'down': False,
    'advance': True,
}})
after_touch_png = state.dump_frame()
after_touch_snap = state.snapshot()
after_touch_framebuffer = after_touch_snap.get('framebuffer') or {{}}
out = {{
    'running': snap.get('running'),
    'job_done_steps': job.get('done_steps'),
    'job_chunk_steps': job.get('chunk_steps'),
    'auto_calibration_stage': snap.get('auto_calibration_stage'),
    'auto_calibration_stage_label': snap.get('auto_calibration_stage_label'),
    'insn_count': snap.get('insn_count'),
    'pc': snap.get('pc'),
    'framebuffer_nonzero_pixels': framebuffer.get('nonzero_pixels'),
    'framebuffer_unique_pixel_values': framebuffer.get('unique_pixel_values'),
    'menu_png_sha256': hashlib.sha256(before_png).hexdigest(),
    'after_key_png_sha256': hashlib.sha256(after_png).hexdigest(),
    'after_key_nonzero_pixels': after_framebuffer.get('nonzero_pixels'),
    'after_key_unique_pixel_values': after_framebuffer.get('unique_pixel_values'),
    'after_key_mode': after_snap.get('key_input_mode'),
    'after_key_pending_keys': after_snap.get('pending_keys'),
    'after_key_stop_reason': after_snap.get('stop_reason'),
    'after_touch_irq12_before': touch_irq_before,
    'after_touch_irq12_after': state.emu.trace_pc_counts.get(0x8001A8FC, 0),
    'after_touch_adc_before': touch_adc_before,
    'after_touch_adc_after': state.emu.trace_pc_counts.get(0x8001AC40, 0),
    'after_touch_queue_before': touch_queue_before,
    'after_touch_queue_after': state.emu.trace_pc_counts.get(0x8000B3DC, 0),
    'after_touch_gui_before': touch_gui_before,
    'after_touch_gui_after': state.emu.trace_pc_counts.get(0x800DD380, 0),
    'after_touch_display': list(touch_display),
    'after_touch_point': list(touch_point),
    'after_touch_png_sha256': hashlib.sha256(after_touch_png).hexdigest(),
    'after_touch_nonzero_pixels': after_touch_framebuffer.get('nonzero_pixels'),
    'after_touch_unique_pixel_values': after_touch_framebuffer.get('unique_pixel_values'),
    'after_touch_pending_touches': after_touch_snap.get('pending_touches'),
    'after_touch_stop_reason': after_touch_snap.get('stop_reason'),
    'stop_reason': snap.get('stop_reason'),
    'elapsed_seconds': round(time.perf_counter() - started, 3),
}}
Path({str(json_out)!r}).write_text(json.dumps(out, indent=2), encoding='utf-8')
"""
    row = run_command("frontend-cold-menu-smoke", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    failures: list[str] = []
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        if not isinstance(data.get("job_done_steps"), int) or int(data.get("job_done_steps") or 0) <= 0:
            failures.append(f"frontend cold-menu job completed {data.get('job_done_steps')} steps")
        if data.get("job_chunk_steps") != 250_000:
            failures.append(f"frontend auto-calibration chunk is {data.get('job_chunk_steps')}")
        if int(data.get("auto_calibration_stage") or 0) < 12:
            failures.append(
                f"auto calibration stage is {data.get('auto_calibration_stage_label')} "
                f"({data.get('auto_calibration_stage')}), expected done"
            )
        if int(data.get("framebuffer_nonzero_pixels") or 0) < 25_000:
            failures.append(f"frontend menu framebuffer has too few nonzero pixels: {data.get('framebuffer_nonzero_pixels')}")
        if int(data.get("framebuffer_unique_pixel_values") or 0) < 200:
            failures.append(
                f"frontend menu framebuffer has too few unique pixel values: {data.get('framebuffer_unique_pixel_values')}"
            )
        if data.get("after_key_mode") != "hardware":
            failures.append(f"frontend key mode after cold menu is {data.get('after_key_mode')}")
        if data.get("after_key_pending_keys") != 0:
            failures.append(f"frontend key path left pending_keys={data.get('after_key_pending_keys')}")
        if data.get("menu_png_sha256") == data.get("after_key_png_sha256"):
            failures.append("frontend hardware right-key did not change the menu framebuffer")
        if int(data.get("after_key_nonzero_pixels") or 0) < 25_000:
            failures.append(f"frontend post-key framebuffer has too few nonzero pixels: {data.get('after_key_nonzero_pixels')}")
        if int(data.get("after_key_unique_pixel_values") or 0) < 200:
            failures.append(
                f"frontend post-key framebuffer has too few unique pixel values: {data.get('after_key_unique_pixel_values')}"
            )
        if data.get("after_key_stop_reason"):
            failures.append(f"frontend hardware right-key stop_reason={data.get('after_key_stop_reason')}")
        if int(data.get("after_touch_irq12_after") or 0) <= int(data.get("after_touch_irq12_before") or 0):
            failures.append(
                "frontend touch did not reach IRQ12 handler 0x8001a8fc "
                f"({data.get('after_touch_irq12_before')} -> {data.get('after_touch_irq12_after')})"
            )
        if int(data.get("after_touch_adc_after") or 0) <= int(data.get("after_touch_adc_before") or 0):
            failures.append(
                "frontend touch did not reach SADC coordinate sampler 0x8001ac40 "
                f"({data.get('after_touch_adc_before')} -> {data.get('after_touch_adc_after')})"
            )
        if int(data.get("after_touch_queue_after") or 0) <= int(data.get("after_touch_queue_before") or 0):
            failures.append(
                "frontend touch did not post GUI/input queue event 0x8000b3dc "
                f"({data.get('after_touch_queue_before')} -> {data.get('after_touch_queue_after')})"
            )
        if int(data.get("after_touch_gui_after") or 0) <= int(data.get("after_touch_gui_before") or 0):
            failures.append(
                "frontend touch did not reach GUI dispatch 0x800dd380 "
                f"({data.get('after_touch_gui_before')} -> {data.get('after_touch_gui_after')})"
            )
        if data.get("after_key_png_sha256") == data.get("after_touch_png_sha256"):
            failures.append(
                "frontend display-coordinate touch did not change the menu framebuffer "
                f"at display={data.get('after_touch_display')} touch={data.get('after_touch_point')}"
            )
        if int(data.get("after_touch_nonzero_pixels") or 0) < 25_000:
            failures.append(f"frontend post-touch framebuffer has too few nonzero pixels: {data.get('after_touch_nonzero_pixels')}")
        if int(data.get("after_touch_unique_pixel_values") or 0) < 200:
            failures.append(
                f"frontend post-touch framebuffer has too few unique pixel values: {data.get('after_touch_unique_pixel_values')}"
            )
        if data.get("after_touch_pending_touches") != 0:
            failures.append(f"frontend touch path left pending_touches={data.get('after_touch_pending_touches')}")
        if data.get("after_touch_stop_reason"):
            failures.append(f"frontend touch stop_reason={data.get('after_touch_stop_reason')}")
        if not isinstance(data.get("insn_count"), int) or data.get("insn_count") <= 0:
            failures.append("frontend cold-menu smoke did not advance instruction count")
        if data.get("stop_reason"):
            failures.append(f"frontend cold-menu stop_reason={data.get('stop_reason')}")
    else:
        failures.append("frontend cold-menu smoke command returned nonzero or wrote no JSON")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_key_controller_scan(rows: list[dict[str, object]], c200: Path, nand_image: Path, timeout: int) -> None:
    state_in = first_existing(
        [
            BUILD / "hwemu_known_delay_menu_smoke_release.pkl",
            BUILD / "hwemu_refactor_menu_smoke_release.pkl",
            BUILD / "hwemu_menu_ready_stage_probe.pkl",
        ]
    )
    json_out = BUILD / "hwemu_regression_key_controller_scan.json"
    png_out = BUILD / "hwemu_regression_key_controller_scan.png"
    failures: list[str] = []
    if state_in is None:
        rows.append(
            {
                "name": "key-controller-scan",
                "ok": False,
                "failures": ["missing a known menu checkpoint"],
            }
        )
        return
    cmd = [
        sys.executable,
        str(HWEMU),
        "--profile",
        "bbk9588-uboot",
        "--image",
        str(c200),
        "--base",
        "0x80004000",
        "--pc",
        "0x80004000",
        "--ram-mb",
        "160",
        "--state-in",
        str(state_in),
        "--json-out",
        str(json_out),
        "--fb-dump",
        str(png_out),
        "--max-seconds",
        "15",
        "--steps",
        "3000000",
        "--fast-hooks",
        "--nand-loop-accelerator",
        "--resource-cache16-accelerator",
        "--no-block-image",
        "--nand-image",
        str(nand_image),
        "--idle-stop-hits",
        "100",
        "--trace-limit",
        "512",
        "--fb-width",
        "240",
        "--fb-height",
        "320",
        "--quiet",
        "--watch-input-state",
        "--key-controller-event",
        "7:1@1",
        "--call-va",
        "0x8001b464@2",
    ]
    row = run_command("key-controller-scan", cmd, timeout)
    row.update({"state_in": str(state_in), "json": str(json_out), "png": str(png_out)})
    if row["ok"]:
        execution = load_execution(json_out)
        watch = execution.get("watch") if isinstance(execution.get("watch"), dict) else {}
        calls = watch.get("calls") if isinstance(watch.get("calls"), list) else []
        call_events = watch.get("call_events") if isinstance(watch.get("call_events"), list) else []
        key_log = watch.get("key_controller_event_log") if isinstance(watch.get("key_controller_event_log"), list) else []
        row["stop_reason"] = execution.get("stop_reason")
        row["invalid_count"] = len(execution.get("invalid", []))
        row["scanner_return"] = None
        for event in call_events:
            if event.get("event") == "return" and event.get("target") == "0x8001b464":
                row["scanner_return"] = event.get("v0")
                break
        if row["invalid_count"] != 0:
            failures.append("invalid memory accesses were recorded")
        if not calls or not bool(calls[0].get("returned")):
            failures.append("scanner scheduled call did not return")
        if row["scanner_return"] != "0x00000007":
            failures.append(f"scanner returned {row['scanner_return']}, expected 0x00000007")
        if not any(
            isinstance(item, dict)
            and item.get("code") == 7
            and item.get("levels", {}).get("0x10010100") == "0x70040000"
            for item in key_log
        ):
            failures.append("GPIO key controller did not drive code 7 active-low level")
    else:
        failures.append("key controller scan command returned nonzero")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_key_controller_irq(rows: list[dict[str, object]], c200: Path, nand_image: Path, timeout: int) -> None:
    state_in = first_existing(
        [
            BUILD / "hwemu_known_delay_menu_smoke_release.pkl",
            BUILD / "hwemu_refactor_menu_smoke_release.pkl",
            BUILD / "hwemu_menu_ready_stage_probe.pkl",
        ]
    )
    json_out = BUILD / "hwemu_regression_key_controller_irq.json"
    png_out = BUILD / "hwemu_regression_key_controller_irq.png"
    failures: list[str] = []
    if state_in is None:
        rows.append(
            {
                "name": "key-controller-irq",
                "ok": False,
                "failures": ["missing a known menu checkpoint"],
            }
        )
        return
    cmd = [
        sys.executable,
        str(HWEMU),
        "--profile",
        "bbk9588-uboot",
        "--image",
        str(c200),
        "--base",
        "0x80004000",
        "--pc",
        "0x80004000",
        "--ram-mb",
        "160",
        "--state-in",
        str(state_in),
        "--json-out",
        str(json_out),
        "--fb-dump",
        str(png_out),
        "--max-seconds",
        "20",
        "--steps",
        "8000000",
        "--fast-hooks",
        "--nand-loop-accelerator",
        "--resource-cache16-accelerator",
        "--no-block-image",
        "--nand-image",
        str(nand_image),
        "--idle-stop-hits",
        "500",
        "--trace-limit",
        "2000",
        "--fb-width",
        "240",
        "--fb-height",
        "320",
        "--quiet",
        "--watch-input-state",
        "--key-controller-event",
        "7:1@1",
        "--key-controller-event",
        "7:0@40",
        "--trace-pc",
        "0x8001b620",
    ]
    row = run_command("key-controller-irq", cmd, timeout)
    row.update({"state_in": str(state_in), "json": str(json_out), "png": str(png_out)})
    if row["ok"]:
        execution = load_execution(json_out)
        watch = execution.get("watch") if isinstance(execution.get("watch"), dict) else {}
        events = execution.get("events") if isinstance(execution.get("events"), list) else []
        trace_counts = ((watch.get("trace_pc") or {}).get("counts") or {}) if isinstance(watch, dict) else {}
        mmio_snapshot = execution.get("mmio_snapshot") if isinstance(execution.get("mmio_snapshot"), dict) else {}
        gpio_regs = mmio_snapshot.get("gpio_regs") if isinstance(mmio_snapshot.get("gpio_regs"), dict) else {}
        row["stop_reason"] = execution.get("stop_reason")
        row["invalid_count"] = len(execution.get("invalid", []))
        row["gpio_isr_hits"] = trace_counts.get("0x8001b620")
        if row["invalid_count"] != 0:
            failures.append("invalid memory accesses were recorded")
        if int(row["gpio_isr_hits"] or 0) < 2:
            failures.append(f"GPIO ISR hit count is {row['gpio_isr_hits']}, expected at least 2")
        if not any(item.get("kind") == "wait-gpio-subirq" and item.get("value") == "0x0000006b" for item in events):
            failures.append("GPIOB bit27 did not dispatch as subirq 0x6b")
        if not any(
            item.get("kind") == "wait-irq-service"
            and item.get("target") == "0x8001b620"
            and item.get("value") == "0x0000006b"
            for item in events
        ):
            failures.append("GPIO subirq did not service real key ISR 0x8001b620")
        if gpio_regs.get("0x10010180") != "0x0":
            failures.append(f"GPIOB flag register left pending: {gpio_regs.get('0x10010180')}")
    else:
        failures.append("key controller IRQ command returned nonzero")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_menu_checkpoint(rows: list[dict[str, object]], c200: Path, nand_image: Path, timeout: int) -> None:
    state_in = first_existing(
        [
            BUILD / "hwemu_known_delay_menu_smoke_release.pkl",
            BUILD / "hwemu_refactor_menu_smoke_release.pkl",
            BUILD / "hwemu_menu_ready_stage_probe.pkl",
        ]
    )
    json_out = BUILD / "hwemu_regression_menu_checkpoint.json"
    png_out = BUILD / "hwemu_regression_menu_checkpoint.png"
    failures: list[str] = []
    if state_in is None:
        rows.append(
            {
                "name": "menu-checkpoint",
                "ok": False,
                "failures": ["missing a known menu checkpoint"],
            }
        )
        return
    cmd = [
        sys.executable,
        str(HWEMU),
        "--profile",
        "bbk9588-uboot",
        "--image",
        str(c200),
        "--base",
        "0x80004000",
        "--pc",
        "0x80004000",
        "--ram-mb",
        "160",
        "--state-in",
        str(state_in),
        "--json-out",
        str(json_out),
        "--fb-dump",
        str(png_out),
        "--max-seconds",
        "15",
        "--steps",
        "250000",
        "--fast-hooks",
        "--nand-loop-accelerator",
        "--resource-cache16-accelerator",
        "--no-block-image",
        "--nand-image",
        str(nand_image),
        "--trace-limit",
        "256",
        "--fb-width",
        "240",
        "--fb-height",
        "320",
        "--quiet",
    ]
    row = run_command("menu-checkpoint", cmd, timeout)
    row.update({"state_in": str(state_in), "json": str(json_out), "png": str(png_out)})
    if row["ok"]:
        execution = load_execution(json_out)
        framebuffer = execution.get("framebuffer") or {}
        nonzero = int(framebuffer.get("nonzero_pixels") or 0) if isinstance(framebuffer, dict) else 0
        row["stop_reason"] = execution.get("stop_reason")
        row["invalid_count"] = len(execution.get("invalid", []))
        row["nonzero_pixels"] = nonzero
        if row["invalid_count"] != 0:
            failures.append("invalid memory accesses were recorded")
        if nonzero < 20000:
            failures.append("framebuffer does not look like a rendered menu")
    else:
        failures.append("menu checkpoint command returned nonzero")
    row["failures"] = failures
    row["ok"] = row["ok"] and not failures
    rows.append(row)


def add_menu_smoke(rows: list[dict[str, object]], nand_image: Path, timeout: int) -> None:
    state_in = BUILD / "hwemu_cold_boot_to_menu_check3_menu.pkl"
    if not state_in.is_file():
        rows.append(
            {
                "name": "menu-touch-smoke",
                "ok": False,
                "failures": [f"missing checkpoint {state_in}"],
            }
        )
        return
    cmd = [
        sys.executable,
        str(Path("reverse") / "hwemu" / "run_system_menu_smoke.py"),
        "--state-in",
        str(state_in),
        "--no-block-image",
        "--nand-image",
        str(nand_image),
        "--prefix",
        "hwemu_regression_menu_touch",
        "--timeout",
        str(timeout),
    ]
    row = run_command("menu-touch-smoke", cmd, timeout + 20)
    rows.append(row)


def add_framebuffer_format_equivalence(rows: list[dict[str, object]], timeout: int) -> None:
    json_out = BUILD / "hwemu_regression_framebuffer_format.json"
    script = f"""
import json, sys
from pathlib import Path
root = Path({str(ROOT)!r})
sys.path.insert(0, str(root / 'reverse' / 'hwemu'))
from hwemu_framebuffer import rgb565_raw_to_info_rgb

cases = [
    ('rgb565', bytes.fromhex('00f81f00'), bytes([255, 0, 0, 0, 0, 255])),
    ('bgr565', bytes.fromhex('00f81f00'), bytes([0, 0, 255, 255, 0, 0])),
    ('rgb565-be', bytes.fromhex('f800001f'), bytes([255, 0, 0, 0, 0, 255])),
    ('bgr565-be', bytes.fromhex('f800001f'), bytes([0, 0, 255, 255, 0, 0])),
]
failures = []
for fmt, raw, expected in cases:
    info, rgb = rgb565_raw_to_info_rgb(raw, 0xA1F82000, 0, 2, 1, 2, fmt, 'raw')
    if rgb != expected:
        failures.append(f'{{fmt}} raw rgb={{rgb.hex()}} expected={{expected.hex()}}')
    if info.get('unique_pixel_values') != 2 or info.get('nonzero_bbox') != [0, 0, 1, 0]:
        failures.append(f'{{fmt}} info={{info}}')
    _info, rot = rgb565_raw_to_info_rgb(raw, 0xA1F82000, 0, 2, 1, 2, fmt, 'rot180')
    if rot != expected[3:6] + expected[0:3]:
        failures.append(f'{{fmt}} rot180 rgb={{rot.hex()}}')
Path({str(json_out)!r}).write_text(json.dumps({{'failures': failures}}, indent=2), encoding='utf-8')
raise SystemExit(1 if failures else 0)
"""
    row = run_command("framebuffer-format-equivalence", [sys.executable, "-c", script], timeout)
    row.update({"json": str(json_out)})
    if row["ok"] and json_out.is_file():
        data = json.loads(json_out.read_text(encoding="utf-8"))
        row["failures"] = data.get("failures", [])
        row["ok"] = not row["failures"]
    elif not row["ok"]:
        row["failures"] = ["framebuffer format equivalence command failed"]
    rows.append(row)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run BBK9588 hwemu refactor regression checks.")
    ap.add_argument(
        "--nand-image",
        type=Path,
        default=BUILD / "bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin",
    )
    ap.add_argument("--summary-json", type=Path, default=BUILD / "hwemu_regression_summary.json")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--menu-smoke", action="store_true", help="Also run the slower menu touch smoke.")
    args = ap.parse_args(argv)

    BUILD.mkdir(parents=True, exist_ok=True)
    if not args.nand_image.is_file():
        raise FileNotFoundError(args.nand_image)
    c200 = find_c200()

    rows: list[dict[str, object]] = []
    rows.append(
        run_command(
            "py-compile",
            [sys.executable, "-m", "py_compile", *[str(path) for path in PY_COMPILE_FILES]],
            args.timeout,
        )
    )
    add_cli_short_boot(rows, c200, args.nand_image, args.timeout)
    add_framebuffer_format_equivalence(rows, args.timeout)
    add_key_pulse_parse(rows, c200, args.timeout)
    add_frontend_state_defaults(rows, args.timeout)
    add_frontend_touch_mapping(rows, args.timeout)
    add_frontend_ws_codec(rows, args.timeout)
    add_frontend_http_ws_smoke(rows, args.timeout)
    add_frontend_deferred_frame(rows, args.timeout)
    add_frontend_input_worker_timeout(rows, args.timeout)
    add_frontend_direct_idle_trace(rows, args.timeout)
    add_glyph_mask_fastpath(rows, c200, args.timeout)
    add_lfn_copy_fastpath(rows, c200, args.timeout)
    add_resource_cache16_fastpath(rows, c200, args.timeout)
    add_fat16_cluster_cache_fastpath(rows, c200, args.timeout)
    add_block_read_wrapper_fastpath(rows, c200, args.timeout)
    add_file_read_sector_loop_fastpath(rows, c200, args.timeout)
    add_frontend_plain_mmio_fastpath(rows, args.timeout)
    add_frontend_cold_menu_smoke(rows, args.timeout)
    add_key_controller_scan(rows, c200, args.nand_image, args.timeout)
    add_key_controller_irq(rows, c200, args.nand_image, args.timeout)
    add_menu_checkpoint(rows, c200, args.nand_image, args.timeout)
    if args.menu_smoke:
        add_menu_smoke(rows, args.nand_image, args.timeout)

    summary = {"ok": all(row.get("ok") for row in rows), "cases": rows}
    args.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for row in rows:
        status = "OK" if row.get("ok") else "FAIL"
        print(
            f"{status} {row['name']}: elapsed={row.get('elapsed_seconds')}s "
            f"stop={row.get('stop_reason')} invalid={row.get('invalid_count')} "
            f"pixels={row.get('nonzero_pixels')}"
        )
        for failure in row.get("failures", []):
            print(f"  - {failure}")
    print(f"summary: {args.summary_json}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
