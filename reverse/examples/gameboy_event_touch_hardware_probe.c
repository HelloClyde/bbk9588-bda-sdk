#include "../bda_research_sdk.h"

#define EVENT_LOG_LIMIT 512u
#define EVENT_CODE_LIMIT 16u
#define FETCH_DRAIN_LIMIT 4u

static const char k_log_path[] = "A:\\GBEVT.TXT";
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

static void log_first_state(int state) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "FIRST STATE=");
    out = append_hex32(out, end, (u32)state);
    *out = 0;
    write_line("ab", g_line);
}

static void log_first_fetch(
    int result,
    const bda_gui_event_fetch_like_t *event
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "FIRST FETCH RET=");
    out = append_s32(out, end, result);
    out = append_text(out, end, " CODE=");
    out = append_s32(out, end, event->code);
    out = append_text(out, end, " VALUE=");
    out = append_hex32(out, end, (u32)event->value);
    *out = 0;
    write_line("ab", g_line);
}

static void log_first_position(u16 x, u16 y) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "FIRST POSITION X=");
    out = append_u32(out, end, (u32)x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, (u32)y);
    *out = 0;
    write_line("ab", g_line);
}

static void log_event(
    u32 index,
    u32 ticks,
    int result,
    int state,
    const bda_gui_event_fetch_like_t *event,
    u16 x,
    u16 y
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "EVENT N=");
    out = append_u32(out, end, index);
    out = append_text(out, end, " TICKS=");
    out = append_u32(out, end, ticks);
    out = append_text(out, end, " RET=");
    out = append_s32(out, end, result);
    out = append_text(out, end, " STATE=");
    out = append_hex32(out, end, (u32)state);
    out = append_text(out, end, " CODE=");
    out = append_s32(out, end, event->code);
    out = append_text(out, end, " VALUE=");
    out = append_hex32(out, end, (u32)event->value);
    out = append_text(out, end, " X=");
    out = append_u32(out, end, (u32)x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, (u32)y);
    *out = 0;
    write_line("ab", g_line);
}

static void log_state_change(u32 ticks, int old_state, int new_state) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "STATE CHANGE TICKS=");
    out = append_u32(out, end, ticks);
    out = append_text(out, end, " OLD=");
    out = append_hex32(out, end, (u32)old_state);
    out = append_text(out, end, " NEW=");
    out = append_hex32(out, end, (u32)new_state);
    *out = 0;
    write_line("ab", g_line);
}

static void log_heartbeat(
    u32 ticks,
    u32 poll_cycles,
    u32 fetch_calls,
    u32 event_count,
    u32 code8_count,
    u32 code11_count,
    u32 other_count,
    int state,
    u16 x,
    u16 y
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "HEARTBEAT TICKS=");
    out = append_u32(out, end, ticks);
    out = append_text(out, end, " POLLS=");
    out = append_u32(out, end, poll_cycles);
    out = append_text(out, end, " FETCH=");
    out = append_u32(out, end, fetch_calls);
    out = append_text(out, end, " EVENTS=");
    out = append_u32(out, end, event_count);
    out = append_text(out, end, " C8=");
    out = append_u32(out, end, code8_count);
    out = append_text(out, end, " C11=");
    out = append_u32(out, end, code11_count);
    out = append_text(out, end, " OTHER=");
    out = append_u32(out, end, other_count);
    out = append_text(out, end, " STATE=");
    out = append_hex32(out, end, (u32)state);
    out = append_text(out, end, " X=");
    out = append_u32(out, end, (u32)x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, (u32)y);
    *out = 0;
    write_line("ab", g_line);
}

