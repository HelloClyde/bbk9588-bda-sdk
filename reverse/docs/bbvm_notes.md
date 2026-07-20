# BB 虚拟机 API 笔记

本文来自 `应用/程序/BB虚拟机.bda`。BB VM 虽然目标是运行 BB bytecode，但它自身
仍是原生 BDA 程序，因此它的系统表封装和调用模式可以为原生 SDK 提供线索。

## Runtime Table 注册

VM 启动时会把原生表保存到全局变量：

```text
0x81c43c60  RES / Dict table
0x81c43c64  GUI table
0x81c43c68  SYS / Media table
0x81c43c6c  FS table
0x81c43c70  MEM / CRTL table
```

随后它会用这些调试字符串调用 `RES+0x094`：

```text
GeneralDLTable Address :%x
GeneralDLTable GUI_Address :%x
GeneralDLTable FS_Address :%x
GeneralDLTable Media_Address :%x
GeneralDLTable CRTL_Address :%x
GeneralDLTable Dict_Address :%x
```

这确认至少有一个原机 runtime 把 `0x81c0000c` 当作 media/system table，而不只是
杂项表。

## 计时线索

可读字符串包括：

```text
msdly_S:%d,%d\n
msdly_E:%d,%d\n
0100831:修改“gettick读出来不是ms”
```

这说明 BB 层程序有 `gettick`/毫秒延时语义，但作者注释也表明 `gettick` 在修复前
读出来不是毫秒。原生代码仍需要探针确认具体单位。当前原生线索仍是：

```text
SYS+0x080  delay/sleep-like
SYS+0x09c  timer/rate preset-like
```

## GUI/事件/显示线索

扫描到的 VM 调用点里没有直接调用 SYS 表；它大量使用 GUI 表，包括这些对模拟器
方向有价值的 offset：

```text
GUI+0x030  event/status poll-like；在 VM 循环中反复调用
GUI+0x050  事件/update 辅助候选
GUI+0x054  事件/update 辅助候选，常在 GUI+0x050 后调用
GUI+0x074  高频绘制/window flush/update-like
GUI+0x1ac  window timer start；frame,timer_id,period_ms，经内部 message 0x162 注册
GUI+0x1b0  window timer stop；frame,timer_id，经内部 message 0x163 注销
GUI+0x334  set background/fill color-like
GUI+0x374  RGB/color query 或 pixel/color conversion-like
GUI+0x3f8  framebuffer/region blit-like
GUI+0x400  alternate framebuffer/region blit-like
GUI+0x4d0  text width/height metric-like
GUI+0x4d4  text width/height metric-like
```

`GUI+0x1ac/+0x1b0` 是窗口 timer 注册/注销，不是 lock/unlock 或 object refresh。
C200 内部 `0x162/0x163` 最终维护 timer 表；到期后 Frame callback 收到 `0x144`。

## 触摸坐标数据流

BBVM 没有直接调用 `GUI+0x6c0`。其触摸坐标来自系统窗口消息，完整路径如下：

```text
GUI+0x030(message, 0)
  -> GUI+0x050(message)
  -> GUI+0x054(message)
  -> root wndproc 0x81c006bc
  -> event bridge 0x81c43d68..0x81c43d70
  -> bridge fetch 0x81c037b0
  -> BB input helper 0x81c0a098
  -> interpreter numeric input opcode 0x2e
```

根 wndproc `0x81c006bc` 首先把 `a1=message` 写入 `0x81c43d68`。当
`message == 1` 或 `message == 2` 时，它还会写入：

```text
0x81c43d6c = low16(wparam)
0x81c43d70 = lparam
```

随后 `0x81c037b0` 运行 `GUI+0x030/+0x050/+0x054`，把上述三个 word 复制给调用者，
并清零 bridge message。`0x81c0a098` 对 `message == 1` 的处理为：

```c
return 0x80000000u | lparam;
```

解释器 jump table 中 opcode `0x2e` 跳到 `0x81c0955c`，该分支调用
`0x81c0a098`，再把返回值保存到 BBVM 的 numeric result/global `0x81c43e00`。
从实现形状看，它是 numeric key/event getter；具体 BB 源语言助记符需要结合
`StdLib.lib` 索引才能最终命名。相邻 opcode `0x2d` 还会把键盘缓冲中的一个 byte
写入 BB string，更像对应的 string input 形式。

