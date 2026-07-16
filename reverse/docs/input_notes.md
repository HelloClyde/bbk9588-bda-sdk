# 触摸和按键输入笔记

本文结论来自原机原生 BDA 的 window procedure，以及 `C200.bin` 中的系统全屏诊断/
window procedure。这里的 message name 仍是 provisional；没有硬件 probe 确认前，都保持 `_LIKE`
后缀。

## Callback ABI

原机代码强烈暗示 GUI window procedure/callback 形态为：

```c
int wndproc(void *hwnd, u32 message, u32 wparam, u32 lparam);
```

对应 MIPS 参数寄存器：

```text
a0 = window/control handle
a1 = message id
a2 = wparam 或打包后的 command/touch 数据
a3 = lparam 或额外事件数据
```

原机代码处理打包值时，经常拆成低/高 16 位：

```text
low  = value & 0xffff
high = value >> 16
```

`bda_sdk.h` 已提供：

```c
BDA_LOWORD(x)
BDA_HIWORD(x)
BDA_MAKEWORD(lo, hi)
typedef int (*bda_wndproc_t)(bda_handle_t hwnd, u32 message, u32 wparam, u32 lparam);
```

## 已观察到的 Message 常量

这些常量出现在原机 window procedure 或 `C200.bin` 诊断 window procedure 里，目前已经以 `_LIKE`
名称暴露在 `bda_sdk.h`：

```text
BDA_MSG_CREATE             0x0010  create/setup 类 message，很多 call site 都出现
BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE 0x0060  BBVM/Thunder/Tank 中用于取得 draw context 的 callback message
BDA_MSG_DRAW_CONTEXT_DETACH_LIKE 0x0066  BBVM/Thunder/Tank 中用于清理 draw/context 的 callback message
BDA_MSG_TOUCH_A_LIKE       0x00b0  系统诊断 window procedure 里的 touch/pen-like 分支
BDA_MSG_REDRAW_INPUT_LIKE  0x00b1  元素周期表里像 redraw/input-refresh；系统诊断里另一个 touch/pen-like 分支
BDA_MSG_COMMAND_LIKE       0x083e  command-like 分支
BDA_MSG_FOCUS_LIKE         0x0841  focus-like 分支
BDA_MSG_INPUT_0842_LIKE    0x0842  系统诊断 window procedure 里的 input/touch-like 分支
BDA_MSG_KEYDOWN_LIKE       0x0844  keydown-like 分支
```

有原机应用会比较 `message == 0x083e` 或 `message == 0x0844`，然后把
`wparam` 拆成低/高 16 位。`C200.bin` 在 `0x8000f718` 附近也有系统全屏
诊断/window proc，会分支处理 `0x00b0`、`0x00b1`、`0x0842`、`0x0844`。

重要修正：不要在通用应用代码里把 `0x00b1` 当成“退出”或“触摸抬起”。展示
应用实验显示，`元素周期表.bda` 更像把它当作 redraw/input-refresh 触发；
启动阶段收到该 message 就退出，会导致第一张图还没绘制应用就关闭。

`BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE` / `BDA_MSG_DRAW_CONTEXT_DETACH_LIKE` 来自
BBVM 文本显示 probe、雷霆战机和决战坦克的交叉证据。`0x60` 分支通常用
callback 的 `hwnd/object` 调 `bda_gui_current_draw_like()` 取得 draw/context；
`0x66` 分支清理该 context。它们是 frame/control lifecycle 信号，不是通用
refresh、close 或 input message。

## 触摸/手写笔线索

`0x80059f68` 的触摸按下/抬起查询已经由独立 BDA 动态验证。稳定返回语义、
固件版本绑定、示例、NAND 导出结果和截图见 `verified/touch_press_api.md`。
该结论只覆盖 pen GPIO 电平，不自动证明坐标或 window message ABI。

系统二进制包含诊断字符串：

```text
The MSG_LBUTTONDOWN x=%d y=%d
The MSG_MOUSEMOVE x=%d y=%d
The MSG_LBUTTONUP x=%d y=%d
pen up!
MSG_LBUTTON
```

这证明 firmware 中存在触摸/手写笔按下、移动、抬起 message。`元素周期表.bda`
进一步静态确认：主 wndproc 在 `message == 1` 时把 `lparam` 的 signed low16 作为 x、
signed high16 作为 y，并直接用于按钮区域命中测试。原版 BDA 的应用层坐标 ABI 因此
已经有明确静态证据；诊断路径还会使用 `0x80477d54` 附近的全局 touch/input 状态结构。

