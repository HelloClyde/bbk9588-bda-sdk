# 数码录音.bda 逆向报告

目标：`应用/程序/数码录音.bda`

证据：

- `reverse/reports/recorder_layout.json`
- `reverse/reports/recorder_calls.txt`
- `reverse/reports/recorder_sys_context.txt`
- `reverse/reports/recorder_fs_context.txt`
- `reverse/reports/recorder_media.txt`
- `reverse/reports/recorder_dlx.txt`

## 头部和布局

```text
菜单标题         数码录音
分类             0x08
文件大小         82364 bytes
入口文件偏移     0x95f8
运行时入口 VA    0x81c00020
运行时文件基址   0x81bf6a28
BSS/global 范围  0x81c0abe0..0x81e35731
checksum          inventory 中为 ok
```

BSS 范围远大于代码文件，符合录音/播放应用需要大缓冲区或后端状态的特征。

启动代码中检测到的运行时表全局变量：

```text
RES 0x81c0abe0
GUI 0x81c0abe4
SYS 0x81c0abe8
FS  0x81c0abec
MEM 0x81c0abf0
```

## 外部资源

该 BDA 引用两个 DLX 皮肤文件：

```text
\shell\record_A.dlx
\shell\record_B.dlx
```

两个文件都存在于 `应用/数据/shell`。`dlx_inspect.py` 识别它们为 variant-3
DLX 包，各有 18 个资源。每个资源都是 type 1，并可解码为 VX RGB565 图片。
重要尺寸包括：

```text
240x320 全屏背景
126x30  状态/按钮条
110x34  标签/按钮
47x50   控件
32x30 和 19x19 图标
45x3    进度线片段
```

按当前 DLX 检查结果，这个应用不需要非图片资源类型。

## 字符串和文件模型

相关字符串：

```text
*.wav
.wav
recorder
Rec%5.5d.wav
 play ====>>>%d,%d,%d
###g_RecorderFileName=%s###RecorderCurrPath=%s###
```

这些字符串说明：

- 文件列表过滤器是 `*.wav`。
- 自动生成的录音文件名形如 `Rec00000.wav`。
- 应用维护当前录音目录/路径全局变量。
- 播放路径带有诊断日志。

## API 使用概览

已分类间接调用：

```text
FS      40 次
GUI     58 次
SYS     77 次
MEM      5 次
RES     11 次
total  181 次
```

高频系统/媒体偏移：

```text
SYS +0x004  28
SYS +0x020  25
SYS +0x02c  13
SYS +0x040   2
SYS +0x08c   2
SYS +0x090   2
RES +0x094  11
```

`SYS+0x004/+0x020/+0x02c` 不是三个独立的录音函数。C200 表明它们和
`SYS+0x000` 共用一个最多 10 个 slot 的 system resource/session manager：

```text
SYS +0x000  descriptor-driven session open
SYS +0x004  session close，并调用对应 backend close callback
SYS +0x014  session 打开后的状态/参数初始化
SYS +0x020  stop/deactivate-like 状态迁移
SYS +0x02c  session status query
```

录音只是该 manager 的 `type=5` backend。它不同于 `GAMEBOY.BDA` 使用的
`SYS+0x06c/+0x074/+0x078/+0x0a0` raw PCM 播放路径。

`RES+0x094` 使用 11 次。硬件探针已经显示这个偏移更像 trace/log，而不是 DLX
加载器。录音应用中带格式占位符的字符串也符合这个解释。

## 录音会话描述符

`数码录音.bda` 在 `0x81c026d0..0x81c02720` 构造 24-byte descriptor，再调用
`SYS+0x000(&descriptor)`：

```text
offset  数码录音调用值       当前含义                         可信度
+0x00   5                    recording backend type          高
+0x04   2                    recording flags/mode            高（位语义未拆解）
+0x08   目标 .wav 完整路径    output path                     高
+0x0c   0x1f40 (8000)        backend parameter               低（不是最终采样率）
+0x10   0x81c01340           event callback                  高
+0x14   0                    callback user/aux data          中
```

返回值是 1..10 的 session id，失败为 0。应用把它保存到全局 `0x81c0ac6c`，
随后调用 `SYS+0x014(session_id, &word)`；该应用传入的 word 为 0。

`情景会话.bda` 在 `0x81c04e5c..0x81c04e8c` 独立构造了相同布局：
`type=5`、`flags=2`、WAV 路径、`0x1f40`、回调和 0。这个交叉样本确认 descriptor
不是录音应用的私有结构。情景会话传给 `SYS+0x014` 的 word 由应用状态计算，
所以该 word 的准确含义仍不能命名。

