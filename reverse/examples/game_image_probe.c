#include "../bda_research_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define IMAGE_WIDTH 32
#define IMAGE_HEIGHT 32
#define VX_HEADER_SIZE 24
#define VX_BYTES (VX_HEADER_SIZE + IMAGE_WIDTH * IMAGE_HEIGHT * 2)
#define BMP_HEADER_SIZE 54
#define BMP_ROW_BYTES (IMAGE_WIDTH * 3)
#define BMP_BYTES (BMP_HEADER_SIZE + BMP_ROW_BYTES * IMAGE_HEIGHT)

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEIMG.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEIMG.TXT";
static const char k_vx_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GFXTEST.VX";
static const char k_bmp_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GFXTEST.BMP";
#ifdef GAME_IMAGE_COMPAT_V6
static const char k_window_title[] = "IMGV6";
#elif defined(GAME_IMAGE_RENDER_V5)
static const char k_window_title[] = "IMGV5";
#else
static const char k_window_title[] = "IMGV4";
#endif

static const char *g_log_path;
static char g_line[160];
static u8 g_vx[VX_BYTES];
static u8 g_bmp[BMP_BYTES];
static bda_picture_like_t g_vx_picture;
static bda_picture_like_t g_bmp_picture;
static void *g_vx_source;
static void *g_bmp_source;
static int g_vx_decode_ok;
static int g_bmp_decode_ok;
static int g_render_done;
static int g_failures;
static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static volatile int g_exit;
static volatile int g_need_draw;
#ifdef GAME_IMAGE_COMPAT_V6
static bda_handle_t g_compat;
static int g_compat_copy_logged;
#endif

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

static void write_u16_le(u8 *out, u16 value) {
    out[0] = (u8)value;
    out[1] = (u8)(value >> 8);
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
    for (x = 2; x < 6; ++x) {
        g_vx[x] = 0xcc;
    }
    write_u32_le(g_vx + 6, IMAGE_WIDTH);
    write_u32_le(g_vx + 10, IMAGE_HEIGHT);
    for (x = 14; x < 20; ++x) {
        g_vx[x] = 0xcc;
    }
    for (x = 20; x < VX_HEADER_SIZE; ++x) {
        g_vx[x] = 0xff;
    }

    for (y = 0; y < IMAGE_HEIGHT; ++y) {
        for (x = 0; x < IMAGE_WIDTH; ++x) {
            u16 value;
            u32 offset = VX_HEADER_SIZE + (u32)(y * IMAGE_WIDTH + x) * 2u;

            if (x == y || x + y == IMAGE_WIDTH - 1) {
                value = rgb565(250, 250, 250);
            } else if (((x / 4) + (y / 4)) & 1) {
                value = rgb565(30, 205, 215);
            } else {
                value = rgb565(230, 145, 30);
            }
            write_u16_le(g_vx + offset, value);
        }
    }
}

static void init_bmp(void) {
    int x;
    int y;

    bda_memset(g_bmp, 0, sizeof(g_bmp));
    g_bmp[0] = 'B';
    g_bmp[1] = 'M';
    write_u32_le(g_bmp + 2, BMP_BYTES);
    write_u32_le(g_bmp + 10, BMP_HEADER_SIZE);
    write_u32_le(g_bmp + 14, 40);
    write_u32_le(g_bmp + 18, IMAGE_WIDTH);
    write_u32_le(g_bmp + 22, IMAGE_HEIGHT);
    write_u16_le(g_bmp + 26, 1);
    write_u16_le(g_bmp + 28, 24);
    write_u32_le(g_bmp + 34, BMP_ROW_BYTES * IMAGE_HEIGHT);
    write_u32_le(g_bmp + 38, 2835);
    write_u32_le(g_bmp + 42, 2835);

    for (y = 0; y < IMAGE_HEIGHT; ++y) {
        for (x = 0; x < IMAGE_WIDTH; ++x) {
            u32 offset = BMP_HEADER_SIZE + (u32)(y * BMP_ROW_BYTES + x * 3);
            int cell = ((x / 4) + (y / 4)) & 1;
            u8 red = cell ? 220 : 35;
            u8 green = cell ? 55 : 180;
            u8 blue = cell ? 70 : 220;

            if (x == 0 || y == 0 || x == IMAGE_WIDTH - 1 || y == IMAGE_HEIGHT - 1) {
                red = 250;
                green = 250;
                blue = 250;
            }
            g_bmp[offset] = blue;
            g_bmp[offset + 1] = green;
            g_bmp[offset + 2] = red;
        }
    }
}

static int write_resource(const char *path, const void *data, u32 size) {
    int file = bda_fs_fopen_raw(path, "wb");
    int written;
    int closed;

    if (!bda_fs_file_is_valid(file)) {
        return 0;
    }
    written = bda_fs_write_raw(file, data, size);
    closed = bda_fs_close_raw(file);
    return written == (int)size && closed == 0;
}

