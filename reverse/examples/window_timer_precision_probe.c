#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define TIMER_ID 1u
#define PHASE_COUNT 4u
#define SAMPLES_PER_PHASE 12u
#define DELIVERY_EARLY_TOLERANCE_MS 2u
#define DELIVERY_LATE_TOLERANCE_MS 10u

typedef struct timer_sample {
    u32 scheduler_delta;
    u32 millisecond_delta;
} timer_sample_t;

static const char k_title[] = "TIMER PREC V6";
static const char k_log_path_a[] = "A:\\WINTPRE6.TXT";
static const char k_log_path_root[] = "\\WINTPRE6.TXT";
static const u32 k_requested_periods[PHASE_COUNT] = {5u, 10u, 15u, 25u};
static const u32 k_expected_periods[PHASE_COUNT] = {10u, 10u, 20u, 30u};

static const char *g_log_path;
static bda_handle_t g_frame;
static volatile u32 g_phase;
static volatile u32 g_sample_count;
static volatile int g_phase_done;
static volatile int g_warmup_seen;
static volatile int g_detached;
static volatile int g_bad_message;
static u32 g_previous_scheduler;
static u32 g_previous_millisecond;
static timer_sample_t g_samples[SAMPLES_PER_PHASE];
static u32 g_scheduler_failures;
static u32 g_delivery_early;
static u32 g_delivery_late;
static char g_line[192];

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

static void log_sample(u32 phase, u32 index, const timer_sample_t *sample) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "SAMPLE P=");
    out = append_u32(out, end, phase);
    out = append_text(out, end, " N=");
    out = append_u32(out, end, index + 1u);
    out = append_text(out, end, " SCHED=");
    out = append_u32(out, end, sample->scheduler_delta);
    out = append_text(out, end, " MS=");
    out = append_u32(out, end, sample->millisecond_delta);
    write_line(out);
}

static void log_phase_summary(
    u32 phase,
    u32 scheduler_min,
    u32 scheduler_max,
    u32 scheduler_total,
    u32 millisecond_min,
    u32 millisecond_max,
    u32 millisecond_total
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "PHASE=");
    out = append_u32(out, end, phase);
    out = append_text(out, end, " REQUEST=");
    out = append_u32(out, end, k_requested_periods[phase]);
    out = append_text(out, end, " EXPECT=");
    out = append_u32(out, end, k_expected_periods[phase]);
    out = append_text(out, end, " SCHED_MIN=");
    out = append_u32(out, end, scheduler_min);
    out = append_text(out, end, " SCHED_MAX=");
    out = append_u32(out, end, scheduler_max);
    out = append_text(out, end, " SCHED_AVG=");
    out = append_u32(out, end, scheduler_total / SAMPLES_PER_PHASE);
    out = append_text(out, end, " MS_MIN=");
    out = append_u32(out, end, millisecond_min);
    out = append_text(out, end, " MS_MAX=");
    out = append_u32(out, end, millisecond_max);
    out = append_text(out, end, " MS_AVG=");
    out = append_u32(out, end, millisecond_total / SAMPLES_PER_PHASE);
    write_line(out);
}

