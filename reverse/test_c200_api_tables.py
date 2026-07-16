from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bda_api_catalog import parse_sdk_defines
from c200_api_tables import build_catalog, write_markdown
from c200_api_disasm import disasm_function, find_row, in_c200, va_to_off
from system_bin_probe import find_c200


class C200ApiTablesTest(unittest.TestCase):
    def test_named_sdk_offsets_resolve_inside_c200_when_firmware_exists(self) -> None:
        try:
            find_c200(Path("."))
        except SystemExit as exc:
            self.skipTest(str(exc))

        catalog = build_catalog(Path("."), Path("reverse/bda_research_sdk.h"))
        rows = catalog["rows"]
        unknown_rows = catalog["unknown_candidate_rows"]

        self.assertEqual(len(rows), len(parse_sdk_defines(Path("reverse/bda_research_sdk.h"))))
        self.assertGreater(len(unknown_rows), 0)
        self.assertTrue(all(row["target_in_c200"] for row in rows))
        self.assertTrue(all(row["target_in_c200"] for row in unknown_rows))
        unknown_keys = {(str(row["table"]), int(row["offset"])) for row in unknown_rows}
        self.assertNotIn(("SYS", 0x040), unknown_keys)
        self.assertNotIn(("FS", 0x000), unknown_keys)
        self.assertNotIn(("GUI", 0x040), unknown_keys)
        self.assertNotIn(("MEM", 0x000), unknown_keys)
        self.assertNotIn(("MEM", 0x004), unknown_keys)

        by_name = {name: row for row in rows for name in row["sdk_names"]}
        self.assertEqual(by_name["BDA_GUI_MSGBOX"]["target_va"], 0x800C6544)
        self.assertEqual(by_name["BDA_GUI_OBJECT_FLAGS_CLEAR_LIKE"]["target_va"], 0x800CE4C8)
        self.assertEqual(by_name["BDA_GUI_OBJECT_FLAGS_OR_LIKE"]["target_va"], 0x800CE4FC)
        self.assertEqual(by_name["BDA_GUI_OBJECT_FLAGS_GET_LIKE"]["target_va"], 0x800CE4A0)
        self.assertEqual(by_name["BDA_GUI_ACCUMULATE_ORIGIN_LIKE"]["target_va"], 0x800CE26C)
        self.assertEqual(by_name["BDA_GUI_SUBTRACT_ORIGIN_LIKE"]["target_va"], 0x800CC664)
        self.assertEqual(by_name["BDA_GUI_RECT_CONTAINS_LIKE"]["target_va"], 0x800C0818)
        self.assertEqual(by_name["BDA_GUI_OBJECT_UPDATE3_LIKE"]["target_va"], 0x800DE150)
        self.assertEqual(by_name["BDA_GUI_OBJECT_UPDATE2_LIKE"]["target_va"], 0x800DE190)
        self.assertEqual(by_name["BDA_GUI_OBJECT_PAIR_EXISTS_LIKE"]["target_va"], 0x800DE0A8)
        self.assertEqual(by_name["BDA_GUI_OBJECT_USERDATA0_GET_LIKE"]["target_va"], 0x800CE558)
        self.assertEqual(by_name["BDA_GUI_OBJECT_USERDATA0_SET_LIKE"]["target_va"], 0x800CE580)
        self.assertEqual(by_name["BDA_GUI_OBJECT_USERDATA1_GET_LIKE"]["target_va"], 0x800CE5B0)
        self.assertEqual(by_name["BDA_GUI_OBJECT_USERDATA1_SET_LIKE"]["target_va"], 0x800CE5D8)
        self.assertEqual(by_name["BDA_GUI_OBJECT_PAYLOAD_WORD_GET_LIKE"]["target_va"], 0x800CE608)
        self.assertEqual(by_name["BDA_GUI_OBJECT_PAYLOAD_WORD_SET_LIKE"]["target_va"], 0x800CE644)
        self.assertEqual(by_name["BDA_GUI_OBJECT_RESOURCE_PTR_GET_LIKE"]["target_va"], 0x800CE7DC)
        self.assertEqual(by_name["BDA_GUI_OBJECT_CALLBACK_PTR_GET_LIKE"]["target_va"], 0x800CE780)
        self.assertEqual(by_name["BDA_GUI_OBJECT_CALLBACK_PTR_SET_LIKE"]["target_va"], 0x800CE7A8)
        self.assertEqual(by_name["BDA_GUI_ACTIVE_FRAME_GET_LIKE"]["target_va"], 0x800CAE04)
        self.assertEqual(by_name["BDA_GUI_OBJECT_RECT_LIKE"]["target_va"], 0x800CE3C8)
        self.assertEqual(by_name["BDA_GUI_SURFACE_FLUSH_LIKE"]["target_va"], 0x800BD584)
        self.assertEqual(by_name["BDA_GUI_DISPLAY_METRIC_LIKE"]["target_va"], 0x800BC8FC)
        self.assertEqual(by_name["BDA_GUI_COMPAT_CONTEXT_CREATE_LIKE"]["target_va"], 0x800BD100)
        self.assertEqual(by_name["BDA_GUI_SET_FILL_COLOR_LIKE"]["target_va"], 0x800B2C7C)
        self.assertEqual(by_name["BDA_GUI_SELECT_DRAW_OBJECT_LIKE"]["target_va"], 0x800B2D40)
        self.assertEqual(by_name["BDA_GUI_LINE_TO_LIKE"]["target_va"], 0x800B715C)
        self.assertEqual(by_name["BDA_GUI_MOVE_TO_LIKE"]["target_va"], 0x800BC328)
        self.assertEqual(by_name["BDA_GUI_CIRCLE_LIKE"]["target_va"], 0x800B7494)
        self.assertEqual(by_name["BDA_GUI_RECTANGLE_LIKE"]["target_va"], 0x800B76D8)
        self.assertEqual(by_name["BDA_GUI_CURRENT_FONT_LIKE"]["target_va"], 0x800BF744)
        self.assertEqual(by_name["BDA_GUI_FONT_CELL_WIDTH_LIKE"]["target_va"], 0x800C1C68)
        self.assertEqual(by_name["BDA_GUI_FONT_CELL_HEIGHT_LIKE"]["target_va"], 0x800C1C80)
        self.assertEqual(by_name["BDA_GUI_CAPTURE_REGION_ALLOC_LIKE"]["target_va"], 0x800C0BF0)
        self.assertEqual(by_name["BDA_GUI_RENDER_COPY_LIKE"]["target_va"], 0x800B3124)
        self.assertEqual(by_name["BDA_GUI_RECT_PREPARE_LIKE"]["target_va"], 0x800C0410)
        self.assertEqual(by_name["BDA_GUI_SCREEN_WIDTH_LIKE"]["target_va"], 0x80024708)
        self.assertEqual(by_name["BDA_FS_OPEN"]["target_va"], 0x80170B68)
        self.assertEqual(by_name["BDA_FS_EOF_LIKE"]["target_va"], 0x8017AC84)
        self.assertEqual(by_name["BDA_FS_ERROR_LIKE"]["target_va"], 0x8017ACFC)
        self.assertEqual(by_name["BDA_FS_CLEAR_ERROR_LIKE"]["target_va"], 0x8017AD70)
        self.assertEqual(by_name["BDA_FS_RENAME_LIKE"]["target_va"], 0x80171D24)
        self.assertEqual(by_name["BDA_FS_GETCWD_LIKE"]["target_va"], 0x801700D0)
        self.assertEqual(by_name["BDA_FS_PATH_INFO_LIKE"]["target_va"], 0x8017A0D8)
        self.assertEqual(by_name["BDA_FS_RMDIR_LIKE"]["target_va"], 0x80172520)
        self.assertEqual(by_name["BDA_FS_MEDIA_PRESENT_RAW_LIKE"]["target_va"], 0x8017952C)
        self.assertEqual(by_name["BDA_MEM_TRACK_ALLOC_LIKE"]["target_va"], 0x80058574)
        self.assertEqual(by_name["BDA_MEM_TRACK_FREE_LIKE"]["target_va"], 0x80058618)
        self.assertEqual(by_name["BDA_MEM_TRACK_BEGIN_LIKE"]["target_va"], 0x80058554)
        self.assertEqual(by_name["BDA_MEM_TRACK_REPORT_LIKE"]["target_va"], 0x8005868C)
        self.assertEqual(by_name["BDA_MEM_TRACK_FINISH_LIKE"]["target_va"], 0x80058750)
        self.assertEqual(by_name["BDA_MEM_TRACK_RETAIN_LIKE"]["target_va"], 0x80058820)
        self.assertEqual(by_name["BDA_MEM_TRACK_RELEASE_LIKE"]["target_va"], 0x800588B8)
        self.assertEqual(by_name["BDA_MEM_ALLOC"]["target_va"], 0x80007648)
        self.assertEqual(by_name["BDA_MEM_CALLOC_LIKE"]["target_va"], 0x800065BC)
        self.assertEqual(by_name["BDA_MEM_REALLOC_LIKE"]["target_va"], 0x800077B0)
        self.assertEqual(by_name["BDA_RES_ENTRY_094_LIKE"]["target_va"], 0x800098C0)
        self.assertEqual(by_name["BDA_SYS_KEYCODE_RAW_LIKE"]["target_va"], 0x8001B464)
        self.assertEqual(by_name["BDA_SYS_AUDIO_STATE_LIKE"]["target_va"], 0x8001DAD4)
        self.assertEqual(by_name["BDA_SYS_PACKAGE_SOUND_OP40_LIKE"]["target_va"], 0x8018921C)
        self.assertEqual(by_name["BDA_SYS_PACKAGE_SOUND_OP44_LIKE"]["target_va"], 0x80189248)
        self.assertNotIn("BDA_SYS_PACKAGE_SOUND_LOAD_LIKE", by_name)
        self.assertNotIn("BDA_GUI_SCREEN_MODE_QUERY_LIKE", by_name)
        self.assertNotIn("BDA_SYS_ALARM_COMMIT_LIKE", by_name)
        self.assertNotIn("BDA_SYS_ALARM_SLOT_TAG_OFFSET", by_name)
        self.assertNotIn("BDA_SYS_ALARM_ENABLE_FLAG_OFFSET", by_name)
        self.assertNotIn("BDA_SYS_ALARM_DB_FIRST_RECORD_OFFSET", by_name)

        fs064 = find_row(catalog, None, "FS", 0x064)
        self.assertEqual(fs064["target_va"], 0x8017AFB4)
        self.assertEqual(fs064["sdk_names"], [])
        self.assertTrue(fs064["target_in_c200"])
        self.assertIn("低层 block read support helper", fs064["candidate_note"])
        self.assertIn("volume/index", fs064["candidate_note"])
        self.assertIn("不公开 wrapper", fs064["candidate_note"])

        fs068 = find_row(catalog, None, "FS", 0x068)
        self.assertEqual(fs068["target_va"], 0x8017A200)
        self.assertEqual(fs068["sdk_names"], [])
        self.assertTrue(fs068["target_in_c200"])
        self.assertIn("file-object block read helper", fs068["candidate_note"])
        self.assertIn("a3 是内部 file object/descriptor", fs068["candidate_note"])

        sys050 = find_row(catalog, None, "SYS", 0x050)
        self.assertEqual(sys050["target_va"], 0x8018EF04)
        self.assertEqual(sys050["sdk_names"], [])
        self.assertTrue(sys050["target_in_c200"])
        self.assertIn("ret1/stub", sys050["candidate_note"])

        sys084 = find_row(catalog, None, "SYS", 0x084)
        self.assertEqual(sys084["target_va"], 0x8001B6A8)
        self.assertEqual(sys084["sdk_names"], [])
        self.assertIn("不是 input reset/init/poll", sys084["candidate_note"])

        res004 = find_row(catalog, None, "RES", 0x004)
        self.assertEqual(res004["target_va"], 0x8013AAF0)
        self.assertEqual(res004["sdk_names"], [])
        self.assertIn("不是 DLX loader", res004["candidate_note"])

        sys0a8 = find_row(catalog, None, "SYS", 0x0A8)
        self.assertEqual(sys0a8["target_va"], 0x8001415C)
        self.assertEqual(sys0a8["sdk_names"], [])
        self.assertTrue(sys0a8["target_in_c200"])

    def test_markdown_keeps_common_table_terms(self) -> None:
        try:
            find_c200(Path("."))
        except SystemExit as exc:
            self.skipTest(str(exc))

        catalog = build_catalog(Path("."), Path("reverse/bda_research_sdk.h"))
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "system_api_tables.md"
            write_markdown(catalog, out)
            text = out.read_text(encoding="utf-8")

        self.assertIn("## Runtime Table Seeds", text)
        self.assertIn("| Table | Runtime slot | C200 table VA | Notes |", text)
        self.assertIn("| Table | Offset | SDK name | entry VA | function VA | in C200 | first insn | Notes |", text)
        self.assertIn("## Unnamed Hot Offset C200 Candidates", text)
        self.assertIn("Candidate status", text)
        self.assertIn("table+offset", text)
        self.assertIn("同一 offset 在某张 table 已命名，不代表其他 table", text)
        self.assertIn("不公开 wrapper", text)
        self.assertIn("不是 DLX loader", text)
        self.assertIn("function-level ABI", text)
        self.assertNotIn("运行时槽位", text)
        self.assertNotIn("函数 VA", text)
        self.assertNotIn("中文说明", text)

    def test_checked_in_system_table_matches_generator_output(self) -> None:
        try:
            find_c200(Path("."))
        except SystemExit as exc:
            self.skipTest(str(exc))

        catalog = build_catalog(Path("."), Path("reverse/bda_research_sdk.h"))
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "system_api_tables.md"
            write_markdown(catalog, out)
            generated = out.read_text(encoding="utf-8")

        checked_in = Path("reverse/docs/system_api_tables.md").read_text(encoding="utf-8")
        self.assertEqual(generated, checked_in)

    def test_disasm_helper_finds_named_api_with_note(self) -> None:
        try:
            c200 = find_c200(Path("."))
        except SystemExit as exc:
            self.skipTest(str(exc))

        catalog = build_catalog(Path("."), Path("reverse/bda_research_sdk.h"))
        row = find_row(catalog, "BDA_GUI_MSGBOX", None, None)

        self.assertEqual(row["table"], "GUI")
        self.assertEqual(row["offset"], 0x2B8)
        self.assertEqual(row["target_va"], 0x800C6544)
        self.assertIn("message box", row["note"])

        lines = disasm_function(c200.read_bytes(), int(row["target_va"]), 0x10)
        self.assertTrue(lines[0].startswith("800c6544: addiu"))

    def test_direct_va_disasm_supports_internal_helpers(self) -> None:
        try:
            c200 = find_c200(Path("."))
        except SystemExit as exc:
            self.skipTest(str(exc))

        data = c200.read_bytes()
        self.assertTrue(in_c200(data, 0x8017E1A0))
        self.assertEqual(va_to_off(0x8017E1A0), 0x17A1A0)
        lines = disasm_function(data, 0x8017E1A0, 0x20)
        self.assertTrue(lines[0].startswith("8017e1a0: addiu"))


if __name__ == "__main__":
    unittest.main()