static void log_picture(const char *section, const bda_picture_like_t *picture, void *source) {
    log_text(section);
    log_value("OUT SOURCE=", (u32)source);
    log_value("PIXELS=", (u32)picture->pixels);
    log_value("WIDTH=", picture->width);
    log_value("HEIGHT=", picture->height);
    log_value("STRIDE=", picture->stride_bytes);
    log_value("MODE=", picture->mode10);
    log_value("BPP=", picture->bits_per_pixel11);
    log_value("SOURCE PIXELS=", (u32)picture->source_pixels);
    log_value("SELECTED=", (u32)picture->selected_index);
}

static int render_picture(
    bda_handle_t context,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    const bda_picture_like_t *picture
) {
    return bda_gui_render_picture_like(
        context, x, y, width, height, picture
    );
}

#ifdef GAME_IMAGE_COMPAT_V6
static int copy_context(
    bda_handle_t source_context,
    s32 source_x,
    s32 source_y,
    s32 width,
    s32 height,
    bda_handle_t destination_context,
    s32 destination_x,
    s32 destination_y,
    u32 backend_arg
) {
    return bda_gui_context_copy_like(
        source_context,
        source_x,
        source_y,
        width,
        height,
        destination_context,
        destination_x,
        destination_y,
        backend_arg
    );
}
#endif

static void picture_source_free(bda_picture_like_t *picture) {
    bda_gui_picture_source_free_like(picture);
    picture->source_pixels = 0;
}

static void decode_resources(void) {
    int result;

    bda_memset(&g_vx_picture, 0, sizeof(g_vx_picture));
    bda_memset(&g_bmp_picture, 0, sizeof(g_bmp_picture));
    g_vx_picture.selected_index = -1;
    g_bmp_picture.selected_index = -1;
    g_vx_source = 0;
    g_bmp_source = 0;

    log_text("BEFORE VX DECODE");
    result = bda_gui_decode_bmp_like(
        g_draw, &g_vx_picture, k_vx_path, &g_vx_source
    );
    log_value("VX DECODE RETURN=", (u32)result);
    log_picture("[VX DESCRIPTOR]", &g_vx_picture, g_vx_source);
    g_vx_decode_ok =
        result == 0 && g_vx_source &&
        g_vx_picture.width == IMAGE_WIDTH &&
        g_vx_picture.height == IMAGE_HEIGHT &&
        g_vx_picture.stride_bytes == IMAGE_WIDTH * 2u &&
        g_vx_picture.bits_per_pixel11 == 16u &&
        g_vx_picture.source_pixels == (void *)((u8 *)g_vx_source + VX_HEADER_SIZE);
    if (!g_vx_decode_ok) {
        ++g_failures;
    }

    log_text("BEFORE BMP DECODE");
    result = bda_gui_decode_bmp_like(
        g_draw, &g_bmp_picture, k_bmp_path, &g_bmp_source
    );
    log_value("BMP DECODE RETURN=", (u32)result);
    log_picture("[BMP DESCRIPTOR]", &g_bmp_picture, g_bmp_source);
    g_bmp_decode_ok =
        result == 0 &&
        g_bmp_picture.width == IMAGE_WIDTH &&
        g_bmp_picture.height == IMAGE_HEIGHT &&
        g_bmp_picture.source_pixels &&
        g_bmp_picture.selected_index == -1;
#ifndef GAME_IMAGE_RENDER_V5
    g_bmp_decode_ok =
        g_bmp_decode_ok &&
        g_bmp_picture.stride_bytes >= IMAGE_WIDTH * 2u &&
        g_bmp_picture.bits_per_pixel11 == 16u;
#endif
    if (!g_bmp_decode_ok) {
        ++g_failures;
    }
}

static void draw_scene(void) {
    bda_handle_t base_draw;
    bda_handle_t object_draw;
    int object_draw_active;
    void *old_object;
    u32 foreground;
    u32 cyan;
    int bmp_render = -1;

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
    cyan = (u32)bda_gui_rgb_like(g_draw, 30, 205, 215);
    old_object = bda_gui_select_draw_object_like(g_draw, g_draw_object);
    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, foreground);
#ifdef GAME_IMAGE_COMPAT_V6
    (void)bda_gui_draw_text_like(g_draw, 35, 8, "IMAGE PIPELINE V6", -1);
#elif defined(GAME_IMAGE_RENDER_V5)
    (void)bda_gui_draw_text_like(g_draw, 35, 8, "IMAGE PIPELINE V5", -1);
#else
    (void)bda_gui_draw_text_like(g_draw, 35, 8, "IMAGE PIPELINE V4", -1);
