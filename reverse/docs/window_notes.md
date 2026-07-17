# Window/Control 创建笔记

本文记录 BDA GUI table 里已经能用于开发的 window、control、draw 生命周期。名称仍带
`_LIKE` 的接口表示 ABI 还在继续确认，但 offset 和基本调用形状已有样本或 C200
固件支撑。

## Control 创建：GUI +0x1a4

`GUI+0x1a4` 创建 window 或 child control。当前 SDK wrapper 是
`bda_gui_create_window_like()`：

```c
bda_handle_t bda_gui_create_window_like(
    const char *class_name,
    const char *caption,
    u32 style,
    u32 flags,
    u32 id,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    bda_handle_t parent,
    u32 extra
);
```

当前推断 ABI：

```text
a0          = class name
a1          = caption/title string or 0
a2          = style
a3          = flags/extended style, often 0
stack+0x10  = control id
stack+0x14  = x
stack+0x18  = y
stack+0x1c  = width
stack+0x20  = height
stack+0x24  = parent/window handle
stack+0x28  = extra/user data
```

C200 中该 entry 目标为 `0x800ccfac`，函数会读取这些 stack 参数并传入内部 control 构造
路径。旧的 `bda_gui_create_ex()` 参数顺序来自早期 probe 误名，已从 SDK 删除；
新代码只应使用 `bda_gui_create_window_like()`。

已观察到的 class/caption：

```text
"listbox"    记事本
"ListBox"    记事本中作为 caption/string 使用
"edit"       系统设置
"medit"      记事本，多行 edit；TXT 正文由该系统控件渲染
"EB_SCROLL"  电子书滚动条
```

样本调用形态：

```text
create("medit", 0, 0x08000000, 0, 0x6e, 0x3c, 0x1b, 0xa8, 0x14, parent, 0)
create("medit", "", 0x08083001, 0, 0x65, 0, 0x46, 0xf0, 0x82, parent, 0)
create("listbox", "ListBox", 0x08090001, 0, 0x6a, 0, 0xda, 0xf0, 0x109, parent, 0)
create("EB_SCROLL", 0, 0x08000000, 0, 0x400, 0x0b, 0x7a, 0xa0, 0x12, parent, 0)
create("edit", caption, 1, 0, 2, 0, 0, 0, 0, parent, 0)
```

不要在 bare `main()` 里随便用空 parent 创建 edit/listbox control。原机应用通常先
取得已有 frame/window context，再创建 child control 并用 `GUI+0x040` 设置属性。
hardware probe 显示，缺少 context 的直接创建容易重启。

## 顶层 Frame Descriptor：GUI +0x084

时间入口替换路径不是通用 GUI bootstrap。真机反馈显示，把 `Mine.bda` 直接替换为
`应用\程序\时间.bda` 后，以下版本都不应再作为可运行 GUI 示例：

- frame/window/text 版本：emu 和真机会崩到 PC=0。
- messagebox-only 版本：仍可能在时间入口上下文崩溃。
- `bda_sys_delay_like()` no-GUI 版本：真机仍可死机，说明 SYS table call 也不能当作
  该入口下的安全 keepalive。

当前 `example/games/minesweeper/minesweeper_bda.c` 已彻底移除雷霆模板、patch 和 BDA 内部绝对
地址。它使用 `style=0`、`surface=0` 的 standalone frame，按已验证顺序执行
`stop -> release -> event poll -> close -> return`，并通过 compatible back surface
一次提交完整 VX 画面。8013 已完成触摸、胜负和 ESC 退出闭环；图形链仍需真机复测。
硬编码时间入口的失败结论不变，不要把该示例替换到 `时间.bda` 路径。

`GUI+0x084` 用一个 0x34 byte descriptor 注册顶层 frame。C200 中目标函数为
`0x800cc1c8`，会分配约 0x114 byte 内部 object，并读取 descriptor `+0x00..+0x30`
范围内的字段。SDK 中对应结构是 `bda_frame_desc_like_t`。

当前字段：

