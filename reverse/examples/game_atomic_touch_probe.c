#include "../bda_research_sdk.h"

#define EMPTY_BENCH_CALLS 50000u
#define STARTUP_DRAIN_LIMIT 4096u
#define EVENT_CODE_LIMIT 16u

static const char k_log_path[] = "A:\\ATOUCH.TXT";
static char g_line[192];

static char *append_char(char *out, char *end, char value) {
    if (out < end) {
        *out++ = value;
    }
    return out;
}

static char *append_text(char *out, char *end, const char *text) {
    while (*text) {
        out = append_char(out, end, *text++);
    }
    return out;
}

static char *append_u32(char *out, char *end, u32 value) {
    char digits[10];
    int count = 0;

    if (value == 0u) {
        return append_char(out, end, '0');
    }
    while (value != 0u && count < (int)sizeof(digits)) {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    }
    while (count > 0) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static char *append_s32(char *out, char *end, s32 value) {
    if (value < 0) {
        out = append_char(out, end, '-');
        return append_u32(out, end, (u32)(0 - value));
    }
    return append_u32(out, end, (u32)value);
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char digits[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        out = append_char(out, end, digits[(value >> shift) & 0x0fu]);
    }
    return out;
}

static u32 text_length(const char *text) {
    u32 length = 0u;
    while (text[length] != 0) {
        ++length;
    }
    return length;
}

static void write_line(const char *mode, const char *text) {
    static const char newline[] = "\r\n";
    int file = bda_fs_fopen_raw(k_log_path, mode);

    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, text, text_length(text));
    (void)bda_fs_write_raw(file, newline, 2u);
    (void)bda_fs_close_raw(file);
}

static void log_event(
    const char *prefix,
    u32 index,
    int result,
    const bda_gui_event_fetch_like_t *event
) {
    u16 x = 0xffffu;
    u16 y = 0xffffu;
    int pen_down = bda_touch_pressed_9588() != 0;
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    bda_gui_touch_position_like(&x, &y);
    out = append_text(out, end, prefix);
    out = append_text(out, end, " N=");
    out = append_u32(out, end, index);
    out = append_text(out, end, " RET=");
    out = append_s32(out, end, result);
    out = append_text(out, end, " CODE=");
    out = append_s32(out, end, event->code);
    out = append_text(out, end, " VALUE=");
    out = append_hex32(out, end, (u32)event->value);
    out = append_text(out, end, " PEN=");
    out = append_u32(out, end, (u32)pen_down);
    out = append_text(out, end, " X=");
    out = append_u32(out, end, (u32)x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, (u32)y);
    *out = 0;
    write_line("ab", g_line);
}

static void log_benchmark(u32 elapsed, u32 code3_events, u32 other_events) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "EMPTY BENCH CALLS=");
    out = append_u32(out, end, EMPTY_BENCH_CALLS);
    out = append_text(out, end, " MS=");
    out = append_u32(out, end, elapsed);
    out = append_text(out, end, " CODE3=");
    out = append_u32(out, end, code3_events);
    out = append_text(out, end, " OTHER=");
    out = append_u32(out, end, other_events);
    *out = 0;
    write_line("ab", g_line);
}

static void log_pen_benchmark(u32 elapsed, u32 calls, u32 down_samples) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "PEN BENCH CALLS=");
    out = append_u32(out, end, calls);
    out = append_text(out, end, " MS=");
    out = append_u32(out, end, elapsed);
    out = append_text(out, end, " DOWN=");
    out = append_u32(out, end, down_samples);
    *out = 0;
    write_line("ab", g_line);
}

static void log_pen_heartbeat(u32 elapsed, u32 samples, u32 transitions) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "HEARTBEAT MS=");
    out = append_u32(out, end, elapsed);
    out = append_text(out, end, " SAMPLES=");
    out = append_u32(out, end, samples);
    out = append_text(out, end, " TRANSITIONS=");
    out = append_u32(out, end, transitions);
    *out = 0;
    write_line("ab", g_line);
}

