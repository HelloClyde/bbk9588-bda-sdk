# 媒体和图片 API 笔记

本文来自原机原生 BDA 样本。它是硬件实验地图，不是最终 API 名称清单。凡是
没有在 `bda_sdk.h` 中稳定暴露、或仍带 `_LIKE` 的接口，都需要继续用 C200、
原机调用点和真机/emu probe 交叉确认。

## 音频

`应用\程序\飞天音乐.bda` 是原生 MP3/WAV/WMA 播放器 UI。

相关字符串：

```text
mp3;wav;wma;blm
\shell\mp3_liba.dlx
\shell\mp3_libc.dlx
\shell\mp3_libb.dlx
\shell\mp3_lyric_help.dlx
KEYDOWN PLAY_STOP
KEYDOWN PLAY_PAUSE
KEYDOWN PLAY_PLAY
```

该应用中的高频间接调用 offset：

```text
RES +0x094  trace/log-like，高频使用
GUI +0x040  send/message-like
SYS +0x004, +0x020  反复出现的媒体后端调用对
SYS +0x02c, +0x034, +0x038, +0x094  媒体播放器后端候选
GUI +0x4f0, +0x378, +0x2fc, +0x338, +0x308, +0x30c, +0x33c  UI/文字 helper
```

详见 `reverse/reports/music_bda_report.md`。

重要修正：硬件 `RES094TraceProbe` 和 `RES094PathProbe` 显示 `RES+0x094`
不是 DLX loader。它在 `飞天音乐.bda` 中的高频使用更可能是 debug/trace logging。

`应用\程序\数码录音.bda` 包含录音/播放逻辑。

相关字符串：

```text
*.wav
\shell\record_A.dlx
\shell\record_B.dlx
recorder
Rec%5.5d.wav
```

详见 `reverse/reports/recorder_bda_report.md`。录音应用和音乐播放器共享早期
SYS 媒体后端调用簇：

```text
SYS +0x004  28 次
SYS +0x020  25 次
SYS +0x02c  13 次
```

这进一步说明 `SYS+0x004/+0x020/+0x02c` 更像播放器/录音器使用的 high-level 媒体后端。
它应和 `GAMEBOY.BDA` 的 raw sample streaming 路径分开看待。

### Raw audio 状态操作

`GAMEBOY.BDA` 使用更 low-level 的采样流路径。研究头保留原始表入口：

```c
void bda_sys_audio_open_like(u32 device, u32 format, u32 channels);
int bda_sys_audio_ready_like(void);
int bda_sys_audio_write_like(const void *buffer, bda_size_t bytes);
void bda_sys_audio_reset_like(void);
void *bda_sys_audio_state_like(void);
void bda_sys_audio_flush_like(void);
```

C200 function-level evidence：

```text
SYS+0x06c -> 0x80194654  raw audio open/init
SYS+0x074 -> 0x80194da4  ready，返回 0x8058+0x6e8 > 0
SYS+0x078 -> 0x80194320  write buffer/bytes
SYS+0x08c -> 0x8001dc04  reset/init
SYS+0x090 -> 0x8001dad4  state pointer getter
SYS+0x0a0 -> 0x801891e8  flush/drain
```

`SYS+0x06c` 会初始化 DMA/audio MMIO 和 `0x8058` 附近的 queue state；只读取
`a0=device`、`a1=format`、`a2=channels`，其中 `a1/a2` 会被截成 signed 8-bit。
当前切片没有看到 `a3` 被读取，函数尾部固定 `v0=0`，因此 SDK wrapper 是
`void`。`SYS+0x078` 把 `a0` 当 sample buffer、`a1` 当 byte count，
`bytes <= 0` 返回 `-1`，正常路径按最大 `0x8000` byte chunk 写入 queue，
return value 是已消费 byte 数。
`SYS+0x074` 可按 `0/1` ready bool 使用。

