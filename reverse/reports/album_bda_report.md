# 我的相册.bda 逆向报告

## 状态

首版静态报告，重点是图片显示和图像相关 SDK 证据。

证据：

```text
应用/程序/我的相册.bda
reverse/reports/album_layout.json
reverse/reports/album_calls.txt
sdk/doc/picture_notes.md
sdk/doc/media_notes.md
sdk/doc/fs_notes.md
```

## 头部和布局

```text
文件大小          317,052 bytes
菜单标题         我的相册
分类           0x08
入口文件偏移  0x95f8
运行时入口 VA   0x81c00020
运行时文件基址  0x81bf6a28
头部 checksum    ok
```

缓存的运行时表全局变量：

```text
RES  0x81c440a0
GUI  0x81c440a4
SYS  0x81c440a8
FS   0x81c440ac
MEM  0x81c440b0
```

通用布局脚本尚未推断出这个应用的 BSS 起止地址，但 `bda_table_globals.py`
确认运行时表缓存块位于 `0x81c440a0`。

## API 使用概览

`我的相册.bda` 包含 269 个已分类的运行时表间接调用：

```text
GUI +0x418   31 次  双 context/双矩形 render helper
GUI +0x40c   11 次  region draw/copy helper
GUI +0x35c   11 次  draw context resource/image slot setter
GUI +0x368    8 次  图片/显示辅助候选
GUI +0x410    5 次  render/copy helper
GUI +0x030    8 次  event poll
GUI +0x050    8 次  event step
GUI +0x054    8 次  event dispatch
GUI +0x084    8 次  register frame
GUI +0x17c    8 次  frame close/release

FS  +0x000    3 次  open/fopen-like
FS  +0x010    3 次  seek-like
FS  +0x014    3 次  tell/size-like
FS  +0x03c    2 次  findfirst-like
FS  +0x040    2 次  findnext-like
FS  +0x044    2 次  findclose-like
FS  +0x07c    1 次   storage-ready-like

RES +0x090    2 次  resource/picture state-like
RES +0x094   55 次  trace/log-like or diagnostics
SYS +0x08c    1 次   媒体/设备辅助候选
SYS +0x090    1 次   媒体/设备辅助候选
```

## 图片流程证据

这个应用目前是图片显示路径最强的原机 BDA 证据。它的调用模式不同于 Element
的简单 VX 绘制路径：

```text
RES +0x090  -> 返回/填充图片状态候选数据
GUI +0x35c  -> 写 draw context +0x20 的 resource/image slot
GUI +0x40c  -> context,x,y,width,height region draw/copy
GUI +0x410  -> context,x,y,width,height,descriptor render/copy
GUI +0x418  -> 双 context/双矩形 render helper
```

这与 `picture_notes.md` 互相印证；其中已经怀疑 `RES+0x090` 是解码图片/资源
状态辅助函数。由于 `我的相册` 只使用少量 FS open/seek/tell，却大量使用 GUI
渲染辅助调用，图片解码很可能不是 Element 那种应用内 DLX 解析器，而是依赖
系统图片解码/显示服务。

C200 已确认 `GUI+0x35c/+0x40c/+0x410/+0x418` 的低层参数边界，但它们都依赖
真实 frame/control/draw context 生命周期。相册报告不能把这些 helper 升格为
可从裸 `bda_main()` 直接调用的 public image API。

## 文件系统行为

该应用使用：

```text
FS+0x07c          存储就绪/媒体存在检查
FS+0x03c/040/044  目录扫描调用组
FS+0x000/010/014  图片文件 open/seek/tell
```

这使 `我的相册` 成为补全用户媒体目录枚举语义的良好样本。它不如记事本适合
普通文件编辑语义，但更适合媒体扫描语义。

## 交叉验证

- `元素周期表.bda` 通过应用内解析 DLX 和 `GUI+0x540` 显示 VX 图片。
- `我的相册.bda` 在当前扫描中没有出现同样的 `GUI+0x540` 路径，而是集中在
  `GUI+0x35c/+0x40c/+0x418` 与 `RES+0x090`。
- 因此固件里至少有两条图片路径：直接 VX 资源绘制（`GUI+0x540`）和
  解码后用户图片显示（`RES+0x090` + GUI 渲染辅助调用）。

## 未确认点

1. `RES+0x090` 的准确参数布局。
2. `GUI+0x368` 与 render helper 族之间的高层调度关系；`+0x40c/+0x410/+0x418`
   的低层 ABI 已有 C200 边界，但相册的 source/destination 业务语义仍需函数级映射。
3. 这个应用中的系统解码器接受哪些图片格式。
4. 用户照片目录和文件名过滤字符串。通用字符串提取器会被嵌入图片数据污染，
   因此这里需要函数上下文提取，而不是直接读原始字符串。

## 后续静态任务

1. 提取两处 `RES+0x090` 调用的指令上下文。
2. 恢复相册传给 `GUI+0x35c/+0x40c/+0x410/+0x418` 的结构体和 mode 分支。
3. 与 `飞天影音.bda`、`电子图书.bda` 的图片/视频路径对比。
4. 构建探针时先复制相册参数布局，再调用 `RES+0x090`，不要把它当作猜测的
   独立调用。

