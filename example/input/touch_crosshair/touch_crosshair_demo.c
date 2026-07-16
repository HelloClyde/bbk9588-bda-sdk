#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define CROSS_RADIUS 10
#define EVENT_QUEUE_SIZE 16u

typedef struct touch_event {
    u32 message;
    u32 lparam;
} touch_event_t;

static const char k_window_title[] = "TOUCH";

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static bda_handle_t g_draw_owner;
static void *g_draw_object;
static volatile int g_exit;
static volatile int g_need_draw;
static volatile u32 g_queue_read;
static volatile u32 g_queue_write;
static touch_event_t g_events[EVENT_QUEUE_SIZE];
static int g_has_touch;
static int g_has_painted_cross;
static int g_has_painted_status;
static int g_initial_scene_drawn;
static int g_initial_redraw_suppressed;
static s32 g_touch_x;
static s32 g_touch_y;
static s32 g_painted_x;
static s32 g_painted_y;

static void release_draw_context(void) {
    bda_handle_t draw = g_draw;

    if (!draw || (s32)draw == -1) {
        g_draw = 0;
        g_draw_owner = 0;
        return;
    }
    g_draw = 0;
    g_draw_owner = 0;
    bda_gui_end_draw(draw);
}

static int acquire_draw_context(bda_handle_t owner) {
    if (g_draw && g_draw_owner == owner) {
        return 1;
    }
    release_draw_context();
    g_draw = bda_gui_current_draw(owner);
    if (!g_draw || (s32)g_draw == -1) {
        g_draw = 0;
        return 0;
    }
    g_draw_owner = owner;
    return 1;
}

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

static void build_coordinate_status(char *status, s32 x, s32 y) {
    char *out = status;

    out = append_text(out, "X=");
    out = append_coord(out, x);
    out = append_text(out, " Y=");
    out = append_coord(out, y);
    *out = 0;
}

static u8 glyph_row(char value, int row) {
    static const u8 digits[10][7] = {
        {0x0e, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0e},
        {0x04, 0x0c, 0x04, 0x04, 0x04, 0x04, 0x0e},
        {0x0e, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1f},
        {0x1e, 0x01, 0x01, 0x0e, 0x01, 0x01, 0x1e},
        {0x02, 0x06, 0x0a, 0x12, 0x1f, 0x02, 0x02},
        {0x1f, 0x10, 0x10, 0x1e, 0x01, 0x01, 0x1e},
        {0x0e, 0x10, 0x10, 0x1e, 0x11, 0x11, 0x0e},
        {0x1f, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08},
        {0x0e, 0x11, 0x11, 0x0e, 0x11, 0x11, 0x0e},
        {0x0e, 0x11, 0x11, 0x0f, 0x01, 0x01, 0x0e},
    };
    static const u8 glyph_x[7] = {
        0x11, 0x11, 0x0a, 0x04, 0x0a, 0x11, 0x11
    };
    static const u8 glyph_y[7] = {
        0x11, 0x11, 0x0a, 0x04, 0x04, 0x04, 0x04
    };
    static const u8 glyph_equal[7] = {
        0x00, 0x1f, 0x00, 0x1f, 0x00, 0x00, 0x00
    };

    if (value >= '0' && value <= '9') {
        return digits[(int)(value - '0')][row];
    }
    if (value == 'X') {
        return glyph_x[row];
    }
    if (value == 'Y') {
        return glyph_y[row];
    }
    if (value == '=') {
        return glyph_equal[row];
    }
    return 0;
}

static void draw_bitmap_text(s32 x, s32 y, const char *text, u32 color) {
    while (*text) {
        int row;

        for (row = 0; row < 7; ++row) {
            u8 bits = glyph_row(*text, row);
            int column;

            for (column = 0; column < 5; ++column) {
                if (bits & (u8)(0x10u >> column)) {
                    (void)bda_gui_put_pixel(
                        g_draw, x + column, y + row, color
                    );
                }
            }
        }
        x += 6;
        ++text;
    }
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
        if (x + delta >= 0 && x + delta < SCREEN_WIDTH) {
            (void)bda_gui_put_pixel(g_draw, x + delta, y, color);
        }
        if (y + delta >= 0 && y + delta < SCREEN_HEIGHT) {
            (void)bda_gui_put_pixel(g_draw, x, y + delta, color);
        }
    }
}

