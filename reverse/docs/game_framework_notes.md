# 原机游戏 BDA 框架笔记

本文总结原机原生游戏的共性：

```text
Eros方块.bda
连连看.bda
黑白子.bda
九宫格.bda
雷霆战机.bda
决战坦克.bda
三国霸业.bda
```

多数游戏共享一套框架。启动代码会把 runtime API table 缓存到五个相邻 global 变量中，
但每个 BDA 的全局地址不同。可用以下工具定位：

```powershell
python reverse\bda_table_globals.py "应用\程序\Eros方块.bda"
python reverse\bda_table_call_scan.py "应用\程序\Eros方块.bda"
```

`bda_table_call_scan.py` 现在会自动检测这些 global table pointer。

窗口与事件框架可用专用扫描器恢复：

```powershell
python reverse\bda_game_framework_scan.py `
  "应用\程序\Eros方块.bda" `
  "应用\程序\连连看.bda" `
  "应用\程序\黑白子.bda" `
  "fly-src-api\雷霆战机.bda"
```

已有逐 BDA 报告：

```text
reverse/reports/eros_bda_report.md
reverse/reports/linkgame_bda_report.md
reverse/reports/blackwhite_bda_report.md
reverse/reports/jiugongge_bda_report.md
reverse/reports/thunder_bda_report.md
reverse/reports/tank_bda_report.md
reverse/reports/sango_bda_report.md
```

`Eros方块` 和 `连连看` 是最小的共享框架确认样本。`黑白子`、`九宫格` 证明
同一 shell 也出现在更多益智游戏里。`雷霆战机`、`决战坦克` 证明打包音效
路径。`三国霸业` 是重要反例：它有 `.lib` 包，但没有 SYS 音效调用簇。

## 通用表缓存顺序

游戏启动时常见缓存顺序：

```text
RES
GUI
SYS
FS
MEM
```

以 `Eros方块.bda` 为例：

```text
RES  0x81c0b240
GUI  0x81c0b244
SYS  0x81c0b248
FS   0x81c0b24c
MEM  0x81c0b250
```

## WindowCreate 与 ProcMap

雷霆源码中的 `WindowCreate` 不是固件 GUI table 中的单一函数。它属于静态链接进 BDA
的游戏窗口库，负责组合 descriptor、child object、过程映射和生命周期。源码调用形态为：

```c
WindowCreate(parent, style, id, x, y, width, height,
             arg8, bitmap_id, arg10, arg11, proc_map, user_data);
```

`BEGIN_CHILDMESSAGE_MAP/ON_MESSAGE` 同样是静态库宏。`ProcMap` 表示窗口类型、消息号和
handler 的映射，不是固件导出函数。现有样本中没有发现可安全复用的独立 `ProcMap`
数据 ABI，因此新程序应直接实现 `bda_wndproc_t` 回调并按 `message` 分派。这样与消息表
行为等价，也避免依赖不同游戏编译版本的私有结构布局。

顶层窗口所需的可移植子集已经从原 BDA 恢复：

```text
bda_frame_desc_like_t
  -> bda_gui_register_frame_desc_like()       GUI+0x084
  -> bda_gui_frame_activate_like()
  -> bda_gui_event_pump_frame_once_like(frame)
       GUI+0x030 poll
       GUI+0x050 derive/step
       GUI+0x054 dispatch to bda_wndproc_t
```

新注册的 custom frame 必须把自己的 handle 传给 poll；`handle=0` 只轮询
global/default slot。只注册 frame 并返回同样不能接收实体键；所有原版样本都会继续运行
事件泵。输入原始消息族为
`BDA_MSG_INPUT_BEGIN_LIKE` (`0x10`) 和 `BDA_MSG_INPUT_END_LIKE` (`0x13`)；
`GUI+0x050` 可派生 `BDA_MSG_INPUT_DERIVED_LIKE` (`0x11`) 与
`BDA_MSG_INPUT_END_DERIVED_LIKE` (`0x14`)。雷霆主循环已确认方向键采用 Linux input
keycode：Up/Left/Right/Down 分别为 `0x67/0x69/0x6a/0x6c`，Enter 为 `0x1c`，
Esc 为 `0x01`。这些不是固件 GPIO code，也不是模拟器前端注入的 `4..10`。

