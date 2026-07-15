#include "bda_sdk.h"

#ifndef TOUCH_STAGE_VERSION
#define TOUCH_STAGE_VERSION 11
#endif

#if TOUCH_STAGE_VERSION == 23
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V23"
#define TOUCH_STAGE_START_LOG "START V23"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 0
#define TOUCH_STAGE_USE_DRAW_GUARD 0
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_REQUEST_OBJECT_REDRAW 0
#define TOUCH_STAGE_PRESENT_AFTER_OBJECT_PAINT 0
#define TOUCH_STAGE_VECTOR_DYNAMIC_STATUS 1
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 22
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V22"
#define TOUCH_STAGE_START_LOG "START V22"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 0
#define TOUCH_STAGE_USE_DRAW_GUARD 0
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_REQUEST_OBJECT_REDRAW 0
#define TOUCH_STAGE_PRESENT_AFTER_OBJECT_PAINT 1
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 21
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V21"
#define TOUCH_STAGE_START_LOG "START V21"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 0
#define TOUCH_STAGE_USE_DRAW_GUARD 0
#define TOUCH_STAGE_DRAW_IN_WNDPROC 1
#define TOUCH_STAGE_REQUEST_OBJECT_REDRAW 1
#define TOUCH_STAGE_DIRECT_REDRAW_NOTIFY 1
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 20
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V20"
#define TOUCH_STAGE_START_LOG "START V20"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 0
#define TOUCH_STAGE_USE_DRAW_GUARD 0
#define TOUCH_STAGE_DRAW_IN_WNDPROC 1
#define TOUCH_STAGE_REQUEST_OBJECT_REDRAW 1
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 19
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V19"
#define TOUCH_STAGE_START_LOG "START V19"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 0
#define TOUCH_STAGE_USE_DRAW_GUARD 0
#define TOUCH_STAGE_DRAW_IN_WNDPROC 1
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 18
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V18"
#define TOUCH_STAGE_START_LOG "START V18"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 0
#define TOUCH_STAGE_USE_DRAW_GUARD 0
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 17
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V17"
#define TOUCH_STAGE_START_LOG "START V17"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 1
#define TOUCH_STAGE_USE_DRAW_GUARD 1
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 1
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 1
#elif TOUCH_STAGE_VERSION == 16
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V16"
#define TOUCH_STAGE_START_LOG "START V16"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 1
#define TOUCH_STAGE_USE_DRAW_GUARD 1
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 1
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 15
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V15"
#define TOUCH_STAGE_START_LOG "START V15"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 1
#define TOUCH_STAGE_USE_DRAW_GUARD 1
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_COMPAT_COPY_IN 1
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 1
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 14
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V14"
#define TOUCH_STAGE_START_LOG "START V14"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 1
#define TOUCH_STAGE_USE_DRAW_GUARD 1
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_COMPAT_COPY_IN 1
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 13
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V13"
#define TOUCH_STAGE_START_LOG "START V13"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 1
#define TOUCH_STAGE_USE_COMPAT_PAINT 0
#define TOUCH_STAGE_USE_DRAW_GUARD 1
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#elif TOUCH_STAGE_VERSION == 12
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V12"
#define TOUCH_STAGE_START_LOG "START V12"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 1
#define TOUCH_STAGE_USE_OBJECT_PAINT 0
#define TOUCH_STAGE_USE_COMPAT_PAINT 0
#define TOUCH_STAGE_USE_DRAW_GUARD 1
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#else
#define TOUCH_STAGE_WINDOW_TITLE "TOUCH V11"
#define TOUCH_STAGE_START_LOG "START V11"
#define TOUCH_STAGE_COALESCE_STARTUP_REDRAWS 0
#define TOUCH_STAGE_USE_OBJECT_PAINT 0
#define TOUCH_STAGE_USE_COMPAT_PAINT 0
#define TOUCH_STAGE_USE_DRAW_GUARD 1
#define TOUCH_STAGE_DRAW_IN_WNDPROC 0
#define TOUCH_STAGE_COMPAT_COPY_IN 0
#define TOUCH_STAGE_COMPAT_WHITE_SURFACE 0
#define TOUCH_STAGE_COPY_DESTINATION_FIRST 0
#define TOUCH_STAGE_SKIP_OLD_ERASE 0
#endif

