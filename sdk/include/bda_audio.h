#ifndef BDA_AUDIO_H
#define BDA_AUDIO_H

#include "bda_types.h"
#include "bda/detail/runtime.h"

/* Dynamically verified raw PCM format on the kj409588/C200 firmware. */
#define BDA_AUDIO_SAMPLE_RATE_22050 22050u
#define BDA_AUDIO_BITS_16           16u
#define BDA_AUDIO_CHANNELS_MONO      1u

/* True-hardware-verified capture format and DMA read size. */
#define BDA_AUDIO_CAPTURE_SAMPLE_RATE_16000 16000u
#define BDA_AUDIO_CAPTURE_BITS_16           16u
#define BDA_AUDIO_CAPTURE_CHANNELS_MONO      1u
#define BDA_AUDIO_CAPTURE_BLOCK_BYTES     4096u

/* Capture API results. Read returns a positive byte count on success. */
#define BDA_AUDIO_CAPTURE_OK                0
#define BDA_AUDIO_CAPTURE_UNSUPPORTED      -1
#define BDA_AUDIO_CAPTURE_INVALID_ARGUMENT -2
#define BDA_AUDIO_CAPTURE_INVALID_STATE    -3
#define BDA_AUDIO_CAPTURE_IO_ERROR         -4

#define BDA_AUDIO_CAPTURE_FIRMWARE_NONE       0u
#define BDA_AUDIO_CAPTURE_FIRMWARE_C200KNL_V1 1u

typedef struct bda_audio_capture {
    u32 firmware;
    u32 state;
} bda_audio_capture_t;

#define BDA_AUDIO_CAPTURE_INITIALIZER { 0u, 0u }

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
 * Firmware-private capture profile verified on BBK 9588 C200 hardware.
 * Supported C200knl.bin SHA-256:
 * dc41701442176ba81bf1b8041b2f9dac449e04f2adf6532993e7c55471de9bea
 *
 * These are not system-table ABI entries. Keep the exact address and machine
 * code checks below: another firmware must return UNSUPPORTED without calling
 * any of these functions.
 */
#define BDA_AUDIO_INTERNAL_C200_SYS_PCM_OPEN  0x80199ad0u
#define BDA_AUDIO_INTERNAL_C200_SYS_PCM_READY 0x8019a050u
#define BDA_AUDIO_INTERNAL_C200_SYS_PCM_WRITE 0x80199720u
#define BDA_AUDIO_INTERNAL_C200_CAPTURE_INIT  0x80199d4cu
#define BDA_AUDIO_INTERNAL_C200_CAPTURE_READ  0x80199290u
#define BDA_AUDIO_INTERNAL_C200_CAPTURE_STOP  0x80199a6cu
#define BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE 0x43415031u

/* Return a supported firmware identifier, or FIRMWARE_NONE. */
static inline u32 bda_audio_capture_firmware(void) {
    void *sys = bda_sdk_internal_sys();
    const volatile u32 *init_code;
    const volatile u32 *read_code;
    const volatile u32 *stop_code;

    if (!sys) {
        return BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
    }
    if ((u32)bda_sdk_internal_api(sys, BDA_AUDIO_INTERNAL_OPEN) !=
            BDA_AUDIO_INTERNAL_C200_SYS_PCM_OPEN ||
        (u32)bda_sdk_internal_api(sys, BDA_AUDIO_INTERNAL_READY) !=
            BDA_AUDIO_INTERNAL_C200_SYS_PCM_READY ||
        (u32)bda_sdk_internal_api(sys, BDA_AUDIO_INTERNAL_WRITE) !=
            BDA_AUDIO_INTERNAL_C200_SYS_PCM_WRITE) {
        return BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
    }

    init_code = (const volatile u32 *)BDA_AUDIO_INTERNAL_C200_CAPTURE_INIT;
    read_code = (const volatile u32 *)BDA_AUDIO_INTERNAL_C200_CAPTURE_READ;
    stop_code = (const volatile u32 *)BDA_AUDIO_INTERNAL_C200_CAPTURE_STOP;
    if (init_code[0] != 0x27bdffe0u || init_code[1] != 0xafbf001cu ||
        read_code[0] != 0x27bdffb8u || read_code[1] != 0xafbe0040u ||
        stop_code[0] != 0x3c03b001u || stop_code[1] != 0x34630080u) {
        return BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
    }
    return BDA_AUDIO_CAPTURE_FIRMWARE_C200KNL_V1;
}