录音 callback `0x81c01340` 至少接收两个参数，并按 `a1` 事件码分支。它会使用
`RES+0x094` 输出日志，并在部分终止事件中清理 session。事件码枚举及 `a0` 的
准确含义尚未确认，不能先定义成公开 ABI。

## C200 type-5 录音后端

`SYS+0x000` 的 type-5 open callback 是 `0x801897f0`。该函数：

1. 检查存储状态和剩余空间。
2. 以 `wb` 打开 descriptor `+0x08` 指向的目标文件。
3. 先写入 `0x3c` byte 占位 WAV header。
4. 分配 `0x404c` byte backend state，其中 `0x4000` byte 用作 PCM 聚合缓冲。
5. 把录音格式初始化为 PCM、单声道、16-bit、16000 Hz。

值得注意的是，原 BDA 写入 descriptor `+0x0c` 的值是 8000，而 type-5 open
会把该字段改写为 `0x3e80`（16000）。因此 `+0x0c` 不能按“调用者可选采样率”
公开；至少当前固件后端会把录音格式固定为 16 kHz。

type-5 data callback `0x80189c78` 每次接收 `0x1000` byte PCM 数据，把它追加到
`0x4000` byte 缓冲；缓冲满后统一写文件。采集数据由固件 AIC/DMA 路径送入该
callback，BDA 不需要、也不应轮询麦克风寄存器或直接读取采样 buffer。

type-5 close callback `0x80189a9c` 会：

1. 写出最后不足 `0x4000` byte 的 PCM 数据。
2. 获取最终文件长度并 seek 回文件头。
3. 重写 RIFF/WAVE/fmt/data header 和长度字段。
4. 关闭文件并释放 `0x404c` byte backend state。

因此只退出窗口或只调用 raw audio stop 都不够；漏掉 session close 会留下未修正
长度的 WAV 文件和 backend 资源。

type-5 status callback `0x80189da8` 向 manager 复制内部状态；`SYS+0x02c` 再输出
一个 0x20-byte 公共状态块。原录音应用读取其中 `+0x0c`，但该字段的单位和准确
语义尚未完成交叉验证，研究代码应暂时按 raw word 处理。

## 生命周期

原厂两个录音样本支持下面的保守顺序：

```c
descriptor.type = 5;
descriptor.flags = 2;
descriptor.path = wav_path;
descriptor.parameter_0c = 8000; /* 固件会改写为 16000 */
descriptor.callback = record_callback;
descriptor.user_data = 0;

session_id = SYS_000(&descriptor);
if (session_id != 0) {
    SYS_014(session_id, &initial_word);
}

/* 运行期间可用 SYS_02c(session_id, &raw_status) 查询。 */

if (session_id != 0) {
    SYS_020(session_id); /* stop/deactivate-like */
    SYS_004(session_id); /* close，最终写回 WAV header */
    session_id = 0;
}
```

`SYS+0x020` 的精确 pause/stop 状态名仍未解决，但 `数码录音.bda` 和
`情景会话.bda` 都在正常 teardown 中紧接着执行 `+0x020`、`+0x004`，所以这对
调用顺序的可信度高。`SYS+0x004` 才是实际分派 type-5 close callback、完成 WAV
文件的步骤。

## 更底层的实时 PCM 采集

type-5 backend 并不是等录音结束后才获得声音。它的 worker 在
`0x80187848..0x801878bc` 循环执行：

```text
0x80193e94(pcm_buffer, 0x1000)  从录音 DMA 队列阻塞读取 PCM
0x80189c78(type5_slot, pcm_buffer, 0x1000)  追加到 WAV backend
```

`0x80193e94(buffer, bytes)` 是真正的流式 PCM read。它从 `0x80580748` 一带的
DMA completed-buffer queue 取出 buffer index，经 `0x8058066c` 的格式转换函数
把采样复制到调用者 buffer，并返回已读取字节数。队列为空时它使用固件 scheduler
等待，不是读取尚未完成的 WAV 文件。

录音硬件初始化函数是：

```c
0x80194900(16000, 16, 1); /* sample rate, bits, channels */
```

原录音 worker 固定使用 16000 Hz、16-bit、mono，并以 `0x1000` byte 为一个读取块；
每块约 128 ms。`0x80194900` 实际只使用前三个参数。停止仍可走 SYS 表稳定入口
`SYS+0x0a0`，其下游会调用 `0x80195170` 停止 AIC 采集状态。

这两个函数没有直接出现在 SYS table。为了避免完全写死 C200 绝对地址，研究头按
现有稳定播放入口相对定位：

```text
record open = address(SYS+0x06c) + 0x2ac
record ready = address(SYS+0x074) + 0x38
record read = address(SYS+0x078) - 0x48c
```

