#include "../bda_research_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define VX_WIDTH 48
#define VX_HEIGHT 48
#define VX_HEADER_SIZE 24
#define VX_BYTES (VX_HEADER_SIZE + VX_WIDTH * VX_HEIGHT * 2)

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEGFX.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEGFX.TXT";
static const char k_window_title[] = "GFXV3";

static const char *g_log_path;
static char g_line[160];
static u8 g_vx[VX_BYTES];
static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_object7;
static void *g_object8;
static volatile int g_exit;
static volatile int g_need_draw;
static int g_context_logged;
static u32 g_draw_count;

static char *append_text(char *out, char *end, const char *text) {
    while (*text && out < end) {
        *out++ = *text++;
    }
    return out;
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char hex[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        if (out < end) {
            *out++ = hex[(value >> shift) & 0x0fu];
        }
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

static void write_line(char *end) {
    int file;
    u32 length;
    char *limit = g_line + sizeof(g_line) - 1;

    end = append_text(end, limit, "\r\n");
    *end = 0;
    length = (u32)(end - g_line);
    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_line, length);
    (void)bda_fs_close_raw(file);
}

static void log_text(const char *text) {
    write_line(append_text(g_line, g_line + sizeof(g_line) - 1, text));
}

static void log_value(const char *label, u32 value) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, value);
    write_line(out);
}

static void write_u32_le(u8 *out, u32 value) {
    out[0] = (u8)value;
    out[1] = (u8)(value >> 8);
    out[2] = (u8)(value >> 16);
    out[3] = (u8)(value >> 24);
}

static u16 rgb565(u32 red, u32 green, u32 blue) {
    return (u16)(((red & 0xf8u) << 8) | ((green & 0xfcu) << 3) | (blue >> 3));
}

static void init_vx(void) {
    int x;
    int y;

    bda_memset(g_vx, 0, sizeof(g_vx));
    g_vx[0] = 'V';
    g_vx[1] = 'X';
    g_vx[2] = 0xcc;
    g_vx[3] = 0xcc;
    g_vx[4] = 0xcc;
    g_vx[5] = 0xcc;
    write_u32_le(g_vx + 6, VX_WIDTH);
    write_u32_le(g_vx + 10, VX_HEIGHT);
    for (x = 14; x < 20; ++x) {
        g_vx[x] = 0xcc;
    }
    for (x = 20; x < VX_HEADER_SIZE; ++x) {
        g_vx[x] = 0xff;
    }

    for (y = 0; y < VX_HEIGHT; ++y) {
        for (x = 0; x < VX_WIDTH; ++x) {
            u16 value;
            u32 offset = VX_HEADER_SIZE + (u32)(y * VX_WIDTH + x) * 2u;
            int cell = ((x / 8) + (y / 8)) & 1;

            if (x == y || x + y == VX_WIDTH - 1) {
                value = rgb565(250, 245, 245);
            } else if (cell) {
                value = rgb565(20, 190, 210);
            } else {
                value = rgb565(235, 155, 35);
            }
            g_vx[offset] = (u8)value;
            g_vx[offset + 1] = (u8)(value >> 8);
        }
    }
}

static void log_context_once(bda_handle_t draw, bda_handle_t object_draw) {
    bda_rect_like_t rect;
    int rect_result;

    if (g_context_logged) {
        return;
    }
    g_context_logged = 1;
    bda_memset(&rect, 0, sizeof(rect));
    rect_result = bda_gui_object_rect_like(g_frame, &rect);
    log_value("FRAME=", (u32)g_frame);
    log_value("DRAW=", (u32)draw);
    log_value("OBJECT DRAW=", (u32)object_draw);
    log_value("OBJECT7=", (u32)g_object7);
    log_value("OBJECT8=", (u32)g_object8);
    log_value("RECT RESULT=", (u32)rect_result);
    log_value("RECT X0=", (u32)rect.x0);
    log_value("RECT Y0=", (u32)rect.y0);
    log_value("RECT X1=", (u32)rect.x1);
    log_value("RECT Y1=", (u32)rect.y1);
    log_value("FONT=", (u32)bda_gui_current_font_like(draw));
    log_value("FONT CELL W=", (u32)bda_gui_font_cell_width_like(draw));
    log_value("FONT CELL H=", (u32)bda_gui_font_cell_height_like(draw));
}