```text
+0x00 style              计算器样本使用 0x08000000
+0x04 internal28         C200 会写入内部 object +0x28，语义未命名
+0x08 title              title/name 字符串，会复制到内部 object
+0x0c internal44         C200 会写入内部 object +0x44
+0x10 internal48         C200 会写入内部 object +0x48
+0x14 helper_arg14       C200 注册前会传给内部 helper
+0x18 wndproc            window procedure function pointer
+0x1c x                  常见为 0
+0x20 y                  常见为 0
+0x24 height             计算器/BBVM 样本常见值 240
+0x28 width              计算器/BBVM 样本常见值 320
+0x2c surface            常用 GUI+0x2fc(15) 返回 object/surface
+0x30 aux30              C200 会写入内部 object +0x80，常见为 0
```

`bda_frame_desc_init_like()` 按 no-template BDA 的稳定路径初始化字段：

```c
bda_frame_desc_like_t desc;
bda_frame_desc_init_like(&desc, "标题", wndproc, 320, 240, 0);
frame = bda_gui_register_frame_desc_like(&desc);
```

这里的 `internal*` 和 `aux30` 仍只表示已确认写入位置；新代码一般只需要
`style/title/wndproc/x/y/width/height/surface`。

注意：旧文档把 `style=0x08000000` 和 `surface=GUI+0x2fc(15)` 写成通用最小
组合，这是不准确的。原机复杂应用经常这样做，但 no-template BDA 在 emu 中用
`style=0,surface=0` 更稳；`0x08000000` 会进入额外内部状态路径，`GUI+0x2fc`
返回的 object/surface 也依赖原机窗口上下文。开发新 BDA 时先使用 helper 的默认值，
需要复刻原机窗口管理时再显式设置。

`GUI+0x084` 注册过程中会同步触发 create 类 message。wndproc 在 create 分支里
不要立刻做 `begin_draw`、`blit` 或大块绘制；应只做轻量初始化，真正绘制放到
注册返回并 activate 之后，或放在后续 redraw/input 分支。
对 tile 游戏还要避免把 `GUI+0x074(0)` / `bda_gui_draw_guard_end_like()` 放进
每个 tile 的绘制循环；它是 present/update 边界，不是方块级 flip API。旧扫雷真机
反馈中的逐块刷新和绘制完成后死机，正符合这种错误 lifecycle。`TileBlit` 的后续真机
结果进一步确认：即使只在循环外统一 present，缺少原机 game surface/context 时仍会逐块
flip 并死机，所以 `GUI+0x074/+0x400` 不能作为 bare BDA 绘图入口。

注册后的典型 event loop：

```text
GUI+0x030(message_buffer, frame_handle)  -> 返回非 0 时继续循环
GUI+0x050(message_buffer)
GUI+0x054(message_buffer)
GUI+0x17c(frame_handle)                 -> close/destroy frame
```

`message_buffer` 固定使用 `bda_gui_message_like_t`，大小为 `BDA_GUI_MESSAGE_SIZE`
也就是 `0x1c` byte。
C200 的 `GUI+0x030` 会先清零这段 buffer，再写入
`handle/message/wparam/lparam` 等字段；`GUI+0x050` 会读取同一个 buffer，
并只对 message `0x10/0x13` 做派生通知；`GUI+0x054` 负责调用目标 handle
的 `+0x88` wndproc。

`bda_gui_message_like_t` 当前 layout 是 `handle`、`message`、`wparam`、`lparam`、
`aux10`、`aux14`、`aux18`。后三个字段来自 C200 清零/写回范围和 dispatch 路径，
暂按内部派生状态处理，不应由应用主动构造复杂含义。

```c
bda_gui_message_like_t msg;
while (bda_gui_event_poll_like(&msg, frame)) {
    bda_gui_event_step_like(&msg);
    bda_gui_event_dispatch_like(&msg);
}
```

message 发送有同步和异步两条路：

```text
GUI+0x040  send-like；直接调用 handle+0x88 wndproc，返回 callback result
GUI+0x03c  notify/post-like；写入 frame queue 或设置 0xb1 pending flag
```

需要立即得到 return value 时用 `bda_gui_send()`；需要交给 event loop 后续处理时用
`bda_gui_notify_like()`。`BDA_MSG_REDRAW_INPUT_LIKE(0xb1)` 在 notify 路径中是
特殊 pending flag，不是 standard queue item。