`C200.bin` 和 `kj409588.bin` 都保持这三个 delta；`4720knl.bin` 也保持 read delta。
研究 wrapper 在调用前检查目标函数开头两个 MIPS word，签名不匹配时禁止调用。
这是 firmware-private ABI，固件升级仍可能改变函数布局。公开 SDK 后来没有直接暴露
这些相对地址 wrapper，而是在 `bda_audio.h` 中加入精确 C200knl profile、系统表目标
地址和 init/read/stop 联合机器码检查；未知固件返回 `BDA_AUDIO_CAPTURE_UNSUPPORTED`。

下面是 V1 阶段的历史调用假设，后续 V2..V12 已证明 open 和首次 ready 门控均不正确，
不能作为当前开发示例：

```c
if (!bda_c200_record_stream_supported_like()) {
    /* firmware mismatch */
}

bda_c200_record_stream_open_like(16000, 16, 1);
while (running) {
    int got = bda_c200_record_stream_read_like(pcm, 0x1000);
    if (got == 0x1000) {
        consume_pcm_now(pcm, got);
    }
}
bda_c200_record_stream_stop_like();
```

`record_stream_read_like` 是阻塞调用。它适合独立采集循环；若直接放进 GUI wndproc，
会阻塞该窗口继续处理消息。小于 `0x1000` byte 的读取虽然函数结构允许，但原厂没有
这样调用，必须单独做真机延迟和停止测试。

`0x80194ddc()` 读取 capture completed queue count 并返回 bool。真机探针可先用
`bda_c200_record_stream_ready_like()` 做有限时轮询，再调用 blocking read，从而避免
麦克风或 DMA 没有启动时直接永久阻塞。

### 真机探针 V1

源码：`reverse/examples/record_stream_hardware_probe.c`

构建产物：`RecordStreamProbeV1.bda`，标题 `RecPcmV1`，工具分类 9。

探针先记录解析出的 open/ready/read 地址和各自两个 MIPS signature word。签名不符
时不启动硬件并返回 `RESULT=UNSUPPORTED`。签名通过后以 16000/16/1 启动采集，
对每个 block 先有限时等待 capture-ready，再读取 0x1000 byte。共读取 8 block，
逐块实时记录：

```text
GOT, POLLS, TICKS, MIN, MAX, PEAK, AVGABS, NZ, RAW
```

日志文件：`A:\应用\数据\游戏\RECPCM.TXT`

PCM 文件：`A:\应用\数据\游戏\RECPCM.RAW`

成功结果应包含 8 行 `GOT=4096`、`CAPTURE STOP RETURNED`、`RESULT=PASS`，PCM 文件
大小应为 32768 byte。RAW 格式为 16000-Hz、signed 16-bit little-endian、mono。
日志每行都重新 open/write/close，发生中途故障时仍能保留最后一个检查点。

真机 V1 实际安全退出为 `RESULT=UNSUPPORTED`：

```text
OPEN ADDRESS=0x80199D7C
READY ADDRESS=0x8019A088
READ ADDRESS=0x80199294
OPEN SIG0=0x3C070040
OPEN SIG1=0x24020019
READY SIG0=0x27BDFFE8
READY SIG1=0xAFBF0014
READ SIG0=0xAFBE0040
READ SIG1=0xAFB50034
SIGNATURE MISMATCH
RESULT=UNSUPPORTED
```

原始日志归档：
[`record_stream_v1_hardware_log.txt`](assets/record_stream_v1_hardware_log.txt)

这不是“真机没有实时录音”的证据。ready 精确匹配；read 的两个 word 表明 V1 guess
落在完整 prologue 后 4 byte，真实入口高概率是 `0x80199290`。open 的精确签名发生
变化，且当前两个 word 不足以证明 `0x80199D7C` 是函数入口。V1 因此正确地在任何硬件
调用前停止，没有启动录音硬件。

### 真机探针 V2

源码：`reverse/examples/record_stream_hardware_probe_v2.c`

构建产物：`build/RecordStreamProbeV2.bda`，标题 `RecPcmV2`，工具分类 9。

V2 不接受单纯替换后的两个真机 word。它在只读固件代码范围内解析结构候选：

1. ready 仍精确匹配 `0x27BDFFE8/0xAFBF0014`。
2. read guess 前后 `0x20` byte 必须只出现一个完整
   `0x27BDFFB8/0xAFBE0040` prologue。
3. ready 前 `0x800` byte 必须只出现一个 stack-frame entry，且后两条指令依次为
   `sll a1,a1,24`、`sll a2,a2,24`。

任一 match count 不是 1 时，V2 记录 open/read 代码窗口并返回
`RESULT=UNSUPPORTED`；只有全部通过才采集 8 个 4096-byte block。

