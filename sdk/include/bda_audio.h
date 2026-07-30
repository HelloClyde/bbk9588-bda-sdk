#ifndef BDA_AUDIO_H
#define BDA_AUDIO_H

#include "bda_types.h"
#include "bda/detail/runtime.h"
#include "bda_hardware.h"

/* Dynamically verified raw PCM format on the kj409588/C200 firmware. */
#define BDA_AUDIO_SAMPLE_RATE_22050 22050u
#define BDA_AUDIO_BITS_16           16u
#define BDA_AUDIO_CHANNELS_MONO      1u

/* Capture format and DMA read size shared by the supported profiles. */
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

/*
 * Exact capture firmware profiles. Numeric values preserve the original
 * C200/JZ4730 public identifier and the first multi-firmware implementation.
 */
#define BDA_AUDIO_CAPTURE_FIRMWARE_NONE          0u
#define BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4730   1u
#define BDA_AUDIO_CAPTURE_FIRMWARE_9688_JZ4730   2u
#define BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4720   3u
#define BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4740   4u
#define BDA_AUDIO_CAPTURE_FIRMWARE_9688_JZ4740   5u

/* Backward-compatible name for the original verified capture profile. */
#define BDA_AUDIO_CAPTURE_FIRMWARE_C200KNL_V1 \
    BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4730

#define BDA_AUDIO_CAPTURE_SUPPORT_NONE             0u
#define BDA_AUDIO_CAPTURE_SUPPORT_STATIC_CANDIDATE 1u
#define BDA_AUDIO_CAPTURE_SUPPORT_HARDWARE_VERIFIED 2u

typedef struct bda_audio_capture_profile {
    u32 firmware;
    u32 device_model;
    u32 chip_model;
    u32 support_level;
    const char *name;
} bda_audio_capture_profile_t;

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

#define BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE 0x43415031u

/*
 * Capture uses firmware-private recorder functions, not stable system-table
 * entries. Every profile is gated by public hardware detection and exact
 * machine-code signatures before any private function is called.
 *
 * Hardware-verified C200knl.bin:
 * dc41701442176ba81bf1b8041b2f9dac449e04f2adf6532993e7c55471de9bea
 *
 * Exact raw recovery payloads:
 * 9588/JZ4720 469a833e8984e8c4c531a411955edc38f5fb57c6089b8694f522f995dbe66c49
 * 9588/JZ4730 c7a4ba34d5a4c006f88b7e9e0c0a991b2b1e7a1ec8896859f0cc3dfb18e44270
 * 9588/JZ4740 02a16107b11a3281067871c6fe3d4c289c910d8dfa9924573dd87f00351d6525
 * 9688/JZ4730 b18ce485a6ca6a8ea9ef5e3963d5970188ff7a2aeb4a6d4e58fe43625f49e514
 * 9688/JZ4740 7ec707b69a1f4fa7016856b2eba6900412d02d7daefc8b4d11654c63731abca0
 */
typedef struct bda_audio_internal_capture_profile {
    bda_audio_capture_profile_t info;
    u32 capture_init;
    u32 capture_read;
    u32 capture_ready;
    u32 capture_stop;
    u32 capture_init_takes_format;
} bda_audio_internal_capture_profile_t;

static const bda_audio_internal_capture_profile_t
bda_audio_internal_profile_9588_jz4730 = {
    {
        BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4730,
        BDA_DEVICE_MODEL_9588,
        BDA_CHIP_MODEL_JZ4730,
        BDA_AUDIO_CAPTURE_SUPPORT_HARDWARE_VERIFIED,
        "9588/C200 JZ4730"
    },
    0x80199d4cu,
    0x80199290u,
    0x8019a088u,
    0x80199a6cu,
    0u
};

