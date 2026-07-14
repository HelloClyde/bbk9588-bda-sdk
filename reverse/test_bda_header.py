from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bda_header import (
    BdaHeaderFields,
    CHECKSUM_OFF,
    CHECKSUM_XOR_KEY,
    decoded_header_words,
    encode_word,
    get_title,
    put_encoded_word,
    write_header,
    verify,
)
from bda_layout import analyze as analyze_layout
from bda_compile_c import build_bda, bundled_prefix, find_tool, parse_bg
import bda_set_icon_png
import dlx_build
from bda_validate import validate_bda


TOOLCHAIN_PREFIX = bundled_prefix() or "mipsel-none-elf-"


class BdaHeaderTest(unittest.TestCase):
    def test_compile_user_errors_are_chinese(self) -> None:
        with self.assertRaisesRegex(Exception, "背景色必须是 RRGGBB 六位十六进制"):
            parse_bg("bad")

        with self.assertRaises(SystemExit) as cm:
            find_tool("Z:/definitely-missing/mipsel-none-elf-", "gcc")
        message = str(cm.exception)
        self.assertIn("未找到", message)
        self.assertIn("scripts\\setup_toolchain.ps1", message)

    def test_build_clis_report_missing_source_in_chinese(self) -> None:
        missing = Path("build") / "test_missing_source" / "missing.c"
        existing_source = Path("sdk/api/examples/hello_msgbox.c")
        missing_icon = Path("build") / "test_missing_source" / "missing.png"
        commands = [
            [
                sys.executable,
                "reverse/bda_compile_c.py",
                str(missing),
                "--title",
                "Missing",
                "--category",
                "9",
                "-o",
                "build/test_missing_source/MissingCompile.bda",
            ],
            [
                sys.executable,
                "reverse/bda_compile_c.py",
                str(existing_source),
                "--icon-png",
                str(missing_icon),
                "--title",
                "MissingIcon",
                "--category",
                "9",
                "-o",
                "build/test_missing_source/MissingIconBuild.bda",
            ],
        ]
        expected_phrases = [
            "源码不存在",
            "图标 PNG 不存在",
        ]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        for command, phrase in zip(commands, expected_phrases):
            proc = subprocess.run(
                command,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=env,
            )
            self.assertNotEqual(proc.returncode, 0, command)
            self.assertIn(phrase, proc.stderr + proc.stdout)

    def test_compile_failures_do_not_show_python_traceback(self) -> None:
        prefix = bundled_prefix() or "mipsel-none-elf-"
        try:
            find_tool(prefix, "gcc")
        except SystemExit as exc:
            self.skipTest(str(exc))

        out_dir = Path("build") / "test_compile_failure"
        out_dir.mkdir(parents=True, exist_ok=True)
        bad_source = out_dir / "bad.c"
        bad_source.write_text("int bda_main(void) { return ;\n", encoding="ascii")

        commands = [(
            [
                sys.executable,
                "reverse/bda_compile_c.py",
                str(bad_source),
                "--prefix",
                prefix,
                "--title",
                "Bad",
                "--category",
                "9",
                "-o",
                str(out_dir / "BadCompile.bda"),
            ],
            "C 编译失败",
        )]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        for command, phrase in commands:
            proc = subprocess.run(
                command,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env=env,
            )
            output = proc.stderr + proc.stdout
            self.assertNotEqual(proc.returncode, 0, command)
            self.assertIn(phrase, output)
            self.assertNotIn("Traceback", output)

    def test_common_background_color_errors_are_chinese(self) -> None:
        parsers = [
            parse_bg,
            bda_set_icon_png.parse_bg,
            dlx_build.parse_bg,
        ]
        for parser in parsers:
            with self.assertRaisesRegex(Exception, "背景色必须是 RRGGBB 六位十六进制"):
                parser("bad")

    def test_write_header_encodes_fields_and_checksum(self) -> None:
        data = bytearray(b"\xff" * 0x120)
        fields = BdaHeaderFields(
            category=9,
            file_size_minus_4=len(data) - 4,
            entry_offset=0x95F8,
            icon_start=0x88,
            icon0_size=0x3218,
            icon1_size=0x3218,
            icon2_size=0x16E0,
            icon3_size=0x1A60,
        )

        write_header(data, fields, "测试BDA")

        words = decoded_header_words(data)
        self.assertEqual(words[:11], list(fields.words()))
        self.assertEqual(get_title(data), "测试BDA")
        self.assertEqual(int.from_bytes(data[0x0C:0x10], "little"), encode_word(9))
        self.assertEqual(data[0x3C:CHECKSUM_OFF], b"\0" * (CHECKSUM_OFF - 0x3C))

        report = verify(data)
        self.assertEqual(report["title"], "测试BDA")
        self.assertEqual(report["category"], 9)
        self.assertEqual(report["file_size_minus_4"], len(data) - 4)
        self.assertEqual(report["entry_offset"], 0x95F8)
        self.assertTrue(report["checksum_ok"])

        decoded_checksum = int.from_bytes(data[CHECKSUM_OFF : CHECKSUM_OFF + 4], "little") ^ CHECKSUM_XOR_KEY
        self.assertGreater(decoded_checksum, 0)

    def test_title_rejects_overlong_gbk(self) -> None:
        data = bytearray(b"\0" * 0x120)
        fields = BdaHeaderFields(file_size_minus_4=len(data) - 4)
        with self.assertRaises(ValueError):
            write_header(data, fields, "超过十六字节的标题")

    def test_write_header_rejects_out_of_range_u32_fields(self) -> None:
        data = bytearray(b"\0" * 0x120)
        cases = [
            (BdaHeaderFields(file_size_minus_4=-1), "file_size_minus_4"),
            (BdaHeaderFields(entry_offset=0x1_0000_0000), "entry_offset"),
            (BdaHeaderFields(icon0_size=-0x20), "icon0_size"),
            (BdaHeaderFields(category=0x1_0000_0000), "category"),
        ]
        for fields, field_name in cases:
            with self.subTest(field=field_name):
                with self.assertRaisesRegex(ValueError, f"header field {field_name}"):
                    write_header(data, fields, "Bad")

    def test_set_category_cli_rejects_out_of_range_u32(self) -> None:
        out_dir = Path("build") / "test_bda_header_category_range"
        out_dir.mkdir(parents=True, exist_ok=True)
        source = out_dir / "Source.bda"
        data = bytearray(b"\0" * 0x120)
        write_header(data, BdaHeaderFields(file_size_minus_4=len(data) - 4), "Src")
        source.write_bytes(data)

        for value in ("-1", "0x100000000"):
            with self.subTest(category=value):
                output = out_dir / f"Bad_{value.replace('x', '_').replace('-', 'neg')}.bda"
                proc = subprocess.run(
                    [
                        sys.executable,
                        "reverse/bda_set_category.py",
                        str(source),
                        "-o",
                        str(output),
                        "--category",
                        value,
                    ],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("header field category", proc.stderr)
                self.assertIn("outside u32 range", proc.stderr)
                self.assertFalse(output.exists())

    def test_validate_rejects_bad_fixed_header_words_and_icon_start(self) -> None:
        out_dir = Path("build") / "test_bda_header_validation"
        out_dir.mkdir(parents=True, exist_ok=True)
        bad = out_dir / "BadHeader.bda"

        data = bytearray(b"\0" * 0x200)
        fields = BdaHeaderFields(
            file_size_minus_4=len(data) - 4,
            entry_offset=0x100,
            icon_start=0x40,
            icon0_size=0,
            icon1_size=0,
            icon2_size=0,
            icon3_size=0,
        )
        write_header(data, fields, "Bad")
        put_encoded_word(data, 0x00, 0x12345678)
        put_encoded_word(data, 0x04, 0)
        put_encoded_word(data, 0x08, 0)
        bad.write_bytes(data)

        report = validate_bda(bad)
        joined_errors = "\n".join(report["errors"])
        self.assertFalse(report["ok"], report)
        self.assertIn("header magic", joined_errors)
        self.assertIn("header word04", joined_errors)
        self.assertIn("header version", joined_errors)
        self.assertIn("icon start offset", joined_errors)
        self.assertIn("小于 header 结束", joined_errors)

    def test_title_and_category_cli_keep_header_valid(self) -> None:
        out_dir = Path("build") / "test_bda_header_cli"
        out_dir.mkdir(parents=True, exist_ok=True)
        original = out_dir / "Original.bda"
        titled = out_dir / "Titled.bda"
        categorized = out_dir / "Categorized.bda"

        original.write_bytes(
            build_bda(
                Path("sdk/api/examples/hello_msgbox.c"),
                "Orig",
                9,
                TOOLCHAIN_PREFIX,
                None,
                (0, 0, 0),
            )
        )
        subprocess.check_call(
            [
                sys.executable,
                "reverse/bda_set_title.py",
                str(original),
                "-o",
                str(titled),
                "--title",
                "标题OK",
            ]
        )
        subprocess.check_call(
            [
                sys.executable,
                "reverse/bda_set_category.py",
                str(titled),
                "-o",
                str(categorized),
                "--category",
                "4",
            ]
        )

        report = validate_bda(categorized)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["title"], "标题OK")
        self.assertEqual(report["category"], 4)
        self.assertTrue(report["checksum_ok"])

    def test_fix_header_checksum_exact_does_not_require_template(self) -> None:
        out_dir = Path("build") / "test_bda_fix_checksum"
        out_dir.mkdir(parents=True, exist_ok=True)
        bad = out_dir / "BadChecksum.bda"
        fixed = out_dir / "FixedChecksum.bda"
        data = build_bda(Path("sdk/api/examples/hello_msgbox.c"), "FixMe", 9, TOOLCHAIN_PREFIX, None, (0, 0, 0))
        data[0x84:0x88] = b"\0\0\0\0"
        bad.write_bytes(data)
        self.assertFalse(validate_bda(bad)["checksum_ok"])

        output = subprocess.check_output(
            [
                sys.executable,
                "reverse/bda_fix_header_checksum.py",
                str(bad),
                "-o",
                str(fixed),
            ],
            text=True,
            encoding="utf-8",
        )
        self.assertIn("mode=exact", output)
        self.assertIn("patched_raw84=", output)
        self.assertNotIn("template_sum=", output)
        report = validate_bda(fixed)
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["checksum_ok"])

    def test_layout_falls_back_to_decoded_header_entry(self) -> None:
        out_dir = Path("build") / "test_bda_layout"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "NoSig.bda"
        path.write_bytes(
            build_bda(
                Path("sdk/api/examples/hello_msgbox.c"),
                "NoSig",
                9,
                TOOLCHAIN_PREFIX,
                None,
                (0, 0, 0),
            )
        )

        report = analyze_layout(path)
        self.assertEqual(report["entry_offset"], 0x95F8)
        self.assertEqual(report["entry_source"], "header")
        self.assertEqual(report["runtime_entry_va"], 0x81C00020)
        self.assertEqual(report["runtime_file_base"], 0x81BF6A28)


if __name__ == "__main__":
    unittest.main()