日志：`A:\应用\数据\游戏\RECPCM2.TXT`

PCM：`A:\应用\数据\游戏\RECPCM2.RAW`

V2 BDA SHA-256：

```text
e168efa236c5ee9afe7816c9c3b78a5a68699f1e381bd165babb4ecfcb514649
```

该版本的真机日志已归档：
[`record_stream_v2_hardware_log.txt`](assets/record_stream_v2_hardware_log.txt)

V2 确认了两项有效信息：ready 入口及签名仍为
`0x8019A088: 0x27BDFFE8/0xAFBF0014`；read 的完整入口为 `0x80199290`，V1 的
`0x80199294` 确实偏移了 4 byte。

但 open 结构规则产生了危险的假阳性：唯一候选 `0x80199AD0` 恰好就是
`SYS+0x06c` 指向的 raw playback open。`CAPTURE OPEN RETURNED` 只证明播放初始化
返回，并不证明录音启动；随后 capture-ready 等待 200 tick 超时正符合这一结果。
探针最后的 stop 和文件 close 都返回，未留下已知音频状态或文件句柄。

V2 源码现已增加硬保护：候选等于 `SYS+0x06c` 时记录
`OPEN RESOLVED TO PLAYBACK ENTRY` 并返回 `RESULT=UNSUPPORTED`。上面的 SHA-256
仅标识已进行真机测试、但 open 解析规则已淘汰的历史构建。

### 只读映射探针 V3

源码：`reverse/examples/record_stream_hardware_probe_v3.c`

构建产物：`build/RecordStreamProbeV3.bda`，标题 `RecPcmV3`，工具分类 9。

V3 从 `SYS+0x06c` 的 playback-open 入口之后扫描到已确认的 capture-ready 入口，
记录所有 stack-frame prologue 的前 6 个 word、旧 open guess 之前最近候选的
`0xc0` byte 窗口以及候选到 ready 之间的所有 `jr ra`。它只读固件代码并实时写日志，
不会调用任何音频函数，正常结尾固定为：

```text
DIAGNOSTIC ONLY; NO AUDIO CALLS
RESULT=MAP_ONLY
END RECORD STREAM HARDWARE PROBE V3
```

日志：`A:\应用\数据\游戏\RECPCM3.TXT`

V3 BDA SHA-256：

```text
fd50ccd5aa87c2a9fa6e4d99e573614b611608787d5edf1397d021fd21b19357
```

V3 真机日志已归档：
[`record_stream_v3_hardware_log.txt`](assets/record_stream_v3_hardware_log.txt)

真机只读扫描得到三个相邻函数入口：

```text
0x80199D4C  stack frame 0x20，返回点 0x80199F00
0x80199F08  stack frame 0x18，返回点 0x80199F70
0x8019A050  stack frame 0x18，返回点 0x8019A080
0x8019A088  已确认 capture-ready 入口
```

旧 open guess `0x80199D7C` 位于第一个函数内部，距离函数入口正好 `0x30` byte。
`0x80199D4C` 在第一次 `jal` 前只保存 `ra/s0`，没有保存传入的 `a0/a1/a2`；第一次
调用返回后又立即覆盖参数寄存器。V3 只确认了函数边界，尚未确认该函数的业务角色；
若调用它，签名应为无参数，不能沿用本地 C200 的 `(16000,16,1)` 函数签名。

### 真机候选调用探针 V4

源码：`reverse/examples/record_stream_hardware_probe_v4.c`

构建产物：`build/RecordStreamProbeV4.bda`，标题 `RecPcmV4`，工具分类 9。

V4 只接受 V3 真机确认的结构：init candidate 前 6 个 word、`+0x1b4` 返回指令、
`+0x1bc` 下一个函数 prologue、ready 两个签名和 read 完整 prologue 必须全部匹配，
且每种候选只能出现一次。任一检查失败时在调用硬件前返回
`RESULT=UNSUPPORTED`。通过后执行：

```text
init-candidate()                       无参数
有限时等待 capture-ready()             最多 200 个 25-ms tick
capture-read(buffer, 0x1000)           ready 后才调用，共 8 block
SYS+0x0a0 stop
RAW file close
```

日志：`A:\应用\数据\游戏\RECPCM4.TXT`

PCM：`A:\应用\数据\游戏\RECPCM4.RAW`

V4 BDA SHA-256：

```text
c12a6ed6aacb68a695857e855e8eee5e68cb77ff9b2cc624e065bb376907cc10
```

V4 真机日志已归档：
[`record_stream_v4_hardware_log.txt`](assets/record_stream_v4_hardware_log.txt)

全部结构检查通过，`0x80199D4C()` 安全返回，但第一个 block 的 capture-ready 在
200 tick 后超时：

