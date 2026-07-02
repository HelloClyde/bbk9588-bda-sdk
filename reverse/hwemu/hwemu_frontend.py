#!/usr/bin/env python3
"""Small local web frontend for the BBK 9588 hardware emulator."""

from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bbk9588_hwemu import (
    Bbk9588HwEmu,
    FirmwareKeySample,
    access_to_dict,
    dump_rgb565_framebuffer,
    find_workspace_file,
)


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
FRAME_PATH = BUILD / "hwemu_frontend_frame.png"
FAT_IMAGE = BUILD / "bbk9588_fs_fat16.img"
COMBINED_NAND_IMAGE = BUILD / "bbk9588_nand_c200_fat_page1c40_gbkshort_usbfix.bin"
FALLBACK_COMBINED_NAND_IMAGE = BUILD / "bbk9588_nand_c200_fat_page1c40.bin"
DEFAULT_READONLY_NAND_RANGE = (0x1C40, 0x28AA7)


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>BBK 9588 HWEMU</title>
  <style>
    :root { color-scheme: dark; font-family: "Segoe UI", sans-serif; background: #15171a; color: #e8eaed; }
    body { margin: 0; min-height: 100vh; display: grid; grid-template-columns: minmax(300px, 420px) 1fr; }
    main { padding: 18px; display: flex; flex-direction: column; gap: 14px; }
    aside { padding: 18px; background: #202327; border-left: 1px solid #343941; overflow: auto; }
    h1 { font-size: 18px; margin: 0 0 8px; font-weight: 650; }
    h2 { font-size: 13px; margin: 0 0 8px; color: #b8c0cc; font-weight: 600; }
    button, input, select { font: inherit; }
    button { background: #2f6fed; color: white; border: 0; border-radius: 6px; padding: 8px 10px; cursor: pointer; }
    button.secondary { background: #343941; }
    button.warn { background: #9b3b3b; }
    button:disabled { opacity: .55; cursor: default; }
    .screen-wrap { display: grid; place-items: center; background: #0b0c0e; border: 1px solid #343941; border-radius: 8px; padding: 12px; }
    #screen { width: min(72vh, 100%); max-width: 360px; aspect-ratio: 3 / 4; image-rendering: pixelated; background: #000; cursor: crosshair; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .panel { border: 1px solid #343941; border-radius: 8px; padding: 12px; background: #1b1e22; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .kv { display: grid; grid-template-columns: 120px 1fr; gap: 5px 10px; font-size: 12px; }
    .keypad button { min-height: 38px; }
    input { width: 90px; color: #e8eaed; background: #111317; border: 1px solid #3b414b; border-radius: 6px; padding: 7px; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.45; color: #c9d1d9; }
    .muted { color: #9aa4b2; font-size: 12px; }
    @media (max-width: 760px) { body { grid-template-columns: 1fr; } aside { border-left: 0; border-top: 1px solid #343941; } }
  </style>
</head>
<body>
  <main>
    <div>
      <h1>BBK 9588 Hardware Emulator</h1>
      <div class="muted">系统镜像常驻运行，屏幕来自模拟 framebuffer。当前输入注入仍是逆向中的近似模型。</div>
    </div>
    <div class="screen-wrap">
      <img id="screen" alt="emulated screen">
    </div>
    <div class="panel">
      <h2>运行</h2>
      <div class="row">
        <button id="boot">后台启动</button>
        <button id="step" class="secondary">运行一片</button>
        <button id="auto" class="secondary">连续运行</button>
        <button id="stop" class="secondary">停止</button>
        <button id="reset" class="warn">重置</button>
      </div>
      <div class="row" style="margin-top:10px">
        <label class="muted">每片指令</label>
        <input id="steps" type="number" min="1000" max="2000000" step="10000" value="250000">
      </div>
    </div>
    <div class="panel keypad">
      <h2>按键</h2>
      <div class="grid">
        <button data-key="10">K10</button>
        <button data-key="5">K5</button>
        <button data-key="7">K7</button>
        <button data-key="6">K6</button>
        <button data-key="9">K9</button>
        <button data-key="4">K4</button>
      </div>
    </div>
  </main>
  <aside>
    <div class="panel">
      <h2>状态</h2>
      <div id="status" class="kv"></div>
    </div>
    <div class="panel" style="margin-top:14px">
      <h2>最近事件</h2>
      <pre id="events"></pre>
    </div>
  </aside>
<script>
const screen = document.getElementById('screen');
const statusEl = document.getElementById('status');
const eventsEl = document.getElementById('events');
const stepsEl = document.getElementById('steps');
let timer = null;
let poller = null;

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}
function refreshImage() {
  screen.src = '/screen.png?t=' + Date.now();
}
function renderStatus(s) {
  const rows = [
    ['running', s.running],
    ['job', s.job?.name || ''],
    ['job steps', s.job ? `${s.job.done_steps}/${s.job.total_steps || '∞'}` : ''],
    ['stop', s.stop_reason || ''],
    ['insn', s.insn_count],
    ['pc', s.pc],
    ['idle', s.idle_loop_hits],
    ['app idle', s.app_idle_loop_hits],
    ['wait', s.scheduler?.wait_wake_count ?? ''],
    ['tick', s.scheduler?.timer_tick_count ?? ''],
    ['dispatch', s.scheduler?.scheduler_dispatch_count ?? ''],
    ['enabled', s.scheduler?.fields?.run_enabled_3f09 ?? ''],
    ['countdown', s.scheduler?.fields?.timer_countdown_3f08 ?? ''],
    ['pixels', s.framebuffer?.nonzero_pixels ?? ''],
    ['bbox', JSON.stringify(s.framebuffer?.nonzero_bbox ?? null)]
  ];
  statusEl.innerHTML = rows.map(([k,v]) => `<div>${k}</div><div>${v}</div>`).join('');
  eventsEl.textContent = JSON.stringify((s.events || []).slice(-12), null, 2);
  refreshImage();
}
async function refresh() { renderStatus(await api('/api/status')); }
function startPolling() {
  if (poller) return;
  poller = setInterval(() => refresh().catch(console.error), 1000);
}
function stopPolling() {
  if (poller) { clearInterval(poller); poller = null; }
}
async function step() {
  const n = Number(stepsEl.value || 250000);
  renderStatus(await api('/api/step?steps=' + encodeURIComponent(n), {method:'POST'}));
}
document.getElementById('boot').onclick = async () => {
  renderStatus(await api('/api/run-start?name=boot&steps=30000000&chunk=100000', {method:'POST'}));
  startPolling();
};
document.getElementById('step').onclick = step;
document.getElementById('reset').onclick = async () => {
  if (timer) { clearInterval(timer); timer = null; document.getElementById('auto').textContent = '连续运行'; }
  stopPolling();
  renderStatus(await api('/api/reset', {method:'POST'}));
};
document.getElementById('auto').onclick = () => {
  const btn = document.getElementById('auto');
  if (timer) {
    clearInterval(timer); timer = null; btn.textContent = '连续运行';
    api('/api/stop', {method:'POST'}).then(renderStatus).catch(console.error);
    return;
  }
  btn.textContent = '停止连续';
  api('/api/run-start?name=continuous&steps=0&chunk=100000', {method:'POST'}).then(renderStatus).catch(console.error);
  timer = setInterval(() => refresh().catch(console.error), 1000);
};
document.getElementById('stop').onclick = async () => {
  if (timer) { clearInterval(timer); timer = null; document.getElementById('auto').textContent = '连续运行'; }
  stopPolling();
  renderStatus(await api('/api/stop', {method:'POST'}));
};
document.querySelectorAll('[data-key]').forEach(btn => {
  btn.onclick = async () => renderStatus(await api('/api/key?code=' + btn.dataset.key, {method:'POST'}));
});
screen.addEventListener('pointerdown', async ev => {
  const r = screen.getBoundingClientRect();
  const x = Math.max(0, Math.min(239, Math.floor((ev.clientX - r.left) * 240 / r.width)));
  const y = Math.max(0, Math.min(319, Math.floor((ev.clientY - r.top) * 320 / r.height)));
  renderStatus(await api(`/api/touch?x=${x}&y=${y}&down=1`, {method:'POST'}));
});
screen.addEventListener('pointerup', async ev => {
  const r = screen.getBoundingClientRect();
  const x = Math.max(0, Math.min(239, Math.floor((ev.clientX - r.left) * 240 / r.width)));
  const y = Math.max(0, Math.min(319, Math.floor((ev.clientY - r.top) * 320 / r.height)));
  renderStatus(await api(`/api/touch?x=${x}&y=${y}&down=0`, {method:'POST'}));
});
refresh().then(s => { if (s?.running) startPolling(); }).catch(console.error);
</script>
</body>
</html>
"""


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
        self.cancel_run = threading.Event()
        self.worker: threading.Thread | None = None
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
        with self.lock:
            BUILD.mkdir(parents=True, exist_ok=True)
            image = find_workspace_file("u_boot_9588_4740.bin")
            payload = find_workspace_file("C200.bin")
            default_nand = (
                COMBINED_NAND_IMAGE
                if COMBINED_NAND_IMAGE.exists()
                else FALLBACK_COMBINED_NAND_IMAGE
                if FALLBACK_COMBINED_NAND_IMAGE.exists()
                else payload
            )
            nand_image = self.args.nand_image or default_nand
            block_image = self._ensure_fat_image() if self.args.block_image else None
            self.emu = Bbk9588HwEmu(
                image=image,
                base=0x80900000,
                pc=0x80900000,
                ram_size=self.args.ram_mb * 1024 * 1024,
                trace_limit=self.args.trace_limit,
                recover_jr=True,
                profile="bbk9588-uboot",
                payload=payload,
                payload_addr=0x80004000,
                idle_stop_hits=0,
                app_idle_stop_hits=0,
                nand_image=nand_image,
                block_image=block_image,
                readonly_nand_page_ranges=[DEFAULT_READONLY_NAND_RANGE],
                bda_text_mode="native",
                bda_native_glyph_layout="rows-lsb-vscale2",
                bda_native_raster_mode="firmware",
                scheduler_tick_clamp=self.args.scheduler_tick_clamp,
                nand_loop_accelerator=self.args.nand_loop_accelerator,
            )
            if self.args.state_in is not None:
                self.emu.load_emulator_state(self.args.state_in)
            self.last_error = None
            self.last_frame = None
            self.running = False
            self.job_name = None
            self.job_total_steps = 0
            self.job_done_steps = 0
            self.cancel_run.set()
            return self.snapshot()

    def _step_locked(self, steps: int) -> None:
        assert self.emu is not None
        self.running = True
        self.emu.state.stop_reason = None
        try:
            self.emu.run(max(1, steps))
            self.last_error = None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.emu.state.stop_reason = self.last_error
            self.cancel_run.set()

    def step(self, steps: int) -> dict[str, object]:
        with self.lock:
            if self.emu is None:
                self.reset()
            self._step_locked(steps)
            self.running = self._worker_alive()
            return self.snapshot()

    def boot(self) -> dict[str, object]:
        return self.step(self.args.boot_steps)

    def _worker_alive(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def run_start(self, name: str, total_steps: int, chunk_steps: int) -> dict[str, object]:
        with self.lock:
            if self._worker_alive():
                return self.snapshot()
            self.cancel_run.clear()
            self.job_name = name or "run"
            self.job_total_steps = max(0, total_steps)
            self.job_done_steps = 0
            chunk = max(1, chunk_steps)

        def worker() -> None:
            try:
                while not self.cancel_run.is_set():
                    with self.lock:
                        if self.emu is None:
                            break
                        remaining = self.job_total_steps - self.job_done_steps if self.job_total_steps else chunk
                        if self.job_total_steps and remaining <= 0:
                            break
                        run_now = min(chunk, remaining) if self.job_total_steps else chunk
                        self._step_locked(run_now)
                        self.job_done_steps += run_now
                    time.sleep(0.001)
            finally:
                with self.lock:
                    self.running = False

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
            return self.snapshot()

    def key(self, code: int) -> dict[str, object]:
        with self.lock:
            assert self.emu is not None
            hit = self.emu.idle_loop_hits + 1
            self.emu.firmware_key_samples.append(FirmwareKeySample(code=code & 0xFF, idle_hit=hit))
        return self.step(self.args.input_steps)

    def touch(self, x: int, y: int, down: bool) -> dict[str, object]:
        with self.lock:
            assert self.emu is not None
            self.emu.set_touch_controller_state(
                max(0, min(239, x)),
                max(0, min(319, y)),
                down,
            )
        return self.step(self.args.input_steps)

    def dump_frame(self) -> bytes:
        with self.lock:
            assert self.emu is not None
            self.last_frame = dump_rgb565_framebuffer(
                self.emu,
                FRAME_PATH,
                0xA1F82000,
                0,
                240,
                320,
                240,
                "rgb565",
                self.args.orientation,
            )
            return FRAME_PATH.read_bytes()

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            assert self.emu is not None
            state = self.emu.state
            worker_alive = self._worker_alive()
            self.running = self.running and worker_alive
            job = None
            if self.job_name is not None:
                job = {
                    "name": self.job_name,
                    "total_steps": self.job_total_steps,
                    "done_steps": self.job_done_steps,
                    "active": worker_alive,
                }
            return {
                "running": worker_alive,
                "job": job,
                "stop_reason": self.last_error or state.stop_reason,
                "insn_count": state.insn_count,
                "pc": f"0x{self.emu.pc:08x}",
                "last_pc": f"0x{state.last_pc:08x}",
                "idle_loop_hits": self.emu.idle_loop_hits,
                "app_idle_loop_hits": self.emu.app_idle_loop_hits,
                "events": state.events[-64:],
                "invalid": [access_to_dict(a) for a in state.invalid[-8:]],
                "scheduler": self.emu.scheduler_snapshot(),
                "framebuffer": self.last_frame,
            }


class Handler(BaseHTTPRequestHandler):
    state: FrontendState

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data: object, status: int = 200) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif parsed.path == "/api/status":
                self._json(self.state.snapshot())
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
            elif parsed.path == "/api/boot":
                self._json(self.state.boot())
            elif parsed.path == "/api/run-start":
                name = qs.get("name", ["run"])[0]
                steps = int(qs.get("steps", ["0"])[0])
                chunk = int(qs.get("chunk", ["100000"])[0])
                self._json(self.state.run_start(name, steps, chunk))
            elif parsed.path == "/api/stop":
                self._json(self.state.stop())
            elif parsed.path == "/api/step":
                steps = int(qs.get("steps", ["250000"])[0])
                self._json(self.state.step(steps))
            elif parsed.path == "/api/key":
                self._json(self.state.key(int(qs.get("code", ["0"])[0])))
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Serve a local BBK 9588 emulator frontend.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9588)
    ap.add_argument("--ram-mb", type=int, default=160)
    ap.add_argument("--trace-limit", type=int, default=5000)
    ap.add_argument("--boot-steps", type=int, default=30_000_000)
    ap.add_argument("--input-steps", type=int, default=500_000)
    ap.add_argument("--state-in", type=Path, help="Load an emulator checkpoint when the frontend resets.")
    ap.add_argument("--nand-image", type=Path, help="Raw NAND image backing the frontend emulator.")
    ap.add_argument("--nand-loop-accelerator", action="store_true", help="Enable diagnostic NAND loop acceleration.")
    ap.add_argument("--block-image", action="store_true", help="Enable the legacy temporary logical block-device hook.")
    ap.add_argument("--scheduler-tick-clamp", action="store_true", help="Enable the old diagnostic scheduler tick clamp.")
    ap.add_argument("--orientation", choices=["raw", "rot180", "cw90", "ccw90", "hflip", "vflip"], default="rot180")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    state = FrontendState(args)
    Handler.state = state
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"BBK9588 HWEMU frontend: http://{args.host}:{args.port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
