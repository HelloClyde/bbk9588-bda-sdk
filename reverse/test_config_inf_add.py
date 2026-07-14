from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config_inf_add import (
    ENTRY_SIZE,
    ENTRY_START,
    TRAILER_OFF,
    add_or_replace_entry,
    checksum,
    max_full_slots,
    parse_entries,
    read_count,
    stored_checksum,
)


def make_config(names: list[str], slots: int = 3) -> bytes:
    size = TRAILER_OFF + 4
    data = bytearray(b"\0" * size)
    data[0:2] = len(names).to_bytes(2, "little")
    data[2:4] = len(names).to_bytes(2, "little")
    for index, name in enumerate(names):
        off = ENTRY_START + index * ENTRY_SIZE
        data[off] = 1
        encoded = name.encode("gbk")
        data[off + 1 : off + 1 + len(encoded)] = encoded
    # Keep synthetic capacity explicit by making sure requested slots fit.
    self_slots = max_full_slots(data)
    if slots != self_slots:
        raise AssertionError(f"fixture slots={self_slots}, expected {slots}")
    value = checksum(data)
    data[TRAILER_OFF : TRAILER_OFF + 4] = value.to_bytes(4, "little")
    return bytes(data)


class ConfigInfAddTest(unittest.TestCase):
    def test_config_tool_help_is_chinese(self) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        output = subprocess.check_output(
            [sys.executable, "reverse/config_inf_add.py", "--help"],
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertIn("位置参数", output)
        self.assertIn("选项", output)
        self.assertIn("显示帮助并退出", output)
        self.assertIn("输出 Config.inf 路径", output)
        self.assertIn("写入前列出现有 entries", output)
        self.assertNotIn("positional arguments", output)
        self.assertNotIn("show this help message and exit", output)

    def test_config_tool_write_output_keeps_common_tool_terms(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            root = Path(td)
            src = root / "Config.inf"
            out = root / "Out.inf"
            src.write_bytes(make_config(["三国霸业.bda", "电子图书.bda"]))
            output = subprocess.check_output(
                [
                    sys.executable,
                    "reverse/config_inf_add.py",
                    str(src),
                    "--name",
                    "RectDemo.bda",
                    "-o",
                    str(out),
                ],
                text=True,
                encoding="utf-8",
                env=env,
            )
            self.assertTrue(out.is_file())
        self.assertIn("wrote ", output)
        self.assertIn("count=3 slots=3", output)
        self.assertIn("slot=0x37b name=RectDemo.bda", output)
        self.assertIn("checksum=0x", output)

    def test_config_probe_help_is_chinese(self) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        output = subprocess.check_output(
            [sys.executable, "reverse/config_inf_probe.py", "--help"],
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertIn("位置参数", output)
        self.assertIn("选项", output)
        self.assertIn("显示帮助并退出", output)
        self.assertIn("要检查的 Config.inf 路径", output)
        self.assertNotIn("positional arguments", output)
        self.assertNotIn("show this help message and exit", output)

    def test_parse_entries_and_checksum(self) -> None:
        data = make_config(["三国霸业.bda", "电子图书.bda", "我的相册.bda"])
        entries = parse_entries(data)

        self.assertEqual(read_count(data), 3)
        self.assertEqual(max_full_slots(data), 3)
        self.assertEqual([entry.name for entry in entries], ["三国霸业.bda", "电子图书.bda", "我的相册.bda"])
        self.assertEqual(stored_checksum(data), checksum(data))

    def test_append_when_full_raises(self) -> None:
        data = make_config(["三国霸业.bda", "电子图书.bda", "我的相册.bda"])
        with self.assertRaises(ValueError):
            add_or_replace_entry(data, "RectDemo.bda")

    def test_replace_existing_slot(self) -> None:
        data = make_config(["三国霸业.bda", "电子图书.bda", "我的相册.bda"])
        new_data, slot, value = add_or_replace_entry(data, "RectDemo.bda", replace_index=1)

        self.assertEqual(slot, ENTRY_START + ENTRY_SIZE)
        self.assertEqual(read_count(new_data), 3)
        self.assertEqual(parse_entries(new_data)[1].name, "RectDemo.bda")
        self.assertEqual(stored_checksum(new_data), value)
        self.assertEqual(stored_checksum(new_data), checksum(new_data))

    def test_append_when_slot_available(self) -> None:
        data = make_config(["三国霸业.bda", "电子图书.bda"])
        new_data, slot, value = add_or_replace_entry(data, "RectDemo.bda")

        self.assertEqual(slot, ENTRY_START + 2 * ENTRY_SIZE)
        self.assertEqual(read_count(new_data), 3)
        self.assertEqual(parse_entries(new_data)[2].name, "RectDemo.bda")
        self.assertEqual(stored_checksum(new_data), value)
        self.assertEqual(stored_checksum(new_data), checksum(new_data))


if __name__ == "__main__":
    unittest.main()