```text
OPEN RESOLVED=0x80199D4C
READ RESOLVED=0x80199290
TRUE HARDWARE SIGNATURE PASS
BEFORE CAPTURE OPEN NOARGS
CAPTURE OPEN RETURNED
READY TIMEOUT TICKS=0x000000C8
RESULT=FAIL
```

stop 和文件 close 再次正常返回。该结果证明 `0x80199D4C` 单独调用不足以启动
capture completed queue，所以不能把它命名为已确认的 capture-open。与本地 C200
的单体大函数相比，量产固件可能把 init、format/config 和 start 拆成多个阶段；也不
排除 `0x80199D4C` 属于另一条音频路径。

### 只读调用图探针 V5

源码：`reverse/examples/record_stream_hardware_probe_v5.c`

构建产物：`build/RecordStreamProbeV5.bda`，标题 `RecPcmV5`，工具分类 9。

V5 不调用任何音频函数。它完成两类只读检查：

1. 导出 init candidate 尾部、`0x80199F08` config candidate 和
   `0x8019A050` pre-ready helper 的完整代码。
2. 从 `SYS+0x000` 的 system manager 入口扫描到 ready 后 `0x400` byte，查找对
   init/config/pre-ready/ready/read 五个候选地址的直接 `jal`，并记录调用点前后
   `0x20` byte 和最近的调用者 prologue。

日志：`A:\应用\数据\游戏\RECPCM5.TXT`

正常结束固定为 `RESULT=MAP_ONLY`。V5 BDA SHA-256：

```text
f2106a653494ea15ff4cb5a3d0a3bad1407dda8c8e106b69bd10af856f4b5a97
```

V5 真机日志已归档：
[`record_stream_v5_hardware_log.txt`](assets/record_stream_v5_hardware_log.txt)

调用图把几个候选收敛为原厂包装器：

```text
0x8018EDAC -> 0x80199D4C()              init wrapper，无参数
0x8018EE00 -> 0x80199F08(3, value)      config wrapper
0x8018F328 -> 0x8019A050()              pre-ready wrapper
0x8018F344 -> 0x8019A088()              ready wrapper
0x8018D6D8 -> 0x80199290(buffer, 0x1000) PCM worker read
0x8018D7D4 -> 0x80199290(buffer, 0x1000) 第二条 PCM read 路径
```

`0x8018EE00` 把输入限制到 `0..127`，作为 `a1` 传递，并在 delay slot 设置
`a0=3`。此前把 op 3 误判为采样率；匹配真机的 `C200knl.bin` 跳转表确认 op 0 才
进入 `8000..48000` 采样率分支，op 3 会再限制到 100 并配置 codec gain。因此 V6
传入 16000 实际等价于满增益，不是采样率设置。

### 真机顺序探针 V6

源码：`reverse/examples/record_stream_hardware_probe_v6.c`

构建产物：`build/RecordStreamProbeV6.bda`，标题 `RecPcmV6`，工具分类 9。

V6 在调用前精确验证 init、config target、config wrapper、ready 和 read。config
wrapper 必须是 V5 记录的唯一调用者，且 `+0x24..+0x48` 的包装和调用指令全部匹配。
验证通过后执行：

```text
0x80199D4C()                 init candidate
0x8018EE00(16000)            gain wrapper 反例；最终被限制为 100
0x8019A088()                 有限时 ready
0x80199290(buffer, 0x1000)   ready 后才读取，共 8 block
SYS+0x0a0                    stop
```

init 或 config 返回非零时不会进入 ready/read，并立即走 stop/文件关闭。日志和 PCM：

```text
A:\应用\数据\游戏\RECPCM6.TXT
A:\应用\数据\游戏\RECPCM6.RAW
```

V6 BDA SHA-256：

```text
ce4a540788c5b3082364d531c5246e3270b28419dda74b8082de19cd9375a7b2
```

V6 真机日志已归档：
[`record_stream_v6_hardware_log.txt`](assets/record_stream_v6_hardware_log.txt)

真机上 init 和 config wrapper 均返回 0，但第一个 block 的 ready 仍在 200 tick
后超时：

```text
CAPTURE INIT RETURN=0x00000000
CONFIG WRAPPER RETURN=0x00000000
READY TIMEOUT TICKS=0x000000C8
RESULT=FAIL
```

因此该结果不能证明缺少采样率 config。`RECPCM6.RAW` 在 ready 成功前不会写入 PCM；
空文件不能作为采集证据。后续反汇编确认真正问题是把 ready 错当成第一次 read 的
前置条件。

### 只读控制调用图探针 V7

源码：`reverse/examples/record_stream_hardware_probe_v7.c`

构建产物：`build/RecordStreamProbeV7.bda`，标题 `RecPcmV7`，工具分类 9。

