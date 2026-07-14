# Paint/Canvas API 笔记

主要证据来自原机 `电子画板.bda` 的静态报告：
`reverse/reports/paint_bda_report.md`。

已经通过独立 BDA 动态闭环的彩色画点、线、圆、矩形轮廓和文字接口统一记录在
`verified/graphics_primitives_api.md`。本文其余内容仍是逆向笔记，不能自动视为已验证 API。

## 画点：GUI +0x368

`GUI+0x368` 是当前映射最强的 canvas helper。`电子画板.bda` 调用它 157 次，
经常出现在简单线段/矩形循环里：

```text
a0 = draw context
a1 = x
a2 = y
a3 = RGB565 color
```

画板应用中能看到用 `0xf800` 绘制红色矩形边框的形态：

```text
GUI+0x368(surface, x+i, y,   0xf800)
GUI+0x368(surface, x+i, y2,  0xf800)
GUI+0x368(surface, x,   y+i, 0xf800)
GUI+0x368(surface, x2,  y+i, 0xf800)
```

SDK wrapper：

```c
int bda_gui_put_pixel_like(bda_handle_t context, s32 x, s32 y, u32 color);
```

该 helper 必须配合 GUI 生命周期中取得的真实 draw context/window handle 使用。
传 `0` 或猜测出来的 handle 不安全。

## 区域绘制和刷新

画板应用大量使用与相册相同的 image/render helper 族：

```text
GUI +0x35c  draw context resource/image slot setter；写 context+0x20
GUI +0x40c  region draw/copy helper；context,x,y,width,height
GUI +0x410  render/copy helper；context,x,y,width,height,descriptor
GUI +0x418  双 context/双矩形 render helper
GUI +0x314  surface/canvas flush-and-free；调用 backend +0x34 后释放 context
GUI +0x334  background/fill color-like
```

`GUI+0x35c` 的 C200 table entry 只读取 `context,value`，返回旧 `context+0x20`，
再把 `value` 写到 `context+0x20`；`context==0` 时使用默认 draw context
`0x80825690`。画板里它常在 region draw 或 color/resource 切换前出现，因此更像当前
bitmap/resource slot setter，而不是 object 生命周期绑定。

`GUI+0x40c` 的 C200 table entry 已确认是五参数
`context,x,y,width,height`，第五参数 `height` 来自 caller `stack+0x10`。函数会构造
`x/y/x+width/y+height` 矩形，叠加 draw context origin/scaling，经过
`context+0xb0` clipping 后通过 draw backend 提交 clipped region。它不是独立
fill-rect API，仍需要真实 draw context 和 backend 状态。

`GUI+0x410` 是六参数 render/copy helper，读取
`context,x,y,width,height,descriptor`。C200 会读取 descriptor `+0x04/+0x08`
作为源尺寸类字段、`+0x14` 作为 source buffer/bitmap pointer、`+0x18` 选择
backend `+0x88` 或 `+0x80` 路径。若 clipping 后宽度和 descriptor 宽度不同，
它会按 backend bytes-per-pixel 临时分配裁剪 buffer，调用 backend `+0x8c`
生成裁剪副本，结束后释放该临时 buffer。

`GUI+0x418` 调用点后面通常紧跟 `GUI+0x314(context)`。C200 已确认
`GUI+0x314` 会调用 draw backend `+0x34(context+0x10)`，清理
`context+0x94/+0xb0`，最后释放 context；它不是只做 invalidate 的无所有权
update。SDK 已暴露 wrapper：

C200 中 `GUI+0x418` 读取第二个 context 和多组 stack 参数，会按两个 context 的
origin/scaling 字段计算 source/destination 区域，再通过 backend `+0x94` 提交。
已确认 `stack+0x14` 是第二 context，`stack+0x18/+0x1c` 是第二矩形 origin，
`stack+0x20` 会转发给 backend；高层 source/destination 语义仍要结合原机调用点。
它不是无参数 render finish，也不适合作为通用 flush API。

```c
void bda_gui_surface_flush_like(bda_handle_t context);
int bda_gui_set_fill_color_like(bda_handle_t handle, u32 color);
```

这两个 wrapper 只适合在已有真实 surface/draw handle 的 draw 生命周期里使用。
不要在裸 `bda_main()` 中传 `0` 调用；这类缺 context 的 probe 可能导致真机重启。

## Image Read/Write 线索

画板应用引用：

```text
.jpg
.bmp
bmp;jpg
```

它的文件大小检查和相册一致：

```text
fopen(path, mode)
fseek(file, 0, SEEK_END)
size = ftell(file)
fclose(file)
if size > 0x400000: reject
```

这能交叉验证相册 `LoaderPicture` 路径。画板自己的 image encode/save ABI 还没有
映射完成，不能作为 public SDK wrapper 使用。
