# 飞天音乐.bda 逆向报告

## 状态

首版静态报告，重点是音频/媒体 SDK 证据。

证据：

```text
应用/程序/飞天音乐.bda
reverse/reports/music_layout.json
reverse/reports/music_calls.txt
sdk/doc/media_notes.md
sdk/doc/gameboy_notes.md
sdk/doc/system_bin_notes.md
```

## 头部和布局

```text
文件大小          150,900 bytes
菜单标题         飞天音乐
分类           0x08
入口文件偏移  0xa3b0
运行时入口 VA   0x81c00020
运行时文件基址  0x81bf5c70
头部 checksum    ok
```

缓存的运行时表全局变量：

```text
RES  0x81c1a9e0
GUI  0x81c1a9e4
SYS  0x81c1a9e8
FS   0x81c1a9ec
MEM  0x81c1a9f0
```

外部 DLX 引用：

```text
\shell\mp3_liba.dlx
\shell\mp3_libc.dlx
\shell\mp3_libb.dlx
\shell\mp3_lyric_help.dlx
```

入口偏移不同于常见的 `0x95f8` 模板，因此这是 builder/analyzer 的一个有用
布局反例。

## API 使用概览

`飞天音乐.bda` 包含 552 个已分类的运行时表间接调用：

```text
SYS +0x004  15 次
SYS +0x020  15 次
SYS +0x02c   5 次
SYS +0x034   4 次
SYS +0x038   4 次
SYS +0x094   3 次
SYS +0x000   1 次
SYS +0x00c   1 次
SYS +0x010   1 次
SYS +0x018   1 次
SYS +0x01c   1 次
SYS +0x040   1 次
SYS +0x080   1 次
SYS +0x090   1 次

FS  +0x000  14 次  open/fopen-like
FS  +0x004  14 次  close/fclose-like
FS  +0x00c  12 次  write/fwrite-like
FS  +0x008   7 次  read/fread-like
FS  +0x048   3 次  disk/storage info-like
FS  +0x07c   1 次   storage-ready-like

GUI +0x040  89 次  send/message-like
GUI +0x4f0  18 次  draw text-like
GUI +0x2fc  14 次  surface/object create-like
GUI +0x084   4 次  register frame

RES +0x094 110 次  trace/log-like
RES +0x090   1 次   resource state-like
```

## 音频和系统表解释

这个应用目前是研究低位 SYS 偏移 `+0x000..+0x040` 的最佳原机样本。这些偏移
与 GAMEBOY 中出现的后段音频流偏移
（`SYS+0x06c/+0x074/+0x078/+0x08c/+0x0a0`）不同。

当前解释：

- `飞天音乐` 可能使用更高层的封装音乐/播放器接口。
- `GAMEBOY.BDA` 使用更低层的原始音频流接口。
- 在参数上下文恢复前，SDK 应把这两组接口分开记录。

重复出现的调用对：

```text
SYS +0x004  15 次
SYS +0x020  15 次
```

说明播放器后端里可能存在 start/stop、open/close 或 state/update 调用对。
DLX 名称（`mp3_*`）可以证明媒体用途，但准确函数名尚未确认。

## 文件和 UI 行为

该应用把媒体设备调用和普通 FS 操作组合使用：

- 打开/读取音频或播放列表文件；
- 写入持久数据（`FS+0x00c` 有 12 次调用）；
- 检查磁盘信息和存储就绪状态；
- 通过 `GUI+0x4f0` 绘制歌词/帮助/状态文字。

`mp3_lyric_help.dlx` 加上 18 次文字绘制调用，说明歌词/帮助 UI 是原生 GUI
文字，而不只是位图资源。

## 交叉验证

- `GAMEBOY.BDA` 证实了使用后段 SYS 偏移的原始音频路径。
- `飞天音乐.bda` 证实了使用前段 SYS 偏移的另一条媒体播放器路径。
- `system_bin_notes.md` 包含音频设备和编解码器相关固件字符串；提取上下文后
  应用这些字符串为 SYS 偏移命名。
- `RES+0x094` 出现频繁，但硬件探针显示它更像 trace/log，不是 DLX loader。
  高调用次数可能来自音乐播放器的调试日志。

## 未确认点

1. SYS `+0x000..+0x040` 的准确名称和签名。
2. 播放器后端是在固件中解码 MP3，还是在应用代码中解码。
3. 播放列表/文件扩展名过滤规则。
4. `飞天音乐.bda` 与 `飞天影音.bda` 的关系。

## 后续静态任务

1. 提取 SYS `+0x004` 与 `+0x020` 调用对上下文。
2. 与 `飞天影音.bda`、`飞天影音_.bda` 对比，确认是否共享媒体后端。
3. 在系统二进制中搜索 MP3/player 函数附近字符串。
4. 在 SDK 中新增高层媒体播放器 SYS 调用小节，并与 GAMEBOY 原始音频流区分。