V7 不调用 init、config、ready、read 或 stop，也不创建 RAW 文件。它先用 V5/V6
的精确签名和唯一直接调用者重新定位 init/config/ready/read，再导出：

1. PCM worker 首个 read 调用者附近 `0x600` byte 的函数入口和调用图。
2. init 包装器前 `0x800` byte 到 ready 包装器后 `0x1000` byte 的 control 调用图。
3. 两个区域内全部直接 `jal`、间接 `jalr`、delay slot 和最近 prologue。
4. 指向 audio-driver 地址范围的每个调用点与目标函数前后 `0x20` byte。

日志：`A:\应用\数据\游戏\RECPCM7.TXT`。V7 BDA SHA-256：

```text
c1c28805516c1782a8ef1b9b02668cb1214c55bbc27b906939b5c2c3afeaeef0
```

V7 真机日志已归档：
[`record_stream_v7_hardware_log.txt`](assets/record_stream_v7_hardware_log.txt)

V7 在扫描前返回 `RESULT=UNSUPPORTED`。原因是探针错误地用旧 guess
`0x80199294` 的指令比较 read 函数入口签名；真实入口是 `0x80199290`。没有执行
调用图扫描，也没有调用音频函数。

### 修正后的只读调用图探针 V8

源码：`reverse/examples/record_stream_hardware_probe_v8.c`

构建产物：`build/RecordStreamProbeV8.bda`，标题 `RecPcmV8`，工具分类 9。

V8 改为从 `read_target[0..1]` 验证完整 read prologue，并单独记录 init、config、
ready、read 四个入口各两条签名。其余扫描范围和只读约束与 V7 相同。日志为
`A:\应用\数据\游戏\RECPCM8.TXT`；正常结束固定为 `RESULT=MAP_ONLY`。

V8 BDA SHA-256：

```text
d5b3af67398cbc4e91eddf05c519c1829098e3add0ecbe5cd516e0047c8b5a16
```

V8 真机日志已归档：
[`record_stream_v8_hardware_log.txt`](assets/record_stream_v8_hardware_log.txt)

V8 完整通过签名与调用者解析并输出 `RESULT=MAP_ONLY`。调用图新增三个重要入口：

```text
0x8018D4AC -> 0x8018EDD4() -> 0x8019B8AC() -> 0x8019B900()
0x8018F1E8 -> 0x80199720()
0x8018D60C -> 0x8018F344() -> 0x8019A088()  ready
```

其中 `0x8018EDD4` 位于原厂 PCM worker 的首次 ready 检查之前，是当前最强的
start/enable 候选；两个下游函数写入固定硬件命令并轮询状态位。`0x80199720`
则是另一条无参数 stream-control 路径。仅凭短代码窗口还不能区分启动、停止和
硬件格式配置，因此暂不执行它们。

### Ready 状态写入者探针 V9

源码：`reverse/examples/record_stream_hardware_probe_v9.c`

构建产物：`build/RecordStreamProbeV9.bda`，标题 `RecPcmV9`，工具分类 9。

V9 仍然完全只读，进一步导出：

1. `0x8018D340` PCM worker 从入口到首次 read 后的完整代码。
2. init、`0x8018EDD4`、config 附近 control wrapper 的完整代码。
3. `0x80199720..0x80199AD0` stream driver 和 `0x8019B8AC/0x8019B900` 硬件函数。
4. audio driver 中对 `0x8058D4xx/0x8058D5xx` capture state 的全部 load/store
   引用，尤其是 ready 使用的 `0x8058D530`。
5. 两组候选 wrapper 和 target 在 system-manager 区的全部直接调用者。

日志为 `A:\应用\数据\游戏\RECPCM9.TXT`；正常结束固定为
`RESULT=MAP_ONLY`。V9 BDA SHA-256：

```text
7ef7b9798bdbe3018c7839a88ac693bcc589c779f94f2e06f3bfdbc4839e05a5
```

V9 真机未完成日志已归档：
[`record_stream_v9_hardware_partial_log.txt`](assets/record_stream_v9_hardware_partial_log.txt)

V9 已完成全部深度函数导出，随后在状态引用扫描推进到 `0x80199400` 时表现为长时间
无响应。原因不是音频调用或无效地址，而是每个状态字段命中会实时写入约 19 行上下文；
每行都执行一次文件 open/write/close，日志达到 1118 行后仍未完成扫描。已记录的内容
确认 read 函数会读取并递减 `0x8058D530`，但尚未覆盖后半段 driver 中的生产者。

### 紧凑状态引用探针 V10

源码：`reverse/examples/record_stream_hardware_probe_v10.c`

构建产物：`build/RecordStreamProbeV10.bda`，标题 `RecPcmV10`，工具分类 9。

