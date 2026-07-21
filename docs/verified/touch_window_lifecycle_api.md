# 触摸窗口与完整生命周期

本文以 `TouchStageV11.bda` 在 BBK 9588 真机上完成的首个 standalone BDA
窗口闭环：应用能创建窗口、显示文字和十字、接收触摸坐标、实时写日志，并在按下
退出键后销毁窗口、返回系统主菜单；后续 V12-V23 继续验证静态文字与动态绘制的
正确提交边界。

这次验证解决的关键问题不是单个绘图函数，而是顶层 frame 的所有权顺序。只有按
本文顺序组合调用，才能把“画面能显示”提升为“应用可以完整启动和退出”。

开发者必须保持的顺序可简写为：
`stop -> release -> event poll 结束/detach -> end draw -> close -> bda_main return`。

## 真机结果

原始真机验证源码：`reverse/examples/touch_input_stage_probe.c`

原始真机验证产物：`build/TouchStageV11.bda`

公共示例源码：`example/input/touch_crosshair/touch_crosshair_demo.c`

公共预编译产物：`example/input/touch_crosshair/TouchCrosshair.bda`

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

下表只表示这些接口按文中对应版本的参数和组合方式通过了真机闭环，不把它们扩张成任意
上下文都安全的通用 API。

| 表项 | 公开 API | 验证覆盖 |
| --- | --- | --- |
| GUI `+0x030/+0x050/+0x054` | `bda_gui_event_pump_frame_once()` | 使用实际 frame handle 轮询、step、dispatch |
| GUI `+0x04c` | `bda_gui_frame_release()` | stop 后标记 frame 退出 |
| GUI `+0x074` | `bda_gui_draw_guard_begin/end()` | V11/V23 动态 draw-context 增量重绘的完整 begin/end 边界 |
| GUI `+0x084` | `bda_gui_register_frame_desc()` | 注册 0x34-byte descriptor 并取得 frame handle |
| GUI `+0x088` | `bda_gui_frame_stop()` | 退出键释放后发起 stop |
| GUI `+0x08c` | `bda_gui_default_proc()` | 非触摸消息交回固件默认过程 |
| GUI `+0x098` | `bda_gui_frame_activate()` | 使用 `mode=0x100` 激活已注册 frame |
| GUI `+0x0e4` | `bda_gui_object_draw_begin()` | V13 使用 frame object 取得配对 draw context |
| GUI `+0x0e8` | `bda_gui_object_draw_end()` | V13 把同一 frame/context 配对收尾 |
| GUI `+0x17c` | `bda_gui_close_frame()` | 事件泵结束后最终释放顶层 frame |
| GUI `+0x2fc` | `bda_gui_draw_object_create()` | `kind=7` 绘图对象 |
| GUI `+0x304` | `bda_gui_current_draw()` | 从 frame 和 attach callback 取得 draw context |
| GUI `+0x30c` | `bda_gui_end_draw()` | C200 静态确认；8013 动态确认 detach 或退出兜底时归还 fixed draw slot |
| GUI `+0x338/+0x33c/+0x4f0` | text mode/color/draw text | V23 仅在初始 object-paint scope 绘制静态标题和退出提示 |
| GUI `+0x358` | `bda_gui_select_draw_object()` | 绘制前选择、结束后恢复旧对象 |
| GUI `+0x368/+0x378` | put pixel/RGB | V23 擦除/绘制十字，并绘制应用内 5x7 动态坐标字 |
| GUI `+0x38c` | `bda_gui_rectangle()` | 绘制触摸区域边框 |
| GUI `+0x5d4` | `bda_gui_input_packet()` | 轮询实体退出键并等待释放 |
| GUI `+0x6c0` | `bda_gui_touch_position()` | 真机 V3 高频读取固件缓存的最新校准逻辑坐标 |
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

需要按住期间更密集地取得位置时，仍由消息 1/2 设置和清除本地 `touch_down`，再在
10 ms 窗口定时消息中调用 `bda_gui_touch_position()`。它是最新坐标 getter，不提供
pressed 状态，也不能替代窗口消息泵。完整说明见 [高速触摸坐标 API](touch_position_api.md)。

原始 V11 在 `0x66` draw context detach 时只清空本地 handle，没有归还 fixed draw
slot；这后来被确认是泄漏。当前公开示例已改为调用 `bda_gui_end_draw()` 后清空本地
handle 并设置退出标志。正常退出也可能由 event poll 返回 0 完成，因此不能把“每次
退出必定收到 0x66”列为已验证保证，退出路径仍必须兜底归还 draw slot。

### 启动重绘会重复进入

真机补充观察表明，V11 启动时 `WAITING MESSAGE 1/2` 会被绘制三次。这不是收到三组
触摸消息，而是三个绘制来源叠加：激活后的主动首帧、首帧后仍未清除的
`g_need_draw`，以及启动消息序列中的 `0x60`/首个 `0xb1`。

