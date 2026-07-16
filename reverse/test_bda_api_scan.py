from __future__ import annotations

import struct
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bda_api_scan import scan_calls


def lw(target: int, base: int, offset: int) -> int:
    return (0x23 << 26) | (base << 21) | (target << 16) | offset


def jalr(reg: int) -> int:
    return (reg << 21) | 0x0000F809


class BdaApiScanTest(unittest.TestCase):
    def test_scans_high_gui_table_offsets(self) -> None:
        words = [lw(2, 3, 0x6D8), 0, jalr(2), 0]
        data = struct.pack("<4I", *words)

        calls = scan_calls(data, 0, len(data))

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["api_offset"], 0x6D8)

    def test_rejects_unnamed_high_object_vtable_offsets(self) -> None:
        words = [lw(2, 3, 0x7E0), 0, jalr(2), 0]
        data = struct.pack("<4I", *words)

        self.assertEqual(scan_calls(data, 0, len(data)), [])


if __name__ == "__main__":
    unittest.main()