#ifndef TOUCH_STAGE_REQUEST_OBJECT_REDRAW
#define TOUCH_STAGE_REQUEST_OBJECT_REDRAW 0
#endif

#ifndef TOUCH_STAGE_DIRECT_REDRAW_NOTIFY
#define TOUCH_STAGE_DIRECT_REDRAW_NOTIFY 0
#endif

#ifndef TOUCH_STAGE_PRESENT_AFTER_OBJECT_PAINT
#define TOUCH_STAGE_PRESENT_AFTER_OBJECT_PAINT 0
#endif

#ifndef TOUCH_STAGE_VECTOR_DYNAMIC_STATUS
#define TOUCH_STAGE_VECTOR_DYNAMIC_STATUS 0
#endif

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define EVENT_QUEUE_SIZE 16u
#define LOG_CAPACITY 4096u

typedef struct touch_event {
    u32 message;
    u32 wparam;
    u32 lparam;
} touch_event_t;

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHDBG.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHDBG.TXT";
static const char k_window_title[] = TOUCH_STAGE_WINDOW_TITLE;

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static volatile u32 g_queue_read;
static volatile u32 g_queue_write;
static volatile int g_exit;
static volatile int g_need_draw;
static touch_event_t g_events[EVENT_QUEUE_SIZE];
static char g_log[LOG_CAPACITY];
static u32 g_log_length;
static u32 g_log_flushed_length;
static const char *g_log_path;
static int g_log_append_supported;
static u32 g_last_message;
static int g_has_coordinate;
static int g_has_painted_cross;
static s32 g_touch_x;
static s32 g_touch_y;
static s32 g_painted_x;
static s32 g_painted_y;
static int g_has_painted_status;
static char g_painted_status[32];
#if TOUCH_STAGE_REQUEST_OBJECT_REDRAW
static int g_redraw_request_logged;
static volatile int g_redraw_callback_seen;
static int g_redraw_callback_logged;

static int touch_stage_request_object_redraw(void) {
#if TOUCH_STAGE_DIRECT_REDRAW_NOTIFY
    return bda_sdk_internal_call4(
        bda_sdk_internal_gui(), 0x03cu,
        (u32)g_frame, BDA_MSG_REDRAW_INPUT, 0, 0
    );
#else
    return bda_sdk_internal_call1(
        bda_sdk_internal_gui(), 0x0e0u, (u32)g_frame
    );
#endif
}
#endif
#if TOUCH_STAGE_USE_OBJECT_PAINT
static int g_object_paint_logged;
#endif
#if TOUCH_STAGE_PRESENT_AFTER_OBJECT_PAINT
static int g_trailing_present_logged;
#endif
#if TOUCH_STAGE_VECTOR_DYNAMIC_STATUS
static int g_vector_draw_logged;
#endif
#if TOUCH_STAGE_USE_COMPAT_PAINT
static bda_handle_t touch_stage_compat_context_create(
    bda_handle_t source_context
) {
    return (bda_handle_t)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), 0x310u, (u32)source_context
    );
}

static int touch_stage_context_copy(
    bda_handle_t source_context,
    s32 source_x,
    s32 source_y,
    s32 width,
    s32 height,
    bda_handle_t destination_context,
    s32 destination_x,
    s32 destination_y,
    u32 backend_arg
) {
    typedef int (*copy_fn_t)(
        u32, u32, u32, u32, u32, u32, u32, u32, u32
    );
    copy_fn_t fn = (copy_fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), 0x418u
    );

    return fn(
        (u32)source_context,
        (u32)source_x,
        (u32)source_y,
        (u32)width,
        (u32)height,
        (u32)destination_context,
        (u32)destination_x,
        (u32)destination_y,
        backend_arg
    );
}

static void touch_stage_compat_context_free(bda_handle_t context) {
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), 0x314u, (u32)context
    );
}
#endif
#if TOUCH_STAGE_COALESCE_STARTUP_REDRAWS
static int g_initial_scene_drawn;
static int g_initial_redraw_suppressed;
#endif

