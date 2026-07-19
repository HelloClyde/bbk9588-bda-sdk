#include "bda_controls.h"
#include "bda_input.h"
#include "bda_memory.h"
#include "bda_time.h"
#include "bda_window.h"

#define CONTROL_COUNT 8u

typedef struct control_spec {
    const char *class_name;
    const char *caption;
    u32 style;
    u32 id;
    s32 x;
    s32 y;
    s32 width;
    s32 height;
} control_spec_t;

static const control_spec_t k_specs[CONTROL_COUNT] = {
    {BDA_CONTROL_CLASS_STATIC, "STATIC", BDA_STATIC_STYLE_DEFAULT,
     0x201u, 8, 12, 108, 22},
    {BDA_CONTROL_CLASS_BUTTON, "BUTTON", BDA_BUTTON_STYLE_DEFAULT,
     0x202u, 124, 12, 108, 22},
    {BDA_CONTROL_CLASS_EDIT, "EDIT", BDA_EDIT_STYLE_DEFAULT,
     0x203u, 8, 40, 224, 24},
    {BDA_CONTROL_CLASS_MEDIT, "MEDIT", BDA_MEDIT_STYLE_DEFAULT,
     0x204u, 8, 70, 224, 38},
    {BDA_CONTROL_CLASS_LISTBOX, "LIST", BDA_LISTBOX_STYLE_DEFAULT,
     0x205u, 8, 114, 108, 72},
    {BDA_CONTROL_CLASS_COMBOBOX, "COMBO", BDA_COMBOBOX_STYLE_DEFAULT,
     0x206u, 124, 114, 108, 28},
    {BDA_CONTROL_CLASS_PROGRESSBAR, "PROGRESS",
     BDA_PROGRESSBAR_STYLE_DEFAULT, 0x207u, 124, 148, 108, 18},
    {BDA_CONTROL_CLASS_TOOLBAR, "TOOLBAR", BDA_TOOLBAR_STYLE_DEFAULT,
     0x208u, 8, 194, 224, 24},
};

static bda_handle_t g_frame;
static bda_handle_t g_controls[CONTROL_COUNT];
static volatile int g_detached;
static volatile int g_escape_requested;

static int gallery_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        g_detached = 1;
    } else if (message == 0x11u && wparam == 0x1bu) {
        g_escape_requested = 1;
    } else if (message == BDA_CONTROL_MSG_COMMAND) {
        u32 id = bda_control_command_id(wparam);
        u32 code = bda_control_command_code(wparam);
        (void)id;
        (void)code;
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

static void create_controls(void) {
    u32 index;

    for (index = 0; index < CONTROL_COUNT; ++index) {
        bda_control_desc_t descriptor;

        bda_memset(&descriptor, 0, sizeof(descriptor));
        descriptor.class_name = k_specs[index].class_name;
        descriptor.caption = k_specs[index].caption;
        descriptor.style = k_specs[index].style;
        descriptor.id = k_specs[index].id;
        descriptor.x = k_specs[index].x;
        descriptor.y = k_specs[index].y;
        descriptor.width = k_specs[index].width;
        descriptor.height = k_specs[index].height;
        descriptor.parent = g_frame;
        g_controls[index] = bda_control_create(&descriptor);
    }

    if (bda_control_is_valid(g_controls[2])) {
        (void)bda_text_control_set_max_length(g_controls[2], 31);
        (void)bda_text_control_set_text(g_controls[2], "EDIT READY");
    }
    if (bda_control_is_valid(g_controls[3])) {
        (void)bda_text_control_set_max_length(g_controls[3], 31);
        (void)bda_text_control_set_text(g_controls[3], "MEDIT READY");
    }
    if (bda_control_is_valid(g_controls[4])) {
        (void)bda_listbox_append_item(g_controls[4], "ALPHA");
        (void)bda_listbox_append_item(g_controls[4], "BETA");
        (void)bda_listbox_append_item(g_controls[4], "GAMMA");
        (void)bda_listbox_set_selection(g_controls[4], 1);
    }
    if (bda_control_is_valid(g_controls[5])) {
        (void)bda_combobox_append_item(g_controls[5], "RED");
        (void)bda_combobox_append_item(g_controls[5], "GREEN");
        (void)bda_combobox_set_selection(g_controls[5], 1);
    }
    if (bda_control_is_valid(g_controls[6])) {
        (void)bda_progressbar_set_range(g_controls[6], 0, 100);
        (void)bda_progressbar_set_position(g_controls[6], 65);
    }
    if (bda_control_is_valid(g_controls[1])) {
        (void)bda_control_set_active(g_controls[1]);
    }
}

static void destroy_controls(void) {
    u32 index = CONTROL_COUNT;

    while (index) {
        --index;
        if (bda_control_is_valid(g_controls[index])) {
            (void)bda_control_destroy(g_controls[index]);
        }
        g_controls[index] = 0;
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    u32 close_wait = 0;
    int close_requested = 0;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    bda_memset(g_controls, 0, sizeof(g_controls));
    g_detached = 0;
    g_escape_requested = 0;

    descriptor.title = "CONTROL GALLERY";
    descriptor.wndproc = gallery_window_proc;
    descriptor.height = 240;
    descriptor.width = 320;
    g_frame = bda_gui_register_frame_desc(&descriptor);
    if (!bda_control_is_valid(g_frame)) {
        return 1;
    }
    (void)bda_gui_frame_activate(g_frame, 0x100);
    create_controls();

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
            destroy_controls();
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
            close_requested = 1;
        }
    }

    bda_gui_close_frame(g_frame);
    g_frame = 0;
    return 0;
}
