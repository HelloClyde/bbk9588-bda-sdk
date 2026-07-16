# 三国霸业.bda 逆向报告

`三国霸业.bda` 是内置分类 `0x04` 游戏。它与其他游戏共享原生游戏 shell 和
内嵌 VX 头部资源，但外部 `\sango.lib` 包没有通过 `SYS+0x040..0x068` 打包
音效调用簇处理，而是由应用代码通过 FS 和 MEM 辅助自行解析。

## 头部和布局

```text
文件大小         214700 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS 范围         0x81c2b0d0..0x81c2ba71
```

运行时表全局变量：

```text
RES  0x81c2b0d0
GUI  0x81c2b0d4
SYS  0x81c2b0d8
FS   0x81c2b0dc
MEM  0x81c2b0e0
```

## 外部文件

相关字符串：

```text
\sango.lib
rbf
```

`0x81c13d80` 附近的字符串交叉引用会在栈缓冲中构造路径，通过 FS wrapper
打开文件、seek 到末尾、取得文件大小、分配内存，并把数据读回应用自有缓冲区。
后续代码会重新打开编号或派生出的包条目，把固定大小片段复制到多个 BSS 结构。

与 `雷霆战机.bda` 和 `决战坦克.bda` 不同，原始扫描中没有
`SYS+0x040..0x068` 调用。因此 `\sango.lib` 属于另一类游戏数据包，当前不能
作为打包音效系统 API 的证据。

## 内嵌 VX 资源

应用内嵌相同的四个通用小游戏 shell VX 资源：

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

## API 使用概览

原始调用扫描共有 176 个间接调用：

```text
FS +0x000/+0x004/+0x008/+0x00c/+0x010/+0x014  包 I/O
FS +0x018/+0x01c/+0x020/+0x028                 额外 stdio 类辅助
FS +0x030                                      mkdir 类辅助
FS +0x068                                      内部 file-object block read helper，不公开 SDK wrapper
FS +0x06c                                      stat/access 类辅助

GUI +0x030/+0x050/+0x054  事件循环
GUI +0x084/+0x088/+0x08c/+0x17c  frame 生命周期
GUI +0x074  高频 pump/present/update 类调用
GUI +0x2fc/+0x35c/+0x40c/+0x414/+0x418  渲染辅助族
GUI +0x3f8/+0x400  framebuffer/区域 blit 调用对

MEM +0x008/+0x00c  allocation/free
RES +0x094         trace/log 类辅助
```

`0x81c1653c`、`0x81c16754`、`0x81c16884`、`0x81c16b20` 附近的 FS 上下文会
反复构造小编号路径、打开包条目、读取记录，并复制到全局变量。这更像剧情、
存档或资源状态，而不是通用系统 loader。

## 当前解释

`三国霸业.bda` 的价值在于它是一个反例：

```text
1. 不是每个游戏 .lib 文件都表示 SYS 打包音效
2. 它确认了没有音效调用簇时仍可使用通用游戏 GUI/VX shell
3. 它展示了另一种基于普通 FS/MEM 调用的应用私有包格式
4. 它展示了内部 file-object block read helper 与 stat/access 类辅助会在私有包解析中相邻出现
```

对 SDK 的实际含义：应暴露并记录 FS/MEM 原语；在包头和 chunk 表映射清楚前，
把 `sango.lib` 视为应用私有包格式。`FS+0x068` 不是 public stat/access API，
也不是普通存档 API；C200 已确认它读取内部 file object/descriptor，普通开发继续
使用 `fopen/fread/fclose` 或 `bda_fs_read_bytes_raw()` 路径。
