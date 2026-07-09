#!/usr/bin/env python3
"""Apply the bundled BBK9588 QEMU patch to a QEMU source tree."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_patch() -> Path:
    return repo_root() / "emu" / "qemu" / "patches" / "qemu-v11.0.0-bbk9588.patch"


def run(command: list[str], cwd: Path) -> int:
    print("+ " + " ".join(command))
    completed = subprocess.run(command, cwd=cwd, check=False)
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qemu-source", type=Path, default=Path(r"E:\qemu-src"))
    ap.add_argument("--patch", type=Path, default=default_patch())
    ap.add_argument("--check", action="store_true", help="Validate only; do not modify the source tree.")
    ap.add_argument("--reverse", action="store_true", help="Reverse the patch.")
    ns = ap.parse_args(argv)

    source = ns.qemu_source.resolve()
    patch = ns.patch.resolve()
    if not (source / "configure").is_file() or not (source / "meson.build").is_file():
        print(f"not a QEMU source tree: {source}", file=sys.stderr)
        return 2
    if not patch.is_file():
        print(f"patch not found: {patch}", file=sys.stderr)
        return 2

    command = ["git", "apply"]
    if ns.reverse:
        command.append("--reverse")
    if ns.check:
        command.append("--check")
    command.append(str(patch))
    return run(command, source)


if __name__ == "__main__":
    raise SystemExit(main())
