#include "../bda_research_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define STAGE_WIDTH 208
#define STAGE_HEIGHT 64
#define SPRITE_WIDTH 32
#define SPRITE_HEIGHT 32
#define STAGE_HEADER_SIZE 24
#define STAGE_BYTES (STAGE_HEADER_SIZE + STAGE_WIDTH * STAGE_HEIGHT * 2)
#define SPRITE_BYTES (STAGE_HEADER_SIZE + SPRITE_WIDTH * SPRITE_HEIGHT * 2)
#define MINIMUM_ANIMATION_FRAMES 240

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEG19.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEG19.TXT";
static const char k_window_title[] = "GFXV19";

static const char *g_log_path;
static char g_line[128];
static u8 g_stage[STAGE_BYTES];
static u8 g_sprite_vx[SPRITE_BYTES];
static bda_handle_t g_frame;
static bda_handle_t g_draw;
static bda_handle_t g_compat;
static bda_handle_t g_sprite_context;
static void *g_draw_object;
static u32 g_animation_frame;
static int g_animation_complete;
static int g_failures;
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

static void init_vx_header(u8 *image, u32 width, u32 height, u32 image_bytes) {
    int index;

    bda_memset(image, 0, image_bytes);
    image[0] = 'V';
    image[1] = 'X';
    for (index = 2; index < 6; ++index) {
        image[index] = 0xcc;
    }
    write_u32_le(image + 6, width);
    write_u32_le(image + 10, height);
    for (index = 14; index < 20; ++index) {
        image[index] = 0xcc;
    }
    for (index = 20; index < STAGE_HEADER_SIZE; ++index) {
        image[index] = 0xff;
    }
}

static void build_stage(void) {
    int x;
    int y;
    u16 background = rgb565(10, 22, 36);
    u16 grid = rgb565(22, 58, 76);

    for (y = 0; y < STAGE_HEIGHT; ++y) {
        for (x = 0; x < STAGE_WIDTH; ++x) {
            u16 color = background;
            u32 offset = STAGE_HEADER_SIZE + (u32)(y * STAGE_WIDTH + x) * 2u;

            if ((x % 16) == 0 || (y % 16) == 0) {
                color = grid;
            }
            write_u16_le(g_stage + offset, color);
        }
    }
}

static void build_sprite(u32 frame) {
    int x;
    int y;
    u16 background = rgb565(7, 12, 18);
    u16 accent = ((frame / 60u) & 1u)
        ? rgb565(250, 190, 35)
        : rgb565(25, 210, 200);

    for (y = 0; y < SPRITE_HEIGHT; ++y) {
        for (x = 0; x < SPRITE_WIDTH; ++x) {
            u16 color = background;
            u32 offset = STAGE_HEADER_SIZE +
                (u32)(y * SPRITE_WIDTH + x) * 2u;

            if (x == 0 || x == SPRITE_WIDTH - 1 ||
                y == 0 || y == SPRITE_HEIGHT - 1 ||
                x == y || x + y == SPRITE_WIDTH - 1 ||
                (x >= 12 && x < 20) || (y >= 12 && y < 20)) {
                color = accent;
            }
            write_u16_le(g_sprite_vx + offset, color);
        }
    }
}

static void draw_static_scene(void) {
    bda_handle_t base_draw;
    bda_handle_t object_draw;
    int object_draw_active;
    void *old_object;
    u32 foreground;
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

    foreground = (u32)bda_gui_rgb_like(g_draw, 235, 240, 245);
    cyan = (u32)bda_gui_rgb_like(g_draw, 25, 205, 215);
    old_object = bda_gui_select_draw_object_like(g_draw, g_draw_object);
    (void)bda_gui_set_text_mode_like(g_draw, 1);
    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 18, 8, "DOUBLE BUFFER + SPRITE V19", -1);
    (void)bda_gui_draw_text_like(g_draw, 30, 55, "SPRITE -> BACK -> SCREEN", -1);
    bda_gui_rectangle_like(g_draw, 14, 88, 225, 155);
    (void)bda_gui_set_text_color_like(g_draw, cyan);
    (void)bda_gui_draw_text_like(
        g_draw,
        35,
        205,
        g_animation_complete ? "240 FRAMES COMPLETE" : "2 SURFACES RUNNING",
        -1
    );
    (void)bda_gui_set_text_color_like(g_draw, foreground);
    (void)bda_gui_draw_text_like(g_draw, 80, 300, "ESC EXIT", -1);
    (void)bda_gui_select_draw_object_like(g_draw, old_object);

    if (object_draw_active) {
        bda_gui_object_draw_end_like(g_frame, object_draw);
        g_draw = base_draw;
    }
}

