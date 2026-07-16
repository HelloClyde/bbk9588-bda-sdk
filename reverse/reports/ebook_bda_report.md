# 电子图书.bda 逆向报告

目标：`应用/程序/电子图书.bda`

证据：

- `reverse/reports/ebook_layout.json`
- `reverse/reports/ebook_calls.txt`
- `reverse/reports/ebook_text_context.txt`
- `reverse/reports/ebook_img_context.txt`
- `reverse/reports/ebook_media.txt`
- `reverse/reports/ebook_dlx.txt`
- `reverse/reports/ebook_extra_dlx.txt`

## 头部和布局

```text
菜单标题         电子图书
分类             0x08
文件大小         147116 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS/global 范围  0x81c1a8d0..0x81c1f861
checksum          inventory 中为 ok
```

启动代码中检测到的运行时表全局变量：

```text
RES 0x81c1a8d0
GUI 0x81c1a8d4
SYS 0x81c1a8d8
FS  0x81c1a8dc
MEM 0x81c1a8e0
```

## 外部资源

该 BDA 直接引用：

```text
\shell\ebook_res_black.dlx
\shell\ebook_res_blue.dlx
```

两个资源都存在于 `应用/数据/shell`。每个包都有 22 个 type-1 VX 资源。资源包
明显偏 UI：

```text
240x320 全屏页面/背景
240x69  页眉/页脚区域
240x30  条栏/列表行
236x178 面板
65x92   插图/图标块
17x19 / 17x20 小图标
```

还存在结构非常相近的相关资源：

```text
\shell\ebook_A.dlx
\shell\ebook_B.dlx
\shell\ebookpic.dlx
\shell\newebookpic.dlx
```

当前分析的应用直接引用 `ebook_res_*` 这一对。额外 ebook DLX 文件可能是旧皮肤
或其他启动路径使用的备用皮肤。

## API 使用概览

已分类间接调用：

```text
GUI      446 次
FS        63 次
MEM       14 次
RES       12 次
SYS        5 次
UNKNOWN   12 次
total    532 次
```

该应用主要由 GUI 驱动。它对 SDK 最有价值的部分是文字、窗口/控件、
图片/资源绘制和文件导航行为。

高频 GUI 偏移：

```text
GUI +0x03c  34
GUI +0x2fc  29
GUI +0x4f0  27
GUI +0x40c  24
GUI +0x33c  22
GUI +0x0e0  22
GUI +0x040  22
GUI +0x46c  20
GUI +0x274  16
GUI +0x4a8  13
GUI +0x35c  12
```

## 文字绘制证据

`GUI+0x4f0` 被调用 27 次。调用上下文与记事本中见到的文字绘制 helper 一致：

```text
lw   v0, 0x4f0(gui)
a0 = draw/window/context
a1 = x
a2 = y
a3 = string pointer
sp+0x10 = -1 or style/color-like value
jalr v0
```

示例：

```text
0x81c0054c: a1=s4, a2=s0, a3=s2, sp+0x10=-1
0x81c02d20: a1=0x20, a2=4, a3=0x81c16d88
0x81c02da8: a1=0xa8, a2=0x12d, a3=0x81c16d90
0x81c0a79c: a1=0x34, a2=0x22, a3=s1
```

这比早期独立文字探针更有证据价值，因为调用发生在应用正常窗口/绘制生命周期中。
旧的易崩溃文字探针很可能调用了正确 helper，但缺少完整 frame 生命周期。

## 资源和图片绘制证据

`GUI+0x46c` 被调用 20 次。上下文反复从小资源记录读取相邻两个值：

```text
lw a1, 0(record)
lw a2, 4(record)
lw v0, 0x46c(gui)
jalr v0
```

其他调用点使用栈上的成对值，然后立即调用 `GUI+0x0f8` 或处理返回尺寸的辅助代码。
这强化了当前解释：`GUI+0x46c` 是读取类应用、图片应用和 DLX UI 屏幕都会使用的
资源/图片相关 helper。

该应用还使用 `GUI+0x35c/+0x40c/+0x410/+0x418` 附近的图片流程偏移，与相册证据重叠。

## 文件系统行为

电子图书使用广泛但常规的 FS 调用组：

```text
FS +0x000  fopen 类
FS +0x004  fclose 类
FS +0x008  fread 类
FS +0x00c  fwrite 类
FS +0x010  fseek 类
FS +0x014  ftell 类
FS +0x024  remove/delete 类
FS +0x02c  chdir/目录存在检查类
FS +0x030  mkdir 类
FS +0x048  disk-info/free-space 类
FS +0x07c  storage-ready 类
```

与记事本和录音应用对比后，可以确认同一套 C 风格文件 API 同时服务于阅读器和工具类应用。

## 事件和窗口行为

标准事件循环存在：

```text
GUI +0x030  poll 类
GUI +0x050  step 类
GUI +0x054  dispatch 类
GUI +0x17c  destroy/close frame 类
```

窗口/控件偏移密集出现：

```text
GUI +0x1a4/+0x1a8/+0x1ac/+0x1b0
GUI +0x270/+0x274/+0x27c
GUI +0x2fc/+0x304/+0x308/+0x30c
GUI +0x338/+0x33c/+0x378
GUI +0x490/+0x498/+0x4a8
```

电子图书比 Element 功能更丰富，又比记事本小很多，是下一轮窗口/控件 SDK
补全的好目标。

## 交叉验证

- 与 `记事本.bda`：确认 `GUI+0x4f0` 在真实生命周期内执行文字绘制。
- 与 `我的相册.bda`：重叠于图片/资源偏移 `GUI+0x35c/+0x40c/+0x410/+0x418`。
- 与 Element/DLX 图片探针：确认量产应用使用纯 VX 的 DLX 包构造复杂界面，
  不只是简单图片测试。
- 与 FS 笔记：确认阅读器应用也使用 `fopen/fread/fseek/ftell` 风格调用和
  存储辅助函数。

## 未确认点

1. `GUI+0x270/+0x274/+0x27c` 附近的控件描述符需要专门的控件创建分析。
2. `RES+0x064` 出现一次，含义尚未命名。
3. `UNKNOWN` 表调用很可能是应用私有函数指针表或 GUI 回调记录；没有 xref
   证据前不应提升为 SDK API。
