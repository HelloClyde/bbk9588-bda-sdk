from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bda_packer.build import (
    build_bda,
    bundled_prefix,
    compiler_include_dirs,
    find_tool,
    sdk_include_dir,
)
from bda_packer.header import BdaHeaderFields, decoded_header_words, verify, write_header
from bda_packer.validate import validate_bda


class StandalonePackerTest(unittest.TestCase):
    def test_custom_include_dirs_precede_stable_sdk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            custom = Path(temp_dir) / "candidate"
            custom.mkdir()
            directories = compiler_include_dirs([custom])

        self.assertEqual(directories[0], custom.resolve())
        self.assertEqual(directories[-1], sdk_include_dir().resolve())

    def test_missing_custom_include_dir_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"
            with self.assertRaisesRegex(SystemExit, "include 目录不存在"):
                compiler_include_dirs([missing])

    def test_public_header_enforces_dynamic_verification_boundary(self) -> None:
        include_dir = sdk_include_dir()
        header_text = (include_dir / "bda_sdk.h").read_text(encoding="utf-8")
        policy_text = (
            Path(__file__).resolve().parents[1]
            / "docs"
            / "verified"
            / "public_api_policy.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Admission rule", header_text)
        self.assertIn("动态验证", policy_text)
        self.assertNotIn("_like", header_text.lower())
        self.assertNotIn("bda_gui_touch_position_like", header_text)
        self.assertNotIn("bda_gui_create_window_like", header_text)
        self.assertNotIn("bda_fs_mkdir_like", header_text)
        for public_name in [
            "bda_alloc",
            "bda_free",
            "bda_fs_seek_raw",
            "bda_fs_mkdir",
            "bda_fs_chdir",
            "bda_fs_findfirst",
            "bda_fs_findnext",
            "bda_fs_findclose",
            "bda_gui_render_picture",
        ]:
            self.assertIn(public_name, header_text)

    def test_header_is_built_from_firmware_constants(self) -> None:
        data = bytearray(b"\0" * 0x200)
        fields = BdaHeaderFields(
            category=4,
            file_size_minus_4=len(data) - 4,
            entry_offset=0x100,
            icon_start=0x88,
            icon0_size=0,
            icon1_size=0,
            icon2_size=0,
            icon3_size=0,
        )
        write_header(data, fields, "HelloWorld")

        report = verify(data)
        self.assertTrue(report["checksum_ok"])
        self.assertEqual(report["title"], "HelloWorld")
        self.assertEqual(decoded_header_words(data)[0], 0x004B4242)
        self.assertEqual(decoded_header_words(data)[1], 0x5D245562)

    def test_compiles_and_validates_freestanding_c(self) -> None:
        prefix = bundled_prefix() or "mipsel-none-elf-"
        try:
            find_tool(prefix, "gcc")
            find_tool(prefix, "objcopy")
        except SystemExit as exc:
            self.skipTest(str(exc))

        header = sdk_include_dir() / "bda_sdk.h"
        self.assertTrue(header.is_file())
        self.assertEqual(header, Path("sdk/include/bda_sdk.h").resolve())
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "hello.c"
            output = root / "HelloWorld.bda"
            source.write_text(
                '#include "bda_sdk.h"\n'
                '__attribute__((section(".text.bda_main")))\n'
                'int bda_main(void) {\n'
                '    bda_msgbox("HelloWorld", "HelloWorld");\n'
                '    return 0;\n'
                '}\n',
                encoding="ascii",
            )
            output.write_bytes(build_bda(source, "HelloWorld", 4, prefix, None, (0, 0, 0)))

            report = validate_bda(output)
            self.assertTrue(report["ok"], report)
            self.assertEqual(report["entry_offset"], 0x95F8)
            self.assertEqual(report["entry_va"], 0x81C00020)
            self.assertEqual(report["title"], "HelloWorld")
            self.assertEqual(report["category"], 4)

            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "bda_sdk.h").write_text(
                "static inline int bda_candidate_probe(void) { return 23; }\n",
                encoding="ascii",
            )
            custom_source = root / "custom_include.c"
            custom_output = root / "CustomInclude.bda"
            custom_source.write_text(
                '#include "bda_sdk.h"\n'
                '__attribute__((section(".text.bda_main")))\n'
                'int bda_main(void) { return bda_candidate_probe(); }\n',
                encoding="ascii",
            )
            custom_output.write_bytes(
                build_bda(
                    custom_source,
                    "CustomInclude",
                    4,
                    prefix,
                    None,
                    (0, 0, 0),
                    [candidate],
                )
            )
            custom_report = validate_bda(custom_output)
            self.assertTrue(custom_report["ok"], custom_report)


if __name__ == "__main__":
    unittest.main()
