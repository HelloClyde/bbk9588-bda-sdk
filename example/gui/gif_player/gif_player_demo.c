#include "bda_controls.h"

#define GIF_CONTROL_ID 0x241u

static const u8 k_animation[] = {
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x20, 0x00,
    0x20, 0x00, 0x81, 0x00, 0x00, 0xdc, 0x1e, 0x28,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x21, 0xff, 0x0b, 0x4e, 0x45, 0x54, 0x53,
    0x43, 0x41, 0x50, 0x45, 0x32, 0x2e, 0x30, 0x03,
    0x01, 0x00, 0x00, 0x00, 0x21, 0xf9, 0x04, 0x08,
    0x64, 0x00, 0x00, 0x00, 0x2c, 0x00, 0x00, 0x00,
    0x00, 0x20, 0x00, 0x20, 0x00, 0x00, 0x08, 0x35,
    0x00, 0x01, 0x08, 0x1c, 0x48, 0xb0, 0xa0, 0xc1,
    0x83, 0x08, 0x13, 0x2a, 0x5c, 0xc8, 0xb0, 0xa1,
    0xc3, 0x87, 0x10, 0x23, 0x4a, 0x9c, 0x48, 0xb1,
    0xa2, 0xc5, 0x8b, 0x18, 0x33, 0x6a, 0xdc, 0xc8,
    0xb1, 0xa3, 0xc7, 0x8f, 0x20, 0x43, 0x8a, 0x1c,
    0x49, 0xb2, 0xa4, 0xc9, 0x93, 0x28, 0x53, 0xaa,
    0x5c, 0xc9, 0x52, 0x64, 0x40, 0x00, 0x21, 0xf9,
    0x04, 0x08, 0x64, 0x00, 0x00, 0x00, 0x2c, 0x00,
    0x00, 0x00, 0x00, 0x20, 0x00, 0x20, 0x00, 0x81,
    0x1e, 0xaa, 0x46, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x08, 0x35, 0x00, 0x01,
    0x08, 0x1c, 0x48, 0xb0, 0xa0, 0xc1, 0x83, 0x08,
    0x13, 0x2a, 0x5c, 0xc8, 0xb0, 0xa1, 0xc3, 0x87,
    0x10, 0x23, 0x4a, 0x9c, 0x48, 0xb1, 0xa2, 0xc5,
    0x8b, 0x18, 0x33, 0x6a, 0xdc, 0xc8, 0xb1, 0xa3,
    0xc7, 0x8f, 0x20, 0x43, 0x8a, 0x1c, 0x49, 0xb2,
    0xa4, 0xc9, 0x93, 0x28, 0x53, 0xaa, 0x5c, 0xc9,
    0x52, 0x64, 0x40, 0x00, 0x3b,
};

static const bda_gifctrl_resource_t k_resource = {
    k_animation,
    0,
    GIF_CONTROL_ID,
};

static bda_handle_t g_frame;
static bda_handle_t g_gif;
static volatile int g_detached;
static volatile int g_escape_requested;

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

static void wait_escape_release(void) {
    bda_gui_input_packet_t packet;

    do {
        (void)bda_gui_input_packet(&packet);
        bda_sys_delay(1);
    } while (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ESCAPE));
}

static bda_handle_t create_gif_control(void) {
    bda_control_desc_t descriptor;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    descriptor.class_name = BDA_CONTROL_CLASS_GIFCTRL;
    descriptor.style = BDA_GIFCTRL_STYLE_ANIMATED;
    descriptor.id = GIF_CONTROL_ID;
    descriptor.x = 104;
    descriptor.y = 88;
    descriptor.width = 32;
    descriptor.height = 32;
    descriptor.parent = g_frame;
    descriptor.extra = (u32)&k_resource;
    return bda_control_create(&descriptor);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    u32 close_wait = 0;
    int close_requested = 0;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_gif = 0;
    g_detached = 0;
    g_escape_requested = 0;

    descriptor.title = "GIF PLAYER";
    descriptor.wndproc = frame_window_proc;
    descriptor.height = 240;
    descriptor.width = 320;
    g_frame = bda_gui_register_frame_desc(&descriptor);
    if (!bda_control_is_valid(g_frame)) {
        return 1;
    }
    (void)bda_gui_frame_activate(g_frame, 0x100);
    g_gif = create_gif_control();
    if (!bda_control_is_valid(g_gif)) {
        (void)bda_gui_frame_stop(g_frame);
        (void)bda_gui_frame_release(g_frame);
        bda_gui_close_frame(g_frame);
        return 2;
    }

    for (;;) {
        int pump_result = bda_gui_event_pump_frame_once(&message, g_frame);

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
            (void)bda_control_destroy(g_gif);
            g_gif = 0;
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
            close_requested = 1;
        }
    }

    bda_gui_close_frame(g_frame);
    g_frame = 0;
    return 0;
}
