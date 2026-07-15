# 文字和简单绘制笔记

GUI 表里有直接文字绘制 helper。当前判断来自记事本、电子书等原机调用点：
这些调用点的字符串参数会指向可见 UI 文本，例如搜索提示、笔记标题、书签标签。
逐 BDA 证据见：

- `reverse/reports/notepad_bda_report.md`
- `reverse/reports/ebook_bda_report.md`

## 绘制文字：GUI +0x4f0

`GUI+0x4f0` 当前命名为 `draw_text_like`：

```text
a0 = drawing/window handle
a1 = x
a2 = y
a3 = GBK/ASCII string
stack+0x10 = extra/width/flags，常见为 -1
```

C200 table entry 目标为 `0x800c0d40`。table entry 会从调用者 stack 读取第五参数 `extra`：

- `extra == 0` 时直接返回 `0`。
- `extra < 0` 时调用内部 strlen-like helper `0x800068c4(text)` 取得字符串长度。
- `extra > 0` 时直接把它作为长度/限制参数传给后续文字尺寸 helper。
- 正常路径调用 `0x80119f68(context, context+0x54, text, extra)` 计算文本宽高，
  并更新 `context+0x5c/+0x60` 一类当前位置字段。

因此 `extra=-1` 是当前最接近“按 NUL 结尾字符串绘制”的保守用法；不要把
`extra=0` 当作默认值。

原机形态示例：

```text
draw_text_like(handle, 0x20, 0x04, "search", -1)
draw_text_like(handle, 0x04, 0x1c, "label", -1)
draw_text_like(handle, 0x04, 0x30, "label", -1)

电子书调用点：
  GUI+0x4f0(handle, 0x20, 0x04, str_at_0x81c16d88, style)
  GUI+0x4f0(handle, 0xa8, 0x12d, str_at_0x81c16d90, style)
  GUI+0x4f0(handle, 0x34, 0x22, dynamic_string, -1)
```

SDK wrapper：

```c
int bda_gui_draw_text_like(bda_handle_t handle, s32 x, s32 y, const char *text, s32 extra);
```

### 记事本短标签的完整作用域

记事本的 11 个 `GUI+0x4f0` 调用用于短标签，不用于 TXT 正文。搜索标题调用点
`0x81c01878..0x81c019e8` 的局部顺序是：

```text
draw = GUI+0x0e4(frame)
... 背景/资源图 ...
GUI+0x338(draw, 1)
color = GUI+0x378(draw, 255, 255, 255)
GUI+0x33c(draw, color)
GUI+0x4f0(draw, 0x20, 4, label, -1)
GUI+0x0e8(frame, draw)
```

这段局部路径没有 `GUI+0x074`。`TouchStageV13` 在 object draw scope 内额外套用
`GUI+0x074(1/0)`，真机文字仍逐字显示，所以 V13 不能作为记事本短标签提交顺序的
精确复刻。`TouchStageV18` 移除这层 guard 后，真机首帧文字不再逐字出现，但 wndproc
返回后绘制的触摸坐标和十字没有提交到屏幕。这说明 `+0x0e8` 的一次性显示效果依赖
消息 paint 阶段，不能当作任意时刻都有效的 present。`TouchStageV19` 把动态绘制
移入触摸 `message 1/2` callback 后仍不显示，进一步说明任意 wndproc 消息也不等于
paint。`TouchStageV20` 使用 `GUI+0x0e0(frame)` 请求 `0xb1`，但真机在该调用内部
死机，说明 `+0x0e0` 的 object preparation 不接受 standalone 顶层 frame。
`TouchStageV21` 绕过 object-specific wrapper，直接用 `GUI+0x03c(frame,0xb1,0,0)`
设置 redraw pending flag；真机返回成功但 event pump 没有派发 `0xb1` callback。
`TouchStageV22` 拆开 `+0x074` 的 begin/end：无 guard 完成 object draw 后只调用
`+0x074(0)`；真机返回 0，但坐标和十字仍不可见，证明 end 调用不能单独充当 present。
`TouchStageV23` 因而保留无 guard 的初始 object paint，并让动态十字恢复完整
`+0x074(1/0)`；动态坐标不用 `GUI+0x4f0`，改由应用内 5x7 点阵字和 `GUI+0x368`
逐像素绘制。V23 真机已确认坐标和十字正常显示且连续更新无闪烁，说明该拆分可以同时
获得静态标签的一次显示和动态像素的可靠提交。

### 记事本 TXT 正文

记事本把正文交给 `"medit"` child control，而不是自行循环调用 `GUI+0x4f0`：