/* Static labels are atomic only in the firmware object-paint scope. */
static void draw_initial_scene(void) {
    bda_handle_t base_draw;
    bda_handle_t object_draw;
    int object_draw_active;
    void *old_object;
    u32 foreground;

    if (!g_draw || !g_draw_object) {
        return;
    }
    base_draw = g_draw;
    object_draw = bda_gui_object_draw_begin(g_frame);
    object_draw_active = object_draw && (s32)(u32)object_draw != -1;
    if (object_draw_active) {
        g_draw = object_draw;
    }

    foreground = (u32)bda_gui_rgb(g_draw, 245, 248, 250);
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    bda_gui_rectangle(g_draw, 7, 50, 232, 276);
    (void)bda_gui_set_text_mode(g_draw, 1);
    (void)bda_gui_set_text_color(g_draw, foreground);
    (void)bda_gui_draw_text(g_draw, 42, 6, "TOUCH SCREEN TEST", -1);
    (void)bda_gui_draw_text(g_draw, 82, 303, "ESC EXIT", -1);
    (void)bda_gui_select_draw_object(g_draw, old_object);

    if (object_draw_active) {
        bda_gui_object_draw_end(g_frame, object_draw);
        g_draw = base_draw;
    }
}

/* Runtime pixels need the complete +0x074(1/0) guard to become visible. */
static void draw_dynamic_scene(void) {
    char status[16];
    void *old_object;
    u32 background;
    u32 foreground;
    u32 cross_color;

    if (!g_draw || !g_draw_object || !g_has_touch) {
        return;
    }
    background = (u32)bda_gui_rgb(g_draw, 0, 0, 0);
    foreground = (u32)bda_gui_rgb(g_draw, 245, 248, 250);
    cross_color = (u32)bda_gui_rgb(g_draw, 35, 210, 225);

    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    if (g_has_painted_cross) {
        draw_cross(g_painted_x, g_painted_y, background);
    }
    if (g_has_painted_status) {
        build_coordinate_status(status, g_painted_x, g_painted_y);
        draw_bitmap_text(42, 29, status, background);
    }
    build_coordinate_status(status, g_touch_x, g_touch_y);
    draw_bitmap_text(42, 29, status, foreground);
    draw_cross(g_touch_x, g_touch_y, cross_color);
    g_painted_x = g_touch_x;
    g_painted_y = g_touch_y;
    g_has_painted_cross = 1;
    g_has_painted_status = 1;
    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
}

static void draw_scene(void) {
    if (g_initial_scene_drawn && g_has_touch) {
        draw_dynamic_scene();
    } else {
        draw_initial_scene();
    }
}

static int touch_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        bda_handle_t previous_draw = g_draw;

        g_frame = handle;
        (void)acquire_draw_context(handle);
        if (!g_draw_object) {
            g_draw_object = bda_gui_draw_object_create(7);
        }
        if (!g_initial_scene_drawn || g_draw != previous_draw) {
            g_need_draw = 1;
        }
    } else if (message == BDA_MSG_REDRAW_INPUT) {
        if (g_initial_scene_drawn &&
            !g_initial_redraw_suppressed &&
            !g_has_touch) {
            g_initial_redraw_suppressed = 1;
        } else {
            g_need_draw = 1;
        }
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        if (!g_draw_owner || g_draw_owner == handle) {
            release_draw_context();
        }
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
    u32 close_wait;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_draw_owner = 0;
    g_draw_object = 0;
    g_exit = 0;
    g_need_draw = 1;
    g_queue_read = 0;
    g_queue_write = 0;
    g_has_touch = 0;
    g_has_painted_cross = 0;
    g_has_painted_status = 0;
    g_initial_scene_drawn = 0;
    g_initial_redraw_suppressed = 0;
    close_requested = 0;
    close_wait = 0;

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
    (void)acquire_draw_context(g_frame);
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create(7);
    }
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        bda_msgbox("Touch", "draw context failed");
        (void)bda_gui_frame_stop(g_frame);
        (void)bda_gui_frame_release(g_frame);
        release_draw_context();
        bda_gui_close_frame(g_frame);
        return 2;
    }
    draw_initial_scene();
    g_initial_scene_drawn = 1;
    g_need_draw = 0;

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
            ++close_wait;
            if (!pump_result || g_exit || close_wait >= 128u) {
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

    release_draw_context();
    if (g_frame) {
        bda_gui_close_frame(g_frame);
        g_frame = 0;
    }
    return 0;
}