static inline int bda_audio_capture_is_supported(void) {
    return bda_audio_capture_firmware() != BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
}

/*
 * Open the fixed 16000 Hz, signed 16-bit, mono capture path. Only one capture
 * may be active. Unsupported firmware is rejected before any private call.
 */
static inline int bda_audio_capture_open(bda_audio_capture_t *capture) {
    typedef int (*capture_init_fn_t)(void);
    capture_init_fn_t init_fn;
    u32 firmware;
    int result;

    if (!capture) {
        return BDA_AUDIO_CAPTURE_INVALID_ARGUMENT;
    }
    if (capture->state == BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE) {
        return BDA_AUDIO_CAPTURE_INVALID_STATE;
    }
    capture->firmware = BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
    capture->state = 0u;
    firmware = bda_audio_capture_firmware();
    if (firmware == BDA_AUDIO_CAPTURE_FIRMWARE_NONE) {
        return BDA_AUDIO_CAPTURE_UNSUPPORTED;
    }

    init_fn = (capture_init_fn_t)BDA_AUDIO_INTERNAL_C200_CAPTURE_INIT;
    result = init_fn();
    if (result != 0) {
        return BDA_AUDIO_CAPTURE_IO_ERROR;
    }
    capture->firmware = firmware;
    capture->state = BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE;
    return BDA_AUDIO_CAPTURE_OK;
}

/*
 * Blocking capture read. The first call starts DMA and waits for one complete
 * 4096-byte block; do not gate it with bda_audio_ready(), which is playback
 * state. Smaller capture reads have not yet completed true-hardware validation.
 */
static inline int bda_audio_capture_read(
    bda_audio_capture_t *capture, void *pcm, bda_size_t bytes
) {
    typedef int (*capture_read_fn_t)(void *, bda_size_t);
    capture_read_fn_t read_fn;
    int result;

    if (!capture || !pcm || bytes != BDA_AUDIO_CAPTURE_BLOCK_BYTES ||
        ((u32)pcm & 1u) != 0u) {
        return BDA_AUDIO_CAPTURE_INVALID_ARGUMENT;
    }
    if (!bda_audio_capture_is_supported()) {
        return BDA_AUDIO_CAPTURE_UNSUPPORTED;
    }
    if (capture->firmware != BDA_AUDIO_CAPTURE_FIRMWARE_C200KNL_V1 ||
        capture->state != BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE) {
        return BDA_AUDIO_CAPTURE_INVALID_STATE;
    }

    read_fn = (capture_read_fn_t)BDA_AUDIO_INTERNAL_C200_CAPTURE_READ;
    result = read_fn(pcm, bytes);
    if (result < 0 || (u32)result > bytes) {
        return BDA_AUDIO_CAPTURE_IO_ERROR;
    }
    return result;
}

/* Stop a successfully opened capture. No private call occurs when unsupported. */
static inline int bda_audio_capture_stop(bda_audio_capture_t *capture) {
    typedef void (*capture_stop_fn_t)(void);
    capture_stop_fn_t stop_fn;

    if (!capture) {
        return BDA_AUDIO_CAPTURE_INVALID_ARGUMENT;
    }
    if (!bda_audio_capture_is_supported()) {
        capture->firmware = BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
        capture->state = 0u;
        return BDA_AUDIO_CAPTURE_UNSUPPORTED;
    }
    if (capture->firmware != BDA_AUDIO_CAPTURE_FIRMWARE_C200KNL_V1 ||
        capture->state != BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE) {
        return BDA_AUDIO_CAPTURE_INVALID_STATE;
    }

    stop_fn = (capture_stop_fn_t)BDA_AUDIO_INTERNAL_C200_CAPTURE_STOP;
    capture->firmware = BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
    capture->state = 0u;
    stop_fn();
    return BDA_AUDIO_CAPTURE_OK;
}

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
