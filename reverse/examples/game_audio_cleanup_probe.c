#include "../bda_research_sdk.h"

typedef signed short s16;

#define PCM_SAMPLES 512u
#define PCM_BYTES (PCM_SAMPLES * (u32)sizeof(s16))
#define PCM_WRITES 8u
#define PCM_REOPEN_WRITES 4u
#define READY_POLL_LIMIT 1000000u
#define STOP_HOLD_TICKS 120u
#define REOPEN_PLAY_TICKS 120u
#define WAIT_POLL_LIMIT 12000000u
#define C200_AUDIO_AIC_RESET_VA 0x80195b24u

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEAUD5.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEAUD5.TXT";

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

static void log_audio_state(const char *label) {
    volatile u32 *state = (volatile u32 *)bda_sys_audio_state_like();
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;
    u32 index;

    out = append_text(out, end, label);
    out = append_text(out, end, " PTR=");
    out = append_hex32(out, end, (u32)state);
    if (state) {
        for (index = 0; index < 4u; ++index) {
            out = append_text(out, end, " W");
            out = append_u32(out, end, index);
            out = append_char(out, end, '=');
            out = append_hex32(out, end, state[index]);
        }
    }
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

static int wait_ticks(u32 ticks, u32 *elapsed_out, u32 *polls_out) {
    u32 start = bda_gui_tick_count_25ms_like();
    u32 current = start;
    u32 polls = 0;

    while ((current - start) < ticks && polls < WAIT_POLL_LIMIT) {
        bda_sys_delay_like(1u);
        current = bda_gui_tick_count_25ms_like();
        ++polls;
    }
    *elapsed_out = current - start;
    *polls_out = polls;
    return (current - start) >= ticks;
}

static int log_wait_result(const char *phase, u32 ticks) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;
    u32 elapsed;
    u32 polls;
    int ok = wait_ticks(ticks, &elapsed, &polls);

    out = append_text(out, end, phase);
    out = append_text(out, end, " ELAPSED=");
    out = append_u32(out, end, elapsed);
    out = append_text(out, end, " POLLS=");
    out = append_u32(out, end, polls);
    out = append_text(out, end, ok ? " OK" : " TIMEOUT");
    write_line(out);
    return ok;
}

static void c200_audio_aic_reset(void) {
    typedef void (*reset_fn)(u32 mode);
    reset_fn fn = (reset_fn)C200_AUDIO_AIC_RESET_VA;

    fn(0u);
}

static int write_pcm_blocks(const char *cycle, u32 count, u32 phase_base) {
    u32 write_index;
    int failures = 0;

    log_text(cycle);
    for (write_index = 0; write_index < count; ++write_index) {
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
        fill_square_wave(phase_base + write_index * 7u);
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
    return failures;
}

static void stop_audio_now(void) {
    bda_sys_audio_flush_like();
    c200_audio_aic_reset();
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int failures = 0;

    reset_log();
    log_text("START GAME AUDIO CLEANUP PROBE V5");
    log_audio_state("STATE BEFORE");
    log_value("READY BEFORE=", (u32)bda_sys_audio_ready_like());

    log_text("BEFORE OPEN 22050/16/1");
    bda_sys_audio_open_like(22050u, 16u, 1u);
    log_text("OPEN RETURNED");
    log_audio_state("STATE AFTER OPEN");
    log_value("READY AFTER OPEN=", (u32)bda_sys_audio_ready_like());

    failures += write_pcm_blocks("CYCLE 1 WRITE", PCM_WRITES, 0u);
    log_text("CYCLE 1 STOP IMMEDIATE");
    stop_audio_now();
    log_text("CYCLE 1 STOP RETURNED");
    if (!log_wait_result("CYCLE 1 STOP HOLD", STOP_HOLD_TICKS)) {
        ++failures;
    }
    log_value("READY AFTER STOP 1=", (u32)bda_sys_audio_ready_like());

    log_text("BEFORE REOPEN 22050/16/1");
    bda_sys_audio_open_like(22050u, 16u, 1u);
    log_text("REOPEN RETURNED");
    failures += write_pcm_blocks("CYCLE 2 WRITE", PCM_REOPEN_WRITES, 100u);
    if (!log_wait_result("CYCLE 2 PLAY HOLD", REOPEN_PLAY_TICKS)) {
        ++failures;
    }
    log_text("CYCLE 2 STOP");
    stop_audio_now();
    log_text("CYCLE 2 STOP RETURNED");
    if (!log_wait_result("CYCLE 2 STOP HOLD", STOP_HOLD_TICKS)) {
        ++failures;
    }
    log_value("READY FINAL=", (u32)bda_sys_audio_ready_like());
    log_audio_state("STATE FINAL");
    log_value("FAILURES=", (u32)failures);
    log_text(failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("RETURN GAME AUDIO CLEANUP PROBE V5");
    return failures ? 1 : 0;
}
