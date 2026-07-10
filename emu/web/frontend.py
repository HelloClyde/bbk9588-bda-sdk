#!/usr/bin/env python3
"""Small local web frontend for the BBK 9588 QEMU system emulator."""

from __future__ import annotations

import argparse
import cProfile
import pstats
from http.server import ThreadingHTTPServer
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from emu.qemu.system import DEFAULT_QEMU_EXECUTABLE, DEFAULT_QEMU_MACHINE
from emu.web.frontend_server import FrontendHandler as Handler
from emu.web.frontend_state import (
    FrontendState,
    display_to_panel_point,
    display_to_raw_point,
    display_to_touch_point,
    raw_to_display_point,
)


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
    input, select { color: #e8eaed; background: #111317; border: 1px solid #3b414b; border-radius: 6px; padding: 7px; }
    input { width: 90px; }
    input[type="checkbox"] { width: auto; accent-color: #5794ff; }
    .grow { flex: 1 1 180px; min-width: 0; }
    .path-input { flex: 1 1 260px; width: auto; min-width: 0; }
    .image-status { min-height: 1.2em; overflow-wrap: anywhere; }
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
      <div class="muted">真实 NAND 硬件级冷启动；画面来自模拟 framebuffer，触摸和按键通过前端事件队列送入。</div>
    </div>
    <div class="screen-wrap">
      <canvas id="screen" width="240" height="320"></canvas>
    </div>
    <div class="panel">
      <h2>NAND 镜像</h2>
      <div class="row">
        <select id="nandImageSelect" class="grow"></select>
        <button id="reloadImages" class="secondary">刷新</button>
      </div>
      <div class="row" style="margin-top:10px">
        <input id="nandImagePath" class="path-input" placeholder="NAND 镜像路径">
        <button id="applyNandImage">切换并重启</button>
      </div>
      <div id="imageStatus" class="muted image-status" style="margin-top:8px"></div>
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
        <label class="check"><input id="frontendInputCalibration" type="checkbox">前端输入校准</label>
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
const frontendInputCalibrationEl = document.getElementById('frontendInputCalibration');
const nandImageSelect = document.getElementById('nandImageSelect');
const nandImagePath = document.getElementById('nandImagePath');
const imageStatusEl = document.getElementById('imageStatus');
let timer = null;
let poller = null;
let framePoller = null;
let framePollInFlight = false;
let ws = null;
let wsOpenPromise = null;
let wsWatchdog = null;
let wsLastMessageAt = 0;
let continuousActive = false;
let pointerActive = false;
let activePointerId = null;
let touchDownAt = 0;
let pendingTouchReleaseTimer = null;
let currentOrientation = 'rot180';
let rgb565Lut = null;
let rawImageData = null;
const minTouchHoldMs = 180;
const wsIdleReconnectMs = 5000;

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}
function commandFetchFallback(msg) {
  return fetch('/api/command', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify(msg)
  }).then(r => r.json()).then(renderStatus);
}
function ensurePolling() {
  if (!poller) poller = setInterval(() => refresh().catch(console.error), 1000);
  ensureFramePolling();
}
function ensureFramePolling() {
  if (!framePoller) {
    framePoller = setInterval(() => refreshFrameFallback().catch(console.error), 250);
    refreshFrameFallback().catch(console.error);
  }
}
function wsIsStale() {
  return ws && ws.readyState === WebSocket.OPEN && performance.now() - wsLastMessageAt > wsIdleReconnectMs;
}
function dropWs(reason = 'stale websocket') {
  const sock = ws;
  ws = null;
  wsOpenPromise = null;
  stopWsWatchdog();
  ensurePolling();
  if (!sock || sock.readyState === WebSocket.CLOSED) return;
  try { sock.close(4000, reason); } catch (err) { console.error(err); }
}
function wsSend(msg) {
  if (wsIsStale()) {
    dropWs();
    connectWs().catch(() => {});
    return commandFetchFallback(msg);
  }
  if (ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify(msg));
      return Promise.resolve();
    } catch (err) {
      dropWs('websocket send failed');
      connectWs().catch(() => {});
      return commandFetchFallback(msg);
    }
  }
  if (!ws || ws.readyState === WebSocket.CLOSING || ws.readyState === WebSocket.CLOSED) {
    connectWs().catch(() => {});
  }
  if (wsOpenPromise) {
    return wsOpenPromise.then(sock => {
      if (!sock || sock.readyState !== WebSocket.OPEN) return commandFetchFallback(msg);
      sock.send(JSON.stringify(msg));
      return undefined;
    }).catch(() => commandFetchFallback(msg));
  }
  return commandFetchFallback(msg);
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
function cancelPendingTouchRelease() {
  if (pendingTouchReleaseTimer) {
    clearTimeout(pendingTouchReleaseTimer);
    pendingTouchReleaseTimer = null;
  }
}
function sendTouchReleaseAt(clientX, clientY, phase, source = 'pointer', clamp = true) {
  const elapsed = performance.now() - touchDownAt;
  const delay = Math.max(0, minTouchHoldMs - elapsed);
  cancelPendingTouchRelease();
  pendingTouchReleaseTimer = setTimeout(() => {
    pendingTouchReleaseTimer = null;
    sendTouchAt(clientX, clientY, false, phase, source, clamp);
  }, delay);
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
function basename(path) {
  return String(path || '').split(/[\\/]/).pop() || String(path || '');
}
function formatBytes(value) {
  const n = Number(value || 0);
  if (!n) return '';
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MiB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${n} B`;
}
function firstNumber(...values) {
  for (const value of values) {
    if (value !== null && value !== undefined && !Number.isNaN(Number(value))) return Number(value);
  }
  return null;
}
function formatRate(value, unit, fallback = 'n/a') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
  return `${Number(value).toFixed(1)} ${unit}`;
}
function formatPercent(value, fallback = 'n/a') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return fallback;
  return `${Number(value).toFixed(1)}%`;
}
function formatGuestIps(perf) {
  if (!perf || !perf.guest_ips_available) return 'n/a';
  const ips = Number(perf.guest_ips || 0);
  if (ips >= 1000000) return `${(ips / 1000000).toFixed(1)} Mips`;
  if (ips >= 1000) return `${(ips / 1000).toFixed(1)} Kips`;
  return `${ips.toFixed(0)} ips`;
}
async function refreshImages() {
  const catalog = await api('/api/images');
  const images = Array.isArray(catalog.images) ? catalog.images : [];
  nandImageSelect.replaceChildren();
  for (const image of images) {
    const option = document.createElement('option');
    option.value = image.path || '';
    const size = image.size ? ` ${formatBytes(image.size)}` : '';
    option.textContent = `${image.current ? '* ' : ''}${image.name || basename(image.path)}${size}${image.exists ? '' : ' 缺失'}`;
    option.disabled = !image.exists;
    option.selected = Boolean(image.current);
    nandImageSelect.appendChild(option);
  }
  if (!nandImageSelect.options.length) {
    const option = document.createElement('option');
    option.textContent = '未找到 NAND 镜像';
    option.disabled = true;
    nandImageSelect.appendChild(option);
  }
  const current = catalog.current_path || nandImageSelect.value || '';
  if (!nandImagePath.value || current) nandImagePath.value = current;
  imageStatusEl.textContent = current ? `当前 ${current}` : '未选择 NAND 镜像';
}
async function applyNandImage() {
  const path = (nandImagePath.value || nandImageSelect.value || '').trim();
  if (!path) {
    imageStatusEl.textContent = '没有可用镜像';
    return;
  }
  imageStatusEl.textContent = '正在切换镜像...';
  setContinuousActive(false);
  stopPolling();
  try {
    const status = await api('/api/command', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({op:'set-nand-image', path, reset:true})
    });
    renderStatus(status);
    await refreshImages();
    connectWs().catch(console.error);
  } catch (err) {
    imageStatusEl.textContent = String(err.message || err);
  }
}
function qemuCp0Status(s) {
  return s.cp0 || s.qemu?.cp0 || null;
}
function formatQemuException(s) {
  const cp0 = qemuCp0Status(s);
  if (!cp0) return '';
  const exc = cp0.exception || '';
  if (!exc) return '';
  if (exc === 'interrupt' && !cp0.exl && !cp0.erl && cp0.pending_enabled_interrupts === '0x00') {
    return '';
  }
  return exc;
}
function formatQemuIrq(s) {
  const cp0 = qemuCp0Status(s);
  if (!cp0) return '';
  const pending = cp0.pending_interrupts || '';
  const enabled = cp0.pending_enabled_interrupts || '';
  const suffix = cp0.exception === 'interrupt' && !cp0.exl && !cp0.erl && enabled === '0x00' ? ' pending' : '';
  return `${pending}/${enabled}${suffix}`;
}
function formatLastInput(s) {
  const ev = s.last_input_event;
  if (!ev) return '';
  const age = ev.at ? `${Math.max(0, (Date.now() / 1000 - Number(ev.at))).toFixed(1)}s` : '';
  const result = ev.result || {};
  if (ev.kind === 'touch') {
    const display = ev.display_x !== undefined ? ` d=${ev.display_x},${ev.display_y}` : '';
    return `${ev.down ? 'down' : 'up'} ${ev.x},${ev.y}${display} ${ev.accepted ? 'ok' : 'fail'} writes=${result.bbk_input_write_count ?? ''} ${age}`;
  }
  if (ev.kind === 'key') {
    return `${ev.down ? 'down' : 'up'} ${ev.code} ${ev.accepted ? 'ok' : 'fail'} writes=${result.bbk_input_write_count ?? ''} ${age}`;
  }
  return JSON.stringify(ev);
}
function renderStatus(s) {
  currentOrientation = s.orientation || currentOrientation;
  frontendInputCalibrationEl.checked = Boolean(s.frontend_input_calibration);
  const qemuPerf = s.qemu?.performance || {};
  const frontendPerf = s.frontend_performance || {};
  const rows = [
    ['running', s.running],
    ['since reset', formatElapsed(s.reset_elapsed_seconds ?? s.emulator_elapsed_seconds)],
    ['run elapsed', formatElapsed(s.run_elapsed_seconds)],
    ['qemu fps', formatRate(firstNumber(qemuPerf.frame_chardev_fps, qemuPerf.frame_chardev_average_fps), 'fps')],
    ['web fps', formatRate(frontendPerf.websocket_fps, 'fps')],
    ['png fps', formatRate(frontendPerf.screen_png_fps, 'fps')],
    ['qemu cpu', formatPercent(firstNumber(qemuPerf.qemu_cpu_one_core_percent, qemuPerf.qemu_cpu_host_percent))],
    ['guest ips', formatGuestIps(qemuPerf)],
    ['boot', s.boot_mode || ''],
    ['nand', basename(s.nand_image || '')],
    ['orientation', s.orientation || ''],
    ['input calib', `${s.frontend_input_calibration ? 'on' : 'off'}:${s.frontend_input_calibration_stage_label || s.frontend_input_calibration_stage || 0}`],
    ['touch queue', s.pending_touches ?? 0],
    ['key queue', s.pending_keys ?? 0],
    ['input wake', s.input_wake_count ?? 0],
    ['last input', formatLastInput(s)],
    ['frame queued', `${s.frame_push?.queued_count ?? 0}/${s.queued_frames ?? 0}`],
    ['frame sent', s.frame_push?.ws_sent_count ?? 0],
    ['job', s.job?.name || ''],
    ['job mode', s.job?.mode || ''],
    ['job status', s.job?.status || ''],
    ['job elapsed', s.job ? formatElapsed(s.job.elapsed_seconds) : ''],
    ['stop', s.stop_reason || ''],
    ['pc', s.pc],
    ['qemu region', s.qemu_pc_region || s.qemu_pc_classification?.region || s.qemu_pc_classification?.name || ''],
    ['qemu exc', formatQemuException(s)],
    ['qemu irq', formatQemuIrq(s)],
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
async function refreshFrameFallback() {
  if (framePollInFlight || (ws && ws.readyState === WebSocket.OPEN)) return;
  framePollInFlight = true;
  try {
    const res = await fetch(`/screen.png?fallback=${Date.now()}`, {cache:'no-store'});
    if (!res.ok) throw new Error(await res.text());
    await drawPngFrame(await res.blob());
  } finally {
    framePollInFlight = false;
  }
}
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
function stopWsWatchdog() {
  if (wsWatchdog) {
    clearInterval(wsWatchdog);
    wsWatchdog = null;
  }
}
function startWsWatchdog() {
  stopWsWatchdog();
  wsLastMessageAt = performance.now();
  wsWatchdog = setInterval(() => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (performance.now() - wsLastMessageAt <= wsIdleReconnectMs) return;
    ws.close(4000, 'stale websocket');
  }, 1000);
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
  ws.onopen = () => {
    stopPolling();
    stopFramePolling();
    startWsWatchdog();
  };
  ws.onmessage = async ev => {
    wsLastMessageAt = performance.now();
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
    stopWsWatchdog();
    ws = null;
    wsOpenPromise = null;
    ensurePolling();
    setTimeout(connectWs, 1500);
  };
  ws.onerror = () => ws?.close();
  return wsOpenPromise;
}
function stopPolling() {
  if (poller) { clearInterval(poller); poller = null; }
}
function stopFramePolling() {
  if (framePoller) { clearInterval(framePoller); framePoller = null; }
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
frontendInputCalibrationEl.onchange = () => {
  wsSend({op:'frontend-input-calibration', enabled:frontendInputCalibrationEl.checked});
};
nandImageSelect.onchange = () => {
  if (nandImageSelect.value) nandImagePath.value = nandImageSelect.value;
};
document.getElementById('reloadImages').onclick = () => refreshImages().catch(err => {
  imageStatusEl.textContent = String(err.message || err);
});
document.getElementById('applyNandImage').onclick = applyNandImage;
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
  cancelPendingTouchRelease();
  if (sendTouchAt(ev.clientX, ev.clientY, true, 'down', ev.pointerType || 'pointer')) {
    pointerActive = true;
    activePointerId = ev.pointerId;
    touchDownAt = performance.now();
    screen.setPointerCapture?.(ev.pointerId);
  }
});
screen.addEventListener('pointermove', ev => {
  if (!pointerActive || ev.pointerId !== activePointerId) return;
  ev.preventDefault();
  ev.stopPropagation();
  cancelPendingTouchRelease();
  sendTouchAt(ev.clientX, ev.clientY, true, 'move', ev.pointerType || 'pointer', true);
});
screen.addEventListener('pointerup', ev => {
  if (!pointerActive || ev.pointerId !== activePointerId) return;
  ev.preventDefault();
  ev.stopPropagation();
  sendTouchReleaseAt(ev.clientX, ev.clientY, 'up', ev.pointerType || 'pointer', true);
  pointerActive = false;
  activePointerId = null;
  screen.releasePointerCapture?.(ev.pointerId);
});
screen.addEventListener('pointercancel', ev => {
  if (!pointerActive || ev.pointerId !== activePointerId) return;
  ev.preventDefault();
  ev.stopPropagation();
  sendTouchReleaseAt(ev.clientX, ev.clientY, 'cancel', ev.pointerType || 'pointer', true);
  pointerActive = false;
  activePointerId = null;
});
screen.addEventListener('mousedown', ev => {
  if (window.PointerEvent) return;
  ev.preventDefault();
  ev.stopPropagation();
  cancelPendingTouchRelease();
  if (sendTouchAt(ev.clientX, ev.clientY, true, 'down', 'mouse')) {
    pointerActive = true;
    touchDownAt = performance.now();
  }
});
window.addEventListener('mouseup', ev => {
  if (window.PointerEvent || !pointerActive) return;
  sendTouchReleaseAt(ev.clientX, ev.clientY, 'up', 'mouse', true);
  pointerActive = false;
});
screen.addEventListener('touchstart', ev => {
  if (window.PointerEvent) return;
  ev.preventDefault();
  const t = ev.changedTouches[0];
  cancelPendingTouchRelease();
  if (t && sendTouchAt(t.clientX, t.clientY, true, 'down', 'touch')) {
    pointerActive = true;
    touchDownAt = performance.now();
  }
}, {passive:false});
screen.addEventListener('touchend', ev => {
  if (window.PointerEvent || !pointerActive) return;
  ev.preventDefault();
  const t = ev.changedTouches[0];
  if (t) sendTouchReleaseAt(t.clientX, t.clientY, 'up', 'touch', true);
  pointerActive = false;
}, {passive:false});
connectWs();
refresh().catch(console.error);
refreshImages().catch(console.error);
</script>
</body>
</html>
"""

Handler.html = HTML


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Serve a local BBK 9588 QEMU frontend.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--ram-mb", type=int, default=160)
    ap.add_argument(
        "--frame-push-min-interval",
        type=float,
        default=1.0 / 30.0,
        help="Minimum seconds between QEMU frame-chardev WebSocket frame pushes.",
    )
    ap.add_argument(
        "--frame-info-min-interval",
        type=float,
        default=1.0,
        help="Minimum seconds between full framebuffer-stat rescans for status JSON.",
    )
    ap.add_argument("--boot-mode", choices=["nand", "c200", "uboot"], default="nand", help="QEMU cold-boot path.")
    ap.add_argument(
        "--image",
        type=Path,
        help="Optional direct boot image path for c200/uboot compatibility modes.",
    )
    ap.add_argument(
        "--payload",
        type=Path,
        help="Optional legacy C200 RAM preload for uboot mode.",
    )
    ap.add_argument("--nand-image", type=Path, help="Raw NAND image backing the frontend emulator.")
    ap.add_argument(
        "--frontend-input-calibration",
        dest="frontend_input_calibration",
        action="store_true",
        default=False,
        help="Frontend diagnostic helper: feed cold-boot calibration touches through the QEMU input chardev.",
    )
    ap.add_argument(
        "--no-frontend-input-calibration",
        dest="frontend_input_calibration",
        action="store_false",
        help="Disable the frontend input calibration helper.",
    )
    ap.add_argument("--orientation", choices=["raw", "rot180", "cw90", "ccw90", "hflip", "vflip"], default="rot180")
    ap.add_argument("--profile-out", type=Path, help="Write a cProfile report when the frontend exits normally.")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--backend", choices=["qemu"], default="qemu", help=argparse.SUPPRESS)
    ap.add_argument("--qemu", default=DEFAULT_QEMU_EXECUTABLE, help="QEMU executable.")
    ap.add_argument("--qemu-machine", default=DEFAULT_QEMU_MACHINE, help="QEMU machine.")
    ap.add_argument("--qemu-cpu", default="24Kf", help="QEMU CPU model.")
    ap.add_argument("--qemu-accel", default="tcg,thread=multi,tb-size=256", help="QEMU accelerator options.")
    ap.add_argument("--qemu-gdb", default="none", help="QEMU GDB stub target; use 'auto' to allocate a local port.")
    ap.add_argument("--qemu-timeout", type=float, default=5.0, help="Default bounded-run timeout used by QEMU probes.")
    ap.add_argument(
        "--qemu-machine-option",
        action="append",
        default=[],
        help="Append one diagnostic bbk9588 -M option, for example progress-trace=on. Can be repeated.",
    )
    ap.add_argument("--qemu-extra-arg", action="append", default=[], help="Append one raw QEMU argument. Can be repeated.")
    ap.add_argument(
        "--qemu-firmware-patch",
        action="append",
        default=None,
        help="Legacy diagnostic QEMU-only firmware patch name for compatibility runs, or 'none'.",
    )
    ap.add_argument(
        "--allow-gdb-diagnostics",
        action="store_true",
        default=False,
        help="Enable explicit intrusive GDB diagnostics such as write watches and breakpoint traces.",
    )
    args = ap.parse_args(argv)
    args.backend = "qemu"

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
        try:
            state.stop()
        except Exception:
            pass
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
