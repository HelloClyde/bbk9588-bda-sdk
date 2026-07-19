#include "bda_audio.h"
#include "bda_filesystem.h"
#include "bda_time.h"

#define PCM_SAMPLE_COUNT 512u
#define PCM_BYTE_COUNT (PCM_SAMPLE_COUNT * (u32)sizeof(s16))
#define PCM_BLOCK_COUNT 8u
#define READY_POLL_LIMIT 1000000u
#define TICK_POLL_LIMIT 12000000u

#ifndef AUDIO_PCM_TRACE_START_TEXT
#define AUDIO_PCM_TRACE_START_TEXT "START AUDIO PCM TRUE HARDWARE VERIFIED V5"
#endif

#ifndef AUDIO_PCM_TRACE_RETURN_TEXT
#define AUDIO_PCM_TRACE_RETURN_TEXT "RETURN AUDIO PCM TRUE HARDWARE VERIFIED V5"
#endif

static const char g_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\AUDIOPCM.TXT";
static const char g_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\AUDIOPCM.TXT";

static s16 g_pcm[PCM_SAMPLE_COUNT];
static const char *g_log_path;
static char g_log_line[128];

static char *append_char(char *out, char *end, char value) {
    if (out < end) {
        *out++ = value;
    }
    return out;
}

static char *append_text(char *out, char *end, const char *text) {
    while (*text && out < end) {
        *out++ = *text++;
    }
    return out;
}

static char *append_u32(char *out, char *end, u32 value) {
    char digits[10];
    int count = 0;

    do {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    } while (value && count < (int)sizeof(digits));
    while (count > 0) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static int open_log(const char *mode) {
    int file;

    if (g_log_path) {
        return bda_fs_fopen_raw(g_log_path, mode);
    }
    file = bda_fs_fopen_raw(g_log_path_a, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = g_log_path_a;
        return file;
    }
    file = bda_fs_fopen_raw(g_log_path_root, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = g_log_path_root;
    }
    return file;
}

static void reset_log(void) {
    int file;

    g_log_path = 0;
    file = open_log("wb");
    if (bda_fs_file_is_valid(file)) {
        (void)bda_fs_close_raw(file);
    }
}

static void write_log_line(char *out) {
    char *end = g_log_line + sizeof(g_log_line) - 1;
    int file;
    u32 length;

    out = append_text(out, end, "\r\n");
    *out = 0;
    length = (u32)(out - g_log_line);
    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_log_line, length);
    (void)bda_fs_close_raw(file);
}

static void log_text(const char *text) {
    write_log_line(append_text(
        g_log_line, g_log_line + sizeof(g_log_line) - 1, text
    ));
}

static void log_value(const char *label, u32 value) {
    char *out = g_log_line;
    char *end = g_log_line + sizeof(g_log_line) - 1;

    out = append_text(out, end, label);
    out = append_u32(out, end, value);
    write_log_line(out);
}

static void fill_square_wave(u32 phase) {
    u32 i;

    for (i = 0; i < PCM_SAMPLE_COUNT; ++i) {
        u32 position = (i + phase) % 50u;
        g_pcm[i] = position < 25u ? (s16)4096 : (s16)-4096;
    }
}

static int wait_ready(u32 *polls_out) {
    u32 polls = 0;

    while (!bda_audio_ready() && polls < READY_POLL_LIMIT) {
        ++polls;
    }
    *polls_out = polls;
    return polls < READY_POLL_LIMIT;
}

