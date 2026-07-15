# 记事本.bda 逆向报告

## 状态

函数级文字路径报告。证据来自：

```text
应用/程序/记事本.bda
reverse/reports/bda_inventory.json
reverse/reports/notepad_calls.txt
sdk/doc/text_notes.md
sdk/doc/window_notes.md
sdk/doc/fs_notes.md
```

这份报告还不是记事本全部业务逻辑的完整逆向，但已经固定短标签绘制、`medit`
控件创建、TXT 读取和正文 set/get text 的函数级调用链。

## 头部和布局

```text
文件大小          138,460 bytes
菜单标题         记事本
分类           0x09
入口文件偏移  0x95f8
运行时入口 VA   0x81c00020
运行时文件基址  0x81bf6a28
BSS                0x81c18700..0x81c32801
头部 checksum    ok
```

缓存的运行时表全局变量：

```text
RES  0x81c18700
GUI  0x81c18704
SYS  0x81c18708
FS   0x81c1870c
MEM  0x81c18710
```

这个布局符合 `元素周期表.bda` 使用的常见原生 BDA 模型：启动代码会把
`0x81c00004..0x81c00014` 的运行时表指针复制到应用自己的 BSS 全局变量，
之后所有 SDK 调用都通过这些全局变量间接完成。

## 外部资源

静态 DLX 引用：

```text
\shell\FP_PIC_BLUE.dlx
\shell\FP_PIC_BLACK.dlx
\shell\EnoteBlueSearch.dlx
\shell\text_A.dlx
\shell\text_B.dlx
\shell\enote_black_add.dlx
\shell\enote_corner.dlx
```

解释：

- `text_A.dlx` / `text_B.dlx` 是共享文字 UI 资源。这与早期使用
  `text_A.dlx` 的文字/图片实验互相印证。
- `EnoteBlueSearch.dlx`、`enote_black_add.dlx`、`enote_corner.dlx`
  更像是记事本专用皮肤或 UI 片段。
- `_BLUE`/`_BLACK` 成对出现，说明应用至少支持两套 shell 主题。

## API 使用概览

`记事本.bda` 当前扫描器分类出 955 个运行时表间接调用。最强的调用组：

```text
GUI +0x040  184 次  send/message-like
GUI +0x074  139 次  draw/present state guard
GUI +0x308   77 次  begin draw
GUI +0x30c   62 次  end draw
GUI +0x03c   53 次  notify/message-like
GUI +0x2b8   46 次  message box
GUI +0x084   12 次  register frame
GUI +0x030   12 次  event poll
GUI +0x050   12 次  event step
GUI +0x054   12 次  event dispatch
GUI +0x17c   12 次  close/release frame

FS  +0x000   22 次  open/fopen-like
FS  +0x004   23 次  close/fclose-like
FS  +0x024   32 次  remove/delete-like
FS  +0x03c   10 次  findfirst-like
FS  +0x040    1 次   findnext-like
FS  +0x044    1 次   findclose-like

SYS +0x080   38 次  delay/sleep-like
RES +0x094   17 次  trace/log-like
```

GUI 事件循环数量值得注意：共有 12 次 frame 注册，并有 12 组匹配的
`GUI+0x030/+0x050/+0x054/+0x17c` 调用。不同于窗口数量较少的
`元素周期表`，记事本看起来会创建多个模态页面或对话框。

## 文字渲染路径

已出现文字相关调用：

```text
GUI +0x338  设置文字模式候选        6 次
GUI +0x33c  设置文字颜色候选        8 次
GUI +0x378  RGB/颜色辅助候选        8 次
GUI +0x4f0  绘制文字候选           11 次
```

记事本使用两条不同的文字路径，不能把“TXT 正文”和“短标签”混为同一种绘制。

### 短标签：GUI +0x4f0

11 个 `GUI+0x4f0` 调用只负责搜索标题、名称/内容标签、窗口标题等短文本。以
`0x81c01878..0x81c019e8` 的搜索标题路径为例：

```text
GUI+0x0e4(frame)                         -> draw
... 背景和资源图绘制 ...
GUI+0x338(draw, 1)
color = GUI+0x378(draw, 255, 255, 255)
GUI+0x33c(draw, color)
GUI+0x4f0(draw, 0x20, 4, label, -1)
GUI+0x0e8(frame, draw)
```

`0x81c09b70..0x81c09bf8` 的“名  称:”和“内  容:”路径使用同一 `draw`，先通过
`GUI+0x378(draw, 0, 0, 0)` 取得黑色，再连续调用两次 `GUI+0x4f0`，最后由同一对象
绘制作用域收尾。真机 patch 已把这两个字符串替换为 `NAME-OK` / `BODY-OK` 并正常显示。

