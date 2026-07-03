#!/usr/bin/env python3
"""Run raw-system BBK9588 main-menu interaction smoke checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


TRACE_PCS = [
    "0x8001a8fc",
    "0x8001ac40",
    "0x8000b3dc",
    "0x800dd380",
    "0x800e0d68",
    "0x8008f9a4",
    "0x8008fc50",
    "0x8008fd80",
    "0x800087c4",
    "0x800080f0",
    "0x800081a8",
    "0x800a7c18",
]


def find_c200() -> Path:
    matches = sorted(Path(".").rglob("C200.bin"))
    if not matches:
        raise FileNotFoundError("C200.bin not found under current workspace")
    return matches[0]


def run_hwemu(
    *,
    c200: Path,
    block_image: Path,
    nand_image: Path | None,
    no_block_image: bool,
    readonly_nand_page_ranges: list[str],
    clear_nand_overrides_page_ranges: list[str],
    state_in: Path,
    state_out: Path,
    json_out: Path,
    png_out: Path,
    timeout: int,
    max_seconds: int,
    steps: int,
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
        str(steps),
        "--fast-hooks",
        "--nand-loop-accelerator",
        "--idle-stop-hits",
        "60000",
        "--trace-limit",
        "2200",
        "--fb-width",
        "240",
        "--fb-height",
        "320",
        "--quiet",
    ]
    if no_block_image:
        cmd += ["--no-block-image"]
    else:
        cmd += ["--block-image", str(block_image)]
    if nand_image is not None:
        cmd += ["--nand-image", str(nand_image)]
    for page_range in readonly_nand_page_ranges:
        cmd += ["--readonly-nand-page-range", page_range]
    for page_range in clear_nand_overrides_page_ranges:
        cmd += ["--clear-nand-overrides-page-range", page_range]
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
    if proc.returncode != 0:
        row["error"] = f"emulator exited with {proc.returncode}"
        return row
    try:
        report = json.loads(json_out.read_text(encoding="utf-8"))
        row["execution"] = report["execution"]
    except Exception as exc:
        row["error"] = f"cannot parse JSON: {type(exc).__name__}: {exc}"
    return row


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def trace_count(execution: dict[str, object], pc: str) -> int:
    watch = execution.get("watch")
    if not isinstance(watch, dict):
        return 0
    trace_pc = watch.get("trace_pc")
    if not isinstance(trace_pc, dict):
        return 0
    counts = trace_pc.get("counts")
    if not isinstance(counts, dict):
        return 0
    value = counts.get(pc)
    return int(value) if value is not None else 0


def input_global(execution: dict[str, object], name: str) -> str | None:
    input_state = execution.get("input_state")
    if not isinstance(input_state, dict):
        return None
    globals_ = input_state.get("input_globals")
    if not isinstance(globals_, dict):
        return None
    value = globals_.get(name)
    return str(value) if value is not None else None


def block_image_snapshot(execution: dict[str, object]) -> dict[str, object]:
    mmio = execution.get("mmio_snapshot")
    if not isinstance(mmio, dict):
        return {}
    block = mmio.get("block_image")
    return block if isinstance(block, dict) else {}


def surface_snapshot(execution: dict[str, object]) -> dict[str, object]:
    mmio = execution.get("mmio_snapshot")
    if not isinstance(mmio, dict):
        return {}
    surface = mmio.get("surface")
    if isinstance(surface, dict):
        return surface
    return {
        "setpixel_accel_count": mmio.get("surface_setpixel_accel_count", 0),
        "hline_accel_count": mmio.get("surface_hline_accel_count", 0),
        "color_span_accel_count": mmio.get("surface_color_span_accel_count", 0),
        "read_span_accel_count": mmio.get("surface_read_span_accel_count", 0),
        "block_read_accel_count": mmio.get("surface_block_read_accel_count", 0),
        "block_write_accel_count": mmio.get("surface_block_write_accel_count", 0),
        "pixel_read_count": mmio.get("surface_pixel_read_count", 0),
    }


def surface_count(surface: dict[str, object], key: str) -> int:
    value = surface.get(key)
    return int(value) if isinstance(value, int) else 0


def validate_surface_activity(
    execution: dict[str, object],
    failures: list[str],
    phase: str,
    *,
    require_draw: bool,
) -> None:
    surface = surface_snapshot(execution)
    setpixel_count = surface_count(surface, "setpixel_accel_count")
    color_span_count = surface_count(surface, "color_span_accel_count")
    event_count = surface_count(surface, "event_count")
    if not require_draw and event_count == 0:
        return
    require(setpixel_count + color_span_count > 0, failures, f"{phase} did not exercise surface draw path")
    if event_count:
        require(event_count >= setpixel_count + color_span_count, failures, f"{phase} surface event count is inconsistent")
        by_mode = surface.get("recent_events_by_mode")
        require(isinstance(by_mode, dict), failures, f"{phase} surface per-mode trace is missing")
        if isinstance(by_mode, dict):
            setpixel_events = by_mode.get("setpixel")
            color_span_events = by_mode.get("color-span")
            require(
                (isinstance(setpixel_events, list) and len(setpixel_events) > 0)
                or (isinstance(color_span_events, list) and len(color_span_events) > 0),
                failures,
                f"{phase} surface per-mode trace has no draw events",
            )


def compact_surface(execution: dict[str, object]) -> dict[str, object]:
    surface = surface_snapshot(execution)
    by_mode = surface.get("recent_events_by_mode")
    mode_counts: dict[str, int] = {}
    if isinstance(by_mode, dict):
        for mode, events in by_mode.items():
            mode_counts[str(mode)] = len(events) if isinstance(events, list) else 0
    return {
        "setpixel": surface_count(surface, "setpixel_accel_count"),
        "hline": surface_count(surface, "hline_accel_count"),
        "color_span": surface_count(surface, "color_span_accel_count"),
        "read_span": surface_count(surface, "read_span_accel_count"),
        "block_read": surface_count(surface, "block_read_accel_count"),
        "block_write": surface_count(surface, "block_write_accel_count"),
        "pixel_read": surface_count(surface, "pixel_read_count"),
        "event_count": surface_count(surface, "event_count"),
        "recent_by_mode_counts": mode_counts,
    }


def compact_input(execution: dict[str, object]) -> dict[str, object]:
    input_state = execution.get("input_state")
    if not isinstance(input_state, dict):
        return {}
    return {
        "input_globals": input_state.get("input_globals", {}),
        "active_node_summary": input_state.get("active_node_summary", []),
        "key_table_nonzero": input_state.get("key_table_nonzero", []),
    }


def validate_press(row: dict[str, object], expect_no_block: bool) -> list[str]:
    failures: list[str] = []
    execution = row.get("execution")
    if not isinstance(execution, dict):
        return [str(row.get("error", "missing execution report"))]
    framebuffer = execution.get("framebuffer") if isinstance(execution.get("framebuffer"), dict) else {}
    require(row.get("returncode") == 0, failures, "press emulator command failed")
    require(len(execution.get("invalid", [])) == 0, failures, "press recorded invalid accesses")
    require(trace_count(execution, "0x8001a8fc") >= 1, failures, "press did not reach touch IRQ path")
    require(trace_count(execution, "0x8001ac40") >= 1, failures, "press did not reach SADC coordinate sampler")
    require(trace_count(execution, "0x8000b3dc") >= 1, failures, "press did not post GUI/input queue event")
    require(trace_count(execution, "0x800dd380") >= 1, failures, "press did not reach GUI dispatch")
    require(input_global(execution, "touch_flag_8048dd04") == "0x00000001", failures, "press did not leave touch-down flag set")
    require(int(framebuffer.get("nonzero_pixels") or 0) > 20000, failures, "press framebuffer is unexpectedly sparse")
    require(Path(str(row.get("png"))).is_file(), failures, "press PNG was not written")
    validate_surface_activity(execution, failures, "press", require_draw=True)
    if expect_no_block:
        block = block_image_snapshot(execution)
        require(block.get("image") is None, failures, "press unexpectedly used block image hook")
        require(not block.get("recent_events"), failures, "press recorded block hook events")
    return failures


def validate_release(row: dict[str, object], strict_hash: str | None, expect_no_block: bool) -> list[str]:
    failures: list[str] = []
    execution = row.get("execution")
    if not isinstance(execution, dict):
        return [str(row.get("error", "missing execution report"))]
    framebuffer = execution.get("framebuffer") if isinstance(execution.get("framebuffer"), dict) else {}
    png = Path(str(row.get("png")))
    require(row.get("returncode") == 0, failures, "release emulator command failed")
    require(len(execution.get("invalid", [])) == 0, failures, "release recorded invalid accesses")
    require(trace_count(execution, "0x800087c4") >= 100, failures, "release did not keep timer tick path active")
    require(trace_count(execution, "0x800080f0") >= 100, failures, "release did not keep scheduler dispatch active")
    require(trace_count(execution, "0x800081a8") >= 1, failures, "release did not switch tasks after menu event")
    require(input_global(execution, "touch_flag_8048dd00") == "0x00000001", failures, "release did not set touch-release flag")
    require(input_global(execution, "touch_flag_8048dd04") == "0x00000000", failures, "release left touch-down flag set")
    require(int(framebuffer.get("nonzero_pixels") or 0) > 20000, failures, "release framebuffer is unexpectedly sparse")
    require(int(framebuffer.get("unique_pixel_values") or 0) > 500, failures, "release framebuffer has too few colors")
    require(png.is_file(), failures, "release PNG was not written")
    validate_surface_activity(execution, failures, "release", require_draw=False)
    if expect_no_block:
        block = block_image_snapshot(execution)
        require(block.get("image") is None, failures, "release unexpectedly used block image hook")
        require(not block.get("recent_events"), failures, "release recorded block hook events")
    if strict_hash and png.is_file():
        digest = hashlib.sha256(png.read_bytes()).hexdigest().lower()
        require(digest == strict_hash.lower(), failures, f"release PNG hash mismatch: {digest}")
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run raw-system BBK9588 menu touch smoke regression.")
    ap.add_argument("--state-in", type=Path, default=Path("build") / "c200_searching_schedfix.pkl")
    ap.add_argument("--block-image", type=Path, default=Path("build") / "bbk9588_fs_fat16.img")
    ap.add_argument("--nand-image", type=Path)
    ap.add_argument("--no-block-image", action="store_true")
    ap.add_argument("--readonly-nand-page-range", action="append", default=[])
    ap.add_argument("--clear-nand-overrides-page-range", action="append", default=[])
    ap.add_argument("--out-dir", type=Path, default=Path("build"))
    ap.add_argument("--prefix", default="hwemu_system_menu")
    ap.add_argument("--timeout", type=int, default=140)
    ap.add_argument("--max-seconds", type=int, default=90)
    ap.add_argument("--steps", type=int, default=100_000_000)
    ap.add_argument("--x", type=int, default=210)
    ap.add_argument("--y", type=int, default=287)
    ap.add_argument("--strict-release-png-sha256")
    args = ap.parse_args(argv)

    if not args.state_in.is_file():
        raise FileNotFoundError(f"state checkpoint not found: {args.state_in}")
    if not args.no_block_image and not args.block_image.is_file():
        raise FileNotFoundError(f"block image not found: {args.block_image}")
    if args.nand_image is not None and not args.nand_image.is_file():
        raise FileNotFoundError(f"NAND image not found: {args.nand_image}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    c200 = find_c200()

    press = run_hwemu(
        c200=c200,
        block_image=args.block_image,
        nand_image=args.nand_image,
        no_block_image=args.no_block_image,
        readonly_nand_page_ranges=args.readonly_nand_page_range,
        clear_nand_overrides_page_ranges=args.clear_nand_overrides_page_range,
        state_in=args.state_in,
        state_out=args.out_dir / f"{args.prefix}_press.pkl",
        json_out=args.out_dir / f"{args.prefix}_press.json",
        png_out=args.out_dir / f"{args.prefix}_press.png",
        timeout=args.timeout,
        max_seconds=args.max_seconds,
        steps=args.steps,
        event_args=["--touch-controller-event", f"{args.x}:{args.y}:1@1"],
    )
    press_failures = validate_press(press, args.no_block_image)

    release = run_hwemu(
        c200=c200,
        block_image=args.block_image,
        nand_image=args.nand_image,
        no_block_image=args.no_block_image,
        readonly_nand_page_ranges=args.readonly_nand_page_range,
        clear_nand_overrides_page_ranges=args.clear_nand_overrides_page_range,
        state_in=Path(str(press["state"])),
        state_out=args.out_dir / f"{args.prefix}_release.pkl",
        json_out=args.out_dir / f"{args.prefix}_release.json",
        png_out=args.out_dir / f"{args.prefix}_release.png",
        timeout=args.timeout,
        max_seconds=args.max_seconds,
        steps=args.steps,
        event_args=["--touch-state", f"{args.x}:{args.y}:0"],
    )
    release_failures = validate_release(release, args.strict_release_png_sha256, args.no_block_image)

    summary = {
        "ok": not press_failures and not release_failures,
        "state_in": str(args.state_in),
        "block_image": None if args.no_block_image else str(args.block_image),
        "nand_image": None if args.nand_image is None else str(args.nand_image),
        "no_block_image": args.no_block_image,
        "readonly_nand_page_ranges": args.readonly_nand_page_range,
        "clear_nand_overrides_page_ranges": args.clear_nand_overrides_page_range,
        "c200": str(c200),
        "touch": {"x": args.x, "y": args.y},
        "press": {
            **{k: v for k, v in press.items() if k != "execution"},
            "surface": compact_surface(press["execution"]) if isinstance(press.get("execution"), dict) else {},
            "input": compact_input(press["execution"]) if isinstance(press.get("execution"), dict) else {},
        },
        "release": {
            **{k: v for k, v in release.items() if k != "execution"},
            "surface": compact_surface(release["execution"]) if isinstance(release.get("execution"), dict) else {},
            "input": compact_input(release["execution"]) if isinstance(release.get("execution"), dict) else {},
        },
        "press_failures": press_failures,
        "release_failures": release_failures,
    }
    summary_path = args.out_dir / f"{args.prefix}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
