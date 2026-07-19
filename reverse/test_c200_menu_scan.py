from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from c200_menu_scan import (
    CATEGORY_LABEL_STRIDE,
    CATEGORY_LABEL_TABLE_VA,
    CATEGORY_STATE_STRIDE,
    CATEGORY_STATE_TABLE_VA,
    DEFAULT_BASE,
    DEFAULT_C200,
    read_category_limits,
)


EXPECTED_LABELS = [
    "听说",
    "语法",
    "阅读",
    "娱乐天地",
    "考试",
    "背诵",
    "词典",
    "娱乐",
    "工具",
]
EXPECTED_CAPACITIES = [7, 5, 9, 10, 10, 8, 15, 10, 20]
EXPECTED_INITIAL_COUNTS = [0, 0, 0, 0, 6, 0, 7, 1, 4]


class C200MenuScanTest(unittest.TestCase):
    def test_category_limit_parser_uses_firmware_tables(self) -> None:
        base = 0x80366000
        data = bytearray(0x1000)
        for index, (label, capacity, initial_count) in enumerate(
            zip(EXPECTED_LABELS, EXPECTED_CAPACITIES, EXPECTED_INITIAL_COUNTS),
            start=1,
        ):
            label_off = (
                CATEGORY_LABEL_TABLE_VA
                + (index - 1) * CATEGORY_LABEL_STRIDE
                - base
            )
            encoded = label.encode("gbk") + b"\0"
            data[label_off : label_off + len(encoded)] = encoded
            state_off = (
                CATEGORY_STATE_TABLE_VA + index * CATEGORY_STATE_STRIDE - base
            )
            struct.pack_into("<HH", data, state_off, capacity, initial_count)

        rows = read_category_limits(bytes(data), base)
        self.assertEqual([row["label"] for row in rows], EXPECTED_LABELS)
        self.assertEqual([row["capacity"] for row in rows], EXPECTED_CAPACITIES)
        self.assertEqual([row["initial_count"] for row in rows], EXPECTED_INITIAL_COUNTS)

    def test_checked_in_c200_matches_documented_category_limits(self) -> None:
        if not Path(DEFAULT_C200).is_file():
            self.skipTest("local C200.bin is not available")
        rows = read_category_limits(Path(DEFAULT_C200).read_bytes(), DEFAULT_BASE)
        self.assertEqual([row["label"] for row in rows], EXPECTED_LABELS)
        self.assertEqual([row["capacity"] for row in rows], EXPECTED_CAPACITIES)
        self.assertEqual([row["initial_count"] for row in rows], EXPECTED_INITIAL_COUNTS)


if __name__ == "__main__":
    unittest.main()
