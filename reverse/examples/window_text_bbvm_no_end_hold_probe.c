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

static bda_handle_t g_frame;
static bda_handle_t g_draw;

static void draw_hold_text(void) {
    if (!g_draw) {
        return;
    }
    bda_gui_pump_present_arg_like(1);
    bda_gui_set_text_mode_like(g_draw, 0);
    int black = bda_gui_rgb_like(g_draw, 0, 0, 0);
    bda_gui_set_text_color_like(g_draw, (u32)black);
    bda_gui_draw_text_like(g_draw, 18, 24, "BBVM NO END HOLD", -1);
    bda_gui_draw_text_like(g_draw, 18, 48, "no cleanup path", -1);
    bda_gui_object_op_like((u32)g_frame, 0, 0);
    bda_gui_pump_present_arg_like(0);
}

static int probe_window_proc(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    if (message == 0x60) {
        g_frame = handle;
        g_draw = bda_gui_current_draw_like();
        draw_hold_text();
    }
    if (message == 0x66) {
        return 1;
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t desc;
    u32 msg[14];
    int i;

    bda_memset(&desc, 0, sizeof(desc));
    bda_memset(msg, 0, sizeof(msg));

    desc.style = 0x08000000u;
    desc.title = "NoEnd";
    desc.proc = probe_window_proc;
    desc.height = 240;
    desc.width = 320;
    desc.surface = bda_gui_frame_surface_like(15);

    g_frame = (bda_handle_t)bda_gui_register_frame_like(&desc);
    if ((s32)g_frame == -1 || !g_frame) {
        bda_msgbox("NoEnd", "register failed");
        return 1;
    }

    bda_gui_frame_activate_like(g_frame, 0x100);

    for (i = 0; i < 300; ++i) {
        if (bda_gui_event_poll_like(msg, g_frame)) {
            bda_gui_event_step_like();
            bda_gui_event_dispatch_like(msg);
        }
        draw_hold_text();
        bda_sys_delay_like(10000);
    }

    return 0;
}