static void log_heartbeat(
    u32 elapsed,
    u32 fetch_calls,
    u32 empty_events,
    u32 code3_events
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "HEARTBEAT MS=");
    out = append_u32(out, end, elapsed);
    out = append_text(out, end, " FETCH=");
    out = append_u32(out, end, fetch_calls);
    out = append_text(out, end, " EMPTY=");
    out = append_u32(out, end, empty_events);
    out = append_text(out, end, " CODE3=");
    out = append_u32(out, end, code3_events);
    *out = 0;
    write_line("ab", g_line);
}

static void log_state(u32 elapsed, int state) {
    u16 x = 0xffffu;
    u16 y = 0xffffu;
    int pen_down = bda_touch_pressed_9588() != 0;
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    bda_gui_touch_position_like(&x, &y);
    out = append_text(out, end, "STATE MS=");
    out = append_u32(out, end, elapsed);
    out = append_text(out, end, " VALUE=");
    out = append_hex32(out, end, (u32)state);
    out = append_text(out, end, " PEN=");
    out = append_u32(out, end, (u32)pen_down);
    out = append_text(out, end, " X=");
    out = append_u32(out, end, (u32)x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, (u32)y);
    *out = 0;
    write_line("ab", g_line);
}

static void log_pen(u32 elapsed, int pen_down, u16 x, u16 y) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, pen_down ? "PEN DOWN MS=" : "PEN UP MS=");
    out = append_u32(out, end, elapsed);
    out = append_text(out, end, " X=");
    out = append_u32(out, end, (u32)x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, (u32)y);
    *out = 0;
    write_line("ab", g_line);
}

static void log_code_counts(const u32 *counts) {
    u32 code;
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "COUNTS");
    for (code = 0u; code < EVENT_CODE_LIMIT; ++code) {
        if (counts[code] != 0u) {
            out = append_text(out, end, " C");
            out = append_u32(out, end, code);
            out = append_char(out, end, '=');
            out = append_u32(out, end, counts[code]);
        }
    }
    *out = 0;
    write_line("ab", g_line);
}

static void wait_escape_release(void) {
    bda_gui_input_packet_like_t packet;

    do {
        (void)bda_gui_input_packet_like(&packet);
    } while (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE));
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_gui_input_packet_like_t packet;
    const u32 benchmark_calls = 100000u;
    u32 benchmark_down = 0u;
    u32 samples = 0u;
    u32 transitions = 0u;
    u32 last_heartbeat;
    u32 start;
    u32 end;
    u32 calls;
    int last_pen = -1;
    u16 last_x = 0xffffu;
    u16 last_y = 0xffffu;

    write_line("wb", "START GAME ATOMIC TOUCH PROBE V6");
    bda_gui_millisecond_timer_start_like();

    start = bda_gui_millisecond_count_like();
    for (calls = 0u; calls < benchmark_calls; ++calls) {
        if (bda_touch_pressed_9588()) {
            ++benchmark_down;
        }
    }
    end = bda_gui_millisecond_count_like();
    log_pen_benchmark(end - start, benchmark_calls, benchmark_down);
    write_line("ab", "READY");
    start = end;
    last_heartbeat = end;

    for (;;) {
        u32 now;
        int pen_down;
        u16 x = last_x;
        u16 y = last_y;

        now = bda_gui_millisecond_count_like();
        ++samples;
        pen_down = bda_touch_pressed_9588() != 0;
        if (pen_down) {
            bda_gui_touch_position_like(&x, &y);
        }
        if (pen_down != last_pen ||
            (pen_down && (x != last_x || y != last_y))) {
            log_pen(now - start, pen_down, x, y);
            ++transitions;
            last_pen = pen_down;
            last_x = x;
            last_y = y;
        }

        (void)bda_gui_input_packet_like(&packet);
        if (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE)) {
            write_line("ab", "ESC DOWN");
            wait_escape_release();
            write_line("ab", "ESC UP");
            break;
        }

        if (now - last_heartbeat >= 1000u) {
            log_pen_heartbeat(now - start, samples, transitions);
            last_heartbeat = now;
        }
    }

    bda_gui_millisecond_timer_stop_like();
    write_line("ab", "RESULT=PASS");
    write_line("ab", "END GAME ATOMIC TOUCH PROBE V6");
    return 0;
}
