from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from bda_build import fix_header_checksum, set_category, set_title
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
    for candidate in candidates:
        p = Path(candidate)
        if p.is_file():
            return str(p)
        found = shutil.which(candidate)
        if found is not None:
            return found
    raise SystemExit(f"could not find {exe}")


def mips_jump_blob(target_va: int) -> bytes:
    hi = (target_va >> 16) & 0xFFFF
    lo = target_va & 0xFFFF
    # lui t9, hi; ori t9, t9, lo; jr t9; nop
    words = [
        0x3C190000 | hi,
        0x37390000 | lo,
        0x03200008,
        0x00000000,
    ]
    return b"".join(w.to_bytes(4, "little") for w in words)


def compile_raw(source: Path, base_va: int, prefix: str) -> bytes:
    cc = find_tool(prefix, "gcc")
    objcopy = find_tool(prefix, "objcopy")
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
        subprocess.check_call(
            [
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
                str(source),
                "-o",
                str(elf),
            ]
        )
        subprocess.check_call([objcopy, "-O", "binary", str(elf), str(raw)])
        return raw.read_bytes()


def main() -> None:
    ap = argparse.ArgumentParser(description="Append a compiled C blob to a BDA and patch one function to jump to it.")
    ap.add_argument("source", type=Path)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--patch-va", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--title")
    ap.add_argument("--category", type=lambda x: int(x, 0))
    ap.add_argument("--replace", action="append", default=[], help="ASCII replacement OLD=NEW, NEW must fit OLD")
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    data = bytearray(ns.template.read_bytes())
    layout = analyze(ns.template)
    file_base = layout["runtime_file_base"]
    if file_base is None:
        raise SystemExit("could not infer runtime file base")

    min_append_off = len(data)
    bss_end = layout.get("bss_end")
    if bss_end is not None:
        min_append_off = max(min_append_off, int(bss_end) - int(file_base))
    append_off = (min_append_off + 15) & ~15
    if append_off > len(data):
        data.extend(b"\0" * (append_off - len(data)))
    append_va = int(file_base) + append_off

    prefix = ns.prefix or bundled_prefix() or "mipsel-none-elf-"
    blob = compile_raw(ns.source, append_va, prefix)
    data.extend(blob)

    patch_off = ns.patch_va - int(file_base)
    if patch_off < 0 or patch_off + 16 > len(data):
        raise SystemExit("patch-va outside template runtime range")
    data[patch_off : patch_off + 16] = mips_jump_blob(append_va)

    for item in ns.replace:
        old, new = item.split("=", 1)
        old_b = old.encode("ascii")
        new_b = new.encode("ascii")
        if len(new_b) > len(old_b):
            raise SystemExit(f"replacement too long: {item}")
        at = data.find(old_b)
        if at < 0:
            raise SystemExit(f"could not find replacement target: {old}")
        data[at : at + len(old_b)] = new_b.ljust(len(old_b), b"\0")

    if ns.title is not None:
        set_title(data, ns.title)
    if ns.category is not None:
        set_category(data, ns.category)
    fix_header_checksum(data)

    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"append_off=0x{append_off:x}")
    print(f"append_va=0x{append_va:x}")
    print(f"blob_size=0x{len(blob):x}")
    print(f"patch_off=0x{patch_off:x}")
    print(f"output={ns.output}")


if __name__ == "__main__":
    main()
