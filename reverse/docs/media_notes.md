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

详见 `reverse/reports/recorder_bda_report.md`。C200 和 `情景会话.bda` 的交叉
证据已经把早期的“媒体调用簇”收敛为 10-slot system resource/session manager：

```text
SYS +0x000  descriptor-driven session open
SYS +0x004  session close/backend close callback
SYS +0x014  open 后状态/参数初始化
SYS +0x020  stop/deactivate-like 状态迁移
SYS +0x02c  session status query
```

录音 descriptor 固定为 24 byte；两个原厂应用都使用 `type=5`、`flags=2`、
输出 WAV 路径、`0x1f40`、callback、0。C200 的 type-5 backend 会以 `wb` 创建文件，
通过 AIC/DMA 接收 0x1000-byte PCM block，在 0x4000-byte 缓冲中聚合，并在 close
时回写 RIFF/WAVE header。实际格式为 PCM、mono、16-bit、16000 Hz；descriptor
`+0x0c` 虽由应用写成 8000，但固件会改写为 16000，不能把该字段先命名成可配置
sample rate。

正常停止顺序是 `SYS+0x020(session)` 后接 `SYS+0x004(session)`。后者才调用
type-5 close callback、写出尾部 PCM、修正 WAV 长度并释放 backend state。该路径
应和 `GAMEBOY.BDA` 的 raw sample streaming 播放 API 分开看待。

### Firmware-private PCM capture

继续下钻 type-5 worker 后确认固件内部支持边录边读：

```text
0x80194900(16000, 16, 1)  capture open
0x80194ddc()               capture completed-buffer ready
0x80193e94(buffer, bytes) blocking PCM read
SYS+0x0a0                  capture/playback stop path
```

原厂录音循环每次读取 `0x1000` byte，再交给 type-5 WAV sink。PCM read 不在 SYS
table 中，V1 研究头通过 `SYS+0x06c target + 0x2ac`、
`SYS+0x074 target + 0x38` 和 `SYS+0x078 target - 0x48c` 相对定位，并检查函数
MIPS prologue 签名。open/ready/read 关系已在本地 `C200.bin`、`kj409588.bin`
交叉确认，read delta 也在 `4720knl.bin` 一致，但真机 V1 已证明这些相对布局不能
直接推广到另一版量产固件。

真机 V1 中 `ready=0x8019A088` 的两条签名完全匹配；`read=0x80199294` 读到的是
预期 read prologue 的第二、第三条指令，真实入口高概率为 `0x80199290`；
`open=0x80199D7C` 的指令则与本地精确签名不同。签名保护正确返回
`RESULT=UNSUPPORTED`，没有启动录音硬件。不能仅把真机看到的新两个 word 直接放宽
成可调用签名，因为 open 候选可能落在函数内部。

V2 改用受限结构解析：在 ready 前 `0x800` byte 范围内寻找唯一的
`stack-frame entry -> sll a1,24 -> sll a2,24` 候选；在 read guess 前后
`0x20` byte 内寻找唯一完整 read prologue。真机确认 read 入口为 `0x80199290`，ready
仍精确匹配 `0x8019A088`。但是 open 解析结果 `0x80199AD0` 恰好等于
`SYS+0x06c` 的 raw playback open 入口，不是 capture open。V2 实际初始化了播放路径，
所以 capture-ready 在 200 tick 后超时；stop 和文件 close 均正常返回。

当前 V2 已增加硬保护：open 候选等于 `SYS+0x06c` 时直接返回
`RESULT=UNSUPPORTED`，不再调用音频硬件。V3 只读扫描 playback-open 到 ready 之间的
stack-frame prologue、候选代码窗口和 `jr ra` 边界，输出 `RESULT=MAP_ONLY`；它不调用
open、ready、read 或 stop。

V3 真机确认旧 guess 所在函数的完整边界为 `0x80199D4C..0x80199F04`，
`0x80199D7C` 位于函数内 `+0x30`。该入口在第一次下游调用前没有保存传入的
`a0/a1/a2`，随后覆盖参数寄存器，因此 V4 按无参数函数调用，并使用前 6 个 word、
返回点、下一个函数 prologue、ready 和 read prologue 做精确联合保护。

V4 中 `0x80199D4C` 安全返回，但 capture-ready 等待 200 个 tick 后仍为零。这证明
该函数单独调用不足以启动采集，不能继续命名为 capture-open；它可能只是拆分后的
DMA/队列初始化阶段，也可能属于另一条音频路径。V5 因此恢复为纯只读探针：导出
`0x80199E0C..0x8019A088` 的剩余函数体，并扫描 system manager 到 audio driver
区间内对 init/config/ready/read 候选的直接 `jal` 调用点和调用者 prologue。

