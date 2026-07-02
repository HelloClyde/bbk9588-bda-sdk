#!/usr/bin/env python3
"""Run direct-BDA smoke regressions for the BBK 9588 emulator."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SmokeCase:
    name: str
    bda: Path
    expected_stop: str = "bda_event_idle"
    expected_text: str | None = None


DEFAULT_CASES = [
    SmokeCase(
        name="msgbox",
        bda=Path("build") / "calc_startup_msgbox_origtitle.bda",
        expected_text="HelloWorld native BDAHello",
    ),
    SmokeCase(
        name="sdkinput",
        bda=Path("build") / "SDKInputReady_gcc.bda",
        expected_text="BDA SDKSDK probe: alloc/gui ok",
    ),
]


def glyph_text(events: list[dict[str, object]]) -> str:
    chars: list[str] = []
    for event in events:
        if event.get("kind") != "synthetic-glyph":
            continue
        value = event.get("value")
        if isinstance(value, str):
            code = int(value, 16)
        elif isinstance(value, int):
            code = value
        else:
            continue
        chars.append(chr(code) if 32 <= code < 127 else "?")
    return "".join(chars)


def run_case(
    case: SmokeCase,
    out_dir: Path,
    timeout: int,
    text_mode: str,
    native_glyph_layout: str,
    native_raster_mode: str,
    fb_orientation: str | None,
    bda_idle_stop_polls: int | None,
    bda_key_events: list[str],
    bda_events: list[str],
    bda_touch_events: list[str],
) -> dict[str, object]:
    suffix = "" if text_mode == "ascii-hook" else f"_{text_mode}_{native_glyph_layout}_{native_raster_mode}"
    if fb_orientation:
        suffix += f"_{fb_orientation}"
    prefix = out_dir / f"hwemu_smoke_{case.name}{suffix}"
    cmd = [
        sys.executable,
        str(Path("reverse") / "hwemu" / "bbk9588_hwemu.py"),
        "--preset",
        "direct-bda-msgbox",
        "--launch-bda",
        f"{case.bda}@2",
        "--out-prefix",
        str(prefix),
        "--bda-text-mode",
        text_mode,
    ]
    if text_mode == "native":
        cmd += ["--bda-native-glyph-layout", native_glyph_layout]
        cmd += ["--bda-native-raster-mode", native_raster_mode]
    if fb_orientation is not None:
        cmd += ["--fb-orientation", fb_orientation]
    if bda_idle_stop_polls is not None:
        cmd += ["--bda-idle-stop-polls", str(bda_idle_stop_polls)]
    for event in bda_key_events:
        cmd += ["--bda-key-event", event]
    for event in bda_events:
        cmd += ["--bda-event", event]
    for event in bda_touch_events:
        cmd += ["--bda-touch-event", event]
    stdout_path = prefix.with_suffix(".stdout.txt")
    with stdout_path.open("w", encoding="utf-8") as stdout:
        proc = subprocess.run(
            cmd,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )

    json_path = prefix.with_suffix(".json")
    png_path = prefix.with_suffix(".png")
    row: dict[str, object] = {
        "name": case.name,
        "bda": str(case.bda),
        "command": cmd,
        "text_mode": text_mode,
        "native_glyph_layout": native_glyph_layout if text_mode == "native" else None,
        "native_raster_mode": native_raster_mode if text_mode == "native" else None,
        "bda_idle_stop_polls": bda_idle_stop_polls,
        "bda_key_events": bda_key_events,
        "bda_events": bda_events,
        "bda_touch_events": bda_touch_events,
        "returncode": proc.returncode,
        "json": str(json_path),
        "png": str(png_path),
        "stdout": str(stdout_path),
        "ok": False,
    }
    if proc.returncode != 0:
        row["error"] = f"emulator exited with {proc.returncode}"
        return row
    try:
        report = json.loads(json_path.read_text(encoding="utf-8"))
        execution = report["execution"]
    except Exception as exc:
        row["error"] = f"cannot parse JSON: {type(exc).__name__}: {exc}"
        return row

    text = glyph_text(execution.get("events", []))
    invalid_count = len(execution.get("invalid", []))
    framebuffer = execution.get("framebuffer") or {}
    watch = execution.get("watch") or {}
    row.update(
        {
            "stop_reason": execution.get("stop_reason"),
            "insn_count": execution.get("insn_count"),
            "last_pc": execution.get("last_pc"),
            "invalid_count": invalid_count,
            "glyph_text": text,
            "nonzero_pixels": framebuffer.get("nonzero_pixels"),
            "nonzero_bbox": framebuffer.get("nonzero_bbox"),
            "bda_event_poll_hits": watch.get("bda_event_poll_hits") if isinstance(watch, dict) else None,
            "bda_key_event_log": watch.get("bda_key_event_log") if isinstance(watch, dict) else None,
            "bda_event_log": watch.get("bda_event_log") if isinstance(watch, dict) else None,
            "bda_touch_event_log": watch.get("bda_touch_event_log") if isinstance(watch, dict) else None,
        }
    )
    failures = []
    if execution.get("stop_reason") != case.expected_stop:
        failures.append(f"stop_reason != {case.expected_stop}")
    if invalid_count != 0:
        failures.append("invalid memory accesses were recorded")
    if case.expected_text is not None and text != case.expected_text:
        failures.append(f"glyph text mismatch: {text!r}")
    if not framebuffer.get("nonzero_pixels"):
        failures.append("framebuffer has no nonzero pixels")
    row["ok"] = not failures
    if failures:
        row["failures"] = failures
    return row


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Run BBK9588 direct-BDA smoke regressions.")
    ap.add_argument("--case", choices=[case.name for case in DEFAULT_CASES], action="append")
    ap.add_argument("--out-dir", type=Path, default=Path("build"))
    ap.add_argument("--timeout", type=int, default=150)
    ap.add_argument("--text-mode", choices=["ascii-hook", "native"], default="ascii-hook")
    ap.add_argument(
        "--native-glyph-layout",
        default="rows-lsb-vscale2",
        choices=[
            "rows-msb-vscale2",
            "rows-lsb-vscale2",
            "rows-msb-vscale2-y0",
            "rows-lsb-vscale2-y0",
            "rows-msb-vscale2-x3",
            "rows-msb-vscale2-hscale2",
            "rows-lsb-vscale2-hscale2",
            "cols-msb-vscale2",
            "cols-lsb-vscale2",
            "cols-msb-vscale2-hscale2",
            "cols-lsb-vscale2-hscale2",
        ],
        help="Forwarded to bbk9588_hwemu.py in --text-mode native.",
    )
    ap.add_argument(
        "--native-raster-mode",
        default="firmware",
        choices=["firmware", "synth"],
        help="Forwarded to bbk9588_hwemu.py in --text-mode native.",
    )
    ap.add_argument(
        "--fb-orientation",
        choices=["raw", "rot180", "cw90", "ccw90", "hflip", "vflip"],
        help="Forwarded to bbk9588_hwemu.py.",
    )
    ap.add_argument(
        "--bda-key-event",
        action="append",
        default=[],
        help="Forwarded to bbk9588_hwemu.py, format code[:event_type]@event_hit.",
    )
    ap.add_argument(
        "--bda-event",
        action="append",
        default=[],
        help="Forwarded to bbk9588_hwemu.py, format event_type[:word0[:word2[:word3]]]@event_hit.",
    )
    ap.add_argument(
        "--bda-touch-event",
        action="append",
        default=[],
        help="Forwarded to bbk9588_hwemu.py, format x:y:down[:event_type]@event_hit.",
    )
    ap.add_argument(
        "--bda-idle-stop-polls",
        type=int,
        help="Forwarded to bbk9588_hwemu.py.",
    )
    ap.add_argument("--summary-json", type=Path, default=Path("build") / "hwemu_smoke_summary.json")
    ns = ap.parse_args(argv)

    ns.out_dir.mkdir(parents=True, exist_ok=True)
    selected = [case for case in DEFAULT_CASES if ns.case is None or case.name in ns.case]
    if ns.text_mode == "native":
        if ns.fb_orientation is None:
            ns.fb_orientation = "hflip"
        selected = [
            SmokeCase(name=case.name, bda=case.bda, expected_stop=case.expected_stop, expected_text=None)
            for case in selected
        ]
    rows = [
        run_case(
            case,
            ns.out_dir,
            ns.timeout,
            ns.text_mode,
            ns.native_glyph_layout,
            ns.native_raster_mode,
            ns.fb_orientation,
            ns.bda_idle_stop_polls,
            ns.bda_key_event,
            ns.bda_event,
            ns.bda_touch_event,
        )
        for case in selected
    ]
    summary = {"ok": all(row.get("ok") for row in rows), "cases": rows}
    ns.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for row in rows:
        status = "OK" if row.get("ok") else "FAIL"
        print(
            f"{status} {row['name']}: stop={row.get('stop_reason')} "
            f"invalid={row.get('invalid_count')} pixels={row.get('nonzero_pixels')} "
            f"text={row.get('glyph_text')!r}"
        )
        if row.get("failures"):
            for failure in row["failures"]:
                print(f"  - {failure}")
    print(f"summary: {ns.summary_json}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