static int window_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
) {
    if (message == BDA_MSG_WINDOW_TIMER) {
        u32 scheduler_now;
        u32 millisecond_now;
        u32 index;

        if (wparam != TIMER_ID || lparam != 0 || g_phase >= PHASE_COUNT) {
            g_bad_message = 1;
            return 1;
        }
        scheduler_now = bda_gui_window_timer_clock_ms();
        millisecond_now = bda_gui_millisecond_count();
        if (!g_warmup_seen) {
            g_previous_scheduler = scheduler_now;
            g_previous_millisecond = millisecond_now;
            g_warmup_seen = 1;
            return 1;
        }
        index = g_sample_count;
        if (index < SAMPLES_PER_PHASE) {
            g_samples[index].scheduler_delta =
                scheduler_now - g_previous_scheduler;
            g_samples[index].millisecond_delta =
                millisecond_now - g_previous_millisecond;
            g_previous_scheduler = scheduler_now;
            g_previous_millisecond = millisecond_now;
            g_sample_count = index + 1u;
            if (g_sample_count == SAMPLES_PER_PHASE) {
                g_phase_done = 1;
            }
        }
        return 1;
    }
    if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        g_detached = 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

static int start_phase(u32 phase) {
    g_phase = phase;
    g_sample_count = 0;
    g_phase_done = 0;
    g_warmup_seen = 0;
    clear_bytes(g_samples, sizeof(g_samples));
    g_previous_scheduler = bda_gui_window_timer_clock_ms();
    g_previous_millisecond = bda_gui_millisecond_count();
    return bda_gui_window_timer_start(
        g_frame, TIMER_ID, k_requested_periods[phase]
    );
}

static void evaluate_and_log_phase(u32 phase) {
    u32 scheduler_min = 0xffffffffu;
    u32 scheduler_max = 0;
    u32 scheduler_total = 0;
    u32 millisecond_min = 0xffffffffu;
    u32 millisecond_max = 0;
    u32 millisecond_total = 0;
    u32 expected = k_expected_periods[phase];
    u32 index;

    for (index = 0; index < SAMPLES_PER_PHASE; ++index) {
        u32 scheduler_delta = g_samples[index].scheduler_delta;
        u32 millisecond_delta = g_samples[index].millisecond_delta;

        if (scheduler_delta < scheduler_min) {
            scheduler_min = scheduler_delta;
        }
        if (scheduler_delta > scheduler_max) {
            scheduler_max = scheduler_delta;
        }
        if (millisecond_delta < millisecond_min) {
            millisecond_min = millisecond_delta;
        }
        if (millisecond_delta > millisecond_max) {
            millisecond_max = millisecond_delta;
        }
        scheduler_total += scheduler_delta;
        millisecond_total += millisecond_delta;
        if (scheduler_delta != expected) {
            ++g_scheduler_failures;
        }
        if (millisecond_delta + DELIVERY_EARLY_TOLERANCE_MS < expected) {
            ++g_delivery_early;
        }
        if (millisecond_delta > expected + DELIVERY_LATE_TOLERANCE_MS) {
            ++g_delivery_late;
        }
        log_sample(phase, index, &g_samples[index]);
    }
    log_phase_summary(
        phase,
        scheduler_min,
        scheduler_max,
        scheduler_total,
        millisecond_min,
        millisecond_max,
        millisecond_total
    );
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    u32 next_phase = 0;
    int result;
    int closing = 0;
    int cleanup_started = 0;
    int timer_active = 0;
    int millisecond_timer_active = 0;

    clear_bytes(&descriptor, sizeof(descriptor));
    clear_bytes(&message, sizeof(message));
    g_frame = 0;
    g_phase = 0;
    g_sample_count = 0;
    g_phase_done = 0;
    g_warmup_seen = 0;
    g_detached = 0;
    g_bad_message = 0;
    g_scheduler_failures = 0;
    g_delivery_early = 0;
    g_delivery_late = 0;
    reset_log();
    log_text("START WINDOW TIMER PRECISION PROBE V6");

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

    bda_gui_millisecond_timer_start();
    millisecond_timer_active = 1;
    log_text("MILLI STARTED");
    result = start_phase(next_phase);
    log_value("PHASE START=", (u32)result);
    if (result == 1) {
        timer_active = 1;
    } else {
        ++g_scheduler_failures;
        closing = 1;
    }

    for (;;) {
        int pump_result;

        if (closing && !cleanup_started) {
            if (timer_active) {
                (void)bda_gui_window_timer_stop(g_frame, TIMER_ID);
                timer_active = 0;
            }
            if (millisecond_timer_active) {
                bda_gui_millisecond_timer_stop();
                millisecond_timer_active = 0;
                log_text("MILLI STOPPED");
            }
            log_value("BAD MESSAGE=", (u32)g_bad_message);
            log_value("SCHED FAILURES=", g_scheduler_failures);
            log_value("DELIVERY EARLY=", g_delivery_early);
            log_value("DELIVERY LATE=", g_delivery_late);
            log_text(
                (!g_bad_message && !g_scheduler_failures) ?
                "SCHED RESULT=PASS" : "SCHED RESULT=FAIL"
            );
            log_text(
                (!g_delivery_early && !g_delivery_late) ?
                "DELIVERY RESULT=PASS" :
                "DELIVERY RESULT=OUTSIDE TOLERANCE"
            );
            log_text(
                (!g_bad_message && !g_scheduler_failures) ?
                "RESULT=PASS" : "RESULT=FAIL"
            );
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
            cleanup_started = 1;
            if (g_detached) {
                break;
            }
        } else if (cleanup_started && g_detached) {
            break;
        }

        pump_result = bda_gui_event_pump_frame_once(&message, g_frame);

        if (!pump_result) {
            log_text("PUMP END");
            break;
        }
        if (g_phase_done && !closing) {
            g_phase_done = 0;
            result = bda_gui_window_timer_stop(g_frame, TIMER_ID);
            timer_active = 0;
            log_value("PHASE STOP=", (u32)result);
            if (result != 1) {
                ++g_scheduler_failures;
            }
            evaluate_and_log_phase(next_phase);
            ++next_phase;
            if (next_phase < PHASE_COUNT) {
                result = start_phase(next_phase);
                log_value("PHASE START=", (u32)result);
                if (result == 1) {
                    timer_active = 1;
                } else {
                    ++g_scheduler_failures;
                    closing = 1;
                }
            } else {
                closing = 1;
            }
        }
    }

    if (timer_active) {
        (void)bda_gui_window_timer_stop(g_frame, TIMER_ID);
    }
    if (millisecond_timer_active) {
        bda_gui_millisecond_timer_stop();
    }
    log_text("BEFORE CLOSE");
    bda_gui_close_frame(g_frame);
    log_text("CLOSE RETURNED");
    return (g_bad_message || g_scheduler_failures) ? 2 : 0;
}