static char *append_char(char *out, char *end, char value) {
    if (out < end) {
        *out++ = value;
    }
    return out;
}

static char *append_text(char *out, char *end, const char *text) {
    while (*text) {
        out = append_char(out, end, *text++);
    }
    return out;
}

static char *append_u32(char *out, char *end, u32 value) {
    char digits[10];
    int count = 0;

    if (!value) {
        return append_char(out, end, '0');
    }
    while (value && count < (int)sizeof(digits)) {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    }
    while (count) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static char hex_digit(u32 value) {
    return (char)(value < 10u ? '0' + value : 'A' + value - 10u);
}

static char *append_hex32(char *out, char *end, u32 value) {
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        out = append_char(out, end, hex_digit((value >> shift) & 0x0fu));
    }
    return out;
}

static s32 event_x(u32 lparam) {
    return (s32)(short)(lparam & 0xffffu);
}

static s32 event_y(u32 lparam) {
    return (s32)(short)((lparam >> 16) & 0xffffu);
}

static int coordinate_valid(s32 x, s32 y) {
    return x >= 0 && x < SCREEN_WIDTH && y >= 0 && y < SCREEN_HEIGHT;
}

static int open_log_file(const char *mode) {
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

static void reset_log_file(void) {
    int file;

    g_log_path = 0;
    g_log_flushed_length = 0;
    file = open_log_file("wb");
    if (bda_fs_file_is_valid(file)) {
        (void)bda_fs_close_raw(file);
    }
}

static void persist_log(void) {
    int file;
    int written;
    u32 pending;

    if (g_log_flushed_length >= g_log_length) {
        return;
    }
    pending = g_log_length - g_log_flushed_length;
    if (g_log_append_supported >= 0) {
        file = open_log_file("ab");
        if (bda_fs_file_is_valid(file)) {
            written = bda_fs_write_raw(
                file, g_log + g_log_flushed_length, pending
            );
            (void)bda_fs_close_raw(file);
            if (written > 0) {
                g_log_append_supported = 1;
                g_log_flushed_length += (u32)written;
            }
            if (g_log_flushed_length >= g_log_length) {
                g_log_length = 0;
                g_log_flushed_length = 0;
                g_log[0] = 0;
            }
            return;
        }
        g_log_append_supported = -1;
    }

    file = open_log_file("wb");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    written = bda_fs_write_raw(file, g_log, g_log_length);
    (void)bda_fs_close_raw(file);
    if (written > 0) {
        g_log_flushed_length = (u32)written;
    }
}

static void finish_log_line_buffered(char *out) {
    char *end = g_log + sizeof(g_log) - 1;

    out = append_text(out, end, "\r\n");
    *out = 0;
    g_log_length = (u32)(out - g_log);
}

static void finish_log_line(char *out) {
    finish_log_line_buffered(out);
    persist_log();
}

static void log_text(const char *text) {
    char *out = g_log + g_log_length;
    char *end = g_log + sizeof(g_log) - 1;

    if (out >= end - 48) {
        return;
    }
    out = append_text(out, end, text);
    finish_log_line(out);
}

static void log_value(const char *label, u32 value) {
    char *out = g_log + g_log_length;
    char *end = g_log + sizeof(g_log) - 1;

    if (out >= end - 48) {
        return;
    }
    out = append_text(out, end, label);
    out = append_hex32(out, end, value);
    finish_log_line(out);
}

static void log_touch_event(const touch_event_t *event, s32 x, s32 y) {
    char *out = g_log + g_log_length;
    char *end = g_log + sizeof(g_log) - 1;

    if (out >= end - 88) {
        return;
    }
    out = append_text(out, end, event->message == BDA_MSG_TOUCH_COORDINATE ?
        "DOWN X=" : "UP X=");
    out = append_u32(out, end, (u32)x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, (u32)y);
    out = append_text(out, end, " RAW=");
    out = append_hex32(out, end, event->lparam);
    finish_log_line(out);
}

static void queue_event(u32 message, u32 wparam, u32 lparam) {
    u32 write = g_queue_write;
    u32 next = (write + 1u) % EVENT_QUEUE_SIZE;

    if (next == g_queue_read) {
        return;
    }
    g_events[write].message = message;
    g_events[write].wparam = wparam;
    g_events[write].lparam = lparam;
    g_queue_write = next;
}

static void drain_events(void) {
    while (g_queue_read != g_queue_write) {
        touch_event_t event = g_events[g_queue_read];
        s32 x;
        s32 y;

        g_queue_read = (g_queue_read + 1u) % EVENT_QUEUE_SIZE;
        g_last_message = event.message;
        if (event.message != BDA_MSG_TOUCH_COORDINATE &&
            event.message != BDA_MSG_TOUCH_RELEASE) {
            continue;
        }
        x = event_x(event.lparam);
        y = event_y(event.lparam);
        if (coordinate_valid(x, y)) {
            log_touch_event(&event, x, y);
            g_touch_x = x;
            g_touch_y = y;
            g_has_coordinate = 1;
#if TOUCH_STAGE_REQUEST_OBJECT_REDRAW
            {
                int redraw_result;

                if (!g_redraw_request_logged) {
                    log_text(
#if TOUCH_STAGE_DIRECT_REDRAW_NOTIFY
                        "BEFORE REDRAW NOTIFY"
#else
                        "BEFORE REDRAW REQUEST"
#endif
                    );
                }
                redraw_result = touch_stage_request_object_redraw();
                if (!g_redraw_request_logged) {
                    log_value(
#if TOUCH_STAGE_DIRECT_REDRAW_NOTIFY
                        "REDRAW NOTIFY="
#else
                        "REDRAW REQUEST="
#endif
                        , (u32)redraw_result
                    );
                    g_redraw_request_logged = 1;
                }
            }
#elif !TOUCH_STAGE_DRAW_IN_WNDPROC
            g_need_draw = 1;
#endif
        }
    }
}

static char *append_coord3(char *out, char *end, s32 value) {
    out = append_char(out, end, (char)('0' + (value / 100) % 10));
    out = append_char(out, end, (char)('0' + (value / 10) % 10));
    return append_char(out, end, (char)('0' + value % 10));
}

static void build_status(char *status) {
    char *out = status;
    char *end = status + 31;

    if (!g_has_coordinate) {
        out = append_text(out, end, "WAITING MESSAGE 1/2");
    } else {
        out = append_text(out, end, "X=");
        out = append_coord3(out, end, g_touch_x);
        out = append_text(out, end, " Y=");
        out = append_coord3(out, end, g_touch_y);
    }
    *out = 0;
}

#if TOUCH_STAGE_VECTOR_DYNAMIC_STATUS
static void draw_cross(s32 x, s32 y, u32 color);

static u8 touch_stage_glyph_row(char value, int row) {
    static const u8 digits[10][7] = {
        {0x0e, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0e},
        {0x04, 0x0c, 0x04, 0x04, 0x04, 0x04, 0x0e},
        {0x0e, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1f},
        {0x1e, 0x01, 0x01, 0x0e, 0x01, 0x01, 0x1e},
        {0x02, 0x06, 0x0a, 0x12, 0x1f, 0x02, 0x02},
        {0x1f, 0x10, 0x10, 0x1e, 0x01, 0x01, 0x1e},
        {0x0e, 0x10, 0x10, 0x1e, 0x11, 0x11, 0x0e},
        {0x1f, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08},
        {0x0e, 0x11, 0x11, 0x0e, 0x11, 0x11, 0x0e},
        {0x0e, 0x11, 0x11, 0x0f, 0x01, 0x01, 0x0e},
    };
    static const u8 glyph_x[7] = {
        0x11, 0x11, 0x0a, 0x04, 0x0a, 0x11, 0x11
    };
    static const u8 glyph_y[7] = {
        0x11, 0x11, 0x0a, 0x04, 0x04, 0x04, 0x04
    };
    static const u8 glyph_equal[7] = {
        0x00, 0x1f, 0x00, 0x1f, 0x00, 0x00, 0x00
    };

    if (value >= '0' && value <= '9') {
        return digits[(int)(value - '0')][row];
    }
    if (value == 'X') {
        return glyph_x[row];
    }
    if (value == 'Y') {
        return glyph_y[row];
    }
    if (value == '=') {
        return glyph_equal[row];
    }
    return 0;
}

static void touch_stage_draw_bitmap_text(
    s32 x, s32 y, const char *text, u32 color
) {
    while (*text) {
        int row;

        for (row = 0; row < 7; ++row) {
            u8 bits = touch_stage_glyph_row(*text, row);
            int column;

            for (column = 0; column < 5; ++column) {
                if (bits & (u8)(0x10u >> column)) {
                    (void)bda_gui_put_pixel(
                        g_draw, x + column, y + row, color
                    );
                }
            }
        }
        x += 6;
        ++text;
    }
}

static void touch_stage_build_coordinate_status(
    char *status, s32 x, s32 y
) {
    char *out = status;
    char *end = status + 15;

    out = append_text(out, end, "X=");
    out = append_coord3(out, end, x);
    out = append_text(out, end, " Y=");
    out = append_coord3(out, end, y);
    *out = 0;
}

static void touch_stage_draw_dynamic_vector_scene(void) {
    char status[16];
    void *old_object;
    u32 background;
    u32 foreground;
    u32 cyan;

    if (!g_draw || !g_draw_object || !g_has_coordinate) {
        return;
    }
    if (!g_vector_draw_logged) {
        log_text("VECTOR DYNAMIC DRAW");
        g_vector_draw_logged = 1;
    }
    background = (u32)bda_gui_rgb(g_draw, 0, 0, 0);
    foreground = (u32)bda_gui_rgb(g_draw, 245, 248, 250);
    cyan = (u32)bda_gui_rgb(g_draw, 35, 210, 225);
    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    if (g_has_painted_cross) {
        draw_cross(g_painted_x, g_painted_y, background);
    }
    if (g_has_painted_status) {
        touch_stage_build_coordinate_status(
            status, g_painted_x, g_painted_y
        );
        touch_stage_draw_bitmap_text(42, 29, status, background);
    }
    touch_stage_build_coordinate_status(status, g_touch_x, g_touch_y);
    touch_stage_draw_bitmap_text(42, 29, status, foreground);
    draw_cross(g_touch_x, g_touch_y, cyan);
    g_painted_x = g_touch_x;
    g_painted_y = g_touch_y;
    g_has_painted_cross = 1;
    g_has_painted_status = 1;
    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
}
#endif

static void draw_cross(s32 x, s32 y, u32 color) {
    int delta;

    for (delta = -10; delta <= 10; ++delta) {
        if (coordinate_valid(x + delta, y)) {
            (void)bda_gui_put_pixel(g_draw, x + delta, y, color);
        }
        if (coordinate_valid(x, y + delta)) {
            (void)bda_gui_put_pixel(g_draw, x, y + delta, color);
        }
    }
}

static void remember_status(const char *status) {
    char *out = g_painted_status;
    char *end = g_painted_status + sizeof(g_painted_status) - 1;

    while (*status && out < end) {
        *out++ = *status++;
    }
    *out = 0;
    g_has_painted_status = 1;
}

static void draw_scene(void) {
    char status[32];
    void *old_object;
    u32 background;
    u32 foreground;
    u32 cyan;
#if TOUCH_STAGE_USE_OBJECT_PAINT
    bda_handle_t base_draw;
    bda_handle_t object_draw;
    int object_draw_active;
#endif
#if TOUCH_STAGE_USE_COMPAT_PAINT
    bda_handle_t visible_draw;
    bda_handle_t compat_draw;
    int compat_draw_active;
    int copy_in_result;
    int copy_out_result;
#endif

    if (!g_draw || !g_draw_object) {
        return;
    }
#if TOUCH_STAGE_VECTOR_DYNAMIC_STATUS
    if (g_initial_scene_drawn && g_has_coordinate) {
        touch_stage_draw_dynamic_vector_scene();
        return;
    }
#endif
#if TOUCH_STAGE_USE_OBJECT_PAINT
    base_draw = g_draw;
    if (!g_object_paint_logged) {
        log_text("BEFORE PAINT BEGIN");
    }
    object_draw = bda_gui_object_draw_begin(g_frame);
    object_draw_active = object_draw && (s32)(u32)object_draw != -1;
    if (!g_object_paint_logged) {
        log_value("PAINT BEGIN=", (u32)object_draw);
    }
    if (object_draw_active) {
        g_draw = object_draw;
    }
#endif
#if TOUCH_STAGE_USE_COMPAT_PAINT
    visible_draw = g_draw;
    if (!g_object_paint_logged) {
        log_text("BEFORE COMPAT CREATE");
    }
    compat_draw = touch_stage_compat_context_create(visible_draw);
    compat_draw_active = compat_draw && (s32)(u32)compat_draw != -1;
    if (!g_object_paint_logged) {
        log_value("COMPAT=", (u32)compat_draw);
    }
    copy_in_result = 0;
    copy_out_result = 0;
    if (compat_draw_active) {
        g_draw = compat_draw;
    }
#endif
    build_status(status);
#if TOUCH_STAGE_COMPAT_WHITE_SURFACE
    background = (u32)bda_gui_rgb(g_draw, 255, 255, 255);
    foreground = (u32)bda_gui_rgb(g_draw, 0, 0, 0);
#else
    background = (u32)bda_gui_rgb(g_draw, 0, 0, 0);
    foreground = (u32)bda_gui_rgb(g_draw, 245, 248, 250);
#endif
    cyan = (u32)bda_gui_rgb(g_draw, 35, 210, 225);
#if TOUCH_STAGE_USE_DRAW_GUARD
    (void)bda_gui_draw_guard_begin();
#endif
#if TOUCH_STAGE_USE_COMPAT_PAINT
    if (compat_draw_active) {
#if TOUCH_STAGE_COMPAT_COPY_IN
        if (!g_object_paint_logged) {
            log_text("BEFORE COPY IN");
        }
#if TOUCH_STAGE_COPY_DESTINATION_FIRST
        copy_in_result = touch_stage_context_copy(
            compat_draw, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT,
            visible_draw, 0, 0, 0
        );
#else
        copy_in_result = touch_stage_context_copy(
            visible_draw, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT,
            compat_draw, 0, 0, 0
        );
#endif
#endif
    }
#endif
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
#if TOUCH_STAGE_SKIP_OLD_ERASE
    if (!compat_draw_active) {
#endif
    if (g_has_painted_cross) {
        draw_cross(g_painted_x, g_painted_y, background);
    }
    if (g_has_painted_status) {
        (void)bda_gui_set_text_mode(g_draw, 1);
        (void)bda_gui_set_text_color(g_draw, background);
        (void)bda_gui_draw_text(g_draw, 42, 29, g_painted_status, -1);
    }
#if TOUCH_STAGE_SKIP_OLD_ERASE
    }
#endif
    bda_gui_rectangle(g_draw, 7, 50, 232, 276);
    (void)bda_gui_set_text_mode(g_draw, 1);
    (void)bda_gui_set_text_color(g_draw, foreground);
    (void)bda_gui_draw_text(g_draw, 42, 6, "TOUCH SCREEN TEST", -1);
#if !TOUCH_STAGE_VECTOR_DYNAMIC_STATUS
    (void)bda_gui_draw_text(g_draw, 42, 29, status, -1);
#endif
    (void)bda_gui_draw_text(g_draw, 82, 303, "ESC EXIT", -1);
    if (g_has_coordinate) {
        draw_cross(g_touch_x, g_touch_y, cyan);
        g_painted_x = g_touch_x;
        g_painted_y = g_touch_y;
        g_has_painted_cross = 1;
    }
#if !TOUCH_STAGE_VECTOR_DYNAMIC_STATUS
    remember_status(status);
#endif
    (void)bda_gui_select_draw_object(g_draw, old_object);
#if TOUCH_STAGE_USE_COMPAT_PAINT
    if (compat_draw_active) {
        if (!g_object_paint_logged) {
            log_text("BEFORE COPY OUT");
        }
#if TOUCH_STAGE_COPY_DESTINATION_FIRST
        copy_out_result = touch_stage_context_copy(
            visible_draw, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT,
            compat_draw, 0, 0, 0
        );
#else
        copy_out_result = touch_stage_context_copy(
            compat_draw, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT,
            visible_draw, 0, 0, 0
        );
#endif
        g_draw = visible_draw;
        if (!g_object_paint_logged) {
            log_text("BEFORE COMPAT FREE");
        }
        touch_stage_compat_context_free(compat_draw);
    }
#endif
#if TOUCH_STAGE_USE_OBJECT_PAINT
    if (object_draw_active) {
        bda_gui_object_draw_end(g_frame, object_draw);
        g_draw = base_draw;
    }
#endif
#if TOUCH_STAGE_PRESENT_AFTER_OBJECT_PAINT
    if (g_initial_scene_drawn) {
        int present_result;

        if (!g_trailing_present_logged) {
            log_text("BEFORE DYNAMIC PRESENT");
        }
        present_result = bda_gui_draw_guard_end();
        if (!g_trailing_present_logged) {
            log_value("DYNAMIC PRESENT=", (u32)present_result);
            g_trailing_present_logged = 1;
        }
    }
#endif
#if TOUCH_STAGE_USE_DRAW_GUARD
    (void)bda_gui_draw_guard_end();
#endif
#if TOUCH_STAGE_USE_OBJECT_PAINT
    if (!g_object_paint_logged) {
#if TOUCH_STAGE_USE_COMPAT_PAINT
        if (compat_draw_active) {
#if TOUCH_STAGE_COMPAT_COPY_IN
            log_value("COPY IN=", (u32)copy_in_result);
#else
            log_text("NO COPY IN");
#endif
#if TOUCH_STAGE_SKIP_OLD_ERASE
            log_text("NO OLD ERASE");
#endif
            log_value("COPY OUT=", (u32)copy_out_result);
            log_text("COMPAT FREED");
        } else {
            log_text("COMPAT FALLBACK");
        }
#endif
        log_text(object_draw_active ? "PAINT END" : "PAINT FALLBACK");
#if !TOUCH_STAGE_USE_DRAW_GUARD
        log_text("NO DRAW GUARD");
#endif
        g_object_paint_logged = 1;
    }
#endif
}

static int touch_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    queue_event(message, wparam, lparam);
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
#if TOUCH_STAGE_COALESCE_STARTUP_REDRAWS
        bda_handle_t previous_draw = g_draw;
#endif
        g_frame = handle;
        g_draw = bda_gui_current_draw(handle);
        if (!g_draw_object) {
            g_draw_object = bda_gui_draw_object_create(7);
        }
#if TOUCH_STAGE_COALESCE_STARTUP_REDRAWS
        if (!g_initial_scene_drawn || g_draw != previous_draw) {
            g_need_draw = 1;
        }
#else
        g_need_draw = 1;
#endif
    } else if (message == BDA_MSG_REDRAW_INPUT) {
#if TOUCH_STAGE_DRAW_IN_WNDPROC
        draw_scene();
        g_need_draw = 0;
#if TOUCH_STAGE_REQUEST_OBJECT_REDRAW
        if (g_has_coordinate) {
            g_redraw_callback_seen = 1;
        }
#endif
#else
#if TOUCH_STAGE_COALESCE_STARTUP_REDRAWS
        if (g_initial_scene_drawn &&
            !g_initial_redraw_suppressed &&
            !g_has_coordinate) {
            g_initial_redraw_suppressed = 1;
        } else {
            g_need_draw = 1;
        }
#else
        g_need_draw = 1;
#endif
#endif
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        g_draw = 0;
        g_exit = 1;
    }
    if (message == BDA_MSG_TOUCH_COORDINATE ||
        message == BDA_MSG_TOUCH_RELEASE) {
#if TOUCH_STAGE_DRAW_IN_WNDPROC && !TOUCH_STAGE_REQUEST_OBJECT_REDRAW
        s32 x = event_x(lparam);
        s32 y = event_y(lparam);

        if (coordinate_valid(x, y)) {
            g_touch_x = x;
            g_touch_y = y;
            g_has_coordinate = 1;
            draw_scene();
            g_need_draw = 0;
        }
#endif
        return 1;
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
    int activate_result;
    int first_loop;
    int close_requested;
    u32 close_wait;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    bda_memset(g_log, 0, sizeof(g_log));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_queue_read = 0;
    g_queue_write = 0;
    g_exit = 0;
    g_need_draw = 1;
    g_log_length = 0;
    g_log_flushed_length = 0;
    g_log_path = 0;
    g_log_append_supported = 0;
    g_last_message = 0;
    g_has_coordinate = 0;
    g_has_painted_cross = 0;
    g_has_painted_status = 0;
    bda_memset(g_painted_status, 0, sizeof(g_painted_status));
#if TOUCH_STAGE_USE_OBJECT_PAINT
    g_object_paint_logged = 0;
#endif
#if TOUCH_STAGE_PRESENT_AFTER_OBJECT_PAINT
    g_trailing_present_logged = 0;
#endif
#if TOUCH_STAGE_VECTOR_DYNAMIC_STATUS
    g_vector_draw_logged = 0;
#endif
#if TOUCH_STAGE_COALESCE_STARTUP_REDRAWS
    g_initial_scene_drawn = 0;
    g_initial_redraw_suppressed = 0;
#endif
#if TOUCH_STAGE_REQUEST_OBJECT_REDRAW
    g_redraw_request_logged = 0;
    g_redraw_callback_seen = 0;
    g_redraw_callback_logged = 0;
#endif
    first_loop = 1;
    close_requested = 0;
    close_wait = 0;
    reset_log_file();
    log_text(TOUCH_STAGE_START_LOG);

    descriptor.style = 0;
    descriptor.title = k_window_title;
    descriptor.wndproc = touch_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = 0;

    log_value("TITLE=", (u32)descriptor.title);
    log_value("STYLE=", descriptor.style);
    log_value("SURFACE=", descriptor.surface);
    log_text("BEFORE REGISTER");

    g_frame = bda_gui_register_frame_desc(&descriptor);
    log_value("REGISTER=", (u32)g_frame);
    if (!g_frame || (s32)g_frame == -1) {
        return 1;
    }
    activate_result = bda_gui_frame_activate(g_frame, 0x100);
    log_value("ACTIVATE=", (u32)activate_result);
    if (!g_draw) {
        g_draw = bda_gui_current_draw(g_frame);
    }
    log_value("DRAW=", (u32)g_draw);
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create(7);
    }
    log_value("OBJECT=", (u32)g_draw_object);
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        return 2;
    }
    log_text("BEFORE DRAW");
    draw_scene();
