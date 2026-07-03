#!/usr/bin/env python3
"""Command-line interface for the BBK 9588 hardware emulator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from hwemu_framebuffer import dump_rgb565_framebuffer, scan_rgb565_framebuffers
from hwemu_utils import (
    access_to_dict,
    cli_option_provided,
    find_workspace_file,
    inspect_image,
    parse_bda_event,
    parse_bda_key_event,
    parse_bda_launch,
    parse_bda_touch_event,
    parse_firmware_key_sample,
    parse_gui_key_event,
    parse_gui_touch_event,
    parse_key_pulse,
    parse_key_controller_event,
    parse_mmio_level,
    parse_mmio_pulse,
    parse_page_range,
    parse_scheduled_call,
    parse_scheduled_poke,
    parse_stop_input_node,
    parse_touch_controller_event,
    parse_touch_sample,
    parse_touch_state,
    parse_watch_range,
)


def apply_preset(ns: argparse.Namespace, argv: list[str]) -> None:
    if ns.preset is None:
        return
    if ns.preset != "direct-bda-msgbox":
        raise ValueError(f"unknown preset: {ns.preset}")

    ns.legacy_direct_bda = True
    if not cli_option_provided(argv, "--image"):
        ns.image = find_workspace_file("u_boot_9588_4740.bin")
    if not cli_option_provided(argv, "--base"):
        ns.base = 0x80900000
    if not cli_option_provided(argv, "--pc"):
        ns.pc = 0x80900000
    if not cli_option_provided(argv, "--ram-mb"):
        ns.ram_mb = 160
    if not cli_option_provided(argv, "--profile"):
        ns.profile = "bbk9588-uboot"
    if not cli_option_provided(argv, "--payload"):
        ns.payload = find_workspace_file("C200.bin")
    if not cli_option_provided(argv, "--payload-addr"):
        ns.payload_addr = 0x80004000
    if not cli_option_provided(argv, "--nand-image"):
        ns.nand_image = ns.payload
    if getattr(ns, "no_block_image", False):
        ns.block_image = None
    elif not cli_option_provided(argv, "--block-image"):
        ns.block_image = Path("build") / "bbk9588_fs_fat16.img"
    if not cli_option_provided(argv, "--steps"):
        ns.steps = 27_000_000
    if not cli_option_provided(argv, "--trace-limit"):
        ns.trace_limit = 6200
    if not cli_option_provided(argv, "--idle-stop-hits"):
        ns.idle_stop_hits = 0
    if not cli_option_provided(argv, "--app-idle-stop-hits"):
        ns.app_idle_stop_hits = 0
    if not cli_option_provided(argv, "--fb-addr"):
        ns.fb_addr = 0xA1F82000
    if not cli_option_provided(argv, "--fb-width"):
        ns.fb_width = 240
    if not cli_option_provided(argv, "--fb-height"):
        ns.fb_height = 320
    if not cli_option_provided(argv, "--bda-text-mode"):
        ns.bda_text_mode = "ascii-hook"
    if ns.bda_text_mode == "native" and not cli_option_provided(argv, "--bda-native-glyph-layout"):
        ns.bda_native_glyph_layout = "rows-lsb-vscale2"
    if not cli_option_provided(argv, "--fb-orientation"):
        ns.fb_orientation = "hflip" if ns.bda_text_mode == "native" else "rot180"
    if not ns.launch_bda:
        ns.launch_bda.append(parse_bda_launch(str(Path("build") / "calc_startup_msgbox_origtitle.bda") + "@2"))

    for spec in ("surfglobal=0x804a60c0:0x140", "shadow=0x80825b90:0x25800"):
        watch = parse_watch_range(spec)
        if all(existing.name != watch.name for existing in ns.watch_va):
            ns.watch_va.append(watch)

    for pc in (0x8012A6A8, 0x80119B50, 0x80119C90, 0x80119CC0, 0x8011A3C4, 0x8011AA1C, 0x8012C90C):
        if pc not in ns.trace_pc:
            ns.trace_pc.append(pc)

    no_json_out = getattr(ns, "no_json_out", False)
    if no_json_out:
        ns.json_out = None
    if ns.out_prefix is not None:
        if ns.json_out is None and not no_json_out:
            ns.json_out = ns.out_prefix.with_suffix(".json")
        if ns.fb_dump is None:
            ns.fb_dump = ns.out_prefix.with_suffix(".png")
    else:
        if ns.json_out is None and not no_json_out:
            ns.json_out = Path("build") / "hwemu_direct_bda_msgbox.json"
        if ns.fb_dump is None:
            ns.fb_dump = Path("build") / "hwemu_direct_bda_msgbox.png"


def validate_legacy_direct_bda(ns: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    legacy_options: list[str] = []
    if ns.launch_bda:
        legacy_options.append("--launch-bda")
    if ns.bda_key_event:
        legacy_options.append("--bda-key-event")
    if ns.bda_event:
        legacy_options.append("--bda-event")
    if ns.bda_touch_event:
        legacy_options.append("--bda-touch-event")
    if ns.bda_text_mode == "ascii-hook":
        legacy_options.append("--bda-text-mode ascii-hook")
    if ns.bda_native_raster_mode == "synth":
        legacy_options.append("--bda-native-raster-mode synth")
    if legacy_options and not ns.legacy_direct_bda:
        joined = ", ".join(legacy_options)
        parser.error(f"{joined} require --legacy-direct-bda; full-system mode does not run direct-BDA shims")


def main(argv: list[str], emulator_cls: type, unicorn_cls: object | None) -> int:
    ap = argparse.ArgumentParser(description="Trace-run BBK 9588 raw MIPS system images.")
    ap.add_argument(
        "--preset",
        choices=["direct-bda-msgbox"],
        help="Apply a known BBK9588 regression preset while allowing explicit CLI arguments to override it.",
    )
    ap.add_argument("--out-prefix", type=Path, help="Set default JSON/framebuffer outputs for a preset.")
    ap.add_argument("--image", type=Path, default=Path("系统") / "数据" / "C200.bin")
    ap.add_argument("--base", type=lambda x: int(x, 0), default=0x80000000)
    ap.add_argument("--pc", type=lambda x: int(x, 0), default=0x80000000)
    ap.add_argument("--ram-mb", type=int, default=32)
    ap.add_argument("--steps", type=int, default=100000)
    ap.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help="Stop execution after this many wall-clock seconds and still write the debug report.",
    )
    ap.add_argument("--trace-limit", type=int, default=256)
    ap.add_argument("--disasm-count", type=int, default=24)
    ap.add_argument("--no-recover-jr", action="store_true", help="Disable Unicorn jr-exception recovery.")
    ap.add_argument("--profile", default="none", choices=["none", "bbk9588-uboot"])
    ap.add_argument("--payload", type=Path, help="Optional second-stage image to pre-load into RAM.")
    ap.add_argument("--payload-addr", type=lambda x: int(x, 0), default=0x80004000)
    ap.add_argument("--nand-image", type=Path, help="Optional raw NAND image backing the external NAND data window.")
    ap.add_argument("--nand-page-size", type=int, default=2048)
    ap.add_argument("--nand-spare-size", type=int, default=64)
    ap.add_argument(
        "--readonly-nand-page-range",
        type=parse_page_range,
        action="append",
        default=[],
        help="Skip NAND program commits for a half-open page range start:end. Repeatable.",
    )
    ap.add_argument(
        "--clear-nand-overrides-page-range",
        type=parse_page_range,
        action="append",
        default=[],
        help="After loading a checkpoint, drop NAND page overrides in a half-open page range start:end. Repeatable.",
    )
    ap.add_argument(
        "--block-image",
        type=Path,
        help="Optional logical block device image served through C200's 0x80182bf4 read path.",
    )
    ap.add_argument(
        "--no-block-image",
        action="store_true",
        help="Disable the temporary C200 logical block-device hook and use the NAND/FTL path only.",
    )
    ap.add_argument(
        "--usb-connected",
        action="store_true",
        help="Model USB cable connected. Default is disconnected, so UDC status/interrupt reads stay idle.",
    )
    ap.add_argument(
        "--idle-stop-hits",
        type=int,
        default=256,
        help="Stop after this many hits at the C200 idle loop. Use 0 to disable.",
    )
    ap.add_argument(
        "--app-idle-stop-hits",
        type=int,
        default=0,
        help="Stop after this many hits at the observed app repaint loop at 0x800bd840. Use 0 to disable.",
    )
    ap.add_argument(
        "--bda-idle-stop-polls",
        type=int,
        default=1,
        help="Stop direct-BDA execution after this many empty BDA event polls once no scheduled BDA events remain.",
    )
    ap.add_argument(
        "--watch-va",
        type=parse_watch_range,
        action="append",
        default=[],
        help="Trace RAM reads/writes in a VA range, format addr:size or name=addr:size. Repeatable.",
    )
    ap.add_argument(
        "--trace-pc",
        type=lambda x: int(x, 0),
        action="append",
        default=[],
        help="Count and snapshot register state when execution reaches this virtual PC. Repeatable.",
    )
    ap.add_argument(
        "--stop-pc",
        type=lambda x: int(x, 0),
        action="append",
        default=[],
        help="Stop execution when this virtual PC is reached. Repeatable.",
    )
    ap.add_argument(
        "--stop-input-node",
        type=parse_stop_input_node,
        action="append",
        default=[],
        help="Stop when an input node matches va:callback:min_status_3c[@pc]. Repeatable.",
    )
    ap.add_argument(
        "--watch-input-state",
        action="store_true",
        help="Trace the observed C200 GUI/input state block at 0x80473f40.",
    )
    ap.add_argument(
        "--watch-input-nodes",
        action="store_true",
        help="Trace the observed C200 GUI/input node pool around 0x806c5000.",
    )
    ap.add_argument(
        "--poke-va",
        type=parse_scheduled_poke,
        action="append",
        default=[],
        help="Write RAM at an idle-loop hit, format addr:size:value[@idle_hit]. Repeatable.",
    )
    ap.add_argument(
        "--call-va",
        type=parse_scheduled_call,
        action="append",
        default=[],
        help="Call firmware code at an idle-loop hit, format addr[:a0[:a1[:a2[:a3]]]][@idle_hit]. Experimental.",
    )
    ap.add_argument(
        "--call-stack",
        type=lambda x: int(x, 0),
        default=None,
        help="Scratch stack pointer used by --call-va. Defaults near the top of emulated RAM.",
    )
    ap.add_argument(
        "--fw-key-sample",
        type=parse_firmware_key_sample,
        action="append",
        default=[],
        help=(
            "Run C200's key sampler at an idle-loop hit and force the next "
            "0x8001b464 scanner result, format code@idle_hit. Use code 0 for release."
        ),
    )
    ap.add_argument(
        "--touch-sample",
        type=parse_touch_sample,
        action="append",
        default=[],
        help=(
            "Run C200's touch sampler at an idle-loop hit and force pen state/coords, "
            "format x:y:down@idle_hit or x:y:down@pc:addr on the 240x320 portrait screen."
        ),
    )
    ap.add_argument(
        "--touch-state",
        type=parse_touch_state,
        action="append",
        default=[],
        help="Set the current emulated touch controller state before running, format x:y:down.",
    )
    ap.add_argument(
        "--touch-controller-event",
        type=parse_touch_controller_event,
        action="append",
        default=[],
        help="Set emulated touch controller state at an idle-loop hit, format x:y:down@idle_hit.",
    )
    ap.add_argument(
        "--key-controller-event",
        type=parse_key_controller_event,
        action="append",
        default=[],
        help="Set emulated physical key GPIO state at an idle-loop hit, format code:down@idle_hit.",
    )
    ap.add_argument(
        "--launch-bda",
        type=parse_bda_launch,
        action="append",
        default=[],
        help=(
            "Load a native BDA tail to 0x81c00020 and jump to it at an idle-loop hit, "
            "format path[@idle_hit]. Diagnostic path toward full app launching."
        ),
    )
    ap.add_argument(
        "--legacy-direct-bda",
        action="store_true",
        help=(
            "Enable the legacy direct-BDA diagnostic path. Full-system mode "
            "keeps this off so BDA event/font/runtime shims cannot affect apps "
            "started by the real firmware loader."
        ),
    )
    ap.add_argument(
        "--gui-key-event",
        type=parse_gui_key_event,
        action="append",
        default=[],
        help=(
            "Mark the C200 GUI key-table node for a key code as pending at an "
            "idle-loop hit, format code@idle_hit. Experimental."
        ),
    )
    ap.add_argument(
        "--gui-touch-event",
        type=parse_gui_touch_event,
        action="append",
        default=[],
        help=(
            "Send a screen-coordinate touch event to the current C200 active GUI object, "
            "format x:y:down@idle_hit. Use with --gui-ring-pump for modal follow-up events."
        ),
    )
    ap.add_argument(
        "--gui-ring-pump",
        action="store_true",
        help="Consume pending C200 GUI ring records at idle through the firmware 0x800dd4b8 dispatcher.",
    )
    ap.add_argument(
        "--bda-key-event",
        type=parse_bda_key_event,
        action="append",
        default=[],
        help=(
            "Inject a key-like event into the direct-BDA event loop, "
            "format code[:event_type]@event_hit. Event type 9 is key down; 10 is key up."
        ),
    )
    ap.add_argument(
        "--bda-event",
        type=parse_bda_event,
        action="append",
        default=[],
        help=(
            "Inject a raw event into the direct-BDA event loop, "
            "format event_type[:word0[:word2[:word3]]]@event_hit."
        ),
    )
    ap.add_argument(
        "--bda-touch-event",
        type=parse_bda_touch_event,
        action="append",
        default=[],
        help=(
            "Inject a touch event into the direct-BDA event loop and seed touch globals, "
            "format x:y:down[:event_type]@event_hit. Defaults: down -> type 4, up -> type 5."
        ),
    )
    ap.add_argument(
        "--gpio-level",
        type=parse_mmio_level,
        action="append",
        default=[],
        help="Force an MMIO read register value, format addr:value. Useful for GPIO/INTC input experiments.",
    )
    ap.add_argument(
        "--gpio-pulse",
        type=parse_mmio_pulse,
        action="append",
        default=[],
        help="Force an MMIO read register for a limited number of reads, format addr:value@idle_hit[:reads].",
    )
    ap.add_argument(
        "--key-pulse",
        type=parse_key_pulse,
        action="append",
        default=[],
        help="Inject a known active-low key scanner code, format code@idle_hit[:reads]. Known codes: 4,5,6,7,9,10.",
    )
    ap.add_argument("--fb-dump", type=Path, help="Dump RGB565 framebuffer after execution (.png or .ppm).")
    ap.add_argument("--fb-addr", type=lambda x: int(x, 0), default=0xA1F82000)
    ap.add_argument("--fb-offset-bytes", type=lambda x: int(x, 0), default=0)
    ap.add_argument("--fb-width", type=int, default=240)
    ap.add_argument("--fb-height", type=int, default=320)
    ap.add_argument("--fb-stride-pixels", type=int, default=240)
    ap.add_argument("--fb-scan", action="store_true", help="Scan RAM for likely RGB565 framebuffer windows.")
    ap.add_argument(
        "--fb-format",
        default="rgb565",
        choices=["rgb565", "bgr565", "rgb565-be", "bgr565-be"],
        help="Framebuffer pixel interpretation.",
    )
    ap.add_argument(
        "--fb-orientation",
        default="rot180",
        choices=["raw", "rot180", "cw90", "ccw90", "hflip", "vflip"],
        help="Display orientation applied to framebuffer dump.",
    )
    ap.add_argument("--json-out", type=Path)
    ap.add_argument("--no-json-out", action="store_true", help="Do not write the final JSON debug report.")
    ap.add_argument("--state-in", type=Path, help="Load a compressed emulator RAM/register checkpoint before running.")
    ap.add_argument("--state-out", type=Path, help="Save a compressed emulator RAM/register checkpoint after running.")
    ap.add_argument("--quiet", action="store_true", help="Do not print the full JSON report to stdout.")
    ap.add_argument(
        "--bda-text-mode",
        default="native",
        choices=["ascii-hook", "native"],
        help="Direct-BDA text handling. ascii-hook is temporary visible ASCII rendering; native leaves firmware font code alone.",
    )
    ap.add_argument(
        "--bda-native-glyph-layout",
        default="rows-msb-vscale2",
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
        help="ASCII glyph buffer packing used only when native text recovery synthesizes missing font glyphs.",
    )
    ap.add_argument(
        "--bda-native-raster-mode",
        default="firmware",
        choices=["firmware", "synth"],
        help="Native text raster handling. firmware runs C200's raster routine; synth is an experimental direct model for ASCII glyphs.",
    )
    ap.add_argument(
        "--scheduler-tick-clamp",
        action="store_true",
        help=(
            "Clamp the C200 scheduler pending-tick byte at 0x80473f08 before "
            "polling. This models timer-pending consumption while the exact "
            "interrupt cadence is still incomplete."
        ),
    )
    ap.add_argument(
        "--fast-hooks",
        action="store_true",
        help=(
            "Use targeted code hooks instead of per-instruction tracing. Much "
            "faster for system boot/menu work, but insn_count and last_pcs are coarse."
        ),
    )
    ap.add_argument(
        "--fast-hook-image-jals",
        action="store_true",
        help="With --fast-hooks, also hook every jal in the loaded image for exact Unicorn branch-exception recovery.",
    )
    ap.add_argument(
        "--fast-hook-image-branches",
        action="store_true",
        help="With --fast-hooks, save pre-instruction register snapshots for recoverable branch/CP0/cache exception PCs.",
    )
    ap.add_argument(
        "--store-delay-branch-hooks",
        choices=["known", "all", "off"],
        default="known",
        help=(
            "Delay-slot store branch hook set used with --fast-hooks. known uses "
            "the current verified C200 cold-menu PC set; all scans the loaded "
            "image; off disables this recovery hook family."
        ),
    )
    ap.add_argument(
        "--fast-hook-store-delay-branches",
        dest="store_delay_branch_hooks",
        action="store_const",
        const="all",
        help=(
            "Legacy alias for --store-delay-branch-hooks all."
        ),
    )
    ap.add_argument(
        "--no-fast-hook-store-delay-branches",
        dest="store_delay_branch_hooks",
        action="store_const",
        const="off",
        help="Legacy alias for --store-delay-branch-hooks off.",
    )
    ap.add_argument(
        "--nand-loop-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: collapse known C200 NAND data-port byte-copy loops "
            "into equivalent bulk MMIO reads. Disabled by default."
        ),
    )
    ap.add_argument(
        "--resource-cache16-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: intercept C200 0x8017ca10 resource-cache 16-bit lookups. "
            "Disabled by default because bad cache modeling can corrupt image/resource data."
        ),
    )
    ap.add_argument(
        "--no-raster-copy-accelerator",
        action="store_true",
        help="Diagnostic: disable the 0x800ac388 raster-copy loop accelerator while keeping other fast hooks.",
    )
    ap.add_argument(
        "--no-glyph-mask-accelerator",
        action="store_true",
        help="Diagnostic: disable the 0x8011b428 glyph-mask loop accelerator while keeping other fast hooks.",
    )
    ap.add_argument(
        "--no-surface-pixel-accelerator",
        action="store_true",
        help="Diagnostic: disable the 0x8012bdf4 surface setpixel accelerator while keeping other fast hooks.",
    )
    ap.add_argument(
        "--no-surface-hline-accelerator",
        action="store_true",
        help="Diagnostic: disable the 0x8012bea4 surface hline accelerator while keeping other fast hooks.",
    )
    ap.add_argument(
        "--surface-pixel-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: replace C200 0x8012bdf4 surface setpixel. "
            "Kept for compatibility; the accelerator is enabled by default."
        ),
    )
    ap.add_argument(
        "--surface-hline-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: replace C200 0x8012bea4 surface hline. "
            "Kept for compatibility; the accelerator is enabled by default."
        ),
    )
    ap.add_argument(
        "--font-helper-accelerator",
        action="store_true",
        help=(
            "Diagnostic speedup: replace selected C200 font helper returns at 0x8012a6a8. "
            "Off by default because it can corrupt GBK glyph selection."
        ),
    )
    ap.add_argument(
        "--repeat-prologue-mode",
        default="off",
        choices=["off", "log", "fix", "stop"],
        help=(
            "Diagnostic mode for repeated stack-prologue observations. "
            "fix keeps legacy compensation; stop halts at the first case."
        ),
    )
    ap.add_argument(
        "--fs-dir-scan-stop-samples",
        type=int,
        default=0,
        help="Diagnostic: stop after collecting this many C200 directory-scan loop samples.",
    )
    ns = ap.parse_args(argv)
    apply_preset(ns, argv)
    validate_legacy_direct_bda(ns, ap)
    watch_ranges = list(ns.watch_va)
    if ns.watch_input_state:
        watch_ranges.append(parse_watch_range("input=0x80473f40:0x80"))
    if ns.watch_input_nodes:
        watch_ranges.append(parse_watch_range("nodes=0x806c5000:0x1000"))

    report: dict[str, object] = {
        "inspect": inspect_image(ns.image, ns.base, ns.disasm_count),
        "payload": None
        if ns.payload is None
        else {
            "path": str(ns.payload),
            "size": ns.payload.stat().st_size,
            "addr": f"0x{ns.payload_addr:08x}",
        },
        "execution": None,
    }

    if unicorn_cls is None:
        report["execution"] = {
            "available": False,
            "reason": "Python package 'unicorn' is not installed.",
        }
    else:
        emu = emulator_cls(
            image=ns.image,
            base=ns.base,
            pc=ns.pc,
            ram_size=ns.ram_mb * 1024 * 1024,
            trace_limit=ns.trace_limit,
            recover_jr=not ns.no_recover_jr,
            profile=ns.profile,
            payload=ns.payload,
            payload_addr=ns.payload_addr,
            idle_stop_hits=ns.idle_stop_hits,
            app_idle_stop_hits=ns.app_idle_stop_hits,
            bda_idle_stop_polls=ns.bda_idle_stop_polls,
            watch_ranges=watch_ranges,
            scheduled_pokes=ns.poke_va,
            scheduled_calls=ns.call_va,
            call_stack=ns.call_stack,
            mmio_levels=ns.gpio_level,
            mmio_pulses=ns.gpio_pulse + ns.key_pulse,
            firmware_key_samples=ns.fw_key_sample,
            touch_samples=ns.touch_sample,
            bda_launches=ns.launch_bda,
            gui_key_events=ns.gui_key_event,
            gui_touch_events=ns.gui_touch_event,
            touch_controller_events=ns.touch_controller_event,
            key_controller_events=ns.key_controller_event,
            bda_key_events=ns.bda_key_event,
            bda_events=ns.bda_event,
            bda_touch_events=ns.bda_touch_event,
            trace_pcs=ns.trace_pc,
            stop_pcs=ns.stop_pc,
            stop_input_nodes=ns.stop_input_node,
            nand_image=ns.nand_image,
            nand_page_size=ns.nand_page_size,
            nand_spare_size=ns.nand_spare_size,
            readonly_nand_page_ranges=ns.readonly_nand_page_range,
            block_image=ns.block_image,
            usb_connected=ns.usb_connected,
            bda_text_mode=ns.bda_text_mode,
            bda_native_glyph_layout=ns.bda_native_glyph_layout,
            bda_native_raster_mode=ns.bda_native_raster_mode,
            legacy_direct_bda=ns.legacy_direct_bda,
            scheduler_tick_clamp=ns.scheduler_tick_clamp,
            fs_dir_scan_stop_samples=ns.fs_dir_scan_stop_samples,
            fast_hooks=ns.fast_hooks,
            fast_hook_image_jals=ns.fast_hook_image_jals,
            fast_hook_image_branches=ns.fast_hook_image_branches,
            store_delay_branch_hooks=ns.store_delay_branch_hooks,
            nand_loop_accelerator=ns.nand_loop_accelerator,
            resource_cache16_accelerator=ns.resource_cache16_accelerator,
            raster_copy_accelerator=not ns.no_raster_copy_accelerator,
            glyph_mask_accelerator=not ns.no_glyph_mask_accelerator,
            surface_pixel_accelerator=not ns.no_surface_pixel_accelerator,
            surface_hline_accelerator=not ns.no_surface_hline_accelerator,
            font_helper_accelerator=ns.font_helper_accelerator,
            gui_ring_pump=ns.gui_ring_pump,
            repeat_prologue_mode=ns.repeat_prologue_mode,
        )
        if ns.state_in:
            emu.load_emulator_state(ns.state_in)
        if ns.clear_nand_overrides_page_range:
            emu.clear_nand_page_overrides(ns.clear_nand_overrides_page_range)
        for x, y, down in ns.touch_state:
            emu.set_touch_controller_state(x, y, down)
        try:
            state = emu.run(ns.steps, max_seconds=ns.max_seconds)
            stop_reason = state.stop_reason or "completed_step_count"
        except Exception as exc:
            state = emu.state
            stop_reason = f"{type(exc).__name__}: {exc}"
        if ns.state_out:
            emu.save_emulator_state(ns.state_out)
        report["execution"] = {
            "available": True,
            "stop_reason": stop_reason,
            "insn_count": state.insn_count,
            "last_pc": f"0x{state.last_pc:08x}",
            "last_pcs": [f"0x{pc:08x}" for pc in state.pcs],
            "last_calls": state.calls,
            "trace_pc_hits": emu.trace_pc_hits[-max(256, ns.trace_limit):],
            "events": list(state.events),
            "regs": emu.regs(),
            "recoveries": state.recoveries,
            "mmio": [access_to_dict(a) for a in state.mmio],
            "invalid": [access_to_dict(a) for a in state.invalid],
            "mmio_snapshot": emu.mmio_snapshot(),
            "uart": emu.uart_snapshot(),
            "watch": emu.watch_snapshot(),
            "input_state": emu.input_snapshot(),
            "fs_dir_scan": emu.fs_dir_scan_events[-256:],
            "return_epilogues": emu.return_epilogue_events[-64:],
            "repeat_prologues": emu.repeat_prologue_events[-256:],
        }
        if ns.fb_dump:
            try:
                report["execution"]["framebuffer"] = dump_rgb565_framebuffer(
                    emu,
                    ns.fb_dump,
                    ns.fb_addr,
                    ns.fb_offset_bytes,
                    ns.fb_width,
                    ns.fb_height,
                    ns.fb_stride_pixels,
                    ns.fb_format,
                    ns.fb_orientation,
                )
            except Exception as exc:
                report["execution"]["framebuffer"] = {
                    "path": str(ns.fb_dump),
                    "error": f"{type(exc).__name__}: {exc}",
                }
        if ns.fb_scan:
            report["execution"]["framebuffer_scan"] = scan_rgb565_framebuffers(
                emu,
                ns.fb_width,
                ns.fb_height,
                ns.fb_stride_pixels,
            )

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if ns.json_out:
        ns.json_out.write_text(text + "\n", encoding="utf-8")
    if ns.quiet:
        execution = report.get("execution") or {}
        if isinstance(execution, dict):
            framebuffer = execution.get("framebuffer") or {}
            pixels = framebuffer.get("nonzero_pixels") if isinstance(framebuffer, dict) else None
            print(
                f"stop={execution.get('stop_reason')} "
                f"invalid={len(execution.get('invalid', []))} "
                f"pixels={pixels} json={ns.json_out}"
            )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    from bbk9588_hwemu import Bbk9588HwEmu, Uc

    raise SystemExit(main(sys.argv[1:], Bbk9588HwEmu, Uc))
