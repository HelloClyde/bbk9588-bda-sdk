#include "../bda_research_sdk.h"

#define SAMPLE_WINDOWS 4u
#define WINDOW_TICKS 8u
#define STOP_TEST_TICKS 2u
#define MAX_POLL_COUNT 4000000u

static const char k_log_path_a[] = "A:\\HRTIMER.TXT";
static const char k_log_path_root[] = "\\HRTIMER.TXT";

static const char *g_log_path;
static char g_line[192];

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

static int wait_for_tick_change(u32 previous, u32 *current, u32 *polls) {
    u32 count = 0;
    u32 value;

    do {
        value = bda_gui_tick_count_25ms_like();
        ++count;
    } while (value == previous && count < MAX_POLL_COUNT);
    *current = value;
    *polls += count;
    return value != previous;
}

static void log_window(
    u32 index,
    u32 tick_delta,
    u32 millisecond_delta,
    u32 start_millisecond,
    u32 end_millisecond,
    u32 polls
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "WINDOW=");
    out = append_u32(out, end, index);
    out = append_text(out, end, " TICKS=");
    out = append_u32(out, end, tick_delta);
    out = append_text(out, end, " MS=");
    out = append_u32(out, end, millisecond_delta);
    out = append_text(out, end, " M0=");
    out = append_u32(out, end, start_millisecond);
    out = append_text(out, end, " M1=");
    out = append_u32(out, end, end_millisecond);
    out = append_text(out, end, " POLLS=");
    out = append_u32(out, end, polls);
    write_line(out);
}

static void log_subtick(
    const char *result,
    u32 tick,
    u32 start_millisecond,
    u32 end_millisecond,
    u32 polls
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "SUBTICK=");
    out = append_text(out, end, result);
    out = append_text(out, end, " TICK=");
    out = append_u32(out, end, tick);
    out = append_text(out, end, " M0=");
    out = append_u32(out, end, start_millisecond);
    out = append_text(out, end, " M1=");
    out = append_u32(out, end, end_millisecond);
    out = append_text(out, end, " POLLS=");
    out = append_u32(out, end, polls);
    write_line(out);
}

static void log_stop_check(u32 tick_delta, u32 start_count, u32 end_count) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "STOP CHECK TICKS=");
    out = append_u32(out, end, tick_delta);
    out = append_text(out, end, " C0=");
    out = append_u32(out, end, start_count);
    out = append_text(out, end, " C1=");
    out = append_u32(out, end, end_count);
    write_line(out);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u32 index;
    u32 previous_tick;
    int failures = 0;

    reset_log();
    log_text("START HIGH RESOLUTION TIMER PROBE V4");
    log_text("BEFORE TIMER START");
    bda_gui_millisecond_timer_start_like();
    log_text("TIMER STARTED");
    log_value("MILLI START=", bda_gui_millisecond_count_like());

    previous_tick = bda_gui_tick_count_25ms_like();
    for (index = 0; index < SAMPLE_WINDOWS; ++index) {
        u32 start_tick;
        u32 end_tick;
        u32 start_millisecond;
        u32 end_millisecond;
        u32 polls = 0;
        u32 tick_delta;
        u32 millisecond_delta;

        if (!wait_for_tick_change(previous_tick, &start_tick, &polls)) {
            ++failures;
            log_text("START BOUNDARY TIMEOUT");
            break;
        }
        start_millisecond = bda_gui_millisecond_count_like();
        end_tick = start_tick;
        while ((u32)(end_tick - start_tick) < WINDOW_TICKS) {
            u32 next_tick;

            if (!wait_for_tick_change(end_tick, &next_tick, &polls)) {
                ++failures;
                log_text("END BOUNDARY TIMEOUT");
                break;
            }
            end_tick = next_tick;
        }
        end_millisecond = bda_gui_millisecond_count_like();
        tick_delta = end_tick - start_tick;
        millisecond_delta = bda_gui_millisecond_elapsed_like(
            start_millisecond,
            end_millisecond
        );
        log_window(
            index,
            tick_delta,
            millisecond_delta,
            start_millisecond,
            end_millisecond,
            polls
        );
        if (
            tick_delta != WINDOW_TICKS ||
            millisecond_delta < 190u ||
            millisecond_delta > 210u
        ) {
            ++failures;
        }
        previous_tick = end_tick;
    }

    {
        u32 start_tick;
        u32 start_millisecond;
        u32 end_millisecond;
        u32 current_tick;
        u32 polls = 0;

        if (!wait_for_tick_change(previous_tick, &start_tick, &polls)) {
            ++failures;
            log_text("SUBTICK BOUNDARY TIMEOUT");
        } else {
            start_millisecond = bda_gui_millisecond_count_like();
            end_millisecond = start_millisecond;
            current_tick = start_tick;
            while (
                end_millisecond == start_millisecond &&
                current_tick == start_tick &&
                polls < MAX_POLL_COUNT
            ) {
                end_millisecond = bda_gui_millisecond_count_like();
                current_tick = bda_gui_tick_count_25ms_like();
                ++polls;
            }
            if (
                current_tick == start_tick &&
                bda_gui_millisecond_elapsed_like(
                    start_millisecond,
                    end_millisecond
                ) > 0u
            ) {
                log_subtick(
                    "PASS",
                    start_tick,
                    start_millisecond,
                    end_millisecond,
                    polls
                );
            } else {
                ++failures;
                log_subtick(
                    "FAIL",
                    start_tick,
                    start_millisecond,
                    end_millisecond,
                    polls
                );
            }
        }
    }

    log_text("BEFORE TIMER STOP");
    bda_gui_millisecond_timer_stop_like();
    log_text("TIMER STOPPED");

    {
        u32 start_tick = bda_gui_tick_count_25ms_like();
        u32 end_tick = start_tick;
        u32 start_count = bda_gui_millisecond_count_like();
        u32 end_count;
        u32 polls = 0;

        while ((u32)(end_tick - start_tick) < STOP_TEST_TICKS) {
            u32 next_tick;

            if (!wait_for_tick_change(end_tick, &next_tick, &polls)) {
                ++failures;
                log_text("STOP CHECK TIMEOUT");
                break;
            }
            end_tick = next_tick;
        }
        end_count = bda_gui_millisecond_count_like();
        log_stop_check(end_tick - start_tick, start_count, end_count);
        if (end_count != start_count) {
            ++failures;
        }
    }

    log_value("FAILURES=", (u32)failures);
    log_text(failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END HIGH RESOLUTION TIMER PROBE V4");
    return failures ? 1 : 0;
}
