# 时间.bda 逆向报告

## 状态

首版静态报告，重点是时间 UI、时钟资源以及系统 delay/time API 线索。

证据：

```text
应用/程序/时间.bda
reverse/reports/time_layout.json
reverse/reports/time_calls.txt
sdk/doc/time_notes.md
sdk/doc/text_notes.md
sdk/doc/window_notes.md
```

## 头部和布局

```text
文件大小          244,860 bytes
菜单标题         时间
分类           0x09
入口文件偏移  0x95f8
运行时入口 VA   0x81c00020
运行时文件基址  0x81bf6a28
BSS                0x81c326a0..0x81c367e1
头部 checksum    ok
```

缓存的运行时表全局变量：

```text
RES  0x81c326a0
GUI  0x81c326a4
SYS  0x81c326a8
FS   0x81c326ac
MEM  0x81c326b0
```

外部 DLX 引用：

```text
\shell\newtimepic.dlx
\shell\timepic.dlx
```

## API 使用概览

`时间.bda` 包含 736 个已分类的运行时表间接调用：

```text
GUI +0x074  104 次  draw/present state guard
GUI +0x308   60 次  begin draw
GUI +0x30c   50 次  end draw
GUI +0x040   51 次  send/message-like
GUI +0x4f0   23 次  draw text-like
GUI +0x378   16 次  RGB/颜色辅助候选
GUI +0x33c   15 次  set text/foreground color-like
GUI +0x084   13 次  register frame
GUI +0x030   13 次  event poll
GUI +0x050   13 次  event step
GUI +0x054   13 次  event dispatch
GUI +0x17c   12 次  close/release frame

FS  +0x048    4 次  disk/storage information
FS  +0x000   13 次  open/fopen-like
FS  +0x008   19 次  read/fread-like

SYS +0x080   42 次  delay/sleep-like
RES +0x08c    4 次  资源辅助候选
RES +0x090    1 次   resource/picture state-like
RES +0x094   24 次  trace/log-like
```

## 时间和时钟解释

虽然这是时钟应用，但当前扫描只在 SYS 表中稳定分类出 `SYS+0x080`。这个偏移
已经从其他应用和探针中确认接近 delay/sleep。时间读取可能是：

- 隐藏在当前扫描器未捕获的另一种表/调用形态后；
- 通过数据文件和 GUI timer 实现；
- 或者位于附近 SYS 偏移，需要上下文级分析才能确认。

这个应用仍然有价值，因为它使用时钟专用 DLX 资源，并包含大量文字/颜色调用。
它可能通过未分类调用获取状态后，自行格式化时间/日期字符串。

## 文字和绘制

该应用使用稳定的文字绘制调用簇：

```text
GUI+0x338  文字模式候选
GUI+0x378  RGB/颜色辅助
GUI+0x33c  设置文字颜色候选
GUI+0x4f0  绘制文字候选
```

这与记事本互相验证：两个普通应用都在完整窗口/绘制生命周期中使用
`GUI+0x4f0`。曾经崩溃的文字探针应基于这些上下文重写，而不是使用独立调用。

## 存储和磁盘调用

`FS+0x048` 出现 4 次。在 `fs_notes.md` 中，这个偏移接近 disk/storage info。
在时间应用里，它可能用于读写时钟/世界时间配置前检查持久设置存储。

## 交叉验证

- 与 Element、记事本相同的事件循环族：
  `GUI+0x084`, `+0x030`, `+0x050`, `+0x054`, `+0x17c`.
- 与记事本相同的文字调用簇，支持 SDK 文字 wrapper。
- 使用时钟专用 DLX 资源，支持 DLX-as-skin/artwork 模型。

## 未确认点

1. 这个应用使用的准确 time-get API。
2. `RES+0x08c` 的含义；它在此处出现 4 次。
3. 时间/闹钟/世界时间配置的设置文件路径。
4. `SYS+0x080` 在这里是否只是 delay，还是也参与 timer tick。

## 后续静态任务

1. 提取全部 SYS 表调用上下文，而不只看扫描器已分类的调用。
2. 搜索打包日期/时间格式常量和格式化字符串。
3. 与应暴露闹钟 set/get 路径的 `闹钟.bda` 对比。
4. 只有在准确 SYS 偏移验证后，才更新 `time_notes.md`。

