# Image Decode/Display 笔记

本文主要来自 `我的相册.bda`，尤其是其中的 `LoaderPicture` 例程。名称仍偏保守，
但 offset 和参数形态有相册调用点支撑。

辅助报告：

- `reverse/reports/album_bda_report.md`：第一份针对 `我的相册.bda` 的静态报告。
- `reverse/reports/ebook_bda_report.md`：电子书应用，提供 GUI image/resource helper 的交叉证据。
- `reverse/reports/paint_bda_report.md`：画布应用，是 `GUI+0x368` 画点和
  `GUI+0x35c/+0x40c/+0x418/+0x314` 绘制/刷新族的最强证据。
- `reverse/reports/schedule_bda_report.md`、`reverse/reports/ninecourse_bda_report.md`：
  内容应用证据，包含外部 shell DLX skin 组合以及 `GUI+0x430/+0x46c`
  rect prepare / rect contains 调用对。

小型游戏显示路径也能交叉验证 VX resource 和 framebuffer 路线：

```text
reverse/reports/eros_bda_report.md
reverse/reports/linkgame_bda_report.md
reverse/reports/blackwhite_bda_report.md
reverse/reports/jiugongge_bda_report.md
reverse/reports/thunder_bda_report.md
reverse/reports/tank_bda_report.md
reverse/reports/sango_bda_report.md
```

这些游戏显示出一个常见模式：把四个 VX resource 直接嵌入 BDA resource 区，而不是依赖外部
DLX 包。

## High-level 流程

系统文件管理器会把 `jpg` 和 `bmp` 文件分发给原机相册应用：

```text
A:\应用\程序\我的相册.bda
*.bmp
*.jpg
bmp;jpg
LoaderPicture
LoaderPicture FileName = %s
开始解码
ret = %d
---Width = %d, Height = %d---
成功
失败
```

相册先通过 FS table 打开选中的 image file：

```text
FS +0x000  fopen(path, "rb")
FS +0x010  fseek(file, 0, SEEK_END)
FS +0x014  ftell(file)
FS +0x004  fclose(file)
```

解码前会拒绝空文件和大于 `0x400000` byte 的文件。

## LoaderPicture ABI

`我的相册.bda` 中 app-level `LoaderPicture` entry 位于 `0x81c0683c`。已观察到的
调用者传参：

```text
a0 = owner/window/image handle
a1 = full path buffer
a2 = output picture descriptor
a3 = preview/extra flag
stack+0x10 = mode byte，已见 0
```

该例程会查找文件名最后一个 `.`。扩展名以 `b` 或 `B` 开头走 BMP 路径，其他
扩展名走 JPEG-like 路径。

## Decode API

`bda_sdk.h` 当前暴露两个 GUI table decode wrapper：

```text
GUI +0x670  BMP decode-like
  C200 target = 0x800e1f74
  a0 = owner/window/image handle
  a1 = bda_picture_like_t *out
  a2 = path
  a3 = void **out_source_buffer；VX 快路径成功会写回源 file buffer pointer，
       非 VX decoder 路径或失败路径通常写 0

GUI +0x808  JPEG decode-like
  C200 target = 0x800e2d2c
  a0 = owner/window/image handle
  a1 = bda_picture_like_t *out
  a2 = path
  a3 = mode byte；C200 会截成 signed 8-bit，已见 0
```

`LoaderPicture` 会记录并传播 decoder return value。周围分支暗示 `0` 是成功、`1` 是
失败，但仍需要用已知可解码 BMP/JPEG 做 hardware probe 确认。

`C200.bin` function-level slice 显示，两个 wrapper 都会先通过内部 helper 读取 `path` 指向的
文件数据，再填充输出 descriptor。BMP/VX 快路径要求 `out_source_buffer` 是
可写 pointer slot，不要传 `NULL`。它们不是完整 image control API；owner handle、
输出 buffer 生命周期和最终 draw/surface 生命周期仍需要由调用者按原机相册路径复刻。

