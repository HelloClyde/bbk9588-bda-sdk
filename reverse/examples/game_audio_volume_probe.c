#include "../bda_research_sdk.h"

typedef signed short probe_s16_t;

#define C200_AUDIO_AIC_RESET_VA 0x80195b24u
#define PCM_SAMPLES 512u
#define PCM_BYTES (PCM_SAMPLES * (u32)sizeof(probe_s16_t))
#define READY_POLL_LIMIT 1000000u

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEVOL1.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEVOL1.TXT";

static const char *g_log_path;
static char g_line[192];
static probe_s16_t g_pcm[PCM_SAMPLES];

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

static char *append_s32(char *out, char *end, s32 value) {
    char digits[11];
    u32 magnitude;
    int count = 0;

    if (value < 0) {
        out = append_char(out, end, '-');
        magnitude = (u32)(-(value + 1)) + 1u;
    } else {
        magnitude = (u32)value;
    }
    do {
        digits[count++] = (char)('0' + magnitude % 10u);
        magnitude /= 10u;
    } while (magnitude && count < (int)sizeof(digits));
    while (count > 0) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static char *append_u32(char *out, char *end, u32 value) {
    return append_s32(out, end, (s32)value);
}

static int open_log(const char *mode) {
    int file;

    if (g_log_path) {
        return bda_fs_fopen_raw(g_log_path, mode);
    }
    file = bda_fs_fopen_raw(k_log_path_a, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = k_log_path_a;
        return file;
    }
    file = bda_fs_fopen_raw(k_log_path_root, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = k_log_path_root;
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

static void write_line(char *end) {
    int file;
    u32 length;

    end = append_text(end, g_line + sizeof(g_line) - 1, "\r\n");
    *end = 0;
    length = (u32)(end - g_line);
    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_line, length);
    (void)bda_fs_close_raw(file);
}

static void log_text(const char *text) {
    write_line(append_text(g_line, g_line + sizeof(g_line) - 1, text));
}

static void log_value(const char *label, s32 value) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_s32(out, end, value);
    write_line(out);
}

static void audio_volume_set_candidate(s32 value) {
    bda_sys_audio_attenuation_set_like(value);
}

static int audio_volume_get_candidate(void) {
    return bda_sys_audio_attenuation_get_like();
}

static void stop_audio(void) {
    typedef void (*reset_fn_t)(u32 mode);
    reset_fn_t reset_fn = (reset_fn_t)C200_AUDIO_AIC_RESET_VA;

    bda_sys_audio_flush_like();
    reset_fn(0u);
}

static int wait_audio_ready(u32 *polls_out) {
    u32 polls = 0;

    while (!bda_sys_audio_ready_like() && polls < READY_POLL_LIMIT) {
        ++polls;
    }
    *polls_out = polls;
    return polls < READY_POLL_LIMIT;
}

static void fill_pcm(probe_s16_t value) {
    u32 i;

    for (i = 0; i < PCM_SAMPLES; ++i) {
        g_pcm[i] = value;
    }
}

static u32 pcm_peak(void) {
    u32 peak = 0;
    u32 i;

    for (i = 0; i < PCM_SAMPLES; ++i) {
        s32 sample = g_pcm[i];
        u32 magnitude = sample < 0 ? (u32)(-sample) : (u32)sample;
        if (magnitude > peak) {
            peak = magnitude;
        }
    }
    return peak;
}

static s32 expected_volume(s32 requested) {
    if (requested < 0) {
        requested = 0;
    } else if (requested > 98) {
        requested = 98;
    }
    return (requested / 3) * 3;
}

static int run_case(s32 requested) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;
    u32 polls;
    int before;
    int after;
    int written;
    s32 expected = expected_volume(requested);

    if (!wait_audio_ready(&polls)) {
        log_text("READY TIMEOUT");
        return 1;
    }

    fill_pcm((probe_s16_t)12000);
    before = audio_volume_get_candidate();
    audio_volume_set_candidate(requested);
    written = bda_sys_audio_write_like(g_pcm, PCM_BYTES);
    after = audio_volume_get_candidate();

    out = append_text(out, end, "CASE REQ=");
    out = append_s32(out, end, requested);
    out = append_text(out, end, " BEFORE=");
    out = append_s32(out, end, before);
    out = append_text(out, end, " AFTER=");
    out = append_s32(out, end, after);
    out = append_text(out, end, " EXPECT=");
    out = append_s32(out, end, expected);
    out = append_text(out, end, " WRITTEN=");
    out = append_s32(out, end, written);
    out = append_text(out, end, " PEAK=");
    out = append_u32(out, end, pcm_peak());
    out = append_text(out, end, " POLLS=");
    out = append_u32(out, end, polls);
    write_line(out);

    return written != (int)PCM_BYTES || after != expected;
}

static int restore_volume(int original) {
    u32 polls;
    int restored;
    int written;

    if (!wait_audio_ready(&polls)) {
        log_text("RESTORE READY TIMEOUT");
        return 1;
    }
    fill_pcm(0);
    audio_volume_set_candidate(original);
    written = bda_sys_audio_write_like(g_pcm, PCM_BYTES);
    restored = audio_volume_get_candidate();
    log_value("RESTORED=", restored);
    return written != (int)PCM_BYTES || restored != expected_volume(original);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    static const s32 cases[] = {-1, 0, 1, 2, 3, 48, 97, 98, 120};
    int original;
    int failures = 0;
    u32 i;

    reset_log();
    log_text("START GAME AUDIO VOLUME PROBE V1");
    original = audio_volume_get_candidate();
    log_value("ORIGINAL=", original);

    bda_sys_audio_open_like(22050u, 16u, 1u);
    log_text("OPEN RETURNED");
    for (i = 0; i < (u32)(sizeof(cases) / sizeof(cases[0])); ++i) {
        failures += run_case(cases[i]);
    }
    failures += restore_volume(original);
    stop_audio();
    log_text("STOP RETURNED");
    log_value("FAILURES=", failures);
    log_text(failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("RETURN GAME AUDIO VOLUME PROBE V1");
    return failures ? 1 : 0;
}
