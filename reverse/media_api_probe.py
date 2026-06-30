from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path

from bda_api_scan import scan_calls
from bda_layout import ENTRY_SIG


KEYWORDS = (
    "mp3",
    "wma",
    "wav",
    "avi",
    "mp4",
    "3gp",
    "jpg",
    "jpeg",
    "bmp",
    "png",
    "pic",
    "record",
    "player",
    "lyric",
    "audio",
    "video",
    "image",
    "photo",
    "play",
    "pause",
    "stop",
    "shell",
    "dlx",
)


def interesting_strings(data: bytes) -> list[tuple[int, str]]:
    result = []
    for match in re.finditer(rb"[\x20-\x7e]{4,}", data):
        text = match.group().decode("ascii", "ignore")
        low = text.lower()
        if any(keyword in low for keyword in KEYWORDS):
            result.append((match.start(), text[:160]))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize media-related strings and API offsets in native BDA files.")
    ap.add_argument("bda", nargs="+", type=Path)
    ap.add_argument("--strings", type=int, default=40)
    ap.add_argument("--offsets", type=int, default=30)
    ns = ap.parse_args()

    for path in ns.bda:
        data = path.read_bytes()
        entry = data.find(ENTRY_SIG)
        calls = scan_calls(data, entry if entry >= 0 else 0, len(data))
        counts = collections.Counter(call["api_offset"] for call in calls)

        print(f"\n== {path} ==")
        print(f"size=0x{len(data):x} entry=0x{entry:x} calls={len(calls)}")
        print("hot offsets:")
        for offset, count in counts.most_common(ns.offsets):
            print(f"  +0x{offset:03x}: {count}")
        print("strings:")
        for offset, text in interesting_strings(data)[: ns.strings]:
            print(f"  0x{offset:x}: {text}")


if __name__ == "__main__":
    main()
