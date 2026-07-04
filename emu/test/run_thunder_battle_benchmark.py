#!/usr/bin/env python3
"""Benchmark Thunder Fighter from a saved battle checkpoint."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from emu.test.run_frontend_web_smoke import (
    BUILD,
    DEFAULT_NAND,
    WebSocketClient,
    find_free_port,
    http_json,
    key_press,
    start_frontend,
    summarize_status,
    wait_http,
)
from emu.test.run_thunder_web_smoke import KEY_LEFT, KEY_OK, KEY_RIGHT, save_ws_capture


def pump_for(ws: WebSocketClient, seconds: float) -> None:
    deadline = time.time() + max(0.0, seconds)
    while time.time() < deadline:
        ws.recv_one()


def make_contact_sheet(captures: list[dict[str, object]], out_path: Path) -> str | None:
    image_paths = [Path(str(item["path"])) for item in captures if item.get("path")]
    image_paths = [path for path in image_paths if path.exists()]
    if not image_paths:
        return None
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    tile_w, tile_h = 240, 344
    cols = min(4, len(image_paths))
    rows = (len(image_paths) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), "black")
    draw = ImageDraw.Draw(sheet)
    for idx, capture in enumerate(captures):
        path = capture.get("path")
        if not path:
            continue
        image_path = Path(str(path))
        if not image_path.exists():
            continue
        image = Image.open(image_path).convert("RGB")
        x = (idx % cols) * tile_w
        y = (idx // cols) * tile_h
        sheet.paste(image, (x, y))
        draw.text((x + 4, y + 322), str(capture.get("name") or image_path.stem), fill="white")
    sheet.save(out_path)
    return str(out_path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a short Thunder battle benchmark from a checkpoint.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="Use 0 to start a private frontend.")
    ap.add_argument("--use-existing", action="store_true")
    ap.add_argument("--nand-image", type=Path, default=DEFAULT_NAND)
    ap.add_argument("--state-in", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=BUILD)
    ap.add_argument("--prefix", default="thunder_battle_benchmark")
    ap.add_argument("--chunk-steps", type=int, default=250000)
    ap.add_argument("--worker-slice-seconds", type=float, default=0.02)
    ap.add_argument("--frame-push-min-interval", type=float, default=0.04)
    ap.add_argument("--probe-seconds", type=float, default=5.0)
    ap.add_argument("--input-probe", action="store_true", default=False)
    ap.add_argument("--completed-step-timer", action="store_true", default=False)
    ap.add_argument("--completed-step-timer-after-auto-boot", action="store_true", default=False)
    ap.add_argument("--frontend-profile-out", type=Path)
    ap.add_argument("--worker-profile-out", type=Path)
    ap.add_argument("--hot-path-stats", action="store_true", default=False)
    ns = ap.parse_args(argv)

    ns.out_dir.mkdir(parents=True, exist_ok=True)
    port = ns.port or find_free_port(ns.host)
    proc: subprocess.Popen[bytes] | None = None
    ws: WebSocketClient | None = None
    captures: list[dict[str, object]] = []
    interactions: list[dict[str, object]] = []
    failures: list[str] = []
    start = time.time()

    try:
        if not ns.state_in.exists():
            raise FileNotFoundError(ns.state_in)
        if not ns.use_existing:
            proc = start_frontend(ns, port)
        wait_http(ns.host, port, 30)
        ws = WebSocketClient(ns.host, port)
        pump_for(ws, 0.5)

        ws.send_json({"op": "reset"})
        pump_for(ws, 0.5)
        start_status = http_json(ns.host, port, "GET", "/api/status")
        interactions.append({"step": "checkpoint-loaded", "status": summarize_status(start_status)})
        captures.append(save_ws_capture(ws, ns.host, port, ns.out_dir, ns.prefix, "00_checkpoint"))

        ws.send_json({"op": "run-start", "name": "thunder-battle-benchmark", "steps": 0, "chunk": ns.chunk_steps})
        probe_start_frames = ws.frames
        probe_start = time.time()
        deadline = probe_start + max(0.1, float(ns.probe_seconds))
        while time.time() < deadline:
            ws.recv_one()
        probe_elapsed = max(0.001, time.time() - probe_start)
        probe_status = http_json(ns.host, port, "GET", "/api/status")
        interactions.append(
            {
                "step": "battle-fps-probe",
                "seconds": round(probe_elapsed, 3),
                "frames_delta": ws.frames - probe_start_frames,
                "frames_per_second": (ws.frames - probe_start_frames) / probe_elapsed,
                "status": summarize_status(probe_status),
            }
        )
        captures.append(save_ws_capture(ws, ns.host, port, ns.out_dir, ns.prefix, "01_after_probe"))

        if ns.input_probe:
            before = str(captures[-1].get("sha256") or "")
            for name, code in (("left", KEY_LEFT), ("right", KEY_RIGHT), ("ok", KEY_OK)):
                key_press(ws, code, poll_status=lambda: http_json(ns.host, port, "GET", "/api/status"))
                pump_for(ws, 1.0)
                capture = save_ws_capture(ws, ns.host, port, ns.out_dir, ns.prefix, f"02_input_{name}")
                captures.append(capture)
                interactions.append(
                    {
                        "step": f"input-{name}",
                        "digest_changed": capture.get("sha256") != before,
                        "status": capture.get("status"),
                    }
                )
                before = str(capture.get("sha256") or before)

        if ws is not None:
            ws.send_json({"op": "stop"})
            pump_for(ws, 0.5)
        if proc is not None:
            try:
                http_json(ns.host, port, "POST", "/api/shutdown")
            except Exception:
                pass
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        if ws is not None:
            ws.close()
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
            if proc.poll() is None:
                proc.kill()

    elapsed = time.time() - start
    contact_sheet = make_contact_sheet(captures, ns.out_dir / f"{ns.prefix}_contactsheet.png")
    summary = {
        "ok": not failures,
        "host": ns.host,
        "port": port,
        "state_in": str(ns.state_in),
        "elapsed_seconds": round(elapsed, 3),
        "failures": failures,
        "captures": captures,
        "contact_sheet": contact_sheet,
        "interactions": interactions,
    }
    summary_path = ns.out_dir / f"{ns.prefix}_summary.json"
    report_path = ns.out_dir / f"{ns.prefix}_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Thunder Battle Benchmark",
        "",
        f"- Result: {'PASS' if summary['ok'] else 'FAIL'}",
        f"- Elapsed seconds: {summary['elapsed_seconds']}",
        f"- State in: {ns.state_in}",
        f"- Contact sheet: {contact_sheet}",
        "",
        "## Steps",
    ]
    for item in interactions:
        lines.append(f"- {item['step']}: `{json.dumps(item, ensure_ascii=False)}`")
    if failures:
        lines += ["", "## Failures"]
        lines += [f"- {failure}" for failure in failures]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": summary["ok"], "summary": str(summary_path), "report": str(report_path), "contact_sheet": contact_sheet}, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