交叉恢复结果：

| BDA | root wndproc | event bridge | frame app init | bridge fetch |
|---|---:|---:|---:|---:|
| Eros方块 | `0x81c006bc` | `0x81c0b348..0x81c0b350` | `0x81c02f6c` | `0x81c03238` |
| 连连看 | `0x81c006bc` | `0x81c0ae88..0x81c0ae90` | `0x81c02f6c` | `0x81c03238` |
| 黑白子 | `0x81c006bc` | `0x81c1ba38..0x81c1ba40` | `0x81c02f6c` | `0x81c03238` |
| 雷霆战机 | `0x81c0d23c` | `0x81c17598..0x81c175a0` | `0x81c0faec` | `0x81c0fdb8` |

前三个样本的代码地址完全相同而 global 地址随链接布局变化；雷霆是同一框架的更大链接
版本。这个差异说明 SDK 应复刻调用协议，不能把任一 BDA 的绝对函数地址当系统 API。

## 共享 GUI 调用

这些游戏中常见的高频 GUI offset：

```text
GUI +0x074  高频；可能是 pump/present/update/event 类
GUI +0x0e0  高频；C200 只读取 object/handle 并发送内部 0xb1 message
GUI +0x2fc  查询 low-level draw object/surface table；不是 framebuffer allocator
GUI +0x35c  draw context resource/image slot setter，写 context+0x20
GUI +0x40c  region draw/copy 类
GUI +0x414  low-level render helper，读取 descriptor 和多个 stack 参数
GUI +0x418  双 context/双矩形 render helper，绘制路径中常和 +0x414 配对
GUI +0x3f8  5 参数 region/frame blit 类
GUI +0x3fc  capture region alloc，返回 buffer 需 bda_free()
GUI +0x400  同形态的备用 blit 类
```

`Eros方块.bda` 和 `连连看.bda` 为 `GUI+0x414` 提供了具体证据。两者都以相同
指令结构调用 8 次：

```text
a0 = surface/object
a1 = x/source-x-like
a2 = y/source-y-like
a3 = width/height/index-like
stack+0x10..0x24 = extra rectangle/clip/descriptor fields
stack+0x1c = descriptor
```

结合 C200，`GUI+0x414` 会读取 `stack+0x1c` 指向的 descriptor，并使用
`descriptor+0x04/+0x08/+0x14/+0x18`；调用者 `stack+0x14/+0x18`
是裁剪后的 width/height gate。它可能申请临时 buffer，按行复制裁剪后的区域，
再调用 draw backend。

它们也会用更大的栈参数块调用 `GUI+0x418`。部分调用点传入 `0x140` 和 `0xf0`，
对应 320x240 屏幕。C200 确认 `GUI+0x414` 会读取 descriptor 并可能申请临时
buffer，`GUI+0x418` 会处理两个 context 的 source/destination 矩形。因此
`GUI+0x414/+0x418` 应与画板、相册证据一起看作 region/render 函数族。

最强 framebuffer 线索是 `GUI+0x3f8/+0x400`。`雷霆战机.bda` 和 `决战坦克.bda`
以屏幕尺寸常量调用：

```text
a0 = x
a1 = y
a2 = 0xf0  (240)
a3 = 0x140 (320)
stack+0x10 = buffer pointer
```

这提示调用形态类似：

```c
gui_blit_like(x, y, height, width, buffer);
```

pixel format 仍需 hardware probe 确认。结合 icon 格式和其他代码，RGB565 是最强候选。

`GUI+0x2fc(15)` 是原机 frame/window descriptor 里常见的 surface/object 候选值，
但不是 no-template BDA 的 framebuffer allocator，也不是最小绘图 demo 入口。
只有已经复刻出原机 frame/control lifecycle 时才应显式传入；普通 no-template
实验应先保持 `surface=0`，避免把孤立的 object table 返回值交给 `register_frame`。

