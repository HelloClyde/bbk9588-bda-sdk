#!/usr/bin/env python3
"""Close the C200 time-change dialog through modeled touchscreen events."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


TRACE_PCS = [
    "0x800ca8c0",
    "0x800cad20",
    "0x800cee94",
    "0x800d099c",
    "0x800dced0",
    "0x800dd380",
    "0x800e0d68",
]


def find_c200() -> Path:
    matches = sorted(Path(".").rglob("C200.bin"))
    if not matches:
        raise FileNotFoundError("C200.bin not found under current workspace")
    return matches[0]


def run_hwemu(
    *,
    c200: Path,
    state_in: Path,
    state_out: Path,
    json_out: Path,
    png_out: Path,
    nand_image: Path,
    timeout: int,
    max_seconds: int,
    event_args: list[str],
) -> dict[str, object]:
    cmd = [
        sys.executable,
        str(Path("reverse") / "hwemu" / "bbk9588_hwemu.py"),
        "--profile",
        "bbk9588-uboot",
        "--image",
        str(c200),
        "--base",
        "0x80004000",
        "--pc",
        "0x80004000",
        "--ram-mb",
        "160",
        "--state-in",
        str(state_in),
        "--state-out",
        str(state_out),
        "--json-out",
        str(json_out),
        "--fb-dump",
        str(png_out),
        "--max-seconds",
        str(max_seconds),
        "--steps",
        "140000000",
        "--fast-hooks",
        "--nand-loop-accelerator",
        "--resource-cache16-accelerator",
        "--scheduler-tick-clamp",
        "--idle-stop-hits",
        "30000",
        "--no-block-image",
        "--nand-image",
        str(nand_image),
        "--readonly-nand-page-range",
        "0x1c40:0x21c40",
        "--clear-nand-overrides-page-range",
        "0x1c40:0x21c40",
        "--trace-limit",
        "12000",
        "--fb-width",
        "240",
        "--fb-height",
        "320",
        "--quiet",
    ]
    for pc in TRACE_PCS:
        cmd += ["--trace-pc", pc]
    cmd += event_args

    stdout_path = json_out.with_suffix(".stdout.txt")
    with stdout_path.open("w", encoding="utf-8") as stdout:
        proc = subprocess.run(cmd, stdout=stdout, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    row: dict[str, object] = {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": str(stdout_path),
        "json": str(json_out),
        "png": str(png_out),
        "state": str(state_out),
    }
    if proc.returncode == 0 and json_out.is_file():
        row["execution"] = json.loads(json_out.read_text(encoding="utf-8"))
    return row


def trace_count(row: dict[str, object], pc: str) -> int:
    execution = row.get("execution")
    if not isinstance(execution, dict):
        return 0
    counts = execution.get("execution", {}).get("watch", {}).get("trace_pc", {}).get("counts", {})
    return int(counts.get(pc, 0))


def input_global(row: dict[str, object], name: str) -> str | None:
    execution = row.get("execution")
    if not isinstance(execution, dict):
        return None
    return (
        execution.get("execution", {})
        .get("input_state", {})
        .get("input_globals", {})
        .get(name)
    )


def framebuffer_pixels(row: dict[str, object]) -> int:
    execution = row.get("execution")
    if not isinstance(execution, dict):
        return 0
    return int(execution.get("execution", {}).get("framebuffer", {}).get("nonzero_pixels") or 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Close the C200 time-change dialog and verify menu entry.")
    ap.add_argument("--state-in", type=Path, default=Path("build") / "c200_after_freefat_root256.pkl")
    ap.add_argument("--nand-image", type=Path, default=Path("build") / "bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin")
    ap.add_argument("--out-dir", type=Path, default=Path("build"))
    ap.add_argument("--prefix", default="hwemu_time_dialog_to_menu")
    ap.add_argument("--timeout", type=int, default=150)
    ap.add_argument("--max-seconds", type=int, default=80)
    ap.add_argument("--x", type=int, default=150)
    ap.add_argument("--y", type=int, default=205)
    ap.add_argument("--stale-touch-x", type=int, default=10)
    ap.add_argument("--stale-touch-y", type=int, default=310)
    args = ap.parse_args(argv)

    if not args.state_in.is_file():
        raise FileNotFoundError(args.state_in)
    if not args.nand_image.is_file():
        raise FileNotFoundError(args.nand_image)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    c200 = find_c200()

    press = run_hwemu(
        c200=c200,
        state_in=args.state_in,
        state_out=args.out_dir / f"{args.prefix}_press.pkl",
        json_out=args.out_dir / f"{args.prefix}_press.json",
        png_out=args.out_dir / f"{args.prefix}_press.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=args.max_seconds,
        event_args=[
            "--touch-controller-event",
            f"{args.stale_touch_x}:{args.stale_touch_y}:0@1",
            "--touch-controller-event",
            f"{args.x}:{args.y}:1@20",
        ],
    )
    release = run_hwemu(
        c200=c200,
        state_in=Path(str(press["state"])),
        state_out=args.out_dir / f"{args.prefix}_release.pkl",
        json_out=args.out_dir / f"{args.prefix}_release.json",
        png_out=args.out_dir / f"{args.prefix}_release.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=args.max_seconds,
        event_args=["--touch-state", f"{args.x}:{args.y}:0"],
    )

    failures: list[str] = []
    if press.get("returncode") != 0:
        failures.append("press phase failed")
    if release.get("returncode") != 0:
        failures.append("release phase failed")
    if trace_count(press, "0x800e0d68") < 3:
        failures.append("press phase did not reach dialog press/highlight handling")
    if input_global(release, "touch_flag_8048dd04") != "0x00000000":
        failures.append("release phase left touch-down flag set")
    if framebuffer_pixels(release) < 20000:
        failures.append("release framebuffer does not look like the main menu")

    summary = {
        "ok": not failures,
        "state_in": str(args.state_in),
        "nand_image": str(args.nand_image),
        "stale_touch_release": {"x": args.stale_touch_x, "y": args.stale_touch_y},
        "touch": {"x": args.x, "y": args.y},
        "press": {k: v for k, v in press.items() if k != "execution"},
        "release": {k: v for k, v in release.items() if k != "execution"},
        "failures": failures,
    }
    summary_path = args.out_dir / f"{args.prefix}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
