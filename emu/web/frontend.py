#!/usr/bin/env python3
"""Small local web frontend for the BBK 9588 hardware emulator."""

from __future__ import annotations

import argparse
import cProfile
import pstats
from http.server import ThreadingHTTPServer
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from emu.web.frontend_server import FrontendHandler as Handler
from emu.web.frontend_state import (
    FrontendState,
    display_to_panel_point,
    display_to_raw_point,
    display_to_touch_point,
    raw_to_display_point,
)


def parse_page_range(value: str) -> tuple[int, int]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("expected start:end")
    start_text, end_text = value.split(":", 1)
    try:
        start = int(start_text, 0)
        end = int(end_text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if start < 0 or end <= start:
        raise argparse.ArgumentTypeError("range must satisfy 0 <= start < end")
    return start, end


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
    #screen { display: block; width: min(72vh, 100%); max-width: 360px; aspect-ratio: 3 / 4; image-rendering: pixelated; background: #000; cursor: crosshair; touch-action: none; user-select: none; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .panel { border: 1px solid #343941; border-radius: 8px; padding: 12px; background: #1b1e22; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .kv { display: grid; grid-template-columns: 120px 1fr; gap: 5px 10px; font-size: 12px; }
    .keypad button { min-height: 42px; }
    .keypad button.blank { visibility: hidden; pointer-events: none; }
    .keypad button.active { background: #5794ff; }
    input { width: 90px; color: #e8eaed; background: #111317; border: 1px solid #3b414b; border-radius: 6px; padding: 7px; }
    input[type="checkbox"] { width: auto; accent-color: #5794ff; }
    .check { display: inline-flex; gap: 6px; align-items: center; color: #c9d1d9; font-size: 12px; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.45; color: #c9d1d9; }
    .muted { color: #9aa4b2; font-size: 12px; }
    @media (max-width: 760px) { body { grid-template-columns: 1fr; } aside { border-left: 0; border-top: 1px solid #343941; } }
  </style>
</head>
<body>
  <main>
    <div>
      <h1>BBK 9588 硬件仿真器</h1>
      <div class="muted">真实 C200.bin 硬件级冷启动；画面来自模拟 framebuffer，触摸和按键通过前端事件队列送入。</div>
    </div>
    <div class="screen-wrap">
      <canvas id="screen" width="240" height="320"></canvas>
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
        <label class="check"><input id="autoBoot" type="checkbox">自动冷启动输入</label>
      </div>
    </div>
    <div class="panel keypad">
      <h2>按键</h2>
      <div class="grid">
        <button data-key="9" data-name="cancel" aria-label="取消">取消</button>
        <button data-key="4" data-name="up" aria-label="上">上</button>
        <button data-key="10" data-name="ok" aria-label="确认">确认</button>
        <button data-key="6" data-name="left" aria-label="左">左</button>
        <button data-key="5" data-name="down" aria-label="下">下</button>
        <button data-key="7" data-name="right" aria-label="右">右</button>
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
const screenCtx = screen.getContext('2d', { alpha: false });
screenCtx.imageSmoothingEnabled = false;
const statusEl = document.getElementById('status');
const eventsEl = document.getElementById('events');
const stepsEl = document.getElementById('steps');
const autoBootEl = document.getElementById('autoBoot');
let timer = null;
let poller = null;
let ws = null;
let wsOpenPromise = null;
let continuousActive = false;
let pointerActive = false;
let activePointerId = null;
let currentOrientation = 'rot180';
let rgb565Lut = null;
let rawImageData = null;

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}
function wsSend(msg) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return fetch('/api/command', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(msg)
    }).then(r => r.json()).then(renderStatus);
  }
  ws.send(JSON.stringify(msg));
}
function screenPointFromClient(clientX, clientY, clamp = false) {
  const r = screen.getBoundingClientRect();
  if (!clamp && (clientX < r.left || clientX >= r.right || clientY < r.top || clientY >= r.bottom)) return null;
  const displayWidth = screen.width || 240;
  const displayHeight = screen.height || 320;
  let x = Math.floor((clientX - r.left) * displayWidth / r.width);
  let y = Math.floor((clientY - r.top) * displayHeight / r.height);
  if (!clamp && (x < 0 || x >= displayWidth || y < 0 || y >= displayHeight)) return null;
  x = Math.max(0, Math.min(displayWidth - 1, x));
  y = Math.max(0, Math.min(displayHeight - 1, y));
  return {x, y, width: displayWidth, height: displayHeight};
}
function sendTouchAt(clientX, clientY, down, phase, source = 'pointer', clamp = false) {
  const p = screenPointFromClient(clientX, clientY, clamp);
  if (!p) return false;
  wsSend({
    op:'touch',
    display_x:p.x,
    display_y:p.y,
    display_width:p.width,
    display_height:p.height,
    down,
    phase,
    source,
    advance:false,
    run:true
  });
  return true;
}
function formatElapsed(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return '';
  const total = Math.max(0, Math.floor(Number(seconds)));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m ${String(s).padStart(2, '0')}s`;
  if (m) return `${m}m ${String(s).padStart(2, '0')}s`;
  return `${s}s`;
}
function formatJobSteps(job) {
  if (!job) return '';
  const total = job.total_steps || 'inf';
  return `${job.observed_insn_delta ?? 0}/${job.requested_done_steps ?? job.done_steps}/${total}`;
}
function renderStatus(s) {
  currentOrientation = s.orientation || currentOrientation;
  autoBootEl.checked = Boolean(s.auto_calibration);
  const rows = [
    ['running', s.running],
    ['since reset', formatElapsed(s.reset_elapsed_seconds ?? s.emulator_elapsed_seconds)],
    ['run elapsed', formatElapsed(s.run_elapsed_seconds)],
    ['boot', s.boot_mode || ''],
    ['orientation', s.orientation || ''],
    ['key mode', s.key_input_mode || ''],
    ['fast hooks', s.fast_hooks],
    ['step timer', `${s.completed_step_timer ? 'completed' : 'hook'}${s.completed_step_timer_after_auto_boot ? ':auto' : ''}`],
    ['res cache', s.resource_cache16],
    ['auto boot', `${s.auto_calibration ? 'on' : 'off'}:${s.auto_calibration_stage_label || s.auto_calibration_stage || 0}`],
    ['touch queue', s.pending_touches ?? 0],
    ['key queue', s.pending_keys ?? 0],
    ['input wake', s.input_wake_count ?? 0],
    ['busy delay', s.busy_delay_accel ?? 0],
    ['busy patch', s.busy_delay_static_patch ? 'on' : 'off'],
    ['ftl scan', s.ftl_scan_accel ?? 0],
    ['cache scan', s.cache_scan_tail_accel ?? 0],
    ['hot logs', s.suppressed_hot_events ?? 0],
    ['poll accel', s.no_event_poll_accel ?? 0],
    ['frame hook', s.frame_push?.hook_count ?? 0],
    ['frame queued', `${s.frame_push?.queued_count ?? 0}/${s.queued_frames ?? 0}`],
    ['frame throttle', s.frame_push?.throttle_count ?? 0],
    ['frame replace', s.frame_push?.replace_count ?? 0],
    ['frame drop', s.frame_push?.drop_count ?? 0],
    ['job', s.job?.name || ''],
    ['job mode', s.job?.mode || ''],
    ['job status', s.job?.status || ''],
    ['job elapsed', s.job ? formatElapsed(s.job.elapsed_seconds) : ''],
    ['job speed', s.job?.steps_per_second ? `${Math.round(s.job.steps_per_second)}/s` : ''],
    ['req speed', s.job?.requested_steps_per_second ? `${Math.round(s.job.requested_steps_per_second)}/s` : ''],
    ['job chunk', s.job?.chunk_steps || ''],
    ['run slice', s.run_internal_chunk_steps || ''],
    ['last slice', s.job ? `${s.job.last_slice_steps || 0}${s.job.last_slice_timed_out ? ' timeout' : ''}` : ''],
    ['job steps', formatJobSteps(s.job)],
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
}
async function refresh() { renderStatus(await api('/api/status')); }
function ensureScreenSize(width, height) {
  if (screen.width !== width || screen.height !== height) {
    screen.width = width;
    screen.height = height;
    screenCtx.imageSmoothingEnabled = false;
    rawImageData = null;
  }
}
function reusableImageData(width, height) {
  if (!rawImageData || rawImageData.width !== width || rawImageData.height !== height) {
    rawImageData = screenCtx.createImageData(width, height);
  }
  return rawImageData;
}
function outputSizeForRaw(width, height, orientation) {
  if (orientation === 'cw90' || orientation === 'ccw90') return [height, width];
  return [width, height];
}
function ensureRgb565Lut() {
  if (rgb565Lut) return rgb565Lut;
  const r = new Uint8Array(65536);
  const g = new Uint8Array(65536);
  const b = new Uint8Array(65536);
  for (let px = 0; px < 65536; px++) {
    r[px] = Math.round(((px >> 11) & 0x1f) * 255 / 31);
    g[px] = Math.round(((px >> 5) & 0x3f) * 255 / 63);
    b[px] = Math.round((px & 0x1f) * 255 / 31);
  }
  rgb565Lut = {r, g, b};
  return rgb565Lut;
}
function drawRawRgb565Frame(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < 20) return false;
  const bytes = new Uint8Array(buffer);
  const magic = [0x42, 0x42, 0x4b, 0x52, 0x41, 0x57, 0x31, 0x00];
  for (let i = 0; i < magic.length; i++) {
    if (bytes[i] !== magic[i]) return false;
  }
  const view = new DataView(buffer);
  const width = view.getUint16(12, true);
  const height = view.getUint16(14, true);
  const stride = view.getUint16(16, true);
  const format = view.getUint16(18, true);
  if (format !== 1 || width <= 0 || height <= 0 || stride < width) return false;
  const raw = new Uint8Array(buffer, 20);
  if (raw.length < stride * height * 2) return false;
  const [outW, outH] = outputSizeForRaw(width, height, currentOrientation);
  ensureScreenSize(outW, outH);
  const image = reusableImageData(outW, outH);
  const out = image.data;
  const lut = ensureRgb565Lut();
  let outIndex = 0;
  if (currentOrientation === 'rot180') {
    for (let y = 0; y < height; y++) {
      let i = ((height - 1 - y) * stride + (width - 1)) * 2;
      for (let x = 0; x < width; x++, i -= 2) {
        const px = raw[i] | (raw[i + 1] << 8);
        out[outIndex++] = lut.r[px];
        out[outIndex++] = lut.g[px];
        out[outIndex++] = lut.b[px];
        out[outIndex++] = 255;
      }
    }
  } else if (!currentOrientation || currentOrientation === 'none') {
    for (let y = 0; y < height; y++) {
      let i = y * stride * 2;
      for (let x = 0; x < width; x++, i += 2) {
        const px = raw[i] | (raw[i + 1] << 8);
        out[outIndex++] = lut.r[px];
        out[outIndex++] = lut.g[px];
        out[outIndex++] = lut.b[px];
        out[outIndex++] = 255;
      }
    }
  } else {
    for (let y = 0; y < outH; y++) {
      for (let x = 0; x < outW; x++) {
        let sx = x;
        let sy = y;
        if (currentOrientation === 'hflip') {
          sx = width - 1 - x;
        } else if (currentOrientation === 'vflip') {
          sy = height - 1 - y;
        } else if (currentOrientation === 'cw90') {
          sx = y;
          sy = height - 1 - x;
        } else if (currentOrientation === 'ccw90') {
          sx = width - 1 - y;
          sy = x;
        }
        const i = (sy * stride + sx) * 2;
        const px = raw[i] | (raw[i + 1] << 8);
        out[outIndex++] = lut.r[px];
        out[outIndex++] = lut.g[px];
        out[outIndex++] = lut.b[px];
        out[outIndex++] = 255;
      }
    }
  }
  screenCtx.putImageData(image, 0, 0);
  return true;
}
async function drawPngFrame(data) {
  const blob = data instanceof Blob ? data : new Blob([data], {type:'image/png'});
  const bitmap = await createImageBitmap(blob);
  ensureScreenSize(bitmap.width, bitmap.height);
  screenCtx.drawImage(bitmap, 0, 0);
  bitmap.close?.();
}
function connectWs() {
  if (ws && ws.readyState === WebSocket.OPEN) return Promise.resolve(ws);
  if (ws && ws.readyState === WebSocket.CONNECTING) return wsOpenPromise || Promise.resolve(ws);
  ws = new WebSocket(`ws://${location.host}/ws`);
  wsOpenPromise = new Promise((resolve, reject) => {
    ws.addEventListener('open', () => resolve(ws), {once:true});
    ws.addEventListener('error', () => reject(new Error('websocket failed')), {once:true});
  });
  ws.binaryType = 'arraybuffer';
  ws.onopen = () => stopPolling();
  ws.onmessage = async ev => {
    if (ev.data instanceof ArrayBuffer) {
      if (!drawRawRgb565Frame(ev.data)) await drawPngFrame(ev.data);
      return;
    }
    if (ev.data instanceof Blob) {
      await drawPngFrame(ev.data);
      return;
    }
    try { renderStatus(JSON.parse(ev.data)); } catch (err) { console.error(err); }
  };
  ws.onclose = () => {
    ws = null;
    wsOpenPromise = null;
    if (!poller) poller = setInterval(() => refresh().catch(console.error), 1000);
    setTimeout(connectWs, 1500);
  };
  ws.onerror = () => ws?.close();
  return wsOpenPromise;
}
function stopPolling() {
  if (poller) { clearInterval(poller); poller = null; }
}
function setContinuousActive(active) {
  continuousActive = active;
  document.getElementById('auto').textContent = active ? '停止连续' : '连续运行';
}
async function step() {
  const n = Number(stepsEl.value || 250000);
  wsSend({op:'step', steps:n});
}
function requestStop() {
  wsSend({op:'stop'});
  setTimeout(async () => {
    try {
      const status = await api('/api/status');
      if (!status.running) {
        renderStatus(status);
        return;
      }
      renderStatus(await api('/api/command', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({op:'stop'})
      }));
    } catch (err) {
      console.error(err);
    }
  }, 1200);
}
document.getElementById('boot').onclick = async () => {
  const n = Number(stepsEl.value || 250000);
  setContinuousActive(true);
  await connectWs();
  wsSend({op:'run-start', name:'boot', steps:0, chunk:n});
};
document.getElementById('step').onclick = step;
document.getElementById('reset').onclick = async () => {
  if (timer) { clearInterval(timer); timer = null; }
  setContinuousActive(false);
  stopPolling();
  wsSend({op:'reset'});
};
document.getElementById('auto').onclick = async () => {
  const n = Number(stepsEl.value || 250000);
  if (continuousActive) {
    setContinuousActive(false);
    requestStop();
    return;
  }
  setContinuousActive(true);
  await connectWs();
  wsSend({op:'run-start', name:'continuous', steps:0, chunk:n});
};
document.getElementById('stop').onclick = async () => {
  if (timer) { clearInterval(timer); timer = null; }
  setContinuousActive(false);
  stopPolling();
  requestStop();
};
autoBootEl.onchange = () => {
  wsSend({op:'auto-calibration', enabled:autoBootEl.checked});
};
const activeButtonPointers = new Map();
const activeKeyboardKeys = new Set();
function sendKeyButton(btn, down, phase = '') {
  btn.classList.toggle('active', down);
  wsSend({
    op:'key',
    code:Number(btn.dataset.key),
    name:btn.dataset.name || '',
    down,
    phase,
    advance:false,
    run:true,
  });
}
document.querySelectorAll('[data-key]').forEach(btn => {
  btn.addEventListener('pointerdown', ev => {
    ev.preventDefault();
    if (activeButtonPointers.has(ev.pointerId)) return;
    activeButtonPointers.set(ev.pointerId, btn);
    btn.setPointerCapture?.(ev.pointerId);
    sendKeyButton(btn, true, 'down');
  });
  btn.addEventListener('pointerup', ev => {
    ev.preventDefault();
    const active = activeButtonPointers.get(ev.pointerId);
    if (!active) return;
    activeButtonPointers.delete(ev.pointerId);
    active.releasePointerCapture?.(ev.pointerId);
    sendKeyButton(active, false, 'up');
  });
  btn.addEventListener('pointercancel', ev => {
    const active = activeButtonPointers.get(ev.pointerId);
    if (!active) return;
    activeButtonPointers.delete(ev.pointerId);
    active.classList.remove('active');
    sendKeyButton(active, false, 'cancel');
  });
});
function keyCodeFromKeyboard(ev) {
  if (ev.key === 'ArrowUp') return 4;
  if (ev.key === 'ArrowDown') return 5;
  if (ev.key === 'ArrowLeft') return 6;
  if (ev.key === 'ArrowRight') return 7;
  if (ev.key === 'Enter') return 10;
  if (ev.key === 'Escape' || ev.key === 'Backspace') return 9;
  return null;
}
window.addEventListener('keydown', ev => {
  const code = keyCodeFromKeyboard(ev);
  if (code === null || activeKeyboardKeys.has(code)) return;
  ev.preventDefault();
  activeKeyboardKeys.add(code);
  wsSend({op:'key', code, down:true, source:'keyboard', advance:false, run:true});
});
window.addEventListener('keyup', ev => {
  const code = keyCodeFromKeyboard(ev);
  if (code === null || !activeKeyboardKeys.has(code)) return;
  ev.preventDefault();
  activeKeyboardKeys.delete(code);
  wsSend({op:'key', code, down:false, source:'keyboard', advance:false, run:true});
});
screen.addEventListener('pointerdown', ev => {
  ev.preventDefault();
  ev.stopPropagation();
  if (sendTouchAt(ev.clientX, ev.clientY, true, 'down', ev.pointerType || 'pointer')) {
    pointerActive = true;
    activePointerId = ev.pointerId;
    screen.setPointerCapture?.(ev.pointerId);
  }
});
screen.addEventListener('pointermove', ev => {
  if (!pointerActive || ev.pointerId !== activePointerId) return;
  ev.preventDefault();
  ev.stopPropagation();
  sendTouchAt(ev.clientX, ev.clientY, true, 'move', ev.pointerType || 'pointer', true);
});
screen.addEventListener('pointerup', ev => {
  if (!pointerActive || ev.pointerId !== activePointerId) return;
  ev.preventDefault();
  ev.stopPropagation();
  sendTouchAt(ev.clientX, ev.clientY, false, 'up', ev.pointerType || 'pointer', true);
  pointerActive = false;
  activePointerId = null;
  screen.releasePointerCapture?.(ev.pointerId);
});
screen.addEventListener('pointercancel', ev => {
  if (!pointerActive || ev.pointerId !== activePointerId) return;
  ev.preventDefault();
  ev.stopPropagation();
  sendTouchAt(ev.clientX, ev.clientY, false, 'cancel', ev.pointerType || 'pointer', true);
  pointerActive = false;
  activePointerId = null;
});
screen.addEventListener('mousedown', ev => {
  if (window.PointerEvent) return;
  ev.preventDefault();
  ev.stopPropagation();
  if (sendTouchAt(ev.clientX, ev.clientY, true, 'down', 'mouse')) pointerActive = true;
});
window.addEventListener('mouseup', ev => {
  if (window.PointerEvent || !pointerActive) return;
  sendTouchAt(ev.clientX, ev.clientY, false, 'up', 'mouse', true);
  pointerActive = false;
});
screen.addEventListener('touchstart', ev => {
  if (window.PointerEvent) return;
  ev.preventDefault();
  const t = ev.changedTouches[0];
  if (t && sendTouchAt(t.clientX, t.clientY, true, 'down', 'touch')) pointerActive = true;
}, {passive:false});
screen.addEventListener('touchend', ev => {
  if (window.PointerEvent || !pointerActive) return;
  ev.preventDefault();
  const t = ev.changedTouches[0];
  if (t) sendTouchAt(t.clientX, t.clientY, false, 'up', 'touch', true);
  pointerActive = false;
}, {passive:false});
connectWs();
refresh().catch(console.error);
</script>
</body>
</html>
"""

Handler.html = HTML


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Serve a local BBK 9588 emulator frontend.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9588)
    ap.add_argument("--ram-mb", type=int, default=160)
    ap.add_argument("--trace-limit", type=int, default=5000)
    ap.add_argument("--boot-steps", type=int, default=6_000_000)
    ap.add_argument("--input-steps", type=int, default=500_000)
    ap.add_argument(
        "--worker-slice-steps",
        type=int,
        default=250_000,
        help="Maximum emulated steps per frontend worker timeslice before publishing status/frames.",
    )
    ap.add_argument(
        "--worker-slice-seconds",
        type=float,
        default=0.02,
        help="Wall-clock timeout for each frontend worker timeslice, keeping input/status responsive in tight loops.",
    )
    ap.add_argument(
        "--run-internal-chunk-steps",
        type=int,
        default=100_000,
        help="Maximum Unicorn emu_start count inside one frontend worker slice. Lower values improve yield points; 100000 matches the previous default.",
    )
    ap.add_argument(
        "--frame-push-min-interval",
        type=float,
        default=0.04,
        help="Minimum seconds between framebuffer-dirty WebSocket frame pushes.",
    )
    ap.add_argument(
        "--frame-info-min-interval",
        type=float,
        default=1.0,
        help="Minimum seconds between full framebuffer-stat rescans for status JSON.",
    )
    ap.add_argument("--boot-mode", choices=["c200", "uboot"], default="c200", help="Frontend cold-boot path. c200 matches the passing menu regression.")
    ap.add_argument("--state-in", type=Path, help="Load an emulator checkpoint when the frontend resets.")
    ap.add_argument("--nand-image", type=Path, help="Raw NAND image backing the frontend emulator.")
    ap.add_argument(
        "--readonly-nand-page-range",
        type=parse_page_range,
        action="append",
        default=[],
        help="Diagnostic: skip NAND program commits for a half-open page range start:end.",
    )
    ap.add_argument(
        "--nand-loop-accelerator",
        dest="nand_loop_accelerator",
        action="store_true",
        default=True,
        help="Enable the verified C200 NAND data-port loop accelerator. Enabled by default for frontend cold boot.",
    )
    ap.add_argument(
        "--no-nand-loop-accelerator",
        dest="nand_loop_accelerator",
        action="store_false",
        help="Disable the C200 NAND data-port loop accelerator for diagnostics.",
    )
    ap.add_argument(
        "--resource-cache16-accelerator",
        dest="resource_cache16_accelerator",
        action="store_true",
        default=True,
        help="Enable the C200 16-bit resource-cache loop accelerator. Enabled by default for the verified cold-menu path.",
    )
    ap.add_argument(
        "--no-resource-cache16-accelerator",
        dest="resource_cache16_accelerator",
        action="store_false",
        help="Disable the C200 16-bit resource-cache loop accelerator for diagnostics.",
    )
    ap.add_argument(
        "--auto-calibration",
        dest="auto_calibration",
        action="store_true",
        default=False,
        help="Inject modeled controller-level touches for cold-boot calibration and the time dialog.",
    )
    ap.add_argument(
        "--no-auto-calibration",
        dest="auto_calibration",
        action="store_false",
        help="Disable automatic cold-boot touchscreen calibration input.",
    )
    ap.add_argument("--slow-global-code-hook", action="store_true", help="Diagnostic: hook every executed instruction instead of selected fast-hook PCs.")
    ap.add_argument("--no-cp0-status-accelerator", action="store_true", help="Diagnostic: disable CP0 status helper fast hooks.")
    ap.add_argument("--no-glyph-mask-accelerator", action="store_true", help="Diagnostic: disable the glyph-mask loop accelerator.")
    ap.add_argument("--block-image", action="store_true", help="Enable the legacy temporary logical block-device hook.")
    ap.add_argument("--scheduler-tick-clamp", action="store_true", help="Enable the old diagnostic scheduler tick clamp.")
    ap.add_argument(
        "--completed-step-timer",
        action="store_true",
        help=(
            "Drive modeled TCU/periodic IRQ time from completed Unicorn steps "
            "instead of hook observations. Keep this off for cold-boot diagnostics."
        ),
    )
    ap.add_argument(
        "--completed-step-timer-after-auto-boot",
        action="store_true",
        default=False,
        help=(
            "Switch to completed-step timer after automatic calibration/time-dialog "
            "input reaches the main menu. Off by default because menu/app event "
            "timing is still calibrated against the hook-observed source."
        ),
    )
    ap.add_argument(
        "--no-completed-step-timer-after-auto-boot",
        dest="completed_step_timer_after_auto_boot",
        action="store_false",
        help="Keep hook-observed timer source even after automatic cold boot finishes.",
    )
    ap.add_argument(
        "--key-input-mode",
        choices=["hardware", "sampler", "both"],
        default="hardware",
        help=(
            "Frontend key delivery. hardware changes modeled GPIO/INTC state; "
            "sampler uses the older 0x8005ce48 probe; both is a diagnostic "
            "compatibility mode."
        ),
    )
    ap.add_argument("--orientation", choices=["raw", "rot180", "cw90", "ccw90", "hflip", "vflip"], default="rot180")
    ap.add_argument("--profile-out", type=Path, help="Write a cProfile report when the frontend exits normally.")
    ap.add_argument("--worker-profile-out", type=Path, help="Write a cProfile report for the emulation worker thread.")
    ap.add_argument("--hot-path-stats", action="store_true", help="Diagnostic: collect per-call counters in hot emulator fast paths.")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    state = FrontendState(args)
    Handler.state = state
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"BBK9588 HWEMU frontend: http://{args.host}:{args.port}/")
    profiler = cProfile.Profile() if args.profile_out is not None else None
    try:
        if profiler is None:
            httpd.serve_forever()
        else:
            profiler.enable()
            httpd.serve_forever()
            profiler.disable()
    except KeyboardInterrupt:
        if profiler is not None:
            profiler.disable()
    finally:
        httpd.server_close()
        if profiler is not None and args.profile_out is not None:
            args.profile_out.parent.mkdir(parents=True, exist_ok=True)
            stats_path = args.profile_out
            profiler.dump_stats(str(stats_path))
            text_path = stats_path.with_suffix(stats_path.suffix + ".txt")
            with text_path.open("w", encoding="utf-8") as fh:
                stats = pstats.Stats(profiler, stream=fh).strip_dirs().sort_stats("cumtime")
                stats.print_stats(80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
