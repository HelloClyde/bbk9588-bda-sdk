#include "../bda_research_sdk.h"


static bda_handle_t g_frame;
static bda_handle_t g_draw;
static int g_painted;

static void bbvm_style_draw(void) {
    if (!g_draw) {
        return;
    }
    bda_gui_pump_present_arg_like(1);
    bda_gui_set_text_mode_like(g_draw, 0);
    int color = bda_gui_rgb_like(g_draw, 255, 255, 255);
    bda_gui_set_text_color_like(g_draw, (u32)color);
    bda_gui_draw_text_like(g_draw, 18, 24, "BBVM STYLE TEXT", -1);
    bda_gui_draw_text_like(g_draw, 18, 48, "draw handle 0x304", -1);
    if (g_frame) {
        bda_gui_object_op_like(g_frame);
    }
    bda_gui_pump_present_arg_like(0);
}

static int probe_window_proc(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE) {
        g_frame = handle;
        g_draw = bda_gui_current_draw_like(handle);
        if (!g_painted) {
            g_painted = 1;
            bbvm_style_draw();
        }
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH_LIKE) {
        if (g_draw) {
            bda_gui_end_draw_like(g_draw);
        }
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
    desc.title = "BBVMTxt";
    desc.wndproc = probe_window_proc;
    desc.height = 240;
    desc.width = 320;
    desc.surface = (u32)bda_gui_draw_object_create_like(15);

    g_frame = (bda_handle_t)bda_gui_register_frame_like(&desc);
    if ((s32)g_frame == -1 || !g_frame) {
        bda_msgbox("BBVMTxt", "register failed");
        return 1;
    }

    bda_gui_frame_activate_like(g_frame, 0x100);

    while (bda_gui_event_poll_like(&msg, g_frame)) {
        bda_gui_event_step_like(&msg);
        bda_gui_event_dispatch_like(&msg);
    }

    bda_gui_close_frame_like(g_frame);
    return 0;
}
