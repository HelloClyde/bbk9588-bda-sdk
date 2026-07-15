#include "bda_sdk.h"

/*
 * Candidate touch-message probe. Build with:
 * python -m bda_packer reverse/examples/touch_window_event_probe.c
 *   --title TouchXY --category 4 -I sdk/api -o build/TouchXY.bda
 */

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define TOUCH_DOWN_MESSAGE 1u
#define TOUCH_UP_MESSAGE 2u
#define EVENT_QUEUE_SIZE 8u
#define LOG_CAPACITY 1536u

static const char k_log_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHXY.TXT";

typedef struct touch_event {
    u32 message;
    u32 wparam;
    u32 lparam;
} touch_event_t;

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static volatile u32 g_queue_read;
static volatile u32 g_queue_write;
static volatile int g_attached;
static volatile int g_attach_pending;
static volatile int g_detached;
static touch_event_t g_queue[EVENT_QUEUE_SIZE];
static char g_log[LOG_CAPACITY];
static u32 g_log_length;
static u32 g_event_sequence;
static char g_status[72];

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

static char *append_dec(char *out, char *end, s32 value) {
    char digits[12];
    u32 magnitude;
    int count = 0;

    if (value < 0) {
        out = append_char(out, end, '-');
        magnitude = (u32)(0 - value);
    } else {
        magnitude = (u32)value;
    }
    if (!magnitude) {
        return append_char(out, end, '0');
    }
    while (magnitude && count < (int)sizeof(digits)) {
        digits[count++] = (char)('0' + magnitude % 10u);
        magnitude /= 10u;
    }
    while (count) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static char hex_digit(u32 value) {
    return (char)(value < 10u ? '0' + value : 'A' + value - 10u);
}

static char *append_hex32(char *out, char *end, u32 value) {
    int shift;
    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        out = append_char(out, end, hex_digit((value >> shift) & 0x0fu));
    }
    return out;
}

static s32 event_x(u32 lparam) {
    return (s32)(s16)BDA_LOWORD(lparam);
}

static s32 event_y(u32 lparam) {
    return (s32)(s16)BDA_HIWORD(lparam);
}

static void persist_log(void) {
    int file = bda_fs_fopen_raw(k_log_path, "wb");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_log, g_log_length);
    (void)bda_fs_close_raw(file);
}

static void append_log_line(const char *line) {
    char *out = g_log + g_log_length;
    char *end = g_log + sizeof(g_log) - 1;
    out = append_text(out, end, line);
    out = append_text(out, end, "\r\n");
    *out = 0;
    g_log_length = (u32)(out - g_log);
    persist_log();
}

static void append_start_line(void) {
    char line[80];
    char *out = line;
    char *end = line + sizeof(line) - 1;
    out = append_text(out, end, "READY FRAME=");
    out = append_hex32(out, end, (u32)g_frame);
    out = append_text(out, end, " ATTACH=");
    out = append_dec(out, end, g_attached);
    *out = 0;
    append_log_line(line);
}

static void append_attach_line(void) {
    char line[48];
    char *out = line;
    char *end = line + sizeof(line) - 1;

    out = append_text(out, end, "ATTACH FRAME=");
    out = append_hex32(out, end, (u32)g_frame);
    *out = 0;
    append_log_line(line);
}

static void append_event_line(const touch_event_t *event) {
    char line[160];
    char *out = line;
    char *end = line + sizeof(line) - 1;
    s32 x = event_x(event->lparam);
    s32 y = event_y(event->lparam);

    ++g_event_sequence;
    out = append_text(out, end, "SEQ=");
    out = append_dec(out, end, (s32)g_event_sequence);
    out = append_text(out, end, " MSG=");
    out = append_dec(out, end, (s32)event->message);
    out = append_text(out, end, " X=");
    out = append_dec(out, end, x);
    out = append_text(out, end, " Y=");
    out = append_dec(out, end, y);
    out = append_text(out, end, " WP=");
    out = append_hex32(out, end, event->wparam);
    out = append_text(out, end, " LP=");
    out = append_hex32(out, end, event->lparam);
    out = append_text(out, end, " PEN=");
    out = append_dec(out, end, bda_touch_pressed_9588() ? 1 : 0);
    *out = 0;
    append_log_line(line);

    out = g_status;
    end = g_status + sizeof(g_status) - 1;
    out = append_text(out, end, event->message == TOUCH_DOWN_MESSAGE ? "DOWN X=" : "UP X=");
    out = append_dec(out, end, x);
    out = append_text(out, end, " Y=");
    out = append_dec(out, end, y);
    *out = 0;
}

