#include "../bda_research_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEG14.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEG14.TXT";
static const char k_window_title[] = "GFXV14";

static const bda_point_like_t k_viewport_extent = {3, 2};
static const bda_point_like_t k_viewport_origin = {20, 40};
static const bda_point_like_t k_window_extent = {2, 1};
static const bda_point_like_t k_window_origin = {5, 7};
static const bda_point_like_t k_logical_point = {25, 27};
static const bda_point_like_t k_map_device_point = {50, 80};

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

static void log_pair(const char *label, const bda_point_like_t *pair) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, (u32)pair->x);
    out = append_text(out, end, ",");
    out = append_hex32(out, end, (u32)pair->y);
    write_line(out);
}

static int pair_equals(
    const bda_point_like_t *left,
    const bda_point_like_t *right
) {
    return left->x == right->x && left->y == right->y;
}

static void draw_cross(bda_handle_t context, s32 x, s32 y, s32 radius) {
    bda_gui_move_to_like(context, x - radius, y);
    bda_gui_line_to_like(context, x + radius, y);
    bda_gui_move_to_like(context, x, y - radius);
    bda_gui_line_to_like(context, x, y + radius);
}

static void probe_and_draw_coordinates(bda_handle_t context) {
    bda_point_like_t old_viewport_extent;
    bda_point_like_t old_viewport_origin;
    bda_point_like_t old_window_extent;
    bda_point_like_t old_window_origin;
    bda_point_like_t map_forward = k_logical_point;
    bda_point_like_t map_reverse;
    bda_point_like_t full_forward = k_logical_point;
    bda_point_like_t full_reverse;
    int old_mode = bda_gui_map_mode_get_like(context);

    bda_gui_viewport_extent_get_like(context, &old_viewport_extent);
    bda_gui_viewport_origin_get_like(context, &old_viewport_origin);
    bda_gui_window_extent_get_like(context, &old_window_extent);
    bda_gui_window_origin_get_like(context, &old_window_origin);

    bda_gui_viewport_extent_set_like(context, &k_viewport_extent);
    bda_gui_viewport_origin_set_like(context, &k_viewport_origin);
    bda_gui_window_extent_set_like(context, &k_window_extent);
    bda_gui_window_origin_set_like(context, &k_window_origin);
    bda_gui_map_mode_set_like(context, 1);

    bda_gui_map_logical_to_device_point_like(context, &map_forward);
    map_reverse = map_forward;
    bda_gui_map_device_to_logical_point_like(context, &map_reverse);
    bda_gui_logical_to_device_point_like(context, &full_forward);
    full_reverse = full_forward;
    bda_gui_device_to_logical_point_like(context, &full_reverse);

    if (!pair_equals(&map_forward, &k_map_device_point)) {
        ++g_failures;
    }
    if (!pair_equals(&map_reverse, &k_logical_point)) {
        ++g_failures;
    }
    if (!pair_equals(&full_reverse, &k_logical_point)) {
        ++g_failures;
    }

    if (!g_scene_logged) {
        log_pair("LOGICAL=", &k_logical_point);
        log_pair("MAP L2D=", &map_forward);
        log_pair("MAP D2L=", &map_reverse);
        log_pair("FULL L2D=", &full_forward);
        log_pair("FULL D2L=", &full_reverse);
    }

    draw_cross(context, k_logical_point.x, k_logical_point.y, 7);
    bda_gui_circle_like(context, k_logical_point.x, k_logical_point.y, 10);

    bda_gui_map_mode_set_like(context, 0);
    bda_gui_viewport_extent_set_like(context, &old_viewport_extent);
    bda_gui_viewport_origin_set_like(context, &old_viewport_origin);
    bda_gui_window_extent_set_like(context, &old_window_extent);
    bda_gui_window_origin_set_like(context, &old_window_origin);
    bda_gui_map_mode_set_like(context, old_mode);

    bda_gui_rectangle_like(
        context,
        map_forward.x - 13,
        map_forward.y - 13,
        map_forward.x + 13,
        map_forward.y + 13
    );
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
    (void)bda_gui_draw_text_like(g_draw, 36, 7, "COORD XFORM V14", -1);
    (void)bda_gui_set_text_color_like(g_draw, accent);
    (void)bda_gui_draw_text_like(g_draw, 32, 35, "L(25,27) -> D(50,80)", -1);

    probe_and_draw_coordinates(g_draw);

    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 23, 125, "CROSS + BOX MUST OVERLAP", -1);
    (void)bda_gui_draw_text_like(g_draw, 80, 296, "ESC EXIT", -1);
    (void)bda_gui_select_draw_object_like(g_draw, old_object);

    if (!g_scene_logged) {
        g_scene_logged = 1;
        log_value("FAILURES NOW=", (u32)g_failures);
        log_text(g_failures ? "COORD XFORM=FAIL" : "COORD XFORM=PASS");
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
    log_text("START GAME COORD XFORM PROBE V14");
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
    log_text("END GAME COORD XFORM PROBE V14");
    return g_failures ? 3 : 0;
}
