# 飞天影音.bda / 飞天影音_.bda 逆向报告

## 状态

首版静态报告，重点是视频/播放器架构。这两个大型 BDA 放在一起分析，因为它们
共享相同的 `player.bin`/`player.cfg` 模型，扫描特征也非常相近。

证据：

```text
应用/程序/飞天影音.bda
应用/程序/飞天影音_.bda
reverse/reports/video_layout.json
reverse/reports/video_alt_layout.json
reverse/reports/video_calls.txt
reverse/reports/video_alt_calls.txt
reverse/docs/media_notes.md
reverse/docs/system_bin_notes.md
```

## 头部和布局

`飞天影音.bda`:

```text
文件大小          3,172,572 bytes
菜单标题         飞天影音
分类           0x80000008
入口文件偏移  0x95f8
运行时文件基址  0x81bf6a28
BSS                0x81efd300..0x81f0ed20
头部 checksum    ok
```

缓存的运行时表全局变量：

```text
RES  0x81efd300
GUI  0x81efd304
SYS  0x81efd308
FS   0x81efd30c
MEM  0x81efd310
```

`飞天影音_.bda`:

```text
文件大小          2,878,316 bytes
菜单标题         飞天影音_
分类           0x80000008
入口文件偏移  0x95f8
运行时文件基址  0x81bf6a28
BSS                0x81eb5590..0x81ed4c40
头部 checksum    ok
```

缓存的运行时表全局变量：

```text
GUI  0x81eb5594
SYS  0x81eb5598
FS   0x81eb559c
MEM  0x81eb55a0
```

备用构建在当前检测器中没有暴露 RES 表缓存，但仍有常见的 GUI/SYS/FS/MEM 表。

## 播放器资源

两个文件都引用：

```text
\player.bin
\player.cfg
```

主构建包含 MP3 相关字符串；备用构建包含 MP4/3GP/MP3 扩展名标记。当前路径
扫描中，两者都没有使用 DLX shell 资源。

这支持 `media_notes.md` 中已有的假设：视频播放不是一个小型 `play_video()`
SDK 函数直接暴露出来的。应用更可能通过 `player.bin` 和配置打包或启动一个
更大的播放器运行时。

## API 使用概览

`飞天影音.bda` 已分类表调用：

```text
FS  +0x008  25 次
FS  +0x010  28 次
FS  +0x000   7 次
FS  +0x068   2 次

SYS +0x040   4 次
SYS +0x06c   3 次
SYS +0x070   1 次
SYS +0x074   1 次
SYS +0x078   1 次
SYS +0x07c   1 次
SYS +0x080   1 次
SYS +0x084   1 次
SYS +0x088   1 次
SYS +0x08c   1 次
SYS +0x090   1 次
SYS +0x0a0   1 次
```

`飞天影音_.bda` 已分类表调用：

```text
FS  +0x07c  19 次
FS  +0x068   3 次
FS  +0x000   2 次

SYS +0x06c   1 次
SYS +0x070   5 次
SYS +0x074   1 次
SYS +0x078   1 次
SYS +0x080   3 次
SYS +0x084   1 次
SYS +0x08c   1 次
SYS +0x090   1 次
SYS +0x094   1 次
SYS +0x09c   1 次
SYS +0x0a0   1 次
```

二者只有很小的原生 GUI 外壳：

```text
GUI+0x084/+0x030/+0x050/+0x054/+0x17c  约 2 个窗口/循环
GUI+0x2b8  1 个消息框
```

## UNKNOWN 调用符合预期

扫描器报告了数千个 `UNKNOWN` 调用，尤其是：

```text
UNKNOWN +0x040  约 1350 次
UNKNOWN +0x010  数百次
UNKNOWN +0x000  数百次
```

这些不应直接解释为缺失的系统 SDK 偏移。它们更可能是通过 BDA 内嵌或加载的
内部 codec/player 函数表进行调用。这正符合 MPlayer/FFmpeg 类运行时的预期。

## 交叉验证

- `飞天音乐.bda` 使用高层媒体播放器 SYS 偏移 `+0x004/+0x020/...`。
- `GAMEBOY.BDA` 使用原始音频流偏移 `SYS+0x06c/+0x074/+0x078`。
- `飞天影音.bda` 使用 `SYS+0x06c/+0x074/+0x078/+0x0a0`，同时还有巨大的私有
  播放器表，说明它可能把原生固件设备/音频/视频 API 与打包播放器引擎桥接起来。

## 对 SDK 的含义

对自定义 BDA 应用来说，现实的视频策略可能是：

1. 理清 `飞天影音` 如何调用/配置 `player.bin`；
2. 对简单媒体任务复用固件设备/音频原语；
3. 避免试图通过一个猜测 API 调用实现完整视频播放。

## 未确认点

1. `player.bin` 是从 BDA 本体中解出，还是已经存在于磁盘。
2. `player.cfg` 的准确格式和作用。
3. SYS `+0x06c/+0x070/+0x074/+0x078` 是否包含视频设备初始化，还是仅用于
   音频输出。
4. 视频启动序列里 `FS+0x068` 的调用上下文仍需继续映射；C200 已确认该 offset
   是内部 file-object block read helper，不是 public stat/access API，也不是普通
   文件路径 API。

## 后续静态任务

1. 定位内嵌 `player.bin` 边界，并与文件系统副本对比。
2. 提取 MPlayer/codec 代码附近字符串，识别导入函数表。
3. 围绕 SYS 调用对比 `飞天影音` 和 `飞天音乐`，区分音频与视频设备操作。
4. 启动序列映射完成后，用 `player.bin` 调用细节更新 `media_notes.md`。

