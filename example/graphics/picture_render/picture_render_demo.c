#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define PICTURE_WIDTH 160
#define PICTURE_HEIGHT 96
#define PICTURE_X 40
#define PICTURE_Y 70

static u16 g_pixels[PICTURE_WIDTH * PICTURE_HEIGHT];
static bda_gui_picture_t g_picture;
static bda_handle_t g_frame;
static bda_handle_t g_draw;
static bda_handle_t g_draw_owner;
static void *g_draw_object;
static u32 g_phase;
static u32 g_previous_keys;
static int g_exit;

static u16 rgb565(u32 red, u32 green, u32 blue)
{
    return (u16)(((red & 0xf8u) << 8) | ((green & 0xfcu) << 3) | (blue >> 3));
}

static void fill_picture(void)
{
    int x;
    int y;

    for (y = 0; y < PICTURE_HEIGHT; ++y) {
        for (x = 0; x < PICTURE_WIDTH; ++x) {
            u16 value;
            if (g_phase == 0u) {
                value = x < PICTURE_WIDTH / 2 ?
                    rgb565(32, 190, 215) : rgb565(245, 180, 35);
            } else if (g_phase == 1u) {
                value = (((x / 10) + (y / 10)) & 1) ?
                    rgb565(238, 242, 245) : rgb565(18, 24, 30);
            } else {
                value = y < PICTURE_HEIGHT / 2 ?
                    rgb565(235, 55, 85) : rgb565(55, 215, 105);
            }
            g_pixels[y * PICTURE_WIDTH + x] = value;
        }
    }
}

static void release_draw_context(void)
{
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

static int acquire_draw_context(bda_handle_t owner)
{
    if (g_draw && g_draw_owner == owner)
        return 1;
    release_draw_context();
    g_draw = bda_gui_current_draw(owner);
    if (!g_draw || (s32)g_draw == -1) {
        g_draw = 0;
        return 0;
    }
    g_draw_owner = owner;
    return 1;
}

static void present_picture(void)
{
    void *old_object;

    fill_picture();
    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    (void)bda_gui_render_picture(
        g_draw,
        PICTURE_X,
        PICTURE_Y,
        PICTURE_WIDTH,
        PICTURE_HEIGHT,
        &g_picture
    );
    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
}

static void draw_labels(void)
{
    void *old_object;
    u32 foreground = (u32)bda_gui_rgb(g_draw, 242, 246, 248);

    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    (void)bda_gui_set_text_mode(g_draw, 1u);
    (void)bda_gui_set_text_color(g_draw, foreground);
    (void)bda_gui_draw_text(g_draw, 34, 16, "RAW RGB565 PICTURE", -1);
    (void)bda_gui_draw_text(g_draw, 36, 198, "ENTER: NEXT PHASE", -1);
    (void)bda_gui_draw_text(g_draw, 72, 238, "ESC: EXIT", -1);
    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
}

static u32 key_mask(const bda_gui_input_packet_t *packet)
{
    u32 mask = 0;
    if (bda_gui_input_packet_key_pressed(packet, BDA_KEY_ENTER))
        mask |= 1u;
    if (bda_gui_input_packet_key_pressed(packet, BDA_KEY_ESCAPE))
        mask |= 2u;
    return mask;
}

static int picture_window_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
)
{
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        g_frame = handle;
        (void)acquire_draw_context(handle);
        if (!g_draw_object)
            g_draw_object = bda_gui_draw_object_create(7u);
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        if (!g_draw_owner || g_draw_owner == handle)
            release_draw_context();
        g_exit = 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void)
{
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    bda_gui_input_packet_t packet;
    int close_requested = 0;
    u32 close_wait = 0;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    bda_memset(&g_picture, 0, sizeof(g_picture));
    g_picture.width = PICTURE_WIDTH;
    g_picture.height = PICTURE_HEIGHT;
    g_picture.source_pixels = g_pixels;
    g_picture.selected_index = -1;
    g_phase = 0;
    g_exit = 0;
    g_frame = 0;
    g_draw = 0;
    g_draw_owner = 0;
    g_draw_object = 0;

    descriptor.title = "Picture";
    descriptor.wndproc = picture_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    g_frame = bda_gui_register_frame_desc(&descriptor);
    if (!g_frame || (s32)g_frame == -1)
        return 1;
    (void)bda_gui_frame_activate(g_frame, 0x100u);
    (void)acquire_draw_context(g_frame);
    if (!g_draw_object)
        g_draw_object = bda_gui_draw_object_create(7u);
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        (void)bda_gui_frame_stop(g_frame);
        (void)bda_gui_frame_release(g_frame);
        release_draw_context();
        bda_gui_close_frame(g_frame);
        g_frame = 0;
        return 2;
    }

    draw_labels();
    present_picture();
    (void)bda_gui_input_packet(&packet);
    g_previous_keys = key_mask(&packet);

    while (!g_exit) {
        int pump_result = bda_gui_event_pump_frame_once(&message, g_frame);
        u32 current;
        u32 pressed;
        (void)bda_gui_input_packet(&packet);
        current = key_mask(&packet);
        pressed = current & ~g_previous_keys;
        g_previous_keys = current;
        if (!close_requested && (pressed & 1u)) {
            g_phase = (g_phase + 1u) % 3u;
            present_picture();
        }
        if (!close_requested && (pressed & 2u)) {
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
            close_requested = 1;
        }
        if (close_requested &&
            (!pump_result || !g_draw || ++close_wait >= 128u))
            break;
        bda_sys_delay(1u);
    }

    release_draw_context();
    if (g_frame) {
        if (!close_requested) {
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
        }
        bda_gui_close_frame(g_frame);
    }
    return 0;
}
