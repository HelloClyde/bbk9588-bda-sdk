#ifndef BDA_AUDIO_H
#define BDA_AUDIO_H

#include "bda_sdk.h"

/* Dynamically verified raw PCM format on the kj409588/C200 firmware. */
#define BDA_AUDIO_SAMPLE_RATE_22050 22050u
#define BDA_AUDIO_BITS_16           16u
#define BDA_AUDIO_CHANNELS_MONO      1u

/* PCM attenuation: 0 is full scale, 96 is near-silent, in steps of 3. */
#define BDA_AUDIO_ATTENUATION_FULL_SCALE  0u
#define BDA_AUDIO_ATTENUATION_HALF_SCALE 48u
#define BDA_AUDIO_ATTENUATION_NEAR_SILENT 96u
#define BDA_AUDIO_ATTENUATION_STEP        3u

#define BDA_AUDIO_INTERNAL_ATTENUATION_SET 0x040u
#define BDA_AUDIO_INTERNAL_ATTENUATION_GET 0x044u
#define BDA_AUDIO_INTERNAL_OPEN       0x06cu
#define BDA_AUDIO_INTERNAL_READY      0x074u
#define BDA_AUDIO_INTERNAL_WRITE      0x078u
#define BDA_AUDIO_INTERNAL_FINISH     0x0a0u

/*
 * Queue attenuation for the next PCM write. Firmware clamps to 0..98 and
 * applies floor(value / 3) * 3, so callers should use the constants above.
 */
static inline void bda_audio_set_attenuation(u32 attenuation) {
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_sys(),
        BDA_AUDIO_INTERNAL_ATTENUATION_SET,
        attenuation
    );
}

/* Return the currently applied PCM attenuation in the effective 0..96 range. */
static inline int bda_audio_get_attenuation(void) {
    typedef int (*fn_t)(void);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_sys(), BDA_AUDIO_INTERNAL_ATTENUATION_GET
    );
    return fn();
}

/* Open the verified 22050 Hz, signed 16-bit, mono raw PCM stream. */
static inline void bda_audio_open_pcm(
    u32 sample_rate_hz, u32 bits_per_sample, u32 channels
) {
    typedef void (*fn_t)(u32, u32, u32);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_sys(), BDA_AUDIO_INTERNAL_OPEN
    );
    fn(sample_rate_hz, bits_per_sample, channels);
}

/* Nonzero means at least one firmware queue slot can accept more PCM. */
static inline int bda_audio_ready(void) {
    typedef int (*fn_t)(void);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_sys(), BDA_AUDIO_INTERNAL_READY
    );
    return fn();
}

/* Return the consumed byte count, or a negative value on failure. */
static inline int bda_audio_write(const void *pcm, bda_size_t bytes) {
    return bda_sdk_internal_call2(
        bda_sdk_internal_sys(),
        BDA_AUDIO_INTERNAL_WRITE,
        (u32)pcm,
        bytes
    );
}

/* Stop raw PCM through the true-hardware-verified SYS+0x0a0 service. */
static inline void bda_audio_stop(void) {
    typedef void (*finish_fn_t)(void);
    finish_fn_t finish_fn = (finish_fn_t)bda_sdk_internal_api(
        bda_sdk_internal_sys(), BDA_AUDIO_INTERNAL_FINISH
    );

    finish_fn();
}

#endif