窗口绘制函数因此必须可重复进入，不能把“只绘制一次”当作生命周期保证。后续 V12
测试版只合并启动阶段的重复请求：主动首帧后清除 dirty flag；相同 draw context 的
`0x60` 不重复绘制；第一个无触摸状态的 `0xb1` 只作为启动刷新确认。draw context
真正变化、后续 `0xb1` 和触摸坐标变化仍会触发重绘。V12 尚未完成真机闭环，所以这项
合并策略暂不提升为已验证 API 语义。

### V13 对象绘制作用域

V13 已在同一台 BBK 9588 真机完成启动、绘制、触摸和退出闭环。普通 draw context 为
`0x804a8494`，`GUI+0x0e4(frame)` 返回 `0x804a8568`；绘制后调用
`GUI+0x0e8(frame, 0x804a8568)`，日志继续到 `PAINT END`。退出仍按
`stop -> release -> poll end -> close` 返回主菜单。

这验证了 `+0x0e4/+0x0e8` 的参数、配对关系和 void end 语义，因此公开头提供
`bda_gui_object_draw_begin()` / `bda_gui_object_draw_end()`。它也验证了一个重要反例：
V13 的文字仍逐字出现在屏幕上。对象绘制作用域虽然返回不同的 context struct，却继续
使用可见 backend；它不是离屏缓冲，也不能把多次图元操作合并成原子提交。

本次 V13 测试产物 SHA-256：

```text
2052d02bcc11f2db8378190fa7cf93435dcee3a796b2b0e7f4c158f39fb73f7a
```

### V14/V15 离屏复制反例

V14 已在真机确认 `GUI+0x310(visible)` 返回独立临时 context `0x80a89340`，两次
`GUI+0x418` 均返回 `0`，`GUI+0x314(temp)` 也完成并继续运行到正常退出。画面为白色
背景且保留黑色矩形边框。V15 把两个 context 对调后，真机画面变成全白。

这两个结果结合 C200 控制流纠正了 V15 的方向判断：第二个 context 是 destination。
早期曾进一步推断 `GUI+0x310` 创建的 compatible context 不能作为复制目标；后续
V19/V20 在完整 C200/QEMU 路径用可区分像素证明 hidden→hidden 复制有效，因此该
推断撤回。V14/V15 的白色画面只证明当时的绘制内容/顺序没有形成有效可见对照，
不能证明 destination 类型限制。入口参数现解释为：

```text
a0          source_context
a1/a2       source_x/source_y
a3/sp+0x10  width/height
sp+0x14     destination_context
sp+0x18/1c  destination_x/destination_y
sp+0x20     RGB565 color_key_or_zero
```

V14/V15 真机仍确认 source/destination ABI、compatible context 的创建与释放，以及
两种调用顺序对应的白色输出；但不能再用它们断言 visible→temp 必然无效。V19/V20
目前只是模拟器补充证据，不把 hidden destination 或色键能力升级为真机已验证 API。

V16 移除无效的 copy-in，直接使用 temp 的白色初始 surface，并把文字从近白色改成黑色。
真机第二次启动后，首帧 `WAITING MESSAGE` 已显示为黑色，证明黑色 text color 本身有效；
但触摸后的 `X=/Y=` 又显示为白色。首帧与后续帧的代码差异是：后续帧会先用白色重画
旧状态。每次重绘都会新建空白 temp，这个擦除步骤既无必要，也可能覆盖随后绘制的黑色
新状态。第一次启动曾停在 `BEFORE REGISTER`，第二次可正常启动，暂记为非稳定复现。

V17 在 temp 创建成功时跳过旧文字和旧十字的擦除；若 temp 创建失败并退回可见 context，
仍保留原擦除逻辑。实际提交继续只调用一次 `temp -> visible`。V17 尚未完成真机验证；
`+0x310/+0x418/+0x314` 暂不进入稳定头。

### V18 记事本短标签路径对照

对官方 `记事本.bda` 的 11 个 `GUI+0x4f0` 调用做函数级检查后，确认其短标签位于
`GUI+0x0e4(frame) -> drawing -> GUI+0x0e8(frame, draw)` 作用域内。搜索标题调用点
`0x81c01878..0x81c019e8` 和名称/内容标签调用点 `0x81c09b70..0x81c09c48` 的局部
路径都没有 `GUI+0x074(1/0)`。

V13-V17 在 object draw scope 内仍调用了 `GUI+0x074`，且顺序是先 `+0x0e8`、后
`+0x074(0)`；这不是记事本短标签的精确提交顺序。V18 以 V13 为基线，移除
`+0x074` 和 compatible context，只保留：

