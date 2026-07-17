#include "bda_sdk.h"

#define CONTROL_COUNT 9u

#define GUI_SEND_OFFSET          0x040u
#define GUI_ACTIVE_SET_OFFSET    0x134u
#define GUI_CONTROL_CREATE_OFFSET 0x1a4u
#define GUI_CONTROL_DESTROY_OFFSET 0x1a8u

#define CONTROL_MSG_GET_TEXT       0x0133u
#define CONTROL_MSG_SET_TEXT       0x0134u
#define CONTROL_MSG_SET_MAX_LENGTH 0xf0c5u

#define LISTBOX_MSG_SET_SELECTION 0xf186u
#define LISTBOX_MSG_GET_SELECTION 0xf188u
#define LISTBOX_MSG_GET_TEXT      0xf189u
#define LISTBOX_MSG_GET_COUNT     0xf18bu
#define LISTBOX_MSG_APPEND_ITEM   0xf180u

#define COMBOBOX_MSG_APPEND_ITEM   0xf143u
#define COMBOBOX_MSG_SET_SELECTION 0xf14eu
#define COMBOBOX_MSG_GET_COUNT     0xf146u
#define COMBOBOX_MSG_GET_SELECTION 0xf147u

#define PROGRESS_MSG_SET_RANGE    0xf0a0u
#define PROGRESS_MSG_SET_POSITION 0xf0a3u

typedef struct control_spec {
    const char *class_name;
    const char *caption;
    u32 style;
    u32 flags;
    u32 id;
    s32 x;
    s32 y;
    s32 width;
    s32 height;
} control_spec_t;

static const char k_log_path_a[] = "A:\\CONTROL.LOG";
static const char k_log_path_root[] = "\\CONTROL.LOG";
static const char k_window_title[] = "CONTROL GALLERY";

static const control_spec_t k_specs[CONTROL_COUNT] = {
    {"static", "STATIC", 0x08000000u, 0, 0x201u, 8, 12, 108, 22},
    {"button", "BUTTON", 0x08000001u, 0, 0x202u, 124, 12, 108, 22},
    {"edit", "EDIT", 0x08000001u, 0, 0x203u, 8, 40, 224, 24},
    {"medit", "MEDIT", 0x08083001u, 0, 0x204u, 8, 70, 224, 38},
    {"listbox", "LISTBOX", 0x08090001u, 0, 0x205u, 8, 114, 108, 72},
    {"combobox", "COMBO", 0x08000001u, 0, 0x206u, 124, 114, 108, 28},
    {"progressbar", "PROGRESS", 0x08000000u, 0, 0x207u, 124, 148, 108, 18},
    {"toolbar", "TOOLBAR", 0x08000000u, 0, 0x208u, 8, 194, 224, 24},
    {"treeview", "TREEVIEW", 0x08000000u, 0, 0x209u, 8, 224, 224, 70},
};

static bda_handle_t g_frame;
static bda_handle_t g_controls[CONTROL_COUNT];
static volatile int g_detached;
static volatile int g_escape_requested;
static volatile int g_log_events;
static volatile u32 g_event_count;
static const char *g_log_path;
static char g_log_line[96];
static char g_edit_text[32];
static char g_medit_text[32];
static char g_list_text[32];

static char *append_text(char *out, char *end, const char *text) {
    while (*text && out < end) {
        *out++ = *text++;
    }
    return out;
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char hex[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        if (out < end) {
            *out++ = hex[(value >> shift) & 0x0fu];
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

static void reset_log(void) {
    int file;

    g_log_path = 0;
    file = open_log("wb");
    if (bda_fs_file_is_valid(file)) {
        (void)bda_fs_close_raw(file);
    }
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

static bda_handle_t control_create(
    const control_spec_t *spec,
    bda_handle_t parent
) {
    typedef bda_handle_t (*fn_t)(
        const char *, const char *, u32, u32, u32,
        s32, s32, s32, s32, bda_handle_t, u32
    );
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), GUI_CONTROL_CREATE_OFFSET
    );
    return fn(
        spec->class_name,
        spec->caption,
        spec->style,
        spec->flags,
        spec->id,
        spec->x,
        spec->y,
        spec->width,
        spec->height,
        parent,
        0
    );
}

static int control_send(
    bda_handle_t control,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    typedef int (*fn_t)(bda_handle_t, u32, u32, u32);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), GUI_SEND_OFFSET
    );
    return fn(control, message, wparam, lparam);
}