```text
GUI+0x1a4("medit", "", 0x08083001, 0,
          0x65, 0, 0x46, 0xf0, 0x82, parent, 0)
GUI+0x040(body, 0x0134, 0, text_buffer)          set text
GUI+0x040(body, 0x0133, 0x19000, output_buffer) get text
GUI+0x040(body, 0xf0c5, 0x19000, 0)             max length
```

`0x0133/0x0134` 是 control message id，不是 GUI table offset。固件控件负责正文的
换行、滚动、光标和后续重绘；这条路径不能直接解释短标签是否原子提交。

## Text Color

`GUI+0x378` 会用当前 draw/context 的 color conversion callback 生成内部 color value：

```text
a0 = draw/context，0 时使用默认 context 0x80825690
a1 = red，C200 只取低 8 位
a2 = green，C200 只取低 8 位
a3 = blue，C200 只取低 8 位
return = 内部 color value
```

return value 随后传给 `GUI+0x33c`。`GUI+0x33c` 会把 color 写入 context+0x50，并返回
旧 text color value：

```text
a0 = draw/context，0 时使用默认 context 0x80825690
a1 = color
```

注意：`GUI+0x378` 的 return value 不是裸 RGB565 常量。直接把 RGB565 传给
`bda_gui_set_text_color_like()` 或 `bda_gui_set_fill_color_like()` 可能只在部分
context 下碰巧有效。

常见形态：

```text
color = GUI+0x378(handle, 255, 255, 255)
GUI+0x33c(handle, color)

color = GUI+0x378(handle, 0, 0, 0)
GUI+0x33c(handle, color)
```

SDK wrapper：

```c
int bda_gui_rgb_like(bda_handle_t handle, u32 r, u32 g, u32 b);
int bda_gui_set_text_color_like(bda_handle_t handle, u32 color);
int bda_gui_set_fill_color_like(bda_handle_t handle, u32 color);
```

## 文本模式

`GUI+0x338(handle, mode)` 经常在选择 color 和 draw text 前调用。C200 会选择
`a0` 指向的 draw/context；`a0 == 0` 时使用默认 context `0x80825690`。
它把 `a1=mode` 写入 `context+0x18`，并返回旧 mode 值。mode 的枚举含义仍需
结合更多绘制路径确认，当前只固定 ABI。

SDK wrapper：

```c
int bda_gui_set_text_mode_like(bda_handle_t handle, u32 mode);
```

## 当前实用状态

文字 API 最大缺口不是 `draw_text` 本身，而是新应用如何稳定取得有效
drawing/window handle。原机应用通常在自己的 window/control handle 上，从 paint 或
event callback 中调用这些文字 helper。当前建议只在以下场景使用：

- 复刻原机 frame/control 生命周期后，在 callback 里拿到真实 handle。
- 基于原机模板 patch，在已有绘制路径里替换文本或增加调用。
- controlled probe 中已经确认 handle 有效。

不要把 `handle=0` 当作安全默认值。

## Hardware Probe 结论

失败/风险 probe：

```text
TextDraw.bda 使用 handle=0 调用 set_text/rgb/draw_text 后重启。
TextEditOnly.bda、TextEditColor.bda、TextEditDraw.bda 也都重启。
这些 probe 在裸 main 中直接调用 GUI+0x1a4 创建 edit/control，因此独立创建 control
不安全。C200 已确认 `GUI+0x1a4` 的 ABI 和 stack 参数布局；失败点更可能是缺少真实
parent/frame lifecycle，而不是简单参数顺序错误。不要把这些 probe 当成 SDK 推荐示例。
```

更安全的验证路线是基于原机记事本模板，只替换已有绘制路径里的字符串。

`TextNativePatch.bda` 替换了记事本搜索窗口文本：

```text
查找到的文件 -> TEXTAPI-OK!!
查找         -> TEXT
```

真机确认：

```text
搜索窗口标题变为 TEXT。
搜索结果窗口标题变为 TEXTAPI-OK!!。
```

`TextBodyPatch.bda` 进一步替换了记事本“新建笔记”对话框正文标签：

```text
名  称: -> NAME-OK
内  容: -> BODY-OK
```

真机确认：

```text
编辑笔记窗口的正文标签区域显示 NAME-OK 和 BODY-OK。
```

## 原机交叉验证

其他原机应用也使用同一 text/color call cluster：

```text
课程表.bda      GUI+0x4f0: 13 次
九门课程.bda    GUI+0x4f0: 50 次
```

九门课程既绘制静态 label，也绘制动态课程 text buffer。因此在拥有有效 draw handle
和 window/control 生命周期的前提下，`GUI+0x4f0` 可以视为通用 GBK/ASCII text renderer。
