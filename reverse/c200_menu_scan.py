#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from capstone import CS_ARCH_MIPS, CS_MODE_32, CS_MODE_LITTLE_ENDIAN, Cs


DEFAULT_C200 = Path("系统") / "数据" / "C200.bin"
DEFAULT_BASE = 0x80004000

MENU_NEEDLES = [
    "a:\\系统\\数据\\Config.inf",
    "A:\\应用\\程序\\*.bda",
    "A:\\应用\\程序\\时间.bda",
    "A:\\应用\\程序\\系统设置.bda",
    "A:\\应用\\程序\\模拟考场.bda",
    "A:\\应用\\程序\\作文.bda",
    "A:\\应用\\程序\\九门课程.bda",
    "A:\\应用\\程序\\电子图书.bda",
    "A:\\应用\\程序\\情景会话.bda",
    "A:\\应用\\程序\\三步互动.bda",
    "A:\\应用\\程序\\飞天音乐.bda",
    "A:\\应用\\程序\\我的相册.bda",
    "没有找到下载程序",
    "没有找到下载程序，或者程序的版本不正确。",
    "MENU",
    "desktop",
    "娱乐",
    "工具",
    "游戏",
]


def find_all(data: bytes, needle: bytes) -> list[int]:
    out: list[int] = []
    start = 0
    while needle:
        off = data.find(needle, start)
        if off < 0:
            return out
        out.append(off)
        start = off + 1
    return out


def c_string(data: bytes, off: int) -> str:
    end = data.find(b"\0", off)
    if end < 0:
        end = min(len(data), off + 128)
    return data[off:end].decode("gbk", "replace")


def mips_hi_lo_refs(data: bytes, va: int) -> list[dict[str, int | str]]:
    """Find simple lui + addiu/ori address materializations.

    This is a conservative scanner for menu-string orientation, not a full xref
    engine. It catches the common MIPS pattern:
      lui   rX, hi
      addiu rY, rX, lo   (or ori)
    """
    lo = va & 0xFFFF
    signed_lo = lo if lo < 0x8000 else lo - 0x10000
    hi_values = {va >> 16}
    if lo >= 0x8000:
        hi_values.add(((va + 0x10000) >> 16) & 0xFFFF)

    lui_hits: list[tuple[int, int, int]] = []
    for off in range(0, len(data) - 4, 4):
        word = int.from_bytes(data[off : off + 4], "little")
        op = word >> 26
        if op != 0x0F:
            continue
        rt = (word >> 16) & 0x1F
        imm = word & 0xFFFF
        if imm in hi_values:
            lui_hits.append((off, rt, imm))

    refs: list[dict[str, int | str]] = []
    for lui_off, reg, hi in lui_hits:
        for off in range(lui_off + 4, min(len(data) - 4, lui_off + 0x80), 4):
            word = int.from_bytes(data[off : off + 4], "little")
            op = word >> 26
            rs = (word >> 21) & 0x1F
            imm = word & 0xFFFF
            if rs != reg:
                continue
            if op == 0x09 and imm == (signed_lo & 0xFFFF):
                refs.append({"lui_off": lui_off, "use_off": off, "op": "addiu"})
            elif op == 0x0D and imm == lo:
                refs.append({"lui_off": lui_off, "use_off": off, "op": "ori"})
    return refs


def candidate_function_start(data: bytes, use_off: int, base: int) -> int | None:
    """Find a nearby MIPS stack prologue before a string-use site."""
    start = max(0, use_off - 0x300)
    start &= ~3
    best: int | None = None
    for off in range(start, use_off + 4, 4):
        word = int.from_bytes(data[off : off + 4], "little")
        op = word >> 26
        rs = (word >> 21) & 0x1F
        rt = (word >> 16) & 0x1F
        imm = word & 0xFFFF
        if op == 0x09 and rs == 29 and rt == 29 and (imm & 0x8000):
            best = off
    return None if best is None else base + best


def disasm_context(data: bytes, use_off: int, base: int, before: int = 0x18, after: int = 0x24) -> list[str]:
    md = Cs(CS_ARCH_MIPS, CS_MODE_32 | CS_MODE_LITTLE_ENDIAN)
    start = max(0, use_off - before)
    start &= ~3
    end = min(len(data), use_off + after)
    lines: list[str] = []
    for ins in md.disasm(data[start:end], base + start):
        mark = "=>" if ins.address == base + use_off else "  "
        lines.append(f"{mark} {ins.address:08x}: {ins.mnemonic:<8} {ins.op_str}")
    return lines


def enrich_refs(data: bytes, refs: list[dict[str, int | str]], base: int) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    seen: set[tuple[int, str]] = set()
    for ref in refs:
        use_off = int(ref["use_off"])
        op = str(ref["op"])
        key = (use_off, op)
        if key in seen:
            continue
        seen.add(key)
        lui_off = int(ref["lui_off"])
        function_va = candidate_function_start(data, use_off, base)
        out.append(
            {
                "lui_off": lui_off,
                "lui_va": base + lui_off,
                "use_off": use_off,
                "use_va": base + use_off,
                "op": op,
                "candidate_function_va": function_va,
                "context": disasm_context(data, use_off, base),
            }
        )
    return out