static int control_set_active(bda_handle_t control) {
    typedef int (*fn_t)(bda_handle_t);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), GUI_ACTIVE_SET_OFFSET
    );
    return fn(control);
}

static int control_destroy(bda_handle_t control) {
    typedef int (*fn_t)(bda_handle_t);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), GUI_CONTROL_DESTROY_OFFSET
    );
    return fn(control);
}

static int handle_is_valid(bda_handle_t handle) {
    return handle && (s32)(u32)handle != -1;
}

static void create_controls(void) {
    u32 index;
    int item;

    for (index = 0; index < CONTROL_COUNT; ++index) {
        char *out = g_log_line;
        char *end = g_log_line + sizeof(g_log_line) - 1;

        g_controls[index] = control_create(&k_specs[index], g_frame);
        out = append_text(out, end, "CREATE ");
        out = append_text(out, end, k_specs[index].class_name);
        out = append_text(out, end, "=");
        out = append_hex32(out, end, (u32)g_controls[index]);
        write_log_line(out);
    }

    if (handle_is_valid(g_controls[2])) {
        (void)control_send(g_controls[2], CONTROL_MSG_SET_MAX_LENGTH, 31, 0);
        (void)control_send(
            g_controls[2], CONTROL_MSG_SET_TEXT, 0, (u32)"EDIT READY"
        );
    }
    if (handle_is_valid(g_controls[3])) {
        (void)control_send(g_controls[3], CONTROL_MSG_SET_MAX_LENGTH, 31, 0);
        (void)control_send(
            g_controls[3], CONTROL_MSG_SET_TEXT, 0, (u32)"MEDIT READY"
        );
    }
    if (handle_is_valid(g_controls[4])) {
        item = control_send(
            g_controls[4], LISTBOX_MSG_APPEND_ITEM, 0, (u32)"ALPHA"
        );
        log_value("LIST ADD ALPHA=", (u32)item);
        item = control_send(
            g_controls[4], LISTBOX_MSG_APPEND_ITEM, 0, (u32)"BETA"
        );
        log_value("LIST ADD BETA=", (u32)item);
        item = control_send(
            g_controls[4], LISTBOX_MSG_APPEND_ITEM, 0, (u32)"GAMMA"
        );
        log_value("LIST ADD GAMMA=", (u32)item);
        log_value(
            "LIST COUNT=",
            (u32)control_send(g_controls[4], LISTBOX_MSG_GET_COUNT, 0, 0)
        );
        log_value(
            "LIST SET SEL=",
            (u32)control_send(g_controls[4], LISTBOX_MSG_SET_SELECTION, 1, 0)
        );
        log_value(
            "LIST GET SEL=",
            (u32)control_send(g_controls[4], LISTBOX_MSG_GET_SELECTION, 0, 0)
        );
        bda_memset(g_list_text, 0, sizeof(g_list_text));
        log_value(
            "LIST GET TEXT=",
            (u32)control_send(
                g_controls[4], LISTBOX_MSG_GET_TEXT, 1, (u32)g_list_text
            )
        );
        log_text(g_list_text);
    }
    if (handle_is_valid(g_controls[5])) {
        log_value(
            "COMBO ADD RED=",
            (u32)control_send(
                g_controls[5], COMBOBOX_MSG_APPEND_ITEM,
                0, (u32)"RED"
            )
        );
        log_value(
            "COMBO ADD GREEN=",
            (u32)control_send(
                g_controls[5], COMBOBOX_MSG_APPEND_ITEM,
                0, (u32)"GREEN"
            )
        );
        log_value(
            "COMBO COUNT=",
            (u32)control_send(g_controls[5], COMBOBOX_MSG_GET_COUNT, 0, 0)
        );
        log_value(
            "COMBO SET SEL=",
            (u32)control_send(
                g_controls[5], COMBOBOX_MSG_SET_SELECTION, 1, 0
            )
        );
        log_value(
            "COMBO GET SEL=",
            (u32)control_send(
                g_controls[5], COMBOBOX_MSG_GET_SELECTION, 0, 0
            )
        );
    }
    if (handle_is_valid(g_controls[6])) {
        log_value(
            "PROGRESS RANGE=",
            (u32)control_send(g_controls[6], PROGRESS_MSG_SET_RANGE, 0, 100)
        );
        log_value(
            "PROGRESS POS=",
            (u32)control_send(
                g_controls[6], PROGRESS_MSG_SET_POSITION, 65, 0
            )
        );
    }
    if (handle_is_valid(g_controls[1])) {
        log_value("ACTIVE BUTTON=", (u32)control_set_active(g_controls[1]));
    }
}