触摸返回值可按下列方式解包：

```c
u32 payload = event_value & 0x7fffffffu;
u16 x = (u16)(payload & 0xffffu);
u16 y = (u16)((payload >> 16) & 0x7fffu);
```

其中 bit31 是 BBVM 自己添加的 touch marker，不是坐标位；原始 `lparam` 仍是
`x=low16`、`y=high16`。这条路径进一步证明原版应用使用固件已经校准并打包好的
window message 坐标，而不是由应用调用 `GUI+0x6c0` 读取 raw panel sample。

## BBVM 的窗口初始化

BBVM 会初始化自己的窗口。BDA 入口 `0x81c00020` 先保存 runtime tables，然后调用
`0x81c0323c`。该函数先使用 `GUI+0x6a8(mode=1)` 打开系统 file selector，随后构造
0x34-byte frame descriptor：

```text
style    = 0x08000000
wndproc  = 0x81c006bc
height   = 240
width    = 320
surface  = GUI+0x2fc(15)
```

descriptor 通过 `GUI+0x084` 注册。BBVM 一共有 3 个可识别的 `GUI+0x084` 调用点：

```text
0x81c02958  modal/辅助 frame，wndproc 0x81c02650
0x81c03350  主 root frame，wndproc 0x81c006bc
0x81c0358c  主 frame 的另一启动分支
```

注册后它持续运行 `GUI+0x030/+0x050/+0x054`，因此触摸消息才能进入 root wndproc。
这里传 `handle=0` 是成立的，因为 BBVM 已把自己的 root frame 建立到系统的
global/default 活动槽；这和“注册 custom frame 后仍错误轮询 0”的失败 probe 不同。

## 是否所有 BDA 都要初始化窗口

不是所有 BDA 都必须直接调用 `GUI+0x084`，但需要分场景理解：

- 需要绘图并接收触摸/按键的完整交互应用，必须取得有效 GUI/window 对象并维持事件循环；
- 应用可以直接调用 `GUI+0x084`，也可以通过随 BDA 静态链接的 `WindowCreate/ProcMap`
  框架间接创建，或调用 MsgBox/file selector 等由固件自行创建 modal frame 的 API；
- 只做文件处理、计算、日志后立即返回的 headless BDA，不需要创建自己的窗口；
- 已有宿主窗口的插件/子模块可以复用宿主 context，但不能假设普通独立 BDA 启动时
  自动拥有一个可绘制、可接收输入的 root frame。

对原版 NAND 中 54 个 BDA 的静态表调用扫描，52 个存在可识别的直接
`GUI+0x084` 调用，53 个调用 `GUI+0x030`。未识别到直接 `GUI+0x084` 的
`雷霆战机.bda` 和 `GAMEBOY.BDA` 仍是交互应用，说明“没有直接表调用”不等于
“没有窗口”；它们可能通过私有静态框架或当前扫描器不能还原的间接路径完成初始化。

## 文件系统线索

BBVM 使用已知的 stdio-like FS 调用组，也使用额外 offset：

```text
FS+0x018  小 wrapper，具体角色未知
FS+0x01c  小 wrapper，具体角色未知
FS+0x020  小 wrapper，具体角色未知
FS+0x028  额外 file/path 操作，具体角色未知
FS+0x068  内部 file-object block read helper；已见 buffer + offset/size + descriptor 参数
```

已知 `open/read/write/seek/tell/close/find` 调用组已经足够支撑 GBA ROM 和存档
文件；这些额外 offset 后续再单独探测。`FS+0x068` 依赖 firmware 内部 file
object/descriptor，不能替代普通 `fread` wrapper。

## 对 GBA/模拟器项目的意义

BBVM 增强了以下探针的优先级：

```text
WindowTimerProbe  验证 GUI+0x1ac/+0x1b0、0x144 callback 和 timer 生命周期
InputPollProbe 探测 GUI+0x030/+0x050/+0x054 事件/status 行为
TickProbe      比较 SYS+0x080/+0x09c 单位和可见延时
```

它没有提供新的直接音频证据；音频仍应从 `GAMEBOY.BDA`、`飞天影音.bda` 或
`飞天音乐.bda` 继续映射。
