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
toggle_snap = state.command({{'op': 'auto-calibration', 'enabled': True}})
out = {{
    'key_input_mode': snap.get('key_input_mode'),
    'auto_calibration_initial': snap.get('auto_calibration'),
    'auto_calibration_after_toggle': toggle_snap.get('auto_calibration'),
    'reset_elapsed_seconds': snap.get('reset_elapsed_seconds'),
    'run_elapsed_seconds': snap.get('run_elapsed_seconds'),
    'worker_slice_steps': args.worker_slice_steps,
    'nand_loop_accelerator': args.nand_loop_accelerator,
    'trace_pc_detail': state.emu.trace_pc_detail,
    'running': snap.get('running'),
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
        if data.get("trace_pc_detail") is not False:
            failures.append("frontend should count trace PCs without detailed register snapshots")
        if not isinstance(data.get("reset_elapsed_seconds"), (int, float)):
            failures.append("reset_elapsed_seconds missing from frontend snapshot")
        if data.get("run_elapsed_seconds") is not None:
            failures.append("run_elapsed_seconds should be None before a run starts")
        if data.get("running") is not False:
            failures.append("frontend should not be running immediately after reset")
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
            "rot180_visible_topleft": [239, 319],
            "rot180_visible_bottomright": [0, 0],
            "rot180_scaled_bottomright": [0, 0],
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
        if data.get("queued") != [[239, 319, True], [0, 0, False]]:
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
from hwemu_frontend_ws import encode_ws_frame, read_ws_frame, recv_ws_text, websocket_accept_key

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

masked_text = encode_ws_frame(0x1, b'hello', mask=b'\\x01\\x02\\x03\\x04')
binary_126 = encode_ws_frame(0x2, b'a' * 130)
binary_127 = encode_ws_frame(0x2, b'b' * 66000)
opcode_126, payload_126 = read_ws_frame(ChunkSocket(binary_126, [1, 2, 3, 5, 8]))
opcode_127, payload_127 = read_ws_frame(ChunkSocket(binary_127, [1, 1, 2, 3, 7, 4096]))
out = {{
    'accept': websocket_accept_key('dGhlIHNhbXBsZSBub25jZQ=='),
    'masked_text': recv_ws_text(ChunkSocket(masked_text, [1, 1, 2, 1, 3])),
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
        input_steps=500_000,
        worker_slice_steps=250_000,
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
    initial_png = None
    deadline = time.time() + 5
    while time.time() < deadline and (initial_ws is None or initial_png is None):
        opcode, payload = recv_ws_frame(sock)
        if opcode == 0x1:
            initial_ws = json.loads(payload.decode('utf-8'))
        elif opcode == 0x2 and payload.startswith(b'\\x89PNG\\r\\n\\x1a\\n'):
            initial_png = {{
                'bytes': len(payload),
                'signature': payload[:8].hex(),
            }}
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
    send_ws_text(sock, json.dumps({{'op': 'run-start', 'name': 'ws-smoke', 'steps': 250000, 'chunk': 250000}}))
    run_done_ws = None
    deadline = time.time() + 15
    while time.time() < deadline:
        opcode, payload = recv_ws_frame(sock)
        if opcode != 0x1:
            continue
        item = json.loads(payload.decode('utf-8'))
        job = item.get('job') or {{}}
        if job.get('name') == 'ws-smoke' and job.get('done_steps', 0) >= 250000 and not item.get('running'):
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
        if job.get('name') == 'input' and job.get('done_steps', 0) >= 500000 and not item.get('running'):
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
        if job.get('name') == 'input' and job.get('done_steps', 0) >= 500000 and not item.get('running'):
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
        'ws_initial_png_bytes': None if initial_png is None else initial_png.get('bytes'),
        'ws_initial_png_signature': None if initial_png is None else initial_png.get('signature'),
        'ws_pending_keys_after_key': None if queued_ws is None else queued_ws.get('pending_keys'),
        'ws_key_input_mode': None if queued_ws is None else queued_ws.get('key_input_mode'),
        'ws_run_done_steps': None if run_job is None else run_job.get('done_steps'),
        'ws_run_chunk_steps': None if run_job is None else run_job.get('chunk_steps'),
        'ws_run_elapsed_seconds_type': None if run_done_ws is None else type(run_done_ws.get('run_elapsed_seconds')).__name__,
        'ws_run_running': None if run_done_ws is None else run_done_ws.get('running'),
        'ws_run_insn_count': None if run_done_ws is None else run_done_ws.get('insn_count'),
        'ws_input_done_steps': None if input_job is None else input_job.get('done_steps'),
        'ws_input_chunk_steps': None if input_job is None else input_job.get('chunk_steps'),
        'ws_input_running': None if input_run_done_ws is None else input_run_done_ws.get('running'),
        'ws_input_pending_touches': None if input_run_done_ws is None else input_run_done_ws.get('pending_touches'),
        'ws_input_release_done_steps': None if input_release_job is None else input_release_job.get('done_steps'),
        'ws_input_release_chunk_steps': None if input_release_job is None else input_release_job.get('chunk_steps'),
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
        if not isinstance(data.get("ws_initial_png_bytes"), int) or data.get("ws_initial_png_bytes") <= 8:
            failures.append("WebSocket did not deliver an initial binary PNG frame")
        if data.get("ws_initial_png_signature") != "89504e470d0a1a0a":
            failures.append(f"WebSocket initial frame signature is {data.get('ws_initial_png_signature')}")
        if data.get("ws_pending_keys_after_key") != 1:
            failures.append(f"WebSocket key command left pending_keys={data.get('ws_pending_keys_after_key')}")
        if data.get("ws_key_input_mode") != "hardware":
            failures.append(f"WebSocket key_input_mode is {data.get('ws_key_input_mode')}")
        if data.get("ws_run_done_steps") != 250_000:
            failures.append(f"WebSocket run-start completed {data.get('ws_run_done_steps')} steps")
        if data.get("ws_run_chunk_steps") != 250_000:
            failures.append(f"WebSocket run-start chunk is {data.get('ws_run_chunk_steps')}")
        if data.get("ws_run_elapsed_seconds_type") not in {"int", "float"}:
            failures.append("WebSocket run-start did not expose run_elapsed_seconds")
        if data.get("ws_run_running") is not False:
            failures.append("WebSocket run-start did not report stopped after finite job")
        if not isinstance(data.get("ws_run_insn_count"), int) or data.get("ws_run_insn_count") <= 0:
            failures.append("WebSocket run-start did not advance emulator instruction count")
        if data.get("ws_input_done_steps") != 500_000:
            failures.append(f"WebSocket input auto-run completed {data.get('ws_input_done_steps')} steps")
        if data.get("ws_input_chunk_steps") != 250_000:
            failures.append(f"WebSocket input auto-run chunk is {data.get('ws_input_chunk_steps')}")
        if data.get("ws_input_running") is not False:
            failures.append("WebSocket input auto-run did not report stopped")
        if data.get("ws_input_pending_touches") != 0:
            failures.append(f"WebSocket input auto-run left pending_touches={data.get('ws_input_pending_touches')}")
        if data.get("ws_input_release_done_steps") != 500_000:
            failures.append(f"WebSocket input release auto-run completed {data.get('ws_input_release_done_steps')} steps")
        if data.get("ws_input_release_chunk_steps") != 250_000:
            failures.append(f"WebSocket input release auto-run chunk is {data.get('ws_input_release_chunk_steps')}")
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
state.run_start('cold-menu-smoke', 6_000_000, 250_000)
deadline = time.time() + 45
snap = state.snapshot()
while time.time() < deadline:
    snap = state.snapshot()
    job = snap.get('job') or {{}}
    if job.get('done_steps', 0) >= 6_000_000 and not snap.get('running'):
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
touch_display = (220, 300)
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
        if data.get("job_done_steps") != 6_000_000:
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
    add_key_pulse_parse(rows, c200, args.timeout)
    add_frontend_state_defaults(rows, args.timeout)
    add_frontend_touch_mapping(rows, args.timeout)
    add_frontend_ws_codec(rows, args.timeout)
    add_frontend_http_ws_smoke(rows, args.timeout)
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
