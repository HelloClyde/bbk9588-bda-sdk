#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define TOUCH_COORDINATE_MESSAGE 1u
#define CROSS_RADIUS 12
#define EVENT_QUEUE_SIZE 32u
#define LOG_CAPACITY 6144u

typedef struct debug_event {
    u32 message;
    u32 wparam;
    u32 lparam;
} debug_event_t;

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHDBG.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHDBG.TXT";

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static volatile u32 g_queue_read;
static volatile u32 g_queue_write;
static volatile u32 g_queue_dropped;
static volatile int g_exit;
static volatile int g_need_redraw;
static volatile int g_need_full_redraw;
static debug_event_t g_events[EVENT_QUEUE_SIZE];
static char g_log[LOG_CAPACITY];
static u32 g_log_length;
static int g_log_dirty;
static int g_pen_down;
static int g_last_pen_down;
static u16 g_last_poll_x;
static u16 g_last_poll_y;
static u32 g_last_message;
static int g_has_coordinate;
static int g_has_painted_cross;
static char g_coordinate_source;
static s32 g_touch_x;
static s32 g_touch_y;
static s32 g_painted_x;
static s32 g_painted_y;

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

    if (!value) {
        return append_char(out, end, '0');
    }
    while (value && count < (int)sizeof(digits)) {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    }
    while (count) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static char *append_s32(char *out, char *end, s32 value) {
    u32 magnitude;

    if (value < 0) {
        out = append_char(out, end, '-');
        magnitude = 0u - (u32)value;
    } else {
        magnitude = (u32)value;
    }
    return append_u32(out, end, magnitude);
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

static int coordinate_valid(s32 x, s32 y) {
    return x >= 0 && x < SCREEN_WIDTH && y >= 0 && y < SCREEN_HEIGHT;
}

static void persist_log(void) {
    int file;

    if (!g_log_dirty) {
        return;
    }
    file = bda_fs_fopen_raw(k_log_path_a, "wb");
    if (!bda_fs_file_is_valid(file)) {
        file = bda_fs_fopen_raw(k_log_path_root, "wb");
    }
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_log, g_log_length);
    (void)bda_fs_close_raw(file);
    g_log_dirty = 0;
}

static void commit_log_line(char *out) {
    char *end = g_log + sizeof(g_log) - 1;

    out = append_text(out, end, "\r\n");
    *out = 0;
    g_log_length = (u32)(out - g_log);
    g_log_dirty = 1;
}

static void log_text(const char *text) {
    char *out = g_log + g_log_length;
    char *end = g_log + sizeof(g_log) - 1;

    if (out >= end - 32) {
        return;
    }
    out = append_text(out, end, text);
    commit_log_line(out);
}

static void log_frame(void) {
    char *out = g_log + g_log_length;
    char *end = g_log + sizeof(g_log) - 1;

    if (out >= end - 48) {
        return;
    }
    out = append_text(out, end, "FRAME=");
    out = append_hex32(out, end, (u32)g_frame);
    commit_log_line(out);
}

static void log_event(const debug_event_t *event) {
    char *out = g_log + g_log_length;
    char *end = g_log + sizeof(g_log) - 1;

    if (out >= end - 96) {
        return;
    }
    out = append_text(out, end, "EV M=");
    out = append_hex32(out, end, event->message);
    out = append_text(out, end, " W=");
    out = append_hex32(out, end, event->wparam);
    out = append_text(out, end, " L=");
    out = append_hex32(out, end, event->lparam);
    if (event->message == TOUCH_COORDINATE_MESSAGE) {
        out = append_text(out, end, " X=");
        out = append_s32(out, end, event_x(event->lparam));
        out = append_text(out, end, " Y=");
        out = append_s32(out, end, event_y(event->lparam));
    }
    commit_log_line(out);
}

static void log_pen(int down) {
    char *out = g_log + g_log_length;
    char *end = g_log + sizeof(g_log) - 1;

    if (out >= end - 24) {
        return;
    }
    out = append_text(out, end, "PEN=");
    out = append_u32(out, end, down ? 1u : 0u);
    commit_log_line(out);
}

static void log_poll(u16 x, u16 y) {
    char *out = g_log + g_log_length;
    char *end = g_log + sizeof(g_log) - 1;

    if (out >= end - 40) {
        return;
    }
    out = append_text(out, end, "POLL X=");
    out = append_u32(out, end, x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, y);
    commit_log_line(out);
}

