# GAMEBOY.BDA 逆向笔记

本文记录 `应用\程序\GAMEBOY.BDA`，即原机内置 Game Boy 模拟器前端。它是当前
研究“模拟器式原生 BDA”的最好样本。

## 布局

```text
file size          0x29a4c
entry offset       0x95f8
runtime base       0x81bf6a28
runtime entry VA   0x81c00020
```

启动代码会把 runtime table 保存到全局变量：

```text
0x81c20470  RES table
0x81c20474  GUI table
0x81c20478  SYS/device table
0x81c2047c  FS table
0x81c20480  MEM table
```

可用 `reverse\bda_table_call_scan.py` 结合这些全局变量分类该应用中的间接 API 调用。

## 核心模块

`GAMEBOY.BDA` 引用：

```text
a:\gameboy\gameboy.dlx
A:\gameboy\
a:\gameboy\gb.cfg
```

当前 dump 里没有 `gameboy.dlx`。早期曾把它当作可能的外部 core，但后续 disasm 显示
主 Game Boy core 嵌在 `GAMEBOY.BDA` 自身里。`gameboy.dlx` 更可能是前端使用的
UI/skin/resource 包。

ROM 路径通过 FS 表打开。`0x81c10808` 附近代码调用：

```text
FS +0x000  open(path, "rb")
MEM +0x008 allocate 0x25800 bytes
FS +0x010 / +0x014 / +0x008 / +0x004 风格调用
```

这是 ROM/config loader 路径，不是外部模拟器代码 loader。

字符串表显示它支持较完整的 Game Boy 功能：

```text
gb;gbc
GameStartBox
Action replay code faulty
Gameboy COLOR rom detected.
ROM ONLY
ROM+MBC1
ROM+MBC2
ROM+MBC1+RAM+BATTERY
ROM+MBC5
MBC5+ROM+SRAM+BATTERY
Nintendo logo not found.
Checksum failure
```

因此该 BDA 支持 GB/GBC 识别、Action Replay 类作弊码、MBC1、MBC2、MBC5、
SRAM/battery save 和 cartridge checksum validation。

## CPU 和内存核心

CPU interpreter entry 在 `0x81c12270`。它是经典 dispatch-loop interpreter，不是 dynarec：

```text
0x81c25272  current PC
0x81c12270  通过 0x81c0ee74 按 PC 读取 opcode
0x81c122b4  PC 自增
0x81c122c4  opcode * 4
0x81c122d0  通过 0x81c1ef40 附近 dispatch table 跳转
0x81c2068c  per-op cycle/flag accumulator-like byte
```

重要内存 helper：

```text
0x81c0ee74  从 GB 地址空间读取 byte
0x81c0f008  通过两次 byte read 读取 little-endian 16-bit word
0x81c0f054  通过两次 byte write 写 little-endian 16-bit word
0x81c017c8  向 GB 地址空间写 byte
```

byte reader 映射普通 Game Boy 区域：

```text
0000-3fff  fixed ROM bank，pointer 0x81c20850
4000-7fff  switchable ROM bank，由 0x81c204e8 选择
8000-9fff  VRAM bank，受 LCD 状态影响
a000-bfff  external RAM bank
c000-cfff  WRAM bank 0
d000-dfff  switchable WRAM bank
ff00-ffff  IO/HRAM/special registers
```

`0x81c08bf4` 的 renderer 消费模拟器 LCD/VRAM 状态，并把 tile pixel 展开到
16-bit 目标 buffer。它会直接操作 palette table 和 screen window；这不是简单
调用一个通用 GUI image draw API。

## 存档和配置数据

`0x81c0f3f0` 附近会读写小型 `0x44` byte record。完整性规则很简单：

```text
sum bytes 0x00..0x3f
compare with u32 at +0x40
```

如果 checksum 失败，文件会被删除/重建。这看起来覆盖 `gb.cfg` 或相关 per-ROM
状态/配置数据，和 BDA header checksum 是两回事。

## 视频/显示线索

前端通过保存于 `0x81c20474` 的扩展 GUI 表取得/使用内部 GUI screen buffer。它把
pointer 存到 `0x81c2051c`，并派生出 `+0x11200` 的另一个 pointer。代码会在
`0x140` by `0xf0` 形态区域上复制或展开数据，匹配 320x240 主机 buffer，
可能是 scaled 或 staging 后的 Game Boy 输出。