`BB虚拟机.bda` 提供了第二条独立证据。它不调用 `GUI+0x6c0`，而是在 root wndproc
`0x81c006bc` 中保存 `message=1` 的完整 `lparam`，再由 BB input helper 返回
`0x80000000 | lparam`。bit31 是 BBVM 的 touch marker；清除后仍按 low16=x、
high16=y 解包。完整地址和 opcode 路径见 `bbvm_notes.md`。

`GUI+0x6c0 -> 0x8001a3a0` 是另一层接口。静态逆向确认它接收两个 `u16 *` 输出参数，
从 `0x807f7112/7114` 读取 raw 值，使用 `0x807f7120..7154` 的校准参数计算坐标，
把结果裁剪到 `0..239` 和 `0..319`，并缓存到 `0x807f7116/7118`。对原版 NAND 中
54 个 BDA 的表调用扫描没有发现应用直接调用 `GUI+0x6c0`；现有证据更符合“固件内部
校准转换器”，而不是原版应用普遍使用的 polling getter。

先前自建 BDA 调用该接口只得到 `(239,319)`，但这次动态测试不能判为接口失败：

- `0x807f7110..715f` 的 dump 来自另一轮空闲状态，没有在按住触摸时同步采集 raw 值；
- 自建 frame 虽保存了 `g_frame`，循环却调用固定传 `handle=0` 的旧
  `event_pump_once`，实际轮询的是 global/default slot，不是刚注册的 frame；
- 自建 frame 的画面叠在原菜单之上，也没有证明它取得了与原版根窗口相同的活动对象和
  事件路由；原 BDA 还包含静态 child-window、ProcMap 和 event bridge 对象链；
- 模拟器测试允许触摸注入后 guest raw globals 保持 `0xffff`，因此必须用同一运行中的
  原版 BDA 作为 positive control，才能区分固件接口问题和模拟器输入模型限制。

对应 provisional wrapper 为 `bda_gui_touch_position_like(u16 *x, u16 *y)`。当前结论是
“静态 ABI 已定位，动态验证无结论”，不是“API 只会返回 `(239,319)`”。在完成同一次
按压中的 raw、转换输出和 wndproc `lparam` 三路对照前，它仍不列入 `verified/`。

SDK 已补充 `bda_gui_event_pump_frame_once_like(message, frame)`，用于新注册的 custom
frame。旧 `bda_gui_event_pump_once_like(message)` 保留为 global/default-slot 兼容入口，
不能再用于证明指定 `g_frame` 是否收到触摸消息。

应用代码中还见到这些 command/control-like ID：

```text
0x047e
0x047f
0x0501
```

SDK 暂时暴露为：

```c
BDA_CMD_LBUTTON_DOWN_LIKE
BDA_CMD_LBUTTON_UP_LIKE
BDA_CMD_PEN_AREA_LIKE
```

这些值更像 control command 或区域事件 ID，不应直接等同于 window proc 里的 `message`。

## 按键线索

`GUI+0x5d4` 的六字节实体键轮询已经由独立 BDA 动态验证，稳定映射、用法、去抖和
验证证据统一记录在 `verified/input_polling_api.md`。本节其余内容讨论的是窗口消息、
雷霆私有事件桥和 `SYS+0x088` raw query，不能用它们否定已经闭环的轮询接口。

系统二进制包含按键诊断字符串：

```text
MSG_KEYDOWN
SCANCODE_ESCAPE
The key is ENTER
The key is BACK
The key is SHIFT
The key is HOME
The key is UP
The key is LEFT
The key is RIGHT
The key is END
The key is DOWN
The key is INS
The key is DEL
```

这证明物理按键和 scancode 处理都在 firmware 中存在。`GUI+0x5d4` 已完成独立轮询
验证。custom window procedure 的触摸 `message/lparam` 已由真机 V11 闭环；实体键
window message ABI 仍未闭环，不能与 packet 轮询混为一谈。

### 雷霆 BDA 的实际输入分层

对 `雷霆战机.bda` 和模拟器运行时的联合探针确认了以下链路：

```text
firmware input
  -> BDA 根窗口过程 0x81c0d23c
  -> 0x81c17598..0x81c175a0 三字事件桥接区
  -> BDA 外层 event fetch 0x81c0fdb8
  -> 静态 child-window framework
  -> ProcMap 中的 WM_KEY handler
  -> wParam 高/低 16 位 KE_* 状态
```