#if TOUCH_STAGE_COALESCE_STARTUP_REDRAWS
    g_initial_scene_drawn = 1;
    g_need_draw = 0;
#endif
    log_text("DRAW OK");
    log_text("ENTER LOOP");

    for (;;) {
        bda_gui_input_packet_t packet;
        int pump_result;

        pump_result = bda_gui_event_pump_frame_once(&message, g_frame);
        drain_events();
#if TOUCH_STAGE_REQUEST_OBJECT_REDRAW
        if (g_redraw_callback_seen && !g_redraw_callback_logged) {
            log_text("REDRAW CALLBACK");
            g_redraw_callback_logged = 1;
        }
#endif
        if (first_loop) {
            log_text("DRAIN OK");
        }
        if (g_need_draw) {
            g_need_draw = 0;
            draw_scene();
        }
        (void)bda_gui_input_packet(&packet);
        if (first_loop) {
            log_text("KEY POLL OK");
        }
        bda_sys_delay(1);
        if (first_loop) {
            first_loop = 0;
            log_text("LOOP READY");
        }
        if (close_requested) {
            ++close_wait;
            if (!pump_result || g_exit || close_wait >= 128u) {
                log_text(!pump_result ? "LOOP END POLL" :
                    (g_exit ? "LOOP END DETACH" : "LOOP END TIMEOUT"));
                break;
            }
            continue;
        }
        if (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ESCAPE)) {
            int stop_result;
            int release_result;

            log_text("ESC DOWN");
            wait_escape_release();
            log_text("ESC UP");
            stop_result = bda_gui_frame_stop(g_frame);
            log_value("STOP=", (u32)stop_result);
            release_result = bda_gui_frame_release(g_frame);
            log_value("RELEASE=", (u32)release_result);
            close_requested = 1;
        }
    }

    log_text("BEFORE CLOSE");
    bda_gui_close_frame(g_frame);
    g_frame = 0;
    log_text("CLOSE RETURNED");
    return 0;
}
