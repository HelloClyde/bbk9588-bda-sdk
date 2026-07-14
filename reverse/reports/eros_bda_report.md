# Eros方块.bda 逆向报告

目标：`应用/程序/Eros方块.bda`

证据：

- `reverse/reports/eros_layout.json`
- `reverse/reports/eros_calls.txt`
- `reverse/reports/eros_fs_context.txt`
- `reverse/reports/eros_gui414_context.txt`
- `reverse/reports/eros_gui418_context.txt`
- `reverse/reports/eros_media.txt`
- `reverse/reports/eros_strings_vx.txt`

## 头部和布局

```text
菜单标题         Eros方块
分类             0x04
文件大小         83996 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS/global 范围  0x81c0b240..0x81c0b561
checksum          inventory 中为 ok
```

运行时表全局变量：

```text
RES 0x81c0b240
GUI 0x81c0b244
SYS 0x81c0b248
FS  0x81c0b24c
MEM 0x81c0b250
```

## 内嵌资源和字符串

未引用外部 `\shell\*.dlx` 资源。BDA 内嵌了其他小游戏 BDA 中常见的四个 VX
资源：

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

相关字符串：

```text
rb
wb
rbf
a:\
\SysPet.yzj
A:\
\ErosData.dat
eros
Game Over
```

`SysPet.yzj` 路径与 `连连看.bda` 共用，说明这是小游戏系统/设置或宠物/皮肤数据。
`ErosData.dat` 是该应用自己的存档或高分数据文件。

## API 使用概览

已分类间接调用：

```text
GUI   128
FS     41
MEM    21
RES    12
total 209
```

高频偏移：

```text
GUI +0x0e0  13
GUI +0x074  10
GUI +0x414   8
GUI +0x2fc   7
GUI +0x418   6
GUI +0x338   6
GUI +0x358   6
FS  +0x000/+0x004/+0x010
RES +0x094   9
```

这是共享原生小游戏框架的紧凑代表样本。

## 文件和存档行为

应用通过接近 stdio 的 FS 调用处理资源和存档文件：

```text
FS +0x000  fopen 类
FS +0x004  fclose 类
FS +0x008  fread 类
FS +0x00c  fwrite 类
FS +0x010  fseek 类
FS +0x014  ftell 类
FS +0x024  remove 类
FS +0x02c  目录存在检查/chdir 类
FS +0x030  mkdir 类
FS +0x03c  findfirst 类
FS +0x044  findclose 类
FS +0x068  内部 file-object block read helper，不公开 SDK wrapper
```

存档初始化路径上下文：

```text
用 "rb" 打开 a:\... 路径
如果缺失，则通过 FS+0x02c / FS+0x030 准备目录
通过 FS+0x024 删除/重建，并用 "wb" 打开
把 0x44 字节记录复制到内存，再写回文件
```

固定的 `0x44` 字节记录大小多次出现，很可能是游戏存档或分数记录大小。

## GUI 和游戏渲染

应用使用标准事件循环：

```text
GUI +0x030  poll 类
GUI +0x050  step 类
GUI +0x054  dispatch 类
GUI +0x17c  close/release 类
```

`GUI+0x414` 被调用 8 次。调用形态是多参数区域渲染辅助：

```text
a0 = context
a1 = x
a2 = y
a3 = width_or_x2_like
stack+0x10/+0x14/+0x18/+0x1c/+0x20/+0x24 = extra rect/clip/descriptor fields
stack+0x1c = descriptor
```

结合 C200，`GUI+0x414` 会读取 `stack+0x1c` 指向的 descriptor，并使用
`descriptor+0x04/+0x08/+0x14/+0x18`；调用者 `stack+0x14/+0x18`
作为裁剪后 width/height gate。它可能申请临时 buffer，按行复制裁剪后的区域。

该调用后面常跟 `GUI+0x0e8` 或 `GUI+0x074`，说明它可能在 present/pump 前准备
或复制渲染区域。

`GUI+0x418` 被调用 6 次，并带有更大的栈参数块。部分调用点传入 `0x140` 和
`0xf0`，对应 320x240 屏幕尺寸。这与 `电子画板.bda` 和相册中看到的区域/渲染
函数族一致。

应用还使用：

```text
GUI +0x368  put-pixel 类，此处次数较少
GUI +0x4f0  文字绘制类，用于标签/Game Over 文本
GUI +0x2b8  消息框类
```

## 交叉验证

- 与 `连连看.bda`：布局、全局变量、FS 调用、GUI 渲染调用、内嵌 VX 资源和
  `\SysPet.yzj` 使用方式几乎相同。
- 与 `电子画板.bda`：确认 `GUI+0x414/+0x418` 属于更广的区域/渲染函数族；
  `GUI+0x368` 仍应视为 put-pixel 类调用。
- 与 FS 笔记：确认小游戏使用与工具/阅读器相同的 stdio/目录/存档文件表。

## 未确认点

1. `FS+0x018/+0x01c/+0x020/+0x028` 尚未命名；它们出现在游戏存档
   helper 区域，可能是 FAT 支持函数。
2. `GUI+0x414/+0x418` 的 stack slot 已有 C200 级别解释；高层 source/destination
   语义仍需结合更多原机调用点和硬件探针。
3. 需要继续对比更多游戏（`黑白棋`、`九宫格`、`雷霆战机`），区分框架代码和
   游戏专用代码。
