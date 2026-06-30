from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from bda_api_scan import scan_calls
from bda_layout import analyze


XOR_KEY = 0x44525744
CHECKSUM_OFF = 0x84
CHECKSUM_XOR_KEY = 0x322D464B


def u32(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "little")


def decode_word(data: bytes, off: int) -> int:
    return u32(data, off) ^ XOR_KEY


def title(data: bytes) -> str:
    raw = data[0x2C:0x3C].split(b"\0", 1)[0]
    for enc in ("gbk", "ascii", "latin1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("latin1", "replace")


def checksum_ok(data: bytes) -> bool:
    if len(data) < CHECKSUM_OFF + 4:
        return False
    buf = bytearray(data[:CHECKSUM_OFF])
    for off in range(0, 0x2C, 4):
        decoded = int.from_bytes(buf[off : off + 4], "little") ^ XOR_KEY
        buf[off : off + 4] = decoded.to_bytes(4, "little")
    expected = sum(buf) & 0xFFFFFFFF
    actual = u32(data, CHECKSUM_OFF) ^ CHECKSUM_XOR_KEY
    return expected == actual


def header(data: bytes) -> dict[str, object]:
    words = [decode_word(data, off) for off in range(0, min(0x2C, len(data)), 4)]
    return {
        "magic": f"0x{words[0]:08x}" if len(words) > 0 else None,
        "category": words[3] if len(words) > 3 else None,
        "body_size": words[4] if len(words) > 4 else None,
        "entry_offset_header": words[5] if len(words) > 5 else None,
        "icon_base": words[6] if len(words) > 6 else None,
        "icon_sizes": words[7:11] if len(words) >= 11 else [],
        "title": title(data),
        "checksum_ok": checksum_ok(data),
    }


def api_counts(data: bytes, entry: int | None) -> dict[str, int]:
    if entry is None:
        return {}
    calls = scan_calls(data, entry, len(data))
    counts = collections.Counter(c["api_offset"] for c in calls)
    return {f"+0x{k:03x}": v for k, v in sorted(counts.items())}


def analyze_bda(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    layout = analyze(path)
    entry = layout.get("entry_offset")
    return {
        "name": path.name,
        "path": str(path),
        "size": len(data),
        "header": header(data),
        "layout": {
            "entry_offset": entry,
            "runtime_file_base": layout.get("runtime_file_base"),
            "bss_start": layout.get("bss_start"),
            "bss_end": layout.get("bss_end"),
        },
        "shell_paths": layout.get("shell_paths", []),
        "api_offset_counts": api_counts(data, int(entry) if entry is not None else None),
    }


def write_markdown(items: list[dict[str, object]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Native BDA Inventory")
    lines.append("")
    lines.append("Generated from the original app directory (`*.bda`). This is an index for per-app reports; it is not a full analysis by itself.")
    lines.append("")
    lines.append("| BDA | Size | Title | Cat | Entry | BSS | Checksum | Hot API Offsets | DLX refs |")
    lines.append("| --- | ---: | --- | ---: | ---: | --- | --- | --- | ---: |")
    for item in items:
        h = item["header"]
        layout = item["layout"]
        api = item["api_offset_counts"]
        hot = ", ".join(f"{k}:{v}" for k, v in sorted(api.items(), key=lambda kv: kv[1], reverse=True)[:6])
        bss_start = layout.get("bss_start")
        bss_end = layout.get("bss_end")
        bss = ""
        if bss_start is not None and bss_end is not None:
            bss = f"0x{int(bss_start):08x}-0x{int(bss_end):08x}"
        entry = layout.get("entry_offset")
        lines.append(
            "| {name} | {size} | {title} | {cat} | {entry} | {bss} | {ck} | {hot} | {dlx} |".format(
                name=item["name"],
                size=item["size"],
                title=str(h.get("title", "")).replace("|", "\\|"),
                cat=h.get("category"),
                entry=f"0x{int(entry):x}" if entry is not None else "",
                bss=bss,
                ck="ok" if h.get("checksum_ok") else "BAD",
                hot=hot.replace("|", "\\|"),
                dlx=len(item.get("shell_paths", [])),
            )
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `Hot API Offsets` are raw indirect call offsets before table classification.")
    lines.append("- Per-app reports should use this inventory as a checklist, then add function-level evidence and cross references to SDK notes.")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build an inventory for native BBK BDA applications.")
    ap.add_argument("--root", type=Path, default=Path("应用") / "程序")
    ap.add_argument("--json-out", type=Path, default=Path("reverse") / "reports" / "bda_inventory.json")
    ap.add_argument("--md-out", type=Path, default=Path("reverse") / "reports" / "bda_inventory.md")
    ns = ap.parse_args()

    items = [analyze_bda(path) for path in sorted(ns.root.glob("*.bda"))]
    ns.json_out.parent.mkdir(parents=True, exist_ok=True)
    ns.json_out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(items, ns.md_out)
    print(f"files={len(items)}")
    print(f"json={ns.json_out}")
    print(f"markdown={ns.md_out}")


if __name__ == "__main__":
    main()
