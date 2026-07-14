from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bda_compile_c import build_bda, bundled_prefix
from bda_validate import validate_bda


class BdaValidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.out_dir = Path("build") / "test_validate"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        data = build_bda(
            Path("sdk/api/examples/hello_msgbox.c"),
            "ValHello",
            9,
            bundled_prefix() or "mipsel-none-elf-",
            None,
            (0, 0, 0),
        )
        self.good = self.out_dir / "ValHello.bda"
        self.good.write_bytes(data)

    def test_validate_generated_bda(self) -> None:
        report = validate_bda(self.good)

        self.assertTrue(report["ok"])
        self.assertEqual(report["title"], "ValHello")
        self.assertEqual(report["category"], 9)
        self.assertEqual(report["decoded_words"][0], 0x004B4242)
        self.assertEqual(report["entry_offset"], 0x95F8)
        self.assertEqual(report["entry_va"], 0x81C00020)
        self.assertEqual(report["runtime_file_base"], 0x81BF6A28)
        self.assertIsInstance(report["entry_code_word"], int)
        self.assertEqual(report["expected_file_size_minus_4"], self.good.stat().st_size - 4)
        self.assertEqual(report["expected_magic"], 0x004B4242)
        self.assertEqual(report["header_xor_key"], 0x44525744)
        self.assertEqual(report["checksum_offset"], 0x84)
        self.assertEqual(report["checksum_xor_key"], 0x322D464B)
        self.assertEqual(report["encoded_word_end"], 0x2C)
        self.assertEqual(report["title_offset"], 0x2C)
        self.assertEqual(report["title_size"], 16)
        self.assertEqual(report["category_offset"], 0x0C)
        self.assertEqual(report["min_icon_start"], 0x88)
        self.assertTrue(report["checksum_ok"])
        self.assertEqual(len(report["icon_ranges"]), 4)
        self.assertTrue(all(item["vx"] for item in report["icon_ranges"]))

    def test_detects_checksum_error(self) -> None:
        bad = self.out_dir / "BadChecksum.bda"
        data = bytearray(self.good.read_bytes())
        data[0x84] ^= 0x01
        bad.write_bytes(data)

        report = validate_bda(bad)

        self.assertFalse(report["ok"])
        self.assertIn("header checksum 不匹配", report["errors"])

    def test_detects_blank_entry_code(self) -> None:
        bad = self.out_dir / "BlankEntry.bda"
        data = bytearray(self.good.read_bytes())
        data[0x95F8:0x95FC] = b"\0\0\0\0"
        bad.write_bytes(data)

        report = validate_bda(bad)

        self.assertFalse(report["ok"])
        self.assertEqual(report["entry_code_word"], 0)
        self.assertTrue(
            any("entry code 0x95f8" in error and "空或未初始化" in error for error in report["errors"]),
            report["errors"],
        )

    def test_detects_entry_self_loop(self) -> None:
        bad = self.out_dir / "SelfLoopEntry.bda"
        data = bytearray(self.good.read_bytes())
        data[0x95F8:0x95FC] = bytes.fromhex("ffff0010")
        bad.write_bytes(data)

        report = validate_bda(bad)

        self.assertFalse(report["ok"])
        self.assertEqual(report["entry_code_word"], 0x1000FFFF)
        self.assertEqual(report["mips_beq_zero_zero_self"], 0x1000FFFF)
        self.assertTrue(
            any("entry code 0x95f8" in error and "入口自跳转" in error for error in report["errors"]),
            report["errors"],
        )

    def test_detects_truncated_entry_code(self) -> None:
        bad = self.out_dir / "ShortEntry.bda"
        bad.write_bytes(self.good.read_bytes()[:0x95FA])

        report = validate_bda(bad)

        self.assertFalse(report["ok"])
        self.assertIsNone(report["entry_code_word"])
        self.assertTrue(
            any("entry code 0x95f8 后不足 4 byte 指令" in error for error in report["errors"]),
            report["errors"],
        )

    def test_cli_text_output_keeps_common_tool_terms(self) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        output = subprocess.check_output(
            [sys.executable, "reverse/bda_validate.py", str(self.good)],
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertIn("checksum: ok", output)
        self.assertIn("entry VA: 0x81c00020", output)
        self.assertIn("runtime file base: 0x81bf6a28", output)
        self.assertRegex(output, r"entry code word: 0x[0-9a-f]{8}")
        self.assertIn("icon0:", output)
        self.assertIn("size=0x", output)
        self.assertIn("vx=True", output)

    def test_cli_json_output_has_stable_debug_fields(self) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        output = subprocess.check_output(
            [sys.executable, "reverse/bda_validate.py", str(self.good), "--json"],
            text=True,
            encoding="utf-8",
            env=env,
        )
        report = json.loads(output)
        self.assertTrue(report["ok"])
        self.assertEqual(report["decoded_words"][0], 0x004B4242)
        self.assertEqual(report["entry_va"], 0x81C00020)
        self.assertEqual(report["runtime_file_base"], 0x81BF6A28)
        self.assertIsInstance(report["entry_code_word"], int)
        self.assertEqual(report["expected_file_size_minus_4"], self.good.stat().st_size - 4)
        self.assertEqual(report["expected_magic"], 0x004B4242)
        self.assertEqual(report["expected_word04"], 0x5D245562)
        self.assertEqual(report["expected_version"], 0x01000102)
        self.assertEqual(report["header_xor_key"], 0x44525744)
        self.assertEqual(report["checksum_offset"], 0x84)
        self.assertEqual(report["checksum_xor_key"], 0x322D464B)
        self.assertEqual(report["encoded_word_end"], 0x2C)
        self.assertEqual(report["title_offset"], 0x2C)
        self.assertEqual(report["title_size"], 16)
        self.assertEqual(report["category_offset"], 0x0C)
        self.assertEqual(report["min_icon_start"], 0x88)
        self.assertEqual(report["mips_beq_zero_zero_self"], 0x1000FFFF)
        self.assertEqual(report["errors"], [])


if __name__ == "__main__":
    unittest.main()