```text
GUI+0x0e4(frame)
select object -> rectangle/pixel/text -> restore object
GUI+0x0e8(frame, draw)
```

V18 真机结果：首帧文字不再逐字出现；退出键仍能正常关闭并返回菜单。但触摸后的
`X=/Y=` 和十字均未显示。触摸事件本身仍由原有消息和队列接收，缺失的是后续画面的
可见提交。这个结果说明：

- 去掉嵌套的 `+0x074` 后，初始 paint scope 可以一次性显示文字。
- 在 wndproc 返回后才执行的 `+0x0e4 -> drawing -> +0x0e8` 不会自动提交后续画面。
- `+0x0e8` 不能脱离消息 paint 阶段被泛化为任意时刻都有效的 present API。

V18 测试产物 SHA-256：

```text
31e6b1c044242305cfa9048ef0a36ba5276df63a179d46479b2f3dcc74d62b1b
```

V19 保留 V18 的无 `+0x074` object draw scope，并把触摸消息触发的动态绘制移入
wndproc，同一 callback 内完成 `+0x0e4 -> drawing -> +0x0e8`。真机仍只显示首帧；
`message 1/2` 坐标完整写入日志，但 `X=/Y=` 和十字没有显示，退出正常。由此确认
“位于任意 wndproc callback”仍不够，绘制必须进入系统认可的 paint/redraw 消息阶段。

V20 不再直接在触摸 `message 1/2` 中绘制。主循环消费触摸状态后调用
`GUI+0x0e0(frame)`；C200 中该 API 先准备 object，再内部调用
`GUI+0x03c(frame, 0xb1, 0, 0)` 设置 frame redraw pending flag。下一次 event poll 分发
`0xb1` 时，wndproc 才执行无 `+0x074` 的 object draw scope。日志增加：

```text
REDRAW REQUEST=0x........
REDRAW CALLBACK
```

V20 真机在首个触摸日志写盘后立即死机，日志停在：

```text
UP X=130 Y=148 RAW=0x00940082
```

下一条 `REDRAW REQUEST` 没有出现，证明死机发生在
`GUI+0x0e0(g_frame)` 内。C200 反汇编显示 `+0x0e0` 会先调用 object-specific helper
`0x800ccc58(object)`，然后才调用 `GUI+0x03c(object, 0xb1, 0, 0)`。电子画板传入的是
它自己的可刷新 child object；standalone 顶层 frame 不能直接套用这层 wrapper。

V21 删除 `+0x0e0`，直接调用已确认只设置 pending flag 的：

```text
GUI+0x03c(g_frame, 0xb1, 0, 0)
```

V21 真机日志显示 `REDRAW NOTIFY=0x00000000`，证明 `GUI+0x03c` 成功设置了 pending
flag；但之后始终没有 `REDRAW CALLBACK`，触摸坐标和十字仍未显示，退出正常。
因此 `message 0xb1` 在该 entry 中只是 frame 内部 pending bit，不保证当前 standalone
event pump 会把它转换成发送给 custom wndproc 的普通队列消息。

V22 回到 V18 的主循环绘制方式，不再请求 `0xb1`。动态 object draw 完成并执行
`GUI+0x0e8(frame,draw)` 后，仅调用一次 `GUI+0x074(0)`；不调用
`GUI+0x074(1)`。这用于区分 V13 的逐字显示究竟来自 `+0x074(1)`，还是来自尾部
调用本身。首个动态调用会记录：

```text
BEFORE DYNAMIC PRESENT
DYNAMIC PRESENT=0x........
```

V22 真机日志记录了 `DYNAMIC PRESENT=0x00000000`，但坐标和十字仍未显示，退出正常。
因此 `GUI+0x074(0)` 的返回值不能解释为“已提交”，而且不能脱离对应的
`GUI+0x074(1)` 独立充当 present。V11 中动态直接绘制可见，依赖的是完整的
`GUI+0x074(1/0)` 区间。

V23 保留 V18 的无 guard 初始 object paint，使标题与短标签一次显示；触摸后的动态路径
改回 V11 已验证的完整 `GUI+0x074(1/0)` 区间。为避免动态 `GUI+0x4f0` 再次逐字刷新，
V23 用 `GUI+0x368` 逐像素绘制应用自带的 5x7 `X=ddd Y=ddd` 点阵字，并在同一个 guard
中绘制十字。首次触摸应增加：

```text
VECTOR DYNAMIC DRAW
```

V23 已在同一 BBK 9588 真机验证通过：触摸后坐标和十字正常出现，连续更新没有闪烁。
它确认了以下 API 分工：

