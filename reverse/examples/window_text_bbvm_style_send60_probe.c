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

static void bbvm_style_draw(void) {
    if (!g_draw) {
        return;
    }
    bda_gui_pump_present_arg_like(1);
    bda_gui_set_text_mode_like(g_draw, 0);
    int color = bda_gui_rgb_like(g_draw, 255, 255, 255);
    bda_gui_set_text_color_like(g_draw, (u32)color);
    bda_gui_draw_text_like(g_draw, 18, 24, "BBVM SEND60", -1);
    bda_gui_draw_text_like(g_draw, 18, 48, "0x304 handle", -1);
    bda_gui_object_op_like((u32)g_frame, 0, 0);
    bda_gui_pump_present_arg_like(0);
}

static int probe_window_proc(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    if (message == 0x60) {
        g_frame = handle;
        g_draw = bda_gui_current_draw_like();
        bbvm_style_draw();
    } else if (message == 0x66) {
        if (g_draw) {
            bda_gui_end_draw_like(g_draw);
        }
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t desc;
    u32 msg[14];

    bda_memset(&desc, 0, sizeof(desc));
    bda_memset(msg, 0, sizeof(msg));

    desc.style = 0x08000000u;
    desc.title = "Send60";
    desc.proc = probe_window_proc;
    desc.height = 240;
    desc.width = 320;
    desc.surface = bda_gui_frame_surface_like(15);

    g_frame = (bda_handle_t)bda_gui_register_frame_like(&desc);
    if ((s32)g_frame == -1 || !g_frame) {
        bda_msgbox("Send60", "register failed");
        return 1;
    }

    bda_gui_frame_activate_like(g_frame, 0x100);
    bda_gui_send(g_frame, 0x60, 0, 0);

    while (bda_gui_event_poll_like(msg, g_frame)) {
        bda_gui_event_step_like();
        bda_gui_event_dispatch_like(msg);
    }

    bda_gui_close_frame_like(g_frame);
    return 0;
}
