# Raw PCM 音频 API

公开头：`sdk/include/bda_audio.h`

验证环境：`bbk9588-emulator-v0.1.5`、端口 8013、kj409588/C200 固件。
`C200.bin` SHA-256：
`02a16107b11a3281067871c6fe3d4c289c910d8dfa9924573dd87f00351d6525`。
当前结论只覆盖模拟器，真机仍待验证。

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
             +-- SYS+0x0a0 finish/config
             +-- C200 0x80195b24(0) AIC reset
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

## 为什么 stop 仍然绑定固件

系统表没有导出完整的 raw PCM close：

- `SYS+0x0a0` 单独调用后，DMA 不再 rearm，但 AIC 输出定时器继续产生 underrun。
- `SYS+0x08c` 只清理由 `SYS+0x090` 指向的高层 resource state；raw open 不写该
  state，因此它不是 raw PCM close。
- `0x80195b24` 是 C200 raw open 自己使用的 AIC reset primitive。它清除
  `AICFR.ENB` 和 `AICCR.ERPL`，但不是 runtime table entry。

因此 `bda_audio_stop()` 先执行系统 finish/config，再调用固件绑定的 AIC reset。SDK
本身只面向 9588，公开方法名不重复设备型号；固定地址和不可直接移植到其他固件的
限制由头文件注释与本文档说明。

## 动态证据

停止探针：`reverse/examples/game_audio_cleanup_probe.c`。
衰减探针：`reverse/examples/game_audio_volume_probe.c`。

`GameAudioV4` 在 8 个 block 全部完成后关闭；`GameAudioV5` 继续验证了“立即 stop、
重新 open、再次写入、再次 stop”。两轮日志均为 `RESULT=PASS` 并正常返回菜单。

V3 只调用 `SYS+0x0a0` 的反例：

```text
playing=true  timer_running=true
dma_completion_count=8  dma_rearm_count=7
audio packets continued increasing
```

V4/V5 调用完整 stop 后：

```text
playing=false  timer_running=false
dma_completion_count=8  dma_rearm_count=7
audio packets stopped at 166
AICFR=0x00001830  AICCR=0x00094800
```

V5 第二轮 reopen/write/stop 后累计 DMA 为 `11/10`，音频包固定在 160，连续观测
15 秒没有增长，应用正常返回“背单词”菜单。

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
