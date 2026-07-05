#!/usr/bin/env python3
"""Run hardware-emulator regressions through the web backend only."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"


def run_command(name: str, cmd: list[str], timeout: int) -> dict[str, object]:
    start = time.time()
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "elapsed_seconds": round(time.time() - start, 3),
        "command": cmd,
        "output_tail": proc.stdout[-8000:],
    }


def maybe_nand_args(path: Path | None) -> list[str]:
    return [] if path is None else ["--nand-image", str(path)]


def latest_summary(prefix: str) -> dict[str, object]:
    path = BUILD / f"{prefix}_summary.json"
    if not path.is_file():
        return {"missing": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run BBK9588 web-backend regression checks.")
    ap.add_argument("--nand-image", type=Path, default=None, help="Override app.py's default NAND image.")
    ap.add_argument("--summary-json", type=Path, default=BUILD / "hwemu_regression_summary.json")
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--album-smoke", action="store_true", help="Also run the slower Album web smoke.")
    ap.add_argument("--thunder-smoke", action="store_true", help="Also run the slower Thunder web smoke.")
    args = ap.parse_args(argv)

    BUILD.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    rows.append(
        run_command(
            "py-compile-emu",
            [sys.executable, "-m", "compileall", "-q", "emu"],
            max(30, min(args.timeout, 120)),
        )
    )

    frontend_prefix = "hwemu_frontend_web_regression"
    rows.append(
        run_command(
            "frontend-http-ws-smoke",
            [
                sys.executable,
                str(Path("emu") / "test" / "run_frontend_web_smoke.py"),
                "--host",
                args.host,
                "--port",
                str(args.port),
                *maybe_nand_args(args.nand_image),
                "--prefix",
                frontend_prefix,
            ],
            args.timeout,
        )
    )

    if args.album_smoke:
        album_prefix = "hwemu_album_web_regression"
        rows.append(
            run_command(
                "album-web-smoke",
                [
                    sys.executable,
                    str(Path("emu") / "test" / "run_album_web_smoke.py"),
                    "--host",
                    args.host,
                    "--port",
                    str(args.port),
                    *maybe_nand_args(args.nand_image),
                    "--prefix",
                    album_prefix,
                ],
                args.timeout,
            )
        )

    if args.thunder_smoke:
        thunder_prefix = "hwemu_thunder_web_regression"
        rows.append(
            run_command(
                "thunder-web-smoke",
                [
                    sys.executable,
                    str(Path("emu") / "test" / "run_thunder_web_smoke.py"),
                    "--host",
                    args.host,
                    "--port",
                    str(args.port),
                    *maybe_nand_args(args.nand_image),
                    "--prefix",
                    thunder_prefix,
                ],
                args.timeout,
            )
        )

    summary = {
        "ok": all(row["ok"] for row in rows),
        "web_backend_only": True,
        "rows": rows,
        "frontend_summary": latest_summary(frontend_prefix),
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
