#include "bda_audio.h"

#define PCM_SAMPLE_COUNT 512u
#define PCM_BYTE_COUNT (PCM_SAMPLE_COUNT * (u32)sizeof(s16))
#define PCM_BLOCK_COUNT 8u
#define READY_POLL_LIMIT 1000000u

static s16 g_pcm[PCM_SAMPLE_COUNT];

static void fill_square_wave(u32 phase) {
    u32 i;

    for (i = 0; i < PCM_SAMPLE_COUNT; ++i) {
        u32 position = (i + phase) % 50u;
        g_pcm[i] = position < 25u ? (s16)4096 : (s16)-4096;
    }
}

static int wait_ready(void) {
    u32 polls = 0;

    while (!bda_audio_ready() && polls < READY_POLL_LIMIT) {
        ++polls;
    }
    return polls < READY_POLL_LIMIT;
}

static void wait_ticks(u32 ticks) {
    u32 start = bda_gui_tick_count_25ms();

    while (bda_gui_tick_elapsed_25ms(
        start, bda_gui_tick_count_25ms()
    ) < ticks) {
        bda_sys_delay(1u);
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u32 block;
    int original_attenuation = bda_audio_get_attenuation();
    int result = 0;

    bda_audio_open_pcm(
        BDA_AUDIO_SAMPLE_RATE_22050,
        BDA_AUDIO_BITS_16,
        BDA_AUDIO_CHANNELS_MONO
    );
    bda_audio_set_attenuation(BDA_AUDIO_ATTENUATION_FULL_SCALE);
    for (block = 0; block < PCM_BLOCK_COUNT; ++block) {
        if (block == PCM_BLOCK_COUNT / 2u) {
            bda_audio_set_attenuation(BDA_AUDIO_ATTENUATION_HALF_SCALE);
        }
        if (!wait_ready()) {
            result = 1;
            break;
        }
        fill_square_wave(block * 7u);
        if (bda_audio_write(g_pcm, PCM_BYTE_COUNT) != (int)PCM_BYTE_COUNT) {
            result = 1;
            break;
        }
    }

    wait_ticks(20u);
    if (wait_ready()) {
        bda_memset(g_pcm, 0, PCM_BYTE_COUNT);
        bda_audio_set_attenuation((u32)original_attenuation);
        if (bda_audio_write(g_pcm, PCM_BYTE_COUNT) != (int)PCM_BYTE_COUNT) {
            result = 1;
        }
    } else {
        result = 1;
    }
    bda_audio_stop();
    wait_ticks(40u);
    return result;
}