V10 只执行 V9 最后一项状态引用扫描。每个命中压缩为一行，包含地址、指令、最近
prologue、前一条和后一条指令；仍逐行关闭日志文件以保留崩溃前记录。它不重复导出
已由 V9 获取的函数体，也不调用任何音频函数。日志为
`A:\应用\数据\游戏\RECPCM10.TXT`，正常结束为 `RESULT=MAP_ONLY`。

V10 BDA SHA-256：

```text
f0dd690579c8f4bb45cc14fae352c1061ab9e253fe72aa6e2638b5b823186ce2
```

V10 真机日志已归档：
[`record_stream_v10_hardware_log.txt`](assets/record_stream_v10_hardware_log.txt)

扫描完整命中 86 个状态引用。`0x8058D530` 在 read `0x80199290` 中被读取并写回，
在 init `0x80199D4C` 中清零；`0x8019A5A0` 是另一处同时读取和写回 `D530` 的函数，
并访问 `D520/D524/D540`，因此是当前最强的 DMA 完成或采集块完成回调候选。

结合 V9 已导出的 worker 代码还需修正此前结论：`0x8018D428` 调用
`0x8018EDCC`，而该函数固定返回 0，所以控制流必然进入 `0x8018D5A8`。
`0x8018EDD4 -> 0x8019B8AC -> 0x8019B900` 所在分支在本固件中不可达，不能再作为
capture start 候选。活动路径在 ready 前调用 `0x8019577C`、`0x801957E0`，随后
再次调用 `0x8019577C`。

### 等待原语与采集回调探针 V11

源码：`reverse/examples/record_stream_hardware_probe_v11.c`

构建产物：`build/RecordStreamProbeV11.bda`，标题 `RecPcmV11`，工具分类 9。

V11 从已确认的 read caller worker 动态解析上述两个调用目标，导出目标函数代码、
`0x8019A5A0..0x8019A7C8` 回调候选代码，并紧凑扫描三者的直接调用者及
`0x8019A5A0` 函数指针物化位置。该版本仅读取固件代码，不打开录音、不调用
ready/read，也不创建 RAW 文件。日志为 `A:\应用\数据\游戏\RECPCM11.TXT`；
正常结束固定为 `RESULT=MAP_ONLY`。

V11 BDA SHA-256：

```text
b47e7b2da7c4504625b335109dbbf49f6cbdbbf3491a641d87a9ce46852e2a09
```

V11 真机日志已归档：
[`record_stream_v11_hardware_log.txt`](assets/record_stream_v11_hardware_log.txt)

真机结果确认 `0x8019A5A0` 没有直接调用者，但在 `0x80199AD0` 和
`0x80199D4C` 中各有一次函数指针物化；capture init 在 `0x80199D74` 把它传给
`0x8019C504`。该底层函数配置 DMA channel，并通过 IRQ 注册函数保存 callback。
`0x8019577C` 和 `0x801957E0` 分别有 16 和 12 个直接调用点，属于通用同步包装器。

V11 的机器码与 `系统/数据/C200knl.bin` 完全匹配：load base 为 `0x80004000`，
文件中代码相对 VA 多 `0x40` byte 容器头。该镜像 SHA-256 为：

```text
dc41701442176ba81bf1b8041b2f9dac449e04f2adf6532993e7c55471de9bea
```

本地反汇编 `0x80199290` 证明首次 read 才会启动 DMA：当 `D530` completed queue
为空时，它从 `D520/D524` free queue 取 buffer，设置 AIC 位并调用 `0x8019C390`，
随后等待 `0x8019A5A0` 回调。`0x8019A088` ready 只读取 completed count，不能在
第一次 read 之前作为门控。V2/V4/V6 的共同失败原因由此确定。

### 首次阻塞读取探针 V12

源码：`reverse/examples/record_stream_hardware_probe_v12.c`

构建产物：`build/RecordStreamProbeV12.bda`，标题 `RecPcmV12`，工具分类 9。

V12 精确检查 init `0x80199D4C`、read `0x80199290` 和 capture-specific stop
`0x80199A6C` 的真机签名，然后执行：

```text
init()
blocking read(buffer, 0x1000) x 4   首个 read 负责 prime DMA
capture-specific stop()
```

每个 read 返回后立即把 PCM 追加到 `RECPCM12.RAW`，并实时记录耗时、峰值、平均绝对
幅度和非零样本数。该版本不调用通用 audio flush，也不在首次 read 前轮询 ready。
日志和 PCM 位于：

```text
A:\应用\数据\游戏\RECPCM12.TXT
A:\应用\数据\游戏\RECPCM12.RAW
```

V12 BDA SHA-256：