值得探测的扩展 GUI 调用：

```text
GUI +0x6b0  screen/framebuffer pointer getter；C200 table entry 无参数
GUI +0x6e0  触摸长按驱动的 game state pump；无参数，阈值到达后写全局状态
GUI +0x738  screen width-like；C200 table entry 当前直接返回 0x130
GUI +0x72c  state/query-like；C200 table entry 无参数
GUI +0x750  event/key fetch-like；C200 ABI 是两个 output pointer，SDK 暴露为 typed result
GUI +0x5d4  input packet-like，传入至少 6 byte buffer，C200 会写入按键状态
```

这些名称都只是从调用上下文推断。注意该应用没有使用其他游戏常见的
`GUI+0x3f8/+0x400` blit 组，而是使用较高 offset 的扩展 GUI/event 表。
`GUI+0x6b0` 返回的 pointer 属于 firmware display state，不是 SDK 分配的稳定
framebuffer；普通 BDA 不要直接写入，也不要把它和 `GUI+0x3f8/+0x400`
拼成自定义 present 路径。

## 音频线索

相关字符串：

```text
/dev/dsp
/dev/audio
AudioOpen
Allocating sound pattern memory 4x%d bytes.
Initializing sound pattern memory.
Sound pattern memory OK.
```

`0x81c11640` 附近，BDA 通过 SYS/device 表初始化音频：

```text
SYS +0x090  raw audio state pointer getter；C200 无参数返回 0x80362830
SYS +0x06c  调用形态 (0x5622, 0x10, 1, 0x64)
SYS +0x09c  传入计算出的 timer/rate preset index；C200 会限制到 0..14
MEM +0x008  分配 4 个 sound pattern buffer，每个 sample_count * 4 byte
```

流式路径使用 `0x81c24db0` 处的 `0x400` byte sample buffer：

```text
SYS +0x074  ready bool：C200 返回 0x8058+0x6e8 > 0
SYS +0x078  write-like: (buffer at 0x81c24db0, 0x400)，返回已消费 byte 数
SYS +0x090  state pointer getter：只用于 probe/状态观察，不是 open API
SYS +0x004  close/release-like
SYS +0x08c  reset/init-like
SYS +0x0a0  flush/drain-like
```

sample 以 16-bit halfword 排队。`0x81c121b8` 的简单输出 helper 会写入
`(sample << 5)`，直到累计 `0x200` 个 sample；随后等待 `SYS+0x074`，通过
`SYS+0x078` 写出 `0x400` byte，再清零计数。另一路在 flush 前用 `0x1000`
或 `0x0000` 填充静音。SDK 目前把这些 wrapper 暴露为 raw `*_LIKE` helper，直到
hardware probe 确认精确契约。

## 输入线索

该 BDA 在 `0x81c10d30` 附近有密集 input/status 例程。它使用 `+0x72c`、
`+0x750`、`+0x5d4` 附近的 GUI 调用，然后更新 `0x81c205f4`、`0x81c205f8`、
`0x81c205fc` 等 global 变量。C200 中 `GUI+0x5d4` 会清 6 byte packet，并从
按键/MMIO 状态写入 `packet[0..5]`。

音频合成路径也会读取 `0x81c204d0` 全局结构里的 button-state-like 字段，offset
包括 `0x12`、`0x1a`、`0x24`、`0x25`、`0x26`。

这些线索有用，但还不是干净 SDK input API。真正的 touch/key message 仍应结合
`input_notes.md` 和 hardware probe BDA 继续固定。

## 对 GBA/模拟器项目的意义

原生 GBA 模拟器 BDA 可行，但它是一个完整模拟器项目，不是小型 SDK demo。
可行形态大致是：

```text
BDA front end:
  header/icon/menu identity
  file picker / ROM loading
  framebuffer allocation and blit
  key/touch input mapping
  audio device buffering

core module:
  ARM7TDMI interpreter or dynarec
  PPU/APU/timer/DMA/cartridge logic
  save RAM/state handling
```

`GAMEBOY.BDA` 说明平台已经具备所需类型的主机服务：framebuffer、input
polling/events、raw PCM output、heap、file IO。缺口仍是精确 framebuffer/input
签名，以及一个足够小、足够快、适合 Ingenic CPU 的可移植模拟器核心。
