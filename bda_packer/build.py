from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .header import (
    BdaHeaderFields,
    FIRMWARE_CATEGORY_CAPACITIES,
    FIRMWARE_CATEGORY_LABELS,
    write_header,
)
from .validate import validate_bda
from .vx_icon import (
    DEFAULT_ALPHA_THRESHOLD,
    DEFAULT_TRANSPARENT_KEY,
    make_vx,
    read_png,
    resize_cover,
    rgb565_bytes,
)


ENTRY_OFFSET = 0x95F8
ENTRY_VA = 0x81C00020
RUNTIME_FILE_BASE = ENTRY_VA - ENTRY_OFFSET
ICON_START = 0x88
ICON_SPECS = ((80, 80), (80, 80), (54, 54), (58, 58))
ICON_SIZES = tuple(24 + width * height * 2 for width, height in ICON_SPECS)
DEFAULT_ICON_TRANSPARENT_KEY = DEFAULT_TRANSPARENT_KEY
DEFAULT_ICON_ALPHA_THRESHOLD = DEFAULT_ALPHA_THRESHOLD
REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SDK_INCLUDE_DIR = REPO_ROOT / "sdk" / "include"
PACKAGED_SDK_INCLUDE_DIR = Path(__file__).resolve().parent / "include"


def category_help_epilog() -> str:
    usage_notes = {
        4: "游戏目录",
        8: "影音、多媒体目录",
    }
    lines = ["菜单分类（header category 低 16 位）："]
    for value, label in FIRMWARE_CATEGORY_LABELS.items():
        note = usage_notes.get(value)
        capacity = FIRMWARE_CATEGORY_CAPACITIES[value]
        details = [note] if note else []
        details.append(f"总菜单项上限 {capacity}")
        suffix = f"（{'；'.join(details)}）"
        lines.append(f"  {value}  {label}{suffix}")
    lines.extend(
        [
            "  0  固件范围检查允许，但未发现对应的原机应用目录，不建议使用",
            "",
            "上限是分类的总菜单项容量，固件内建项也会占用槽位。",
            "category 4 的第 11 个 BDA 不展示已动态验证；其他上限来自 C200 静态分析。",
            "通常直接传 1..9。原机个别 BDA 的高 16 位带有标志，含义尚未确认。",
        ]
    )
    return "\n".join(lines)


def bundled_prefix() -> str | None:
    for root in (REPO_ROOT / ".toolchain", REPO_ROOT / "tools"):
        direct = root / "bin" / "mipsel-none-elf-gcc.exe"
        if direct.is_file():
            return str(direct.parent / "mipsel-none-elf-")
        for gcc in root.glob("g++-mipsel-none-elf-*/bin/mipsel-none-elf-gcc.exe"):
            return str(gcc.parent / "mipsel-none-elf-")
    return None


def sdk_include_dir() -> Path:
    configured = os.environ.get("BDA_SDK_INCLUDE")
    candidates = [
        Path(configured).expanduser() if configured else None,
        SOURCE_SDK_INCLUDE_DIR,
        PACKAGED_SDK_INCLUDE_DIR,
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "bda_sdk.h").is_file():
            return candidate
    searched = ", ".join(str(item) for item in candidates if item is not None)
    raise SystemExit(
        "打包器缺少 SDK header；可设置 BDA_SDK_INCLUDE。"
        f"已搜索：{searched}"
    )


def compiler_include_dirs(extra_dirs: Sequence[Path] = ()) -> list[Path]:
    directories: list[Path] = []
    for directory in (*extra_dirs, sdk_include_dir()):
        resolved = directory.resolve()
        if not resolved.is_dir():
            raise SystemExit(f"include 目录不存在：{directory}")
        if resolved not in directories:
            directories.append(resolved)
    return directories


def find_tool(prefix: str, name: str) -> str:
    executable = f"{prefix}{name}"
    candidates = [executable]
    if not executable.lower().endswith(".exe"):
        candidates.append(executable + ".exe")
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return str(path)
        found = shutil.which(candidate)
        if found is not None:
            return found
    raise SystemExit(
        f"未找到 {executable}；请传 --prefix 或先运行 "
        "scripts\\setup_toolchain.ps1 安装 mipsel toolchain"
    )


def run_checked(command: list[str], step: str) -> None:
    try:
        subprocess.check_call(command)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"{step}失败，退出码 {exc.returncode}") from exc