static void queue_event(u32 message, u32 wparam, u32 lparam) {
    u32 write = g_queue_write;
    u32 next = (write + 1u) % EVENT_QUEUE_SIZE;

    if (next == g_queue_read) {
        ++g_queue_dropped;
        return;
    }
    g_events[write].message = message;
    g_events[write].wparam = wparam;
    g_events[write].lparam = lparam;
    g_queue_write = next;
}

static void update_coordinate(char source, s32 x, s32 y) {
    if (!coordinate_valid(x, y)) {
        return;
    }
    if (!g_has_coordinate || g_touch_x != x || g_touch_y != y ||
        g_coordinate_source != source) {
        g_coordinate_source = source;
        g_touch_x = x;
        g_touch_y = y;
        g_has_coordinate = 1;
        g_need_redraw = 1;
    }
}

static void drain_events(void) {
    while (g_queue_read != g_queue_write) {
        debug_event_t event = g_events[g_queue_read];
        g_queue_read = (g_queue_read + 1u) % EVENT_QUEUE_SIZE;
        g_last_message = event.message;
        log_event(&event);
        if (event.message == TOUCH_COORDINATE_MESSAGE) {
            update_coordinate('M', event_x(event.lparam), event_y(event.lparam));
        }
    }
}

static void poll_touch(void) {
    int down = bda_touch_pressed_9588() != 0;

    g_pen_down = down;
    if (down != g_last_pen_down) {
        g_last_pen_down = down;
        log_pen(down);
        g_need_redraw = 1;
    }
    if (down) {
        u16 x = 0xffffu;
        u16 y = 0xffffu;

        bda_gui_touch_position_like(&x, &y);
        if (x != g_last_poll_x || y != g_last_poll_y) {
            g_last_poll_x = x;
            g_last_poll_y = y;
            log_poll(x, y);
            update_coordinate('P', (s32)x, (s32)y);
        }
    }
}

static void fill_pixels(
    s32 left,
    s32 top,
    s32 right,
    s32 bottom,
    u32 color
) {
    s32 x;
    s32 y;

    for (y = top; y <= bottom; ++y) {
        for (x = left; x <= right; ++x) {
            (void)bda_gui_put_pixel_like(g_draw, x, y, color);
        }
    }
}

static void draw_cross(s32 x, s32 y, u32 color) {
    s32 delta;

    for (delta = -CROSS_RADIUS; delta <= CROSS_RADIUS; ++delta) {
        if (coordinate_valid(x + delta, y)) {
            (void)bda_gui_put_pixel_like(g_draw, x + delta, y, color);
        }
        if (coordinate_valid(x, y + delta)) {
            (void)bda_gui_put_pixel_like(g_draw, x, y + delta, color);
        }
    }
}

static void build_primary_status(char *status) {
    char *out = status;
    char *end = status + 31;

    if (!g_has_coordinate) {
        out = append_text(out, end, "NO COORDINATE");
    } else {
        out = append_text(out, end, "SRC=");
        out = append_char(out, end, g_coordinate_source);
        out = append_text(out, end, " X=");
        out = append_s32(out, end, g_touch_x);
        out = append_text(out, end, " Y=");
        out = append_s32(out, end, g_touch_y);
    }
    *out = 0;
}

static void build_secondary_status(char *status) {
    char *out = status;
    char *end = status + 31;

    out = append_text(out, end, "PEN=");
    out = append_u32(out, end, g_pen_down ? 1u : 0u);
    out = append_text(out, end, " MSG=");
    out = append_hex32(out, end, g_last_message);
    *out = 0;
}

