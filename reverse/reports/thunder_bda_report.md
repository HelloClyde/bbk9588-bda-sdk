# 雷霆战机.bda 逆向报告

`雷霆战机.bda` 是内置分类 `0x04` 游戏。它使用与益智游戏相同的小游戏 shell，
但额外引用 `\FlySound.lib`，提供打包音效路径的第一份强证据。

## 头部和布局

```text
文件大小         131452 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS 范围         0x81c16ba0..0x81c178f1
```

运行时表全局变量：

```text
RES  0x81c16ba0
GUI  0x81c16ba4
SYS  0x81c16ba8
FS   0x81c16bac
MEM  0x81c16bb0
```

## 配套源码的版本边界

`fly-src-api/Fly原码` 提供了 Rockchip GUI 层函数名和游戏业务语义，但不是该 BDA
的精确构建快照。BDA 时间为 2008-01-15；`fly.c` 最新 revision 是 2008-06，
`game.c` 文件时间是 2010-02。后续源码使用 `C:\APPDATA\fly\FlySave.bin`，而 BDA
字符串仍是 `a:\应用\数据\游戏\Flydata.dat`、`FlySound.lib` 和 `GamFlyInfo.Sav`；
源码中的 `MixerSetChannel` 已注释，BDA 则有完整 SYS package sound 调用簇。

因此源码只用于恢复 `WindowCreate`、`WindowInvalidateWindow`、`DrawBmpIdEx`、
`FSFileOpen` 等 high-level 名称和用途。table offset、MIPS o32 参数和返回值仍由
BDA 调用点与 C200 实现确认。开发者映射和调用示例见
`sdk/doc/thunder_api_notes.md`，完整 291-call/75-entry 表见
`sdk/doc/thunder_api_inventory.md`。

## 外部文件

相关字符串：

```text
\Flydata.dat
\FlySound.lib
\GamFlyInfo.Sav
\SysPet.yzj
gFly_soundState = %d
rb
wb
wb+
rbf
```

`\Flydata.dat` 和 `\GamFlyInfo.Sav` 是应用数据/存档路径。`\FlySound.lib`
是额外音效包。虽然后缀是 `.lib`，但它不是主机链接库；应用会把它作为运行时
数据打开和解析。

## 内嵌 VX 资源

应用内嵌四个通用小游戏 VX 资源：

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

## 绘制路径

`GUI+0x3f8` 和 `GUI+0x400` 是雷霆战机最明确的 framebuffer/region blit
路径。调用点会把 buffer 指针压到 `sp+0x10`，然后传入 `x,y,height,width`：

```text
GUI+0x3f8 @ 0x81c11240:
  a0=0, a1=0, a2=0xf0, a3=0x140, sp+0x10=buffer

GUI+0x400 @ 0x81c11288:
  a0=0, a1=0, a2=0xf0, a3=0x140, sp+0x10=buffer
```

C200 里的对应实现也确认了参数顺序是 `x,y,height,width,buffer`。`+0x400`
在 blit 前会走一次全局 clip/prepare；`+0x3f8` 更直接，最终都落到显示后端。

后续真机 `TileBlit` 反馈推翻了早期“直接用小块 tile + `GUI+0x400`”的 SDK
建议：即使只在循环外统一 present，缺少原机游戏 shell 的 surface/context 时也会
逐块 flip，并在全部 tile 渲染后死机。因此这组调用目前只能证明原机游戏的 ABI 和
参数顺序，不能直接作为自定义游戏绘图接口。
旧扫雷真机反馈里的“每个方块逐个 flip”属于错误 lifecycle 信号，不是正常动画效果。

`bda_table_call_scan.py --context` 对 `雷霆战机.bda` 的调用点显示，原机不是单独
调用 `GUI+0x400`：

```text
0x81c11240  GUI+0x3f8(0, 0, 0xf0, 0x140, buffer)
0x81c1125c  GUI+0x6e0()
0x81c11288  GUI+0x400(0, 0, 0xf0, 0x140, buffer)
0x81c112a0  MEM+0x00c(buffer)
```

另一组 `GUI+0x414` render helper 调用后会接 `GUI+0x0e8(object, draw)`；
分支路径还会先 `GUI+0x074(1)` 再进入 render helper。也就是说，雷霆战机的
framebuffer blit 只是完整小游戏 shell 中的一段，前置的 object/draw/present
状态仍未被 SDK 复刻出来。

具体 object render 序列也与坦克样本同构：

```text
0x81c0d8b4  GUI+0x414(...)
0x81c0d8e0  GUI+0x0e8(object=0x81c16c8c, draw=s0)
0x81c0d8f4  GUI+0x074(0)

0x81c0f69c  GUI+0x414(...)
0x81c0f6c4  GUI+0x0e8(object=0x81c16c8c, draw=s0)
0x81c0f6d8  GUI+0x074(0)
```

pre-render context/state 路径里，`GUI+0x35c` 会先把 value 写到 context slot，
随后立刻 `GUI+0x40c` region draw；这不是创建 context：

