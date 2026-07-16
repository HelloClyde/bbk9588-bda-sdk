#include "../bda_research_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEG12.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEG12.TXT";
static const char k_window_title[] = "GFXV12";

static const char *g_log_path;
static char g_line[160];
static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static volatile int g_exit;
static volatile int g_need_draw;
static int g_scene_logged;
static int g_failures;

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
    for (shift = 28; shift >= 0 && out < end; shift -= 4) {
        *out++ = hex[(value >> shift) & 0x0fu];
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
    u32 length;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "\r\n");
    *out = 0;
    length = (u32)(out - g_line);
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
    char *out = append_text(g_line, g_line + sizeof(g_line) - 1, label);
    write_line(append_hex32(out, g_line + sizeof(g_line) - 1, value));
}

static void draw_center_mark(bda_handle_t context, s32 x, s32 y) {
    bda_gui_move_to_like(context, x - 3, y);
    bda_gui_line_to_like(context, x + 3, y);
    bda_gui_move_to_like(context, x, y - 3);
    bda_gui_line_to_like(context, x, y + 3);
}

static void draw_scene(void) {
    bda_handle_t base_draw;
    bda_handle_t object_draw;
    int object_draw_active;
    void *old_object;
    u32 foreground;
    u32 accent;

    if (!g_draw || !g_draw_object) {
        return;
    }

    base_draw = g_draw;
    object_draw = bda_gui_object_draw_begin_like(g_frame);
    object_draw_active = object_draw && (s32)(u32)object_draw != -1;
    if (object_draw_active) {
        g_draw = object_draw;
    }

    foreground = (u32)bda_gui_rgb_like(g_draw, 245, 248, 250);
    accent = (u32)bda_gui_rgb_like(g_draw, 25, 205, 215);
    old_object = bda_gui_select_draw_object_like(g_draw, g_draw_object);
    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 22, 7, "ARC + ROUND RECT V12", -1);
    (void)bda_gui_set_text_color_like(g_draw, accent);
    (void)bda_gui_draw_text_like(g_draw, 18, 39, "ARC 0-180", -1);
    (void)bda_gui_draw_text_like(g_draw, 126, 39, "ARC 180-360", -1);
    bda_gui_arc_like(g_draw, 60, 101, 0, 180, 43);
    bda_gui_arc_like(g_draw, 180, 101, 180, 360, 43);
    draw_center_mark(g_draw, 60, 101);
    draw_center_mark(g_draw, 180, 101);

    (void)bda_gui_set_text_color_like(g_draw, accent);
    (void)bda_gui_draw_text_like(g_draw, 27, 153, "ROUND O", -1);
    (void)bda_gui_draw_text_like(g_draw, 147, 153, "ROUND F", -1);
    bda_gui_round_rect_like(g_draw, 60, 220, 96, 70, 18, 18, 0);
    bda_gui_round_rect_like(g_draw, 180, 220, 96, 70, 18, 18, 1);

    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 80, 296, "ESC EXIT", -1);
    (void)bda_gui_select_draw_object_like(g_draw, old_object);

    if (!g_scene_logged) {
        g_scene_logged = 1;
        log_value("DRAW=", (u32)g_draw);
        log_value("OBJECT=", (u32)g_draw_object);
        log_value("ARC CALLS=", 2);
        log_value("ROUND RECT CALLS=", 2);
        log_value("FAILURES NOW=", (u32)g_failures);
    }

    if (object_draw_active) {
        bda_gui_object_draw_end_like(g_frame, object_draw);
        g_draw = base_draw;
    }
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
        if (!g_draw_object) {
            g_draw_object = bda_gui_draw_object_create_like(7);
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
    log_text("START GAME ARC ROUND RECT PROBE V12");
    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_exit = 0;
    g_need_draw = 1;
    g_scene_logged = 0;
    g_failures = 0;

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
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create_like(7);
    }
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        log_text("RESULT=DRAW CONTEXT FAIL");
        return 2;
    }

    draw_scene();
    g_need_draw = 0;
    log_text("LOOP READY");

    for (;;) {
        bda_gui_input_packet_like_t packet;
        int pump_result = bda_gui_event_pump_frame_once_like(&message, g_frame);

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
    log_value("FAILURES=", (u32)g_failures);
    log_text(g_failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END GAME ARC ROUND RECT PROBE V12");
    return g_failures ? 3 : 0;
}
