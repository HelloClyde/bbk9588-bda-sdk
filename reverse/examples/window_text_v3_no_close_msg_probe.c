#include "../sdk/bda_sdk.h"

typedef struct bda_frame_desc_like {
    u32 style;
    u32 reserved04;
    const char *title;
    u32 reserved0c;
    u32 reserved10;
    u32 reserved14;
    int (*proc)(bda_handle_t, u32, u32, u32);
    u32 reserved1c;
    u32 reserved20;
    u32 height;
    u32 width;
    void *surface;
    u32 reserved30;
} bda_frame_desc_like_t;

static bda_handle_t g_window;
static int g_painted;

static void draw_text_v3(bda_handle_t window) {
    bda_handle_t draw = bda_gui_begin_draw_like(window);
    if (!draw) {
        return;
    }
    bda_gui_pump_present_arg_like(1);
    bda_gui_set_text_mode_like(draw, 1);
    int color = bda_gui_rgb_like(draw, 255, 255, 255);
    bda_gui_set_text_color_like(draw, (u32)color);
    bda_gui_draw_text_like(draw, 18, 24, "V3 NO CLOSE MSG", -1);
    bda_gui_draw_text_like(draw, 18, 48, "no send 0x66", -1);
    bda_gui_pump_present_arg_like(0);
    bda_gui_end_draw_like(draw);
}

static int probe_window_proc(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    int ret = bda_gui_default_proc_like(handle, message, wparam, lparam);
    if (!g_painted && (message == 1 || message == 2 || message == 0x10 || message == 0x60)) {
        g_painted = 1;
        draw_text_v3(handle);
    }
    return ret;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t desc;
    u32 msg[14];

    bda_memset(&desc, 0, sizeof(desc));
    bda_memset(msg, 0, sizeof(msg));

    desc.style = 0x08000000u;
    desc.title = "WinV3";
    desc.proc = probe_window_proc;
    desc.height = 240;
    desc.width = 320;
    desc.surface = bda_gui_frame_surface_like(15);

    g_window = (bda_handle_t)bda_gui_register_frame_like(&desc);
    if ((s32)g_window == -1 || !g_window) {
        bda_msgbox("WinV3", "register failed");
        return 1;
    }

    bda_gui_frame_activate_like(g_window, 0x100);
    draw_text_v3(g_window);

    while (bda_gui_event_poll_like(msg, g_window)) {
        bda_gui_event_step_like();
        bda_gui_event_dispatch_like(msg);
    }

    bda_gui_close_frame_like(g_window);
    return 0;
}
