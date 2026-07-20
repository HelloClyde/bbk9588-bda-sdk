#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define TIMER_ID 1u
#define SPARSE_TIMER_A 2u
#define SPARSE_TIMER_B 3u
#define FIRST_PERIOD_MS 40u
#define SECOND_PERIOD_MS 20u
#define FIRST_EVENT_COUNT 4u
#define FINAL_EVENT_COUNT 8u

static const char k_title[] = "WINDOW TIMER";
static const char k_log_path_a[] = "A:\\WINTIMER.TXT";
static const char k_log_path_root[] = "\\WINTIMER.TXT";

static const char *g_log_path;
static bda_handle_t g_frame;
static volatile u32 g_timer_count;
static volatile int g_change_period;
static volatile int g_done;
static volatile int g_detached;
static u32 g_previous_tick;
static u32 g_previous_timer_clock;
static int g_failures;
static char g_line[160];

static void clear_bytes(void *destination, u32 size) {
    u8 *out = (u8 *)destination;

    while (size--) {
        *out++ = 0;
    }
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
    while (count > 0 && out < end) {
        *out++ = digits[--count];
    }
    return out;
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char digits[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0 && out < end; shift -= 4) {
        *out++ = digits[(value >> shift) & 0x0fu];
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
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "\r\n");
    *out = 0;
    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_line, (u32)(out - g_line));
    (void)bda_fs_close_raw(file);
}

static void log_text(const char *text) {
    write_line(append_text(g_line, g_line + sizeof(g_line) - 1, text));
}

static void log_value(const char *label, u32 value) {
    char *out = append_text(g_line, g_line + sizeof(g_line) - 1, label);
    write_line(append_hex32(out, g_line + sizeof(g_line) - 1, value));
}

static void log_timer(
    u32 count,
    u32 timer_id,
    u32 timer_clock,
    u32 timer_delta,
    u32 tick,
    u32 tick_delta
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "TIMER N=");
    out = append_u32(out, end, count);
    out = append_text(out, end, " ID=");
    out = append_u32(out, end, timer_id);
    out = append_text(out, end, " CLOCK=");
    out = append_u32(out, end, timer_clock);
    out = append_text(out, end, " CLOCK_DELTA=");
    out = append_u32(out, end, timer_delta);
    out = append_text(out, end, " TICK=");
    out = append_u32(out, end, tick);
    out = append_text(out, end, " TICK_DELTA=");
    out = append_u32(out, end, tick_delta);
    write_line(out);
}

