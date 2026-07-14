# 九宫格.bda 逆向报告

`九宫格.bda` 是内置分类 `0x04` 益智游戏。它使用与 `Eros方块.bda`、
`连连看.bda`、`黑白子.bda` 相同的原生游戏 shell，但文件和内存活动稍重。

## 头部和布局

```text
文件大小         102028 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS 范围         0x81c0f8b0..0x81c0fda1
```

运行时表全局变量：

```text
RES  0x81c0f8b0
GUI  0x81c0f8b4
SYS  0x81c0f8b8
FS   0x81c0f8bc
MEM  0x81c0f8c0
```

## 外部文件

相关字符串：

```text
\SdData.dat
\GamSdSave.Sav
\SysPet.yzj
rb
wb
wb+
rbf
a:\
```

`\SdData.dat` 和 `\GamSdSave.Sav` 是应用专用数据/存档文件。这里同时出现
`wb+` 和 `rb` 路径，解释了它比更小游戏拥有更多 FS 调用。

## 内嵌 VX 资源

应用内嵌相同的四个通用 VX 资源：

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

当前扫描没有发现外部 `.dlx` 包字符串。

## API 使用概览

原始调用扫描共有 227 个间接调用。

重要调用族：

```text
FS +0x000   8 次
FS +0x004  10 次
FS +0x008   4 次
FS +0x00c   5 次
FS +0x010   6 次
FS +0x014   2 次

GUI +0x074/+0x0e0/+0x2fc/+0x35c/+0x40c/+0x414/+0x418
MEM +0x008/+0x00c
RES +0x090/+0x094
```

GUI 调用形态匹配通用游戏 shell。额外 FS/MEM 流量更像关卡/存档数据处理，而不是
另一套应用框架。

## 当前解释

`九宫格.bda` 强化了共享 shell 结论，并提供第二种存档文件模式：

```text
1. shell 视觉资源直接嵌入 BDA
2. 应用专用数据/存档文件使用普通 FS 表
3. 应用路径中没有通用 DLX loader 证据
4. GUI 渲染辅助调用簇与其他小游戏一致
```

后续价值：检查 `\SdData.dat` 与 `\GamSdSave.Sav` 附近调用点，区分关卡数据加载
和存档/高分记录。
