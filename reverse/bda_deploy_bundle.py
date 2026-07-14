from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from bda_validate import validate_bda
from config_inf_add import ENTRY_SIZE, ENTRY_START, add_or_replace_entry, parse_entries, read_count


APP_DIR = Path("应用") / "程序"
CONFIG_PATH = Path("系统") / "数据" / "Config.inf"


def check_entry_name(name: str) -> None:
    if not name:
        raise ValueError("BDA 文件名不能为空")
    if Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("BDA 文件名不能包含目录分隔符")
    if not name.lower().endswith(".bda"):
        raise ValueError("BDA 文件名必须以 .bda 结尾")
    name.encode("gbk")


def write_readme(out_dir: Path, entry_name: str, config_slot: int, checksum: int) -> Path:
    readme = out_dir / "DEPLOY_README.txt"
    readme.write_text(
        "\n".join(
            [
                "BBK 9588 BDA historical deploy bundle",
                "",
                "本目录只保留“BDA 文件复制 + Config.inf checksum”这一历史组合，",
                "Config.inf 不是当前已确认的 BDA app 注册或启动机制。",
                "新增 BDA 文件名能否出现在首页、能否点击启动，仍需要菜单 smoke 或真机验证。",
                "",
                "如需复现实验，可把本目录内的两个路径复制到 emu snapshot 或真机存储的同名位置：",
                f"- {APP_DIR}\\{entry_name}",
                f"- {CONFIG_PATH}",
                "",
                f"Config.inf slot offset: 0x{config_slot:x}",
                f"Config.inf checksum: 0x{checksum:08x}",
                "",
                "不要覆盖或提交原始 dump；建议只把本 deploy bundle 用于临时测试。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return readme


def create_deploy_bundle(
    bda_path: Path,
    config_path: Path,
    out_dir: Path,
    *,
    name: str | None = None,
    replace_index: int | None = None,
    validate: bool = True,
) -> dict[str, object]:
    bda_path = bda_path.resolve()
    config_path = config_path.resolve()
    out_dir = out_dir.resolve()
    entry_name = name or bda_path.name
    check_entry_name(entry_name)

    validation: dict[str, object] | None = None
    if validate:
        validation = validate_bda(bda_path)
        if not validation.get("ok"):
            raise ValueError(f"BDA static validation 失败：{validation.get('errors')}")

    config_data = config_path.read_bytes()
    new_config, slot_offset, checksum = add_or_replace_entry(config_data, entry_name, replace_index)

    app_out = out_dir / APP_DIR
    config_out = out_dir / CONFIG_PATH
    app_out.mkdir(parents=True, exist_ok=True)
    config_out.parent.mkdir(parents=True, exist_ok=True)

    bda_out = app_out / entry_name
    shutil.copyfile(bda_path, bda_out)
    config_out.write_bytes(new_config)
    readme = write_readme(out_dir, entry_name, slot_offset, checksum)

    return {
        "out_dir": str(out_dir),
        "launch_evidence": False,
        "warning": "Config.inf 不是已确认的 BDA app 注册或启动机制；新增文件名仍需菜单 smoke 或真机验证。",
        "source_bda": str(bda_path),
        "source_config": str(config_path),
        "bda": str(bda_out),
        "config": str(config_out),
        "readme": str(readme),
        "relative_bda": str(APP_DIR / entry_name),
        "relative_config": str(CONFIG_PATH),
        "relative_readme": "DEPLOY_README.txt",
        "entry_name": entry_name,
        "slot_offset": slot_offset,
        "slot_index": (slot_offset - ENTRY_START) // ENTRY_SIZE,
        "checksum": checksum,
        "count": read_count(new_config),
        "entries": [entry.__dict__ for entry in parse_entries(new_config)],
        "validated": validate,
        "validation": validation,
    }


def print_report(report: dict[str, object]) -> None:
    print(f"historical deploy bundle 目录: {report['out_dir']}")
    print(f"警告: {report['warning']}")
    print(f"BDA: {report['bda']}")
    print(f"Config.inf: {report['config']}")
    print(f"说明: {report['readme']}")
    print(f"copy path: {report['relative_bda']} / {report['relative_config']}")
    print(f"entry name: {report['entry_name']}")
    print(f"slot index: {report['slot_index']}")
    print(f"slot offset: 0x{int(report['slot_offset']):x}")
    print(f"Config.inf checksum: 0x{int(report['checksum']):08x}")
    print(f"BDA static validation: {'已执行' if report.get('validated') else '已跳过'}")
    print("Config.inf entries:")
    for entry in report["entries"]:
        row = dict(entry)
        state = "on" if row["enabled"] else "off"
        print(f"  [{row['index']}] off=0x{int(row['offset']):x} {state} {row['name']}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="生成历史 BDA deploy bundle；Config.inf 不作为 BDA app 注册或启动证据。",
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("--bda", type=Path, required=True, help="已构建的 .bda 文件")
    ap.add_argument("--config", type=Path, default=Path("系统") / "数据" / "Config.inf", help="原始 系统\\数据\\Config.inf 路径")
    ap.add_argument("-o", "--output", type=Path, required=True, help="输出 deploy bundle 目录")
    ap.add_argument("--name", help="写入 Config.inf 的 BDA entry name，默认使用 --bda basename")
    ap.add_argument("--replace-index", type=int, help="替换已有 slot；不传则尝试追加")
    ap.add_argument("--no-validate", action="store_true", help="跳过 BDA static validation")
    ap.add_argument("--json", action="store_true", help="输出 JSON，便于脚本集成")
    ns = ap.parse_args()

    try:
        report = create_deploy_bundle(
            ns.bda,
            ns.config,
            ns.output,
            name=ns.name,
            replace_index=ns.replace_index,
            validate=not ns.no_validate,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if ns.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