`SYS+0x090` 是只读 probe 用的 state pointer getter。C200 entry 不读取参数，
直接返回固件全局结构 `0x80362830`。它不是 `open`、不是 high-level 播放器对象，
也不保证结构字段对 SDK 开发者稳定；需要调试 raw audio 生命周期时只能读取，不要写入。

`SYS+0x094 -> 0x8001dae0` 是相邻的 raw audio state 写入 helper。它读取调用者
传入的 state pointer，把 `state+0x00/+0x04`、`state+0x08` 起的一段状态以及
`state+0x210..+0x221` 复制到 `0x80362830` 全局 state，并清 `0x804781b4`。
SDK 不公开这个 wrapper；不要把它当成 high-level audio state setter 或恢复 API。

C200 table entry 确认 `SYS+0x08c -> 0x8001dc04`，wrapper 不读取调用参数；它会取全局 audio
object，调用内部关闭/释放 helper，把全局 pointer 清零，再进入初始化路径。SDK 因此
按无参数 `void bda_sys_audio_reset_like(void)` 暴露，不假设 return value 有效。

`SYS+0x0a0 -> 0x801891e8` 同样是无参数 wrapper，内部连续调用
`0x80195db0`、`0x80195db8`、`0x80195170`。V3 动态证明它不会清除 AIC replay/global
enable：DMA queue 不再 rearm 后仍持续产生 underrun。因此研究头按
`void bda_sys_audio_flush_like(void)` 暴露，但不能单独当作 stop。

V4/V5 已确认当前 C200 的完整停止顺序是 `SYS+0x0a0` 后调用内部 AIC reset
`0x80195b24(0)`；后者没有 system table entry。公开头 `sdk/include/bda_audio.h`
将两步封装为 `bda_audio_stop()`，并提供已验证的 `bda_audio_open_pcm()`、
`bda_audio_ready()` 和 `bda_audio_write()`。固定 VA 只适用于当前 kj409588/C200 固件；
不要把这组接口套用到飞天音乐/数码录音的 high-level 播放器后端。

### 游戏打包音效

原机游戏提供第三条音频路径：打包音效资源。当前证据来自：

- `reverse/reports/thunder_bda_report.md`
- `reverse/reports/tank_bda_report.md`
- `reverse/reports/sango_bda_report.md`

`雷霆战机.bda` 会打开 `\FlySound.lib`，构造 `0x20` byte chunk descriptor，
并使用：

```text
SYS +0x040/+0x044 attenuation，+0x050/+0x054 stub，+0x058/+0x05c/+0x060/+0x064/+0x068 package sound
```

`决战坦克.bda` 交叉验证了同一族调用：

```text
\TankSound.lib
descriptor stride 0x20
loop bound 0x14 chunks
SYS+0x044 读取当前 PCM attenuation
SYS+0x040 接收该值，或接收 0x75 - (index * 13)
```

C200 table entry 给出一个关键修正：`SYS+0x050` 和 `SYS+0x054` 当前都只是立即返回
`1` 的 stub，不能把它们单独当作已确认 loader/free API。真正有明显行为的
package sound wrapper 是 `SYS+0x058/+0x05c/+0x060/+0x064/+0x068`；它们会读写
`0x804c4ba4/0x804c4ba8` 一带的全局状态，或调用内部音频释放/状态函数。
`SYS+0x040/+0x044` 已由 `GameVolV1` 排除出 package sound 簇：它们分别设置 pending
PCM attenuation 和读取 effective attenuation。下一次 raw write 才应用 setter；
effective range 为 `0..96`、步进 3，数值越大越安静。
`SYS+0x024/+0x048/+0x04c` 在 C200 中也是 stub，不应命名为声音加载、兼容或
flush API。

`三国霸业.bda` 是反例：它引用 `\sango.lib`，但不使用 `SYS+0x040..0x068`；
该 `.lib` 更像应用私有包数据，由应用自己通过 FS/MEM 读取。