VX 快路径会写：

```text
out+0x00 = 0
out+0x04 = width   (来自 VX header +0x06)
out+0x08 = height  (来自 VX header +0x0a)
out+0x0c = width * 2
out+0x10 = resource[0x12]
out+0x11 = 0x10
out+0x14 = resource + 0x18
out+0x18 = -1
*out_source_buffer = file buffer
```

临时 output struct：

```c
typedef struct bda_picture_like {
    void *pixels;            /* +0x00 decoder/normalized RGB565 pixels */
    u32 width;               /* +0x04 */
    u32 height;              /* +0x08 */
    u32 stride_bytes;        /* +0x0c, VX 快路径写 width * 2 */
    u8 mode10;               /* +0x10, VX 快路径来自 resource[0x12] */
    u8 bits_per_pixel11;     /* +0x11, VX 快路径写 0x10 */
    u8 internal12;           /* +0x12 */
    u8 internal13;           /* +0x13 */
    void *source_pixels;     /* +0x14, VX 快路径写 resource + 0x18 */
    s32 selected_index;      /* +0x18 initialized to -1 by album helper */
} bda_picture_like_t;
```

`mode10/internal12/internal13` 仍是保守命名；`width/height/stride_bytes` 和
`source_pixels` 来自 C200 VX 快路径的直接写入证据。

## 解码后的渲染

相册会读取描述符 `+0x00`、`+0x04`、`+0x08`、`+0x0c`、`+0x10`、`+0x14`、
`+0x18` 等字段，并把尺寸和 `240`、`320` 比较，以选择居中或 scaling。

`0x81c014d0` 附近的 helper 会把解码后的 RGB565 image 归一化进这个 descriptor。
根据 global direction byte，它要么直接指向 decoder buffer，要么用 `MEM+0x008` 分配一份
复制/旋转后的 RGB565 buffer。

显示阶段会走相册、画板和游戏都出现过的 region/render helper 族：

```text
GUI +0x35c  resource/image slot setter；写 draw context +0x20
GUI +0x40c  region draw/copy helper；context,x,y,width,height
GUI +0x410  render/copy helper；context,x,y,width,height,descriptor
GUI +0x418  双 context/双矩形 render helper
```

`GUI+0x35c` 的 C200 table entry `0x800b2d58` 已确认是 `context,value` setter：
返回旧 `context+0x20`，再写入新值。它不负责分配或释放 image resource，只是把当前
draw pipeline 使用的 resource/image-like 值挂到 context 状态里。

`GUI+0x410` 的 C200 table entry `0x800b3124` 是六参数 render/copy helper，会读取
`descriptor+0x04/+0x08/+0x14/+0x18`，按当前 context clipping 裁剪后调用 backend
`+0x80/+0x88`。`descriptor+0x04/+0x08` 是源尺寸类字段，`+0x14` 常作为
source buffer/bitmap pointer，`+0x18` 选择 backend 路径。裁剪后宽度变化时，
C200 会按 backend bytes-per-pixel 临时分配 buffer，并调用 backend `+0x8c`
生成裁剪副本，结束后释放该临时 buffer。它仍不是可独立使用的 image control API。

`GUI+0x418` 的 C200 table entry `0x800b3d90` 会读取第二个 context 和 source/destination
矩形参数，命中子区域后调用 backend `+0x94`。因此它更像双 context render/copy
helper，不是简单 present/finish。末参数为 RGB565 `color_key_or_zero`：原机
雷霆战机/决战坦克使用 `0xf81f`，V20 已在模拟器确认洋红 source pixel 透明。

`0x81c06f78` 的 dispatcher 通过 jump table 选择 `0..7` render/clip/scaling mode，
并大量调用 `GUI+0x418`。

