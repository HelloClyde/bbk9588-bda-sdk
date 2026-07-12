#ifndef BDA_SDK_H
#define BDA_SDK_H

/*
 * Stable public SDK for the kj409588/C200 firmware.
 *
 * Admission rule: a system API may appear in this header only after an
 * independent BDA has dynamically exercised its exact ABI and produced a
 * reproducible observable result. Static disassembly, an original-app call
 * site, successful compilation, or a non-crashing run is not sufficient.
 * Evidence and usage notes live in sdk/doc/verified/. See sdk/include/README.md.
 */

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;
typedef unsigned int bda_size_t;
typedef void *bda_handle_t;
typedef int (*bda_wndproc_t)(bda_handle_t, u32, u32, u32);

#define BDA_GUI_MESSAGE_SIZE 0x1cu
#define BDA_GUI_INPUT_PACKET_SIZE 6u

#define BDA_KEY_ESCAPE 0x01u
#define BDA_KEY_ENTER  0x1cu
#define BDA_KEY_UP     0x67u
#define BDA_KEY_LEFT   0x69u
#define BDA_KEY_RIGHT  0x6au
#define BDA_KEY_DOWN   0x6cu

#define BDA_INPUT_PACKET_RIGHT_INDEX  0u
#define BDA_INPUT_PACKET_LEFT_INDEX   1u
#define BDA_INPUT_PACKET_DOWN_INDEX   2u
#define BDA_INPUT_PACKET_UP_INDEX     3u
#define BDA_INPUT_PACKET_ESCAPE_INDEX 4u
#define BDA_INPUT_PACKET_ENTER_INDEX  5u

#define BDA_MSG_DRAW_CONTEXT_ATTACH 0x0060u
#define BDA_MSG_DRAW_CONTEXT_DETACH 0x0066u
#define BDA_MSG_REDRAW_INPUT        0x00b1u

typedef struct bda_frame_desc {
    u32 style;
    u32 internal28;
    const char *title;
    u32 internal44;
    u32 internal48;
    u32 helper_arg14;
    bda_wndproc_t wndproc;
    s32 x;
    s32 y;
    s32 height;
    s32 width;
    u32 surface;
    u32 aux30;
} bda_frame_desc_t;

typedef struct bda_gui_message {
    bda_handle_t handle;
    u32 message;
    u32 wparam;
    u32 lparam;
    u32 aux10;
    u32 aux14;
    u32 aux18;
} bda_gui_message_t;

typedef struct bda_gui_input_packet {
    u8 bytes[BDA_GUI_INPUT_PACKET_SIZE];
} bda_gui_input_packet_t;

/* Private implementation details. Applications must use the wrappers below. */
#define BDA_SDK_INTERNAL_GUI_TABLE_ADDR 0x81c00004u
#define BDA_SDK_INTERNAL_FS_TABLE_ADDR  0x81c00008u
#define BDA_SDK_INTERNAL_SYS_TABLE_ADDR 0x81c0000cu

#define BDA_SDK_INTERNAL_GUI_MSGBOX            0x2b8u
#define BDA_SDK_INTERNAL_GUI_EVENT_POLL        0x030u
#define BDA_SDK_INTERNAL_GUI_FRAME_RELEASE     0x04cu
#define BDA_SDK_INTERNAL_GUI_EVENT_STEP        0x050u
#define BDA_SDK_INTERNAL_GUI_EVENT_DISPATCH    0x054u
#define BDA_SDK_INTERNAL_GUI_DRAW_GUARD        0x074u
#define BDA_SDK_INTERNAL_GUI_REGISTER_FRAME    0x084u
#define BDA_SDK_INTERNAL_GUI_FRAME_STOP        0x088u
#define BDA_SDK_INTERNAL_GUI_DEFAULT_PROC      0x08cu
#define BDA_SDK_INTERNAL_GUI_FRAME_ACTIVATE    0x098u
#define BDA_SDK_INTERNAL_GUI_DRAW_OBJECT       0x2fcu
#define BDA_SDK_INTERNAL_GUI_CURRENT_DRAW      0x304u
#define BDA_SDK_INTERNAL_GUI_SET_TEXT_MODE     0x338u
#define BDA_SDK_INTERNAL_GUI_SET_TEXT_COLOR    0x33cu
#define BDA_SDK_INTERNAL_GUI_SELECT_DRAW       0x358u
#define BDA_SDK_INTERNAL_GUI_PUT_PIXEL         0x368u
#define BDA_SDK_INTERNAL_GUI_PUT_PIXEL_RGB     0x36cu
#define BDA_SDK_INTERNAL_GUI_RGB               0x378u
#define BDA_SDK_INTERNAL_GUI_LINE_TO           0x37cu
#define BDA_SDK_INTERNAL_GUI_MOVE_TO           0x380u
#define BDA_SDK_INTERNAL_GUI_CIRCLE            0x388u
#define BDA_SDK_INTERNAL_GUI_RECTANGLE         0x38cu
#define BDA_SDK_INTERNAL_GUI_DRAW_TEXT         0x4f0u
#define BDA_SDK_INTERNAL_GUI_INPUT_PACKET      0x5d4u