`bda_sdk.h` 暴露的临时 wrapper：

```c
bda_gui_draw_guard_begin_like();                          /* GUI +0x074(1) */
bda_gui_draw_guard_end_like();                            /* GUI +0x074(0) */
bda_gui_draw_object_create_like(kind);                    /* GUI +0x2fc */
bda_gui_object_bind_like(context, value);                 /* GUI +0x35c: set context+0x20 */
bda_gui_region_draw_like(context, x, y, width, height);    /* GUI +0x40c */
bda_gui_blit_like(x, y, height, width, buffer);           /* GUI +0x3f8 */
bda_gui_capture_region_alloc_like(x, y, width, height);   /* GUI +0x3fc */
bda_gui_blit_alt_like(x, y, height, width, buffer);       /* GUI +0x400 */
```

真机反馈给扫雷类 tile 游戏增加了两个硬边界。第一，不要在每个方块后调用
`bda_gui_draw_guard_end_like()` 或 `GUI+0x074(0)`；它是 present/update 边界，放在
tile 循环里会表现成每个方块逐个 flip，完整绘制后还可能白屏或死机。第二，
`TileBlit` 已确认即使只在循环外统一 present，硬编码时间入口/no-template 路径仍会逐块
flip 并死机，说明 `GUI+0x074/+0x400` 不能脱离原机游戏 surface/context 生命周期。
原机雷霆战机/决战坦克的形态更接近：

```text
game shell 创建/绑定 surface/context
  GUI+0x414 render helper
  GUI+0x0e8 object draw end
  GUI+0x074(0) draw/present guard end

temporary full-screen buffer path:
  GUI+0x3f8 blit full/dirty region buffer
  GUI+0x6e0 game/display state pump
  GUI+0x400 alternate blit/restore
  MEM+0x00c free temporary buffer
```

如果需要全屏刷新，原机路径也会先批量 blit 全部 dirty region，再统一 present/update；
不要把 present 当成“每次画完一个方块就刷新”的函数。但 SDK 目前还没复刻出创建
有效 game surface/context 的前置 lifecycle，所以不能把 `bda_gui_blit_alt_like()`
直接暴露成可玩游戏绘图框架。
`reverse/examples/tile_blit_probe.c` 现在只保留为 ABI/build probe：它用一次 draw guard
批量 blit 8x6 个 16x16 RGB565 tile 后统一 present，真机已确认仍逐块 flip 并死机。

V19-V21 已确认一条不依赖裸 `GUI+0x3f8/+0x400` 的 standalone 双缓冲路径：在完成
frame 注册和 message `0x60 -> GUI+0x304(object)` 后，用 `GUI+0x310` 创建 back 与
sprite 两块 compatible context；`GUI+0x418(sprite -> back)` 完成隐藏 surface 合成，
最后只对 `GUI+0x418(back -> visible)` 使用一次 `GUI+0x074(1/0)`。连续 116616 帧
无旧位置残影，两块 context 均由 `GUI+0x314` 释放。V20 又结合原机调用点确认
`GUI+0x418` 末参数 0 禁用透明键，RGB565 `0xf81f` 跳过洋红 source pixel；透明精灵
连续 4448 帧正常。V21 再增加 clean background surface：先把旧精灵区域从 clean
恢复到 back，再合成新精灵，只在一个 draw guard 内把新旧位置的最小外接 dirty rect
提交到 visible；第一次移动只提交 `33x32`，连续 20862 帧无残影并释放三块 surface。
alpha blending 仍待恢复，V19-V21 都需要真机复测。
这条链路与完整扫雷闭环已经按模拟器稳定等级进入公开 include；开发者应使用
`bda_gui_compatible_context_create/free()`、`bda_gui_draw_vx()` 和
`bda_gui_context_copy()`，完整图解见 `verified/game_rendering_api.md`。

两款游戏的全屏 buffer 调用点已经用 `bda_table_call_scan.py --context` 交叉验证：

