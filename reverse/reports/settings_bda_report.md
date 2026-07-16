# 系统设置.bda 逆向报告

目标：`应用/程序/系统设置.bda`

证据：

- `reverse/reports/settings_layout.json`
- `reverse/reports/settings_calls.txt`
- `reverse/reports/settings_fs_context.txt`
- `reverse/reports/settings_fs048_context.txt`
- `reverse/reports/settings_gui3f8_context.txt`
- `reverse/reports/settings_media.txt`
- `reverse/reports/settings_dlx.txt`

## 头部和布局

```text
菜单标题         系统设置
分类             0x09
文件大小         556140 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS/global 范围  0x81c7e690..0x81c7fa61
checksum          inventory 中为 ok
```

运行时表全局变量：

```text
RES 0x81c7e690
GUI 0x81c7e694
SYS 0x81c7e698
FS  0x81c7e69c
MEM 0x81c7e6a0
```

## 外部资源

该 BDA 引用五个 shell 资源：

```text
\shell\SysSet.dlx
\shell\SysSetnew.dlx
\shell\sysset_skin.dlx
\shell\sysset_add_blue.dlx
\shell\sysset_add_black.dlx
```

这些文件都存在于 `应用/数据/shell`。`dlx_inspect.py` 显示这些文件中的每个
资源条目都是 type 1 VX RGB565 图片数据。

重要包：

```text
SysSet.dlx / SysSetnew.dlx
  29 张 VX 图片
  包含 240x320 全屏背景、197x153 面板、139x59 按钮

sysset_skin.dlx
  2 张 VX 图片
  都是 240x320

sysset_add_blue.dlx / sysset_add_black.dlx
  3 张 VX 图片
  240x30 和 240x25 列表/状态条
```

这强化了当前 DLX 模型：量产 UI 皮肤是由 VX 图片组成的普通 DLX 容器。

## API 使用概览

已分类间接调用：

```text
GUI      777
FS        98
MEM      123
RES       28
SYS        4
UNKNOWN    5
total   1001
```

高频偏移：

```text
GUI +0x3f8  58
GUI +0x400  44
GUI +0x0f4  58
GUI +0x0e4  49
GUI +0x0e8  44
GUI +0x4f0  30
FS  +0x048  17
FS  +0x000/+0x004/+0x008/+0x00c/+0x010/+0x014
FS  +0x03c/+0x040/+0x044
MEM +0x008/+0x00c
RES +0x090/+0x094
SYS +0x080/+0x09c
```

系统设置主要是 GUI、存储和配置应用。它不能提供强音视频 ABI 证据，但它是当前
研究存储状态和带皮肤设置页面的最佳样本之一。

## 磁盘和存储信息

`FS+0x048` 被调用 17 次，调用形态稳定：

```text
a0 = 0
a1 = 调用者持有的 info struct
return = 状态类返回值
```

调用后应用立即把三个 word 相乘：

```text
word(info+0x04) * word(info+0x08) * word(info+0x0c)
```

示例：

```text
0x81c00a6c: FS+0x048(0, sp+0x30)
  使用 sp+0x34, sp+0x38, sp+0x3c

0x81c02fa0: FS+0x048(0, sp+0x230)
  使用 sp+0x234, sp+0x238, sp+0x23c
  与 0x200000 比较

0x81c03254: FS+0x048(0, sp+0x28)
  使用 sp+0x2c, sp+0x30, sp+0x34
```

这把 `FS+0x048` 固定为磁盘/存储信息辅助。结合 C200 反汇编，SDK 已暴露
`bda_fs_disk_info_like_t`，其中 `info+0x04/+0x08/+0x0c` 可用于计算剩余容量。

## 文件系统行为

系统设置使用标准 FS 调用组：

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
FS +0x040  findnext 类
FS +0x044  findclose 类
FS +0x048  disk-info 类
FS +0x07c  storage-ready 类
```

应用通过文件读写保存配置数据，并按扩展名扫描文件：

```text
.bmp
.jpg
.wav
.wma
.mp3
```

这与相册、音乐、录音和电子图书中的文件选择/媒体扩展名行为互相验证。

## GUI 行为

系统设置使用许多完整事件循环：

```text
GUI +0x030  poll 类
GUI +0x050  step 类
GUI +0x054  dispatch 类
GUI +0x17c  destroy/close 类
```

`GUI+0x3f8` 出现 58 次。典型调用：

```text
a0 = destination/surface
a1 = source/resource pointer
a2 = width 类，常见 0x27 或 0x28
a3 = height 类，常见 0x10..0x12
sp+0x10 = buffer/style pointer
```

调用者经常在调用后逐字节反转小输出缓冲，因此 `GUI+0x3f8` 可能是图片/文字到
缓冲区或 bitmap-copy 辅助，用于高亮/禁用设置项。这个判断在与游戏和系统代码
继续对比前仍应保持 provisional。

应用还使用已建立的文字和颜色辅助：

```text
GUI +0x338/+0x33c/+0x378/+0x4f0
```

## 交叉验证

- 比其他应用更强地确认 `FS+0x048` disk-info 语义。
- 确认设置 UI 中也使用 `FS+0x03c/+0x040/+0x044` 目录枚举。
- 确认 `RES+0x094` 接近 logging/trace，不是 DLX 加载。
- 确认 DLX UI 皮肤是纯 VX 图片包。

## 未确认点

1. `FS+0x048` 返回结构中每个字段的最终名称。
2. `GUI+0x3f8/+0x400` 是图片缓冲转换、masked blit，还是禁用项渲染辅助。
3. 通过 `FS+0x00c` 写入的配置文件和设置记录格式。