static const bda_audio_internal_capture_profile_t
bda_audio_internal_profile_9688_jz4730 = {
    {
        BDA_AUDIO_CAPTURE_FIRMWARE_9688_JZ4730,
        BDA_DEVICE_MODEL_9688,
        BDA_CHIP_MODEL_JZ4730,
        BDA_AUDIO_CAPTURE_SUPPORT_STATIC_CANDIDATE,
        "9688/C100 JZ4730"
    },
    0x801a169cu,
    0x801a04d0u,
    0x801a19d8u,
    0x801a13bcu,
    0u
};

static const bda_audio_internal_capture_profile_t
bda_audio_internal_profile_9588_jz4720 = {
    {
        BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4720,
        BDA_DEVICE_MODEL_9588,
        BDA_CHIP_MODEL_JZ4720,
        BDA_AUDIO_CAPTURE_SUPPORT_STATIC_CANDIDATE,
        "9588/C200 JZ4720"
    },
    0x801967f0u,
    0x80195d84u,
    0x80196cccu,
    0x8018b0d8u,
    1u
};

static const bda_audio_internal_capture_profile_t
bda_audio_internal_profile_9588_jz4740 = {
    {
        BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4740,
        BDA_DEVICE_MODEL_9588,
        BDA_CHIP_MODEL_JZ4740,
        BDA_AUDIO_CAPTURE_SUPPORT_STATIC_CANDIDATE,
        "9588/C200 JZ4740"
    },
    0x80194900u,
    0x80193e94u,
    0x80194ddcu,
    0x801891e8u,
    1u
};

static const bda_audio_internal_capture_profile_t
bda_audio_internal_profile_9688_jz4740 = {
    {
        BDA_AUDIO_CAPTURE_FIRMWARE_9688_JZ4740,
        BDA_DEVICE_MODEL_9688,
        BDA_CHIP_MODEL_JZ4740,
        BDA_AUDIO_CAPTURE_SUPPORT_STATIC_CANDIDATE,
        "9688/C100 JZ4740"
    },
    0x8019e400u,
    0x8019d284u,
    0x8019eb88u,
    0x801925d8u,
    1u
};

static inline int bda_audio_internal_words_match(
    u32 address,
    u32 word0,
    u32 word1,
    u32 word2,
    u32 word3
) {
    const volatile u32 *code = (const volatile u32 *)address;

    return code[0] == word0 &&
        code[1] == word1 &&
        code[2] == word2 &&
        code[3] == word3;
}

static inline int bda_audio_internal_capture_read_matches(u32 address) {
    return bda_audio_internal_words_match(
        address,
        0x27bdffb8u,
        0xafbe0040u,
        0xafb50034u,
        0xafb40030u
    );
}

static inline int bda_audio_internal_jz4730_stop_matches(u32 address) {
    return bda_audio_internal_words_match(
        address,
        0x3c03b001u,
        0x34630080u,
        0x8c620000u,
        0x2406fffbu
    );
}

static inline int bda_audio_internal_musb_stop_matches(
    u32 address, u32 first_call
) {
    return bda_audio_internal_words_match(
        address,
        0x27bdffe8u,
        0xafbf0010u,
        first_call,
        0x00000000u
    );
}

static inline int bda_audio_internal_profile_matches_9588_jz4730(void) {
    void *sys = bda_sdk_internal_sys();

    if (
        (u32)bda_sdk_internal_api(sys, BDA_AUDIO_INTERNAL_OPEN) !=
            0x80199ad0u ||
        (u32)bda_sdk_internal_api(sys, BDA_AUDIO_INTERNAL_READY) !=
            0x8019a050u ||
        (u32)bda_sdk_internal_api(sys, BDA_AUDIO_INTERNAL_WRITE) !=
            0x80199720u
    ) {
        return 0;
    }
    return bda_audio_internal_words_match(
            0x80199d4cu,
            0x27bdffe0u,
            0xafbf001cu,
            0x0c0669f2u,
            0xafb00018u
        ) &&
        bda_audio_internal_capture_read_matches(0x80199290u) &&
        bda_audio_internal_jz4730_stop_matches(0x80199a6cu) &&
        bda_audio_internal_words_match(
            0x8019a088u,
            0x27bdffe8u,
            0xafbf0014u,
            0x0c001356u,
            0xafb00010u
        );
}

