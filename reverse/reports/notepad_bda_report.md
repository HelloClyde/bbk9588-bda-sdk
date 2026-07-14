# 记事本.bda 逆向报告

## 状态

首版静态报告。证据来自：

```text
应用/程序/记事本.bda
reverse/reports/bda_inventory.json
reverse/reports/notepad_calls.txt
sdk/doc/text_notes.md
sdk/doc/window_notes.md
sdk/doc/fs_notes.md
```

这份报告还不是完整函数级逆向；当前阶段先固定布局、资源文件和
SDK/API 使用证据，供后续交叉验证。

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

## 文字绘制交叉验证

已出现文字相关调用：

```text
GUI +0x338  设置文字模式候选        6 次
GUI +0x33c  设置文字颜色候选        8 次
GUI +0x378  RGB/颜色辅助候选        8 次
GUI +0x4f0  绘制文字候选           11 次
```

这支持早期硬件观察：修改记事本窗口文字可以显示 `NAME-OK` 和 `BODY-OK`。
它也比曾经崩溃的独立文字探针更适合作为文字 SDK 的依据，因为记事本是在
正常窗口/控件生命周期内执行文字绘制。

当前假设：

- `GUI+0x4f0` 可以用于文字渲染。
- 不稳定探针可能使用了错误生命周期、错误句柄，或者在 GUI 分发/绘制状态
  仍活动时退出。
- 后续文字探针应复制记事本的调用上下文，而不是对任意句柄直接调用
  `draw_text`。

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
3. `GUI+0x134`、`+0x138`、`+0x46c` 以及 bitmap/control 辅助调用的参数布局。
4. 记事本是否使用与 Element 相同的 `0x00b1` 重绘/输入消息语义。
5. 稳定自定义文字渲染所需的文字控件生命周期。

## 后续静态任务

1. 反汇编 `记事本.bda`，并在全部 12 处 `GUI+0x084` frame 注册附近建立函数标签。
2. 提取 `GUI+0x4f0` 文字调用上下文，并与 `text_notes.md` 对比。
3. 提取 `FS+0x03c/+0x040/+0x044` 上下文，用记事本 find-data 布局更新
   `fs_notes.md`。
4. 与 `元素周期表.bda` 对比命令常量（`0x66`、`0x7fd`、`0x083e`、`0x0844`、
   `0x00b1`）。

