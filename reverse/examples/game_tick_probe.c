#include "../bda_research_sdk.h"

#define TARGET_RAW_TICKS 40u
#define MAX_POLL_COUNT 2000000u

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMETICK.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMETICK.TXT";

static const char *g_log_path;
static char g_line[128];

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
    while (count > 0 && out < end) {
        *out++ = digits[--count];
    }
    return out;
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char hex[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0 && out < end; shift -= 4) {
        *out++ = hex[(value >> shift) & 0x0fu];
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

static void write_line(char *out) {
    int file;
    u32 length;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "\r\n");
    *out = 0;
    length = (u32)(out - g_line);
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

static void log_sample(u32 start, u32 end, u32 polls) {
    char *out = g_line;
    char *limit = g_line + sizeof(g_line) - 1;
    u32 elapsed = bda_gui_tick_elapsed_25ms_like(start, end);

    out = append_text(out, limit, "END=");
    out = append_hex32(out, limit, end);
    out = append_text(out, limit, " RAW_DELTA=");
    out = append_u32(out, limit, elapsed);
    out = append_text(out, limit, " MS=");
    out = append_u32(out, limit, bda_gui_tick_elapsed_ms_like(start, end));
    out = append_text(out, limit, " POLLS=");
    out = append_u32(out, limit, polls);
    write_line(out);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u32 start;
    u32 previous;
    u32 current;
    u32 polls = 0;
    int failures = 0;

    reset_log();
    log_text("START GAME TICK PROBE V9");
    start = bda_gui_tick_count_25ms_like();
    previous = start;
    log_value("START=", start);

    do {
        current = bda_gui_tick_count_25ms_like();
        if (current != previous) {
            u32 step = current - previous;
            if (step >= 0x80000000u) {
                ++failures;
                log_text("MONOTONIC=FAIL");
                break;
            }
            previous = current;
        }
        bda_sys_delay_like(1);
        ++polls;
    } while (
        bda_gui_tick_elapsed_25ms_like(start, current) < TARGET_RAW_TICKS &&
        polls < MAX_POLL_COUNT
    );

    log_sample(start, current, polls);
    if (bda_gui_tick_elapsed_25ms_like(start, current) < TARGET_RAW_TICKS) {
        ++failures;
        log_text("ADVANCE=FAIL");
    } else {
        log_text("ADVANCE=PASS");
    }
    if (bda_gui_tick_elapsed_25ms_like(0xfffffff0u, 0x10u) != 0x20u) {
        ++failures;
        log_text("WRAP=FAIL");
    } else {
        log_text("WRAP=PASS");
    }
    log_value("FAILURES=", (u32)failures);
    log_text(failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END GAME TICK PROBE V9");
    return failures ? 1 : 0;
}