| 阶段 | API 组合 | 已确认语义 |
| --- | --- | --- |
| 初始静态绘制 | `+0x0e4 -> +0x338/+0x33c/+0x4f0 -> +0x0e8` | object-paint scope 内的短标签一次显示，不需要嵌套 `+0x074` |
| 动态提交 | `+0x074(1) -> +0x358/+0x368 -> +0x074(0)` | 完整 guard 让运行期像素变更可见；只调用 `(0)` 无效 |
| 颜色 | `+0x378(context,r,g,b)` | 先按当前 context 转换颜色，再传给 `+0x368` |
| 十字和坐标 | `+0x368(context,x,y,color)` | 只擦除旧图元并绘制新图元，不清屏，连续触摸无闪烁 |

V23 不把 `+0x0e8` 或 `+0x074(0)` 单独命名为 present，也不使用已在 V20/V21 证明不适用
于 standalone 顶层 frame 的 `+0x0e0(frame)` / `+0x03c(frame,0xb1,0,0)` 重绘路径。

V23 真机测试产物 SHA-256：

```text
9d872884482e8539487cdead9f293d70ba5038572a43a2562c63cc197cbb4aee
```

复现构建：

```powershell
python reverse\bda_compile_c.py reverse\examples\touch_input_stage_probe_v23.c `
  --title TouchV23 --category 9 -o build\TouchStageV23.bda
python reverse\bda_validate.py build\TouchStageV23.bda
```

公共开发者示例 `example/input/touch_crosshair/touch_crosshair_demo.c` 已整理为相同的 V23 两阶段绘制
结构；`reverse/examples/touch_input_stage_probe_v23.c` 保留带实时日志的原始验证入口。

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

`bda_gui_current_draw()` 不是无状态 getter。当前固件只有 5 个普通 fixed draw slot；
每次成功调用都必须由同一 handle 的 `bda_gui_end_draw()` 结束。重复 attach 不能对同一
owner 再次 acquire；detach 未到达时，退出路径必须兜底释放。

### 8013 draw slot 泄漏现场

2026-07-17 的扫雷卡住现场停在第 3935 帧，QEMU 仍持续执行，NAND 无错误。直接读取
C200 的 draw context 池后确认：

| 区域 | 状态 | owner/handle |
| --- | --- | --- |
| 普通槽 0 `0x804a60c0` | 占用 | 娱乐菜单 `0x80963cb8` |
| 普通槽 1..4 | 全部占用 | 扫雷 frame `0x80963e14` |
| `0x804a64e4` | 固件保留 context | 不是第 6 个普通槽 |
| 池外 `0x804a65b8` | 已被写入 | 第 6 次扫描越界产生 |

`GUI+0x304` 的固件循环使用 `slti index,6`，因此 5 个普通槽全满时还会检查保留
context。保留 context 的 `+0x08` 非零后，函数继续按 index 6 计算池外地址，而不是
返回“槽已满”。这会破坏相邻全局数据。SDK 因而把 5 视为硬上限，并要求每次成功的
`bda_gui_current_draw()` 都与一次 `bda_gui_end_draw()` 配对；不能依赖固件处理耗尽。

修复后在同一个 8013 QEMU 进程中连续启动、退出扫雷 6 轮。每轮运行时只有一个普通槽
占用，退出后槽 0..4 的 `+0x08` 全部为 0；最后一轮日志为
`DRAW ACQUIRES=1`、`DRAW RELEASES=1`、`RESULT=PASS`。这动态确认了
`GUI+0x30c` 会归还 `GUI+0x304` 取得的 fixed draw slot。

收到 `BDA_MSG_DRAW_CONTEXT_ATTACH` (`0x60`) 时，应使用 callback 的 `handle` 重新取得
draw context。不要假设注册后取得的 context 永远不变。

V11 的直接 draw-context 路径在 guard 内选择 object，并在结束前恢复旧 object：

```c
void *old_object;

bda_gui_draw_guard_begin();
old_object = bda_gui_select_draw_object(draw, draw_object);
/* put pixel / rectangle / text */
bda_gui_select_draw_object(draw, old_object);
bda_gui_draw_guard_end();
```

这段是 V11 已验证组合，不是所有绘制作用域的强制模板。若通过
`bda_gui_object_draw_begin()` 取得 object draw context，是否还应嵌套 `+0x074`
取决于原机调用链；记事本短标签没有这层嵌套。V18 已确认初始 object paint 去掉这层
guard 后文字一次显示；V22 则确认 `+0x074(0)` 不能单独提交运行期动态绘制。

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
GUI+0x30c  end_draw(draw)，detach 已执行时跳过
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

if (draw) {
    bda_gui_end_draw(draw); /* detach callback 应先把 draw 清零。 */
    draw = 0;
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
- 调用 `bda_gui_current_draw()` 后只清空本地指针、不调用 `bda_gui_end_draw()`：每次
  运行会永久占用一个 fixed slot；池满后固件会越界初始化 context 并破坏全局内存。

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
