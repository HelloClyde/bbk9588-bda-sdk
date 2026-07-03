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
from typing import Callable

from hwemu_frontend_ws import encode_ws_frame, read_ws_frame


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
DEFAULT_NAND = BUILD / "bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin"


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
        self.last_status: dict[str, object] = {}
        self.last_frame: bytes | None = None
        self.frames = 0

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass

    def send_json(self, msg: dict[str, object]) -> None:
        payload = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        self.sock.sendall(encode_ws_frame(0x1, payload, mask=os.urandom(4)))

    def recv_one(self) -> tuple[str, object] | None:
        try:
            frame = read_ws_frame(self.sock)
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
            self.last_frame = payload
            self.frames += 1
            return "frame", payload
        if opcode == 0x8:
            return "close", payload
        return "other", payload

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


def start_frontend(args: argparse.Namespace, port: int) -> subprocess.Popen[bytes]:
    cmd = [
        sys.executable,
        str(ROOT / "reverse" / "hwemu" / "hwemu_frontend.py"),
        "--host",
        args.host,
        "--port",
        str(port),
        "--nand-image",
        str(args.nand_image),
        "--worker-slice-seconds",
        str(args.worker_slice_seconds),
        "--quiet",
    ]
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
    return {
        "running": status.get("running"),
        "pc": status.get("pc"),
        "auto_calibration_stage": status.get("auto_calibration_stage"),
        "auto_calibration_stage_label": status.get("auto_calibration_stage_label"),
        "pending_touches": status.get("pending_touches"),
        "pending_keys": status.get("pending_keys"),
        "nonzero_pixels": fb.get("nonzero_pixels"),
        "unique_pixel_values": fb.get("unique_pixel_values"),
        "job": {
            "name": job.get("name"),
            "status": job.get("status"),
            "done_steps": job.get("done_steps"),
            "steps_per_second": job.get("steps_per_second"),
        },
    }


def looks_like_menu(status: dict[str, object]) -> bool:
    fb = status.get("framebuffer") if isinstance(status.get("framebuffer"), dict) else {}
    return (
        int(status.get("auto_calibration_stage") or 0) >= 12
        and int(fb.get("nonzero_pixels") or 0) >= 25000
        and int(fb.get("unique_pixel_values") or 0) >= 500
        and status.get("pc") == "0x80008a84"
    )


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


def tap(ws: WebSocketClient, x: int, y: int) -> None:
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
    ws.send_json(down)
    ws.pump(0.8)
    up = dict(base)
    up["down"] = False
    up["phase"] = "up"
    ws.send_json(up)
    ws.pump(2.0)


