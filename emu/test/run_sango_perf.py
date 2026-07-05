#!/usr/bin/env python3
"""Reproducible probes for 三国霸业 under 娱乐天地."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from emu.test.run_frontend_web_smoke import BUILD


ROOT = Path(__file__).resolve().parents[2]
RUN_PERF = ROOT / "emu" / "test" / "run_perf_paths.py"
ENTWORLD_CHECKPOINT = BUILD / "sango_entworld_checkpoint.pkl"
AFTER_LAUNCH_CHECKPOINT = BUILD / "sango_after_launch_checkpoint.pkl"


def action_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def run_perf(args: list[str]) -> int:
    cmd = [sys.executable, str(RUN_PERF), *args]
    return subprocess.call(cmd, cwd=ROOT)


def common(ns: argparse.Namespace, prefix: str) -> list[str]:
    args = ["--out-dir", str(ns.out_dir), "--prefix", prefix]
    if ns.hot_path_stats:
        args.append("--hot-path-stats")
    if ns.scheduler_tick_clamp:
        args.append("--scheduler-tick-clamp")
    if ns.completed_step_timer:
        args.append("--completed-step-timer")
    args += ["--worker-slice-seconds", str(ns.worker_slice_seconds)]
    args += ["--run-internal-chunk-steps", str(ns.run_internal_chunk_steps)]
    return args


def phase_entworld(ns: argparse.Namespace) -> int:
    return run_perf(
        [
            "--case",
            "tap-sequence",
            "--boot-timeout",
            str(ns.boot_timeout),
            *common(ns, ns.prefix or "sango_entworld"),
            "--action",
            "key:dismiss_pet:10:0.5",
            "--action",
            "run:after_dismiss:1.5",
            "--action",
            "tap:entertainment:168:286:0.2",
            "--action",
            "run:wait_entertainment:2.5",
            "--action",
            "tap:ent_world_icon:120:72:0.2",
            "--action",
            "run:wait_entworld_select:1.0",
            "--action",
            "tap:play_toolbar:82:306:0.2",
            "--action",
            "run:wait_entworld_open:4.0",
            "--action",
            f"save:entworld_checkpoint:{action_path(ENTWORLD_CHECKPOINT)}:0.1",
        ]
    )


def phase_launch(ns: argparse.Namespace) -> int:
    state_in = ns.state_in or ENTWORLD_CHECKPOINT
    return run_perf(
        [
            "--case",
            "tap-sequence",
            "--state-in",
            str(state_in),
            *common(ns, ns.prefix or "sango_launch"),
            "--action",
            "tap:select_sango:45:170:0.2",
            "--action",
            "run:wait_select:1.0",
            "--action",
            "tap:play_toolbar:82:306:0.2",
            "--action",
            f"run:wait_loading_or_menu:{ns.seconds}",
            "--action",
            f"save:after_launch_checkpoint:{action_path(AFTER_LAUNCH_CHECKPOINT)}:0.1",
        ]
    )


def phase_loading(ns: argparse.Namespace) -> int:
    state_in = ns.state_in or AFTER_LAUNCH_CHECKPOINT
    return run_perf(
        [
            "--case",
            "tap-sequence",
            "--state-in",
            str(state_in),
            *common(ns, ns.prefix or "sango_loading"),
            "--action",
            f"run:loading:{ns.seconds}",
            "--action",
            f"save:loading_after:{action_path(ns.out_dir / 'sango_loading_after_checkpoint.pkl')}:0.1",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run fixed 三国霸业 performance probes.")
    ap.add_argument("--phase", choices=["entworld", "launch", "loading"], required=True)
    ap.add_argument("--out-dir", type=Path, default=BUILD)
    ap.add_argument("--prefix", default="")
    ap.add_argument("--state-in", type=Path)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--boot-timeout", type=int, default=240)
    ap.add_argument("--hot-path-stats", action="store_true", default=True)
    ap.add_argument("--no-hot-path-stats", dest="hot_path_stats", action="store_false")
    ap.add_argument("--scheduler-tick-clamp", action="store_true", default=False)
    ap.add_argument("--completed-step-timer", action="store_true", default=False)
    ap.add_argument("--worker-slice-seconds", type=float, default=0.1)
    ap.add_argument("--run-internal-chunk-steps", type=int, default=500000)
    ns = ap.parse_args(argv)
    ns.out_dir.mkdir(parents=True, exist_ok=True)
    if ns.phase == "entworld":
        return phase_entworld(ns)
    if ns.phase == "launch":
        return phase_launch(ns)
    return phase_loading(ns)


if __name__ == "__main__":
    raise SystemExit(main())