关键差异是：这些短标签的局部调用链中没有 `GUI+0x074(1/0)`。标签、背景资源和其他
图元都位于同一 `GUI+0x0e4/+0x0e8` object draw scope 内。TouchStageV13 虽然加入了
`+0x0e4/+0x0e8`，但仍在内部套用了 `+0x074`，不能称为记事本短标签路径的精确复刻。

### TXT 正文：medit 控件

TXT 正文不经过上述 11 个 `GUI+0x4f0` 调用。记事本通过 `GUI+0x1a4` 创建系统
`"medit"` 多行编辑控件；正文实例的调用形态是：

```text
create("medit", "", 0x08083001, 0,
       0x65, 0, 0x46, 0xf0, 0x82, parent, 0)
```

读取路径 `0x81c0d210..0x81c0d3c8`：

```text
FS+0x000(path, mode)                         open
MEMSET(0x81c197a0, 0, 0x19000)
FS+0x008(0x81c197a0, 0x19000, 1, file)       read
... 内容变换/校验 ...
GUI+0x040(body_medit, 0x0134, 0, 0x81c197a0) set text
FS+0x004(file)                               close
```

保存路径使用反向消息：

```text
GUI+0x040(body_medit, 0x0133, 0x19000, output_buffer) get text
```

标题 edit 使用同一个 `0x0133`，但容量为 `0x14`。`0xf0c5` 消息用于设置最大文本长度，
正文为 `0x19000`，标题为 `0x16`。这里的 `0x0133/0x0134/0xf0c5` 是发给 control 的
窗口消息号；不要和 GUI 函数表偏移 `GUI+0x134` 混淆。

## 文件系统行为

记事本目前是补全原生 FS API 的最佳样本之一：

- open/close/read/write/seek/tell 都已出现。
- `FS+0x024` 有 32 次调用，很可能是 delete/remove。
- `FS+0x03c/+0x040/+0x044` 形成目录枚举调用组。
- 目录准备使用 `FS+0x02c/+0x030`。

这与 `fs_notes.md` 互相印证，继续写目录枚举探针前应优先参考这里的上下文。
Showcase 中得到的重要修正仍然适用：成功 handle 是高地址 pointer，signed 值通常为负数；
必须用 `bda_fs_file_is_valid(handle)` 排除 `0` 和 `0xffffffff` 两个失败哨兵。

## 窗口和事件行为

记事本使用与 Element 相同的大体窗口模型：

```text
GUI+0x2fc  surface/object creation
GUI+0x084  frame registration
GUI+0x030  event poll
GUI+0x050  event step
GUI+0x054  dispatch
GUI+0x17c  final close/release
```

它还大量使用 `GUI+0x040` 和 `GUI+0x03c`，支持 `0x040` 与 `0x03c`
是不同 send/notify 路径的判断。Element 会通过这些路径处理 `0x66` 这类
关闭/返回命令，下一步应检查记事本是否使用相同命令常量。

## 未确认点

1. 记事本文档路径格式和扩展名过滤规则。
2. 列表、编辑、搜索、确认对话框分别对应哪些窗口过程。
3. GUI 函数表 `+0x138`、`+0x46c` 以及 bitmap/control 辅助调用的参数布局。
4. 记事本是否使用与 Element 相同的 `0x00b1` 重绘/输入消息语义。
5. `medit` 初始化消息 `0xf0dd` 第三个参数所指对象的正式语义。

## 后续静态任务

1. 反汇编 `记事本.bda`，并在全部 12 处 `GUI+0x084` frame 注册附近建立函数标签。
2. V18 已确认去掉 `+0x074` 后首帧文字一次性显示，V19 已确认普通触摸 callback
   仍不提交，V20 已确认 `GUI+0x0e0` 不能接收 standalone 顶层 frame，V21 已确认
   `GUI+0x03c` 的 `0xb1` pending 不会变成 custom callback，V22 已确认单独尾部
   `GUI+0x074(0)` 不会提交动态画面；V23 用完整 guard 提交十字，并以应用内 5x7
   点阵字替代动态 `GUI+0x4f0`，真机已确认连续触摸更新正常且无闪烁。
3. 提取 `FS+0x03c/+0x040/+0x044` 上下文，用记事本 find-data 布局更新
   `fs_notes.md`。
4. 与 `元素周期表.bda` 对比命令常量（`0x66`、`0x7fd`、`0x083e`、`0x0844`、
   `0x00b1`）。