static void read_back_text(void) {
    int result;

    bda_memset(g_edit_text, 0, sizeof(g_edit_text));
    bda_memset(g_medit_text, 0, sizeof(g_medit_text));
    if (handle_is_valid(g_controls[2])) {
        result = control_send(
            g_controls[2], CONTROL_MSG_GET_TEXT,
            sizeof(g_edit_text), (u32)g_edit_text
        );
        log_value("GET EDIT=", (u32)result);
        log_text(g_edit_text);
    }
    if (handle_is_valid(g_controls[3])) {
        result = control_send(
            g_controls[3], CONTROL_MSG_GET_TEXT,
            sizeof(g_medit_text), (u32)g_medit_text
        );
        log_value("GET MEDIT=", (u32)result);
        log_text(g_medit_text);
    }
}

static void destroy_controls(void) {
    u32 index = CONTROL_COUNT;

    while (index) {
        --index;
        if (handle_is_valid(g_controls[index])) {
            char *out = g_log_line;
            char *end = g_log_line + sizeof(g_log_line) - 1;
            int result = control_destroy(g_controls[index]);

            out = append_text(out, end, "DESTROY ");
            out = append_text(out, end, k_specs[index].class_name);
            out = append_text(out, end, "=");
            out = append_hex32(out, end, (u32)result);
            write_log_line(out);
        }
        g_controls[index] = 0;
    }
}

static int gallery_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        log_text("FRAME ATTACH");
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        log_text("FRAME DETACH");
        g_detached = 1;
    } else if (message == 0x11u && wparam == 0x1bu) {
        g_escape_requested = 1;
    } else if (g_log_events && g_event_count < 48u) {
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
    bda_memset(g_controls, 0, sizeof(g_controls));
    g_frame = 0;
    g_detached = 0;
    g_escape_requested = 0;
    g_log_events = 0;
    g_event_count = 0;
    reset_log();
    log_text("START CONTROL GALLERY V7");

    descriptor.style = 0;
    descriptor.title = k_window_title;
    descriptor.wndproc = gallery_window_proc;
    descriptor.height = 240;
    descriptor.width = 320;
    descriptor.surface = 0;

    g_frame = bda_gui_register_frame_desc(&descriptor);
    log_value("FRAME=", (u32)g_frame);
    if (!handle_is_valid(g_frame)) {
        log_text("RESULT=FRAME FAIL");
        return 1;
    }
    log_value("ACTIVATE=", (u32)bda_gui_frame_activate(g_frame, 0x100));
    create_controls();
    log_text("LOOP READY");
    g_log_events = 1;

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
            read_back_text();
            destroy_controls();
            log_value("STOP=", (u32)bda_gui_frame_stop(g_frame));
            log_value("RELEASE=", (u32)bda_gui_frame_release(g_frame));
            close_requested = 1;
        }
    }

    log_text("BEFORE CLOSE");
    bda_gui_close_frame(g_frame);
    g_frame = 0;
    log_text("RESULT=PASS");
    return 0;
}