static void log_counts(const u32 *counts) {
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
    bda_gui_event_fetch_like_t event;
    u32 counts[EVENT_CODE_LIMIT];
    u32 start_tick;
    u32 last_poll_tick;
    u32 last_heartbeat_tick;
    u32 spin_count = 0u;
    u32 poll_cycles = 0u;
    u32 fetch_calls = 0u;
    u32 event_count = 0u;
    u32 code8_count = 0u;
    u32 code11_count = 0u;
    u32 other_count = 0u;
    u32 code;
    int state;
    u16 last_x = 0xffffu;
    u16 last_y = 0xffffu;

    for (code = 0u; code < EVENT_CODE_LIMIT; ++code) {
        counts[code] = 0u;
    }

    write_line("wb", "START GAMEBOY EVENT TOUCH HARDWARE PROBE V1");
    write_line("ab", "PATH=GUI+72C STATE -> GUI+750 EVENT -> GUI+6C0 XY");
    write_line("ab", "NO FIXED VA; NO GPIO; NO WINDOW TIMER; ESC TO EXIT");

    write_line("ab", "BEFORE FIRST STATE");
    state = bda_gui_state_query_like();
    log_first_state(state);

    event.code = -2;
    event.value = -2;
    write_line("ab", "BEFORE FIRST FETCH");
    log_first_fetch(bda_gui_event_fetch_like(&event), &event);

    write_line("ab", "BEFORE FIRST POSITION");
    bda_gui_touch_position_like(&last_x, &last_y);
    log_first_position(last_x, last_y);
    write_line("ab", "READY TOUCH SCREEN; TAP AND DRAG; ESC TO EXIT");

    start_tick = bda_gui_tick_count_25ms_like();
    last_poll_tick = start_tick;
    last_heartbeat_tick = start_tick;

    for (;;) {
        u32 now_tick;
        u32 elapsed_ticks;
        int new_state;
        u32 drain;

        ++spin_count;
        if ((spin_count & 0x3fu) == 0u) {
            (void)bda_gui_input_packet_like(&packet);
            if (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE)) {
                write_line("ab", "ESC DOWN");
                wait_escape_release();
                write_line("ab", "ESC UP");
                break;
            }
        }

        now_tick = bda_gui_tick_count_25ms_like();
        if (now_tick == last_poll_tick) {
            continue;
        }
        last_poll_tick = now_tick;
        elapsed_ticks = now_tick - start_tick;
        ++poll_cycles;

        new_state = bda_gui_state_query_like();
        if (new_state != state) {
            log_state_change(elapsed_ticks, state, new_state);
            state = new_state;
        }

        for (drain = 0u; drain < FETCH_DRAIN_LIMIT; ++drain) {
            int result;

            event.code = -1;
            event.value = -1;
            result = bda_gui_event_fetch_like(&event);
            ++fetch_calls;
            if (event.code < 0) {
                break;
            }

            ++event_count;
            if ((u32)event.code < EVENT_CODE_LIMIT) {
                ++counts[(u32)event.code];
            }
            if (event.code == 8) {
                ++code8_count;
            } else if (event.code == 11) {
                ++code11_count;
            } else {
                ++other_count;
            }

            bda_gui_touch_position_like(&last_x, &last_y);
            if (event_count <= EVENT_LOG_LIMIT) {
                log_event(
                    event_count,
                    elapsed_ticks,
                    result,
                    state,
                    &event,
                    last_x,
                    last_y
                );
            } else if (event_count == EVENT_LOG_LIMIT + 1u) {
                write_line("ab", "EVENT LOG LIMIT REACHED; COUNTS CONTINUE");
            }
        }

        if (now_tick - last_heartbeat_tick >= 40u) {
            log_heartbeat(
                elapsed_ticks,
                poll_cycles,
                fetch_calls,
                event_count,
                code8_count,
                code11_count,
                other_count,
                state,
                last_x,
                last_y
            );
            last_heartbeat_tick = now_tick;
        }
    }

    log_counts(counts);
    write_line("ab", "RESULT=PASS");
    write_line("ab", "END GAMEBOY EVENT TOUCH HARDWARE PROBE V1");
    return 0;
}
