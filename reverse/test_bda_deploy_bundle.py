from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bda_deploy_bundle import APP_DIR, CONFIG_PATH, create_deploy_bundle
from config_inf_add import ENTRY_SIZE, ENTRY_START, TRAILER_OFF, checksum, parse_entries, stored_checksum


def make_config(names: list[str]) -> bytes:
    data = bytearray(b"\0" * (TRAILER_OFF + 4))
    data[0:2] = len(names).to_bytes(2, "little")
    data[2:4] = len(names).to_bytes(2, "little")
    for index, name in enumerate(names):
        off = ENTRY_START + index * ENTRY_SIZE
        data[off] = 1
        encoded = name.encode("gbk")
        data[off + 1 : off + 1 + len(encoded)] = encoded
    value = checksum(data)
    data[TRAILER_OFF : TRAILER_OFF + 4] = value.to_bytes(4, "little")
    return bytes(data)


class BdaDeployBundleTest(unittest.TestCase):
    def test_deploy_tool_help_is_chinese(self) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        output = subprocess.check_output(
            [sys.executable, "reverse/bda_deploy_bundle.py", "--help"],
            text=True,
            encoding="utf-8",
            env=env,
        )
        self.assertIn("选项", output)
        self.assertIn("显示帮助并退出", output)
        self.assertIn("原始 系统\\数据\\Config.inf 路径", output)
        self.assertIn("输出 deploy bundle 目录", output)
        self.assertIn("Config.inf 不作为 BDA app 注册或启动证据", output)
        self.assertNotIn("positional arguments", output)
        self.assertNotIn("show this help message and exit", output)

    def test_deploy_tool_text_output_keeps_common_tool_terms(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            root = Path(td)
            bda = root / "RectDemo.bda"
            config = root / "Config.inf"
            out = root / "deploy"
            bda.write_bytes(b"payload")
            config.write_bytes(make_config(["三国霸业.bda", "电子图书.bda"]))

            output = subprocess.check_output(
                [
                    sys.executable,
                    "reverse/bda_deploy_bundle.py",
                    "--bda",
                    str(bda),
                    "--config",
                    str(config),
                    "--no-validate",
                    "-o",
                    str(out),
                ],
                text=True,
                encoding="utf-8",
                env=env,
            )

            self.assertIn("historical deploy bundle 目录:", output)
            self.assertIn("Config.inf checksum:", output)
            self.assertIn("Config.inf 不是已确认的 BDA app 注册或启动机制", output)
            self.assertIn("off=0x", output)
            self.assertIn("on RectDemo.bda", output)
            self.assertIn("copy path:", output)
            self.assertIn("slot index:", output)
            self.assertIn("BDA static validation: 已跳过", output)

    def test_bundle_replaces_slot_and_copies_tree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bda = root / "RectDemo.bda"
            config = root / "Config.inf"
            out = root / "deploy"
            bda.write_bytes(b"not a real bda")
            original_config = make_config(["三国霸业.bda", "电子图书.bda", "我的相册.bda"])
            config.write_bytes(original_config)

            report = create_deploy_bundle(
                bda,
                config,
                out,
                replace_index=1,
                validate=False,
            )

            self.assertEqual((out / APP_DIR / "RectDemo.bda").read_bytes(), b"not a real bda")
            self.assertTrue((out / CONFIG_PATH).is_file())
            self.assertTrue((out / "DEPLOY_README.txt").is_file())
            self.assertEqual(config.read_bytes(), original_config)
            new_config = (out / CONFIG_PATH).read_bytes()
            self.assertEqual(parse_entries(new_config)[1].name, "RectDemo.bda")
            self.assertEqual(stored_checksum(new_config), checksum(new_config))
            self.assertEqual(report["entry_name"], "RectDemo.bda")
            self.assertEqual(report["slot_offset"], ENTRY_START + ENTRY_SIZE)
            self.assertEqual(report["slot_index"], 1)
            self.assertEqual(report["relative_bda"], str(APP_DIR / "RectDemo.bda"))
            self.assertEqual(report["relative_config"], str(CONFIG_PATH))
            self.assertEqual(report["relative_readme"], "DEPLOY_README.txt")
            self.assertFalse(report["launch_evidence"])
            self.assertIn("Config.inf 不是已确认的 BDA app 注册或启动机制", report["warning"])
            self.assertEqual(report["source_bda"], str(bda.resolve()))
            self.assertEqual(report["source_config"], str(config.resolve()))
            self.assertFalse(report["validated"])
            readme = (out / "DEPLOY_README.txt").read_text(encoding="utf-8")
            self.assertIn("historical deploy bundle", readme)
            self.assertIn("Config.inf 不是当前已确认的 BDA app 注册或启动机制", readme)
            self.assertIn("仍需要菜单 smoke 或真机验证", readme)

    def test_json_output_has_stable_deploy_fields(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            root = Path(td)
            bda = root / "RectDemo.bda"
            config = root / "Config.inf"
            out = root / "deploy"
            bda.write_bytes(b"payload")
            config.write_bytes(make_config(["三国霸业.bda", "电子图书.bda"]))

            output = subprocess.check_output(
                [
                    sys.executable,
                    "reverse/bda_deploy_bundle.py",
                    "--bda",
                    str(bda),
                    "--config",
                    str(config),
                    "--no-validate",
                    "--replace-index",
                    "0",
                    "-o",
                    str(out),
                    "--json",
                ],
                text=True,
                encoding="utf-8",
                env=env,
            )

            report = json.loads(output)
            self.assertEqual(report["entry_name"], "RectDemo.bda")
            self.assertEqual(report["slot_index"], 0)
            self.assertEqual(report["slot_offset"], ENTRY_START)
            self.assertEqual(report["relative_bda"], str(APP_DIR / "RectDemo.bda"))
            self.assertEqual(report["relative_config"], str(CONFIG_PATH))
            self.assertEqual(report["relative_readme"], "DEPLOY_README.txt")
            self.assertFalse(report["launch_evidence"])
            self.assertIn("新增文件名仍需菜单 smoke 或真机验证", report["warning"])
            self.assertEqual(report["source_bda"], str(bda.resolve()))
            self.assertEqual(report["source_config"], str(config.resolve()))
            self.assertFalse(report["validated"])
            self.assertIsNone(report["validation"])

    def test_name_override_controls_copy_and_config_entry(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bda = root / "source.bda"
            config = root / "Config.inf"
            out = root / "deploy"
            bda.write_bytes(b"payload")
            config.write_bytes(make_config(["三国霸业.bda", "电子图书.bda"]))

            create_deploy_bundle(
                bda,
                config,
                out,
                name="测试程序.bda",
                validate=False,
            )

            self.assertTrue((out / APP_DIR / "测试程序.bda").is_file())
            self.assertEqual(parse_entries((out / CONFIG_PATH).read_bytes())[2].name, "测试程序.bda")

    def test_validation_rejects_non_bda_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bda = root / "Bad.bda"
            config = root / "Config.inf"
            bda.write_bytes(b"bad")
            config.write_bytes(make_config(["三国霸业.bda", "电子图书.bda"]))

            with self.assertRaises(ValueError):
                create_deploy_bundle(bda, config, root / "deploy")

    def test_rejects_path_like_entry_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bda = root / "source.bda"
            config = root / "Config.inf"
            bda.write_bytes(b"payload")
            config.write_bytes(make_config(["三国霸业.bda", "电子图书.bda"]))

            with self.assertRaises(ValueError):
                create_deploy_bundle(bda, config, root / "deploy", name="dir\\Bad.bda", validate=False)


if __name__ == "__main__":
    unittest.main()
