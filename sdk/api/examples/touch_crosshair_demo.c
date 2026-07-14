#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define CROSS_RADIUS 12
#define EVENT_QUEUE_SIZE 16u

typedef struct touch_event {
    u32 message;
    u32 lparam;
} touch_event_t;

static const char k_window_title[] = "TOUCH";

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static volatile int g_exit;
static volatile int g_need_draw;
static volatile u32 g_queue_read;
static volatile u32 g_queue_write;
static touch_event_t g_events[EVENT_QUEUE_SIZE];
static int g_has_touch;
static int g_has_painted_cross;
static int g_has_painted_status;
static s32 g_touch_x;
static s32 g_touch_y;
static s32 g_painted_x;
static s32 g_painted_y;
static char g_painted_status[32];

static s32 touch_x_from_lparam(u32 lparam) {
    return (s32)(short)(lparam & 0xffffu);
}

static s32 touch_y_from_lparam(u32 lparam) {
    return (s32)(short)((lparam >> 16) & 0xffffu);
}

static char *append_text(char *out, const char *text) {
    while (*text) {
        *out++ = *text++;
    }
    return out;
}

static char *append_coord(char *out, s32 value) {
    *out++ = (char)('0' + (value / 100) % 10);
    *out++ = (char)('0' + (value / 10) % 10);
    *out++ = (char)('0' + value % 10);
    return out;
}

static void build_status(char *status) {
    char *out = status;

    if (!g_has_touch) {
        out = append_text(out, "WAITING FOR TOUCH");
    } else {
        out = append_text(out, "TOUCH X=");
        out = append_coord(out, g_touch_x);
        out = append_text(out, " Y=");
        out = append_coord(out, g_touch_y);
    }
    *out = 0;
}

static void queue_touch_event(u32 message, u32 lparam) {
    u32 write = g_queue_write;
    u32 next = (write + 1u) % EVENT_QUEUE_SIZE;

    if (next == g_queue_read) {
        return;
    }
    g_events[write].message = message;
    g_events[write].lparam = lparam;
    g_queue_write = next;
}

static void drain_touch_events(void) {
    while (g_queue_read != g_queue_write) {
        touch_event_t event = g_events[g_queue_read];
        s32 x = touch_x_from_lparam(event.lparam);
        s32 y = touch_y_from_lparam(event.lparam);

        g_queue_read = (g_queue_read + 1u) % EVENT_QUEUE_SIZE;
        if (x >= 0 && x < SCREEN_WIDTH && y >= 0 && y < SCREEN_HEIGHT) {
            g_touch_x = x;
            g_touch_y = y;
            g_has_touch = 1;
            g_need_draw = 1;
        }
    }
}

static void draw_cross(s32 x, s32 y, u32 color) {
    s32 delta;

    for (delta = -CROSS_RADIUS; delta <= CROSS_RADIUS; ++delta) {
        if (x + delta >= 0 && x + delta < SCREEN_WIDTH &&
            y >= 0 && y < SCREEN_HEIGHT) {
            (void)bda_gui_put_pixel(g_draw, x + delta, y, color);
        }
        if (x >= 0 && x < SCREEN_WIDTH &&
            y + delta >= 0 && y + delta < SCREEN_HEIGHT) {
            (void)bda_gui_put_pixel(g_draw, x, y + delta, color);
        }
    }
}

static void remember_status(const char *status) {
    char *out = g_painted_status;
    char *end = g_painted_status + sizeof(g_painted_status) - 1;

    while (*status && out < end) {
        *out++ = *status++;
    }
    *out = 0;
    g_has_painted_status = 1;
}

static void draw_scene(void) {
    char status[32];
    void *old_object;
    u32 background;
    u32 foreground;
    u32 cross_color;

    if (!g_draw || !g_draw_object) {
        return;
    }

    background = (u32)bda_gui_rgb(g_draw, 0, 0, 0);
    foreground = (u32)bda_gui_rgb(g_draw, 245, 248, 250);
    cross_color = (u32)bda_gui_rgb(g_draw, 35, 210, 225);
    build_status(status);

    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);

    if (g_has_painted_cross) {
        draw_cross(g_painted_x, g_painted_y, background);
    }
    if (g_has_painted_status) {
        (void)bda_gui_set_text_mode(g_draw, 1);
        (void)bda_gui_set_text_color(g_draw, background);
        (void)bda_gui_draw_text(g_draw, 43, 28, g_painted_status, -1);
    }

    bda_gui_rectangle(g_draw, 7, 50, 232, 287);
    (void)bda_gui_set_text_mode(g_draw, 1);
    (void)bda_gui_set_text_color(g_draw, foreground);
    (void)bda_gui_draw_text(g_draw, 47, 6, "TOUCH SCREEN TEST", -1);
    (void)bda_gui_draw_text(g_draw, 43, 28, status, -1);
    (void)bda_gui_draw_text(g_draw, 82, 298, "ESC EXIT", -1);

    if (g_has_touch) {
        draw_cross(g_touch_x, g_touch_y, cross_color);
        g_painted_x = g_touch_x;
        g_painted_y = g_touch_y;
        g_has_painted_cross = 1;
    }
    remember_status(status);

    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
}

static int touch_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        g_frame = handle;
        g_draw = bda_gui_current_draw(handle);
        if (!g_draw_object) {
            g_draw_object = bda_gui_draw_object_create(7);
        }
        g_need_draw = 1;
    } else if (message == BDA_MSG_REDRAW_INPUT) {
        g_need_draw = 1;
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        g_draw = 0;
        g_exit = 1;
    }
    if (message == BDA_MSG_TOUCH_COORDINATE ||
        message == BDA_MSG_TOUCH_RELEASE) {
        queue_touch_event(message, lparam);
        return 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

static void wait_escape_release(void) {
    bda_gui_input_packet_t packet;

    do {
        (void)bda_gui_input_packet(&packet);
        bda_sys_delay(1);
    } while (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ESCAPE));
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    int close_requested;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_exit = 0;
    g_need_draw = 1;
    g_queue_read = 0;
    g_queue_write = 0;
    g_has_touch = 0;
    g_has_painted_cross = 0;
    g_has_painted_status = 0;
    bda_memset(g_painted_status, 0, sizeof(g_painted_status));
    close_requested = 0;

    descriptor.style = 0;
    descriptor.title = k_window_title;
    descriptor.wndproc = touch_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = 0;

    g_frame = bda_gui_register_frame_desc(&descriptor);
    if (!g_frame || (s32)g_frame == -1) {
        bda_msgbox("Touch", "frame registration failed");
        return 1;
    }
    (void)bda_gui_frame_activate(g_frame, 0x100);

    if (!g_draw) {
        g_draw = bda_gui_current_draw(g_frame);
    }
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create(7);
    }
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        bda_msgbox("Touch", "draw context failed");
        return 2;
    }
    draw_scene();

    for (;;) {
        bda_gui_input_packet_t packet;
        int pump_result;

        pump_result = bda_gui_event_pump_frame_once(&message, g_frame);
        drain_touch_events();
        if (g_need_draw) {
            g_need_draw = 0;
            draw_scene();
        }
        (void)bda_gui_input_packet(&packet);
        bda_sys_delay(1);
        if (close_requested) {
            if (!pump_result || g_exit) {
                break;
            }
            continue;
        }
        if (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ESCAPE)) {
            wait_escape_release();
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
            close_requested = 1;
        }
    }

    if (g_frame) {
        bda_gui_close_frame(g_frame);
        g_frame = 0;
    }
    return 0;
}
