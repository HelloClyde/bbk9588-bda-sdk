#!/usr/bin/env python3
"""Run C200 from raw image/NAND through calibration and the time dialog."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


BOOT_TRACE_PCS = [
    "0x8001e900",
    "0x80172840",
    "0x8017d3b0",
]

DIALOG_TRACE_PCS = [
    "0x800ca8c0",
    "0x800cad20",
    "0x800cee94",
    "0x800d099c",
    "0x800dced0",
    "0x800dd380",
    "0x800e0d68",
    "0x800087c4",
    "0x800080f0",
    "0x800081a8",
    "0x8005bcd4",
]


def find_c200() -> Path:
    matches = sorted(Path(".").rglob("C200.bin"))
    if not matches:
        raise FileNotFoundError("C200.bin not found under current workspace")
    return matches[0]


def run_cmd(cmd: list[str], stdout_path: Path, timeout: int) -> int:
    with stdout_path.open("w", encoding="utf-8") as stdout:
        proc = subprocess.run(cmd, stdout=stdout, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    return proc.returncode


def run_hwemu(
    *,
    c200: Path,
    state_in: Path | None,
    state_out: Path,
    json_out: Path,
    png_out: Path,
    nand_image: Path,
    timeout: int,
    max_seconds: int,
    trace_pcs: list[str],
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
        "--state-out",
        str(state_out),
        "--json-out",
        str(json_out),
        "--fb-dump",
        str(png_out),
        "--max-seconds",
        str(max_seconds),
        "--steps",
        "180000000",
        "--fast-hooks",
        "--nand-loop-accelerator",
        "--resource-cache16-accelerator",
        "--idle-stop-hits",
        "30000",
        "--no-block-image",
        "--nand-image",
        str(nand_image),
        "--trace-limit",
        "12000",
        "--fb-width",
        "240",
        "--fb-height",
        "320",
        "--quiet",
    ]
    if state_in is not None:
        cmd += ["--state-in", str(state_in)]
    for pc in trace_pcs:
        cmd += ["--trace-pc", pc]
    cmd += event_args

    stdout_path = json_out.with_suffix(".stdout.txt")
    returncode = run_cmd(cmd, stdout_path, timeout)
    row: dict[str, object] = {
        "command": cmd,
        "returncode": returncode,
        "stdout": str(stdout_path),
        "json": str(json_out),
        "png": str(png_out),
        "state": str(state_out),
    }
    if returncode == 0 and json_out.is_file():
        row["execution"] = json.loads(json_out.read_text(encoding="utf-8"))
    return row


def trace_count(row: dict[str, object], pc: str) -> int:
    execution = row.get("execution")
    if not isinstance(execution, dict):
        return 0
    return int(
        execution.get("execution", {})
        .get("watch", {})
        .get("trace_pc", {})
        .get("counts", {})
        .get(pc, 0)
    )


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


def framebuffer(row: dict[str, object]) -> dict[str, object]:
    execution = row.get("execution")
    if not isinstance(execution, dict):
        return {}
    fb = execution.get("execution", {}).get("framebuffer", {})
    return fb if isinstance(fb, dict) else {}


def execution_payload(row: dict[str, object]) -> dict[str, object]:
    execution = row.get("execution")
    if not isinstance(execution, dict):
        return {}
    payload = execution.get("execution")
    return payload if isinstance(payload, dict) else {}


def surface_count(surface: dict[str, object], key: str) -> int:
    value = surface.get(key)
    return int(value) if isinstance(value, int) else 0


def compact_runtime(row: dict[str, object]) -> dict[str, object]:
    payload = execution_payload(row)
    if not payload:
        return {}
    regs = payload.get("regs") if isinstance(payload.get("regs"), dict) else {}
    mmio = payload.get("mmio_snapshot") if isinstance(payload.get("mmio_snapshot"), dict) else {}
    touch = mmio.get("touch_controller") if isinstance(mmio.get("touch_controller"), dict) else {}
    surface = mmio.get("surface") if isinstance(mmio.get("surface"), dict) else {}
    watch = payload.get("watch") if isinstance(payload.get("watch"), dict) else {}
    trace_pc = watch.get("trace_pc") if isinstance(watch.get("trace_pc"), dict) else {}
    trace_counts = trace_pc.get("counts", {})
    if not isinstance(trace_counts, dict):
        trace_counts = {}
    return {
        "stop_reason": payload.get("stop_reason"),
        "pc": regs.get("pc"),
        "invalid_count": len(payload.get("invalid", [])) if isinstance(payload.get("invalid"), list) else 0,
        "framebuffer": {
            "nonzero_pixels": framebuffer(row).get("nonzero_pixels"),
            "unique_pixel_values": framebuffer(row).get("unique_pixel_values"),
        },
        "touch_controller": {
            "x": touch.get("x"),
            "y": touch.get("y"),
            "down": touch.get("down"),
            "controller_poll_hits": touch.get("controller_poll_hits"),
            "sadc_status_event": touch.get("sadc_status_event"),
            "sadc_conversion_events_remaining": touch.get("sadc_conversion_events_remaining"),
        },
        "trace_counts": {str(k): int(v) for k, v in trace_counts.items()},
        "surface": {
            "setpixel": surface_count(surface, "setpixel_accel_count"),
            "pixel_read": surface_count(surface, "pixel_read_count"),
            "event_count": surface_count(surface, "event_count"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Boot C200 from raw NAND and close the time dialog.")
    ap.add_argument("--nand-image", type=Path, default=Path("build") / "bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin")
    ap.add_argument("--out-dir", type=Path, default=Path("build"))
    ap.add_argument("--prefix", default="hwemu_cold_boot_to_menu")
    ap.add_argument("--timeout", type=int, default=190)
    ap.add_argument("--boot-max-seconds", type=int, default=120)
    ap.add_argument("--dialog-max-seconds", type=int, default=80)
    ap.add_argument("--x", type=int, default=180)
    ap.add_argument("--y", type=int, default=220)
    args = ap.parse_args(argv)

    if not args.nand_image.is_file():
        raise FileNotFoundError(args.nand_image)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    c200 = find_c200()

    boot = run_hwemu(
        c200=c200,
        state_in=None,
        state_out=args.out_dir / f"{args.prefix}_calib_left.pkl",
        json_out=args.out_dir / f"{args.prefix}_calib_left.json",
        png_out=args.out_dir / f"{args.prefix}_calib_left.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=args.boot_max_seconds,
        trace_pcs=BOOT_TRACE_PCS,
        event_args=[],
    )
    left_press = run_hwemu(
        c200=c200,
        state_in=Path(str(boot["state"])),
        state_out=args.out_dir / f"{args.prefix}_calib_left_press.pkl",
        json_out=args.out_dir / f"{args.prefix}_calib_left_press.json",
        png_out=args.out_dir / f"{args.prefix}_calib_left_press.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=40,
        trace_pcs=BOOT_TRACE_PCS,
        event_args=["--touch-state", "10:10:1"],
    )
    left_release = run_hwemu(
        c200=c200,
        state_in=Path(str(left_press["state"])),
        state_out=args.out_dir / f"{args.prefix}_calib_left_release.pkl",
        json_out=args.out_dir / f"{args.prefix}_calib_left_release.json",
        png_out=args.out_dir / f"{args.prefix}_calib_left_release.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=40,
        trace_pcs=BOOT_TRACE_PCS,
        event_args=["--touch-state", "10:10:0"],
    )
    right_press = run_hwemu(
        c200=c200,
        state_in=Path(str(left_release["state"])),
        state_out=args.out_dir / f"{args.prefix}_calib_right_press.pkl",
        json_out=args.out_dir / f"{args.prefix}_calib_right_press.json",
        png_out=args.out_dir / f"{args.prefix}_calib_right_press.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=50,
        trace_pcs=BOOT_TRACE_PCS,
        event_args=["--touch-state", "229:10:1"],
    )
    right_release = run_hwemu(
        c200=c200,
        state_in=Path(str(right_press["state"])),
        state_out=args.out_dir / f"{args.prefix}_calib_right_release.pkl",
        json_out=args.out_dir / f"{args.prefix}_calib_right_release.json",
        png_out=args.out_dir / f"{args.prefix}_calib_right_release.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=80,
        trace_pcs=DIALOG_TRACE_PCS,
        event_args=["--touch-state", "229:10:0"],
    )
    dialog = run_hwemu(
        c200=c200,
        state_in=Path(str(right_release["state"])),
        state_out=args.out_dir / f"{args.prefix}_dialog.pkl",
        json_out=args.out_dir / f"{args.prefix}_dialog.json",
        png_out=args.out_dir / f"{args.prefix}_dialog.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=args.boot_max_seconds,
        trace_pcs=DIALOG_TRACE_PCS,
        event_args=[],
    )
    press = run_hwemu(
        c200=c200,
        state_in=Path(str(dialog["state"])),
        state_out=args.out_dir / f"{args.prefix}_press.pkl",
        json_out=args.out_dir / f"{args.prefix}_press.json",
        png_out=args.out_dir / f"{args.prefix}_press.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=args.dialog_max_seconds,
        trace_pcs=DIALOG_TRACE_PCS,
        event_args=[
            "--touch-controller-event",
            "229:10:0@1",
            "--touch-controller-event",
            f"{args.x}:{args.y}:1@20",
        ],
    )
    release = run_hwemu(
        c200=c200,
        state_in=Path(str(press["state"])),
        state_out=args.out_dir / f"{args.prefix}_menu.pkl",
        json_out=args.out_dir / f"{args.prefix}_menu.json",
        png_out=args.out_dir / f"{args.prefix}_menu.png",
        nand_image=args.nand_image,
        timeout=args.timeout,
        max_seconds=args.dialog_max_seconds,
        trace_pcs=DIALOG_TRACE_PCS,
        event_args=["--touch-state", f"{args.x}:{args.y}:0"],
    )

    failures: list[str] = []
    if boot.get("returncode") != 0:
        failures.append("boot phase failed")
    if left_press.get("returncode") != 0:
        failures.append("left calibration press phase failed")
    if left_release.get("returncode") != 0:
        failures.append("left calibration release phase failed")
    if right_press.get("returncode") != 0:
        failures.append("right calibration press phase failed")
    if right_release.get("returncode") != 0:
        failures.append("right calibration release phase failed")
    if dialog.get("returncode") != 0:
        failures.append("dialog wait phase failed")
    if press.get("returncode") != 0:
        failures.append("press phase failed")
    if release.get("returncode") != 0:
        failures.append("release phase failed")
    boot_fb = framebuffer(boot)
    dialog_fb = framebuffer(dialog)
    release_fb = framebuffer(release)
    boot_execution = boot.get("execution")
    boot_pc = ""
    if isinstance(boot_execution, dict):
        boot_pc = str(boot_execution.get("execution", {}).get("regs", {}).get("pc", ""))
    if boot_pc in {"0x8000403c", "0x80004074", "0x80004078"}:
        failures.append("boot phase stayed in C200 reset init loop")
    if int(dialog_fb.get("nonzero_pixels") or 0) < 10000:
        failures.append("dialog framebuffer does not look like the time dialog")
    if trace_count(press, "0x800e0d68") < 3:
        failures.append("press phase did not reach dialog button handling")
    if input_global(release, "touch_flag_8048dd04") != "0x00000000":
        failures.append("release phase left touch-down flag set")
    if int(release_fb.get("nonzero_pixels") or 0) < 20000:
        failures.append("release framebuffer does not look like the main menu")

    release_runtime = compact_runtime(release)
    release_trace = release_runtime.get("trace_counts", {})
    if not isinstance(release_trace, dict):
        release_trace = {}
    menu_checkpoint_ready = (
        release_runtime.get("pc") == "0x80008a84"
        or int(release_trace.get("0x800080f0", 0)) > 0
        or int(release_trace.get("0x8005bcd4", 0)) > 0
    )

    summary = {
        "ok": not failures,
        "nand_image": str(args.nand_image),
        "touch": {"x": args.x, "y": args.y},
        "menu_checkpoint_ready_for_hardware_input": menu_checkpoint_ready,
        "boot": {**{k: v for k, v in boot.items() if k != "execution"}, "runtime": compact_runtime(boot)},
        "left_press": {**{k: v for k, v in left_press.items() if k != "execution"}, "runtime": compact_runtime(left_press)},
        "left_release": {**{k: v for k, v in left_release.items() if k != "execution"}, "runtime": compact_runtime(left_release)},
        "right_press": {**{k: v for k, v in right_press.items() if k != "execution"}, "runtime": compact_runtime(right_press)},
        "right_release": {**{k: v for k, v in right_release.items() if k != "execution"}, "runtime": compact_runtime(right_release)},
        "dialog": {**{k: v for k, v in dialog.items() if k != "execution"}, "runtime": compact_runtime(dialog)},
        "press": {**{k: v for k, v in press.items() if k != "execution"}, "runtime": compact_runtime(press)},
        "release": {**{k: v for k, v in release.items() if k != "execution"}, "runtime": release_runtime},
        "failures": failures,
    }
    summary_path = args.out_dir / f"{args.prefix}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
