#include "bda_controls.h"

#define CUSTOM_WIDTH  170
#define CUSTOM_HEIGHT 100

static const char k_class_name[] = "SDK_CUSTOM";
static bda_handle_t g_frame;
static bda_handle_t g_control;
static volatile int g_detached;
static volatile int g_escape_requested;
static volatile int g_dirty;
static volatile int g_pressed;

static int custom_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_TOUCH_COORDINATE) {
        g_pressed = !g_pressed;
        g_dirty = 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

static int frame_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        g_detached = 1;
    } else if (message == 0x11u && wparam == 0x1bu) {
        g_escape_requested = 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

static void draw_pixel(
    bda_handle_t draw,
    s32 x,
    s32 y,
    u32 red,
    u32 green,
    u32 blue
) {
    (void)bda_gui_put_pixel_rgb(draw, x, y, red, green, blue);
}

static void paint_control(void) {
    bda_handle_t draw;
    s32 index;
    u32 red = g_pressed ? 220u : 24u;
    u32 green = g_pressed ? 42u : 132u;
    u32 blue = g_pressed ? 42u : 220u;

    if (!bda_control_is_valid(g_control)) {
        return;
    }
    draw = bda_gui_object_draw_begin(g_control);
    if (!bda_control_is_valid(draw)) {
        return;
    }

    (void)bda_gui_draw_guard_begin();
    for (index = 0; index < CUSTOM_WIDTH; ++index) {
        draw_pixel(draw, index, 0, red, green, blue);
        draw_pixel(draw, index, CUSTOM_HEIGHT - 1, red, green, blue);
    }
    for (index = 0; index < CUSTOM_HEIGHT; ++index) {
        draw_pixel(draw, 0, index, red, green, blue);
        draw_pixel(draw, CUSTOM_WIDTH - 1, index, red, green, blue);
        draw_pixel(draw, index + 30, index, red, green, blue);
        draw_pixel(draw, CUSTOM_WIDTH - 31 - index, index, red, green, blue);
    }
    (void)bda_gui_draw_guard_end();
    bda_gui_object_draw_end(g_control, draw);
}

static void wait_escape_release(void) {
    bda_gui_input_packet_t packet;

    do {
        (void)bda_gui_input_packet(&packet);
        bda_sys_delay(1);
    } while (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ESCAPE));
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_control_class_desc_t class_descriptor;
    bda_control_desc_t control_descriptor;
    bda_frame_desc_t frame_descriptor;
    bda_gui_message_t message;
    u32 close_wait = 0;
    int close_requested = 0;

    bda_memset(&class_descriptor, 0, sizeof(class_descriptor));
    bda_memset(&control_descriptor, 0, sizeof(control_descriptor));
    bda_memset(&frame_descriptor, 0, sizeof(frame_descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_control = 0;
    g_detached = 0;
    g_escape_requested = 0;
    g_dirty = 0;
    g_pressed = 0;

    class_descriptor.class_name = k_class_name;
    class_descriptor.draw_object = bda_gui_draw_object_create(15);
    class_descriptor.wndproc = custom_window_proc;
    if (!bda_control_class_register(&class_descriptor)) {
        return 1;
    }

    frame_descriptor.title = "CUSTOM CONTROL";
    frame_descriptor.wndproc = frame_window_proc;
    frame_descriptor.height = 240;
    frame_descriptor.width = 320;
    g_frame = bda_gui_register_frame_desc(&frame_descriptor);
    if (!bda_control_is_valid(g_frame)) {
        (void)bda_control_class_unregister(k_class_name);
        return 2;
    }
    (void)bda_gui_frame_activate(g_frame, 0x100);

    control_descriptor.class_name = k_class_name;
    control_descriptor.caption = "TOUCH ME";
    control_descriptor.style = BDA_BUTTON_STYLE_DEFAULT;
    control_descriptor.id = 0x301u;
    control_descriptor.x = 35;
    control_descriptor.y = 85;
    control_descriptor.width = CUSTOM_WIDTH;
    control_descriptor.height = CUSTOM_HEIGHT;
    control_descriptor.parent = g_frame;
    g_control = bda_control_create(&control_descriptor);
    if (!bda_control_is_valid(g_control)) {
        (void)bda_gui_frame_stop(g_frame);
        (void)bda_gui_frame_release(g_frame);
        bda_gui_close_frame(g_frame);
        (void)bda_control_class_unregister(k_class_name);
        return 3;
    }
    (void)bda_control_set_active(g_control);
    paint_control();

    for (;;) {
        int pump_result = bda_gui_event_pump_frame_once(&message, g_frame);

        if (g_dirty) {
            g_dirty = 0;
            paint_control();
        }
        bda_sys_delay(1);
        if (close_requested) {
            ++close_wait;
            if (!pump_result || g_detached || close_wait >= 128u) {
                break;
            }
            continue;
        }
        if (g_escape_requested) {
            wait_escape_release();
            (void)bda_control_destroy(g_control);
            g_control = 0;
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
            close_requested = 1;
        }
    }

    bda_gui_close_frame(g_frame);
    g_frame = 0;
    (void)bda_control_class_unregister(k_class_name);
    return 0;
}
