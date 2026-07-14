#include "bda_sdk.h"


static bda_handle_t g_window;
static int g_draw_count;

static void draw_probe_text(bda_handle_t window) {
    bda_handle_t draw = bda_gui_begin_draw_like(window);
    if (!draw) {
        return;
    }

    bda_gui_pump_present_arg_like(1);
    bda_gui_set_text_mode_like(draw, 1);
    int white = bda_gui_rgb_like(draw, 255, 255, 255);
    bda_gui_set_text_color_like(draw, (u32)white);
    bda_gui_draw_text_like(draw, 24, 24, "WINDOW TEXT OK", -1);
    bda_gui_draw_text_like(draw, 24, 48, "native callback", -1);
    bda_gui_pump_present_arg_like(0);
    bda_gui_end_draw_like(draw);
}

static int probe_window_proc(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    if (message == 1 || message == 2 || message == 0x10 || message == 0x60 || message == 0x66) {
        ++g_draw_count;
        draw_probe_text(handle);
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t desc;
    bda_gui_message_like_t msg;

    bda_memset(&desc, 0, sizeof(desc));
    bda_memset(&msg, 0, sizeof(msg));

    desc.style = 0x08000000u;
    desc.title = "WinText";
    desc.wndproc = probe_window_proc;
    desc.height = 240;
    desc.width = 320;
    desc.surface = (u32)bda_gui_frame_surface_like(15);

    g_window = (bda_handle_t)bda_gui_register_frame_like(&desc);
    if ((s32)g_window == -1 || !g_window) {
        bda_msgbox("WinText", "register failed");
        return 1;
    }

    bda_gui_send(g_window, 0x66, 0, 0);
    draw_probe_text(g_window);

    while (bda_gui_event_poll_like(&msg, g_window)) {
        bda_gui_event_step_like(&msg);
        bda_gui_event_dispatch_like(&msg);
    }

    bda_gui_close_frame_like(g_window);
    return 0;
}