static inline int bda_audio_internal_profile_matches_9688_jz4730(void) {
    return bda_audio_internal_words_match(
            0x801a169cu,
            0x27bdffe0u,
            0xafbf001cu,
            0x0c068846u,
            0xafb00018u
        ) &&
        bda_audio_internal_capture_read_matches(0x801a04d0u) &&
        bda_audio_internal_jz4730_stop_matches(0x801a13bcu) &&
        bda_audio_internal_words_match(
            0x801a19d8u,
            0x27bdffe8u,
            0xafbf0014u,
            0x0c001356u,
            0xafb00010u
        );
}

static inline int bda_audio_internal_profile_matches_9588_jz4720(void) {
    const volatile u32 *ready = (const volatile u32 *)0x80196cccu;

    return bda_audio_internal_words_match(
            0x801967f0u,
            0x27bdffd0u,
            0x00052e00u,
            0x00063600u,
            0xafbf002cu
        ) &&
        bda_audio_internal_capture_read_matches(0x80195d84u) &&
        bda_audio_internal_musb_stop_matches(
            0x8018b0d8u, 0x0c065f28u
        ) &&
        ready[0] == 0x27bdffe8u &&
        ready[1] == 0xafbf0014u &&
        ready[4] == 0x3c108058u &&
        ready[5] == 0x8e102d98u;
}

static inline int bda_audio_internal_profile_matches_9588_jz4740(void) {
    const volatile u32 *ready = (const volatile u32 *)0x80194ddcu;

    return bda_audio_internal_words_match(
            0x80194900u,
            0x27bdffd0u,
            0x00052e00u,
            0x00063600u,
            0xafbf002cu
        ) &&
        bda_audio_internal_capture_read_matches(0x80193e94u) &&
        bda_audio_internal_musb_stop_matches(
            0x801891e8u, 0x0c06576cu
        ) &&
        ready[0] == 0x27bdffe8u &&
        ready[1] == 0xafbf0014u &&
        ready[4] == 0x3c108058u &&
        ready[5] == 0x8e100748u;
}

static inline int bda_audio_internal_profile_matches_9688_jz4740(void) {
    const volatile u32 *ready = (const volatile u32 *)0x8019eb88u;

    return bda_audio_internal_words_match(
            0x8019e400u,
            0x27bdffd0u,
            0x00052e00u,
            0x00063600u,
            0xafbf002cu
        ) &&
        bda_audio_internal_capture_read_matches(0x8019d284u) &&
        bda_audio_internal_musb_stop_matches(
            0x801925d8u, 0x0c067ed8u
        ) &&
        ready[0] == 0x27bdffe8u &&
        ready[1] == 0xafbf0014u &&
        ready[4] == 0x3c10805bu &&
        ready[5] == 0x8e106358u;
}

static inline const bda_audio_internal_capture_profile_t *
bda_audio_internal_capture_profile_by_firmware(u32 firmware) {
    switch (firmware) {
        case BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4730:
            return &bda_audio_internal_profile_9588_jz4730;
        case BDA_AUDIO_CAPTURE_FIRMWARE_9688_JZ4730:
            return &bda_audio_internal_profile_9688_jz4730;
        case BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4720:
            return &bda_audio_internal_profile_9588_jz4720;
        case BDA_AUDIO_CAPTURE_FIRMWARE_9588_JZ4740:
            return &bda_audio_internal_profile_9588_jz4740;
        case BDA_AUDIO_CAPTURE_FIRMWARE_9688_JZ4740:
            return &bda_audio_internal_profile_9688_jz4740;
        default:
            return 0;
    }
}