static void draw_scene(int full_redraw) {
    char primary[32];
    char secondary[32];
    void *old_object;
    u32 background;
    u32 foreground;
    u32 cross_color;

    if (!g_draw || !g_draw_object) {
        return;
    }
    background = (u32)bda_gui_rgb_like(g_draw, 0, 0, 0);
    foreground = (u32)bda_gui_rgb_like(g_draw, 245, 248, 250);
    cross_color = (u32)bda_gui_rgb_like(g_draw, 35, 210, 225);
    build_primary_status(primary);
    build_secondary_status(secondary);

    (void)bda_gui_draw_guard_begin_like();
    old_object = bda_gui_select_draw_object_like(g_draw, g_draw_object);
    if (full_redraw) {
        fill_pixels(0, 0, SCREEN_WIDTH - 1, SCREEN_HEIGHT - 1, background);
        g_has_painted_cross = 0;
    } else {
        if (g_has_painted_cross) {
            draw_cross(g_painted_x, g_painted_y, background);
        }
        fill_pixels(0, 24, SCREEN_WIDTH - 1, 49, background);
        fill_pixels(0, 280, SCREEN_WIDTH - 1, 319, background);
    }

    bda_gui_rectangle_like(g_draw, 7, 52, 232, 276);
    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 38, 5, "TOUCH DEBUG TEST", -1);
    (void)bda_gui_draw_text_like(g_draw, 40, 29, primary, -1);
    (void)bda_gui_draw_text_like(g_draw, 25, 283, secondary, -1);
    (void)bda_gui_draw_text_like(g_draw, 82, 303, "ESC EXIT", -1);

    if (g_has_coordinate) {
        draw_cross(g_touch_x, g_touch_y, cross_color);
        g_painted_x = g_touch_x;
        g_painted_y = g_touch_y;
        g_has_painted_cross = 1;
    }
    (void)bda_gui_select_draw_object_like(g_draw, old_object);
    (void)bda_gui_draw_guard_end_like();
}

static int touch_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    queue_event(message, wparam, lparam);
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE) {
        g_frame = handle;
        g_draw = bda_gui_current_draw_like(handle);
        if (!g_draw_object) {
            g_draw_object = bda_gui_draw_object_create_like(7);
        }
        g_need_full_redraw = 1;
    } else if (message == BDA_MSG_REDRAW_INPUT_LIKE) {
        g_need_full_redraw = 1;
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH_LIKE) {
        g_draw = 0;
        g_exit = 1;
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

static void wait_escape_release(void) {
    bda_gui_input_packet_like_t packet;

    do {
        (void)bda_gui_input_packet_like(&packet);
        bda_sys_delay_like(1);
    } while (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE));
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t descriptor;
    bda_gui_message_like_t message;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    bda_memset(g_log, 0, sizeof(g_log));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_queue_read = 0;
    g_queue_write = 0;
    g_queue_dropped = 0;
    g_exit = 0;
    g_need_redraw = 1;
    g_need_full_redraw = 1;
    g_log_length = 0;
    g_log_dirty = 0;
    g_pen_down = 0;
    g_last_pen_down = -1;
    g_last_poll_x = 0xffffu;
    g_last_poll_y = 0xffffu;
    g_last_message = 0;
    g_has_coordinate = 0;
    g_has_painted_cross = 0;
    log_text("START TOUCH DEBUG");
    persist_log();

    descriptor.style = 0x08000000u;
    descriptor.wndproc = touch_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = (u32)bda_gui_frame_surface_like(15);

    g_frame = bda_gui_register_frame_desc_like(&descriptor);
    if (!g_frame || (s32)g_frame == -1) {
        log_text("REGISTER FAIL");
        persist_log();
        return 1;
    }
    log_frame();
    (void)bda_gui_frame_activate_like(g_frame, 0x100);
    if (!g_draw) {
        g_draw = bda_gui_current_draw_like(g_frame);
    }
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create_like(7);
    }
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        log_text("DRAW CONTEXT FAIL");
        persist_log();
        return 2;
    }

    while (!g_exit) {
        bda_gui_input_packet_like_t packet;

        (void)bda_gui_event_pump_frame_once_like(&message, g_frame);
        drain_events();
        poll_touch();
        if (g_need_full_redraw) {
            g_need_full_redraw = 0;
            g_need_redraw = 0;
            draw_scene(1);
        } else if (g_need_redraw) {
            g_need_redraw = 0;
            draw_scene(0);
        }
        persist_log();

        (void)bda_gui_input_packet_like(&packet);
        if (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE)) {
            wait_escape_release();
            break;
        }
        bda_sys_delay_like(1);
    }

    if (g_queue_dropped) {
        log_text("EVENT QUEUE DROPPED");
    }
    log_text("EXIT");
    persist_log();
    if (g_frame) {
        (void)bda_gui_frame_stop_like(g_frame);
        (void)bda_gui_frame_release_like(g_frame);
    }
    return 0;
}