根窗口过程对 `BDA_MSG_TOUCH_COORDINATE(1)` / `BDA_MSG_TOUCH_RELEASE(2)` 保存参数，
对 `message=0x60` 保存 frame 和 current draw；
`0x81c0fdb8` 读取事件后会把 `0x81c17598` 清零。外层循环还会处理原始
`0x0844` 事件，并在 child framework 前调用 `GUI+0x1b0` 和 `GUI+0x5c4(1,1)`。

这不等于 `GUI+0x084` 注册的任意新 frame 都会收到 `message=0x0844`。扫雷探针中，
新 frame 在创建阶段收到 7 次 callback，最后一条为 `0x60`；模拟器方向键会触发
固件刷新，但 callback 计数、`wparam/lparam` 和游戏 cursor 均不变。后续与 Eros、连连看、
黑白子的事件循环交叉后，确认该探针在注册 frame 后直接返回，遗漏了原版持续运行的
`GUI+0x030/+0x050/+0x054` 事件泵；因此这个结果不能证明 frame 不支持实体键。
`BDA_MSG_KEYDOWN_LIKE` 也不能描述成通用且已验证的窗口按键 ABI。

V11 真机已确认触摸消息的 `lparam` 低/高 16 位分别为 x/y，并确认必须把实际 frame
handle 传给事件泵。完整窗口顺序见 `verified/touch_window_lifecycle_api.md`。

`SYS+0x088()` 是一个更底层的 raw keycode query。C200 table entry 目标为
`0x8001b464`，不读取调用者参数，直接读取 `0xb0010100`、`0xb0010200`、
`0xb0010300` 等硬件输入寄存器，并返回 raw code。当前可见返回值包括
`0`、`4`、`5`、`6`、`7`、`9`、`10`；SDK 暴露为
`bda_sys_keycode_raw_like()`。这些 code 还没有和具体实体键完成硬件对照，文档中
暂不命名为 ENTER/BACK/方向键。已有完整 child-window framework 的应用应优先处理
其 `WM_KEY`；只有完成硬件验证的 window ABI 才能使用 `BDA_MSG_KEYDOWN_LIKE`。

多 BDA 交叉逆向确认，之前“注册 frame 后收不到键”的原因包括缺少持续事件泵，以及
custom frame 错误轮询 global/default slot，并不是 `GUI+0x084` 本身不支持输入。
SDK 现提供 `bda_gui_event_pump_frame_once_like(message, frame)`，按原版顺序调用
`GUI+0x030/+0x050/+0x054`。原始输入消息常量为
`BDA_MSG_INPUT_BEGIN_LIKE`、`BDA_MSG_INPUT_DERIVED_LIKE`、
`BDA_MSG_INPUT_END_LIKE`、`BDA_MSG_INPUT_END_DERIVED_LIKE`。旧的
`BDA_MSG_KEYDOWN_LIKE` (`0x844`) 仍保留为已观察到的外层游戏输入/状态消息，不能再把它
当作所有窗口的唯一实体键回调。

`WindowCreate/ProcMap` 是 BDA 静态窗口库，不是固件里的两个导出 SDK 函数。新游戏可用
`bda_frame_desc_like_t + bda_wndproc_t + bda_gui_event_pump_frame_once_like()` 实现顶层
窗口和消息 switch；厂商 child-window `ProcMap` 的私有结构 ABI 仍未声明为可移植接口。

雷霆主循环进一步确认了固件转换后的 `WM_KEY` 值。`message=0x10` 时，`wParam` 使用
Linux input keycode，而不是模拟器前端注入的 `4..10`：

```text
0x01  Esc
0x1c  Enter
0x67  Up
0x69  Left
0x6a  Right
0x6c  Down
```

雷霆的选择菜单对 `0x67/0x69` 走递减分支，对 `0x6a/0x6c` 走递增分支，与上述方向
一致。自建 frame 的 `message=0x10` 路径仍未闭环，但这不影响已经独立验证的
`GUI+0x5d4` packet 轮询；两者不能混为同一接口。

