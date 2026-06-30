from __future__ import annotations

import argparse
from pathlib import Path

from bda_layout import analyze
from minimips import assemble_file


NOP = b"\0\0\0\0"


def main() -> None:
    ap = argparse.ArgumentParser(description="Patch a MIPS source blob into a native BDA at a file offset.")
    ap.add_argument("source", type=Path)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--offset", type=lambda x: int(x, 0), required=True)
    ap.add_argument("--base-va", type=lambda x: int(x, 0), default=None)
    ap.add_argument("--wipe-bytes", type=lambda x: int(x, 0), default=0x200)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ns = ap.parse_args()

    layout = analyze(ns.template)
    file_base = layout["runtime_file_base"]
    if file_base is None and ns.base_va is None:
        raise SystemExit("could not infer runtime file base; pass --base-va")
    base_va = ns.base_va if ns.base_va is not None else int(file_base) + ns.offset

    code = assemble_file(ns.source, int(base_va))
    if len(code) > ns.wipe_bytes:
        raise SystemExit(f"assembled code is 0x{len(code):x} bytes, exceeds wipe area 0x{ns.wipe_bytes:x}")

    data = bytearray(ns.template.read_bytes())
    if ns.offset < 0 or ns.offset + ns.wipe_bytes > len(data):
        raise SystemExit("patch range is outside file")
    data[ns.offset : ns.offset + ns.wipe_bytes] = NOP * (ns.wipe_bytes // 4)
    data[ns.offset : ns.offset + len(code)] = code

    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)
    print(f"template={ns.template}")
    print(f"source={ns.source}")
    print(f"output={ns.output}")
    print(f"patch_offset=0x{ns.offset:x}")
    print(f"patch_va=0x{int(base_va):x}")
    print(f"code_size=0x{len(code):x}")


if __name__ == "__main__":
    main()
