#include "bda_controls.h"

#define TEXT_A_BACKGROUND_INDEX 11u
#define BLACK_BACKGROUND_INDEX   1u
#define MAX_VX_RESOURCE_SIZE     0x28000u

static const char k_text_a_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char k_text_a_fallback[] = "\\shell\\text_A.dlx";
static const char k_black_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\shell\\enote_black_add.dlx";
static const char k_black_fallback[] = "\\shell\\enote_black_add.dlx";
static const char k_log_path_a[] = "A:\\SKINBIND.LOG";
static const char k_log_path_root[] = "\\SKINBIND.LOG";

static bda_handle_t g_frame;
static bda_handle_t g_medit;
static bda_handle_t g_dark_medit;
static bda_handle_t g_listbox;
static bda_handle_t g_default_edit;
static void *g_blue_background;
static void *g_black_background;
static volatile int g_detached;
static volatile int g_escape_requested;
static const char *g_log_path;
static char g_log_line[112];

static u32 read_u32_le(const u8 *bytes) {
    return (u32)bytes[0] |
        ((u32)bytes[1] << 8) |
        ((u32)bytes[2] << 16) |
        ((u32)bytes[3] << 24);
}

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

static int open_resource_file(const char *path, const char *fallback) {
    int file = bda_fs_fopen_raw(path, "rb");

    if (!bda_fs_file_is_valid(file)) {
        file = bda_fs_fopen_raw(fallback, "rb");
    }
    return file;
}

static void *load_dlx_vx(
    const char *path,
    const char *fallback,
    u32 resource_index,
    const char *log_prefix
) {
    u8 header[0x24];
    u8 entry[12];
    u8 *resource;
    u32 count;
    u32 header_size;
    u32 resource_offset;
    u32 resource_size;
    int file = open_resource_file(path, fallback);

    log_value(log_prefix, (u32)file);
    if (!bda_fs_file_is_valid(file)) {
        return 0;
    }
    if (bda_fs_fread_raw(header, 1, sizeof(header), file) !=
        (int)sizeof(header)) {
        (void)bda_fs_close_raw(file);
        return 0;
    }
    count = header[3];
    header_size = read_u32_le(header + 0x0c);
    if (header[0] != 'D' || header[1] != 'L' || header[2] != 'X' ||
        resource_index >= count || header_size < sizeof(header)) {
        (void)bda_fs_close_raw(file);
        return 0;
    }
    if (bda_fs_seek_raw(
            file, (s32)(0x24u + resource_index * 12u), BDA_SEEK_SET
        ) < 0 ||
        bda_fs_fread_raw(entry, 1, sizeof(entry), file) !=
            (int)sizeof(entry)) {
        (void)bda_fs_close_raw(file);
        return 0;
    }
    resource_offset = header_size + read_u32_le(entry + 4);
    resource_size = read_u32_le(entry + 8);
    if (read_u32_le(entry) != 1u || resource_size < 24u ||
        resource_size > MAX_VX_RESOURCE_SIZE) {
        (void)bda_fs_close_raw(file);
        return 0;
    }
    resource = (u8 *)bda_alloc(resource_size);
    if (!resource) {
        (void)bda_fs_close_raw(file);
        return 0;
    }
    if (bda_fs_seek_raw(file, (s32)resource_offset, BDA_SEEK_SET) < 0 ||
        bda_fs_fread_raw(resource, 1, resource_size, file) !=
            (int)resource_size) {
        bda_free(resource);
        (void)bda_fs_close_raw(file);
        return 0;
    }
    (void)bda_fs_close_raw(file);
    if (resource[0] != 'V' || resource[1] != 'X' ||
        read_u32_le(resource + 6) != 240u ||
        read_u32_le(resource + 10) != 265u) {
        bda_free(resource);
        return 0;
    }
    log_value("VX PTR=", (u32)resource);
    log_value("VX SIZE=", resource_size);
    return resource;
}

static bda_handle_t create_control(
    const char *class_name,
    const char *caption,
    u32 style,
    u32 id,
    s32 x,
    s32 y,
    s32 width,
    s32 height
) {
    bda_control_desc_t descriptor;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    descriptor.class_name = class_name;
    descriptor.caption = caption;
    descriptor.style = style;
    descriptor.id = id;
    descriptor.x = x;
    descriptor.y = y;
    descriptor.width = width;
    descriptor.height = height;
    descriptor.parent = g_frame;
    return bda_control_create(&descriptor);
}

static int skin_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
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