#define BDA_SDK_INTERNAL_FS_OPEN  0x000u
#define BDA_SDK_INTERNAL_FS_CLOSE 0x004u
#define BDA_SDK_INTERNAL_FS_READ  0x008u
#define BDA_SDK_INTERNAL_FS_WRITE 0x00cu
#define BDA_SDK_INTERNAL_FS_TELL  0x014u
#define BDA_SDK_INTERNAL_FS_ERROR 0x01cu

#define BDA_SDK_INTERNAL_SYS_DELAY 0x080u

static inline void *bda_sdk_internal_table(u32 address) {
    return *(void **)address;
}

static inline void *bda_sdk_internal_api(void *table, u32 offset) {
    return *(void **)((u8 *)table + offset);
}

static inline void *bda_sdk_internal_gui(void) {
    return bda_sdk_internal_table(BDA_SDK_INTERNAL_GUI_TABLE_ADDR);
}

static inline void *bda_sdk_internal_fs(void) {
    return bda_sdk_internal_table(BDA_SDK_INTERNAL_FS_TABLE_ADDR);
}

static inline void *bda_sdk_internal_sys(void) {
    return bda_sdk_internal_table(BDA_SDK_INTERNAL_SYS_TABLE_ADDR);
}

static inline int bda_sdk_internal_call1(void *table, u32 offset, u32 a0) {
    typedef int (*fn_t)(u32);
    return ((fn_t)bda_sdk_internal_api(table, offset))(a0);
}

static inline int bda_sdk_internal_call2(void *table, u32 offset, u32 a0, u32 a1) {
    typedef int (*fn_t)(u32, u32);
    return ((fn_t)bda_sdk_internal_api(table, offset))(a0, a1);
}

static inline int bda_sdk_internal_call3(
    void *table, u32 offset, u32 a0, u32 a1, u32 a2
) {
    typedef int (*fn_t)(u32, u32, u32);
    return ((fn_t)bda_sdk_internal_api(table, offset))(a0, a1, a2);
}

static inline int bda_sdk_internal_call4(
    void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3
) {
    typedef int (*fn_t)(u32, u32, u32, u32);
    return ((fn_t)bda_sdk_internal_api(table, offset))(a0, a1, a2, a3);
}

static inline int bda_sdk_internal_call5(
    void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3, u32 a4
) {
    typedef int (*fn_t)(u32, u32, u32, u32, u32);
    return ((fn_t)bda_sdk_internal_api(table, offset))(a0, a1, a2, a3, a4);
}

static inline int bda_sdk_internal_call6(
    void *table,
    u32 offset,
    u32 a0,
    u32 a1,
    u32 a2,
    u32 a3,
    u32 a4,
    u32 a5
) {
    typedef int (*fn_t)(u32, u32, u32, u32, u32, u32);
    return ((fn_t)bda_sdk_internal_api(table, offset))(a0, a1, a2, a3, a4, a5);
}

/* Freestanding helper; this does not call a firmware API. */
static inline void *bda_memset(void *destination, int value, bda_size_t size) {
    u8 *out = (u8 *)destination;
    while (size-- != 0u) {
        *out++ = (u8)value;
    }
    return destination;
}

/* Message box: GUI+0x2b8. */
static inline int bda_msgbox_ex(
    void *parent, const char *title, const char *message, u32 flags
) {
    typedef int (*fn_t)(void *, const char *, const char *, u32);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_MSGBOX
    );
    return fn(parent, message, title, flags);
}