def scan(data: bytes, base: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for text in MENU_NEEDLES:
        encoded = text.encode("gbk")
        for off in find_all(data, encoded):
            va = base + off
            refs = mips_hi_lo_refs(data, va)
            enriched = enrich_refs(data, refs, base)
            display_text = text if len(text) <= 4 else c_string(data, off)
            rows.append(
                {
                    "text": display_text,
                    "file_off": off,
                    "va": va,
                    "xref_count": len(enriched),
                    "xrefs": enriched[:8],
                }
            )
    rows.sort(key=lambda row: int(row["file_off"]))
    return rows


def write_markdown(rows: list[dict[str, object]], out: Path, source: Path, base: int) -> None:
    context_rows = [row for row in rows if row.get("xrefs")]
    lines = [
        "# C200 首页菜单索引线索",
        "",
        f"- source: `{source}`",
        f"- base: `0x{base:08x}`",
        "",
        "本报告由 `reverse/c200_menu_scan.py` 生成，记录 C200 中和首页/menu/deploy",
        "相关的 GBK 字符串。`xref_count` 是保守的 `lui + addiu/ori` 静态匹配数量，",
        "用于定位候选函数，不等于完整反汇编控制流。`candidate_function_va` 来自向前",
        "搜索最近的 `addiu sp, sp, -imm` stack prologue，只是切片入口提示。",
        "每个字符串最多展开前 2 个去重 use-site，完整数据见 JSON。",
        "",
        "## 结论",
        "",
        "- C200 同时包含 `a:\\系统\\数据\\Config.inf` 和 `A:\\应用\\程序\\*.bda`，说明存在下载/额外应用表和 BDA 目录扫描路径。",
        "- 首页 carousel 还硬编码了一批 `A:\\应用\\程序\\*.bda` 路径，例如 `时间.bda`、`系统设置.bda`、`模拟考场.bda`、`作文.bda`、`九门课程.bda`、`电子图书.bda` 和 `我的相册.bda`。",
        "- 因此仅替换 `Config.inf` slot 不能证明新增 BDA 会出现在首页；deploy 后仍需要菜单可见性和点击启动 smoke。",
        "",
        "## 字符串表",
        "",
        "| file_off | VA | xrefs | text |",
        "|---:|---:|---:|---|",
    ]
    for row in rows:
        text = str(row["text"]).replace("|", "\\|")
        lines.append(
            f"| `0x{int(row['file_off']):06x}` | `0x{int(row['va']):08x}` | "
            f"{int(row['xref_count'])} | `{text}` |"
        )
    lines.extend(["", "## Xref 候选调用点", ""])
    for row in context_rows:
        xrefs = list(row.get("xrefs", []))
        if not xrefs:
            continue
        lines.append(f"### `{row['text']}`")
        lines.append("")
        for ref in xrefs[:2]:
            function_va = ref.get("candidate_function_va")
            function_text = "(unknown)" if function_va is None else f"0x{int(function_va):08x}"
            lines.append(
                f"- use `0x{int(ref['use_va']):08x}` ({ref['op']}), "
                f"candidate_function_va `{function_text}`"
            )
            lines.append("")
            lines.append("```asm")
            lines.extend(str(line) for line in ref.get("context", []))
            lines.append("```")
            lines.append("")
    lines.append("")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="扫描 C200.bin 中首页/menu/deploy 相关 BDA 字符串和粗 xref。",
        add_help=False,
    )
    ap._positionals.title = "位置参数"
    ap._optionals.title = "选项"
    ap.add_argument("-h", "--help", action="help", help="显示帮助并退出")
    ap.add_argument("--bin", type=Path, default=DEFAULT_C200, help="C200.bin 路径，默认 系统\\数据\\C200.bin")
    ap.add_argument("--base", type=lambda text: int(text, 0), default=DEFAULT_BASE, help="C200 加载基址，默认 0x80004000")
    ap.add_argument("--json", type=Path, help="输出 JSON 报告")
    ap.add_argument("--markdown", type=Path, help="输出 Markdown 报告")
    ns = ap.parse_args()

    data = ns.bin.read_bytes()
    rows = scan(data, ns.base)
    if ns.json is not None:
        ns.json.parent.mkdir(parents=True, exist_ok=True)
        ns.json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if ns.markdown is not None:
        write_markdown(rows, ns.markdown, ns.bin, ns.base)

    for row in rows:
        print(
            f"0x{int(row['file_off']):06x} 0x{int(row['va']):08x} "
            f"xrefs={int(row['xref_count'])} {row['text']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