#endif
    (void)bda_gui_draw_text_like(g_draw, 10, 48, "DIRECT", -1);
    (void)bda_gui_draw_text_like(g_draw, 84, 48, "VX FILE", -1);
    (void)bda_gui_draw_text_like(g_draw, 162, 48, "BMP", -1);

    (void)bda_gui_draw_vx_like(g_draw, 18, 76, g_vx);
    if (g_vx_decode_ok) {
        (void)bda_gui_draw_vx_like(g_draw, 94, 76, g_vx_source);
    }
    if (g_bmp_decode_ok) {
        log_text("BEFORE BMP RENDER");
        bmp_render = render_picture(
            g_draw, 174, 76, IMAGE_WIDTH, IMAGE_HEIGHT, &g_bmp_picture
        );
        log_value("BMP RENDER RETURN=", (u32)bmp_render);
    }
    bda_gui_rectangle_like(g_draw, 16, 74, 51, 109);
    bda_gui_rectangle_like(g_draw, 92, 74, 127, 109);
    bda_gui_rectangle_like(g_draw, 172, 74, 207, 109);

    (void)bda_gui_set_text_color_like(g_draw, cyan);
    (void)bda_gui_draw_text_like(
        g_draw, 30, 145,
        g_vx_decode_ok ? "VX DECODE PASS" : "VX DECODE FAIL", -1
    );
    (void)bda_gui_draw_text_like(
        g_draw, 30, 175,
        g_bmp_decode_ok ? "BMP DECODE PASS" : "BMP DECODE FAIL", -1
    );
#ifdef GAME_IMAGE_COMPAT_V6
    if (g_compat && (s32)g_compat != -1) {
        int copy_result;

        (void)bda_gui_set_text_color_like(g_draw, foreground);
        (void)bda_gui_draw_text_like(g_draw, 60, 210, "COMPAT COPY", -1);
        log_text("BEFORE COMPAT COPY");
        copy_result = copy_context(
            g_compat, 0, 0, IMAGE_WIDTH, IMAGE_HEIGHT,
            g_draw, 104, 236, 0
        );
        if (!g_compat_copy_logged) {
            log_value("COMPAT COPY RETURN=", (u32)copy_result);
            g_compat_copy_logged = 1;
        }
        bda_gui_rectangle_like(g_draw, 102, 234, 137, 269);
    }
#endif
    (void)bda_gui_set_text_color_like(g_draw, foreground);
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
    log_text("BEFORE PICTURE CLEANUP");
#ifdef GAME_IMAGE_COMPAT_V6
    if (g_compat && (s32)g_compat != -1) {
        log_text("BEFORE COMPAT FREE");
        bda_gui_surface_flush_like(g_compat);
        g_compat = 0;
        log_text("COMPAT FREED");
    }
#endif
    if (g_vx_source) {
        bda_free(g_vx_source);
        g_vx_source = 0;
        g_vx_picture.source_pixels = 0;
        log_text("VX SOURCE FREED");
    }
    if (g_bmp_source) {
        bda_free(g_bmp_source);
        g_bmp_source = 0;
        g_bmp_picture.source_pixels = 0;
        log_text("BMP OUT SOURCE FREED");
    } else if (g_bmp_picture.source_pixels) {
        picture_source_free(&g_bmp_picture);
        log_text("BMP PICTURE SOURCE FREED");
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t descriptor;
    bda_gui_message_like_t message;
    int close_requested = 0;
    u32 close_wait = 0;

    reset_log();
#ifdef GAME_IMAGE_COMPAT_V6
    log_text("START GAME IMAGE PROBE V6");
#elif defined(GAME_IMAGE_RENDER_V5)
    log_text("START GAME IMAGE PROBE V5");
#else
    log_text("START GAME IMAGE PROBE V4");
#endif
    init_vx();
    init_bmp();
    g_failures = 0;
    if (!write_resource(k_vx_path, g_vx, sizeof(g_vx))) {
        log_text("VX FILE WRITE FAIL");
        ++g_failures;
    } else {
        log_text("VX FILE WRITE PASS");
    }
    if (!write_resource(k_bmp_path, g_bmp, sizeof(g_bmp))) {
        log_text("BMP FILE WRITE FAIL");
        ++g_failures;
    } else {
        log_text("BMP FILE WRITE PASS");
    }

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_exit = 0;
    g_need_draw = 1;
    g_vx_decode_ok = 0;
    g_bmp_decode_ok = 0;
    g_render_done = 0;
#ifdef GAME_IMAGE_COMPAT_V6
    g_compat = 0;
    g_compat_copy_logged = 0;
#endif

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

    decode_resources();
#ifdef GAME_IMAGE_COMPAT_V6
    log_text("BEFORE COMPAT CREATE");
    g_compat = bda_gui_compat_context_create_like(g_draw);
    log_value("COMPAT=", (u32)g_compat);
    if (!g_compat || (s32)g_compat == -1) {
        ++g_failures;
    } else {
        log_text("BEFORE COMPAT DRAW VX");
        log_value(
            "COMPAT DRAW VX RETURN=",
            (u32)bda_gui_draw_vx_like(g_compat, 0, 0, g_vx)
        );
    }
#endif
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
    (void)bda_fs_remove_raw(k_vx_path);
    (void)bda_fs_remove_raw(k_bmp_path);
    log_value("FAILURES=", (u32)g_failures);
    log_text(g_failures ? "RESULT=FAIL" : "RESULT=PASS");
#ifdef GAME_IMAGE_COMPAT_V6
    log_text("END GAME IMAGE PROBE V6");
#elif defined(GAME_IMAGE_RENDER_V5)
    log_text("END GAME IMAGE PROBE V5");
#else
    log_text("END GAME IMAGE PROBE V4");
#endif
    return g_failures ? 3 : 0;
}
