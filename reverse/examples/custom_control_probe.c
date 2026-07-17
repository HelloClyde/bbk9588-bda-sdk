#include "bda_sdk.h"

#define GUI_SEND_OFFSET             0x040u
#define GUI_ACTIVE_SET_OFFSET       0x134u
#define GUI_CLASS_REGISTER_OFFSET   0x190u
#define GUI_CLASS_UNREGISTER_OFFSET 0x194u
#define GUI_CONTROL_CREATE_OFFSET   0x1a4u
#define GUI_CONTROL_DESTROY_OFFSET  0x1a8u

#define CUSTOM_CONTROL_ID 0x301u
#define CUSTOM_WIDTH      170
#define CUSTOM_HEIGHT     100

typedef struct custom_class_desc {
    const char *class_name;
    u32 reserved04;
    u32 reserved08;
    void *draw_object;
    bda_wndproc_t wndproc;
} custom_class_desc_t;

static const char k_class_name[] = "SDK_CUSTOM";
static const char k_window_title[] = "CUSTOM CONTROL";
static const char k_log_path_a[] = "A:\\CUSTOM.LOG";
static const char k_log_path_root[] = "\\CUSTOM.LOG";

static bda_handle_t g_frame;
static bda_handle_t g_control;
static volatile int g_detached;
static volatile int g_escape_requested;
static volatile int g_custom_dirty;
static volatile int g_custom_pressed;
static volatile u32 g_custom_events;
static volatile u32 g_paint_count;
static const char *g_log_path;
static char g_log_line[96];

static char *append_text(char *out, char *end, const char *value) {
    while (*value && out < end) {
        *out++ = *value++;
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

static void log_text(const char *value) {
    write_log_line(append_text(
        g_log_line, g_log_line + sizeof(g_log_line) - 1, value
    ));
}

static void log_value(const char *label, u32 value) {
    char *out = g_log_line;
    char *end = g_log_line + sizeof(g_log_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, value);
    write_log_line(out);
}

static void log_event(const char *label, u32 message, u32 wparam, u32 lparam) {
    char *out = g_log_line;
    char *end = g_log_line + sizeof(g_log_line) - 1;

    out = append_text(out, end, label);
    out = append_text(out, end, " M=");
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

static int class_register(custom_class_desc_t *descriptor) {
    typedef int (*fn_t)(custom_class_desc_t *);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), GUI_CLASS_REGISTER_OFFSET
    );
    return fn(descriptor);
}

static int class_unregister(const char *class_name) {
    typedef int (*fn_t)(const char *);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), GUI_CLASS_UNREGISTER_OFFSET
    );
    return fn(class_name);
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
        k_class_name, "TOUCH ME", 0x08000001u, 0, CUSTOM_CONTROL_ID,
        35, 85, CUSTOM_WIDTH, CUSTOM_HEIGHT, parent, 0
    );
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

static void draw_pixel(
    bda_handle_t draw, s32 x, s32 y, u32 red, u32 green, u32 blue
) {
    (void)bda_gui_put_pixel_rgb(draw, x, y, red, green, blue);
}

static void draw_custom_control(void) {
    bda_handle_t draw;
    s32 index;
    u32 red = g_custom_pressed ? 220u : 24u;
    u32 green = g_custom_pressed ? 42u : 132u;
    u32 blue = g_custom_pressed ? 42u : 220u;

    if (!handle_is_valid(g_control)) {
        return;
    }
    draw = bda_gui_object_draw_begin(g_control);
    log_value("PAINT BEGIN=", (u32)draw);
    if (!handle_is_valid(draw)) {
        return;
    }
    (void)bda_gui_draw_guard_begin();
    for (index = 0; index < CUSTOM_WIDTH; ++index) {
        draw_pixel(draw, index, 0, red, green, blue);
        draw_pixel(draw, index, CUSTOM_HEIGHT - 1, red, green, blue);
    }
    for (index = 0; index < CUSTOM_HEIGHT; ++index) {
        draw_pixel(draw, 0, index, red, green, blue);
        draw_pixel(draw, CUSTOM_WIDTH - 1, index, red, green, blue);
        draw_pixel(draw, index + 30, index, red, green, blue);
        draw_pixel(draw, CUSTOM_WIDTH - 31 - index, index, red, green, blue);
    }
    (void)bda_gui_draw_guard_end();
    bda_gui_object_draw_end(g_control, draw);
    ++g_paint_count;
    log_value("PAINT COUNT=", g_paint_count);
}

