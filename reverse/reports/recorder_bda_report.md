# 数码录音.bda 逆向报告

目标：`应用/程序/数码录音.bda`

证据：

- `reverse/reports/recorder_layout.json`
- `reverse/reports/recorder_calls.txt`
- `reverse/reports/recorder_sys_context.txt`
- `reverse/reports/recorder_fs_context.txt`
- `reverse/reports/recorder_media.txt`
- `reverse/reports/recorder_dlx.txt`

## 头部和布局

```text
菜单标题         数码录音
分类             0x08
文件大小         82364 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS/global 范围  0x81c0abe0..0x81e35731
checksum          inventory 中为 ok
```

BSS 范围远大于代码文件，符合录音/播放应用需要大缓冲区或后端状态的特征。

启动代码中检测到的运行时表全局变量：

```text
RES 0x81c0abe0
GUI 0x81c0abe4
SYS 0x81c0abe8
FS  0x81c0abec
MEM 0x81c0abf0
```

## 外部资源

该 BDA 引用两个 DLX 皮肤文件：

```text
\shell\record_A.dlx
\shell\record_B.dlx
```

两个文件都存在于 `应用/数据/shell`。`dlx_inspect.py` 识别它们为 variant-3
DLX 包，各有 18 个资源。每个资源都是 type 1，并可解码为 VX RGB565 图片。
重要尺寸包括：

```text
240x320 全屏背景
126x30  状态/按钮条
110x34  标签/按钮
47x50   控件
32x30 和 19x19 图标
45x3    进度线片段
```

按当前 DLX 检查结果，这个应用不需要非图片资源类型。

## 字符串和文件模型

相关字符串：

```text
*.wav
.wav
recorder
Rec%5.5d.wav
 play ====>>>%d,%d,%d
###g_RecorderFileName=%s###RecorderCurrPath=%s###
```

这些字符串说明：

- 文件列表过滤器是 `*.wav`。
- 自动生成的录音文件名形如 `Rec00000.wav`。
- 应用维护当前录音目录/路径全局变量。
- 播放路径带有诊断日志。

## API 使用概览

已分类间接调用：

```text
FS      40 次
GUI     58 次
SYS     77 次
MEM      5 次
RES     11 次
total  181 次
```

高频系统/媒体偏移：

```text
SYS +0x004  28
SYS +0x020  25
SYS +0x02c  13
SYS +0x040   2
SYS +0x08c   2
SYS +0x090   2
RES +0x094  11
```

`SYS+0x004/+0x020/+0x02c` 调用簇与 `飞天音乐.bda` 中已见的高层媒体后端簇
一致，不同于 `GAMEBOY.BDA` 的原始 PCM 路径。当前 SDK 应把这些偏移记录为
录音/音乐后端候选，而不是直接命名为最终音频 ABI。

`RES+0x094` 使用 11 次。硬件探针已经显示这个偏移更像 trace/log，而不是 DLX
加载器。录音应用中带格式占位符的字符串也符合这个解释。

## 文件系统行为

录音应用使用：

```text
FS +0x000  fopen 类
FS +0x004  fclose 类
FS +0x008  fread 类
FS +0x010  fseek 类
FS +0x024  remove/delete 类
FS +0x02c  chdir/目录存在检查类
FS +0x030  mkdir 类
FS +0x03c  findfirst 类
FS +0x040  findnext 类
FS +0x044  findclose 类
FS +0x048  disk-info/free-space 类
FS +0x078  存储/路径辅助，未命名
FS +0x07c  storage-ready 类
```

第一个 helper 会打开文件、读取 `0x24` 字节，并在加载 UI 资源时检查 DLX magic。
后续独立 FS 调用点负责 WAV 列表枚举、删除和生成录音文件名。

重复出现的 `FS+0x024` 调用点可交叉验证其他文件管理类应用中推断出的
delete/remove 语义。

## GUI 和事件行为

应用使用正常事件循环偏移：

```text
GUI +0x030  poll 类
GUI +0x050  step 类
GUI +0x054  dispatch 类
GUI +0x17c  destroy/close frame 类
```

它也使用常见窗口/控件/资源偏移：

```text
GUI +0x074, +0x03c
GUI +0x0e4/+0x0e8
GUI +0x1ac/+0x1b0
GUI +0x338/+0x33c/+0x378/+0x4f0
GUI +0x46c
```

这里的文字偏移调用比记事本/电子图书少，但足以确认录音 UI 使用同一套 GUI
栈，而不是完全自定义的游戏 framebuffer。

## 交叉验证

- 与 `飞天音乐.bda`：共享 SYS 高层媒体调用簇 `+0x004/+0x020/+0x02c`，并且
  `RES+0x094` 调用很多。
- 与 `记事本.bda` 和 FS 探针：确认 FS 表包含普通 C 风格文件操作，以及
  find/delete/storage 辅助函数。
- 与 DLX 工作：确认另一个量产应用的 DLX 资源也只是 type-1 VX 图片。

## 未确认点

1. `SYS+0x004`、`SYS+0x020`、`SYS+0x02c` 的准确签名尚未解决；它们很可能是
   后端状态/播放器/录音器操作。
2. `SYS+0x08c/+0x090` 在这里各只出现两次，命名前应与 `GAMEBOY.BDA`、视频和
   音乐应用对比。
3. WAV 头写入路径还需要更细的函数级切片，确认录音是直接使用 `FS+0x00c`
   输出，还是主要委托给 SYS 媒体后端。
