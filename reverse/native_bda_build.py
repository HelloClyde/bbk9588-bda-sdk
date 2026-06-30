from __future__ import annotations

import argparse
from pathlib import Path

from bda_layout import analyze
from minimips import assemble_file


NOP = b"\0\0\0\0"


def main() -> None:
    ap = argparse.ArgumentParser(description="Assemble a tiny MIPS source file into a native BDA template.")
    ap.add_argument("source", type=Path)
    ap.add_argument("--template", type=Path, default=None)
    ap.add_argument("--template-size", type=int, default=185868)
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--wipe-bytes", type=lambda x: int(x, 0), default=0x400)
    ns = ap.parse_args()

    template = ns.template
    if template is None:
        matches = [
            p
            for p in ns.root.rglob("*")
            if p.is_file() and p.suffix.lower() == ".bda" and p.stat().st_size == ns.template_size
        ]
        matches = [
            p
            for p in matches
            if not any(part.lower() in {"build", "reverse"} for part in p.parts)
        ]
        matches = [p for p in matches if analyze(p)["entry_offset"] is not None]
        if not matches:
            raise SystemExit(f"no .bda with size {ns.template_size} found under {ns.root}")
        template = matches[0]

    layout = analyze(template)
    entry = layout["entry_offset"]
    entry_va = layout["runtime_entry_va"]
    if entry is None or entry_va is None:
        raise SystemExit(f"could not infer runtime entry for {template}")

    code = assemble_file(ns.source, int(entry_va))
    if len(code) > ns.wipe_bytes:
        raise SystemExit(f"assembled code is 0x{len(code):x} bytes, exceeds wipe area 0x{ns.wipe_bytes:x}")

    data = bytearray(template.read_bytes())
    wipe = min(ns.wipe_bytes, len(data) - int(entry))
    data[int(entry) : int(entry) + wipe] = NOP * (wipe // 4)
    data[int(entry) : int(entry) + len(code)] = code

    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"template={template}")
    print(f"source={ns.source}")
    print(f"output={ns.output}")
    print(f"entry_offset=0x{int(entry):x}")
    print(f"entry_va=0x{int(entry_va):x}")
    print(f"code_size=0x{len(code):x}")


if __name__ == "__main__":
    main()