def compile_c(
    source: Path,
    prefix: str,
    include_dirs: Sequence[Path] = (),
) -> bytes:
    include_args = [
        argument
        for directory in compiler_include_dirs(include_dirs)
        for argument in ("-I", str(directory))
    ]
    cc = find_tool(prefix, "gcc")
    objcopy = find_tool(prefix, "objcopy")
    with tempfile.TemporaryDirectory() as temp_dir:
        work = Path(temp_dir)
        elf = work / "app.elf"
        raw = work / "app.bin"
        linker_script = work / "bda.ld"
        linker_script.write_text(
            f"""
ENTRY(bda_main)
SECTIONS
{{
  . = 0x{ENTRY_VA:x};
  .text : {{ *(.text.bda_main) *(.text*) }}
  .rodata : {{ *(.rodata*) }}
  .data : {{ *(.data*) *(.sdata*) *(.bss*) *(COMMON) }}
}}
""".strip()
            + "\n",
            encoding="ascii",
        )
        run_checked(
            [
                cc,
                "-EL",
                "-march=mips32",
                "-mno-abicalls",
                "-G0",
                "-fno-pic",
                "-Os",
                "-ffreestanding",
                "-fno-builtin",
                "-nostdlib",
                *include_args,
                "-Wl,--build-id=none",
                f"-Wl,-T,{linker_script}",
                str(source),
                "-o",
                str(elf),
            ],
            "C 编译",
        )
        run_checked(
            [objcopy, "-O", "binary", str(elf), str(raw)],
            "objcopy 导出 raw 二进制",
        )
        return raw.read_bytes()


def parse_bg(text: str) -> tuple[int, int, int]:
    value = text.strip().lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("背景色必须是 RRGGBB 六位十六进制")
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("背景色必须是 RRGGBB 六位十六进制") from exc


def parse_icon_transparent_key(text: str) -> tuple[int, int, int] | None:
    if text.strip().lower() in {"none", "off"}:
        return None
    return parse_bg(text)


def parse_alpha_threshold(text: str) -> int:
    try:
        value = int(text, 0)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("alpha 阈值必须是 0..255 的整数") from exc
    if not 0 <= value <= 255:
        raise argparse.ArgumentTypeError("alpha 阈值必须是 0..255 的整数")
    return value


def make_default_icon(
    width: int,
    height: int,
    foreground: tuple[int, int, int],
    background: tuple[int, int, int],
) -> bytes:
    pixels: list[tuple[int, int, int, int]] = []
    for y in range(height):
        for x in range(width):
            border = x < 3 or y < 3 or x >= width - 3 or y >= height - 3
            diagonal = abs(x - y) <= 1 or abs((width - 1 - x) - y) <= 1
            red, green, blue = foreground if border or diagonal else background
            pixels.append((red, green, blue, 255))
    return make_vx(width, height, rgb565_bytes(pixels, background))


def build_icons(
    icon_png: Path | None,
    background: tuple[int, int, int],
    *,
    transparent_key: tuple[int, int, int] | None = DEFAULT_ICON_TRANSPARENT_KEY,
    alpha_threshold: int = DEFAULT_ICON_ALPHA_THRESHOLD,
) -> bytes:
    output = bytearray()
    if icon_png is not None:
        source_width, source_height, source_pixels = read_png(icon_png)
        for width, height in ICON_SPECS:
            resized = resize_cover(source_width, source_height, source_pixels, width, height)
            output.extend(
                make_vx(
                    width,
                    height,
                    rgb565_bytes(
                        resized,
                        background,
                        transparent_key=transparent_key,
                        alpha_threshold=alpha_threshold,
                    ),
                )
            )
        return bytes(output)

    colors = (
        ((255, 255, 255), (0, 64, 96)),
        ((255, 255, 255), (96, 32, 0)),
        ((0, 0, 0), (180, 220, 255)),
        ((255, 255, 255), (40, 40, 40)),
    )
    for (width, height), (foreground, icon_background) in zip(ICON_SPECS, colors):
        output.extend(make_default_icon(width, height, foreground, icon_background))
    return bytes(output)


