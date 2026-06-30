from __future__ import annotations

import argparse
import os
import time
from pathlib import Path


def newest_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return 0.0


def tail_log(log_path: Path, stop_after: float | None) -> None:
    pos = 0
    start = time.time()
    print(f"tailing {log_path}")
    while True:
        if stop_after is not None and time.time() - start >= stop_after:
            return
        if log_path.exists():
            size = log_path.stat().st_size
            if size < pos:
                pos = 0
            with log_path.open("rb") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
            if chunk:
                print(chunk.decode("gbk", errors="replace"), end="")
        time.sleep(0.5)


def write_command(cmd_path: Path, command: str) -> None:
    cmd_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cmd_path.with_suffix(".tmp")
    tmp.write_text(command.rstrip("\r\n") + "\r\n", encoding="ascii")
    os.replace(tmp, cmd_path)
    print(f"sent: {command}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Host-side helper for UsbDebugBridge.bda over USB mass storage.")
    ap.add_argument("--drive", default="F:", help="mounted device drive, e.g. F:")
    ap.add_argument("--command", "-c", help="send one command, e.g. ping/status/msg hello/quit")
    ap.add_argument("--tail", action="store_true", help="tail debug log")
    ap.add_argument("--seconds", type=float, default=None, help="optional tail duration")
    ns = ap.parse_args()

    root = Path(ns.drive + "\\") if len(ns.drive) == 2 and ns.drive[1] == ":" else Path(ns.drive)
    debug_dir = root / "应用" / "数据" / "debug"
    log_path = debug_dir / "usbdebug.log"
    cmd_path = debug_dir / "cmd.txt"

    if ns.command:
        write_command(cmd_path, ns.command)
    if ns.tail or not ns.command:
        tail_log(log_path, ns.seconds)


if __name__ == "__main__":
    main()
