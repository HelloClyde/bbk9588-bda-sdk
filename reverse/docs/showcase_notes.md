# Showcase / Element 风格显示实验记录

本文记录基于 `元素周期表.bda` 的显示类应用实验。

## 已确认基线

`DLXImageElementStyle_Rebuild.bda` 由
`reverse/examples/dlx_image_element_style_probe.c` 重建，仍然可以通过
Element 风格路径显示 VX image：

```text
FS fopen/read DLX -> keep full VX resource block -> GUI+0x540(draw, x, y, w, h, vx)
```

该构建可以显示 image，但没有系统管理的 window title bar，目前还不能干净退出。

真机更新：

```text
DLXImageElementStyle_Rebuild.bda  显示 image，无 window title bar，不能关闭
ShowcaseDisplayOnly.bda           立即重启
ShowcaseDemo.bda                  立即重启
```

因此问题不在 header/category/build 路径。已知可用基线和失败的 Showcase 构建
使用相同模板和 patch point，差异主要在 resource source 和 lifecycle 逻辑。

从 `reverse/reports/schedule_bda_report.md` 和
`reverse/reports/ninecourse_bda_report.md` 交叉检查可见：内置显示/内容类应用
不是启动后直接画一张 bitmap，而是创建/注册 GUI object、运行正常 event pump，并从 callback 或
对象持有的 draw handle 绘制。九科还使用 `GUI+0x1ac/+0x1b0` 对象更新调用。
因此当前 Showcase 失败更像生命周期/对象模型不匹配，而不是 BDA header 或 DLX
解析问题。

## Showcase 回归

`ShowcaseDisplayOnly.bda` 和 `ShowcaseDemo.bda` 最初在显示图片前重启。当前最强
解释是文件打开错误处理：

```c
f = bda_fs_fopen_raw(path, "rb");
if (!f) ...
```

这种写法不安全。有效 FS handle 是高地址 pointer，signed 值通常为负数；失败哨兵为
`0` 或 `0xffffffff`。wrapper/probe code 必须检查：

```c
if (!bda_fs_file_is_valid(f)) {
    return -1;
}
```

这是所有文件打开代码都需要遵守的 SDK 修正，不只适用于 Showcase。

后续 Showcase 构建已经使用 `bda_fs_file_is_valid(f)`，所以剩余重启大概率发生在打开文件之后或更
后面的阶段。为此增加了分阶段探测：

```text
build/ShowcaseStage1Load.bda   打开系统 text_A.dlx，读取 VX，然后退出
build/ShowcaseStage2Frame.bda  stage 1 + 注册 frame
build/ShowcaseStage3Draw.bda   stage 2 + 执行一次 GUI+0x540 绘制
```

三者都使用 Element 模板和已知系统 `text_A.dlx` 资源，不使用 custom 320x240
`ShowcaseDemo.dlx`。这样可以隔离失败点：

```text
Stage1 失败  -> file/DLX/VX 读取路径仍然错误
Stage2 失败  -> frame descriptor/register 路径错误
Stage3 失败  -> draw handle 或 GUI+0x540 调用时机错误
全部通过     -> Showcase 重启更可能来自 custom DLX 尺寸/路径或 event loop 逻辑
```

真机更新：

```text
ShowcaseStage1Load.bda:
  点击应用
  显示 "open text_A"
  显示 "open failed"
  正常退出
```

这证明 Stage1 失败来自 `FS+0x000` 路径形式，不是 header 问题，也不是 DLX 解析
崩溃。原始 Stage1 路径是完整 GBK 路径 `A:\应用\数据\shell\text_A.dlx`。随后
增加路径矩阵探测，用来测试真机原生 FS 实际接受的路径写法。

新增无模板探测：

```text
build/TextAPathMatrix.bda
  尝试 text_A.dlx 的八种路径写法，并报告原始 fopen handle

build/ShowcaseStage1LoadMulti.bda
  尝试同一组路径写法，只要有任一路径打开成功就读取 DLX/VX

build/ShowcaseStage2FrameMulti.bda
  Stage1Multi + 注册 frame

build/ShowcaseStage3DrawMulti.bda
  Stage2Multi + 执行一次 GUI+0x540 绘制
```

对 `TextAPathMatrix.bda` / `TextAPathClassify.bda` 来说，`00000000` 和
`FFFFFFFF` 是失败。其他非零值即使最高位为 1、按有符号数看起来是负数，也可能是
valid handle。

`TextAPathClassify.bda` 真机结果：

