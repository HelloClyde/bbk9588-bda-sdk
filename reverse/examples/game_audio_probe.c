#include "../bda_research_sdk.h"

typedef signed short s16;

#define PCM_SAMPLES 512u
#define PCM_BYTES (PCM_SAMPLES * (u32)sizeof(s16))
#define PCM_WRITES 8u
#define READY_POLL_LIMIT 1000000u

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEAUDIO.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEAUDIO.TXT";

static const char *g_log_path;
static char g_line[160];
static s16 g_pcm[PCM_SAMPLES];

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

static char *append_hex32(char *out, char *end, u32 value) {
    static const char hex[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        out = append_char(out, end, hex[(value >> shift) & 0x0fu]);
    }
    return out;
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

static void log_value(const char *label, u32 value) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, value);
    write_line(out);
}

static void fill_square_wave(u32 phase) {
    u32 i;

    for (i = 0; i < PCM_SAMPLES; ++i) {
        u32 cycle = (i + phase) % 50u;
        g_pcm[i] = cycle < 25u ? (s16)4096 : (s16)-4096;
    }
}

static int wait_audio_ready(u32 *polls_out) {
    u32 polls = 0;

    while (!bda_sys_audio_ready_like() && polls < READY_POLL_LIMIT) {
        ++polls;
    }
    *polls_out = polls;
    return polls < READY_POLL_LIMIT;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u32 write_index;
    int failures = 0;

    reset_log();
    log_text("START GAME AUDIO PROBE V2");
    log_value("STATE BEFORE=", (u32)bda_sys_audio_state_like());
    log_value("READY BEFORE=", (u32)bda_sys_audio_ready_like());

    log_text("BEFORE OPEN 22050/16/1");
    bda_sys_audio_open_like(22050u, 16u, 1u);
    log_text("OPEN RETURNED");
    log_value("STATE AFTER=", (u32)bda_sys_audio_state_like());
    log_value("READY AFTER=", (u32)bda_sys_audio_ready_like());

    for (write_index = 0; write_index < PCM_WRITES; ++write_index) {
        u32 polls;
        int ready;
        int written;
        char *out = g_line;
        char *end = g_line + sizeof(g_line) - 1;

        ready = wait_audio_ready(&polls);
        if (!ready) {
            out = append_text(out, end, "WRITE ");
            out = append_u32(out, end, write_index);
            out = append_text(out, end, " READY=TIMEOUT");
            write_line(out);
            ++failures;
            break;
        }
        fill_square_wave(write_index * 7u);
        written = bda_sys_audio_write_like(g_pcm, PCM_BYTES);
        out = append_text(out, end, "WRITE ");
        out = append_u32(out, end, write_index);
        out = append_text(out, end, " POLLS=");
        out = append_u32(out, end, polls);
        out = append_text(out, end, " BYTES=");
        out = append_hex32(out, end, (u32)written);
        write_line(out);
        if (written != (int)PCM_BYTES) {
            ++failures;
            break;
        }
    }

    log_text("BEFORE FLUSH");
    bda_sys_audio_flush_like();
    log_text("FLUSH RETURNED");
    log_text("BEFORE RESET");
    bda_sys_audio_reset_like();
    log_text("RESET RETURNED");
    log_value("FAILURES=", (u32)failures);
    log_text(failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END GAME AUDIO PROBE V2");
    return failures ? 1 : 0;
}
