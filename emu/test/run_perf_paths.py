#!/usr/bin/env python3
"""Reproducible performance probes for known slow BBK9588 frontend paths."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from emu.test.run_frontend_web_smoke import (
    BUILD,
    WebSocketClient,
    find_free_port,
    http_json,
    key_press,
    looks_like_menu,
    start_frontend,
    summarize_status,
    tap,
    wait_http,
)
from emu.test.run_thunder_web_smoke import capture_after, make_contact_sheet, save_ws_capture
from emu.tools.utils import parse_scheduled_call


TAB_POINTS = {
    "exam": (24, 286),
    "recite": (72, 286),
    "dictionary": (120, 286),
    "entertainment": (168, 286),
    "tools": (210, 287),
}


def pump_for(ws: WebSocketClient, seconds: float) -> None:
    deadline = time.time() + max(0.0, seconds)
    while time.time() < deadline:
        ws.recv_one()


def checkpoint(host: str, port: int, path: Path) -> dict[str, object]:
    return http_json(host, port, "POST", f"/api/checkpoint?path={quote(str(path))}")


def wait_for_menu(ws: WebSocketClient, host: str, port: int, timeout: float) -> dict[str, object]:
    ws.send_json({"op": "auto-calibration", "enabled": True})
    pump_for(ws, 0.5)
    ws.send_json({"op": "run-start", "name": "perf-wait-menu", "steps": 0, "chunk": 250000})
    return ws.wait_for(looks_like_menu, timeout, poll_status=lambda: http_json(host, port, "GET", "/api/status"))


def measure_tab_taps(
    ws: WebSocketClient,
    host: str,
    port: int,
    out_dir: Path,
    prefix: str,
    tabs: list[str],
    settle_seconds: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    captures: list[dict[str, object]] = []
    interactions: list[dict[str, object]] = []
    captures.append(save_ws_capture(ws, host, port, out_dir, prefix, "00_start"))
    poll_status = lambda: http_json(host, port, "GET", "/api/status")
    for index, tab in enumerate(tabs, 1):
        if tab not in TAB_POINTS:
            raise ValueError(f"unknown tab {tab!r}; known={sorted(TAB_POINTS)}")
        x, y = TAB_POINTS[tab]
        before_seq = ws.last_frame_seq
        before_frames = ws.frames
        before_status = http_json(host, port, "GET", "/api/status")
        before_insn = int(before_status.get("insn_count") or 0)
        started = time.time()
        tap(ws, x, y, poll_status=poll_status)
        frame_advanced = ws.wait_for_frame_after(before_seq, max(0.2, settle_seconds))
        pump_for(ws, settle_seconds)
        elapsed = time.time() - started
        status = http_json(host, port, "GET", "/api/status")
        after_insn = int(status.get("insn_count") or before_insn)
        capture = save_ws_capture(ws, host, port, out_dir, prefix, f"{index:02d}_tab_{tab}")
        captures.append(capture)
        interactions.append(
            {
                "step": f"tab-{tab}",
                "display": [x, y],
                "elapsed_seconds": round(elapsed, 3),
                "frame_advanced": frame_advanced,
                "frames_delta": ws.frames - before_frames,
                "insn_delta": max(0, after_insn - before_insn),
                "status": summarize_status(status),
            }
        )
    return captures, interactions


PerfAction = tuple[str, str, tuple[int | str, ...], float]
Candidate = tuple[str, list[PerfAction]]


def parse_tap(value: str) -> tuple[str, int, int, float]:
    parts = value.split(":")
    if len(parts) not in (3, 4):
        raise argparse.ArgumentTypeError("tap action must be name:x:y[:settle_seconds]")
    name = parts[0] or "tap"
    try:
        x = int(parts[1], 0)
        y = int(parts[2], 0)
        settle = float(parts[3]) if len(parts) == 4 else 1.0
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return name, x, y, settle


def parse_action(value: str) -> PerfAction:
    parts = value.split(":")
    if len(parts) < 3:
        raise argparse.ArgumentTypeError("action must be tap/key/drag/save/run")
    kind = parts[0].lower()
    name = parts[1] or kind
    try:
        if kind == "tap":
            if len(parts) not in (4, 5):
                raise argparse.ArgumentTypeError("tap action must be tap:name:x:y[:settle_seconds]")
            x = int(parts[2], 0)
            y = int(parts[3], 0)
            settle = float(parts[4]) if len(parts) == 5 else 1.0
            return kind, name, (x, y), settle
        if kind == "key":
            if len(parts) not in (3, 4):
                raise argparse.ArgumentTypeError("key action must be key:name:code[:settle_seconds]")
            code = int(parts[2], 0)
            settle = float(parts[3]) if len(parts) == 4 else 1.0
            return kind, name, (code,), settle
        if kind == "keyhold":
            if len(parts) not in (4, 5):
                raise argparse.ArgumentTypeError("keyhold action must be keyhold:name:code:hold_seconds[:settle_seconds]")
            code = int(parts[2], 0)
            hold = float(parts[3])
            settle = float(parts[4]) if len(parts) == 5 else 0.5
            return kind, name, (code, str(hold)), settle
        if kind == "drag":
            if len(parts) not in (6, 7, 8):
                raise argparse.ArgumentTypeError("drag action must be drag:name:x1:y1:x2:y2[:steps][:settle_seconds]")
            x1 = int(parts[2], 0)
            y1 = int(parts[3], 0)
            x2 = int(parts[4], 0)
            y2 = int(parts[5], 0)
            steps = int(parts[6], 0) if len(parts) >= 7 else 6
            settle = float(parts[7]) if len(parts) == 8 else 1.0
            return kind, name, (x1, y1, x2, y2, max(1, steps)), settle
        if kind == "save":
            if len(parts) not in (3, 4):
                raise argparse.ArgumentTypeError("save action must be save:name:path[:settle_seconds]")
            settle = float(parts[3]) if len(parts) == 4 else 0.1
            return kind, name, (parts[2],), settle
        if kind == "run":
            if len(parts) != 3:
                raise argparse.ArgumentTypeError("run action must be run:name:seconds")
            seconds = float(parts[2])
            return kind, name, (), seconds
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    raise argparse.ArgumentTypeError("action kind must be tap, key, keyhold, drag, save, or run")


def parse_candidate(value: str) -> Candidate:
    if "=" not in value:
        raise argparse.ArgumentTypeError("candidate must be name=action[;action...]")
    name, actions_text = value.split("=", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("candidate name must not be empty")
    actions = [parse_action(part.strip()) for part in actions_text.split(";") if part.strip()]
    if not actions:
        raise argparse.ArgumentTypeError("candidate must contain at least one action")
    return name, actions


def measure_tap_sequence(
    ws: WebSocketClient,
    host: str,
    port: int,
    out_dir: Path,
    prefix: str,
    actions: list[tuple[str, int, int, float]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    captures = [save_ws_capture(ws, host, port, out_dir, prefix, "00_start")]
    interactions: list[dict[str, object]] = []
    poll_status = lambda: http_json(host, port, "GET", "/api/status")
    for index, (name, x, y, settle) in enumerate(actions, 1):
        before_seq = ws.last_frame_seq
        before_frames = ws.frames
        before_status = http_json(host, port, "GET", "/api/status")
        before_insn = int(before_status.get("insn_count") or 0)
        started = time.time()
        tap(ws, x, y, poll_status=poll_status)
        frame_advanced = ws.wait_for_frame_after(before_seq, max(0.2, settle))
        pump_for(ws, settle)
        elapsed = time.time() - started
        status = http_json(host, port, "GET", "/api/status")
        after_insn = int(status.get("insn_count") or before_insn)
        captures.append(save_ws_capture(ws, host, port, out_dir, prefix, f"{index:02d}_{name}"))
        interactions.append(
            {
                "step": name,
                "display": [x, y],
                "elapsed_seconds": round(elapsed, 3),
                "frame_advanced": frame_advanced,
                "frames_delta": ws.frames - before_frames,
                "insn_delta": max(0, after_insn - before_insn),
                "status": summarize_status(status),
            }
        )
    return captures, interactions


def measure_action_sequence(
    ws: WebSocketClient,
    host: str,
    port: int,
    out_dir: Path,
    prefix: str,
    actions: list[PerfAction],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    captures = [save_ws_capture(ws, host, port, out_dir, prefix, "00_start")]
    interactions: list[dict[str, object]] = []
    poll_status = lambda: http_json(host, port, "GET", "/api/status")
    detail_status = lambda: http_json(host, port, "GET", "/api/status?detail=full")
    for index, (kind, name, values, settle) in enumerate(actions, 1):
        before_seq = ws.last_frame_seq
        before_frames = ws.frames
        before_status = http_json(host, port, "GET", "/api/status")
        before_insn = int(before_status.get("insn_count") or 0)
        started = time.time()
        post_settle = settle
        if kind == "tap":
            a, b = values
            tap(ws, a, b, poll_status=poll_status)
            target = [a, b]
        elif kind == "key":
            (a,) = values
            key_press(ws, a, poll_status=poll_status)
            target = a
        elif kind == "keyhold":
            a, hold_text = values
            hold = max(0.0, float(hold_text))
            down_seq = ws.send_command_async({"op": "key", "code": a, "down": True, "advance": False, "run": True})
            ws.wait_for_command_seen(down_seq, 3, poll_status=poll_status)
            ws.wait_for_queue_drained("pending_keys", 5, poll_status=poll_status)
            pump_for(ws, hold)
            up_seq = ws.send_command_async({"op": "key", "code": a, "down": False, "advance": False, "run": True})
            ws.wait_for_command_seen(up_seq, 3, poll_status=poll_status)
            ws.wait_for_queue_drained("pending_keys", 5, poll_status=poll_status)
            target = {"code": a, "hold_seconds": hold}
        elif kind == "drag":
            x1, y1, x2, y2, drag_steps = values
            if not all(isinstance(value, int) for value in values):
                raise ValueError(f"drag action {name!r} has invalid non-integer values")
            down_seq = ws.send_command_async({"op": "touch", "display_x": x1, "display_y": y1, "down": True, "phase": "down", "advance": False, "run": True})
            ws.wait_for_command_seen(down_seq, 3, poll_status=poll_status)
            ws.wait_for_queue_drained("pending_touches", 5, poll_status=poll_status)
            for step in range(1, drag_steps + 1):
                x = round(x1 + (x2 - x1) * step / drag_steps)
                y = round(y1 + (y2 - y1) * step / drag_steps)
                move_seq = ws.send_command_async({"op": "touch", "display_x": x, "display_y": y, "down": True, "phase": "move", "advance": False, "run": True})
                ws.wait_for_command_seen(move_seq, 3, poll_status=poll_status)
                ws.wait_for_queue_drained("pending_touches", 5, poll_status=poll_status)
            up_seq = ws.send_command_async({"op": "touch", "display_x": x2, "display_y": y2, "down": False, "phase": "up", "advance": False, "run": True})
            ws.wait_for_command_seen(up_seq, 3, poll_status=poll_status)
            ws.wait_for_queue_drained("pending_touches", 5, poll_status=poll_status)
            target = [x1, y1, x2, y2, drag_steps]
        elif kind == "save":
            (path_value,) = values
            path = Path(str(path_value))
            checkpoint_status = checkpoint(host, port, path)
            target = str(path)
        elif kind == "run":
            seconds = max(0.0, float(settle))
            ws.send_json({"op": "run-start", "name": f"perf-{name}", "steps": 0, "chunk": 250000})
            pump_for(ws, seconds)
            ws.send_json({"op": "stop"})
            pump_for(ws, 0.2)
            target = seconds
            post_settle = 0.2
        else:
            raise ValueError(f"unknown action kind {kind!r}")
        frame_advanced = ws.wait_for_frame_after(before_seq, max(0.2, post_settle))
        pump_for(ws, post_settle)
        elapsed = time.time() - started
        status = detail_status()
        after_insn = int(status.get("insn_count") or before_insn)
        probe = status.get("native_bda_event_probe")
        bda_runtime = status.get("bda_runtime")
        captures.append(save_ws_capture(ws, host, port, out_dir, prefix, f"{index:02d}_{name}"))
        interactions.append(
            {
                "step": name,
                "kind": kind,
                "target": target,
                "elapsed_seconds": round(elapsed, 3),
                "frame_advanced": frame_advanced,
                "frames_delta": ws.frames - before_frames,
                "insn_delta": max(0, after_insn - before_insn),
                "status": summarize_status(status if kind != "save" else checkpoint_status),
                "native_bda_event_probe": probe,
                "bda_runtime": bda_runtime,
            }
        )
    return captures, interactions


def measure_candidate_scan(
    ws: WebSocketClient,
    host: str,
    port: int,
    out_dir: Path,
    prefix: str,
    candidates: list[Candidate],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    captures: list[dict[str, object]] = []
    interactions: list[dict[str, object]] = []
    for cand_index, (candidate_name, actions) in enumerate(candidates, 1):
        ws.send_json({"op": "reset"})
        pump_for(ws, 0.5)
        start_status = http_json(host, port, "GET", "/api/status?detail=full")
        start_capture = save_ws_capture(ws, host, port, out_dir, prefix, f"{cand_index:02d}_{candidate_name}_00_start")
        captures.append(start_capture)
        candidate_prefix = f"{prefix}_{cand_index:02d}_{candidate_name}"
        measured_captures, measured = measure_action_sequence(
            ws,
            host,
            port,
            out_dir,
            candidate_prefix,
            actions,
        )
        # Drop the nested 00_start capture from measure_action_sequence; this
        # scan already saved a candidate-qualified start image.
        captures.extend(
            {
                **capture,
                "name": f"{cand_index:02d}_{candidate_name}_{capture.get('name', '')}",
            }
            for capture in measured_captures[1:]
        )
        final_status = http_json(host, port, "GET", "/api/status?detail=full")
        interactions.append(
            {
                "step": candidate_name,
                "kind": "candidate",
                "actions": [action[1] for action in actions],
                "start_sha256": start_capture.get("sha256"),
                "final_sha256": captures[-1].get("sha256") if captures else start_capture.get("sha256"),
                "changed": captures[-1].get("sha256") != start_capture.get("sha256") if captures else False,
                "start_status": summarize_status(start_status),
                "final_status": summarize_status(final_status),
                "native_bda_event_probe": final_status.get("native_bda_event_probe"),
                "measurements": measured,
            }
        )
    return captures, interactions


def run_probe(ns: argparse.Namespace) -> int:
    ns.out_dir.mkdir(parents=True, exist_ok=True)
    port = ns.port or find_free_port(ns.host)
    proc: subprocess.Popen[bytes] | None = None
    ws: WebSocketClient | None = None
    failures: list[str] = []
    captures: list[dict[str, object]] = []
    interactions: list[dict[str, object]] = []
    started = time.time()
    try:
        if not ns.use_existing:
            proc = start_frontend(ns, port)
        wait_http(ns.host, port, 30)
        ws = WebSocketClient(ns.host, port)
        pump_for(ws, 0.5)

        if ns.state_in is None:
            ws.send_json({"op": "reset"})
            pump_for(ws, 0.5)
            menu_status = wait_for_menu(ws, ns.host, port, ns.boot_timeout)
            interactions.append({"step": "wait-menu", "status": summarize_status(menu_status)})
            if not looks_like_menu(menu_status):
                failures.append("cold boot did not reach main menu")
        else:
            ws.send_json({"op": "reset"})
            pump_for(ws, 0.5)
            interactions.append(
                {
                    "step": "checkpoint-loaded",
                    "state_in": str(ns.state_in),
                    "status": summarize_status(http_json(ns.host, port, "GET", "/api/status")),
                }
            )

        if ns.checkpoint_out is not None and not failures:
            checkpoint_status = checkpoint(ns.host, port, ns.checkpoint_out)
            interactions.append(
                {
                    "step": "save-checkpoint",
                    "path": str(ns.checkpoint_out),
                    "status": summarize_status(checkpoint_status),
                }
            )

        if ns.case == "menu-tabs" and not failures:
            captures, measured = measure_tab_taps(
                ws,
                ns.host,
                port,
                ns.out_dir,
                ns.prefix,
                [part for part in ns.tabs.split(",") if part],
                ns.settle_seconds,
            )
            interactions.extend(measured)
        elif ns.case == "tap-sequence" and not failures:
            if ns.action:
                captures, measured = measure_action_sequence(ws, ns.host, port, ns.out_dir, ns.prefix, ns.action)
            else:
                captures, measured = measure_tap_sequence(ws, ns.host, port, ns.out_dir, ns.prefix, ns.tap)
            interactions.extend(measured)
        elif ns.case == "candidate-scan" and not failures:
            captures, measured = measure_candidate_scan(ws, ns.host, port, ns.out_dir, ns.prefix, ns.candidate)
            interactions.extend(measured)

        if ws is not None:
            ws.send_json({"op": "stop"})
            pump_for(ws, 0.5)
    except Exception as exc:
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        if ws is not None:
            ws.close()
        if proc is not None:
            try:
                http_json(ns.host, port, "POST", "/api/shutdown")
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()

    contact_sheet = make_contact_sheet(captures, ns.out_dir / f"{ns.prefix}_contactsheet.png")
    summary = {
        "ok": not failures,
        "case": ns.case,
        "host": ns.host,
        "port": port,
        "state_in": None if ns.state_in is None else str(ns.state_in),
        "elapsed_seconds": round(time.time() - started, 3),
        "failures": failures,
        "captures": captures,
        "contact_sheet": contact_sheet,
        "interactions": interactions,
    }
    summary_path = ns.out_dir / f"{ns.prefix}_summary.json"
    report_path = ns.out_dir / f"{ns.prefix}_report.md"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Performance Path Probe",
        "",
        f"- Result: {'PASS' if summary['ok'] else 'FAIL'}",
        f"- Case: {ns.case}",
        f"- Elapsed seconds: {summary['elapsed_seconds']}",
        f"- Contact sheet: {contact_sheet}",
        "",
        "## Steps",
    ]
    for item in interactions:
        lines.append(f"- {item['step']}: `{json.dumps(item, ensure_ascii=False)}`")
    if failures:
        lines += ["", "## Failures", *[f"- {failure}" for failure in failures]]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": summary["ok"], "summary": str(summary_path), "report": str(report_path), "contact_sheet": contact_sheet}, ensure_ascii=False))
    return 0 if summary["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run reproducible BBK9588 performance path probes.")
    ap.add_argument("--case", choices=["menu-tabs", "tap-sequence", "candidate-scan"], default="menu-tabs")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--use-existing", action="store_true")
    ap.add_argument("--nand-image", type=Path, default=None, help="Override app.py's default NAND image.")
    ap.add_argument("--state-in", type=Path)
    ap.add_argument("--mem-write-hex", action="append", default=[])
    ap.add_argument("--scheduled-call", action="append", type=parse_scheduled_call, default=[])
    ap.add_argument("--checkpoint-out", type=Path)
    ap.add_argument("--out-dir", type=Path, default=BUILD)
    ap.add_argument("--prefix", default="perf_paths")
    ap.add_argument("--boot-timeout", type=int, default=240)
    ap.add_argument("--chunk-steps", type=int, default=250000)
    ap.add_argument("--worker-slice-seconds", type=float, default=0.1)
    ap.add_argument("--run-internal-chunk-steps", type=int, default=500000)
    ap.add_argument("--frame-push-min-interval", type=float, default=0.04)
    ap.add_argument("--completed-step-timer", action="store_true", default=False)
    ap.add_argument("--completed-step-timer-after-auto-boot", action="store_true", default=False)
    ap.add_argument("--scheduler-tick-clamp", action="store_true", default=False)
    ap.add_argument("--no-cp0-status-accelerator", action="store_true", default=False)
    ap.add_argument("--no-glyph-mask-accelerator", action="store_true", default=False)
    ap.add_argument("--trace-pc", action="append", type=lambda value: int(value, 0), default=[])
    ap.add_argument("--trace-pc-detail", action="store_true", default=False)
    ap.add_argument("--hot-path-stats", action="store_true", default=False)
    ap.add_argument("--frontend-profile-out", type=Path)
    ap.add_argument("--worker-profile-out", type=Path)
    ap.add_argument("--tabs", default="exam,recite,dictionary,entertainment,tools")
    ap.add_argument("--settle-seconds", type=float, default=0.8)
    ap.add_argument(
        "--tap",
        action="append",
        type=parse_tap,
        default=[],
        help="For --case tap-sequence: name:x:y[:settle_seconds]. Can be repeated.",
    )
    ap.add_argument(
        "--action",
        action="append",
        type=parse_action,
        default=[],
        help=(
            "For --case tap-sequence: tap:name:x:y[:settle_seconds], "
            "key:name:code[:settle_seconds], keyhold:name:code:hold_seconds[:settle_seconds], "
            "drag:name:x1:y1:x2:y2[:steps][:settle_seconds], "
            "save:name:path[:settle_seconds], or run:name:seconds. Can be repeated."
        ),
    )
    ap.add_argument(
        "--candidate",
        action="append",
        type=parse_candidate,
        default=[],
        help=(
            "For --case candidate-scan: name=action[;action...]. Each candidate resets "
            "to --state-in before running. Actions use the same syntax as --action."
        ),
    )
    ns = ap.parse_args(argv)
    if ns.case == "candidate-scan" and not ns.candidate:
        ap.error("--case candidate-scan requires at least one --candidate")
    if ns.case == "tap-sequence" and not ns.tap and not ns.action:
        ns.tap = [
            ("tools-tab", 210, 287, 1.0),
            ("tools-next", 150, 306, 1.0),
            ("candidate", 120, 160, 2.0),
        ]
    return run_probe(ns)


if __name__ == "__main__":
    raise SystemExit(main())
