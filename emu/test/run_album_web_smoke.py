#!/usr/bin/env python3
"""Find and exercise the bundled Album app through the web frontend."""

from __future__ import annotations

import argparse
import json
import shutil
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
    fetch_screen_digest,
    find_free_port,
    http_json,
    key_press,
    looks_like_menu,
    start_frontend,
    summarize_status,
    tap,
    wait_http,
)


def album_list_like(status: dict[str, object]) -> bool:
    fb = status.get("framebuffer") if isinstance(status.get("framebuffer"), dict) else {}
    return int(fb.get("nonzero_pixels") or 0) >= 65000 and int(fb.get("unique_pixel_values") or 0) >= 20


def save_capture(host: str, port: int, out_dir: Path, prefix: str, name: str) -> dict[str, object]:
    status_code, png, digest = fetch_screen_digest(host, port)
    path = out_dir / f"{prefix}_{name}.png"
    if status_code == 200:
        path.write_bytes(png)
    return {
        "name": name,
        "path": str(path) if status_code == 200 else None,
        "sha256": digest,
        "status_code": status_code,
        "status": summarize_status(http_json(host, port, "GET", "/api/status")),
    }


def wait_for_digest_change(
    host: str,
    port: int,
    previous_digest: str,
    timeout: float,
) -> tuple[str, dict[str, object]]:
    deadline = time.time() + timeout
    last_digest = previous_digest
    last_status: dict[str, object] = {}
    while time.time() < deadline:
        _status_code, _png, last_digest = fetch_screen_digest(host, port)
        last_status = http_json(host, port, "GET", "/api/status")
        if last_digest and last_digest != previous_digest:
            return last_digest, last_status
        time.sleep(0.7)
    return last_digest, last_status


