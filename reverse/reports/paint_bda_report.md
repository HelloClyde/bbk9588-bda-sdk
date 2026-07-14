# 电子画板.bda 逆向报告

目标：`应用/程序/电子画板.bda`

证据：

- `reverse/reports/paint_layout.json`
- `reverse/reports/paint_calls.txt`
- `reverse/reports/paint_fs_context.txt`
- `reverse/reports/paint_gui368_context.txt`
- `reverse/reports/paint_gui35c_context.txt`
- `reverse/reports/paint_gui40c_context.txt`
- `reverse/reports/paint_gui418_context.txt`
- `reverse/reports/paint_gui314_context.txt`
- `reverse/reports/paint_media.txt`

## 头部和布局

```text
菜单标题         电子画板
分类             0x08
文件大小         1245084 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
checksum          inventory 中为 ok
```

通用布局扫描器没有推断出该应用的 BSS 边界，但启动代码确实缓存了运行时 API 表：

```text
RES 0x81d269c0
GUI 0x81d269c4
SYS 0x81d269c8
FS  0x81d269cc
MEM 0x81d269d0
```

## 内嵌资源

应用没有引用外部 `\shell\*.dlx` 路径，但引用了图片扩展名：

```text
.jpg
.bmp
bmp;jpg
```

扫描 BDA 本体可找到四张内嵌 VX 图片：

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

这些很可能是 BDA 头部/资源区中的菜单图标资源。应用的大体积主要来自代码和数据，
不是外部 DLX 皮肤。

## API 使用概览

已分类间接调用：

```text
GUI      566
FS        11
MEM        9
RES       33
SYS        2
UNKNOWN    4
total    625
```

高频 GUI 偏移：

```text
GUI +0x368  157
GUI +0x35c   63
GUI +0x40c   57
GUI +0x378   35
GUI +0x418   30
GUI +0x314   29
GUI +0x46c   27
GUI +0x4f0   13
GUI +0x310   10
```

这是当前研究绘图/画布 API 的最佳量产应用样本。

## 像素和线段绘制

`GUI+0x368` 是当前映射最强的新绘图 helper。它被调用 157 次，常出现在带坐标
和 RGB565 颜色的循环中：

```text
a0 = surface/canvas handle
a1 = x
a2 = y
a3 = RGB565 color
```

示例：

```text
0x81c04018: GUI+0x368(surface, x+i, y, 0xf800)
0x81c04054: GUI+0x368(surface, x+i, y2, 0xf800)
0x81c04094: GUI+0x368(surface, x, y+i, 0xf800)
0x81c040d0: GUI+0x368(surface, x2, y+i, 0xf800)
```

这四个循环会用红色 `0xf800` 画矩形边框，因此 `GUI+0x368` 可以高置信度命名为
put-pixel 或 draw-point 类 helper。

其他调用点会在传参前反转 16-bit 颜色：

```text
lhu a3, color
nor a3, zero, a3
andi a3, a3, 0xffff
GUI+0x368(surface, x, y, inverted_rgb565)
```

这符合橡皮、选择或反色绘制行为。

## 区域绘制和刷新

`GUI+0x35c` 会在区域复制/绘制操作前调用，也会跟在颜色创建后调用。C200 已确认
它是 draw context `+0x20` slot setter：读取 `a0=context`、`a1=value`，
返回旧 `context+0x20`，再写入新 value。常见形态：

```text
GUI+0x35c(context, resource_or_image_slot_value)
```

`GUI+0x40c` 的 C200 ABI 已确认是五参数 region draw/copy：

```text
a0 = context
a1 = x
a2 = y
a3 = width
sp+0x10 = height
```

示例中常见 `a3 = 0xf0`、`sp+0x10 = 0xf7`，接近 240x247 画布或面板刷新区域。
较小调用使用 `0x13` 和偏移坐标，可能用于工具条/UI 条带。C200 会叠加
context origin/scaling，并经过 `context+0xb0` clipping 后提交 clipped region；
它不是独立 fill-rect API。

`GUI+0x418` 表现为更大区域绘制或 update helper：

```text
a0 = context_a
a1 = x
a2 = y
a3 = width_or_x2_like
sp+0x10 = height_or_y2_like
sp+0x14 = context_b
sp+0x18 = rect_b_x
sp+0x1c = rect_b_y
sp+0x20 = backend_arg
```

C200 会把 `a0` 和 `stack+0x14` 归一化成两个 context，分别叠加 origin/scaling，
遍历 `context_b+0xc0` 子区域链，并把 `stack+0x20` 转发给 backend `+0x94`。

大多数 `GUI+0x418` 调用后立刻跟着：

```text
GUI+0x314(context)
```

因此 `GUI+0x314` 是绘图 surface/canvas flush-and-free 路径的一部分。C200 已确认
它调用 backend `+0x34(context+0x10)`，清理 `context+0x94/+0xb0`，随后释放
context；它不是单纯 invalidate。

## 文件行为

与 GUI 工作量相比，该应用 FS 调用很少：

```text
FS +0x000  fopen 类
FS +0x004  fclose 类
FS +0x010  fseek 类
FS +0x014  ftell 类
FS +0x02c  目录存在检查/chdir 类
FS +0x030  mkdir 类
FS +0x03c  findfirst 类
FS +0x044  findclose 类
FS +0x048  disk-info 类
```

图片读取/保存路径会检查文件大小：

```text
fopen(path, mode)
fseek(file, 0, SEEK_END)
size = ftell(file)
fclose(file)
if size > 0x400000: reject
```

这与相册 `LoaderPicture` 路径中观察到的 `0x400000` 图片大小上限一致。

## 交叉验证

- 与相册：确认图片扩展名集合 `.jpg/.bmp/bmp;jpg` 和 `0x400000` 最大图片大小限制。
- 与图片笔记：强化 `GUI+0x35c/+0x40c/+0x410/+0x418` 属于图片/画布绘制族。
- 与文字、电子图书、记事本：确认画布应用也使用 `GUI+0x4f0` 绘制标签/工具 UI。
- 与系统设置：确认依赖存储的操作前会使用 `FS+0x048` disk-info。

## 未确认点

1. `GUI+0x418` 的高层 source/destination 语义仍需结合原机调用点和硬件探针。
2. BMP/JPEG 保存路径还未命名；当前扫描能看到扩展名和大小检查，但直接上下文
   还不足以命名编码器调用。