static int window_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
) {
    if (message == BDA_MSG_WINDOW_TIMER) {
        u32 timer_clock = bda_gui_window_timer_clock_ms();
        u32 tick = bda_gui_tick_count_25ms();
        u32 count = ++g_timer_count;
        u32 timer_delta = timer_clock - g_previous_timer_clock;
        u32 tick_delta = tick - g_previous_tick;

        g_previous_timer_clock = timer_clock;
        g_previous_tick = tick;
        log_timer(
            count, wparam, timer_clock, timer_delta, tick, tick_delta
        );
        if (wparam != TIMER_ID || lparam != 0) {
            ++g_failures;
        }
        if (count > 1u) {
            u32 expected = count <= FIRST_EVENT_COUNT ?
                FIRST_PERIOD_MS : SECOND_PERIOD_MS;
            if (timer_delta < expected || timer_delta > expected + 10u) {
                ++g_failures;
            }
        }
        if (count == FIRST_EVENT_COUNT) {
            g_change_period = 1;
        } else if (count >= FINAL_EVENT_COUNT) {
            g_done = 1;
        }
        return 1;
    }
    if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        g_detached = 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    int result;
    int closing = 0;

    clear_bytes(&descriptor, sizeof(descriptor));
    clear_bytes(&message, sizeof(message));
    g_frame = 0;
    g_timer_count = 0;
    g_change_period = 0;
    g_done = 0;
    g_detached = 0;
    g_previous_tick = 0;
    g_previous_timer_clock = 0;
    g_failures = 0;
    reset_log();
    log_text("START WINDOW TIMER PROBE V4");

    descriptor.style = 0;
    descriptor.title = k_title;
    descriptor.wndproc = window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = 0;
    g_frame = bda_gui_register_frame_desc(&descriptor);
    log_value("REGISTER=", (u32)g_frame);
    if (!g_frame || (s32)(u32)g_frame == -1) {
        log_text("RESULT=FAIL REGISTER");
        return 1;
    }
    result = bda_gui_frame_activate(g_frame, 0x100u);
    log_value("ACTIVATE=", (u32)result);

    g_previous_tick = bda_gui_tick_count_25ms();
    g_previous_timer_clock = bda_gui_window_timer_clock_ms();
    result = bda_gui_window_timer_start(
        g_frame, TIMER_ID, FIRST_PERIOD_MS
    );
    log_value("START RETURN=", (u32)result);
    if (result != 1) {
        ++g_failures;
        g_done = 1;
    }
    result = bda_gui_window_timer_exists(g_frame, TIMER_ID);
    log_value("EXISTS AFTER START=", (u32)result);
    if (result != 1) {
        ++g_failures;
        g_done = 1;
    }

    for (;;) {
        int pump_result;

        pump_result = bda_gui_event_pump_frame_once(&message, g_frame);
        if (!pump_result) {
            log_text("PUMP END");
            break;
        }
        if (g_change_period) {
            g_change_period = 0;
            result = bda_gui_window_timer_set_period(
                g_frame, TIMER_ID, SECOND_PERIOD_MS
            );
            log_value("SET PERIOD RETURN=", (u32)result);
            if (result != 1) {
                ++g_failures;
                g_done = 1;
            }
            result = bda_gui_window_timer_exists(g_frame, TIMER_ID);
            log_value("EXISTS AFTER SET=", (u32)result);
            if (result != 1) {
                ++g_failures;
                g_done = 1;
            }
        }
        if (g_done && !closing) {
            result = bda_gui_window_timer_stop(g_frame, TIMER_ID);
            log_value("STOP RETURN=", (u32)result);
            if (result != 1) {
                ++g_failures;
            }
            result = bda_gui_window_timer_exists(g_frame, TIMER_ID);
            log_value("EXISTS AFTER STOP=", (u32)result);
            if (result != 0) {
                ++g_failures;
            }

            result = bda_gui_window_timer_start(
                g_frame, SPARSE_TIMER_A, 100u
            );
            log_value("SPARSE START A=", (u32)result);
            if (result != 1) {
                ++g_failures;
            }
            result = bda_gui_window_timer_start(
                g_frame, SPARSE_TIMER_B, 100u
            );
            log_value("SPARSE START B=", (u32)result);
            if (result != 1) {
                ++g_failures;
            }
            result = bda_gui_window_timer_stop(g_frame, SPARSE_TIMER_A);
            log_value("SPARSE STOP A=", (u32)result);
            if (result != 1) {
                ++g_failures;
            }
            result = bda_gui_window_timer_set_period(
                g_frame, SPARSE_TIMER_B, 50u
            );
            log_value("SPARSE SET B=", (u32)result);
            if (result != 1 ||
                bda_gui_window_timer_exists(g_frame, SPARSE_TIMER_B) != 1) {
                ++g_failures;
            }
            result = bda_gui_window_timer_stop(g_frame, SPARSE_TIMER_B);
            log_value("SPARSE STOP B=", (u32)result);
            if (result != 1) {
                ++g_failures;
            }
            log_value("FAILURES=", (u32)g_failures);
            log_text(g_failures ? "RESULT=FAIL" : "RESULT=PASS");
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
            closing = 1;
            if (g_detached) {
                break;
            }
        } else if (closing && g_detached) {
            break;
        }
    }

    log_text("BEFORE CLOSE");
    bda_gui_close_frame(g_frame);
    log_text("CLOSE RETURNED");
    return g_failures ? 2 : 0;
}
