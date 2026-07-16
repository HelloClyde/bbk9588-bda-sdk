# 决战坦克.bda 逆向报告

`决战坦克.bda` 是内置分类 `0x04` 游戏。它是 `雷霆战机.bda` 打包音效路径的
最强交叉验证：两个应用都使用 `SYS+0x040..0x068` 调用簇、`0x20` 字节
descriptor 间距，以及 `0x14` 个 chunk 的循环上界。

## 头部和布局

```text
文件大小         114204 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS 范围         0x81c12840..0x81c13f31
```

运行时表全局变量：

```text
RES  0x81c12840
GUI  0x81c12844
SYS  0x81c12848
FS   0x81c1284c
MEM  0x81c12850
```

## 外部文件

相关字符串：

```text
\SysPet.yzj
\maptank\map
.map
\TankData.dat
\TankSound.lib
rb
wb
rbf
GeneralDLTable GUI_Address :%x
GeneralDLTable FS_Address :%x
GeneralDLTable Media_Address :%x
```

应用至少使用三类外部数据：

```text
\maptank\map*.map   地图/关卡数据
\TankData.dat       存档或游戏数据
\TankSound.lib      打包音效包
```

## 内嵌 VX 资源

应用内嵌相同的四个通用小游戏 shell VX 资源：

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

## API 使用概览

原始调用扫描共有 296 个间接调用，包含通用游戏 shell 和打包音效 SYS 调用簇：

```text
FS +0x000  11 次
FS +0x004  13 次
FS +0x008  14 次
FS +0x010  19 次
FS +0x014   5 次
FS +0x018/+0x01c/+0x020/+0x024/+0x028  额外 stdio 类辅助

GUI +0x030/+0x050/+0x054  事件循环
GUI +0x084/+0x088/+0x08c/+0x17c  frame 生命周期
GUI +0x2fc/+0x35c/+0x40c/+0x414/+0x418  渲染辅助族
GUI +0x3f8/+0x400  framebuffer/区域 blit 类调用对
GUI +0x4f0  文字绘制类

SYS +0x040/+0x044/+0x050/+0x054/+0x058/+0x05c/+0x060/+0x064/+0x068/+0x08c
SYS +0x090  额外系统/媒体类调用
```

`GUI+0x3f8/+0x400` 的关键上下文与 `雷霆战机.bda` 同构。`bda_table_call_scan.py
--context` 显示全屏 buffer 路径为：

```text
0x81c04600  GUI+0x3f8(0, 0, 0xf0, 0x140, buffer)
0x81c0461c  GUI+0x6e0()
0x81c04648  GUI+0x400(0, 0, 0xf0, 0x140, buffer)
0x81c04660  MEM+0x00c(buffer)
```

另一组 `GUI+0x414` render helper 后同样接 `GUI+0x0e8(object, draw)`，分支路径
还会先走 `GUI+0x074(1)`。因此坦克样本也只能证明原机小游戏 shell 的完整
surface/context 状态机中使用了这些 blit helper，不能证明 bare BDA 可直接用
`GUI+0x400` 实现可玩 tile 游戏。`TileBlit` 真机反馈已经确认，脱离该 lifecycle
会逐块 flip 并死机。

具体 object render 序列与雷霆战机同构：

```text
0x81c00d34  GUI+0x414(...)
0x81c00d60  GUI+0x0e8(object=0x81c12854, draw=s0)
0x81c00d74  GUI+0x074(0)

0x81c02b1c  GUI+0x414(...)
0x81c02b44  GUI+0x0e8(object=0x81c12854, draw=s0)
0x81c02b58  GUI+0x074(0)
```

pre-render context/state 路径同样与雷霆战机一致：

```text
message 0x60:
0x81c007ac  save callback a0 object to 0x81c12854
0x81c007b0  GUI+0x304(object)
0x81c007c4  save returned context to 0x81c1285c

0x81c00a30  GUI+0x35c(context=0x81c1285c, value=s0)
0x81c00a50  GUI+0x40c(context=0x81c1285c, ...)

0x81c01e00  GUI+0x2fc(0x10)
0x81c01e28  GUI+0x334(context=0x81c1285c, color=value)
0x81c01e38  save value to 0x81c129e4

0x81c01ecc  GUI+0x2fc(0x10)
0x81c01ef4  GUI+0x33c(context=0x81c1285c, color=value)
0x81c01f04  save value to 0x81c129e8

message 0x66:
0x81c00804  GUI+0x30c(context=0x81c1285c)
0x81c00820  GUI+0x088(object=0x81c12854)
0x81c0083c  GUI+0x04c(object=0x81c12854)
```

## 打包音效流程

`0x81c04548` 附近是关键音效包调用点。周围循环：

```text
向 descriptor 写入两个 word
调用 SYS 表中的音效相关入口
descriptor 指针增加 0x20
chunk index < 0x14 时继续循环
把 descriptor base 保存到 0x81c12a10/0x81c12a20 附近
```

这与 `雷霆战机.bda` 中 `0x81c11188` 附近的包处理代码可逐指令对比。

`0x81c04b98` 附近会用同样的 `0x20` 间距遍历 descriptor 并释放/关闭它们。
`SYS+0x064` 与 `SYS+0x068` 多次成对出现，和 `雷霆战机.bda` 一致。

`SYS+0x044` 会把一个字节保存到 `0x81c1288c`。后续 `SYS+0x040` 接收该字节或
下列形式计算出的 id：

```text
sound_id = 0x75 - (index * 13)
```

这与 `雷霆战机.bda` 的选择/控制模式一致。

C200 表项验证显示：`SYS+0x050` 和 `SYS+0x054` 目前是返回 `1` 的 stub，
因此不应把它们单独命名为最终 loader/free API。`SYS+0x058/+0x05c/+0x060/
+0x064/+0x068` 才是有实际状态和播放/停止行为的入口。

## 当前解释

`决战坦克.bda` 证明 `SYS+0x040..0x068` 不是 `雷霆战机` 的一次性 helper，而是
内置原生游戏可复用的系统级打包音效接口。

对 SDK 的实际含义：

```text
1. GAMEBOY raw audio 和游戏打包音效必须分开记录
2. 打包音效 descriptor 暂按 0x20 字节记录用于实验
3. 游戏 .lib 文件是运行时包，不是主机链接库
4. 命名单个 SYS 操作前，应同时使用 Tank + Thunder + C200 表项证据
5. `GUI+0x3f8/+0x400` 不是独立游戏绘图 API，必须继续逆向小游戏 shell 的
   surface/context 前置 lifecycle
```