def make_contact_sheet(captures: list[dict[str, object]], out_path: Path) -> str | None:
    image_paths: list[Path] = []
    for capture in captures:
        path = capture.get("path")
        if not path:
            continue
        image_path = Path(str(path))
        if image_path.exists():
            image_paths.append(image_path)

    try:
        from PIL import Image, ImageDraw
    except Exception:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg or not image_paths:
            return None
        cols = min(4, len(image_paths))
        layout = "|".join(f"{(idx % cols) * 240}_{(idx // cols) * 320}" for idx in range(len(image_paths)))
        cmd = [ffmpeg, "-y"]
        for image_path in image_paths:
            cmd += ["-i", str(image_path)]
        cmd += [
            "-filter_complex",
            f"xstack=inputs={len(image_paths)}:layout={layout}:fill=black",
            "-frames:v",
            "1",
            str(out_path),
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except Exception:
            return None
        return str(out_path)
    images = []
    for image_path in image_paths:
        image = Image.open(image_path).convert("RGB")
        name = next((str(capture.get("name")) for capture in captures if capture.get("path") == str(image_path)), image_path.stem)
        images.append((name, image))
    if not images:
        return None
    tile_w, tile_h = 240, 344
    cols = min(4, len(images))
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tile_w, rows * tile_h), "black")
    draw = ImageDraw.Draw(sheet)
    for idx, (name, image) in enumerate(images):
        x = (idx % cols) * tile_w
        y = (idx // cols) * tile_h
        sheet.paste(image, (x, y))
        draw.text((x + 4, y + 322), str(name), fill="white")
    sheet.save(out_path)
    return str(out_path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a web smoke test for 鎴戠殑鐩稿唽 / Album.")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="Use 0 to start a private frontend.")
    ap.add_argument("--use-existing", action="store_true")
    ap.add_argument("--nand-image", type=Path, default=DEFAULT_NAND)
    ap.add_argument("--out-dir", type=Path, default=BUILD)
    ap.add_argument("--prefix", default="album_web_smoke")
    ap.add_argument("--boot-timeout", type=int, default=480)
    ap.add_argument("--chunk-steps", type=int, default=250000)
    ap.add_argument("--worker-slice-seconds", type=float, default=0.25)
    ns = ap.parse_args(argv)

    ns.out_dir.mkdir(parents=True, exist_ok=True)
    port = ns.port or find_free_port(ns.host)
    proc: subprocess.Popen[bytes] | None = None
    ws: WebSocketClient | None = None
    captures: list[dict[str, object]] = []
    interactions: list[dict[str, object]] = []
    failures: list[str] = []
    logs: dict[str, object] = {}
    start = time.time()
    try:
        if not ns.use_existing:
            proc = start_frontend(ns, port)
        wait_http(ns.host, port, 30)
        ws = WebSocketClient(ns.host, port)
        ws.pump(1.0)

        ws.send_json({"op": "reset"})
        ws.pump(1.0)
        ws.send_json({"op": "auto-calibration", "enabled": True})
        ws.pump(0.5)
        ws.send_json({"op": "run-start", "name": "album-web-smoke", "steps": 0, "chunk": ns.chunk_steps})
        menu_status = ws.wait_for(
            looks_like_menu,
            ns.boot_timeout,
            poll_status=lambda: http_json(ns.host, port, "GET", "/api/status"),
        )
        interactions.append({"step": "wait-menu", "status": summarize_status(menu_status)})
        if not looks_like_menu(menu_status):
            failures.append("cold boot did not reach the main menu")
        else:
            menu_capture = save_capture(ns.host, port, ns.out_dir, ns.prefix, "menu")
            captures.append(menu_capture)

            for index in range(7):
                key_press(ws, 7)
                status = http_json(ns.host, port, "GET", "/api/status")
                interactions.append({"step": f"right-{index + 1}", "status": summarize_status(status)})
            selected = save_capture(ns.host, port, ns.out_dir, ns.prefix, "selected_album")
            captures.append(selected)

            key_press(ws, 10)
            launch_digest, launch_status = wait_for_digest_change(
                ns.host,
                port,
                str(selected.get("sha256") or ""),
                35,
            )
            interactions.append({"step": "key-ok-launch", "digest": launch_digest, "status": summarize_status(launch_status)})
            captures.append(save_capture(ns.host, port, ns.out_dir, ns.prefix, "after_key_ok"))

            if not album_list_like(launch_status):
                failures.append("Album app did not reach its blue list/photo browser screen")

            key_press(ws, 5)
            down_digest, down_status = wait_for_digest_change(ns.host, port, str(captures[-1].get("sha256") or ""), 20)
            interactions.append({"step": "normalize-key-down", "digest": down_digest, "status": summarize_status(down_status)})
            captures.append(save_capture(ns.host, port, ns.out_dir, ns.prefix, "after_key_down"))

            key_press(ws, 10)
            ok2_digest, ok2_status = wait_for_digest_change(ns.host, port, down_digest, 20)
            interactions.append({"step": "normalize-key-ok", "digest": ok2_digest, "status": summarize_status(ok2_status)})
            captures.append(save_capture(ns.host, port, ns.out_dir, ns.prefix, "after_key_ok2"))

            tap(ws, 66, 92)
            first_digest, first_status = wait_for_digest_change(ns.host, port, ok2_digest, 35)
            interactions.append({"step": "tap-first-tile", "digest": first_digest, "status": summarize_status(first_status)})
            captures.append(save_capture(ns.host, port, ns.out_dir, ns.prefix, "after_first_tile"))

            first_fb = first_status.get("framebuffer") if isinstance(first_status.get("framebuffer"), dict) else {}
            if int(first_fb.get("unique_pixel_values") or 0) < 100:
                failures.append("Album first thumbnail did not render after tapping the first tile")

            tap(ws, 225, 305)
            next_digest, next_status = wait_for_digest_change(ns.host, port, first_digest, 20)
            interactions.append({"step": "tap-bottom-right", "digest": next_digest, "status": summarize_status(next_status)})
            captures.append(save_capture(ns.host, port, ns.out_dir, ns.prefix, "after_bottom_right"))

        if ws is not None:
            ws.send_json({"op": "stop"})
            ws.pump(1.0)
        logs = http_json(ns.host, port, "GET", "/api/logs?limit=120")
    finally:
        if ws is not None:
            ws.close()
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    elapsed = time.time() - start
    contact_sheet = make_contact_sheet(captures, ns.out_dir / f"{ns.prefix}_contactsheet.png")
    summary = {
        "ok": not failures,
        "host": ns.host,
        "port": port,
        "used_existing": ns.use_existing,
        "elapsed_seconds": round(elapsed, 3),
        "failures": failures,
        "captures": captures,
        "contact_sheet": contact_sheet,
        "interactions": interactions,
        "log_count": logs.get("count"),
        "recent_logs": logs.get("events", []),
    }
    json_path = ns.out_dir / f"{ns.prefix}_summary.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    report_path = ns.out_dir / f"{ns.prefix}_report.md"
    lines = [
        "# Album Web Smoke Report",
        "",
        f"- Result: {'PASS' if summary['ok'] else 'FAIL'}",
        f"- Elapsed seconds: {summary['elapsed_seconds']}",
        f"- Contact sheet: {contact_sheet}",
        "",
        "## Steps",
    ]
    for item in interactions:
        lines.append(f"- {item['step']}: `{json.dumps(item.get('status', {}), ensure_ascii=False)}`")
    if failures:
        lines += ["", "## Failures"]
        lines += [f"- {failure}" for failure in failures]
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"ok": summary["ok"], "summary": str(json_path), "report": str(report_path), "contact_sheet": contact_sheet}, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