frame 生命周期 wrapper 分工：

```text
GUI+0x04c  frame release/request-like；标记目标对象高位状态 flag，不是 close
GUI+0x088  frame stop-like；解析 frame 后向子对象/自身发送内部 stop message
GUI+0x134  active frame set-like；切换 manager+0xd8，并向旧/新 frame 发 0x31/0x30
GUI+0x13c  active child get-like；读取 context，解析所属 container 后返回 container+0xd8
GUI+0x098  frame activate/state-like；参数是 handle,mode，mode 不是 show flag
GUI+0x17c  close frame-like；释放关联对象、frame 本体，并清空 active frame 全局槽
```

真机 V11 已确认顶层 frame 必须按
`stop -> release -> event poll 结束 -> close -> bda_main return` 收尾。公开代码调用
`void bda_gui_close_frame(frame)`；不要读取
`GUI+0x17c` 的返回寄存器。不要用 child-control `bda_gui_destroy_like()` 替代顶层 frame
close；也不要在不了解 mode 的情况下把
`bda_gui_frame_activate_like()` 当成 show/hide wrapper。`bda_gui_frame_release_like()`
只是 request/mark 类 wrapper，不负责释放 frame 本体；`bda_gui_active_frame_set_like()`
用于复刻原机 frame 切换流程，不要把 return value 当作新 active handle。
`bda_gui_active_child_get_like(context)` 只查询有效 context 所属 container 的 active-child
slot，不创建或激活 frame，也不能把 bare `bda_main()` 变成可绘制 GUI 上下文。该 API
不能无参调用；否则 C200 会解引用未定义的 `a0`。

完整真机证据、触摸消息 ABI 和可直接复用的生命周期骨架见
`docs/verified/touch_window_lifecycle_api.md`。

## Window Procedure fallback：GUI +0x08c

`GUI+0x08c` 是 default window procedure-like wrapper，签名与 SDK 的
`bda_wndproc_t(hwnd, message, wparam, lparam)` 一致。C200 会按 message 区间分组
处理 system message，并对 `0xb0..0xb3` 这组 input/redraw message 走专门路径。

custom callback 的推荐形态：

```c
static int wndproc(bda_handle_t hwnd, u32 message, u32 wparam, u32 lparam) {
    if (message == BDA_MSG_CREATE) {
        return 0;
    }
    return bda_gui_default_proc_like(hwnd, message, wparam, lparam);
}
```

不要把 `GUI+0x08c` 当成通用 send/dispatch API；它是 callback fallback。主动给
control 或 frame 发 message 时仍使用 `bda_gui_send()` 或 `bda_gui_notify_like()`。

## Draw 生命周期：GUI +0x308 / +0x30c

记事本等路径中常见 draw 顺序：

```text
draw = GUI+0x308(window_or_control_handle)
bda_gui_draw_guard_begin_like()  /* GUI+0x074(1) */
... draw images/text with draw ...
bda_gui_draw_guard_end_like()    /* GUI+0x074(0) */
GUI+0x30c(draw)
```

C200 中：

- `GUI+0x308` 目标 `0x800bce50`，从一组 5 个普通 draw context slot 中取/初始化
  draw context，并以 mode=1 调用内部 helper。紧邻第 6 个 `0xd4` 区域是保留 context，
  不是普通槽；固件扫描会检查它，满池后还会计算越界地址。
- `GUI+0x304` 目标 `0x800bceec`，使用同一组 draw context slot，但以 mode=0
  调用内部 helper。它不是无参数 getter，也不是创建 frame/window 生命周期的入口。
- `GUI+0x30c` 目标 `0x800bd4b0`，释放/刷新 draw context，并清理部分状态。
- 每次 `GUI+0x304/+0x308` 成功返回都必须有且仅有一次 `GUI+0x30c`。只释放
  `GUI+0x310` 创建的 compatible context 不能归还 fixed draw slot。