static int custom_window_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
) {
    if (g_custom_events < 24u) {
        ++g_custom_events;
        log_event("CUSTOM", message, wparam, lparam);
    }
    if (message == BDA_MSG_TOUCH_COORDINATE) {
        g_custom_pressed = !g_custom_pressed;
        g_custom_dirty = 1;
        log_text(g_custom_pressed ? "CUSTOM PRESSED" : "CUSTOM RELEASED");
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

static int frame_window_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        log_text("FRAME ATTACH");
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        g_detached = 1;
        log_text("FRAME DETACH");
    } else if (message == 0x11u && wparam == 0x1bu) {
        g_escape_requested = 1;
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
    custom_class_desc_t class_descriptor;
    bda_frame_desc_t frame_descriptor;
    bda_gui_message_t message;
    u32 close_wait = 0;
    int close_requested = 0;
    int class_registered = 0;

    bda_memset(&class_descriptor, 0, sizeof(class_descriptor));
    bda_memset(&frame_descriptor, 0, sizeof(frame_descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_control = 0;
    g_detached = 0;
    g_escape_requested = 0;
    g_custom_dirty = 0;
    g_custom_pressed = 0;
    g_custom_events = 0;
    g_paint_count = 0;
    reset_log();
    log_text("START CUSTOM CONTROL V1");

    class_descriptor.class_name = k_class_name;
    class_descriptor.draw_object = bda_gui_draw_object_create(15);
    class_descriptor.wndproc = custom_window_proc;
    log_value("DRAW OBJECT=", (u32)class_descriptor.draw_object);
    class_registered = class_register(&class_descriptor);
    log_value("CLASS REGISTER=", (u32)class_registered);
    if (!class_registered) {
        log_text("RESULT=REGISTER FAIL");
        return 1;
    }

    frame_descriptor.title = k_window_title;
    frame_descriptor.wndproc = frame_window_proc;
    frame_descriptor.height = 240;
    frame_descriptor.width = 320;
    g_frame = bda_gui_register_frame_desc(&frame_descriptor);
    log_value("FRAME=", (u32)g_frame);
    if (!handle_is_valid(g_frame)) {
        (void)class_unregister(k_class_name);
        log_text("RESULT=FRAME FAIL");
        return 2;
    }
    log_value("ACTIVATE=", (u32)bda_gui_frame_activate(g_frame, 0x100));
    g_control = control_create(g_frame);
    log_value("CONTROL=", (u32)g_control);
    if (!handle_is_valid(g_control)) {
        log_text("RESULT=CREATE FAIL");
        (void)bda_gui_frame_stop(g_frame);
        (void)bda_gui_frame_release(g_frame);
        bda_gui_close_frame(g_frame);
        (void)class_unregister(k_class_name);
        return 3;
    }
    log_value("ACTIVE=", (u32)control_set_active(g_control));
    draw_custom_control();
    log_text("LOOP READY");

    for (;;) {
        int pump_result = bda_gui_event_pump_frame_once(&message, g_frame);

        if (g_custom_dirty) {
            g_custom_dirty = 0;
            draw_custom_control();
        }
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
            log_value("DESTROY=", (u32)control_destroy(g_control));
            g_control = 0;
            log_value("STOP=", (u32)bda_gui_frame_stop(g_frame));
            log_value("RELEASE=", (u32)bda_gui_frame_release(g_frame));
            close_requested = 1;
        }
    }

    log_text("BEFORE CLOSE");
    bda_gui_close_frame(g_frame);
    g_frame = 0;
    log_value("CLASS UNREGISTER=", (u32)class_unregister(k_class_name));
    log_text(g_paint_count >= 2u ? "RESULT=PASS" : "RESULT=NO TOUCH");
    return 0;
}
