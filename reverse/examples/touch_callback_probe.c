#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define TOUCH_DOWN_MESSAGE 1u
#define TOUCH_UP_MESSAGE 2u

static const char k_log_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHAPI.TXT";

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static volatile int g_pending;
static volatile u32 g_touch_message;
static volatile u32 g_touch_lparam;
static char g_status[64];

static char *append_text(char *out, const char *text) {
    while (*text) {
        *out++ = *text++;
    }
    return out;
}

static char *append_dec(char *out, s32 value) {
    char digits[12];
    u32 magnitude;
    int count = 0;
    if (value < 0) {
        *out++ = '-';
        magnitude = (u32)(0 - value);
    } else {
        magnitude = (u32)value;
    }
    if (magnitude == 0) {
        *out++ = '0';
        return out;
    }
    while (magnitude) {
        digits[count++] = (char)('0' + magnitude % 10u);
        magnitude /= 10u;
    }
    while (count) {
        *out++ = digits[--count];
    }
    return out;
}

static s32 event_x(u32 lparam) {
    return (s32)(s16)BDA_LOWORD(lparam);
}

static s32 event_y(u32 lparam) {
    return (s32)(s16)BDA_HIWORD(lparam);
}

static void build_status(u32 message, u32 lparam) {
    char *out = g_status;
    out = append_text(out, message == TOUCH_DOWN_MESSAGE ? "DOWN" : "UP");
    out = append_text(out, " X=");
    out = append_dec(out, event_x(lparam));
    out = append_text(out, " Y=");
    out = append_dec(out, event_y(lparam));
    *out = 0;
}

static void write_status(void) {
    int file = bda_fs_fopen_raw(k_log_path, "wb");
    u32 length = 0;
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    while (g_status[length]) {
        ++length;
    }
    (void)bda_fs_write_raw(file, g_status, length);
    (void)bda_fs_close_raw(file);
}

static void draw_initial_scene(void) {
    void *old_object;
    u32 white;
    if (!g_draw || !g_draw_object) {
        return;
    }
    old_object = bda_gui_select_draw_object_like(g_draw, g_draw_object);
    white = (u32)bda_gui_rgb_like(g_draw, 245, 248, 250);
    (void)bda_gui_draw_guard_begin_like();
    bda_gui_rectangle_like(g_draw, 8, 38, 231, 286);
    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, white);
    (void)bda_gui_draw_text_like(g_draw, 48, 10, "TOUCH SCREEN", -1);
    (void)bda_gui_draw_text_like(g_draw, 45, 296, "WAITING FOR TOUCH", -1);
    (void)bda_gui_select_draw_object_like(g_draw, old_object);
    (void)bda_gui_draw_guard_end_like();
}

static void draw_event(u32 message, u32 lparam) {
    s32 x = event_x(lparam);
    s32 y = event_y(lparam);
    int delta;
    u32 red = message == TOUCH_DOWN_MESSAGE ? 250u : 35u;
    u32 green = message == TOUCH_DOWN_MESSAGE ? 65u : 210u;
    u32 blue = 45u;
    u32 white;
    if (!g_draw || x < 0 || x >= SCREEN_WIDTH || y < 0 || y >= SCREEN_HEIGHT) {
        return;
    }
    for (delta = -10; delta <= 10; ++delta) {
        if (x + delta >= 0 && x + delta < SCREEN_WIDTH) {
            (void)bda_gui_put_pixel_rgb_like(g_draw, x + delta, y, red, green, blue);
        }
        if (y + delta >= 0 && y + delta < SCREEN_HEIGHT) {
            (void)bda_gui_put_pixel_rgb_like(g_draw, x, y + delta, red, green, blue);
        }
    }
    white = (u32)bda_gui_rgb_like(g_draw, 245, 248, 250);
    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, white);
    (void)bda_gui_draw_text_like(g_draw, 40, 296, g_status, -1);
    (void)bda_gui_invalidate_window_like(g_frame);
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
        draw_initial_scene();
    } else if (message == TOUCH_DOWN_MESSAGE || message == TOUCH_UP_MESSAGE) {
        g_touch_message = message;
        g_touch_lparam = lparam;
        g_pending = 1;
        return 1;
    } else if (message == BDA_MSG_REDRAW_INPUT_LIKE) {
        draw_initial_scene();
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH_LIKE) {
        g_draw = 0;
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t descriptor;
    bda_gui_message_like_t message;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_pending = 0;

    descriptor.style = 0x08000000u;
    descriptor.wndproc = touch_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = (u32)bda_gui_frame_surface_like(15);

    g_frame = bda_gui_register_frame_desc_like(&descriptor);
    if (!g_frame || (s32)g_frame == -1) {
        return 1;
    }
    (void)bda_gui_frame_activate_like(g_frame, 0x100);
    if (!g_draw) {
        g_draw = bda_gui_current_draw_like(g_frame);
    }
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create_like(7);
    }
    draw_initial_scene();

    for (;;) {
        bda_gui_input_packet_like_t packet;
        (void)bda_gui_event_pump_frame_once_like(&message, g_frame);
        if (g_pending) {
            u32 touch_message = g_touch_message;
            u32 touch_lparam = g_touch_lparam;
            g_pending = 0;
            build_status(touch_message, touch_lparam);
            draw_event(touch_message, touch_lparam);
            write_status();
        }
        (void)bda_gui_input_packet_like(&packet);
        if (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE)) {
            break;
        }
        bda_sys_delay_like(1);
    }
    return 0;
}