static inline int bda_msgbox(const char *title, const char *message) {
    return bda_msgbox_ex(0, title, message, 0);
}

/* File API: FS+0x000/+0x004/+0x008/+0x00c/+0x014/+0x01c. */
static inline int bda_fs_fopen_raw(const char *path, const char *mode) {
    typedef int (*fn_t)(const char *, const char *);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_OPEN
    );
    return fn(path, mode);
}

static inline int bda_fs_file_is_valid(int file) {
    return file != 0 && (u32)file != 0xffffffffu;
}

static inline int bda_fs_close_raw(int file) {
    typedef int (*fn_t)(int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_CLOSE
    );
    return fn(file);
}

static inline int bda_fs_fread_raw(
    void *buffer, bda_size_t size, bda_size_t count, int file
) {
    typedef int (*fn_t)(void *, bda_size_t, bda_size_t, int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_READ
    );
    return fn(buffer, size, count, file);
}

static inline int bda_fs_read_raw(int file, void *buffer, bda_size_t size) {
    return bda_fs_fread_raw(buffer, 1u, size, file);
}

static inline int bda_fs_fwrite_raw(
    const void *buffer, bda_size_t size, bda_size_t count, int file
) {
    typedef int (*fn_t)(const void *, bda_size_t, bda_size_t, int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_WRITE
    );
    return fn(buffer, size, count, file);
}

static inline int bda_fs_write_raw(
    int file, const void *buffer, bda_size_t size
) {
    return bda_fs_fwrite_raw(buffer, 1u, size, file);
}

static inline int bda_fs_tell_raw(int file) {
    typedef int (*fn_t)(int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_TELL
    );
    return fn(file);
}

static inline int bda_fs_error(int file) {
    typedef int (*fn_t)(int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_ERROR
    );
    return fn(file);
}

/* Physical-key packet: GUI+0x5d4. */
static inline int bda_gui_input_packet(
    bda_gui_input_packet_t *packet
) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_INPUT_PACKET,
        (u32)packet
    );
}

static inline int bda_gui_input_packet_key_pressed(
    const bda_gui_input_packet_t *packet,
    u32 keycode
) {
    u32 index;
    switch (keycode) {
        case BDA_KEY_RIGHT: index = BDA_INPUT_PACKET_RIGHT_INDEX; break;
        case BDA_KEY_LEFT: index = BDA_INPUT_PACKET_LEFT_INDEX; break;
        case BDA_KEY_DOWN: index = BDA_INPUT_PACKET_DOWN_INDEX; break;
        case BDA_KEY_UP: index = BDA_INPUT_PACKET_UP_INDEX; break;
        case BDA_KEY_ESCAPE: index = BDA_INPUT_PACKET_ESCAPE_INDEX; break;
        case BDA_KEY_ENTER: index = BDA_INPUT_PACKET_ENTER_INDEX; break;
        default: return 0;
    }
    return packet->bytes[index] == 1u;
}

static inline int bda_gui_key_pressed(u32 keycode) {
    bda_gui_input_packet_t packet;
    (void)bda_gui_input_packet(&packet);
    return bda_gui_input_packet_key_pressed(&packet, keycode);
}

/* Firmware-bound touch level query dynamically verified on kj409588/C200. */
static inline int bda_touch_pressed_9588(void) {
    typedef int (*fn_t)(void);
    return ((fn_t)0x80059f68u)();
}

/* Busy-wait delay exercised by the verified input, touch and graphics BDAs. */
static inline void bda_sys_delay(u32 delay_units) {
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_sys(), BDA_SDK_INTERNAL_SYS_DELAY, delay_units
    );
}

/* Verified frame lifecycle and event pump used by the graphics BDA. */
static inline bda_handle_t bda_gui_register_frame_desc(
    bda_frame_desc_t *descriptor
) {
    return (bda_handle_t)bda_sdk_internal_call1(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_REGISTER_FRAME,
        (u32)descriptor
    );
}

static inline int bda_gui_frame_activate(bda_handle_t handle, u32 mode) {
    return bda_sdk_internal_call2(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_FRAME_ACTIVATE,
        (u32)handle,
        mode
    );
}

static inline int bda_gui_frame_stop(bda_handle_t handle) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_FRAME_STOP, (u32)handle
    );
}

