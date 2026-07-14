# 触摸窗口与完整生命周期

本文记录 `TouchStageV11.bda` 在 BBK 9588 真机上完成的首个 standalone BDA
窗口闭环：应用能创建窗口、显示文字和十字、接收触摸坐标、实时写日志，并在按下
退出键后销毁窗口、返回系统主菜单。

这次验证解决的关键问题不是单个绘图函数，而是顶层 frame 的所有权顺序。只有按
本文顺序组合调用，才能把“画面能显示”提升为“应用可以完整启动和退出”。

开发者必须保持的顺序可简写为：
`stop -> release -> event poll 结束 -> close -> bda_main return`。

## 真机结果

测试源码：`reverse/examples/touch_input_stage_probe.c`

测试产物：`build/TouchStageV11.bda`

真机可观察结果：

1. 从系统菜单启动后显示 240x320 触摸测试窗口。
2. 点击屏幕后显示对应坐标和十字，连续点击能够及时更新。
3. `TOUCHDBG.TXT` 按事件实时追加，包含按下和抬起坐标。
4. 按退出键后应用不死机、不停留在冻结画面，能够返回系统主菜单。

测试产物 SHA-256：

```text
6362f946fbd84c74937e75290c082df36be7356dc10a30aa9044e96680da9aa6
```

## 已验证系统接口

下表只表示这些接口按 V11 的参数和组合方式通过了真机闭环，不把它们扩张成任意
上下文都安全的通用 API。

| 表项 | 公开 API | V11 覆盖 |
| --- | --- | --- |
| GUI `+0x030/+0x050/+0x054` | `bda_gui_event_pump_frame_once()` | 使用实际 frame handle 轮询、step、dispatch |
| GUI `+0x04c` | `bda_gui_frame_release()` | stop 后标记 frame 退出 |
| GUI `+0x074` | `bda_gui_draw_guard_begin/end()` | 每次增量重绘的 begin/end 边界 |
| GUI `+0x084` | `bda_gui_register_frame_desc()` | 注册 0x34-byte descriptor 并取得 frame handle |
| GUI `+0x088` | `bda_gui_frame_stop()` | 退出键释放后发起 stop |
| GUI `+0x08c` | `bda_gui_default_proc()` | 非触摸消息交回固件默认过程 |
| GUI `+0x098` | `bda_gui_frame_activate()` | 使用 `mode=0x100` 激活已注册 frame |
| GUI `+0x17c` | `bda_gui_close_frame()` | 事件泵结束后最终释放顶层 frame |
| GUI `+0x2fc` | `bda_gui_draw_object_create()` | `kind=7` 绘图对象 |
| GUI `+0x304` | `bda_gui_current_draw()` | 从 frame 和 attach callback 取得 draw context |
| GUI `+0x338/+0x33c/+0x4f0` | text mode/color/draw text | 绘制标题、坐标和退出提示 |
| GUI `+0x358` | `bda_gui_select_draw_object()` | 绘制前选择、结束后恢复旧对象 |
| GUI `+0x368/+0x378` | put pixel/RGB | 擦除旧十字并绘制新十字 |
| GUI `+0x38c` | `bda_gui_rectangle()` | 绘制触摸区域边框 |
| GUI `+0x5d4` | `bda_gui_input_packet()` | 轮询实体退出键并等待释放 |
| FS `+0x000/+0x00c/+0x004` | open/write/close | `wb` 建立日志，`ab` 实时追加并立即关闭 |
| SYS `+0x080` | `bda_sys_delay()` | 事件循环和按键释放等待中的短延时 |

`bda_memset()`、`bda_fs_file_is_valid()` 和
`bda_gui_input_packet_key_pressed()` 是公开头中的本地 helper，不是额外系统表项。

## 已验证触摸消息

窗口过程收到以下消息：

```text
BDA_MSG_TOUCH_COORDINATE = 1  触摸按下/坐标更新
BDA_MSG_TOUCH_RELEASE    = 2  触摸抬起
lparam low 16 bits   x
lparam high 16 bits  y
```

解析时按 signed 16-bit 扩展，再检查 `0 <= x < 240`、`0 <= y < 320`：

```c
s32 x = (s32)(short)(lparam & 0xffffu);
s32 y = (s32)(short)((lparam >> 16) & 0xffffu);
```

V11 对消息 1/2 返回 `1`，避免把已消费的触摸坐标再次交给默认过程。其他消息继续
调用 `bda_gui_default_proc()`。已经实际观察到的 GUI 消息还包括：

```text
0x60  draw context attach
0xb1  redraw/input notification
```

代码也处理 `0x66` draw context detach：清空 draw context 并设置退出标志。但本次
正常退出可以由 event poll 返回 0 完成，因此不能把“每次退出必定收到 0x66”列为
已验证保证。

## 窗口生命周期

### 1. 初始化 descriptor

V11 使用的最小 standalone 布局是：