V5 真机调用图确认原厂无参数 init wrapper 为 `0x8018EDAC`，另有
`0x8018EE00(value) -> 0x80199F08(3, value)`。后续用匹配真机的 `C200knl.bin`
跳转表复核发现，op 0 才是 `8000..48000` 采样率；op 3 把值限制到 100 并写 codec
gain。`0x8018EE00` 自身还会先限制到 `0..127`，所以 V6 传入 16000 实际变成满增益，
并没有再次设置采样率。

V6 真机中 init 和 gain config 均返回 0，但 ready 仍在 200 tick 后超时，
`RECPCM6.RAW` 没有有效 PCM。V7
恢复为纯只读探针，动态定位上述包装器后导出 PCM worker 和 record-control 区的
完整直接/间接调用图，重点寻找 config 后的 start/enable、DMA 挂接或 worker 注册。
V7 因把旧 read guess 当作真实入口检查而在扫描前安全拒绝；V8 修正为检查
`0x80199290` 的完整 prologue。两版都不调用任何音频函数，V8 正常完成时固定输出
`RESULT=MAP_ONLY`。

V9 完整 worker 代码推翻了 V8 的启动候选判断：`0x8018D428` 调用的
`0x8018EDCC` 固定返回 0，随后必然跳到 `0x8018D5A8`；包含
`0x8018EDD4 -> 0x8019B8AC -> 0x8019B900` 的分支在这版固件中不可达。
`0x80199720` 的参数和状态访问也表明它是 playback buffer/length 路径，不是无参数
capture start。活动路径在首次 ready 前调用 `0x8019577C`、`0x801957E0`，然后再次
调用 `0x8019577C`，更像通用同步或等待原语。

V9 对每个状态命中实时写入完整代码窗口，在 1118 行后仍未结束；V10 改为单行记录
后完成了全部 86 个引用。`0x8058D530` 由 read `0x80199290` 读取并递减，init
`0x80199D4C` 清零；`0x8019A5A0` 是另一处读取并写回该计数的回调候选，同时访问
`D520/D524/D540`。V11 真机确认 `0x8019A5A0` 在 `0x80199D4C` 内作为函数指针
传给 `0x8019C504`；后者配置 DMA 通道并注册 IRQ callback。两个等待包装器各有大量
调用者，属于通用同步原语，不是 capture start。

V11 的指令还与 `系统/数据/C200knl.bin` 在 load base `0x80004000`、文件头
`0x40` 后逐字匹配。直接反汇编 read `0x80199290` 后确认：当 completed queue
`D530` 为空时，read 会从 free queue `D520/D524` 取 buffer，调用 `0x8019C390`
启动 DMA，然后等待 `0x8019A5A0` 回调。也就是说第一次 read 本身负责 prime DMA；
ready 只查看已经完成的 block，不能放在第一次 read 前作为门控。V12 因而改为
`init -> blocking read`，并用采集专用 `0x80199A6C` 停止。

V12 真机完整读取 4 个 `0x1000` byte block，全部返回 4096，产生连续的 16384-byte
PCM。四块耗时分别为 9、4、3、3 个 25-ms tick；8192 个 signed 16-bit sample 全部
非零，跨 block 边界差值仅为 -1、-12、+16。capture-specific stop 与文件关闭均
正常返回，结果为 `PASS`。V13 继续验证 `0x400` byte block（理论 32 ms）以及同一
BDA 内 stop 后再次 init/read/stop；完成前公开 API 仍只允许 4096-byte block。

V12 已定位并验证完整的 `init -> blocking read -> capture-specific stop` 序列。
公开 `bda_audio.h` 只在系统表目标地址和三处机器码均匹配已验证 C200knl profile 时
开放该路径；未知固件返回 `BDA_AUDIO_CAPTURE_UNSUPPORTED`。读取会阻塞等待 DMA
block，当前只允许 4096-byte block，不能在 wndproc 中直接调用，也不能在签名检查
失败时继续跳转。公开波形示例把 read 放在主循环中，并已真机确认 128-block 录制、
实时波形、日志和 ESC 返回。

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
`0x80195db0`、`0x80195db8`、`0x80195170`。模拟器后端在调用后仍报告 AIC timer
active，但真机 V4 已确认它能停止声音并安全返回菜单；原厂 `GAMEBOY.BDA` 也在调用
该表项后直接返回。

模拟器 V4/V5 曾额外直调内部 `0x80195b24(0)` 清 AIC 状态。真机 V3 在这一步死锁，
证明该固定地址 MMIO helper 不是 BDA ABI。公开头 `sdk/include/bda_audio.h` 的
`bda_audio_stop()` 因此只调用 `SYS+0x0a0`；open/ready/write/attenuation/stop 已完成
真机闭环。不要把 raw PCM 接口套用到飞天音乐/数码录音的 high-level 播放器后端。

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
