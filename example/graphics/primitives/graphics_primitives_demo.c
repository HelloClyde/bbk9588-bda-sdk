#include "bda_dialogs.h"
#include "bda_graphics.h"
#include "bda_input.h"
#include "bda_memory.h"
#include "bda_time.h"
#include "bda_window.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static bda_handle_t g_draw_owner;
static void *g_draw_object;
static int g_dirty;
static int g_exit;

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

static u32 color(u32 red, u32 green, u32 blue) {
    return (u32)bda_gui_rgb(g_draw, red, green, blue);
}

static void fill_pixels_converted(
    s32 left,
    s32 top,
    s32 width,
    s32 height,
    u32 value
) {
    int x;
    int y;
    for (y = 0; y < height; ++y) {
        for (x = 0; x < width; ++x) {
            (void)bda_gui_put_pixel(g_draw, left + x, top + y, value);
        }
    }
}

static void fill_pixels_rgb(
    s32 left,
    s32 top,
    s32 width,
    s32 height,
    u32 red,
    u32 green,
    u32 blue
) {
    int x;
    int y;
    for (y = 0; y < height; ++y) {
        for (x = 0; x < width; ++x) {
            (void)bda_gui_put_pixel_rgb(
                g_draw, left + x, top + y, red, green, blue
            );
        }
    }
}

static void draw_pixel_swatch(s32 left, s32 top) {
    int x;
    int y;
    u32 light = color(245, 248, 250);
    u32 accent = color(250, 190, 35);

    for (y = 0; y < 12; ++y) {
        for (x = 0; x < 20; ++x) {
            int alternate = ((x / 4) + (y / 4)) & 1;
            if (x < 10) {
                u32 value = alternate ? accent : light;
                (void)bda_gui_put_pixel(g_draw, left + x, top + y, value);
            } else if (alternate) {
                (void)bda_gui_put_pixel_rgb(g_draw, left + x, top + y, 250, 190, 35);
            } else {
                (void)bda_gui_put_pixel_rgb(g_draw, left + x, top + y, 245, 248, 250);
            }
        }
    }
}

static void draw_scene(void) {
    void *old_object;
    u32 panel_a;
    u32 foreground;
    u32 muted;

    if (!g_draw || !g_dirty) {
        return;
    }
    g_dirty = 0;
    panel_a = color(20, 145, 170);
    foreground = color(245, 248, 250);
    muted = color(165, 180, 190);

    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);

    fill_pixels_converted(16, 48, 88, 48, panel_a);
    fill_pixels_rgb(136, 48, 88, 48, 235, 165, 35);

    bda_gui_rectangle(g_draw, 12, 42, 108, 104);
    bda_gui_rectangle(g_draw, 132, 42, 228, 104);
    bda_gui_move_to(g_draw, 18, 135);
    bda_gui_line_to(g_draw, 222, 135);
    bda_gui_circle(g_draw, 60, 185, 34);
    bda_gui_rectangle(g_draw, 126, 151, 218, 219);
    draw_pixel_swatch(110, 240);

    (void)bda_gui_set_text_mode(g_draw, 1);
    (void)bda_gui_set_text_color(g_draw, foreground);
    (void)bda_gui_draw_text(g_draw, 40, 10, "GRAPHICS API", -1);
    (void)bda_gui_draw_text(g_draw, 25, 66, "RECT", -1);
    (void)bda_gui_draw_text(g_draw, 152, 66, "FILL", -1);
    (void)bda_gui_set_text_color(g_draw, muted);
    (void)bda_gui_draw_text(g_draw, 75, 278, "ESC EXIT", -1);

    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
}

static int graphics_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        g_frame = handle;
        (void)acquire_draw_context(handle);
        if (!g_draw_object) {
            g_draw_object = bda_gui_draw_object_create(7);
        }
        g_dirty = 1;
        draw_scene();
    } else if (message == BDA_MSG_REDRAW_INPUT) {
        g_dirty = 1;
        draw_scene();
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        if (!g_draw_owner || g_draw_owner == handle) {
            release_draw_context();
        }
        g_exit = 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

static void wait_key_release(u32 keycode) {
    bda_gui_input_packet_t packet;
    do {
        (void)bda_gui_input_packet(&packet);
        bda_sys_delay(1);
    } while (bda_gui_input_packet_key_pressed(&packet, keycode));
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    int close_requested = 0;
    u32 close_wait = 0;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_draw_owner = 0;
    g_draw_object = 0;
    g_dirty = 1;
    g_exit = 0;

    descriptor.style = 0x08000000u;
    descriptor.title = 0;
    descriptor.wndproc = graphics_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = (u32)bda_gui_draw_object_create(15);

    g_frame = bda_gui_register_frame_desc(&descriptor);
    if (!g_frame || (s32)g_frame == -1) {
        bda_msgbox("Graphics", "frame registration failed");
        return 1;
    }
    (void)bda_gui_frame_activate(g_frame, 0x100);
    (void)acquire_draw_context(g_frame);
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create(7);
    }
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        bda_msgbox("Graphics", "draw context failed");
        (void)bda_gui_frame_stop(g_frame);
        (void)bda_gui_frame_release(g_frame);
        release_draw_context();
        bda_gui_close_frame(g_frame);
        return 2;
    }
    draw_scene();

    while (!g_exit) {
        bda_gui_input_packet_t packet;
        int pump_result = bda_gui_event_pump_frame_once(&message, g_frame);
        (void)bda_gui_input_packet(&packet);
        if (!close_requested &&
            bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ESCAPE)) {
            wait_key_release(BDA_KEY_ESCAPE);
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
            close_requested = 1;
        }
        if (close_requested) {
            ++close_wait;
            if (!pump_result || !g_draw || close_wait >= 128u) {
                break;
            }
        }
        bda_sys_delay(1);
    }

    release_draw_context();
    if (g_frame) {
        if (!close_requested) {
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
        }
        bda_gui_close_frame(g_frame);
        g_frame = 0;
    }
    return 0;
}