- `GUI+0x074` 目标 `0x800d48a8` 会把 `a0` 写入全局状态；`a0==0` 时若内部
  present/update object 存在，会继续调用 `0x8012c8f0`。SDK 因此删除无参数
  wrapper，只保留显式 `bda_gui_pump_present_arg_like(draw_guard_enabled)` 和
  `bda_gui_draw_guard_begin_like()` / `bda_gui_draw_guard_end_like()`。

BBVM 给出了另一条已验证可显示文本的路径：window procedure 在
`BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE` (`0x60`) 中通过 `GUI+0x304(frame_handle)`
获取 draw handle，绘制时使用：

```text
bda_gui_draw_guard_begin_like()
GUI+0x4f0(draw, x, y, text, -1)
GUI+0x0e0(frame)
bda_gui_draw_guard_end_like()
```

color/text mode 设置在 draw handle 上：

```text
color = GUI+0x378(draw, r, g, b)
GUI+0x334(draw, color)  background/fill color-like
GUI+0x33c(draw, color)  foreground/text color-like
GUI+0x338(draw, mode)
```

hardware probe 已确认 BBVM 风格路径可以显示黑字白底文本；Thunder/Tank 也在
`0x60` 中保存 callback object 并调用 `GUI+0x304(object)`，在
`BDA_MSG_DRAW_CONTEXT_DETACH_LIKE` (`0x66`) 中走 `GUI+0x30c/+0x088/+0x04c`
清理。未完全解决的问题是独立 probe 的 frame 生命周期和退出清理。复用 BBVM 模型时
要同时复刻外围 event/state 机，不要只复制局部 `0x66` cleanup。

## gifctrl 内存资源和 timer 生命周期

C200 在 `0x800ea3f4` 注册真实类名 `gifctrl`，draw object kind 为 `0x21`，window
procedure 位于 `0x800ea1c0`。当前恢复出的关键路径：

- `0x60`：仅当 style 低 4 bit 为 1 时分配 `0x340` byte decoder state；从
  object `+0x80` 指向的 descriptor 读取 `+0x00` GIF data pointer 和 `+0x08`
  timer id。descriptor `+0x04` 在该路径中没有被读取。
- 初始化会用 `0x800de150(handle, timer_id, 1)` 注册 timer。timer callback 以
  message `0x144` 回到该 control，且 `wparam` 必须等于 timer id。
- `0x144` 通过 `0x800bce50` 获取 fixed draw context，调用 `0x800b0324` 解析并绘制
  下一帧，再以 `0x800bd4b0` 成对释放 draw context。解析器识别 GIF trailer、image
  descriptor、extension block 和 LZW data，并把 Graphic Control Extension delay
  写入 state `+0x18`；delay 改变时由 `0x800de0f8` 重设 timer。
- parser 返回 trailer 时，control 把当前 data pointer 重置为起始 pointer，形成循环；
  parser 没有从 descriptor 接收 buffer 长度，因此损坏或截断数据存在越界风险。
- `0x64` 先调用 `0x800de190(handle, timer_id)` 删除 timer，再释放 `0x340` byte state，
  最后进入 default procedure。应用必须在关闭 parent frame 前销毁 gifctrl。

8013 的 `GIFCTRL V2` probe 用内嵌双帧 GIF89a 验证了自动换帧；正式公开示例把
descriptor `+0x04` 保持为 0，并同样完成播放、child destroy 和返回菜单。开发者 ABI、
截图和日志见 `docs/verified/controls_api.md`。

## Message/属性调用

`GUI+0x03c` 和 `GUI+0x040` 都像 handle/message/value/value 形状：

```text
a0 = handle
a1 = message/property id
a2 = value
a3 = value
```

`GUI+0x040` 高频用于 edit control 属性和 command message。已见 id 包括 `0xf184`、
`0xf186`、`0xf0dd`、`0xf0df`、`0xf1b5`、`0x864`。

记事本已固定的 `medit` 文本消息：

```text
GUI+0x040(control, 0x0133, capacity, output_buffer)  get text
GUI+0x040(control, 0x0134, 0, text_buffer)           set text
GUI+0x040(control, 0xf0c5, max_length, 0)            set max length
```

