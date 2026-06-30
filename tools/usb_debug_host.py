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


def read_new_log(log_path: Path, pos: int) -> tuple[int, str]:
    if not log_path.exists():
        return pos, ""
    size = log_path.stat().st_size
    if size < pos:
        pos = 0
    with log_path.open("rb") as f:
        f.seek(pos)
        chunk = f.read()
        pos = f.tell()
    return pos, chunk.decode("gbk", errors="replace")


def write_command(cmd_path: Path, command: str) -> None:
    cmd_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cmd_path.with_suffix(".tmp")
    tmp.write_text(command.rstrip("\r\n") + "\r\n", encoding="ascii")
    os.replace(tmp, cmd_path)
    print(f"sent: {command}")


def run_command(log_path: Path, cmd_path: Path, command: str, timeout: float, quiet: bool = False) -> tuple[str, str]:
    pos = log_path.stat().st_size if log_path.exists() else 0
    write_command(cmd_path, command)
    deadline = time.time() + timeout
    collected = []
    saw_begin = False
    last_ret = ""

    while time.time() < deadline:
        pos, text = read_new_log(log_path, pos)
        if text:
            collected.append(text)
            if not quiet:
                print(text, end="")
            for line in text.splitlines():
                if line.startswith("[BDA] begin "):
                    saw_begin = True
                if line.startswith("[BDA] ret "):
                    last_ret = line.removeprefix("[BDA] ret ").strip()
                if line.startswith("[BDA] error "):
                    return "error", "".join(collected)
                if line.startswith("[BDA] done "):
                    return last_ret or "done", "".join(collected)
                if line.startswith("[BDA] pong "):
                    return "pong", "".join(collected)
        time.sleep(0.25)

    if saw_begin:
        return "timeout_after_begin", "".join(collected)
    return "timeout_no_begin", "".join(collected)


def batch_commands(path: Path) -> list[str]:
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def scan_commands(table: str, start: int, end: int, step: int, argc: int, args: list[str]) -> list[str]:
    if argc < 0 or argc > 4:
        raise SystemExit("--argc must be 0..4")
    if len(args) < argc:
        args = args + ["0"] * (argc - len(args))
    out = []
    off = start
    while off <= end:
        fields = ["call", table, f"{off:x}", str(argc), *args[:argc]]
        out.append(" ".join(fields))
        off += step
    return out


def run_sequence(log_path: Path, cmd_path: Path, commands: list[str], timeout: float, stop_on_timeout: bool) -> None:
    print(f"running {len(commands)} commands")
    results = []
    for index, command in enumerate(commands, 1):
        print(f"\n=== {index}/{len(commands)} {command} ===")
        status, text = run_command(log_path, cmd_path, command, timeout)
        results.append((command, status))
        print(f"\n=> {status}")
        if status.startswith("timeout") and stop_on_timeout:
            print("stopping after timeout; device may have crashed or stopped polling")
            break

    print("\nsummary:")
    for command, status in results:
        print(f"{status:20} {command}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Host-side helper for UsbDebugBridge.bda over USB mass storage.")
    ap.add_argument("--drive", default="F:", help="mounted device drive, e.g. F:")
    ap.add_argument(
        "--command",
        "-c",
        help="send one command, e.g. ping/status/msg hello/call gui 2b8 4 0 0 0 0/peek 81c00000 4/quit",
    )
    ap.add_argument("--tail", action="store_true", help="tail debug log")
    ap.add_argument("--seconds", type=float, default=None, help="optional tail duration")
    ap.add_argument("--batch", type=Path, help="run commands from a UTF-8 text file")
    ap.add_argument("--timeout", type=float, default=5.0, help="seconds to wait for each command in batch/scan mode")
    ap.add_argument("--continue-on-timeout", action="store_true", help="keep sending commands after a timeout")
    ap.add_argument("--scan-table", choices=["gui", "fs", "sys", "mem", "res"], help="generate call commands for one table")
    ap.add_argument("--start", type=lambda x: int(x, 0), default=0, help="scan start offset")
    ap.add_argument("--end", type=lambda x: int(x, 0), default=0, help="scan end offset")
    ap.add_argument("--step", type=lambda x: int(x, 0), default=4, help="scan offset step")
    ap.add_argument("--argc", type=int, default=0, help="scan call argument count, 0..4")
    ap.add_argument("--arg", action="append", default=[], help="scan call argument, repeatable; hex without 0x is allowed")
    ns = ap.parse_args()

    root = Path(ns.drive + "\\") if len(ns.drive) == 2 and ns.drive[1] == ":" else Path(ns.drive)
    debug_dir = root / "应用" / "数据" / "debug"
    log_path = debug_dir / "usbdebug.log"
    cmd_path = debug_dir / "cmd.txt"

    if ns.command:
        write_command(cmd_path, ns.command)
    if ns.batch:
        run_sequence(log_path, cmd_path, batch_commands(ns.batch), ns.timeout, not ns.continue_on_timeout)
        return
    if ns.scan_table:
        if ns.end < ns.start:
            raise SystemExit("--end must be >= --start")
        commands = scan_commands(ns.scan_table, ns.start, ns.end, ns.step, ns.argc, ns.arg)
        run_sequence(log_path, cmd_path, commands, ns.timeout, not ns.continue_on_timeout)
        return
    if ns.tail or not ns.command:
        tail_log(log_path, ns.seconds)


if __name__ == "__main__":
    main()
