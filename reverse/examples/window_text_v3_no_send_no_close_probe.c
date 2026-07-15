#include "bda_sdk.h"


static bda_handle_t g_window;

static void draw_text_v3_nc(bda_handle_t window) {
    bda_handle_t draw = bda_gui_begin_draw_like(window);
    if (!draw) {
        return;
    }
    bda_gui_pump_present_arg_like(1);
    bda_gui_set_text_mode_like(draw, 1);
    int color = bda_gui_rgb_like(draw, 255, 255, 255);
    bda_gui_set_text_color_like(draw, (u32)color);
    bda_gui_draw_text_like(draw, 18, 24, "V3 NO SEND", -1);
    bda_gui_draw_text_like(draw, 18, 48, "NO CLOSE", -1);
    bda_gui_pump_present_arg_like(0);
    bda_gui_end_draw_like(draw);
}

static int probe_window_proc(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    int ret = bda_gui_default_proc_like(handle, message, wparam, lparam);
    if (message == 1 || message == 2 || message == 0x10 || message == 0x60) {
        draw_text_v3_nc(handle);
    }
    return ret;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t desc;
    bda_gui_message_like_t msg;

    bda_memset(&desc, 0, sizeof(desc));
    bda_memset(&msg, 0, sizeof(msg));

    desc.style = 0x08000000u;
    desc.title = "WinV3NC";
    desc.wndproc = probe_window_proc;
    desc.height = 240;
    desc.width = 320;
    desc.surface = (u32)bda_gui_draw_object_create_like(15);

    g_window = (bda_handle_t)bda_gui_register_frame_like(&desc);
    if ((s32)g_window == -1 || !g_window) {
        bda_msgbox("WinV3NC", "register failed");
        return 1;
    }

    bda_gui_frame_activate_like(g_window, 0x100);
    draw_text_v3_nc(g_window);

    while (bda_gui_event_poll_like(&msg, g_window)) {
        bda_gui_event_step_like(&msg);
        bda_gui_event_dispatch_like(&msg);
    }

    return 0;
}