雷霆在外层 `0x844` 路径调用 `GUI+0x1b0(root_handle,state_or_page)`。C200 反汇编确认
`GUI+0x1b0` 会构造 `{root_handle,state_or_page}` packet 并同步发送内部消息 `0x163`；
它不是普通 object update。对赋值点继续回溯后确认第二个参数在初始化时固定写为 `1`，
并非之前推测的 child-window 指针。紧随其后的 `GUI+0x5c4(1,1)` 在当前 C200 版本中是
空 stub，因此也不能把这条 `0x844` 分支解释为实体键转换链。

雷霆 `0x81c001a0` 是原应用主函数，不是可单独复用并立即返回的 common-init。它完成
资源和状态初始化后进入自己的事件循环；新 BDA 若在自建 frame 后调用它，原循环会先
消费全部 GUI 事件。模板内部的事件桥是 `0x81c0fdb8`：它依次执行
`GUI+0x030/+0x050/+0x054`，再从 `0x81c17598..0x81c175a0` 复制三字应用事件并清空
message word。其输出布局为 `{message,wParam,lParam}`，其中 `message=0x10` 的
`wParam` 即上面的 Linux input keycode。

该桥不能脱离雷霆完整根对象链直接作为公开 SDK API。模拟器 framebuffer 和 CP0
联合验证结果如下：

- 自建 frame 使用自己的 wndproc 时可以短暂绘制棋盘，但 `0x81c0fdb8` 没有产生可消费的
  实体键事件。
- 把雷霆私有根 wndproc `0x81c0d23c` 直接挂到自建 frame，会异步进入 C200 TLB-load
  异常，CP0 EPC 为 `0x800068c4`；补发 `GUI+0x1ac(root,1,100)` 不能修复。
- 从系统 app-init 再调用 `0x81c001a0`，或手工重入雷霆外层循环，会在完整对象状态建立前
  进入另一条 TLB-load 异常，已见 CP0 EPC `0x800ce93c`。

因此当前缺口仍是原静态 `WindowCreate + ProcMap` 建立的对象链，而不是一个尚未调用的
runtime table offset。棋盘可见、header 被菜单识别和按键闭环是三项独立验证，不能互相替代。

`SYS+0x084 -> 0x8001b6a8` 是相邻的 raw input/internal helper。C200 entry
不读取调用者参数，只顺序调用 `0x8001b324()` 和 `0x8001b0e4()`；相邻后续函数
会读取固件内置输入配置文件，但 table entry 本身没有覆盖那段逻辑。SDK 不公开
这个 wrapper；不要把它命名为 input reset、keyboard init 或 key polling API。

## 与事件相关的 GUI 表 offset

输入较重的原机应用经常使用这些 GUI offset：

```text
+0x030
+0x03c
+0x040
+0x050
+0x054
+0x074
+0x084
+0x088
+0x08c
+0x0e0
+0x0e4
+0x0e8
+0x134
+0x17c
+0x1a4
+0x1a8
+0x1ac
+0x1b0
+0x1b4
+0x2fc
+0x308
+0x30c
+0x338
+0x33c
+0x35c
+0x368
+0x378
+0x40c
+0x418
+0x4f0
```

当前已知或较可信的职责：

```text
+0x040  send/set message or property
+0x084  register frame/window descriptor
+0x088  frame/window stop-like
+0x08c  default window procedure-like
+0x1a4  create control/window
+0x1a8  destroy control/window
+0x2b8  message box
+0x338  set text/background mode-like
+0x33c  set text/foreground color-like
+0x378  RGB/color helper candidate
```

其余 offset 需要围绕 window callback 的 hardware probe 继续确认，不能仅凭调用频率给稳定
SDK name。

`GUI+0x08c` 的 C200 table entry 已确认读取 `handle,message,wparam,lparam` 四参数。
`0xb0`、`0xb1`、`0xb2`、`0xb3` 都在 default proc 中有特殊分支；custom
window procedure 未消费的 message 应交回 `bda_gui_default_proc_like()`，而不是
直接返回随机值或把该 table entry 当作主动 send API。

## SDK 示例

`example/input/key_polling/key_msgbox_demo.c` 是已验证的六键轮询示例，完整说明见
`verified/input_polling_api.md`。

`reverse/examples/input_state_demo.c` 是其他 input 相关 wrapper 的最小查询示例：
它调用 `bda_gui_input_packet_like()`、`bda_gui_event_fetch_like()` 和
`bda_gui_state_query_like()`，然后用 message box 显示 return value 和 event
code/value。该示例只做状态查询，不创建 control，也不把 event code 解释成稳定
按键枚举；其中 event/state 和触摸映射仍需要 hardware probe 继续确认。
