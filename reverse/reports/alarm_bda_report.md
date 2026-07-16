# 闹钟.bda 逆向报告

## 状态

首版静态报告，重点是 RTC/闹钟 API。本报告与 `时间.bda` 和
`time_notes.md` 互相验证。

证据：

```text
应用/程序/闹钟.bda
reverse/reports/alarm_layout.json
reverse/reports/alarm_calls.txt
reverse/docs/time_notes.md
reverse/docs/window_notes.md
```

## 头部和布局

```text
文件大小          88,476 bytes
菜单标题         闹钟
分类           0x09
入口文件偏移  0x95f8
运行时入口 VA   0x81c00020
运行时文件基址  0x81bf6a28
BSS                0x81c0c3c0..0x81e0d301
头部 checksum    ok
```

缓存的运行时表全局变量：

```text
RES  0x81c0c3c0
GUI  0x81c0c3c4
SYS  0x81c0c3c8
FS   0x81c0c3cc
MEM  0x81c0c3d0
```

外部资源：

```text
\shell\naoling_A.dlx
\shell\naoling_B.dlx
```

## API 使用概览

`闹钟.bda` 包含 443 个已分类的运行时表间接调用：

```text
SYS +0x080   6 次  delay/sleep-like
SYS +0x0a8   4 次  C200 no-op stub 调用点记录
SYS +0x0ac   3 次  alarm set-like
SYS +0x0b0   3 次  alarm get-like
SYS +0x0b8   4 次  alarm due record get-like

GUI +0x074  42 次  draw/present guard
GUI +0x4f0  27 次  draw text-like
GUI +0x308  23 次  begin draw
GUI +0x30c  21 次  end draw
GUI +0x084   5 次  register frame
GUI +0x030   5 次  event poll
GUI +0x050   5 次  event step
GUI +0x054   5 次  event dispatch
GUI +0x17c   5 次  frame close/release

FS  +0x000  15 次  open/fopen-like
FS  +0x004  15 次  close/fclose-like
FS  +0x03c   2 次  findfirst-like
FS  +0x044   2 次  findclose-like
FS  +0x07c   2 次  storage-ready-like
```

## RTC 和闹钟 API 证据

这个应用是时钟/闹钟 SDK 调用最清晰的样本：

```text
SYS+0x0b8  alarm due record get-like
SYS+0x0b0  alarm get-like
SYS+0x0ac  alarm set-like
SYS+0x0a8  C200 no-op stub，旧 commit/refresh 猜测已废弃
```

这与早期 `time_probe.c` 设计互相印证：探针可以读取 `SYS+0x0b8` 的 due
alarm record 和 `SYS+0x0b0`，但在结构体布局完全确认前应避免调用 `SYS+0x0ac`。后续 C200
反汇编确认 `SYS+0x0a8 -> 0x8001415c` 只有 `jr ra; nop`，因此它不是已确认
提交或持久化入口，SDK 也不再公开对应 wrapper。

`时间.bda` 大量使用 `SYS+0x080` delay 调用，但当前扫描器没有暴露直接的
`SYS+0x0b8` 路径。因此 `闹钟.bda` 应作为 alarm/RTC 相关函数签名的权威样本。

## UI 行为

该应用使用正常的原生窗口生命周期：

```text
GUI+0x084  register frame
GUI+0x030  event poll
GUI+0x050  event step
GUI+0x054  event dispatch
GUI+0x17c  frame close/release
```

它也使用了与 `记事本.bda`、`时间.bda` 相同的文字绘制调用簇：

```text
GUI+0x338  文字模式候选
GUI+0x378  RGB/颜色辅助候选
GUI+0x33c  设置文字颜色候选
GUI+0x4f0  绘制文字候选
```

## 文件系统行为

FS 调用主要与配置/资源有关，不像重型媒体扫描。`FS+0x03c/+0x044` 出现而
`FS+0x040` 很少，说明这里可能是短目录检查或一次性扫描。

## 未确认点

1. `SYS+0x0b8` 输出的 due alarm record 字段布局。
2. `SYS+0x0b0/+0x0ac` 使用的闹钟结构体准确布局。
3. 闹钟声音文件/资源选择路径。

## 后续静态任务

1. 提取全部 `SYS+0x0b8/+0x0b0/+0x0ac` 调用上下文。
2. 与 `系统设置.bda` 的日期/时间设置 UI 对比。
3. 映射结构体字段后，更新 `time_probe.c` 输出解释。

