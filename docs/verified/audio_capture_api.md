# 实时 PCM 录音 API

公开头：`sdk/include/bda_audio.h`

## 接口与固件边界

`bda_audio_capture_open/read/ready/stop` 的生命周期、参数和返回值已经在 BBK 9588
C200/JZ4730 真机上动态闭环，因此这些名称和调用约定属于公开 SDK API。底层仍调用
原机固件的私有录音驱动，不是稳定的系统函数表 ABI。

SDK 先使用 `bda_hardware.h` 识别设备和芯片，再检查 capture init、read、ready、stop
入口的精确机器码。只有型号、芯片和所有签名一致时才返回 profile；未知固件返回
`BDA_AUDIO_CAPTURE_UNSUPPORTED`，不会调用任何录音私有地址。成功或失败的检测结果
都会在当前 BDA 会话中缓存，5 MiB OS 镜像扫描不会进入录音热路径。

## 固件 Profile

| Profile 常量 | 设备 | 芯片 | 固件 SHA-256 | 支持等级 |
|---|---|---|---|---|
| `BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4720` | 9588/C200 | JZ4720 | `469A833E8984E8C4C531A411955EDC38F5FB57C6089B8694F522F995DBE66C49` | 静态候选 |
| `BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4730` | 9588/C200 | JZ4730 | `C7A4BA34D5A4C006F88B7E9E0C0A991B2B1E7A1EC8896859F0CC3DFB18E44270` | 真机验证 |
| `BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4740` | 9588/C200 | JZ4740 | `02A16107B11A3281067871C6FE3D4C289C910D8DFA9924573DD87F00351D6525` | 静态候选 |
| `BDA_AUDIO_CAPTURE_FIRMWARE_9688_JZ4730` | 9688/C100 | JZ4730 | `B18CE485A6CA6A8EA9EF5E3963D5970188FF7A2AEB4A6D4E58FE43625F49E514` | 静态候选 |
| `BDA_AUDIO_CAPTURE_FIRMWARE_9688_JZ4740` | 9688/C100 | JZ4740 | `7EC707B69A1F4FA7016856B2EBA6900412D02D7DAEFC8B4D11654C63731ABCA0` | 静态候选 |

表中 hash 是加载到 `0x80004000` 的原始恢复 payload。真机验证所用
`C200knl.bin` 带 0x40-byte container header，其 SHA-256 是
`dc41701442176ba81bf1b8041b2f9dac449e04f2adf6532993e7c55471de9bea`；
去除 header 后与表中的 9588/JZ4730 payload 完全相同。

“静态候选”表示恢复镜像、地址、调用约定和机器码门禁已经离线核对，但尚未在对应真机
完成 open/read/ready/stop 闭环。它不是“真机已兼容”的声明。应用可读取
`bda_audio_capture_profile()->support_level`，分别处理：

```c
BDA_AUDIO_CAPTURE_SUPPORT_HARDWARE_VERIFIED
BDA_AUDIO_CAPTURE_SUPPORT_STATIC_CANDIDATE
```

`bda_audio_capture_firmware()` 返回当前 profile 的数值标识；
`bda_audio_capture_is_supported()` 是“profile 不为空”的便捷判断。需要显示机型、芯片
或验证等级时应直接读取 `bda_audio_capture_profile()` 返回的只读信息。

## 固件调用约定

| 设备/芯片 | Capture init | Capture read | Capture ready | Capture stop | Init 参数 |
|---|---:|---:|---:|---:|---|
| 9588/JZ4720 | `0x801967F0` | `0x80195D84` | `0x80196CCC` | `0x8018B0D8` | `16000, 16, 1` |
| 9588/JZ4730 | `0x80199D4C` | `0x80199290` | `0x8019A088` | `0x80199A6C` | 无 |
| 9588/JZ4740 | `0x80194900` | `0x80193E94` | `0x80194DDC` | `0x801891E8` | `16000, 16, 1` |
| 9688/JZ4730 | `0x801A169C` | `0x801A04D0` | `0x801A19D8` | `0x801A13BC` | 无 |
| 9688/JZ4740 | `0x8019E400` | `0x8019D284` | `0x8019EB88` | `0x801925D8` | `16000, 16, 1` |

JZ4720/JZ4740 的 initializer 是带三个参数的 `void` 函数；JZ4730 initializer
无参数并返回状态。SDK 在内部 profile 中封装差异，应用始终使用同一套公开 API。

## 已验证格式

```c
BDA_AUDIO_CAPTURE_SAMPLE_RATE_16000 /* 16000 Hz */
BDA_AUDIO_CAPTURE_BITS_16           /* signed little-endian PCM */
BDA_AUDIO_CAPTURE_CHANNELS_MONO     /* mono */
BDA_AUDIO_CAPTURE_BLOCK_BYTES       /* 4096 bytes */
```

