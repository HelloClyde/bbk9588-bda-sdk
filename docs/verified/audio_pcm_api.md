# Raw PCM 音频 API

公开头：`sdk/include/bda_audio.h`

验证环境：

- `bbk9588-emulator-v0.1.5`、端口 8013、kj409588/C200 固件；`C200.bin`
  SHA-256 为 `02a16107b11a3281067871c6fe3d4c289c910d8dfa9924573dd87f00351d6525`。
- BBK 9588 C200 真机；完成 8 个 1024-byte block、衰减切换、静音恢复块、
  `SYS+0x0a0` stop 和返回菜单闭环，返回后无声音且系统响应正常。

## 生命周期

```text
bda_audio_open_pcm(22050, 16, 1)
             |
             v
 bda_audio_set_attenuation(value) [optional, applies on next write]
             |
             v
  bda_audio_ready() != 0 ----> bda_audio_write(pcm, bytes)
             |                         |
             +----------- repeat <----+
             |
             v
          bda_audio_stop()
             |
             +-- SYS+0x0a0 firmware finish/stop
```

已动态验证的格式只有 22050 Hz、signed 16-bit、mono。对应常量：

```c
BDA_AUDIO_SAMPLE_RATE_22050
BDA_AUDIO_BITS_16
BDA_AUDIO_CHANNELS_MONO
```

`bda_audio_ready()` 非零只表示至少一个 firmware queue slot 可写，不表示全部待播
数据已经排空。`bda_audio_write()` 成功时返回消费的 byte 数；测试使用 1024-byte
block。

## PCM 衰减

```c
int original = bda_audio_get_attenuation();

bda_audio_set_attenuation(BDA_AUDIO_ATTENUATION_FULL_SCALE);  /* 0 */
/* The new value is applied by the next bda_audio_write(). */

bda_audio_set_attenuation(BDA_AUDIO_ATTENUATION_HALF_SCALE);  /* 48 */
bda_audio_set_attenuation(BDA_AUDIO_ATTENUATION_NEAR_SILENT); /* 96 */
```

这里的参数是 attenuation，不是“数值越大声音越大”的 volume：

| effective attenuation | 12000 输入峰值 | 含义 |
| ---: | ---: | --- |
| 0 | 12000 | full scale |
| 3 | 11625 | 轻微衰减 |
| 48 | 6000 | half scale |
| 96 | 46 | near-silent，不保证绝对静音 |

`bda_audio_set_attenuation()` 对应 `SYS+0x040`。它只保存 pending value，下一次
`bda_audio_write()` 才应用。firmware 先把输入限制到 `0..98`，再按
`floor(value / 3) * 3` 量化，因此 getter 的有效范围是 `0..96`，步进为 3。
`bda_audio_get_attenuation()` 对应 `SYS+0x044`，返回当前已经应用的值。

应用退出前若修改过衰减，应保存原值，并在 stop 前用一个 silent PCM block 应用恢复值。
仅调用 setter 后立即 stop 会留下尚未应用的 pending value。

## Stop 的真机边界

公开 `bda_audio_stop()` 只调用动态系统表 `SYS+0x0a0`。真机验证中该调用正常返回，
应用随后返回菜单，声音停止且系统未卡顿。原厂 `GAMEBOY.BDA` 的对应清理函数也是调用
`SYS+0x0a0` 后直接返回。

模拟器后端曾显示 `SYS+0x0a0` 后 AIC timer 仍为 active，因此早期实验额外直调
`0x80195b24(0)`。真机 V3 已推翻这一做法：`SYS+0x0a0` 正常返回，但随后直调该固定
地址立即死锁，日志最后一行为 `BEFORE AIC RESET`。该函数直接操作 `0xb002xxxx`
AIC MMIO，只是 raw open 内部初始化路径的一部分，不是 BDA 可调用的系统 API。