resource state 路径可用 `RES+0x090` 读取。C200 会向 `bda_res_state_like_t` 写入
7 个 word，其中 `+0x10` 写出后会减 1；字段语义仍按 `aux*` 保守命名。该结构
适合复刻相册/课程表这类 resource render 路径，不应当作通用 image control 状态。该 API
只写 snapshot，SDK wrapper 是 `void`，不要读取 return value。
当前字段名为 `aux00`、`aux04`、`aux08`、`aux0c`、`aux10_minus1`、
`aux14`、`aux18`；这些名字只保证 offset 和写入顺序，不保证业务语义。
最小编译示例见 `sdk/api/examples/res_state_demo.c`；它用于验证 SDK 类型和
wrapper ABI，不是推荐的第一个运行 smoke。

## 与其他应用的交叉证据

电子书应用为 `GUI+0x46c` 提供了额外证据：很多 call site 会先从小型 resource record 相邻
word 里加载 `a1/a2`，再调用 `GUI+0x46c`，随后用附近 GUI helper 查询或绘制。
C200 已确认 `GUI+0x46c` 是 `rect,x,y` 点-in-rect 判断，不是 image draw 或
resource loader。电子书中的 `a1/a2` 应理解为待测试点坐标。

课程表和九门课程也支持这个方向：它们会调用 `GUI+0x430` 写入栈上的
`x0/y0/x1/y1` rect record，然后以计算出的坐标值调用 `GUI+0x46c` 做 hit-test。
这组路径属于内容应用的 rect prepare / rect contains 逻辑，和直接绘制完整 VX block
的 `GUI+0x540` 分开。

`C200.bin` 的 GUI table 确认 `GUI+0x430` 指向 `0x800c0410`。SDK 现在提供
`bda_gui_rect_prepare_like(rect, x0, y0, x1, y1)`，按
`BDA_GUI_RECT_PREPARE_LIKE` 的 `rect,x0,y0,x1,y1` 五参数 ABI 写入 rect；
第五参数来自 `stack+0x10`，由 wrapper 通过 `bda_call5` 传入。调用者仍要保证
`rect` 指向至少 16 byte 可写内存。
`GUI+0x46c` 指向 `0x800c0818`，SDK 包装为
`bda_gui_rect_contains_like(rect, x, y)`；它只读取四个 word rect 和两个坐标，
返回点是否在矩形内。

## SDK 状态

`bda_sdk.h` 当前提供：

```c
int bda_gui_decode_bmp_like(void *owner, bda_picture_like_t *out,
                            const char *path, void **out_source_buffer);
int bda_gui_decode_jpeg_like(void *owner, bda_picture_like_t *out,
                             const char *path, u32 mode);
void bda_gui_rect_prepare_like(bda_rect_like_t *rect, s32 x0, s32 y0, s32 x1, s32 y1);
```

`GameJpegProbeV7` 已在完整 NAND 模拟器上用官方 `gcddh.jpg` 验证 mode 0/1：两次均
返回独立的 `300x300` `source_pixels`，可由 `GUI+0x410` 缩放到 `100x100` 显示，
并可分别通过 `GUI+0x50c` 释放。普通 JPEG descriptor 的 `stride/mode/bpp` 仍为零，
调用者只应依赖 `width/height/source_pixels/selected_index`。该结果尚未提升为真机 verified。

这些 wrapper 适合 controlled experiment，不适合作为“直接可用的 image control API”。要做稳健 custom
应用，还缺少两个真机已验证边界：

- 当前 frame draw context 作为 decoder owner 的适用范围。
- `GUI+0x410` 缩放、裁剪和 decoder source 释放的真机闭环。

在这两点确认前，普通应用更稳的 image 路线仍是保留完整 VX resource block 并通过
`bda_gui_draw_vx_like(handle, x, y, vx_resource)` 在已有 draw handle 上绘制。
`GUI+0x540` 的 C200 table entry 虽然 ABI 上保留 6 个参数位置，但实际 width/height
来自 VX header 的 `+0x06/+0x0a`，不是调用者传入的 scaling 参数。
