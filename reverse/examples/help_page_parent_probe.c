#include "bda_research_sdk.h"

static const char g_help_document[] =
    "Parent help probe\r\n"
    "This help page has a registered frame parent.\n"
    "Press ESC to return to the parent call site.\n";

static int window_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
) {
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

static void write_log(const char *mode, const char *text) {
    bda_size_t length = 0u;
    int file;

    while (text[length] != '\0') {
        ++length;
    }
    file = bda_fs_fopen_raw("A:\\HELP_PARENT.LOG", mode);
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, text, length);
    (void)bda_fs_close_raw(file);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t descriptor;
    bda_handle_t frame;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    descriptor.style = 0x08000000u;
    descriptor.title = "";
    descriptor.wndproc = window_proc;
    descriptor.height = 240;
    descriptor.width = 320;
    descriptor.surface = (u32)bda_gui_draw_object_create_like(15);

    frame = bda_gui_register_frame_desc_like(&descriptor);
    if (!frame || (s32)(u32)frame == -1) {
        write_log("wb", "FRAME ERROR\n");
        return 1;
    }
    (void)bda_gui_frame_activate_like(frame, 0x100u);
    write_log("wb", "BEFORE PARENT HELP\n");
    (void)bda_gui_help_page_like(frame, g_help_document);
    write_log("ab", "RETURNED TO PARENT\n");
    (void)bda_msgbox_ex(frame, "Parent help probe", "RETURNED: PASS", 0u);

    (void)bda_gui_frame_stop_like(frame);
    (void)bda_gui_frame_release_like(frame);
    bda_gui_close_frame_like(frame);
    return 0;
}