```text
雷霆战机  0x81c11240 GUI+0x3f8 -> 0x81c1125c GUI+0x6e0 -> 0x81c11288 GUI+0x400 -> MEM+0x00c
决战坦克  0x81c04600 GUI+0x3f8 -> 0x81c0461c GUI+0x6e0 -> 0x81c04648 GUI+0x400 -> MEM+0x00c
```

两款游戏的 object render 调用点也同构：

```text
雷霆战机  0x81c0d8b4 GUI+0x414 -> 0x81c0d8e0 GUI+0x0e8 -> 0x81c0d8f4 GUI+0x074(0)
雷霆战机  0x81c0f69c GUI+0x414 -> 0x81c0f6c4 GUI+0x0e8 -> 0x81c0f6d8 GUI+0x074(0)
决战坦克  0x81c00d34 GUI+0x414 -> 0x81c00d60 GUI+0x0e8 -> 0x81c00d74 GUI+0x074(0)
决战坦克  0x81c02b1c GUI+0x414 -> 0x81c02b44 GUI+0x0e8 -> 0x81c02b58 GUI+0x074(0)
```

两款游戏的 pre-render context/state 序列也同构，能解释为什么裸 BDA 只调用
`GUI+0x400` 不成立：

```text
雷霆战机  message 0x60: save object=0x81c16c8c -> GUI+0x304(object) -> save context=0x81c16c94
决战坦克  message 0x60: save object=0x81c12854 -> GUI+0x304(object) -> save context=0x81c1285c
雷霆战机  GUI+0x35c(context=0x81c16c94, value=s0) -> GUI+0x40c(context=0x81c16c94, ...)
决战坦克  GUI+0x35c(context=0x81c1285c, value=s0) -> GUI+0x40c(context=0x81c1285c, ...)
雷霆战机  GUI+0x2fc(0x10) -> GUI+0x334/0x33c(context=0x81c16c94, color=value)
决战坦克  GUI+0x2fc(0x10) -> GUI+0x334/0x33c(context=0x81c1285c, color=value)
雷霆战机/决战坦克  message 0x66: GUI+0x30c(context) -> GUI+0x088(object) -> GUI+0x04c(object)
```

这里 `GUI+0x2fc(0x10)` 不是创建 game surface；C200 已确认 `GUI+0x334/+0x33c`
只是 fill/text color setter，写的是 context 字段并返回旧值。游戏把 table 查询结果当
color-like value 使用，进一步证明 `GUI+0x2fc` 不能被统一解释为“创建绘图对象”。
真正的 context 来源是 wndproc message `0x60` 里传入的 object 和 `GUI+0x304(object)`；
这条路径依赖已注册 frame/control callback，不能在 `bda_main()` 中手工拼出来。

这说明裸 `GUI+0x3f8/+0x400` 当前缺失的是原机 shell 状态机，而不是单个 blit
wrapper；但普通 BDA 已可用 `GUI+0x310/+0x418/+0x314` 走模拟器已验证的 compatible
surface 双缓冲、色键精灵和局部 dirty present 链。下一步逆向重点是 alpha/其他
blend mode，以及原机
`GUI+0x414`、`GUI+0x6e0` 和 raw full-screen blit 的状态关系。

## Game Resource Package

`Eros方块.bda`、`连连看.bda` 这类小游戏不引用外部 DLX 包。它们把同样四个 VX
image 直接嵌在 BDA resource area：

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

这些游戏还会引用共享 `\SysPet.yzj` 文件和各自存档文件：

```text
\ErosData.dat
\LLKData.dat
\BlackData.dat
\SdData.dat
\GamSdSave.Sav
\Flydata.dat
\GamFlyInfo.Sav
\TankData.dat
\maptank\map*.map
\sango.lib
```

它们包含固定 `0x44` byte record 的复制/读写循环，可能是存档或排行榜 record。

`blackwhite_bda_report.md` 还发现一个游戏专属嵌入 VX 资源，offset `0x194e4`，
尺寸 240x95。`thunder_bda_report.md`、`tank_bda_report.md` 和
`sango_bda_report.md` 也确认了同样四个通用 shell VX 资源。

部分游戏使用外部包文件：

