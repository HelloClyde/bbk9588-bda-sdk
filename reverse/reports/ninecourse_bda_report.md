# 九门课程.bda 逆向报告

`九门课程.bda` 是分类 `0x05` 的学习/内容应用。它比 `课程表.bda` 更大、
状态更多，是当前较好的非游戏样本之一：同一个应用里同时出现文件数据、外部
DLX 皮肤、GUI 控件、文字绘制和大区域绘制。

## 头部和布局

```text
文件大小         143,868 bytes
菜单标题         九门课程
分类             0x05
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS 范围         0x81c19c20..0x81c52991
checksum          ok
```

运行时表全局变量：

```text
RES  0x81c19c20
GUI  0x81c19c24
SYS  0x81c19c28
FS   0x81c19c2c
MEM  0x81c19c30
```

## 外部资源

可见字符串包括：

```text
\Shell\JiuMenKeCheng.dlx
\Shell\JiuMenKeChengHeiSeTuPian.dlx
rb
wb
```

应用还内嵌四个通用 shell VX 资源：

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

两个外部 DLX 名称被反复引用，推测是普通/暗色皮肤包，或不同页面使用的美术包。

## API 使用概览

当前间接调用扫描共发现 708 个运行时表调用：

```text
FS  +0x000   9  fopen 类
FS  +0x004   9  fclose 类
FS  +0x008  23  fread 类
FS  +0x00c   4  fwrite 类
FS  +0x010  21  fseek 类
FS  +0x02c   2  目录存在检查/chdir 类
FS  +0x030   2  mkdir 类
FS  +0x048   3  磁盘信息类
FS  +0x064   2  低层 block read support helper；不公开 SDK wrapper

GUI +0x030/+0x050/+0x054  事件 poll/step/dispatch
GUI +0x084/+0x088/+0x08c/+0x17c  frame 生命周期
GUI +0x1a4/+0x1a8/+0x1ac/+0x1b0  control/object 创建、销毁和 update message
GUI +0x308/+0x30c  begin/end draw
GUI +0x338/+0x33c/+0x378/+0x4f0  文字模式、颜色、文字绘制
GUI +0x3f8/+0x400  framebuffer/大区域绘制族
GUI +0x430/+0x46c  rect prepare / rect contains 调用对
GUI +0x540  VX/资源绘制分支中出现

MEM +0x008  25  allocation 类
MEM +0x00c  23  free 类
RES +0x090   3  资源状态辅助类
RES +0x094  18  trace/log 类
```

## GUI 对象模型

应用通过 `GUI+0x1a4` 创建顶层对象，style 值位于 `0x08000000` 家族，并把
返回 handle 保存到应用全局变量。随后它使用额外控件/对象调用：

```text
GUI+0x1ac(handle, 0x64, 0x190)
GUI+0x1b0(handle, 0x64)
```

这些调用出现在滚动、翻页或重建视图路径中。C200 已确认 `GUI+0x1ac`
同步发送内部 message `0x162`，参数形态为 `handle,a1,a2`；`GUI+0x1b0`
同步发送内部 message `0x163`，参数形态为 `handle,a1`。它们不是 lock/unlock
或 begin/end frame，而是对象 update notification，最终效果由目标 object/control
callback 决定。最小 Element 图片探针没有使用它们，因此它们是解释“简单
Showcase 应用能画一次但不像完整应用那样运行”的重要线索。

## 绘制模型

九门课程大量使用普通 draw handle 和大区域辅助：

```text
GUI+0x308/+0x30c       draw 生命周期
GUI+0x074              draw/present guard
GUI+0x3f8/+0x400       大区域/framebuffer 调用对
GUI+0x430/+0x46c       rect prepare / rect contains 调用对
GUI+0x4f0              文字绘制类
```

`GUI+0x4f0` 出现 50 次。有些调用传静态字符串，有些绘制由课程数据生成的动态
文本缓冲区。应用在绘制前频繁设置文字模式和文字颜色，与记事本、时间、电子图书
和 BBVM 的行为一致。

`GUI+0x430/+0x46c` 在内容 UI 热点判断里成对出现。C200 已确认 `GUI+0x430`
是 `rect,x0,y0,x1,y1` 五参数 rect writer，`GUI+0x46c` 是 `rect,x,y`
点-in-rect 判断；这里不应再解释为资源/图片绘制 API。

`GUI+0x3f8/+0x400` 也出现在小游戏里，但这里它出现在学习/内容 UI 内部。因此
这对入口应描述为大区域/framebuffer 类，而不是游戏专用。

## 文件和存储流程

该应用比课程表读写更多数据。它使用：

```text
open/read/seek/write/close 处理固定记录
FS+0x02c / FS+0x030 准备目录
FS+0x048 检查磁盘信息
FS+0x064 低层 block read support 调用
```

在 `FS+0x048` 调用点，应用会读取返回信息缓冲区中的 word，并计算类似容量的
值；这个模式与系统设置和时间应用一致。

`FS+0x064` 不是普通 stdio 调用。两个调用点都会建立 `0x218` byte stack
buffer，传 `a2=1, a3=stack+0x10`，然后分别读取 `stack+0x34` 或
`stack+0x14` 的 byte 与应用全局变量比较。C200 侧确认该入口会检查
signed 16-bit volume/index、转换 block/cluster 参数，并调用内部
`0x8017fbc0(...)` 读到调用者 buffer。它仍不应公开为 SDK wrapper；详见
`reverse/docs/fs_notes.md` 和 `reverse/docs/c200_api_function_notes.md`。

## 对 SDK 的含义

1. 自定义显示应用在使用文字和图片 helper 前，需要稳定的对象/frame 生命周期。
2. `GUI+0x1ac/+0x1b0` 已可按 object update message pair 记录；九门课程是当前
   最强来源，但具体业务效果仍要看 object/control callback。
3. `GUI+0x3f8/+0x400` 不应标成游戏专用。
4. `FS+0x064` 依赖 firmware 内部 volume/index 和 block 参数，不能暴露为公共 SDK helper。

## 未确认点

1. `GUI+0x1ac/+0x1b0` 在九门课程滚动/翻页路径中的高层业务语义。
2. 课程数据文件的结构/记录格式。
3. `FS+0x064` 上游 volume/index 和 block 参数来自哪些课程数据路径。
4. 普通/暗色 DLX 是否由主题、显示模式或资源回退路径选择。