static void destroy_control(bda_handle_t *control, const char *label) {
    if (bda_control_is_valid(*control)) {
        log_value(label, (u32)bda_control_destroy(*control));
    }
    *control = 0;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_t frame_descriptor;
    bda_gui_message_t message;
    void *dark_draw_object;
    u32 close_wait = 0;
    int close_requested = 0;

    g_frame = 0;
    g_medit = 0;
    g_dark_medit = 0;
    g_listbox = 0;
    g_default_edit = 0;
    g_blue_background = 0;
    g_black_background = 0;
    g_detached = 0;
    g_escape_requested = 0;
    reset_log();
    log_text("START CONTROL SKIN V2");

    g_blue_background = load_dlx_vx(
        k_text_a_path, k_text_a_fallback,
        TEXT_A_BACKGROUND_INDEX, "OPEN BLUE="
    );
    g_black_background = load_dlx_vx(
        k_black_path, k_black_fallback,
        BLACK_BACKGROUND_INDEX, "OPEN BLACK="
    );
    if (!g_blue_background || !g_black_background) {
        log_text("RESULT=RESOURCE FAIL");
        if (g_black_background) {
            bda_free(g_black_background);
        }
        if (g_blue_background) {
            bda_free(g_blue_background);
        }
        return 2;
    }

    bda_memset(&frame_descriptor, 0, sizeof(frame_descriptor));
    bda_memset(&message, 0, sizeof(message));
    frame_descriptor.title = "CONTROL SKIN BINDING";
    frame_descriptor.wndproc = skin_window_proc;
    frame_descriptor.height = 240;
    frame_descriptor.width = 320;
    g_frame = bda_gui_register_frame_desc(&frame_descriptor);
    log_value("FRAME=", (u32)g_frame);
    if (!bda_control_is_valid(g_frame)) {
        log_text("RESULT=FRAME FAIL");
        bda_free(g_black_background);
        bda_free(g_blue_background);
        return 3;
    }
    log_value("ACTIVATE=", (u32)bda_gui_frame_activate(g_frame, 0x100));

    g_medit = create_control(
        BDA_CONTROL_CLASS_MEDIT, "", BDA_MEDIT_STYLE_DEFAULT,
        0x301u, 0, 25, 240, 100
    );
    log_value("CREATE MEDIT=", (u32)g_medit);
    if (bda_control_is_valid(g_medit)) {
        log_value(
            "MEDIT F0DD=",
            (u32)bda_medit_set_background_vx(
                g_medit, g_blue_background
            )
        );
        (void)bda_text_control_set_max_length(g_medit, 63);
        log_value(
            "MEDIT TEXT=",
            (u32)bda_text_control_set_text(g_medit, "MEDIT BLUE SKIN")
        );
    }

    dark_draw_object = bda_gui_draw_object_create(15);
    log_value("DRAW OBJECT=", (u32)dark_draw_object);
    g_dark_medit = create_control(
        BDA_CONTROL_CLASS_MEDIT, "", BDA_MEDIT_STYLE_DEFAULT,
        0x304u, 0, 130, 240, 40
    );
    log_value("CREATE DARK MEDIT=", (u32)g_dark_medit);
    if (bda_control_is_valid(g_dark_medit)) {
        log_value(
            "DARK MEDIT F0DD=",
            (u32)bda_medit_set_background_vx(
                g_dark_medit, g_black_background
            )
        );
        log_value(
            "DARK MEDIT F0DF=",
            (u32)bda_medit_set_draw_object(
                g_dark_medit, 1, dark_draw_object
            )
        );
        (void)bda_text_control_set_max_length(g_dark_medit, 31);
        (void)bda_text_control_set_text(g_dark_medit, "MEDIT BLACK SKIN");
    }

    g_listbox = create_control(
        BDA_CONTROL_CLASS_LISTBOX, "LISTBOX", BDA_LISTBOX_STYLE_DEFAULT,
        0x302u, 0, 175, 240, 70
    );
    log_value("CREATE LISTBOX=", (u32)g_listbox);
    if (bda_control_is_valid(g_listbox)) {
        log_value(
            "LIST F1B4=",
            (u32)bda_listbox_set_background_vx(
                g_listbox, g_black_background
            )
        );
        log_value(
            "LIST F1B5=",
            (u32)bda_listbox_set_draw_object(
                g_listbox, 1, dark_draw_object
            )
        );
        (void)bda_listbox_append_item(g_listbox, "BLACK SKIN ITEM 1");
        (void)bda_listbox_append_item(g_listbox, "BLACK SKIN ITEM 2");
        (void)bda_listbox_set_selection(g_listbox, 0);
    }

    g_default_edit = create_control(
        BDA_CONTROL_CLASS_EDIT, "DEFAULT GRAY EDIT", BDA_EDIT_STYLE_DEFAULT,
        0x303u, 0, 250, 240, 25
    );
    log_value("CREATE DEFAULT=", (u32)g_default_edit);
    if (bda_control_is_valid(g_default_edit)) {
        (void)bda_text_control_set_text(g_default_edit, "DEFAULT GRAY EDIT");
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
            destroy_control(&g_default_edit, "DESTROY DEFAULT=");
            destroy_control(&g_listbox, "DESTROY LIST=");
            destroy_control(&g_dark_medit, "DESTROY DARK MEDIT=");
            destroy_control(&g_medit, "DESTROY MEDIT=");
            log_value("STOP=", (u32)bda_gui_frame_stop(g_frame));
            log_value("RELEASE=", (u32)bda_gui_frame_release(g_frame));
            close_requested = 1;
        }
    }

    log_text("BEFORE CLOSE");
    bda_gui_close_frame(g_frame);
    g_frame = 0;
    log_text("CLOSE RETURNED");
    bda_free(g_black_background);
    g_black_background = 0;
    log_text("FREE BLACK");
    bda_free(g_blue_background);
    g_blue_background = 0;
    log_text("FREE BLUE");
    log_text("RESULT=PASS");
    return 0;
}