V12 真机读取了 4 个连续的 4096-byte block，共 16384 byte。首次 read 会启动 DMA，
然后阻塞到 IRQ callback 提供完整数据。后续循环可先调用
`bda_audio_capture_ready()`，只在返回 `1` 时读取，以免 UI 或 USB 服务循环阻塞。
不要使用 `bda_audio_ready()` 判断录音状态；它属于播放队列。

1024-byte 小块仍未完成真机验证，公开 wrapper 会将非 4096-byte 请求作为
`BDA_AUDIO_CAPTURE_INVALID_ARGUMENT` 拒绝。

## 生命周期

```text
bda_audio_capture_profile()
             |
             +-- null: unsupported; no private firmware call
             |
             v
bda_audio_capture_open(&capture)
             |
             +-- first bda_audio_capture_read(&capture, pcm, 4096)
             |      starts DMA and may block
             |
             +-- bda_audio_capture_ready(&capture)
             |      1: one complete block can be read
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
| `BDA_AUDIO_CAPTURE_INVALID_STATE` | -3 | 重复 open、未 open 就 read/ready/stop |
| `BDA_AUDIO_CAPTURE_IO_ERROR` | -4 | 固件初始化或读取返回异常 |

`bda_audio_capture_read()` 成功时返回实际读取的正 byte 数，当前完整成功值应为 4096。
`bda_audio_capture_ready()` 返回 `1` 或 `0`，参数或状态错误时返回上述负值。

## 最小用法

```c
#include "bda_audio.h"

static s16 pcm[BDA_AUDIO_CAPTURE_BLOCK_BYTES / sizeof(s16)];
bda_audio_capture_t capture = BDA_AUDIO_CAPTURE_INITIALIZER;
const bda_audio_capture_profile_t *profile;
int result;

profile = bda_audio_capture_profile();
if (profile == 0) {
    return;
}

result = bda_audio_capture_open(&capture);
if (result != BDA_AUDIO_CAPTURE_OK) {
    return;
}

result = bda_audio_capture_read(
    &capture, pcm, BDA_AUDIO_CAPTURE_BLOCK_BYTES
);
if (result == (int)BDA_AUDIO_CAPTURE_BLOCK_BYTES) {
    /* Process the first complete block. */
}

while (bda_audio_capture_ready(&capture) == 1) {
    result = bda_audio_capture_read(
        &capture, pcm, BDA_AUDIO_CAPTURE_BLOCK_BYTES
    );
    if (result != (int)BDA_AUDIO_CAPTURE_BLOCK_BYTES) {
        break;
    }
}

(void)bda_audio_capture_stop(&capture);
```

完整示例：`example/system/audio_capture/audio_capture_demo.c`。它在每次阻塞 read
返回后去除 block 的直流偏置、自动计算显示增益，并把 2048 个样本降采样为 220 列
实时波形。波形约每 128 ms 更新一次；按 ESC 会先停止 capture，再按已验证 Frame
生命周期退出。成功后生成 `A:\应用\数据\游戏\AUDCAP.RAW`，最多录制 128 个
4096-byte block（约 16.4 秒、512 KiB）。

## 动态证据

9588/JZ4730 真机测试源码：
`reverse/examples/record_stream_hardware_probe_v12.c`。

完整实时日志：
[`../../reverse/reports/assets/record_stream_v12_hardware_log.txt`](../../reverse/reports/assets/record_stream_v12_hardware_log.txt)。
日志包含 4 次 `GOT=4096`、`CAPTURE-SPECIFIC STOP RETURNED` 和 `RESULT=PASS`。
导出的 RAW 长度为 16384 byte，8192 个样本全部非零；四个 block 的边界差值分别为
-1、-12、+16，确认数据连续而不是重复块。

尚未真机验证：9588/JZ4720、9588/JZ4740、9688/JZ4730、9688/JZ4740、模拟器录音
设备、立体声、其他采样率、非 16-bit PCM、非 4096-byte read，以及多录音流并发。

历史单 profile 波形版 `AudioCapture.bda`（SHA-256
`D9F27ED3A7D84DE151316AAC84E6B34C36C8A728946769515C9D0102E3979FA0`）
已由 9588/JZ4730 真机测试者确认能够启动并运行。观察记录见
[`assets/audio_capture_waveform_hardware_result.txt`](assets/audio_capture_waveform_hardware_result.txt)。

当前仓库中的多 profile `AudioCapture.bda` 由同目录源码重新构建，SHA-256 为
`ED9135E648E074DFA7C74A9D7E659FD306C3CF452348DD0323FB605C0CF46A39`。该 hash
表示离线构建产物，不把四个静态候选升级为真机验证。
