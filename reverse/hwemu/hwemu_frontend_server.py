"""HTTP/WebSocket request handler for the BBK 9588 frontend."""

from __future__ import annotations

import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from hwemu_frontend_ws import encode_ws_frame, recv_ws_text, websocket_accept_key


class FrontendHandler(BaseHTTPRequestHandler):
    state: object
    html: str = ""

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: object, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _ws_send_frame(self, opcode: int, payload: bytes) -> None:
        self.connection.sendall(encode_ws_frame(opcode, payload))

    def _ws_send_json(self, data: object) -> None:
        self._ws_send_frame(0x1, json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _ws_send_frame_png(self, allow_cached: bool = True, allow_dump: bool = True) -> bool:
        frame = self.state.pop_queued_frame()
        if frame is None and allow_cached:
            frame = self.state.cached_frame()
        if frame is None and allow_dump:
            frame = self.state.dump_frame()
        if frame is None:
            return False
        self._ws_send_frame(0x2, frame)
        return True

    def _ws_send_queued_frame_png(self) -> bool:
        frame = self.state.pop_queued_frame()
        if frame is None:
            return False
        self._ws_send_frame(0x2, frame)
        return True

    def _handle_ws(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self._send(400, b"missing websocket key", "text/plain")
            return
        accept = websocket_accept_key(key)
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.connection.settimeout(0.25)
        last_push = 0.0
        self._ws_send_json(self.state.snapshot())
        self._ws_send_frame_png(allow_cached=True, allow_dump=not self.state.worker_active())
        while True:
            now = time.time()
            if self._ws_send_queued_frame_png():
                self._ws_send_json(self.state.snapshot())
                last_push = now
            elif now - last_push >= 0.5:
                self._ws_send_json(self.state.snapshot())
                last_push = now
            try:
                text = recv_ws_text(self.connection)
            except TimeoutError:
                continue
            except OSError:
                break
            if text is None:
                break
            if not text:
                continue
            try:
                msg = json.loads(text)
                if isinstance(msg, dict):
                    self._ws_send_json(self.state.command(msg))
                    active = self.state.worker_active()
                    self._ws_send_frame_png(allow_cached=not active, allow_dump=not active)
            except Exception as exc:
                self._ws_send_json({"error": f"{type(exc).__name__}: {exc}"})

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(200, self.html.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/ws":
                self._handle_ws()
            elif parsed.path == "/api/status":
                self._json(self.state.snapshot())
            elif parsed.path == "/api/logs":
                limit = int(parse_qs(parsed.query).get("limit", ["512"])[0])
                self._json(self.state.logs(limit))
            elif parsed.path == "/screen.png":
                self._send(200, self.state.dump_frame(), "image/png")
            else:
                ctype = mimetypes.guess_type(parsed.path)[0] or "text/plain"
                self._send(404, b"not found", ctype)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if parsed.path == "/api/reset":
                self._json(self.state.reset())
            elif parsed.path == "/api/command":
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length else b"{}"
                msg = json.loads(raw.decode("utf-8") or "{}")
                if not isinstance(msg, dict):
                    raise ValueError("command body must be a JSON object")
                self._json(self.state.command(msg))
            elif parsed.path == "/api/boot":
                self._json(self.state.boot())
            elif parsed.path == "/api/run-start":
                name = qs.get("name", ["run"])[0]
                steps = int(qs.get("steps", ["0"])[0])
                chunk = int(qs.get("chunk", ["100000"])[0])
                self._json(self.state.run_start(name, steps, chunk))
            elif parsed.path == "/api/stop":
                self._json(self.state.stop())
            elif parsed.path == "/api/logs/clear":
                self._json(self.state.clear_logs())
            elif parsed.path == "/api/step":
                steps = int(qs.get("steps", ["250000"])[0])
                self._json(self.state.step(steps))
            elif parsed.path == "/api/key":
                down = qs.get("down", ["1"])[0] not in {"0", "false", "False"}
                self._json(self.state.key(int(qs.get("code", ["0"])[0]), down))
            elif parsed.path == "/api/touch":
                x = int(qs.get("x", ["0"])[0])
                y = int(qs.get("y", ["0"])[0])
                down = qs.get("down", ["1"])[0] not in {"0", "false", "False"}
                self._json(self.state.touch(x, y, down))
            else:
                self._send(404, b"not found", "text/plain")
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def log_message(self, fmt: str, *args: object) -> None:
        if not getattr(self.state.args, "quiet", False):
            super().log_message(fmt, *args)
