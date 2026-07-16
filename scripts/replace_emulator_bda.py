from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


SDK_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = "/应用/程序/宠物单词.bda"
C200_PATH = "/系统/数据/C200.bin"


def file_digest(fs, path: str) -> str:
    digest = hashlib.sha256()
    with fs.openbin(path, "r") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def replace_target(fs, target: str, payload: bytes) -> str:
    if not fs.isfile(target):
        raise FileNotFoundError(f"固定测试入口不存在：{target}")

    old_size = fs.getsize(target)
    if len(payload) <= old_size:
        with fs.openbin(target, "r+b") as stream:
            stream.seek(0)
            stream.write(payload)
            stream.truncate(len(payload))
        return "in-place"

    fs.remove(target)
    with fs.openbin(target, "w") as stream:
        stream.write(payload)
    return "recreate"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(
        description="只替换模拟器 NAND 中的固定宠物单词 BDA，不修改 C200.bin。"
    )
    ap.add_argument("--emulator-root", type=Path, required=True)
    ap.add_argument("--nand", type=Path, required=True)
    ap.add_argument("--bda", type=Path, required=True)
    ap.add_argument("--target", default=DEFAULT_TARGET)
    args = ap.parse_args()

    emulator_root = args.emulator_root.resolve()
    nand = args.nand.resolve()
    bda = args.bda.resolve()
    if not emulator_root.is_dir():
        raise SystemExit(f"模拟器目录不存在：{emulator_root}")
    if not nand.is_file():
        raise SystemExit(f"测试 NAND 不存在：{nand}")
    if not bda.is_file():
        raise SystemExit(f"BDA 不存在：{bda}")
    if bda.suffix.lower() != ".bda":
        raise SystemExit(f"输入文件不是 .bda：{bda}")

    sys.path.insert(0, str(emulator_root))
    sys.path.insert(1, str(SDK_ROOT))
    from bda_packer.validate import validate_bda
    from emu.qemu.nand_fs import mutate_nand_files

    report = validate_bda(bda)
    if not report["ok"]:
        details = "\n".join(str(item) for item in report["errors"])
        raise SystemExit(f"BDA 静态校验失败：\n{details}")

    payload = bda.read_bytes()
    payload_sha = hashlib.sha256(payload).hexdigest()
    state: dict[str, str] = {}

    def operation(fs):
        state["c200_before"] = file_digest(fs, C200_PATH)
        state["write_mode"] = replace_target(fs, args.target, payload)

    def validator(fs):
        if not fs.isfile(args.target):
            raise ValueError(f"替换后的 BDA 不存在：{args.target}")
        if fs.getsize(args.target) != len(payload):
            raise ValueError(f"替换后的 BDA 大小错误：{args.target}")
        if file_digest(fs, args.target) != payload_sha:
            raise ValueError(f"替换后的 BDA SHA256 错误：{args.target}")
        state["c200_after"] = file_digest(fs, C200_PATH)
        if state["c200_after"] != state["c200_before"]:
            raise ValueError("C200.bin 在替换 BDA 时发生了变化")

    mutate_nand_files(nand, operation, validator=validator)
    print(
        json.dumps(
            {
                "ok": True,
                "nand": str(nand),
                "source_bda": str(bda),
                "target": args.target,
                "title": report.get("title"),
                "size": len(payload),
                "sha256": payload_sha,
                "write_mode": state["write_mode"],
                "c200_sha256": state["c200_after"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