```text
雷霆战机.bda   A:\...\FlySound.lib
决战坦克.bda   A:\...\TankSound.lib
三国霸业.bda   a:\...\sango.lib
```

package load 模式通常是读取小 header、checksum、分配内存，然后保存 chunk descriptor 列表。
`雷霆战机.bda` 有代码迭代最多 `0x14` 个 chunk，并在填充 descriptor 后调用
SYS table entry。C200 交叉验证显示 `SYS+0x050` 本身是立即返回 `1` 的 stub，
因此不能把 `+0x050` 单独命名为 loader。

这些 `.lib` 文件不是主机上的标准库。它们更像游戏数据或声音/资源包，由游戏
BDA 框架消费。

## 音效线索

`雷霆战机.bda` 和 `决战坦克.bda` 使用额外 SYS 表 offset：

```text
SYS +0x040
SYS +0x044
SYS +0x050
SYS +0x054
SYS +0x058
SYS +0x05c
SYS +0x060
SYS +0x064
SYS +0x068
SYS +0x08c
```

`雷霆战机.bda` `0x81c11188` 和 `决战坦克.bda` `0x81c04548` 附近会构造包
chunk descriptor 并进入 SYS 音效调用簇。后续路径调用
`SYS+0x40/+0x44/+0x58/+0x5c/+0x60/+0x64/+0x68` 做状态、播放、释放类操作。

这和 `GAMEBOY.BDA` 的 raw PCM-like `SYS+0x74/+0x78` 流式路径不同。对游戏来说，
系统可能提供了 high-level 打包音效 helper。`bda_sdk.h` 目前以
`bda_sys_package_sound_*_like()` 形式暴露，但 descriptor 布局仍需 hardware probe；
`op40(sound_id)` 只写全局 sound id 并置 pending flag，`op44()` 只触发内部 helper。
`+0x050/+0x054` 在 C200 中都是立即返回 `1` 的 stub，SDK 不公开这两个 offset，
也不应把它们当作兼容、加载或释放 API。

`thunder_bda_report.md` 细节：

```text
\FlySound.lib
\TankSound.lib
gFly_soundState = %d
descriptor stride 0x20
loop bound 0x14 chunks
SYS+0x044 会保存一个 byte，后续由 SYS+0x040 复用
SYS+0x040 接收该 byte，或接收计算出来的小 sound id
SYS+0x064 和 SYS+0x068 反复成对出现
```

`tank_bda_report.md` 独立确认：

```text
descriptor stride 0x20
loop bound 0x14 chunks
SYS+0x044 会把一个 byte 保存到 0x81c1288c
SYS+0x040 接收该 byte，或接收 0x75 - (index * 13)
```

不要把这套逻辑推广到所有 `.lib` 游戏包。`sango_bda_report.md` 引用
`\sango.lib`，但没有 `SYS+0x040..0x068` 调用；它通过 FS/MEM 代码自己解析包数据。

## 对 GBA/模拟器项目的意义

这些游戏比 `GAMEBOY.BDA` 更适合研究显示输出。它们展示了一条较紧凑的路径：
通过 GUI 表在已经创建好的 game shell surface/context 中处理 320x240 buffer 或区域。
但真机 `TileBlit` 已经证明，裸 no-template BDA 不能只靠 `GUI+0x3f8/+0x400`
复刻这条路径；缺少 shell lifecycle 时仍会逐块 flip 并死机。结合 `GAMEBOY.BDA`
的 raw 音频流路径，模拟器类 SDK 还缺的主要是：

```text
1. 复原 game shell surface/context 创建、绑定和释放 lifecycle
2. 在原机 lifecycle 中验证 GUI+0x3f8/+0x400 的 RGB565/stride/dirty region 约定
3. 固定一条稳定 key/touch input polling 或 window message dispatch 路径
4. 决定使用 raw PCM 路径还是游戏打包音效路径
```

`+0x3f8/+0x400` 目前不应再按“哪个负责 present、哪个负责清屏”的二选一理解；
雷霆战机和决战坦克显示它们中间还夹着 `GUI+0x6e0` game/display state pump，
并依赖前置 object/draw/present 状态。