def build_bda(
    source: Path,
    title: str,
    category: int,
    prefix: str,
    icon_png: Path | None,
    icon_background: tuple[int, int, int],
    include_dirs: Sequence[Path] = (),
    icon_transparent_key: tuple[int, int, int] | None = DEFAULT_ICON_TRANSPARENT_KEY,
    icon_alpha_threshold: int = DEFAULT_ICON_ALPHA_THRESHOLD,
) -> bytearray:
    if not source.is_file():
        raise SystemExit(f"源码不存在：{source}")
    if source.suffix.lower() != ".c":
        raise SystemExit("只接受 .c 源码；BDA 入口必须定义为 bda_main")
    if icon_png is not None and not icon_png.is_file():
        raise SystemExit(f"图标 PNG 不存在：{icon_png}")

    code = compile_c(source, prefix, include_dirs)
    data = bytearray(b"\0" * ENTRY_OFFSET)
    icons = build_icons(
        icon_png,
        icon_background,
        transparent_key=icon_transparent_key,
        alpha_threshold=icon_alpha_threshold,
    )
    expected_icon_bytes = ENTRY_OFFSET - ICON_START
    if len(icons) != expected_icon_bytes:
        raise SystemExit(
            f"图标区大小为 0x{len(icons):x}，预期 0x{expected_icon_bytes:x}"
        )
    data[ICON_START:ENTRY_OFFSET] = icons
    data.extend(code)
    if len(data) % 4:
        data.extend(b"\0" * (4 - len(data) % 4))

    fields = BdaHeaderFields(
        category=category,
        file_size_minus_4=len(data) - 4,
        entry_offset=ENTRY_OFFSET,
        icon_start=ICON_START,
        icon0_size=ICON_SIZES[0],
        icon1_size=ICON_SIZES[1],
        icon2_size=ICON_SIZES[2],
        icon3_size=ICON_SIZES[3],
    )
    try:
        write_header(data, fields, title)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    return data


def main() -> None:
    ap = argparse.ArgumentParser(
        description="从 freestanding C 源码直接编译、链接并打包 BBK 9588 BDA。",
        epilog=category_help_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("source", type=Path, help="包含 bda_main 的 freestanding C 源码")
    ap.add_argument("--title", required=True, help="菜单标题，GBK 编码后最多 16 字节")
    ap.add_argument(
        "--category",
        type=lambda text: int(text, 0),
        required=True,
        metavar="N",
        help="菜单分类编号，通常使用 1..9；完整映射见下方",
    )
    ap.add_argument("--icon-png", type=Path, help="菜单图标 PNG；省略时生成内置诊断图标")
    ap.add_argument(
        "--icon-background",
        type=parse_bg,
        default=(0, 0, 0),
        help="关闭透明色键时使用的 PNG alpha 背景色，RRGGBB，默认 000000",
    )
    ap.add_argument(
        "--icon-transparent-key",
        type=parse_icon_transparent_key,
        default=DEFAULT_ICON_TRANSPARENT_KEY,
        metavar="RRGGBB|none",
        help="PNG 透明像素的 RGB565 色键，默认 FF00FF；传 none 可关闭",
    )
    ap.add_argument(
        "--icon-alpha-threshold",
        type=parse_alpha_threshold,
        default=DEFAULT_ICON_ALPHA_THRESHOLD,
        metavar="N",
        help="alpha 小于等于该值时写透明色键，默认 8",
    )
    ap.add_argument(
        "--prefix",
        default=None,
        help="toolchain prefix，例如 mipsel-none-elf- 或完整路径前缀",
    )
    ap.add_argument(
        "-I",
        "--include-dir",
        action="append",
        type=Path,
        default=[],
        metavar="DIR",
        help="额外 include 目录，可重复；搜索顺序优先于稳定 sdk/include",
    )
    ap.add_argument("-o", "--output", type=Path, required=True, help="输出 BDA 路径")
    ns = ap.parse_args()

    prefix = (
        ns.prefix
        or os.environ.get("BDA_TOOLCHAIN_PREFIX")
        or bundled_prefix()
        or "mipsel-none-elf-"
    )
    data = build_bda(
        ns.source,
        ns.title,
        ns.category,
        prefix,
        ns.icon_png,
        ns.icon_background,
        ns.include_dir,
        ns.icon_transparent_key,
        ns.icon_alpha_threshold,
    )
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(data)

    report = validate_bda(ns.output)
    if not report["ok"]:
        details = "; ".join(str(item) for item in report["errors"])
        ns.output.unlink(missing_ok=True)
        raise SystemExit(f"打包后固件规则校验失败：{details}")

    print(f"output={ns.output}")
    print(f"size=0x{len(data):x}")
    print(f"entry_offset=0x{ENTRY_OFFSET:x}")
    print(f"entry_va=0x{ENTRY_VA:x}")
    print(f"runtime_file_base=0x{RUNTIME_FILE_BASE:x}")
    print(f"title={report['title']}")
    print(f"category=0x{int(report['category']):x}")
    print(f"checksum_ok={report['checksum_ok']}")
    print("packaging=standalone")


if __name__ == "__main__":
    main()
