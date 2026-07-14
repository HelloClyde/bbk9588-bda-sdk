from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bda_api_catalog import inventory_totals, parse_sdk_defines, write_markdown


class BdaApiCatalogTest(unittest.TestCase):
    def test_parse_sdk_defines_skips_runtime_table_addresses(self) -> None:
        defs = parse_sdk_defines(Path("sdk/api/bda_sdk.h"))

        self.assertIn(("GUI", 0x2B8), defs)
        self.assertIn("BDA_GUI_MSGBOX", defs[("GUI", 0x2B8)])
        self.assertNotIn(("GUI", 0x81C00004), defs)
        self.assertNotIn(("FS", 0x81C00008), defs)
        self.assertNotIn(("SYS", 0x000), defs)
        self.assertNotIn(("SYS", 0x010), defs)
        self.assertNotIn(("SYS", 0x578), defs)

        names = {name for values in defs.values() for name in values}
        self.assertNotIn("BDA_SYS_ALARM_SLOT_TAG_OFFSET", names)
        self.assertNotIn("BDA_SYS_ALARM_ENABLE_FLAG_OFFSET", names)
        self.assertNotIn("BDA_SYS_ALARM_DB_FIRST_RECORD_OFFSET", names)
        self.assertNotIn("BDA_SYS_ALARM_DUE_MISS_TAG", names)
        self.assertIn("BDA_SYS_ALARM_SET_LIKE", names)

    def test_write_markdown_keeps_common_table_terms(self) -> None:
        defs = {("GUI", 0x2B8): ["BDA_GUI_MSGBOX"]}
        totals, apps = inventory_totals(Path("reverse/reports/bda_inventory.json"))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "api_catalog.md"
            write_markdown(out, defs, totals, apps)
            text = out.read_text(encoding="utf-8")

        self.assertIn("| Table | Offset | SDK name | Raw calls same offset | App count | Confidence | Notes |", text)
        self.assertIn("原机 BDA call inventory", text)
        self.assertIn("BDA_GUI_MSGBOX", text)
        self.assertNotIn("TABLE_ADDR", text)
        self.assertNotIn("SDK 名称", text)
        self.assertNotIn("中文说明", text)

    def test_checked_in_catalog_matches_generator_output(self) -> None:
        defs = parse_sdk_defines(Path("sdk/api/bda_sdk.h"))
        totals, apps = inventory_totals(Path("reverse/reports/bda_inventory.json"))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "api_catalog.md"
            write_markdown(out, defs, totals, apps)
            generated = out.read_text(encoding="utf-8")

        checked_in = Path("sdk/doc/api_catalog.md").read_text(encoding="utf-8")
        self.assertEqual(generated, checked_in)


if __name__ == "__main__":
    unittest.main()