```text
0: OK 80A8CFF0
1: OK 80A8D048
2: OK 80A8D0A0
3: ZERO 00000000
4: ZERO 00000000
5: ZERO 00000000
6: ZERO 00000000
7: ZERO 00000000
```

该结果修正了 Stage loader bug：旧代码用有符号 `f > 0` 判断成功，导致把
`0x80xxxxxx` handle 当成失败。`ShowcaseStage1LoadMulti.bda`、
`ShowcaseStage2FrameMulti.bda` 和 `ShowcaseStage3DrawMulti.bda` 已重建为接受除
`0` 和 `0xffffffff` 之外的任意 handle。

修复后的真机结果：

```text
Stage1Mu:
  open text_A -> open ok path 0 -> load ok -> 正常退出

Stage2Mu:
  open text_A -> open ok path 0 -> load ok -> register frame
  屏幕变白，frame ok，对话框消失，不能退出

Stage3Mu:
  open text_A -> open ok path 0 -> load ok -> register frame
  屏幕变白，frame ok，对话框消失，随后崩溃/重启
```

解释：

```text
Stage1 证明 DLX 路径/解析/VX 提取正确。
Stage2 证明 frame 注册成功，但没有 event loop 或 GUI+0x17c 清理时直接返回，会把 shell 留在被接管的白色 frame 状态。
Stage3 从 mainline 绘制后释放 VX/返回，而 frame 仍可能接收 callback；这种 lifecycle 不匹配可以解释崩溃。
```

后续探测：

```text
build/ShowcaseStage2Close.bda  注册 frame 后立即调用 GUI+0x17c
build/ShowcaseStage3Loop.bda   在 callback 中保存绘制状态，并运行有界 event loop
```

真机结果：

```text
ShowcaseStage2Close.bda:
  frame/image 显示成功，但 GUI+0x17c 不能干净关闭/返回。

ShowcaseStage3Loop.bda:
image 显示，随后应用在显示阶段后崩溃/重启。
```

这确认 image 路径本身可用。剩余问题是 frame ownership 和清理。已构建两个更窄的 probe：

```text
build/ShowcaseStage2StopRel.bda  使用 BBVM 观察到的 GUI+0x088 再 GUI+0x04c 清理
build/ShowcaseStage3Hold.bda     通过 event loop 显示，但故意跳过 frame/VX 清理
```

## 与 Element 窗口生命周期的差异

Element 不依赖系统绘制的 title bar。它从 DLX resource 绘制自己的 UI，并在 window proc
中处理 touch hot zone。关闭/返回动作会发送类似 command 的 message，例如 `0x66`/`0x7fd`，然后
让 GUI event loop 和默认 proc 自然推进。

已知稳定的 Element 循环：

```c
while (GUI+0x030(msg, 0)) {
    GUI+0x050(message_buffer);
    GUI+0x054(msg);
}
GUI+0x17c(frame);
```

不要假设在 window proc 内设置本地 `g_exit` 等同于 Element 的关闭路径。GUI 分发
仍在活动时强行退出，可能破坏 lifecycle。

## Message 命名修正

`0x00b1` 不是通用 touch-exit 消息。在 Element 中，它表现得更像输入/重绘触发。
old SDK name `BDA_MSG_TOUCH_B_LIKE` 已删除；新代码使用
`BDA_MSG_REDRAW_INPUT_LIKE`。

## 当前测试构建

```text
build/DLXImageElementStyle_Rebuild.bda  已知显示基线
build/ShowcaseFallbackOnly.bda          display-only，强制使用系统 text_A.dlx
build/ShowcaseDisplayOnly.bda           display-only，先试 ShowcaseDemo.dlx 再 fallback
build/ShowcaseDemo.bda                  显示 + 实验性关闭处理
build/ShowcaseDemo.dlx                  custom VX resource container
build/ShowcaseStage1Load.bda            分阶段诊断：仅 load
build/ShowcaseStage2Frame.bda           分阶段诊断：load + frame
build/ShowcaseStage3Draw.bda            分阶段诊断：load + frame + draw once
build/TextAPathMatrix.bda               无模板 text_A.dlx 路径形式矩阵
build/TextAPathClassify.bda             更清晰的路径矩阵：OK/ZERO/NEG1 标签
build/ShowcaseStage1LoadMulti.bda       带路径 fallback 的无模板 Stage1
build/ShowcaseStage2FrameMulti.bda      带路径 fallback 的无模板 Stage2
build/ShowcaseStage3DrawMulti.bda       带路径 fallback 的无模板 Stage3
```
