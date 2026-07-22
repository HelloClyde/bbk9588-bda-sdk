# 实时 PCM 录音 API

公开头：`sdk/include/bda_audio.h`

## 固件边界

该接口调用固件内部录音驱动，不是稳定的系统函数表 ABI。目前只支持并验证了 BBK
9588 C200 真机上的这一版 `C200knl.bin`：

```text
SHA-256 dc41701442176ba81bf1b8041b2f9dac449e04f2adf6532993e7c55471de9bea
load base 0x80004000
capture init 0x80199D4C
capture read 0x80199290
capture stop 0x80199A6C
```

`bda_audio_capture_firmware()` 先检查三个系统表目标地址，再检查上述三个函数入口的
机器码签名。只有全部匹配才返回
`BDA_AUDIO_CAPTURE_FIRMWARE_C200KNL_V1`。任何未知或修改过的固件都返回
`BDA_AUDIO_CAPTURE_FIRMWARE_NONE`；`open/read/stop` 随后返回
`BDA_AUDIO_CAPTURE_UNSUPPORTED`，不会调用固件私有地址。

这项保护识别的是固件代码，不代表模拟器实现了麦克风设备。当前录音验证必须在真机
完成。

## 已验证格式

```c
BDA_AUDIO_CAPTURE_SAMPLE_RATE_16000 /* 16000 Hz */
BDA_AUDIO_CAPTURE_BITS_16           /* signed little-endian PCM */
BDA_AUDIO_CAPTURE_CHANNELS_MONO     /* mono */
BDA_AUDIO_CAPTURE_BLOCK_BYTES       /* 4096 bytes */
```

V12 真机读取了 4 个连续的 4096-byte block，共 16384 byte。首次 read 会启动 DMA，
然后阻塞到 IRQ callback 提供完整数据。不要在首次 read 前调用 `bda_audio_ready()`；
该函数属于播放队列，不能表示录音数据就绪。1024-byte 小块仍在 V13 验证阶段，公开
wrapper 会将非 4096-byte 请求作为 `BDA_AUDIO_CAPTURE_INVALID_ARGUMENT` 拒绝。

## 生命周期

```text
bda_audio_capture_is_supported()
             |
             +-- 0: do not call private firmware code
             |
             v
bda_audio_capture_open(&capture)
             |
             v
bda_audio_capture_read(&capture, pcm, 4096) -- blocking; repeat
             |
             v
bda_audio_capture_stop(&capture)
```

只有一个录音流可以处于打开状态。每次成功 `open` 都必须以 `stop` 结束，包括文件
写入失败或用户提前退出的路径。

## 返回值

| 常量 | 值 | 含义 |
|---|---:|---|
| `BDA_AUDIO_CAPTURE_OK` | 0 | open/stop 成功 |
| `BDA_AUDIO_CAPTURE_UNSUPPORTED` | -1 | 固件 profile 或机器码签名不匹配 |
| `BDA_AUDIO_CAPTURE_INVALID_ARGUMENT` | -2 | 空指针、未对齐缓冲区或块大小不为 4096 |
| `BDA_AUDIO_CAPTURE_INVALID_STATE` | -3 | 重复 open、未 open 就 read/stop |
| `BDA_AUDIO_CAPTURE_IO_ERROR` | -4 | 固件初始化或读取返回异常 |

`bda_audio_capture_read()` 成功时返回实际读取的正 byte 数。当前完整成功值应为 4096。

## 最小用法

```c
#include "bda_audio.h"

static s16 pcm[BDA_AUDIO_CAPTURE_BLOCK_BYTES / sizeof(s16)];
bda_audio_capture_t capture = BDA_AUDIO_CAPTURE_INITIALIZER;
int result;

result = bda_audio_capture_open(&capture);
if (result == BDA_AUDIO_CAPTURE_UNSUPPORTED) {
    /* This firmware is not supported; no private function was called. */
    return;
}
if (result != BDA_AUDIO_CAPTURE_OK) {
    return;
}

result = bda_audio_capture_read(
    &capture, pcm, BDA_AUDIO_CAPTURE_BLOCK_BYTES
);
/* Process or write exactly result bytes when result is positive. */

(void)bda_audio_capture_stop(&capture);
```

完整示例：`example/system/audio_capture/audio_capture_demo.c`。它在每次阻塞 read
返回后去除 block 的直流偏置、自动计算显示增益，并把 2048 个样本降采样为 220 列
实时波形。波形约每 128 ms 更新一次；按 ESC 会先停止 capture，再按已验证 Frame
生命周期退出。成功后生成 `A:\应用\数据\游戏\AUDCAP.RAW`，最多录制 128 个
4096-byte block（约 16.4 秒、512 KiB）。

示例把低频生命周期日志实时写入并关闭
`A:\应用\数据\游戏\AUDCAP.TXT`。日志至少包含固件 profile、Frame 注册、首块 read、
首帧波形、每 8 块进度、capture stop 和窗口关闭；真机中途异常时已完成的日志行仍可
导出分析。

## 动态证据

真机测试源码：`reverse/examples/record_stream_hardware_probe_v12.c`。

完整实时日志：
[`../../reverse/reports/assets/record_stream_v12_hardware_log.txt`](../../reverse/reports/assets/record_stream_v12_hardware_log.txt)。
日志包含 4 次 `GOT=4096`、`CAPTURE-SPECIFIC STOP RETURNED` 和 `RESULT=PASS`。
导出的 RAW 长度为 16384 byte，8192 个样本全部非零；四个 block 的边界差值分别为
-1、-12、+16，确认数据连续而不是重复块。

尚未验证：其他 C200/kj409588 固件版本、模拟器录音设备、立体声、其他采样率、非
16-bit PCM、非 4096-byte read，以及多录音流并发。

波形版 `AudioCapture.bda`（SHA-256
`D9F27ED3A7D84DE151316AAC84E6B34C36C8A728946769515C9D0102E3979FA0`）已由真机
测试者确认能够启动并运行。该次未附 `AUDCAP.TXT` 或 `AUDCAP.RAW`，因此只把“波形
显示、日志生成、ESC 安全返回和完整 128-block 录制”记为真机人工闭环；文件内容本身
没有随本次仓库更新归档。
观察记录见
[`assets/audio_capture_waveform_hardware_result.txt`](assets/audio_capture_waveform_hardware_result.txt)。