static int wait_ticks(u32 ticks, u32 *elapsed_out, u32 *polls_out) {
    u32 start = bda_gui_tick_count_25ms();
    u32 current = start;
    u32 polls = 0;

    while (bda_gui_tick_elapsed_25ms(start, current) < ticks &&
           polls < TICK_POLL_LIMIT) {
        bda_sys_delay(1u);
        current = bda_gui_tick_count_25ms();
        ++polls;
    }
    *elapsed_out = bda_gui_tick_elapsed_25ms(start, current);
    *polls_out = polls;
    return *elapsed_out >= ticks;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u32 block;
    u32 polls;
    u32 elapsed;
    int original_attenuation;
    int result = 0;

    reset_log();
    log_text(AUDIO_PCM_TRACE_START_TEXT);
    log_text("BEFORE GET ATTENUATION");
    original_attenuation = bda_audio_get_attenuation();
    log_value("ORIGINAL ATTENUATION=", (u32)original_attenuation);

    log_text("BEFORE OPEN 22050/16/1");
    bda_audio_open_pcm(
        BDA_AUDIO_SAMPLE_RATE_22050,
        BDA_AUDIO_BITS_16,
        BDA_AUDIO_CHANNELS_MONO
    );
    log_text("AFTER OPEN");
    log_text("BEFORE SET FULL SCALE");
    bda_audio_set_attenuation(BDA_AUDIO_ATTENUATION_FULL_SCALE);
    log_text("AFTER SET FULL SCALE");
    for (block = 0; block < PCM_BLOCK_COUNT; ++block) {
        log_value("BLOCK BEGIN=", block);
        if (block == PCM_BLOCK_COUNT / 2u) {
            log_text("BEFORE SET HALF SCALE");
            bda_audio_set_attenuation(BDA_AUDIO_ATTENUATION_HALF_SCALE);
            log_text("AFTER SET HALF SCALE");
        }
        log_text("BEFORE READY");
        if (!wait_ready(&polls)) {
            log_value("READY TIMEOUT POLLS=", polls);
            result = 1;
            break;
        }
        log_value("READY POLLS=", polls);
        fill_square_wave(block * 7u);
        log_text("BEFORE WRITE");
        {
            int written = bda_audio_write(g_pcm, PCM_BYTE_COUNT);

            log_value("WRITE RETURN=", (u32)written);
            if (written != (int)PCM_BYTE_COUNT) {
                result = 1;
                break;
            }
        }
    }

    log_text("BEFORE PLAY HOLD");
    if (!wait_ticks(20u, &elapsed, &polls)) {
        log_value("PLAY HOLD TIMEOUT ELAPSED=", elapsed);
        log_value("PLAY HOLD POLLS=", polls);
        result = 1;
    } else {
        log_value("PLAY HOLD ELAPSED=", elapsed);
        log_value("PLAY HOLD POLLS=", polls);
    }

    log_text("BEFORE RESTORE READY");
    if (wait_ready(&polls)) {
        int written;

        log_value("RESTORE READY POLLS=", polls);
        bda_memset(g_pcm, 0, PCM_BYTE_COUNT);
        log_text("BEFORE RESTORE ATTENUATION");
        bda_audio_set_attenuation((u32)original_attenuation);
        log_text("AFTER RESTORE ATTENUATION");
        log_text("BEFORE SILENT WRITE");
        written = bda_audio_write(g_pcm, PCM_BYTE_COUNT);
        log_value("SILENT WRITE RETURN=", (u32)written);
        if (written != (int)PCM_BYTE_COUNT) {
            result = 1;
        }
    } else {
        log_value("RESTORE READY TIMEOUT POLLS=", polls);
        result = 1;
    }

    log_text("BEFORE AUDIO STOP");
    bda_audio_stop();
    log_text("AFTER AUDIO STOP");
    log_text("BEFORE STOP HOLD");
    if (!wait_ticks(40u, &elapsed, &polls)) {
        log_value("STOP HOLD TIMEOUT ELAPSED=", elapsed);
        log_value("STOP HOLD POLLS=", polls);
        result = 1;
    } else {
        log_value("STOP HOLD ELAPSED=", elapsed);
        log_value("STOP HOLD POLLS=", polls);
    }
    log_value("RESULT=", (u32)result);
    log_text(AUDIO_PCM_TRACE_RETURN_TEXT);
    return result;
}
