# 课程表.bda 逆向报告

`课程表.bda` 是分类 `0x09` 的工具/内容应用。它是非游戏显示应用窗口/事件
生命周期的有用交叉验证样本：应用会打开外部 DLX 皮肤文件、创建 GUI 对象、
使用正常事件 pump，并在生命周期内部绘制文字和资源图片。

## 头部和布局

```text
文件大小         83,020 bytes
菜单标题         课程表
分类             0x09
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS 范围         0x81c0ae70..0x81c0b001
checksum          ok
```

运行时表全局变量：

```text
RES  0x81c0ae70
GUI  0x81c0ae74
SYS  0x81c0ae78
FS   0x81c0ae7c
MEM  0x81c0ae80
```

## 外部资源

可见资源路径：

```text
\Shell\KeChengBiao.dlx
\Shell\KeChengBiaoHeiSeTuPian.dlx
rb
wb+
```

应用还在 BDA image 中直接内嵌四个通用 shell VX 资源：

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

`HeiSeTuPian` 资源名与其他普通应用一致，很可能表示黑色/暗色图片变体，而不是
独立可执行模块。

## API 使用概览

当前间接调用扫描共发现 304 个运行时表调用：

```text
FS  +0x000   4  fopen 类
FS  +0x004   6  fclose 类
FS  +0x008   6  fread 类
FS  +0x00c   1  fwrite 类
FS  +0x010   3  fseek 类
FS  +0x02c   1  目录存在检查/chdir 类
FS  +0x030   1  mkdir 类
FS  +0x048   1  磁盘信息类

GUI +0x030/+0x050/+0x054  事件 poll/step/dispatch
GUI +0x084/+0x088/+0x08c/+0x17c  frame 生命周期
GUI +0x1a4/+0x1a8  控件/window 创建和销毁
GUI +0x308/+0x30c  begin/end draw
GUI +0x338/+0x33c/+0x378/+0x4f0  文字模式、颜色、文字绘制
GUI +0x430/+0x46c  rect prepare / rect contains 调用对
GUI +0x35c/+0x40c  图片/区域辅助族

SYS +0x080  22  delay/sleep 类
RES +0x090   2  资源状态辅助类
RES +0x094   5  trace/log 类
MEM +0x008/+0x00c allocation/free 类
```

## 窗口和事件流程

`课程表.bda` 使用正常应用事件 pump：

```text
GUI+0x030(message, frame_or_context)
GUI+0x050()
GUI+0x054(message)
...
GUI+0x17c(frame)
```

这与 Element、BBVM、时间、记事本等完整应用一致。只在启动阶段做一次绘制的
自定义显示程序缺少这个生命周期，因此当前 Showcase 实验只能在很窄的
Element 风格场景中显示，复杂变体会无法关闭或重启。

应用至少通过 `GUI+0x1a4` 创建一个 GUI 对象。调用形态与现有
create-window/control ABI 一致：

```text
a0 = class/name pointer
a1 = title/caption 或 0
a2 = style，已见高位属于 0x08000000 家族
a3 = flags/extra，常为 0
stack fields = id, x, y, width, height, parent, extra
```

## 绘制行为

绘制路径组合：

```text
GUI+0x308 / GUI+0x30c       drawing handle 生命周期
GUI+0x074                  draw/present guard
GUI+0x430                  rect prepare；写 x0/y0/x1/y1
GUI+0x46c                  rect contains；判断点是否在 rect 内
GUI+0x4f0                  文字绘制类
```

`GUI+0x430` 使用栈上记录写入 `x0/y0/x1/y1` rect。多处 `GUI+0x46c`
紧跟这些记录调用，且 `a1/a2` 来自计算坐标。C200 已确认 `GUI+0x46c`
等价于 `rect[0] <= x && x < rect[2] && rect[1] <= y && y < rect[3]`；
因此这里应解释为内容 UI 的 hit-test/rect 判断，而不是资源/图片绘制 API 或
通用 DLX loader。

## 文件流程

FS 模式标准：

```text
用 "rb" 打开 DLX 或数据文件
读取固定记录
按需 seek
用 "wb+" 写入/更新
关闭 handle
通过 FS+0x02c / FS+0x030 准备应用数据目录
```

没有证据表明 `RES+0x094` 会加载这些 DLX 文件。硬件探针显示 `RES+0x094`
传路径风格字符串会返回但没有可见资源效果；而该应用明确使用 FS 调用处理资源/
数据路径。

## 对 SDK 的含义

1. Showcase 风格自定义应用应使用完整 frame/control 事件生命周期，而不是只走
   一次性 `GUI+0x540` 图片绘制路径。
2. `GUI+0x430` 已可按 rect prepare 使用；调用方必须提供至少 16 byte 可写 rect。
3. `GUI+0x46c` 已可按 rect contains 使用；课程表为电子图书之外提供了更多
   内容 UI hit-test 证据。
4. `RES+0x094` 应保持 trace/log 类命名。

## 未确认点

1. `GUI+0x430/+0x46c` 周围的高层 UI record 与资源索引关系。
2. `GUI+0x1a4` 调用使用的准确 object/class 字符串。
3. 课程表持久数据文件格式。
4. 黑色图片 DLX 是按主题、显示模式，还是资源回退路径选择。