static void draw_status(void) {
    void *old_object;
    u32 white;

    if (!g_draw || !g_draw_object) {
        return;
    }
    old_object = bda_gui_select_draw_object_like(g_draw, g_draw_object);
    white = (u32)bda_gui_rgb_like(g_draw, 245, 248, 250);
    (void)bda_gui_draw_guard_begin_like();
    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, white);
    (void)bda_gui_draw_text_like(g_draw, 42, 18, "TOUCH XY EVENT", -1);
    (void)bda_gui_draw_text_like(g_draw, 20, 292, g_status, -1);
    (void)bda_gui_select_draw_object_like(g_draw, old_object);
    (void)bda_gui_draw_guard_end_like();
}

static void queue_touch_event(u32 message, u32 wparam, u32 lparam) {
    u32 write = g_queue_write;
    u32 next = (write + 1u) % EVENT_QUEUE_SIZE;
    if (next == g_queue_read) {
        return;
    }
    g_queue[write].message = message;
    g_queue[write].wparam = wparam;
    g_queue[write].lparam = lparam;
    g_queue_write = next;
}

static int touch_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE) {
        g_frame = handle;
        g_draw = bda_gui_current_draw_like(handle);
        if (!g_draw_object) {
            g_draw_object = bda_gui_draw_object_create_like(7);
        }
        g_attached = 1;
        g_attach_pending = 1;
        draw_status();
        return 1;
    }
    if (message == TOUCH_DOWN_MESSAGE || message == TOUCH_UP_MESSAGE) {
        queue_touch_event(message, wparam, lparam);
        return 1;
    }
    if (message == BDA_MSG_REDRAW_INPUT_LIKE) {
        draw_status();
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH_LIKE) {
        g_detached = 1;
        g_draw = 0;
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

static void drain_touch_events(void) {
    while (g_queue_read != g_queue_write) {
        touch_event_t event = g_queue[g_queue_read];
        g_queue_read = (g_queue_read + 1u) % EVENT_QUEUE_SIZE;
        append_event_line(&event);
        draw_status();
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t descriptor;
    bda_gui_message_like_t message;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    bda_memset(g_log, 0, sizeof(g_log));
    bda_memset(g_status, 0, sizeof(g_status));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_queue_read = 0;
    g_queue_write = 0;
    g_attached = 0;
    g_attach_pending = 0;
    g_detached = 0;
    g_log_length = 0;
    g_event_sequence = 0;
    append_text(g_status, g_status + sizeof(g_status) - 1, "WAITING FOR WINDOW TOUCH");

    descriptor.style = 0x08000000u;
    descriptor.wndproc = touch_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = (u32)bda_gui_draw_object_create_like(15);

    g_frame = bda_gui_register_frame_desc_like(&descriptor);
    if (!g_frame || (s32)g_frame == -1) {
        append_log_line("REGISTER_FAIL");
        return 1;
    }
    (void)bda_gui_frame_activate_like(g_frame, 0x100);
    if (!g_draw) {
        g_draw = bda_gui_current_draw_like(g_frame);
    }
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create_like(7);
    }
    append_start_line();
    draw_status();

    while (!g_detached) {
        bda_gui_input_packet_like_t packet;
        (void)bda_gui_event_pump_frame_once_like(&message, g_frame);
        if (g_attach_pending) {
            g_attach_pending = 0;
            append_attach_line();
        }
        drain_touch_events();
        (void)bda_gui_input_packet_like(&packet);
        if (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE)) {
            append_log_line("EXIT");
            break;
        }
        bda_sys_delay_like(1);
    }
    if (g_detached) {
        append_log_line("DETACH");
    }
    return 0;
}