因此固定地址已从公开头移除。开发者不得复制模拟器探针中的 AIC reset 调用，也不应
使用 `SYS+0x08c` 替代 stop；后者处理的是另一套高层 resource state。

## 动态证据

模拟器停止探针：`reverse/examples/game_audio_cleanup_probe.c`。
衰减探针：`reverse/examples/game_audio_volume_probe.c`。
真机 stop 失败探针：`reverse/examples/audio_pcm_hw_stop_probe.c`。
真机 finish-only 成功探针：`reverse/examples/audio_pcm_hw_finish_probe.c`。

8013 的 `GameAudioV4/V5` 曾用固定地址补停模拟器 AIC timer。该结果只描述模拟器后端，
不能作为真机 ABI。真机 V2 完成全部 8 次写入和静音恢复写入后停在
`BEFORE AUDIO STOP`；分段 V3 进一步记录：

```text
BEFORE AUDIO STOP
BEFORE SYS FINISH
AFTER SYS FINISH
BEFORE AIC RESET
```

这证明系统表 finish 正常，固定地址调用才是死锁点。完整日志见
[`assets/audio_pcm_true_hardware_v3_log.txt`](assets/audio_pcm_true_hardware_v3_log.txt)。

V4 删除固定地址调用，只保留 `SYS+0x0a0`，真机结果为：

- 正常返回菜单；
- 返回后无声音；
- 系统操作正常，没有卡顿。

人工观察记录见
[`assets/audio_pcm_true_hardware_v4_result.txt`](assets/audio_pcm_true_hardware_v4_result.txt)。

模拟器只调用 `SYS+0x0a0` 时曾观察到：

```text
playing=true  timer_running=true
dma_completion_count=8  dma_rearm_count=7
audio packets continued increasing
```

模拟器额外直调 AIC reset 后：

```text
playing=false  timer_running=false
dma_completion_count=8  dma_rearm_count=7
audio packets stopped at 166
AICFR=0x00001830  AICCR=0x00094800
```

这个差异说明模拟器的 AIC timer 状态不能反推真机必须执行同一 MMIO 序列。公开 API
以真机安全闭环和原厂 BDA 调用方式为准。

`GameVolV1` 保存原衰减后测试 `-1/0/1/2/3/48/97/98/120`，所有 getter 量化、
PCM 峰值变化、原值恢复和 stop 均通过，日志为 `FAILURES=0`、`RESULT=PASS`。
程序返回菜单后连续 4 秒保持 `playing=false`、`timer_running=false`，音频传输包
保持 `15 -> 15`。

## 最小用法

```c
#include "bda_audio.h"

int original_attenuation = bda_audio_get_attenuation();

bda_audio_open_pcm(
    BDA_AUDIO_SAMPLE_RATE_22050,
    BDA_AUDIO_BITS_16,
    BDA_AUDIO_CHANNELS_MONO
);

bda_audio_set_attenuation(BDA_AUDIO_ATTENUATION_HALF_SCALE);

if (bda_audio_ready()) {
    int written = bda_audio_write(samples, sample_bytes);
    if (written != (int)sample_bytes) {
        /* handle short write/error */
    }
}

if (bda_audio_ready()) {
    bda_memset(samples, 0, sample_bytes);
    bda_audio_set_attenuation((u32)original_attenuation);
    (void)bda_audio_write(samples, sample_bytes);
}

bda_audio_stop();
```

完整示例：`example/system/audio_pcm/audio_pcm_demo.c`，编译产物为同目录
`AudioPcm.bda`。游戏退出、切换关卡或不再需要声音时必须调用 stop；仅从
`bda_main()` return 不会替 raw stream 关闭 AIC 定时器。

该示例每条日志都会立即 close，真机中写入
`A:\应用\数据\游戏\AUDIOPCM.TXT`，路径无盘符版本作为回退。正式 V5 日志以
`START AUDIO PCM TRUE HARDWARE VERIFIED V5` 开头。
