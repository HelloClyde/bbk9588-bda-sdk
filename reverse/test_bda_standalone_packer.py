from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bda_packer.build import build_bda, bundled_prefix, find_tool, sdk_include_dir
from bda_packer.header import BdaHeaderFields, decoded_header_words, verify, write_header
from bda_packer.validate import validate_bda


class StandalonePackerTest(unittest.TestCase):
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

        self.assertTrue((sdk_include_dir() / "bda_sdk.h").is_file())
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


if __name__ == "__main__":
    unittest.main()