```text
e876cee77c3719f95d4e81b6317922db1e5f70d9eb0cae7520c6bee0aa8e2c94
```

V12 真机日志已归档：
[`record_stream_v12_hardware_log.txt`](assets/record_stream_v12_hardware_log.txt)

真机完整返回 4 个 4096-byte block，总计 16384 byte，结果为 `PASS`。首块读取耗时
9 个 25-ms tick，后续为 4、3、3 tick；每块 2048 个 sample 全部非零。下载到主机
的 RAW SHA-256 为：

```text
91993bd45590df3dbd5c126967da5b741a4d19448be4ad4be4a17a78e2666ab4
```

按 little-endian signed 16-bit、16000 Hz 解析得到 8192 sample、0.512 秒；全局范围
`-1503..5228`，去直流 RMS 约 421.9。三个 block 边界的相邻 sample 差值为
`-1/-12/+16`，说明 DMA 数据连续，没有重复 block 或拼接断层。停止函数和 RAW close
均正常返回。

### 低延迟与重启探针 V13

源码：`reverse/examples/record_stream_hardware_probe_v13.c`

构建产物：`build/RecordStreamProbeV13.bda`，标题 `RecPcmV13`，工具分类 9。

V13 在一次运行中执行两个完整采集周期。每周期 init 后读取 8 个 1024-byte block，
随后 capture-specific stop；第二周期立即重新 init 并重复读取。成功时
`RECPCM13.RAW` 共 16384 byte，可同时确认较小 block 的约 32-ms 理论粒度及 stop 后
重启能力。日志和 PCM 位于：

```text
A:\应用\数据\游戏\RECPCM13.TXT
A:\应用\数据\游戏\RECPCM13.RAW
```

V13 BDA SHA-256：

```text
0b98c777adebf89d8db8628183eaa327be19845e253809c469ce816e75a2dad7
```

## 文件系统行为

录音应用使用：

```text
FS +0x000  fopen 类
FS +0x004  fclose 类
FS +0x008  fread 类
FS +0x010  fseek 类
FS +0x024  remove/delete 类
FS +0x02c  chdir/目录存在检查类
FS +0x030  mkdir 类
FS +0x03c  findfirst 类
FS +0x040  findnext 类
FS +0x044  findclose 类
FS +0x048  disk-info/free-space 类
FS +0x078  存储/路径辅助，未命名
FS +0x07c  storage-ready 类
```

第一个 helper 会打开文件、读取 `0x24` 字节，并在加载 UI 资源时检查 DLX magic。
后续独立 FS 调用点负责 WAV 列表枚举、删除和生成录音文件名。

重复出现的 `FS+0x024` 调用点可交叉验证其他文件管理类应用中推断出的
delete/remove 语义。

## GUI 和事件行为

应用使用正常事件循环偏移：

```text
GUI +0x030  poll 类
GUI +0x050  step 类
GUI +0x054  dispatch 类
GUI +0x17c  destroy/close frame 类
```

它也使用常见窗口/控件/资源偏移：

```text
GUI +0x074, +0x03c
GUI +0x0e4/+0x0e8
GUI +0x1ac/+0x1b0
GUI +0x338/+0x33c/+0x378/+0x4f0
GUI +0x46c
```

这里的文字偏移调用比记事本/电子图书少，但足以确认录音 UI 使用同一套 GUI
栈，而不是完全自定义的游戏 framebuffer。

## 交叉验证

- 与 `情景会话.bda`：确认 type-5 descriptor 的全部六个 word，并确认正常关闭顺序
  是 `SYS+0x020` 后接 `SYS+0x004`。
- 与 `飞天音乐.bda`：确认播放和录音都复用 session manager，而不是每个 offset
  对应一种媒体格式。
- 与 `记事本.bda` 和 FS 探针：确认 FS 表包含普通 C 风格文件操作，以及
  find/delete/storage 辅助函数。
- 与 DLX 工作：确认另一个量产应用的 DLX 资源也只是 type-1 VX 图片。

## 未确认点

1. `SYS+0x014` 第二参数 word 的业务含义，以及 `SYS+0x020` 的准确状态名。
2. callback 的 `a0` 含义和 `a1` 事件码枚举。
3. `SYS+0x02c` 0x20-byte status 各字段的准确单位和名称。
4. 真机需要验证短录音能否按上述顺序生成可重放 WAV，并检查 RIFF/data 长度、
   实际 16000 Hz/mono/16-bit 格式以及重复 open/close 是否泄漏。
5. 1024-byte 低延迟读取、stop 后立即重启仍等待 V13 真机结果；4096-byte 连续读取、
   capture-specific stop、GUI 波形显示、ESC 返回和完整 128-block 录制已经通过真机。