因此，打包音效簇不能直接推广成通用播放器 API。它应先保持
`BDA_SYS_PACKAGE_SOUND_*_LIKE` 这类保守命名；其中 `+0x050/+0x054` 尤其要按
不公开 stub 看待。

## 视频

`应用\程序\飞天影音_.bda` 内嵌 MPlayer/FFmpeg-style player runtime。相关字符串：

```text
avi;mp4;3gp
\player.bin
\player.cfg
Starting playback...
Open stream, file name:%s
MPlayer  (C) 2000-2005 MPlayer Team
```

这更像大型私有 player runtime，不像一个小型系统 API。实际 SDK 路线可能是启动或
复用 `player.bin`/配置，而不是调用一个简单 `play_video()` 函数。

`reverse/reports/video_bda_report.md` 对比了两个原机视频 BDA。两个变体都引用
`\player.bin` 和 `\player.cfg`，并包含大块未知间接调用簇。在这些调用和其他
应用或 `C200.bin` 交叉验证前，不要仅因 offset 在视频应用中很热就升格为公共
SDK wrapper。

## 图片

`应用\程序\我的相册.bda` 引用：

```text
LoaderPicture
LoaderPicture FileName = %s
*.bmp
*.jpg
bmp;jpg
```

`应用\程序\电子画板.bda` 也保存或加载：

```text
.jpg
.bmp
bmp;jpg
```

图片密集应用常见 GUI offset：

```text
+0x35c, +0x368, +0x40c, +0x410, +0x414, +0x418, +0x46c, +0x4f0
```

其中 `GUI+0x40c/+0x410/+0x414/+0x418` 已有 C200 级别参数边界：`+0x40c`
是五参数 region draw/copy，`+0x410` 是六参数 render/copy，`+0x414` 会读取
descriptor 和多个 stack 参数，`+0x418` 是双 context/双矩形 render helper。
这些仍是 low-level render helper，不等于可脱离 frame/control lifecycle 的 public
图片 API。

`电子图书.bda` 会在图片/资源流程里用 pointer-like 参数调用 `+0x46c`。这是
图片/资源绘制 helper 的候选，但具体签名仍需硬件测试。详见
`reverse/reports/ebook_bda_report.md`，其中有 `a1/a2` 从相邻资源记录 word
加载后传入 `GUI+0x46c` 的调用上下文。

更强的相册图片 pipeline 证据见：

- `reverse/reports/album_bda_report.md`
- `reverse/docs/picture_notes.md`

## SDK 实验 helper

`bda_sdk.h` 暴露了通用表调用，适合做受控 probe：

```c
bda_call0(table, offset);
bda_call1(table, offset, a0);
bda_call2(table, offset, a0, a1);
bda_call3(table, offset, a0, a1, a2);
bda_call4(table, offset, a0, a1, a2, a3);
```

历史说明：旧版 SDK 曾提供 `bda_load_dlx_*`，但这些 helper 实际调用
`RES+0x094`。后续对 `元素周期表.bda` 的分析显示，该 offset 会接收 printf
风格 trace 字符串。因此 `load_dlx` 名称是早期未确认猜测，不是已确认通用
DLX loader。详见 `element_bda_notes.md`。这些旧别名已经从 `bda_sdk.h` 删除。

真机 `RES094TraceProbe.bda` 结果：

```text
literal=00000000
gui_fmt=00000000
fs_fmt=00000000
res_tbl=80253E60
```

应用在三次调用后继续正常运行，这强烈支持 `RES+0x094` 是 trace/log 语义。

真机 `RES094PathProbe.bda` 又传入两个看起来像 DLX 路径的字符串：

```text
res=80253E60
gui=80253F90
path0=00000000
path1=00000000
```

这些调用同样正常返回 `0`，且没有可见加载行为。这基本排除了“路径字符串会触发
资源加载”的早期猜测。

当前只保留保守 trace wrapper：

```c
bda_res_entry_094_like(text_or_path, arg);
bda_res_trace_like(format, arg);
```