static inline const bda_audio_internal_capture_profile_t *
bda_audio_internal_capture_profile_detect(void) {
    static const bda_audio_internal_capture_profile_t *cached_profile;
    static u32 detection_complete;
    bda_hardware_info_t hardware;

    if (cached_profile != 0) {
        return cached_profile;
    }
    if (detection_complete != 0u || bda_sdk_internal_sys() == 0) {
        return 0;
    }

    bda_detect_hardware(&hardware);
    if (
        hardware.device_model == BDA_DEVICE_MODEL_9588 &&
        hardware.chip_model == BDA_CHIP_MODEL_JZ4730 &&
        bda_audio_internal_profile_matches_9588_jz4730()
    ) {
        cached_profile = &bda_audio_internal_profile_9588_jz4730;
    } else if (
        hardware.device_model == BDA_DEVICE_MODEL_9688 &&
        hardware.chip_model == BDA_CHIP_MODEL_JZ4730 &&
        bda_audio_internal_profile_matches_9688_jz4730()
    ) {
        cached_profile = &bda_audio_internal_profile_9688_jz4730;
    } else if (
        hardware.device_model == BDA_DEVICE_MODEL_9588 &&
        hardware.chip_model == BDA_CHIP_MODEL_JZ4720 &&
        bda_audio_internal_profile_matches_9588_jz4720()
    ) {
        cached_profile = &bda_audio_internal_profile_9588_jz4720;
    } else if (
        hardware.device_model == BDA_DEVICE_MODEL_9588 &&
        hardware.chip_model == BDA_CHIP_MODEL_JZ4740 &&
        bda_audio_internal_profile_matches_9588_jz4740()
    ) {
        cached_profile = &bda_audio_internal_profile_9588_jz4740;
    } else if (
        hardware.device_model == BDA_DEVICE_MODEL_9688 &&
        hardware.chip_model == BDA_CHIP_MODEL_JZ4740 &&
        bda_audio_internal_profile_matches_9688_jz4740()
    ) {
        cached_profile = &bda_audio_internal_profile_9688_jz4740;
    }

    detection_complete = 1u;
    return cached_profile;
}

/*
 * Return the exact current capture profile after hardware and firmware
 * signature checks, or null when the image is unsupported.
 */
static inline const bda_audio_capture_profile_t *
bda_audio_capture_profile(void) {
    const bda_audio_internal_capture_profile_t *profile =
        bda_audio_internal_capture_profile_detect();

    return profile != 0 ? &profile->info : 0;
}

/* Return a supported firmware identifier, or FIRMWARE_NONE. */
static inline u32 bda_audio_capture_firmware(void) {
    const bda_audio_capture_profile_t *profile =
        bda_audio_capture_profile();

    return profile != 0
        ? profile->firmware
        : BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
}

static inline int bda_audio_capture_is_supported(void) {
    return bda_audio_capture_profile() != 0;
}

/*
 * Open the fixed 16000 Hz, signed 16-bit, mono capture path. Only one capture
 * may be active. Unsupported firmware is rejected before any private call.
 */
static inline int bda_audio_capture_open(bda_audio_capture_t *capture) {
    typedef int (*capture_init_fn_t)(void);
    typedef void (*capture_init_format_fn_t)(u32, u32, u32);
    const bda_audio_internal_capture_profile_t *profile;
    int result;

    if (capture == 0) {
        return BDA_AUDIO_CAPTURE_INVALID_ARGUMENT;
    }
    if (capture->state == BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE) {
        return BDA_AUDIO_CAPTURE_INVALID_STATE;
    }
    capture->firmware = BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
    capture->state = 0u;

    profile = bda_audio_internal_capture_profile_detect();
    if (profile == 0) {
        return BDA_AUDIO_CAPTURE_UNSUPPORTED;
    }
    if (profile->capture_init_takes_format != 0u) {
        capture_init_format_fn_t init_format_fn =
            (capture_init_format_fn_t)profile->capture_init;
        init_format_fn(
            BDA_AUDIO_CAPTURE_SAMPLE_RATE_16000,
            BDA_AUDIO_CAPTURE_BITS_16,
            BDA_AUDIO_CAPTURE_CHANNELS_MONO
        );
        result = 0;
    } else {
        capture_init_fn_t init_fn =
            (capture_init_fn_t)profile->capture_init;
        result = init_fn();
    }
    if (result != 0) {
        return BDA_AUDIO_CAPTURE_IO_ERROR;
    }

    capture->firmware = profile->info.firmware;
    capture->state = BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE;
    return BDA_AUDIO_CAPTURE_OK;
}

