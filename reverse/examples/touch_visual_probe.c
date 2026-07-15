#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320

static const char k_log_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHAPI.TXT";

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static volatile int g_ready;
static volatile int g_pending;
static volatile u32 g_message;
static volatile u32 g_wparam;
static volatile u32 g_lparam;
static char g_status[96];

static void append_char(char **out, char value) {
    **out = value;
    *out += 1;
}

static void append_text(char **out, const char *text) {
    while (*text) {
        append_char(out, *text++);
    }
}

static void append_dec(char **out, s32 value) {
    char digits[12];
    u32 magnitude;
    int count = 0;

    if (value < 0) {
        append_char(out, '-');
        magnitude = (u32)(0 - value);
    } else {
        magnitude = (u32)value;
    }
    if (magnitude == 0) {
        append_char(out, '0');
        return;
    }
    while (magnitude) {
        digits[count++] = (char)('0' + magnitude % 10u);
        magnitude /= 10u;
    }
    while (count) {
        append_char(out, digits[--count]);
    }
}

static void append_hex32(char **out, u32 value) {
    static const char digits[] = "0123456789ABCDEF";
    int shift;
    append_text(out, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        append_char(out, digits[(value >> shift) & 0x0fu]);
    }
}

static s32 touch_x(u32 lparam) {
    return (s32)(s16)(lparam & 0xffffu);
}

static s32 touch_y(u32 lparam) {
    return (s32)(s16)((lparam >> 16) & 0xffffu);
}

static void build_status(char source, u32 message, u32 wparam, u32 lparam) {
    char *out = g_status;
    append_text(&out, "SRC=");
    append_char(&out, source);
    append_text(&out, " M=");
    append_dec(&out, (s32)message);
    append_text(&out, " X=");
    append_dec(&out, touch_x(lparam));
    append_text(&out, " Y=");
    append_dec(&out, touch_y(lparam));
    append_text(&out, "\nW=");
    append_hex32(&out, wparam);
    append_text(&out, " L=");
    append_hex32(&out, lparam);
    append_char(&out, 0);
}

static void write_status_log(void) {
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
    bda_gui_rectangle_like(g_draw, 8, 38, 231, 300);
    bda_gui_move_to_like(g_draw, 120, 45);
    bda_gui_line_to_like(g_draw, 120, 294);
    bda_gui_move_to_like(g_draw, 14, 160);
    bda_gui_line_to_like(g_draw, 225, 160);
    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, white);
    (void)bda_gui_draw_text_like(g_draw, 48, 10, "TOUCH SCREEN", -1);
    (void)bda_gui_select_draw_object_like(g_draw, old_object);
    (void)bda_gui_draw_guard_end_like();
}

static void draw_touch_event(u32 message, u32 lparam) {
    s32 x = touch_x(lparam);
    s32 y = touch_y(lparam);
    int delta;
    u32 red = message == 1 ? 245u : 250u;
    u32 green = message == 1 ? 70u : 190u;
    u32 blue = message == 1 ? 65u : 35u;
    u32 white;

    if (!g_draw || x < 0 || x >= SCREEN_WIDTH || y < 0 || y >= SCREEN_HEIGHT) {
        return;
    }
    for (delta = -8; delta <= 8; ++delta) {
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
    (void)bda_gui_draw_text_like(g_draw, 12, 306, g_status, -1);
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
        g_ready = 1;
    } else if (g_ready && (message == 1u || message == 2u)) {
        g_message = message;
        g_wparam = wparam;
        g_lparam = lparam;
        g_pending = 1;
        return 1;
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH_LIKE) {
        g_ready = 0;
        g_draw = 0;
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t descriptor;
    bda_gui_message_like_t message;
    u16 touch_x_value = 0xffffu;
    u16 touch_y_value = 0xffffu;
    u16 last_x = 0xffffu;
    u16 last_y = 0xffffu;
    int touch_down_value;
    int last_down = -1;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_ready = 0;
    g_pending = 0;

    descriptor.style = 0x08000000u;
    descriptor.title = 0;
    descriptor.wndproc = touch_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = (u32)bda_gui_draw_object_create_like(15);

    g_frame = bda_gui_register_frame_desc_like(&descriptor);
    if (!g_frame || (s32)g_frame == -1) {
        bda_msgbox("Touch", "frame registration failed");
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
    g_ready = 1;

    for (;;) {
        bda_gui_input_packet_like_t packet;
        (void)bda_gui_event_pump_frame_once_like(&message, g_frame);
        touch_down_value = bda_touch_pressed_9588() != 0;
        if (touch_down_value) {
            bda_gui_touch_position_like(&touch_x_value, &touch_y_value);
        }
        if (touch_down_value != last_down ||
            (touch_down_value &&
             (touch_x_value != last_x || touch_y_value != last_y))) {
            u32 lparam = BDA_MAKEWORD(touch_x_value, touch_y_value);
            last_down = touch_down_value;
            last_x = touch_x_value;
            last_y = touch_y_value;
            build_status('P', touch_down_value ? 1u : 2u, 0, lparam);
            draw_touch_event(touch_down_value ? 1u : 2u, lparam);
            write_status_log();
        }
        if (g_pending) {
            u32 message = g_message;
            u32 wparam = g_wparam;
            u32 lparam = g_lparam;
            g_pending = 0;
            build_status('C', message, wparam, lparam);
            draw_touch_event(message, lparam);
            write_status_log();
        }
        (void)bda_gui_input_packet_like(&packet);
        if (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE)) {
            break;
        }
        bda_sys_delay_like(1);
    }
    return 0;
}
