from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bda_patch_main import find_main_offset
from bda_layout import analyze


def bundled_prefix() -> str | None:
    root = Path(__file__).resolve().parents[1] / "tools"
    for gcc in root.glob("g++-mipsel-none-elf-*/bin/mipsel-none-elf-gcc.exe"):
        return str(gcc.parent / "mipsel-none-elf-")
    return None


def find_tool(prefix: str, name: str) -> str:
    exe = f"{prefix}{name}"
    candidates = [exe]
    if not exe.lower().endswith(".exe"):
        candidates.append(exe + ".exe")
    path = None
    for candidate in candidates:
        p = Path(candidate)
        if p.is_file():
            path = str(p)
            break
        found = shutil.which(candidate)
        if found is not None:
            path = found
            break
    if path is None:
        raise SystemExit(f"could not find {exe}; pass --prefix or install a mipsel toolchain")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="Compile freestanding C to a raw MIPS blob and package it as a BDA.")
    ap.add_argument("source", type=Path)
    ap.add_argument("--template", type=Path)
    ap.add_argument("--no-template", action="store_true", help="package from scratch with bda_pack_minimal.py")
    ap.add_argument("--prefix", default=None, help="tool prefix, e.g. mipsel-none-elf-, mipsel-elf-, or full path prefix")
    ap.add_argument("--title")
    ap.add_argument("--category", type=lambda x: int(x, 0))
    ap.add_argument("--icon-png", type=Path)
    ap.add_argument("--icon-background", default="000000")
    ap.add_argument("--wipe-bytes", type=lambda x: int(x, 0), default=0x300)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    prefix = ns.prefix or bundled_prefix() or "mipsel-none-elf-"

    if ns.no_template or ns.template is None:
        if ns.template is not None:
            raise SystemExit("pass either --template or --no-template, not both")
        build_cmd = [
            sys.executable,
            str(Path(__file__).with_name("bda_pack_minimal.py")),
            str(ns.source),
            "--prefix",
            prefix,
            "-o",
            str(ns.output),
        ]
        if ns.title is not None:
            build_cmd += ["--title", ns.title]
        if ns.category is not None:
            build_cmd += ["--category", hex(ns.category)]
        if ns.icon_png is not None:
            build_cmd += ["--icon-png", str(ns.icon_png), "--icon-background", ns.icon_background]
        subprocess.check_call(build_cmd)
        print("packaging=no-template")
        return

    cc = find_tool(prefix, "gcc")
    objcopy = find_tool(prefix, "objcopy")

    offset, main_va = find_main_offset(ns.template)
    layout = analyze(ns.template)
    file_base = layout["runtime_file_base"]
    if file_base is None:
        raise SystemExit(f"could not infer runtime file base for {ns.template}")
    base_va = int(file_base) + offset

    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        elf = tdir / "app.elf"
        raw = tdir / "app.bin"
        lds = tdir / "bda.ld"
        lds.write_text(
            f"""
ENTRY(bda_main)
SECTIONS
{{
  . = 0x{base_va:x};
  .text : {{ *(.text.bda_main) *(.text*) }}
  .rodata : {{ *(.rodata*) }}
  .data : {{ *(.data*) }}
  .bss : {{ *(.bss*) *(COMMON) }}
}}
""".strip()
            + "\n",
            encoding="ascii",
        )
        cmd = [
            cc,
            "-EL",
            "-march=mips32",
            "-mno-abicalls",
            "-G0",
            "-fno-pic",
            "-Os",
            "-ffreestanding",
            "-fno-builtin",
            "-nostdlib",
            "-Wl,--build-id=none",
            f"-Wl,-T,{lds}",
            str(ns.source),
            "-o",
            str(elf),
        ]
        subprocess.check_call(cmd)
        subprocess.check_call([objcopy, "-O", "binary", str(elf), str(raw)])

        build_cmd = [
            sys.executable,
            str(Path(__file__).with_name("bda_build.py")),
            "--template",
            str(ns.template),
            "--raw-bin",
            str(raw),
            "--wipe-bytes",
            hex(ns.wipe_bytes),
            "-o",
            str(ns.output),
        ]
        if ns.title is not None:
            build_cmd += ["--title", ns.title]
        if ns.category is not None:
            build_cmd += ["--category", hex(ns.category)]
        if ns.icon_png is not None:
            build_cmd += ["--icon-png", str(ns.icon_png), "--icon-background", ns.icon_background]
        subprocess.check_call(build_cmd)
    print(f"main_va=0x{main_va:x}")


if __name__ == "__main__":
    main()