/*
 * Poll the firmware recorder queue. Return 1 when one full capture block can
 * be read without waiting, 0 when no block is ready, or a negative API error.
 */
static inline int bda_audio_capture_ready(
    const bda_audio_capture_t *capture
) {
    typedef int (*capture_ready_fn_t)(void);
    const bda_audio_internal_capture_profile_t *profile;
    capture_ready_fn_t ready_fn;

    if (capture == 0) {
        return BDA_AUDIO_CAPTURE_INVALID_ARGUMENT;
    }
    if (capture->state != BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE) {
        return BDA_AUDIO_CAPTURE_INVALID_STATE;
    }
    profile = bda_audio_internal_capture_profile_by_firmware(
        capture->firmware
    );
    if (profile == 0) {
        return BDA_AUDIO_CAPTURE_UNSUPPORTED;
    }

    ready_fn = (capture_ready_fn_t)profile->capture_ready;
    return ready_fn() != 0 ? 1 : 0;
}

/*
 * Blocking capture read. The first call starts DMA and waits for one complete
 * 4096-byte block. Later calls may be gated with bda_audio_capture_ready().
 */
static inline int bda_audio_capture_read(
    bda_audio_capture_t *capture, void *pcm, bda_size_t bytes
) {
    typedef int (*capture_read_fn_t)(void *, bda_size_t);
    const bda_audio_internal_capture_profile_t *profile;
    capture_read_fn_t read_fn;
    int result;

    if (
        capture == 0 ||
        pcm == 0 ||
        bytes != BDA_AUDIO_CAPTURE_BLOCK_BYTES ||
        ((u32)pcm & 1u) != 0u
    ) {
        return BDA_AUDIO_CAPTURE_INVALID_ARGUMENT;
    }
    if (capture->state != BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE) {
        return BDA_AUDIO_CAPTURE_INVALID_STATE;
    }
    profile = bda_audio_internal_capture_profile_by_firmware(
        capture->firmware
    );
    if (profile == 0) {
        return BDA_AUDIO_CAPTURE_UNSUPPORTED;
    }

    read_fn = (capture_read_fn_t)profile->capture_read;
    result = read_fn(pcm, bytes);
    if (result < 0 || (u32)result > bytes) {
        return BDA_AUDIO_CAPTURE_IO_ERROR;
    }
    return result;
}

/* Stop a successfully opened capture. */
static inline int bda_audio_capture_stop(bda_audio_capture_t *capture) {
    typedef void (*capture_stop_fn_t)(void);
    const bda_audio_internal_capture_profile_t *profile;
    capture_stop_fn_t stop_fn;

    if (capture == 0) {
        return BDA_AUDIO_CAPTURE_INVALID_ARGUMENT;
    }
    if (capture->state != BDA_AUDIO_INTERNAL_CAPTURE_OPEN_STATE) {
        return BDA_AUDIO_CAPTURE_INVALID_STATE;
    }
    profile = bda_audio_internal_capture_profile_by_firmware(
        capture->firmware
    );
    if (profile == 0) {
        return BDA_AUDIO_CAPTURE_UNSUPPORTED;
    }

    capture->firmware = BDA_AUDIO_CAPTURE_FIRMWARE_NONE;
    capture->state = 0u;
    stop_fn = (capture_stop_fn_t)profile->capture_stop;
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