static void draw_scene(void) {
    bda_handle_t base_draw;
    bda_handle_t object_draw;
    int object_draw_active;
    void *old_object;
    void *previous_object;
    u32 foreground;
    u32 cyan;
    u32 orange;
    int fill_old;
    int vx_result;

    if (!g_draw || !g_object7) {
        return;
    }

    base_draw = g_draw;
    object_draw = bda_gui_object_draw_begin_like(g_frame);
    object_draw_active = object_draw && (s32)(u32)object_draw != -1;
    if (object_draw_active) {
        g_draw = object_draw;
    }

    foreground = (u32)bda_gui_rgb_like(g_draw, 245, 248, 250);
    cyan = (u32)bda_gui_rgb_like(g_draw, 25, 195, 215);
    orange = (u32)bda_gui_rgb_like(g_draw, 235, 155, 35);
    old_object = bda_gui_select_draw_object_like(g_draw, g_object7);

    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 28, 6, "GRAPHICS MATRIX V3", -1);
    (void)bda_gui_draw_text_like(g_draw, 10, 35, "PRIMITIVES", -1);
    bda_gui_move_to_like(g_draw, 10, 56);
    bda_gui_line_to_like(g_draw, 228, 56);
    bda_gui_circle_like(g_draw, 45, 95, 25);
    bda_gui_rectangle_like(g_draw, 88, 70, 148, 120);
    (void)bda_gui_set_text_color_like(g_draw, cyan);
    (void)bda_gui_draw_text_like(g_draw, 158, 87, "LINE", -1);

    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 10, 136, "OBJECT 8 FILL?", -1);
    fill_old = bda_gui_set_fill_color_like(g_draw, orange);
    if (g_object8 && (s32)(u32)g_object8 != -1) {
        previous_object = bda_gui_select_draw_object_like(g_draw, g_object8);
        bda_gui_rectangle_like(g_draw, 18, 158, 100, 208);
        (void)bda_gui_select_draw_object_like(g_draw, previous_object);
    }

    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 130, 136, "VX SPRITE", -1);
    vx_result = bda_gui_draw_vx_like(g_draw, 150, 158, g_vx);
    bda_gui_rectangle_like(g_draw, 148, 156, 199, 207);

    (void)bda_gui_set_text_color_like(g_draw, cyan);
    (void)bda_gui_draw_text_like(g_draw, 35, 235, "FONT METRICS QUERIED", -1);
    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 80, 300, "ESC EXIT", -1);
    (void)bda_gui_select_draw_object_like(g_draw, old_object);

    if (object_draw_active) {
        bda_gui_object_draw_end_like(g_frame, object_draw);
        g_draw = base_draw;
    }

    log_context_once(base_draw, object_draw);
    if (g_draw_count == 0) {
        log_value("FILL OLD=", (u32)fill_old);
        log_value("VX RETURN=", (u32)vx_result);
    }
    ++g_draw_count;
    log_value("DRAW COUNT=", g_draw_count);
}

static int graphics_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE) {
        g_frame = handle;
        g_draw = bda_gui_current_draw_like(handle);
        if (!g_object7) {
            g_object7 = bda_gui_draw_object_create_like(7);
        }
        if (!g_object8) {
            g_object8 = bda_gui_draw_object_create_like(8);
        }
        g_need_draw = 1;
    } else if (message == BDA_MSG_REDRAW_INPUT_LIKE) {
        g_need_draw = 1;
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
    int close_requested = 0;
    u32 close_wait = 0;

    reset_log();
    log_text("START GAME GRAPHICS PROBE V3");
    init_vx();
    log_value("VX BYTES=", sizeof(g_vx));

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_object7 = 0;
    g_object8 = 0;
    g_exit = 0;
    g_need_draw = 1;
    g_context_logged = 0;
    g_draw_count = 0;

    descriptor.style = 0;
    descriptor.title = k_window_title;
    descriptor.wndproc = graphics_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = 0;

    log_text("BEFORE REGISTER");
    g_frame = (bda_handle_t)bda_gui_register_frame_like(&descriptor);
    log_value("REGISTER=", (u32)g_frame);
    if (!g_frame || (s32)g_frame == -1) {
        log_text("RESULT=FRAME FAIL");
        return 1;
    }
    log_value("ACTIVATE=", (u32)bda_gui_frame_activate_like(g_frame, 0x100));

    if (!g_draw) {
        g_draw = bda_gui_current_draw_like(g_frame);
    }
    if (!g_object7) {
        g_object7 = bda_gui_draw_object_create_like(7);
    }
    if (!g_object8) {
        g_object8 = bda_gui_draw_object_create_like(8);
    }
    if (!g_draw || !g_object7 || (s32)(u32)g_object7 == -1) {
        log_text("RESULT=DRAW CONTEXT FAIL");
        return 2;
    }

    draw_scene();
    g_need_draw = 0;
    log_text("LOOP READY");

    for (;;) {
        bda_gui_input_packet_like_t packet;
        int pump_result;

        pump_result = bda_gui_event_pump_frame_once_like(&message, g_frame);
        if (g_need_draw) {
            g_need_draw = 0;
            draw_scene();
        }
        (void)bda_gui_input_packet_like(&packet);
        bda_sys_delay_like(1);
        if (close_requested) {
            ++close_wait;
            if (!pump_result || g_exit || close_wait >= 128u) {
                break;
            }
            continue;
        }
        if (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE)) {
            log_text("ESC DOWN");
            wait_escape_release();
            log_text("ESC UP");
            log_value("STOP=", (u32)bda_gui_frame_stop_like(g_frame));
            log_value("RELEASE=", (u32)bda_gui_frame_release_like(g_frame));
            close_requested = 1;
        }
    }

    log_text("LOOP END");
    if (g_frame) {
        (void)bda_gui_close_frame_like(g_frame);
        g_frame = 0;
    }
    log_text("RESULT=PASS");
    log_text("END GAME GRAPHICS PROBE V3");
    return 0;
}