```c
bda_frame_desc_t descriptor;

bda_memset(&descriptor, 0, sizeof(descriptor));
descriptor.style = 0;
descriptor.title = "TOUCH V11";
descriptor.wndproc = touch_window_proc;
descriptor.height = 240;
descriptor.width = 320;
descriptor.surface = 0;
```

V11 把 descriptor 放在 `bda_main()` stack 上，而 `bda_main()` 持续运行到 frame 被关闭，
所以测试期间 descriptor 始终有效。这是当前已验证写法；虽然 C200 静态实现会复制主要
字段，但“注册后立即让 descriptor storage 失效”尚未单独做真机 A/B，不应写进推荐模板。

### 2. 注册并激活

```c
frame = bda_gui_register_frame_desc(&descriptor);
if (!frame || (s32)frame == -1) {
    return 1;
}

if (bda_gui_frame_activate(frame, 0x100) == 0) {
    /* 按应用策略处理激活失败。 */
}
```

`register` 和 `activate` 是两个阶段。不要把注册成功等同于窗口已经进入活动状态，也
不要在注册前查询所谓“全局 active frame”。`GUI+0x13c` 实际要求有效 context，错误的
无参调用会解引用未定义 `a0`，真机曾表现为启动即死机。

### 3. 建立绘图状态

```c
draw = bda_gui_current_draw(frame);
draw_object = bda_gui_draw_object_create(7);
if (!draw || !draw_object || (s32)(u32)draw_object == -1) {
    /* 不进入绘图循环。 */
}
```

收到 `BDA_MSG_DRAW_CONTEXT_ATTACH` (`0x60`) 时，应使用 callback 的 `handle` 重新取得
draw context。不要假设注册后取得的 context 永远不变。

绘图必须在 guard 内选择 object，并在结束前恢复旧 object：

```c
void *old_object;

bda_gui_draw_guard_begin();
old_object = bda_gui_select_draw_object(draw, draw_object);
/* put pixel / rectangle / text */
bda_gui_select_draw_object(draw, old_object);
bda_gui_draw_guard_end();
```

V11 只擦除旧十字和旧状态文字，再绘制新状态。不要在每次触摸时逐像素清空整屏；真机
测试表明这种做法会造成明显输入延迟。

### 4. 消息泵

```c
for (;;) {
    int present = bda_gui_event_pump_frame_once(&message, frame);

    drain_touch_events();
    if (need_draw) {
        draw_scene();
    }
    /* input packet + short delay + exit state */
}
```

必须把已注册的 `frame` 传给消息泵。该 wrapper 按顺序调用：

```text
GUI+0x030  poll(message, frame)
GUI+0x050  step(message)
GUI+0x054  dispatch(message)
```

窗口过程只把触摸消息放入固定队列并设置 redraw flag；实际文件 IO 和绘图在主循环中
执行。这样可以避免在固件 dispatch stack 内进行长时间操作。

### 5. 完整退出

V11 真机通过的退出顺序是：

```text
等待 ESC 抬起
GUI+0x088  frame_stop(frame)
GUI+0x04c  frame_release(frame)
继续 event pump，直到 poll 返回 0 或收到 detach
GUI+0x17c  close_frame(frame)
清空本地 frame handle
从 bda_main 返回
```

对应代码骨架：

```c
bda_gui_frame_stop(frame);
bda_gui_frame_release(frame);

while (bda_gui_event_pump_frame_once(&message, frame)) {
    bda_sys_delay(1);
}

bda_gui_close_frame(frame);
frame = 0;
return 0;
```

三类已确认错误：

- 只 `release` 后直接调用 `close`：frame 的 stop 生命周期不完整，真机会在退出时死机。
- `release` 后直接从 `bda_main` 返回而不 `close`：代码已经返回，但测试 frame 仍接管
  GUI，画面冻结且不能回主菜单。
- 把 `GUI+0x17c` 返回寄存器当成功状态：该函数没有稳定返回值。公开 wrapper 因此是
  `void bda_gui_close_frame()`。

`close` 只能执行一次，并且调用后不得再访问 frame、draw context 或向该窗口 dispatch
消息。

## 实时日志

V11 启动时用 `wb` 截断日志，之后每行使用 `ab` 打开、写入并立即关闭。这让中途死机
时已经写出的行仍可在真机文件系统中读取，也验证了当前固件的追加模式。

高频日志不能放在每次空闲 pump 中。早期版本记录每一个 `PUMP=1`，文件反复打开和
写入导致触摸显示明显延迟。V11 只记录生命周期节点和有效触摸事件。

## 验证边界

- 本文验证的是 BBK 9588 当前 C200 固件和 240x320 单点触摸路径。
- 触摸压力、多点、手写中断、校准表修改不在验证范围内。
- `style=0,surface=0` 是 V11 的已验证组合；不能据此推断所有 style/surface 组合安全。
- bitmap、VX、离屏 context、frame 嵌套和多窗口 active-child 切换仍需单独验证。
- 本文证明的是上述完整组合；不能跳过生命周期阶段后仍引用“单个 API 已验证”作为
  安全依据。