正文容量/上限为 `0x19000`，标题 get-text 容量为 `0x14`，标题上限为 `0x16`。
这些数字是 `GUI+0x040` 的第二参数，即 control message id；`0x0134` 不是
GUI table 的 `GUI+0x134` active-frame setter。

`GUI+0x03c` 像相关的 notify/post/send 路径，常见 message 有 `0x66`、`0x10`、
`0x120`、`0x805`、`0x806`。若没有确认，不要把 `0x66` 当 standard refresh message；多个
应用在关闭/退出视图时也会使用它。

## Destroy/Refresh

- `GUI+0x1a8(handle)` 用于销毁 `GUI+0x1a4` 创建出的 child control/object。
  C200 要求对象 kind 为 `1`、subtype 为 `0x12`，先同步发送内部 `0x64` message，
  再从 parent/manager 链接中摘除并释放资源。它不是顶层 frame close。
- `GUI+0x1ac(handle, a1, a2)` 会发送内部 message `0x162`。
- `GUI+0x1b0(handle, a1)` 会发送内部 message `0x163`。
- `GUI+0x1b4(a0, a1)` 不发送 message；它只扫描 `0x804a6b40` GUI 记录表，
  比较记录 `+0/+4` 并返回 `0/1`，不能当成通用 handle validity check。
- `GUI+0x07c/+0x080/+0x0b0` 是 kind=1 object 的 `+0x24` flags clear/OR/get helper；
  `+0x080` 置位，`+0x07c` 清除 mask 对应 bit，成功返回 `1`；`+0x0b0`
  读取 flags，失败返回 `0`。它们不是通用 show/hide/enable/disable API。
- `GUI+0x0b8/+0x0bc/+0x0c0/+0x0c4` 是 kind=1 object 的 `+0x80/+0x84`
  caller data word getter/setter；setter 返回旧值，会改 object 内部字段。
- `GUI+0x0c8/+0x0cc` 进一步要求 subtype `0x12`，通过 `handle+0xec` 指向的
  payload 访问 `payload+0x1c` word；setter 同样返回旧值。
- `GUI+0x0d0` 是 kind=1 object 的 `+0x8c` pointer getter；相邻 `GUI+0x0d4`
  会按 subtype 分配/释放资源或发送 `0x134` message，暂不公开 SDK wrapper。
- `GUI+0x0d8/+0x0dc` 是 kind=1 object 的 `+0x88` pointer getter/setter；
  setter 只有 value 非 0 时才写入。该字段接近 wndproc/callback 指针，不要随意改。
- `GUI+0x1ac(handle, 0x64, 0x190)` 与 `GUI+0x1b0(handle, 0x64)` 在九门课程
  中成对出现，像 object layout/refresh notify。C200 会构造 stack message packet 并
  通过同步 send 派发，具体效果由目标对象 wndproc 决定。SDK 暂命名为
  `bda_gui_object_update3_like()` 和 `bda_gui_object_update2_like()`。
- `GUI+0x0e4/+0x0e8` 与 object 级 draw begin/end 相关；C200 内部会分别调用
  `GUI+0x308/+0x30c` 对应函数。SDK 暂命名为
  `bda_gui_object_draw_begin_like()` / `bda_gui_object_draw_end_like()`。
  `begin` 会递增 `object+0x54+0x1c` 的 draw 计数，并可能根据 `object+0x7c`
  的附加描述符进入额外准备路径；`end` 必须传回同一个 object 和 begin 返回的
  draw context，不能把它当作无状态 present/flush。
- `GUI+0x0f4(handle, &x, &y)` 会沿 object 父链累计 `+0x14/+0x18` 坐标字段，
  可用于把局部坐标转换为累计原点坐标。SDK 暂命名为
  `bda_gui_accumulate_origin_like()`。
- `GUI+0x0f8(handle, &x, &y)` 是同一组坐标字段的反向换算，会沿 object 父链
  从 `x/y` 中减去 `+0x14/+0x18`。SDK 暂命名为
  `bda_gui_subtract_origin_like()`。

## 仍需补齐

- 顶层 app/window bootstrap callback 的完整所有权关系。
- `GUI+0x084` 描述符中 `internal28/internal44/internal48/helper_arg14/aux30` 的正式语义。