static inline int bda_gui_frame_release(bda_handle_t handle) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_FRAME_RELEASE, (u32)handle
    );
}

static inline int bda_gui_default_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
) {
    return bda_sdk_internal_call4(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_DEFAULT_PROC,
        (u32)handle,
        message,
        wparam,
        lparam
    );
}

static inline int bda_gui_event_pump_frame_once(
    bda_gui_message_t *message,
    bda_handle_t frame
) {
    int present = bda_sdk_internal_call2(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_EVENT_POLL,
        (u32)message,
        (u32)frame
    );
    if (!present) {
        return 0;
    }
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_EVENT_STEP, (u32)message
    );
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_EVENT_DISPATCH,
        (u32)message
    );
    return 1;
}

/* Verified graphics primitives. A registered and active frame is required. */
static inline int bda_gui_draw_guard_begin(void) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_DRAW_GUARD, 1u
    );
}

static inline int bda_gui_draw_guard_end(void) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_DRAW_GUARD, 0u
    );
}

static inline void *bda_gui_draw_object_create(u32 kind) {
    return (void *)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_DRAW_OBJECT, kind
    );
}

static inline void *bda_gui_frame_surface(u32 kind) {
    return bda_gui_draw_object_create(kind);
}

static inline bda_handle_t bda_gui_current_draw(bda_handle_t handle) {
    return (bda_handle_t)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_CURRENT_DRAW, (u32)handle
    );
}

static inline void *bda_gui_select_draw_object(
    bda_handle_t context, void *object
) {
    return (void *)bda_sdk_internal_call2(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_SELECT_DRAW,
        (u32)context,
        (u32)object
    );
}

static inline int bda_gui_rgb(
    bda_handle_t context, u32 red, u32 green, u32 blue
) {
    return bda_sdk_internal_call4(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_RGB,
        (u32)context,
        red,
        green,
        blue
    );
}

static inline int bda_gui_put_pixel(
    bda_handle_t context, s32 x, s32 y, u32 color
) {
    return bda_sdk_internal_call4(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_PUT_PIXEL,
        (u32)context,
        (u32)x,
        (u32)y,
        color
    );
}

static inline int bda_gui_put_pixel_rgb(
    bda_handle_t context,
    s32 x,
    s32 y,
    u32 red,
    u32 green,
    u32 blue
) {
    return bda_sdk_internal_call6(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_PUT_PIXEL_RGB,
        (u32)context,
        (u32)x,
        (u32)y,
        red,
        green,
        blue
    );
}

static inline void bda_gui_move_to(
    bda_handle_t context, s32 x, s32 y
) {
    (void)bda_sdk_internal_call3(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_MOVE_TO,
        (u32)context,
        (u32)x,
        (u32)y
    );
}

static inline void bda_gui_line_to(
    bda_handle_t context, s32 x, s32 y
) {
    (void)bda_sdk_internal_call3(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_LINE_TO,
        (u32)context,
        (u32)x,
        (u32)y
    );
}

static inline void bda_gui_circle(
    bda_handle_t context, s32 x, s32 y, s32 radius
) {
    (void)bda_sdk_internal_call4(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_CIRCLE,
        (u32)context,
        (u32)x,
        (u32)y,
        (u32)radius
    );
}

static inline void bda_gui_rectangle(
    bda_handle_t context, s32 left, s32 top, s32 right, s32 bottom
) {
    (void)bda_sdk_internal_call5(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_RECTANGLE,
        (u32)context,
        (u32)left,
        (u32)top,
        (u32)right,
        (u32)bottom
    );
}

static inline int bda_gui_set_text_mode(
    bda_handle_t context, u32 mode
) {
    return bda_sdk_internal_call2(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_SET_TEXT_MODE,
        (u32)context,
        mode
    );
}

static inline int bda_gui_set_text_color(
    bda_handle_t context, u32 color
) {
    return bda_sdk_internal_call2(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_SET_TEXT_COLOR,
        (u32)context,
        color
    );
}

static inline int bda_gui_draw_text(
    bda_handle_t context, s32 x, s32 y, const char *text, s32 extra
) {
    return bda_sdk_internal_call5(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_DRAW_TEXT,
        (u32)context,
        (u32)x,
        (u32)y,
        (u32)text,
        (u32)extra
    );
}

#endif
