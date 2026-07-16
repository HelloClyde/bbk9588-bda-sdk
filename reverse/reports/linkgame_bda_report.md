# 连连看.bda 逆向报告

目标：`应用/程序/连连看.bda`

证据：

- `reverse/reports/linkgame_layout.json`
- `reverse/reports/linkgame_calls.txt`
- `reverse/reports/linkgame_fs_context.txt`
- `reverse/reports/linkgame_gui414_context.txt`
- `reverse/reports/linkgame_media.txt`
- `reverse/reports/linkgame_strings_vx.txt`

## 头部和布局

```text
菜单标题         连连看
分类             0x04
文件大小         82732 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS/global 范围  0x81c0ad50..0x81c0ba91
checksum          inventory 中为 ok
```

运行时表全局变量：

```text
RES 0x81c0ad50
GUI 0x81c0ad54
SYS 0x81c0ad58
FS  0x81c0ad5c
MEM 0x81c0ad60
```

## 内嵌资源和字符串

未引用外部 `\shell\*.dlx` 资源。应用内嵌了与 `Eros方块.bda` 相同的四个 VX
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
\LLKData.dat
```

`LLKData.dat` 是该游戏专用存档或高分文件。`SysPet.yzj` 与 `Eros方块.bda`
共用，确认二者依赖同一个小游戏框架组件。

## API 使用概览

已分类间接调用：

```text
GUI   128
FS     41
MEM    25
RES    12
total 213
```

调用表几乎与 `Eros方块.bda` 相同；小差异主要是 `MEM+0x008/+0x00c` 次数和
应用专用数据。

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

## 文件和存档行为

FS 调用集合与 `Eros方块.bda` 完全匹配：

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

上下文显示同一模式：

```text
用 "rb" 打开共享/系统数据路径
缺失时准备目录
需要时删除/重建存档文件
复制/写入固定 0x44 字节记录
```

记录复制循环和存档 helper 与 Eros 结构相同，只是全局偏移和 `LLKData.dat`
文件名不同。

## GUI 和游戏渲染

应用使用相同的标准事件循环：

```text
GUI +0x030  poll 类
GUI +0x050  step 类
GUI +0x054  dispatch 类
GUI +0x17c  close/release 类
```

除全局地址不同外，`GUI+0x414` 调用上下文与 Eros 逐指令匹配。这是强证据：
`+0x414` 属于共享游戏/渲染 helper，而不是 Eros 专用游戏逻辑。
C200 已确认该入口读取 `stack+0x1c` 指向的 descriptor，并使用
`descriptor+0x04/+0x08/+0x14/+0x18`；`stack+0x14/+0x18` 是裁剪后的
width/height gate。该 helper 可能分配临时 buffer，并按行复制裁剪后的区域。

应用还使用：

```text
GUI +0x418  区域/渲染结束类
GUI +0x368  put-pixel 类，次数较少
GUI +0x4f0  文字绘制类
GUI +0x2b8  消息框类
```

## 交叉验证

- 与 `Eros方块.bda`：确认共享小游戏 BDA 框架和存档 helper。
- 与 `电子画板.bda`：确认 `GUI+0x368/+0x40c/+0x414/+0x418` 与渲染相关，
  而不是文字/窗口建立逻辑。
- 与 `game_framework_notes.md`：这两个应用应作为当前已知最小的小游戏框架样本。

## 未确认点

1. `FS+0x068` 在两个游戏中各出现一次；C200 已确认它读取内部 file object/descriptor，
   不是公共存档 API，也不公开 SDK wrapper。
2. `GUI+0x414` 的 stack slot 已有 C200 级别解释；高层 source/destination
   语义仍需结合 Eros/连连看以外的原机调用点继续命名。
3. 需要识别 `0x44` 字节存档/高分记录的准确结构。