static int draw_animation_frame(void) {
    void *old_object;
    int travel;
    int sprite_x;
    int guard_begin_result;
    int background_draw_result;
    int sprite_draw_result;
    int sprite_copy_result;
    int present_copy_result;
    int guard_end_result;

    if (!g_draw || !g_compat || !g_sprite_context || !g_draw_object) {
        return 0;
    }

    travel = (int)(g_animation_frame % 352u);
    sprite_x = travel <= 176 ? travel : 352 - travel;
    build_stage();
    build_sprite(g_animation_frame);
    background_draw_result = bda_gui_draw_vx_like(g_compat, 0, 0, g_stage);
    sprite_draw_result = bda_gui_draw_vx_like(
        g_sprite_context, 0, 0, g_sprite_vx
    );
    sprite_copy_result = bda_gui_context_copy_like(
        g_sprite_context,
        0,
        0,
        SPRITE_WIDTH,
        SPRITE_HEIGHT,
        g_compat,
        sprite_x,
        16,
        0
    );
    guard_begin_result = bda_gui_draw_guard_begin_like();
    old_object = bda_gui_select_draw_object_like(g_draw, g_draw_object);
    present_copy_result = bda_gui_context_copy_like(
        g_compat,
        0,
        0,
        STAGE_WIDTH,
        STAGE_HEIGHT,
        g_draw,
        16,
        90,
        0
    );
    (void)bda_gui_select_draw_object_like(g_draw, old_object);
    guard_end_result = bda_gui_draw_guard_end_like();

    if (g_animation_frame == 0) {
        log_value("FIRST BACKGROUND DRAW=", (u32)background_draw_result);
        log_value("FIRST SPRITE DRAW=", (u32)sprite_draw_result);
        log_value("FIRST SPRITE COPY=", (u32)sprite_copy_result);
        log_value("FIRST GUARD BEGIN=", (u32)guard_begin_result);
        log_value("FIRST PRESENT COPY=", (u32)present_copy_result);
        log_value("FIRST GUARD END=", (u32)guard_end_result);
    }
    ++g_animation_frame;
    if (!g_animation_complete && (g_animation_frame % 60u) == 0) {
        log_value("FRAME=", g_animation_frame);
    }
    if (!g_animation_complete &&
        g_animation_frame >= MINIMUM_ANIMATION_FRAMES) {
        g_animation_complete = 1;
        log_text("ANIMATION MINIMUM COMPLETE");
    }
    return 1;
}

static int animation_window_proc(
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
    log_text("START DOUBLE BUFFER SPRITE PROBE V19");
    init_vx_header(g_stage, STAGE_WIDTH, STAGE_HEIGHT, sizeof(g_stage));
    init_vx_header(
        g_sprite_vx, SPRITE_WIDTH, SPRITE_HEIGHT, sizeof(g_sprite_vx)
    );
    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_compat = 0;
    g_sprite_context = 0;
    g_draw_object = 0;
    g_animation_frame = 0;
    g_animation_complete = 0;
    g_failures = 0;
    g_exit = 0;
    g_need_draw = 1;

    descriptor.style = 0;
    descriptor.title = k_window_title;
    descriptor.wndproc = animation_window_proc;
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

    log_text("BEFORE BACK CREATE");
    g_compat = bda_gui_compat_context_create_like(g_draw);
    log_value("BACK=", (u32)g_compat);
    if (!g_compat || (s32)g_compat == -1) {
        log_text("RESULT=BACK FAIL");
        return 3;
    }
    log_text("BEFORE SPRITE CREATE");
    g_sprite_context = bda_gui_compat_context_create_like(g_draw);
    log_value("SPRITE=", (u32)g_sprite_context);
    if (!g_sprite_context || (s32)g_sprite_context == -1) {
        log_text("RESULT=SPRITE FAIL");
        bda_gui_surface_flush_like(g_compat);
        g_compat = 0;
        (void)bda_gui_close_frame_like(g_frame);
        g_frame = 0;
        return 4;
    }
    draw_static_scene();
    g_need_draw = 0;
    log_text("LOOP READY");

    for (;;) {
        bda_gui_input_packet_like_t packet;
        int pump_result;

        pump_result = bda_gui_event_pump_frame_once_like(&message, g_frame);
        if (g_need_draw) {
            g_need_draw = 0;
            draw_static_scene();
        }
        if (!draw_animation_frame()) {
            ++g_failures;
            log_text("ANIMATION DRAW FAIL");
            break;
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
    if (g_compat && (s32)g_compat != -1) {
        log_text("BEFORE BACK FREE");
        bda_gui_surface_flush_like(g_compat);
        g_compat = 0;
        log_text("BACK FREED");
    }
    if (g_sprite_context && (s32)g_sprite_context != -1) {
        log_text("BEFORE SPRITE FREE");
        bda_gui_surface_flush_like(g_sprite_context);
        g_sprite_context = 0;
        log_text("SPRITE FREED");
    }
    if (g_animation_frame < MINIMUM_ANIMATION_FRAMES) {
        ++g_failures;
    }
    log_value("FRAMES=", g_animation_frame);
    log_value("FAILURES=", (u32)g_failures);
    log_text(g_failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END DOUBLE BUFFER SPRITE PROBE V19");
    return g_failures ? 5 : 0;
}
