#include "bda_sdk.h"

#define GUI_CONTROL_CREATE_OFFSET  0x1a4u
#define GUI_CONTROL_DESTROY_OFFSET 0x1a8u

#ifndef TEST_CLASS
#define TEST_CLASS   "SLIDERCTRL"
#define TEST_CAPTION "SLIDER"
#define TEST_STYLE   0x08000001u
#define TEST_ID      0x242u
#define TEST_VERSION "SLIDERCTRL V1"
#define TEST_Y       100
#define TEST_HEIGHT  30
#endif

#ifndef TEST_EXTRA
#define TEST_EXTRA 0u
#endif

static const char k_log_path_a[] = "A:\\SPECIAL.LOG";
static const char k_log_path_root[] = "\\SPECIAL.LOG";
static bda_handle_t g_frame;
static bda_handle_t g_control;
static volatile int g_detached;
static volatile int g_escape_requested;
static volatile u32 g_event_count;
static const char *g_log_path;
static char g_log_line[96];

static char *append_text(char *out, char *end, const char *text) {
    while (*text && out < end) {
        *out++ = *text++;
    }
    return out;
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char digits[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        if (out < end) {
            *out++ = digits[(value >> shift) & 0x0fu];
        }
    }
    return out;
}

static int open_log(const char *mode) {
    int file;

    if (g_log_path) {
        return bda_fs_fopen_raw(g_log_path, mode);
    }
    file = bda_fs_fopen_raw(k_log_path_a, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = k_log_path_a;
        return file;
    }
    file = bda_fs_fopen_raw(k_log_path_root, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = k_log_path_root;
    }
    return file;
}

static void write_log_line(char *out) {
    char *end = g_log_line + sizeof(g_log_line) - 1;
    int file;
    u32 length;

    out = append_text(out, end, "\r\n");
    *out = 0;
    length = (u32)(out - g_log_line);
    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_log_line, length);
    (void)bda_fs_close_raw(file);
}

static void reset_log(void) {
    int file;

    g_log_path = 0;
    file = open_log("wb");
    if (bda_fs_file_is_valid(file)) {
        (void)bda_fs_close_raw(file);
    }
}

static void log_text(const char *text) {
    write_log_line(append_text(
        g_log_line, g_log_line + sizeof(g_log_line) - 1, text
    ));
}

static void log_value(const char *label, u32 value) {
    char *out = g_log_line;
    char *end = g_log_line + sizeof(g_log_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, value);
    write_log_line(out);
}

static void log_event(u32 message, u32 wparam, u32 lparam) {
    char *out = g_log_line;
    char *end = g_log_line + sizeof(g_log_line) - 1;

    out = append_text(out, end, "EVENT M=");
    out = append_hex32(out, end, message);
    out = append_text(out, end, " W=");
    out = append_hex32(out, end, wparam);
    out = append_text(out, end, " L=");
    out = append_hex32(out, end, lparam);
    write_log_line(out);
}

static int handle_is_valid(bda_handle_t handle) {
    return handle && (u32)handle != 0xffffffffu;
}

static bda_handle_t control_create(bda_handle_t parent) {
    typedef bda_handle_t (*fn_t)(
        const char *, const char *, u32, u32, u32,
        s32, s32, s32, s32, bda_handle_t, u32
    );
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), GUI_CONTROL_CREATE_OFFSET
    );

    return fn(
        TEST_CLASS, TEST_CAPTION, TEST_STYLE, 0, TEST_ID,
        20, TEST_Y, 200, TEST_HEIGHT, parent, TEST_EXTRA
    );
}

static int control_destroy(bda_handle_t control) {
    typedef int (*fn_t)(bda_handle_t);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), GUI_CONTROL_DESTROY_OFFSET
    );
    return fn(control);
}

static int special_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        log_text("FRAME ATTACH");
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        g_detached = 1;
        log_text("FRAME DETACH");
    } else if (message == 0x11u && wparam == 0x1bu) {
        g_escape_requested = 1;
    } else if (g_event_count < 40u) {
        ++g_event_count;
        log_event(message, wparam, lparam);
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

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    u32 close_wait = 0;
    int close_requested = 0;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_control = 0;
    g_detached = 0;
    g_escape_requested = 0;
    g_event_count = 0;
    reset_log();
    log_text("START " TEST_VERSION);

    descriptor.title = TEST_VERSION;
    descriptor.wndproc = special_window_proc;
    descriptor.height = 240;
    descriptor.width = 320;

    g_frame = bda_gui_register_frame_desc(&descriptor);
    log_value("FRAME=", (u32)g_frame);
    if (!handle_is_valid(g_frame)) {
        log_text("RESULT=FRAME FAIL");
        return 1;
    }
    log_value("ACTIVATE=", (u32)bda_gui_frame_activate(g_frame, 0x100));
    g_control = control_create(g_frame);
    log_value("CONTROL=", (u32)g_control);
    if (!handle_is_valid(g_control)) {
        log_text("CONTROL INVALID");
    }
    log_text("LOOP READY");

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
            log_text("ESC DOWN");
            wait_escape_release();
            log_text("ESC UP");
            if (handle_is_valid(g_control)) {
                log_value("DESTROY=", (u32)control_destroy(g_control));
                g_control = 0;
            }
            log_value("STOP=", (u32)bda_gui_frame_stop(g_frame));
            log_value("RELEASE=", (u32)bda_gui_frame_release(g_frame));
            close_requested = 1;
        }
    }

    log_text("BEFORE CLOSE");
    bda_gui_close_frame(g_frame);
    log_text("RESULT=PASS");
    return 0;
}