def key_press(ws: WebSocketClient, code: int) -> None:
    ws.send_json({"op": "key", "code": code, "down": True, "advance": False, "run": True})
    ws.pump(0.5)
    ws.send_json({"op": "key", "code": code, "down": False, "advance": False, "run": True})
    ws.pump(1.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a user-like web frontend smoke test over HTTP and WebSocket.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="Use 0 to start a private frontend on a free port.")
    ap.add_argument("--use-existing", action="store_true", help="Connect to an already running frontend instead of starting one.")
    ap.add_argument("--nand-image", type=Path, default=DEFAULT_NAND)
    ap.add_argument("--out-dir", type=Path, default=BUILD)
    ap.add_argument("--prefix", default="hwemu_frontend_web_smoke")
    ap.add_argument("--boot-timeout", type=int, default=480)
    ap.add_argument("--chunk-steps", type=int, default=250000)
    ap.add_argument("--worker-slice-seconds", type=float, default=0.25)
    ns = ap.parse_args(argv)

    ns.out_dir.mkdir(parents=True, exist_ok=True)
    port = ns.port or find_free_port(ns.host)
    proc: subprocess.Popen[bytes] | None = None
    ws: WebSocketClient | None = None
    failures: list[str] = []
    interactions: list[dict[str, object]] = []
    screenshots: dict[str, dict[str, object]] = {}
    logs: dict[str, object] = {}
    start = time.time()
    try:
        if not ns.use_existing:
            proc = start_frontend(ns, port)
        wait_http(ns.host, port, 30)
        html_status, html = http_bytes(ns.host, port, "/")
        if html_status != 200 or b"<canvas" not in html:
            failures.append("frontend HTML did not load or canvas was missing")

        ws = WebSocketClient(ns.host, port)
        ws.pump(1.0)
        interactions.append({"step": "connect", "status": summarize_status(ws.last_status), "frames": ws.frames})

        ws.send_json({"op": "reset"})
        ws.pump(1.0)
        interactions.append({"step": "reset", "status": summarize_status(ws.last_status)})

        ws.send_json({"op": "auto-calibration", "enabled": True})
        ws.pump(0.5)
        interactions.append({"step": "enable-auto-calibration", "status": summarize_status(ws.last_status)})

        ws.send_json({"op": "run-start", "name": "web-human-smoke", "steps": 0, "chunk": ns.chunk_steps})
        menu_status = ws.wait_for(
            looks_like_menu,
            ns.boot_timeout,
            poll_status=lambda: http_json(ns.host, port, "GET", "/api/status"),
        )
        interactions.append({"step": "wait-menu", "status": summarize_status(menu_status), "frames": ws.frames})
        boot_ok = looks_like_menu(menu_status)
        if not boot_ok:
            failures.append("cold boot did not reach a menu-looking framebuffer through the web worker")
            ws.send_json({"op": "stop"})
            ws.pump(1.0)
            stopped = http_json(ns.host, port, "GET", "/api/status")
            interactions.append({"step": "stop-after-boot-failure", "status": summarize_status(stopped)})
            logs = http_json(ns.host, port, "GET", "/api/logs?limit=80")
        else:
            status_code, menu_png, menu_digest = fetch_screen_digest(ns.host, port)
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
            for name, x, y in category_points:
                tap(ws, x, y)
                ws.wait_for(
                    lambda s: int(s.get("pending_touches") or 0) == 0,
                    15,
                    poll_status=lambda: http_json(ns.host, port, "GET", "/api/status"),
                )
                status_code, png, digest = wait_screen_digest(
                    ns.host,
                    port,
                    lambda value: bool(value and value != menu_digest),
                    12,
                )
                changed = bool(digest and digest != menu_digest)
                changed_categories += 1 if changed else 0
                out_path = ns.out_dir / f"{ns.prefix}_tap_{name}.png"
                if status_code == 200:
                    out_path.write_bytes(png)
                    screenshots[f"tap_{name}"] = {"path": str(out_path), "sha256": digest}
                interactions.append(
                    {
                        "step": f"tap-{name}",
                        "display": [x, y],
                        "changed_from_menu": changed,
                        "png": str(out_path) if status_code == 200 else None,
                        "sha256": digest,
                        "status": summarize_status(http_json(ns.host, port, "GET", "/api/status")),
                    }
                )
                if not changed:
                    failures.append(f"category {name} did not change the framebuffer from the main menu")
                    continue
                returned_home = False
                home_digest = ""
                for index, (home_x, home_y) in enumerate(home_points, 1):
                    tap(ws, home_x, home_y)
                    _home_status, _home_png, home_digest = wait_screen_digest(
                        ns.host,
                        port,
                        lambda value: bool(value and value == menu_digest),
                        10,
                    )
                    interactions.append(
                        {
                            "step": f"home-after-{name}-{index}",
                            "display": [home_x, home_y],
                            "returned_to_menu": home_digest == menu_digest,
                            "sha256": home_digest,
                            "status": summarize_status(http_json(ns.host, port, "GET", "/api/status")),
                        }
                    )
                    if home_digest == menu_digest:
                        returned_home = True
                        break
                if not returned_home:
                    failures.append(f"category {name} did not return to the main menu through the home button")
                    break
            if changed_categories == 0:
                failures.append("bottom category taps did not change the framebuffer")

            for code, name in [(4, "up"), (5, "down"), (6, "left"), (7, "right"), (9, "cancel"), (10, "ok")]:
                key_press(ws, code)
                status = http_json(ns.host, port, "GET", "/api/status")
                interactions.append({"step": f"key-{name}", "code": code, "status": summarize_status(status)})
                if int(status.get("pending_keys") or 0) != 0:
                    failures.append(f"key {name} left pending_keys={status.get('pending_keys')}")

            ws.send_json({"op": "stop"})
            ws.pump(1.0)
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
        "failures": failures,
        "screenshots": screenshots,
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
        f"- Frames received over WS: {ws.frames if ws is not None else 0}",
        f"- Failures: {len(failures)}",
        "",
        "## Interactions",
    ]
    for item in interactions:
        lines.append(f"- {item['step']}: `{json.dumps(item.get('status', {}), ensure_ascii=False)}`")
    if failures:
        lines += ["", "## Failures"]
        lines += [f"- {failure}" for failure in failures]
    lines += [
        "",
        "## Notes",
        "- This smoke drives the frontend through HTTP and WebSocket, not direct Python state calls.",
        "- Touches use rendered display coordinates and rely on the frontend orientation mapping.",
        "- Category coverage is framebuffer-change based; it does not yet OCR labels or assert exact selected menu names.",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"ok": summary["ok"], "summary": str(json_path), "report": str(report_path), "failures": failures}, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
