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
    :root { color-scheme: dark; font-family: "Segoe UI", sans-serif; background: #15171a; color: #e8eaed; letter-spacing: 0; }
    * { box-sizing: border-box; }
    html, body { min-height: 100%; }
    body { margin: 0; min-height: 100vh; background: #15171a; }
    .app-header { height: 56px; display: flex; align-items: center; padding: 0 18px; border-bottom: 1px solid #343941; background: #191b1f; }
    .workspace { min-height: calc(100vh - 56px); display: grid; grid-template-columns: minmax(280px, 340px) minmax(390px, 1fr) minmax(280px, 340px); grid-template-areas: "controls stage status"; }
    .control-sidebar { grid-area: controls; padding: 16px; border-right: 1px solid #343941; background: #1b1e22; overflow: auto; }
    .emulator-stage { grid-area: stage; min-width: 0; padding: 16px 20px 22px; display: flex; flex-direction: column; align-items: center; gap: 12px; overflow: auto; }
    .status-sidebar { grid-area: status; padding: 16px; border-left: 1px solid #343941; background: #202327; overflow: auto; }
    h1 { font-size: 18px; margin: 0; font-weight: 650; }
    h2 { font-size: 13px; margin: 0 0 10px; color: #b8c0cc; font-weight: 600; }
    button, input, select { font: inherit; }
    button { background: #2f6fed; color: white; border: 0; border-radius: 6px; padding: 8px 10px; cursor: pointer; }
    button.secondary { background: #343941; }
    button.warn { background: #9b3b3b; }
    button:disabled { opacity: .55; cursor: default; }
    .icon-button { width: 40px; height: 36px; display: inline-grid; place-items: center; padding: 0; font-size: 22px; line-height: 1; }
    .screen-toolbar { width: min(560px, 100%); display: flex; justify-content: center; align-items: center; gap: 8px; }
    .orientation-label { min-width: 54px; text-align: center; color: #c9d1d9; font-size: 12px; font-variant-numeric: tabular-nums; }
    .screen-wrap { width: 100%; min-height: 0; display: flex; justify-content: center; align-items: center; background: #08090b; border: 1px solid #343941; border-radius: 8px; padding: 12px; }
    #screen { display: block; width: min(360px, 100%); height: auto; max-height: 62vh; image-rendering: pixelated; background: #000; cursor: crosshair; touch-action: none; user-select: none; }
    #screen.landscape { width: min(560px, 100%); }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .panel { border: 1px solid #343941; border-radius: 8px; padding: 12px; background: #1b1e22; margin-bottom: 14px; }
    .kv { display: grid; grid-template-columns: minmax(100px, 120px) minmax(0, 1fr); gap: 5px 10px; font-size: 12px; }
    .kv > div { min-width: 0; }
    .kv-value { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .device-controls { width: min(560px, 100%); display: flex; flex-direction: column; align-items: center; gap: 14px; }
    .device-keypad { display: grid; grid-template-columns: repeat(5, 54px); grid-template-rows: repeat(2, 48px); gap: 8px; justify-content: center; }
    .device-key { min-width: 0; min-height: 0; padding: 5px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; background: #343941; }
    .device-key.active { background: #5794ff; }
    .device-key .key-symbol { font-size: 19px; line-height: 1; }
    .device-key kbd { min-width: 24px; color: #adb7c5; font-size: 10px; font-family: inherit; font-weight: 500; }
    .device-key.active kbd { color: white; }
    .key-up { grid-column: 3; grid-row: 1; }
    .key-left { grid-column: 2; grid-row: 2; }
    .key-down { grid-column: 3; grid-row: 2; }
    .key-right { grid-column: 4; grid-row: 2; }
    .key-cancel { grid-column: 1; grid-row: 1 / 3; }
    .key-ok { grid-column: 5; grid-row: 1 / 3; }
    .keymap-panel { width: 100%; border-top: 1px solid #343941; padding-top: 12px; }
    .keymap-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    .keymap-header h2 { margin: 0; }
    .keymap-header .icon-button { width: 32px; height: 30px; font-size: 18px; }
    .binding-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; }
    .binding-control { display: grid; grid-template-columns: 42px minmax(0, 1fr); align-items: center; gap: 6px; color: #b8c0cc; font-size: 12px; }
    .binding-control button { min-width: 0; height: 32px; padding: 4px 6px; background: #2a2e34; border: 1px solid #414751; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .binding-control button.capturing { border-color: #5794ff; background: #253c62; }
    input, select { color: #e8eaed; background: #111317; border: 1px solid #3b414b; border-radius: 6px; padding: 7px; }
    input { width: 90px; }
    input[type="checkbox"] { width: auto; accent-color: #5794ff; }
    .grow { flex: 1 1 180px; min-width: 0; }
    .path-input { flex: 1 1 260px; width: auto; min-width: 0; }
    .image-status { min-height: 1.2em; overflow-wrap: anywhere; }
    .check { display: inline-flex; gap: 6px; align-items: center; color: #c9d1d9; font-size: 12px; }
    pre { margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.45; color: #c9d1d9; }
    .muted { color: #9aa4b2; font-size: 12px; }
    @media (max-width: 1120px) {
      .workspace { grid-template-columns: minmax(250px, 300px) minmax(390px, 1fr); grid-template-areas: "controls stage" "status status"; }
      .status-sidebar { border-left: 0; border-top: 1px solid #343941; }
    }
    @media (max-width: 760px) {
      .app-header { height: 50px; }
      .workspace { min-height: calc(100vh - 50px); grid-template-columns: minmax(0, 1fr); grid-template-areas: "stage" "controls" "status"; }
      .emulator-stage { padding: 12px; }
      .control-sidebar, .status-sidebar { border: 0; border-top: 1px solid #343941; }
      #screen { max-height: none; }
      .binding-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 380px) {
      .device-keypad { grid-template-columns: repeat(5, 48px); gap: 6px; }
    }
  </style>
</head>
<body>
  <header class="app-header">
    <h1>BBK 9588 硬件仿真器</h1>
  </header>
  <div class="workspace">
    <aside class="control-sidebar" aria-label="镜像与运行控制">
      <section class="panel">
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
      </section>
      <section class="panel">
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
      </section>
    </aside>
    <main class="emulator-stage">
      <div class="screen-toolbar" role="toolbar" aria-label="屏幕方向">
        <button id="rotateLeft" class="secondary icon-button" title="向左旋转 90°" aria-label="向左旋转 90°">↶</button>
        <span id="orientationLabel" class="orientation-label">180°</span>
        <button id="rotateRight" class="secondary icon-button" title="向右旋转 90°" aria-label="向右旋转 90°">↷</button>
      </div>
      <div class="screen-wrap">
        <canvas id="screen" width="240" height="320"></canvas>
      </div>
      <div class="device-controls">
        <div class="device-keypad" aria-label="设备按键">
          <button class="device-key key-up" data-key="4" data-name="up" aria-label="上"><span class="key-symbol">↑</span><kbd data-key-hint="4">W</kbd></button>
          <button class="device-key key-left" data-key="6" data-name="left" aria-label="左"><span class="key-symbol">←</span><kbd data-key-hint="6">A</kbd></button>
          <button class="device-key key-down" data-key="5" data-name="down" aria-label="下"><span class="key-symbol">↓</span><kbd data-key-hint="5">S</kbd></button>
          <button class="device-key key-right" data-key="7" data-name="right" aria-label="右"><span class="key-symbol">→</span><kbd data-key-hint="7">D</kbd></button>
          <button class="device-key key-cancel" data-key="9" data-name="cancel" aria-label="退出"><span class="key-symbol">退出</span><kbd data-key-hint="9">Esc</kbd></button>
          <button class="device-key key-ok" data-key="10" data-name="ok" aria-label="确定"><span class="key-symbol">确定</span><kbd data-key-hint="10">Space</kbd></button>
        </div>
        <section class="keymap-panel">
          <div class="keymap-header">
            <h2>键盘映射</h2>
            <button id="resetKeyBindings" class="secondary icon-button" title="恢复默认映射" aria-label="恢复默认映射">↺</button>
          </div>
          <div class="binding-grid">
            <div class="binding-control"><span>上</span><button data-binding-code="4">W</button></div>
            <div class="binding-control"><span>下</span><button data-binding-code="5">S</button></div>
            <div class="binding-control"><span>左</span><button data-binding-code="6">A</button></div>
            <div class="binding-control"><span>右</span><button data-binding-code="7">D</button></div>
            <div class="binding-control"><span>确定</span><button data-binding-code="10">Space</button></div>
            <div class="binding-control"><span>退出</span><button data-binding-code="9">Esc</button></div>
          </div>
        </section>
      </div>
    </main>
    <aside class="status-sidebar" aria-label="模拟器状态">
      <section class="panel">
        <h2>状态</h2>
        <div id="status" class="kv"></div>
      </section>
    </aside>
  </div>
<script>
const screen = document.getElementById('screen');
const screenCtx = screen.getContext('2d', { alpha: false });
screenCtx.imageSmoothingEnabled = false;
const statusEl = document.getElementById('status');
const stepsEl = document.getElementById('steps');
const frontendInputCalibrationEl = document.getElementById('frontendInputCalibration');
const nandImageSelect = document.getElementById('nandImageSelect');
const nandImagePath = document.getElementById('nandImagePath');
const imageStatusEl = document.getElementById('imageStatus');
const rotateLeftEl = document.getElementById('rotateLeft');
const rotateRightEl = document.getElementById('rotateRight');
const orientationLabelEl = document.getElementById('orientationLabel');
const resetKeyBindingsEl = document.getElementById('resetKeyBindings');
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
let pendingTouchMove = null;
let pendingTouchMoveFrame = null;
let pendingTouchMoveTimer = null;
let lastTouchMoveSentAt = 0;
let touchMoveAwaitingFrame = false;
let currentOrientation = 'rot180';
let pendingOrientation = null;
let lastRawFrameBuffer = null;
let rgb565Lut = null;
let rawImageData = null;
let bindingCaptureCode = null;
const minTouchHoldMs = 180;
const minTouchMoveIntervalMs = 1000 / 30;
const touchMoveBackpressureMs = 100;
const minKeyHoldMs = 100;
const wsIdleReconnectMs = 5000;
const keyBindingStorageKey = 'bbk9588.keyBindings.v1';
const defaultKeyBindings = Object.freeze({
  4:'KeyW',
  5:'KeyS',
  6:'KeyA',
  7:'KeyD',
  9:'Escape',
  10:'Space',
});
const rotationOrientations = ['raw', 'cw90', 'rot180', 'ccw90'];
const orientationLabels = {raw:'0°', cw90:'90°', rot180:'180°', ccw90:'270°', hflip:'水平', vflip:'垂直'};
let keyBindings = loadKeyBindings();

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
function clearPendingTouchMove() {
  pendingTouchMove = null;
  if (pendingTouchMoveFrame !== null) {
    cancelAnimationFrame(pendingTouchMoveFrame);
    pendingTouchMoveFrame = null;
  }
  if (pendingTouchMoveTimer !== null) {
    clearTimeout(pendingTouchMoveTimer);
    pendingTouchMoveTimer = null;
  }
}
function flushPendingTouchMove() {
  if (!pendingTouchMove) {
    clearPendingTouchMove();
    return false;
  }
  const move = pendingTouchMove;
  clearPendingTouchMove();
  const sent = sendTouchAt(move.clientX, move.clientY, true, 'move', move.source, true);
  if (sent) {
    lastTouchMoveSentAt = performance.now();
    touchMoveAwaitingFrame = true;
  }
  return sent;
}
function schedulePendingTouchMove() {
  if (pendingTouchMoveFrame !== null || pendingTouchMoveTimer !== null) return;
  const elapsed = performance.now() - lastTouchMoveSentAt;
  const rateDelay = minTouchMoveIntervalMs - elapsed;
  const frameDelay = touchMoveAwaitingFrame ? touchMoveBackpressureMs - elapsed : 0;
  const delay = Math.max(0, rateDelay, frameDelay);
  if (delay > 0) {
    pendingTouchMoveTimer = setTimeout(() => {
      pendingTouchMoveTimer = null;
      schedulePendingTouchMove();
    }, delay);
    return;
  }
  pendingTouchMoveFrame = requestAnimationFrame(() => {
    pendingTouchMoveFrame = null;
    const move = pendingTouchMove;
    pendingTouchMove = null;
    if (move && pointerActive) {
      if (sendTouchAt(move.clientX, move.clientY, true, 'move', move.source, true)) {
        lastTouchMoveSentAt = performance.now();
        touchMoveAwaitingFrame = true;
      }
    }
    if (pendingTouchMove) schedulePendingTouchMove();
  });
}
function queueTouchMove(clientX, clientY, source = 'pointer') {
  pendingTouchMove = {clientX, clientY, source};
  schedulePendingTouchMove();
}
function sendTouchReleaseAt(clientX, clientY, phase, source = 'pointer', clamp = true) {
  flushPendingTouchMove();
  const elapsed = performance.now() - touchDownAt;
  const delay = Math.max(0, minTouchHoldMs - elapsed);
  cancelPendingTouchRelease();
  pendingTouchReleaseTimer = setTimeout(() => {
    pendingTouchReleaseTimer = null;
    sendTouchAt(clientX, clientY, false, phase, source, clamp);
    touchMoveAwaitingFrame = false;
  }, delay);
}
function noteScreenFrame() {
  if (!touchMoveAwaitingFrame) return;
  touchMoveAwaitingFrame = false;
  if (pendingTouchMove && pointerActive) schedulePendingTouchMove();
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
function updateOrientationControls() {
  orientationLabelEl.textContent = orientationLabels[currentOrientation] || currentOrientation;
  const disabled = pendingOrientation !== null;
  rotateLeftEl.disabled = disabled;
  rotateRightEl.disabled = disabled;
}
function applyFrontendOrientation(orientation) {
  if (!orientation || !(orientation in orientationLabels)) return;
  const changed = currentOrientation !== orientation;
  currentOrientation = orientation;
  if (pendingOrientation === orientation) pendingOrientation = null;
  updateOrientationControls();
  if (changed && lastRawFrameBuffer) {
    requestAnimationFrame(() => drawRawRgb565Frame(lastRawFrameBuffer));
  }
}
function requestRotation(delta) {
  if (pendingOrientation !== null) return;
  let index = rotationOrientations.indexOf(currentOrientation);
  if (index < 0) index = rotationOrientations.indexOf('rot180');
  const next = rotationOrientations[(index + delta + rotationOrientations.length) % rotationOrientations.length];
  pendingOrientation = next;
  updateOrientationControls();
  wsSend({op:'set-orientation', orientation:next}).catch(err => {
    console.error(err);
    pendingOrientation = null;
    updateOrientationControls();
  });
  setTimeout(() => {
    if (pendingOrientation !== next) return;
    refresh().catch(console.error).finally(() => {
      if (pendingOrientation === next) {
        pendingOrientation = null;
        updateOrientationControls();
      }
    });
  }, 1200);
}
function renderStatus(s) {
  applyFrontendOrientation(s.orientation || currentOrientation);
  frontendInputCalibrationEl.checked = Boolean(s.frontend_input_calibration);
  const qemuPerf = s.qemu?.performance || {};
  const frontendPerf = s.frontend_performance || {};
  const rows = [
    ['running', s.running],
    ['since reset', formatElapsed(s.reset_elapsed_seconds ?? s.emulator_elapsed_seconds)],
    ['run elapsed', formatElapsed(s.run_elapsed_seconds)],
    ['qemu fps', formatRate(firstNumber(qemuPerf.frame_chardev_fps, qemuPerf.frame_chardev_average_fps), 'fps')],
    ['web fps', formatRate(frontendPerf.websocket_fps, 'fps')],
    ['web tx', formatRate(frontendPerf.websocket_transport_fps, 'fps')],
    ['ws clients', s.frame_push?.ws_connections ?? 0],
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
    ['push lag', `${s.frame_push?.source_lag_ms ?? ''} ms`],
    ['frame skipped', s.frame_push?.replace_count ?? 0],
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
  const statusNodes = [];
  for (const [key, value] of rows) {
    const labelEl = document.createElement('div');
    const valueEl = document.createElement('div');
    const valueText = String(value);
    labelEl.textContent = key;
    valueEl.className = 'kv-value';
    valueEl.textContent = valueText;
    valueEl.title = valueText;
    statusNodes.push(labelEl, valueEl);
  }
  statusEl.replaceChildren(...statusNodes);
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
  screen.classList.toggle('landscape', width > height);
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
  lastRawFrameBuffer = buffer;
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
  noteScreenFrame();
  return true;
}
async function drawPngFrame(data) {
  const blob = data instanceof Blob ? data : new Blob([data], {type:'image/png'});
  const bitmap = await createImageBitmap(blob);
  ensureScreenSize(bitmap.width, bitmap.height);
  screenCtx.drawImage(bitmap, 0, 0);
  bitmap.close?.();
  noteScreenFrame();
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
rotateLeftEl.onclick = () => requestRotation(-1);
rotateRightEl.onclick = () => requestRotation(1);

function loadKeyBindings() {
  const bindings = {...defaultKeyBindings};
  try {
    const saved = JSON.parse(localStorage.getItem(keyBindingStorageKey) || '{}');
    for (const code of Object.keys(bindings)) {
      if (typeof saved[code] === 'string' && saved[code]) bindings[code] = saved[code];
    }
    if (new Set(Object.values(bindings)).size !== Object.keys(bindings).length) {
      return {...defaultKeyBindings};
    }
  } catch (err) {
    console.error(err);
  }
  return bindings;
}
function saveKeyBindings() {
  try { localStorage.setItem(keyBindingStorageKey, JSON.stringify(keyBindings)); } catch (err) { console.error(err); }
}
function keyboardCodeLabel(code) {
  if (code === 'Space') return 'Space';
  if (code === 'Escape') return 'Esc';
  if (code === 'Enter') return 'Enter';
  if (code === 'Backspace') return 'Backspace';
  if (code.startsWith('Key')) return code.slice(3);
  if (code.startsWith('Digit')) return code.slice(5);
  if (code.startsWith('Numpad')) return `Num ${code.slice(6)}`;
  if (code.startsWith('Arrow')) return code.slice(5);
  return code;
}
function updateKeyBindingUi() {
  document.querySelectorAll('[data-key-hint]').forEach(el => {
    el.textContent = keyboardCodeLabel(keyBindings[String(el.dataset.keyHint)] || '');
  });
  document.querySelectorAll('[data-binding-code]').forEach(btn => {
    const code = String(btn.dataset.bindingCode);
    const capturing = bindingCaptureCode === code;
    btn.classList.toggle('capturing', capturing);
    btn.textContent = capturing ? '…' : keyboardCodeLabel(keyBindings[code] || '');
  });
}
function beginBindingCapture(code) {
  bindingCaptureCode = String(code);
  updateKeyBindingUi();
}
function assignCapturedBinding(physicalCode) {
  const targetCode = bindingCaptureCode;
  if (targetCode === null) return;
  const previous = keyBindings[targetCode];
  const duplicate = Object.keys(keyBindings).find(code => code !== targetCode && keyBindings[code] === physicalCode);
  if (duplicate) keyBindings[duplicate] = previous;
  keyBindings[targetCode] = physicalCode;
  bindingCaptureCode = null;
  saveKeyBindings();
  updateKeyBindingUi();
  if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
}
document.querySelectorAll('[data-binding-code]').forEach(btn => {
  btn.addEventListener('click', ev => {
    ev.preventDefault();
    beginBindingCapture(btn.dataset.bindingCode);
  });
});
resetKeyBindingsEl.onclick = () => {
  keyBindings = {...defaultKeyBindings};
  bindingCaptureCode = null;
  saveKeyBindings();
  updateKeyBindingUi();
};
const activeButtonPointers = new Map();
const buttonKeyStates = new Map();
const activeKeyboardKeys = new Map();
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
function beginKeyButton(btn) {
  const code = Number(btn.dataset.key);
  const pending = buttonKeyStates.get(code);
  if (pending?.releaseTimer) {
    clearTimeout(pending.releaseTimer);
    pending.releaseTimer = null;
    btn.classList.add('active');
    return;
  }
  if (pending) return;
  sendKeyButton(btn, true, 'down');
  buttonKeyStates.set(code, {btn, downAt:performance.now(), releaseTimer:null});
}
function endKeyButton(btn, phase) {
  const code = Number(btn.dataset.key);
  const state = buttonKeyStates.get(code);
  if (!state || state.releaseTimer) return;
  const delay = Math.max(0, minKeyHoldMs - (performance.now() - state.downAt));
  state.releaseTimer = setTimeout(() => {
    sendKeyButton(state.btn, false, phase);
    buttonKeyStates.delete(code);
  }, delay);
}
document.querySelectorAll('[data-key]').forEach(btn => {
  btn.addEventListener('pointerdown', ev => {
    ev.preventDefault();
    if (activeButtonPointers.has(ev.pointerId)) return;
    activeButtonPointers.set(ev.pointerId, btn);
    btn.setPointerCapture?.(ev.pointerId);
    beginKeyButton(btn);
  });
  btn.addEventListener('pointerup', ev => {
    ev.preventDefault();
    const active = activeButtonPointers.get(ev.pointerId);
    if (!active) return;
    activeButtonPointers.delete(ev.pointerId);
    active.releasePointerCapture?.(ev.pointerId);
    endKeyButton(active, 'up');
  });
  btn.addEventListener('pointercancel', ev => {
    const active = activeButtonPointers.get(ev.pointerId);
    if (!active) return;
    activeButtonPointers.delete(ev.pointerId);
    endKeyButton(active, 'cancel');
  });
});
function keyCodeFromKeyboard(ev) {
  for (const [guestCode, physicalCode] of Object.entries(keyBindings)) {
    if (physicalCode === ev.code) return Number(guestCode);
  }
  return null;
}
function isEditableTarget(target) {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName);
}
window.addEventListener('keydown', ev => {
  if (bindingCaptureCode !== null) {
    ev.preventDefault();
    ev.stopPropagation();
    assignCapturedBinding(ev.code);
    return;
  }
  if (isEditableTarget(ev.target)) return;
  const code = keyCodeFromKeyboard(ev);
  if (code === null || activeKeyboardKeys.has(ev.code)) return;
  ev.preventDefault();
  activeKeyboardKeys.set(ev.code, code);
  wsSend({op:'key', code, down:true, source:'keyboard', advance:false, run:true});
});
window.addEventListener('keyup', ev => {
  const code = activeKeyboardKeys.get(ev.code);
  if (code === undefined) return;
  ev.preventDefault();
  activeKeyboardKeys.delete(ev.code);
  wsSend({op:'key', code, down:false, source:'keyboard', advance:false, run:true});
});
window.addEventListener('blur', () => {
  for (const code of activeKeyboardKeys.values()) {
    wsSend({op:'key', code, down:false, source:'keyboard-blur', advance:false, run:true});
  }
  activeKeyboardKeys.clear();
});
screen.addEventListener('pointerdown', ev => {
  ev.preventDefault();
  ev.stopPropagation();
  cancelPendingTouchRelease();
  clearPendingTouchMove();
  touchMoveAwaitingFrame = false;
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
  queueTouchMove(ev.clientX, ev.clientY, ev.pointerType || 'pointer');
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
  clearPendingTouchMove();
  touchMoveAwaitingFrame = false;
  if (sendTouchAt(ev.clientX, ev.clientY, true, 'down', 'mouse')) {
    pointerActive = true;
    touchDownAt = performance.now();
  }
});
screen.addEventListener('mousemove', ev => {
  if (window.PointerEvent || !pointerActive) return;
  ev.preventDefault();
  ev.stopPropagation();
  cancelPendingTouchRelease();
  queueTouchMove(ev.clientX, ev.clientY, 'mouse');
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
  clearPendingTouchMove();
  touchMoveAwaitingFrame = false;
  if (t && sendTouchAt(t.clientX, t.clientY, true, 'down', 'touch')) {
    pointerActive = true;
    touchDownAt = performance.now();
  }
}, {passive:false});
screen.addEventListener('touchmove', ev => {
  if (window.PointerEvent || !pointerActive) return;
  ev.preventDefault();
  const t = ev.changedTouches[0];
  if (t) {
    cancelPendingTouchRelease();
    queueTouchMove(t.clientX, t.clientY, 'touch');
  }
}, {passive:false});
screen.addEventListener('touchend', ev => {
  if (window.PointerEvent || !pointerActive) return;
  ev.preventDefault();
  const t = ev.changedTouches[0];
  if (t) sendTouchReleaseAt(t.clientX, t.clientY, 'up', 'touch', true);
  pointerActive = false;
}, {passive:false});
updateOrientationControls();
updateKeyBindingUi();
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
