#include "../bda_research_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define PREVIEW_SIZE 100

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEJPG.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEJPG.TXT";
static const char k_jpeg_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xce\xd2\xb5\xc4\xcf\xe0\xb2\xe1\\gcddh.jpg";
static const char k_window_title[] = "IMGV7";

static const char *g_log_path;
static char g_line[160];
static bda_picture_like_t g_mode0_picture;
static bda_picture_like_t g_mode1_picture;
static int g_mode0_ok;
static int g_mode1_ok;
static int g_failures;
static int g_render_done;
static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static volatile int g_exit;
static volatile int g_need_draw;

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
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, value);
    write_line(out);
}

static void log_picture(const char *section, const bda_picture_like_t *picture) {
    log_text(section);
    log_value("PIXELS=", (u32)picture->pixels);
    log_value("WIDTH=", picture->width);
    log_value("HEIGHT=", picture->height);
    log_value("STRIDE=", picture->stride_bytes);
    log_value("MODE=", picture->mode10);
    log_value("BPP=", picture->bits_per_pixel11);
    log_value("SOURCE PIXELS=", (u32)picture->source_pixels);
    log_value("SELECTED=", (u32)picture->selected_index);
}

static int picture_is_valid(const bda_picture_like_t *picture) {
    return picture->width > 0 && picture->height > 0 &&
        picture->width <= 640u && picture->height <= 640u &&
        picture->source_pixels != 0;
}

static void decode_jpeg_modes(void) {
    int result;

    bda_memset(&g_mode0_picture, 0, sizeof(g_mode0_picture));
    bda_memset(&g_mode1_picture, 0, sizeof(g_mode1_picture));
    g_mode0_picture.selected_index = -1;
    g_mode1_picture.selected_index = -1;

    log_text("BEFORE JPEG MODE0");
    result = bda_gui_decode_jpeg_like(
        g_draw, &g_mode0_picture, k_jpeg_path, 0
    );
    log_value("MODE0 RETURN=", (u32)result);
    log_picture("[MODE0 DESCRIPTOR]", &g_mode0_picture);
    g_mode0_ok = result == 0 && picture_is_valid(&g_mode0_picture);
    if (!g_mode0_ok) {
        ++g_failures;
    }

    log_text("BEFORE JPEG MODE1");
    result = bda_gui_decode_jpeg_like(
        g_draw, &g_mode1_picture, k_jpeg_path, 1
    );
    log_value("MODE1 RETURN=", (u32)result);
    log_picture("[MODE1 DESCRIPTOR]", &g_mode1_picture);
    g_mode1_ok = result == 0 && picture_is_valid(&g_mode1_picture);
    if (!g_mode1_ok) {
        ++g_failures;
    }
    log_value(
        "SAME SOURCE=",
        g_mode0_picture.source_pixels == g_mode1_picture.source_pixels
    );
}

static void draw_scene(void) {
    bda_handle_t base_draw;
    bda_handle_t object_draw;
    int object_draw_active;
    void *old_object;
    u32 black;
    u32 cyan;

    if (!g_draw || !g_draw_object) {
        return;
    }
    base_draw = g_draw;
    object_draw = bda_gui_object_draw_begin_like(g_frame);
    object_draw_active = object_draw && (s32)(u32)object_draw != -1;
    if (object_draw_active) {
        g_draw = object_draw;
    }

    black = (u32)bda_gui_rgb_like(g_draw, 18, 22, 28);
    cyan = (u32)bda_gui_rgb_like(g_draw, 0, 145, 165);
    old_object = bda_gui_select_draw_object_like(g_draw, g_draw_object);
    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, black);
    (void)bda_gui_draw_text_like(g_draw, 42, 8, "JPEG PIPELINE V7", -1);
    (void)bda_gui_draw_text_like(g_draw, 34, 42, "MODE 0", -1);
    (void)bda_gui_draw_text_like(g_draw, 150, 42, "MODE 1", -1);

    if (g_mode0_ok) {
        log_value(
            "MODE0 RENDER=",
            (u32)bda_gui_render_picture_like(
                g_draw, 10, 68, PREVIEW_SIZE, PREVIEW_SIZE, &g_mode0_picture
            )
        );
    }
    if (g_mode1_ok) {
        log_value(
            "MODE1 RENDER=",
            (u32)bda_gui_render_picture_like(
                g_draw, 130, 68, PREVIEW_SIZE, PREVIEW_SIZE, &g_mode1_picture
            )
        );
    }
    bda_gui_rectangle_like(g_draw, 8, 66, 111, 169);
    bda_gui_rectangle_like(g_draw, 128, 66, 231, 169);

    (void)bda_gui_set_text_color_like(g_draw, cyan);
    (void)bda_gui_draw_text_like(
        g_draw, 45, 205, g_mode0_ok ? "MODE 0 PASS" : "MODE 0 FAIL", -1
    );
    (void)bda_gui_draw_text_like(
        g_draw, 45, 235, g_mode1_ok ? "MODE 1 PASS" : "MODE 1 FAIL", -1
    );
    (void)bda_gui_set_text_color_like(g_draw, black);
    (void)bda_gui_draw_text_like(g_draw, 80, 300, "ESC EXIT", -1);
    (void)bda_gui_select_draw_object_like(g_draw, old_object);

    if (object_draw_active) {
        bda_gui_object_draw_end_like(g_frame, object_draw);
        g_draw = base_draw;
    }
    g_render_done = 1;
}

static int image_window_proc(
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

static void cleanup_pictures(void) {
    void *mode0_source = g_mode0_picture.source_pixels;
    void *mode1_source = g_mode1_picture.source_pixels;

    log_text("BEFORE PICTURE CLEANUP");
    if (mode0_source) {
        bda_gui_picture_source_free_like(&g_mode0_picture);
        g_mode0_picture.source_pixels = 0;
        log_text("MODE0 SOURCE FREED");
    }
    if (mode1_source && mode1_source != mode0_source) {
        bda_gui_picture_source_free_like(&g_mode1_picture);
        log_text("MODE1 SOURCE FREED");
    } else if (mode1_source) {
        log_text("MODE1 SOURCE SHARED");
    }
    g_mode1_picture.source_pixels = 0;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t descriptor;
    bda_gui_message_like_t message;
    int close_requested = 0;
    u32 close_wait = 0;

    reset_log();
    log_text("START GAME JPEG PROBE V7");
    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_exit = 0;
    g_need_draw = 1;
    g_mode0_ok = 0;
    g_mode1_ok = 0;
    g_failures = 0;
    g_render_done = 0;

    descriptor.style = 0;
    descriptor.title = k_window_title;
    descriptor.wndproc = image_window_proc;
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

    decode_jpeg_modes();
    draw_scene();
    g_need_draw = 0;
    log_text("LOOP READY");

    for (;;) {
        bda_gui_input_packet_like_t packet;
        int pump_result;

        pump_result = bda_gui_event_pump_frame_once_like(&message, g_frame);
        if (g_need_draw && g_render_done) {
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
    cleanup_pictures();
    log_value("FAILURES=", (u32)g_failures);
    log_text(g_failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END GAME JPEG PROBE V7");
    return g_failures ? 3 : 0;
}