```text
message 0x60:
0x81c0d32c  save callback a0 object to 0x81c16c8c
0x81c0d330  GUI+0x304(object)
0x81c0d344  save returned context to 0x81c16c94

0x81c0d5b0  GUI+0x35c(context=0x81c16c94, value=s0)
0x81c0d5d0  GUI+0x40c(context=0x81c16c94, ...)

0x81c0e980  GUI+0x2fc(0x10)
0x81c0e9a8  GUI+0x334(context=0x81c16c94, color=value)
0x81c0e9b8  save value to 0x81c17584

0x81c0ea4c  GUI+0x2fc(0x10)
0x81c0ea74  GUI+0x33c(context=0x81c16c94, color=value)
0x81c0ea84  save value to 0x81c17588

message 0x66:
0x81c0d384  GUI+0x30c(context=0x81c16c94)
0x81c0d3a0  GUI+0x088(object=0x81c16c8c)
0x81c0d3bc  GUI+0x04c(object=0x81c16c8c)
```

开发者当前不要把 `bda_gui_blit_like()` / `bda_gui_blit_alt_like()` 当作可玩游戏
框架。恢复扫雷前，需要先复刻出原机小游戏 shell 创建 game surface/context 的
前置 lifecycle，再用真机验证。

另一个容易踩的点是 `GUI+0x084` 注册 frame 时会同步触发 create 类 message。
wndproc 在这个阶段不应立刻做 `begin_draw`、`blit` 或大块绘制；原机调用点通常
在注册成功后再走后续 attach/activate/update 路径。SDK 示例应把 create 分支
当作轻量初始化，真正绘制放在注册返回、激活 frame 之后，或放到后续 redraw/input。

no-template toolchain 还必须把 `.bss` 作为零填充区域写进 BDA。C200 的 BDA loader
没有给我们当前生成物单独清零 `.bss` 的证据；如果 `.bss` 只留在 ELF 里而没有进入
最终 BDA，应用的 global 会落在文件末尾之后，容易覆盖 runtime heap。表现之一就是
`GUI+0x084` 内部分配 `0x114` byte window object 失败，应用弹出 `frame failed`。

## API 使用概览

原始调用扫描共有 291 个间接调用，包含通用游戏 shell 和额外 SYS 音效调用：

```text
RES  14 calls /  2 unique entries
GUI 139 calls / 45 unique entries
SYS  23 calls / 10 unique entries
FS   72 calls / 16 unique entries
MEM  43 calls /  2 unique entries
```

```text
FS +0x000/+0x004/+0x008/+0x00c/+0x010/+0x014  数据/存档/包 I/O
GUI +0x074/+0x0e0/+0x2fc/+0x35c/+0x3f8/+0x400/+0x40c/+0x414/+0x418
MEM +0x008/+0x00c
RES +0x090/+0x094

SYS +0x040  3 次
SYS +0x044  1 次
SYS +0x050  1 次
SYS +0x054  1 次
SYS +0x058  2 次
SYS +0x05c  4 次
SYS +0x060  2 次
SYS +0x064  4 次
SYS +0x068  4 次
SYS +0x08c  1 次
```

## 打包音效流程

`0x81c11188` 附近代码会遍历最多 `0x14` 个声音/包 chunk，填充间距为
`0x20` 字节的 descriptor，然后调用 SYS 表中的相关入口。

后续函数使用紧密的操作簇：

```text
SYS+0x058  状态/启动/检查类操作
SYS+0x05c  descriptor 操作，调用前常传入四个接近 0 的参数
SYS+0x060  返回状态；非 0 时调用者保存状态
SYS+0x064  常与 SYS+0x068 成对
SYS+0x068  常跟在 SYS+0x064 后，接近停止/提交/释放类操作
```

`SYS+0x044` 会把一个字节保存到 `0x81c16bc4`，后续 `SYS+0x040` 接收这个字节
或计算得到的小音效 id。这更像音效选择或通道/状态控制。

C200 交叉验证带来一个重要修正：运行时表里的 `SYS+0x050` 和 `SYS+0x054`
当前都是立即返回 `1` 的 stub，不能把它们单独命名为“加载器”。真正有明显行为
的是 `SYS+0x058/+0x05c/+0x060/+0x064/+0x068`。报告中的 `SYS+0x050` 调用点
仍有记录价值，但 SDK 文档应把它视为不公开 no-op stub，而不是兼容、加载或
释放 API。

## 当前解释

`雷霆战机.bda` 是共享游戏渲染 shell 与游戏专用音效包 API 之间的关键样本：

```text
1. 显示 shell 仍使用相同的内嵌 VX 和 GUI 渲染调用簇
2. 打包音效主要走 SYS+0x058..0x068，而不是 GAMEBOY 的 raw PCM 路径
3. 游戏里的 .lib 文件是运行时数据包
4. 自定义游戏可以先忽略打包音效路径，使用 raw audio；若要复刻原机游戏音效，
   应继续研究这组 SYS 调用
5. `GUI+0x3f8/+0x400` 需要原机小游戏 shell 的 surface/context，不能脱离该
   lifecycle 直接作为 SDK 游戏绘图 API
```

后续价值：与 `决战坦克.bda` 对比；后者使用 `TankSound.lib` 并确认同一套音效包框架。
