#ifndef BDA_SDK_H
#define BDA_SDK_H

/*
 * Stable public SDK for the kj409588/C200 firmware.
 *
 * Admission rule: a system API may appear in this header only after an
 * independent BDA has dynamically exercised its exact ABI and produced a
 * reproducible observable result. Static disassembly, an original-app call
 * site, successful compilation, or a non-crashing run is not sufficient.
 * Evidence and usage notes live in docs/verified/. See docs/verified/public_api_policy.md.
 */

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed short s16;
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
#define BDA_MSG_TOUCH_COORDINATE    0x0001u
#define BDA_MSG_TOUCH_RELEASE       0x0002u

#define BDA_MSGBOX_TYPE_OK      0u
#define BDA_MSGBOX_TYPE_YES_NO  2u
#define BDA_DIALOG_RESULT_YES   6
#define BDA_DIALOG_RESULT_NO    7

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

/* Raw RGB565 picture descriptor verified for native-size GUI+0x410 draws. */
typedef struct bda_gui_picture {
    void *pixels;
    u32 width;
    u32 height;
    u32 stride_bytes;
    u8 mode10;
    u8 bits_per_pixel11;
    u8 internal12;
    u8 internal13;
    const void *source_pixels;
    s32 selected_index;
} bda_gui_picture_t;

#define BDA_FS_FIND_DATA_SIZE 0x220u

#define BDA_FILE_SELECTOR_PATH_SIZE            0x12du
#define BDA_FILE_SELECTOR_DIRECTORY_STATE_SIZE 0x12du
#define BDA_FILE_SELECTOR_ERROR                (-1)
#define BDA_FILE_SELECTOR_CANCELLED             0
#define BDA_FILE_SELECTOR_SELECTED              1

typedef struct bda_fs_find_data {
    void *cursor;
    u32 size_or_aux;
    u32 attr_or_flags;
    u16 time;
    u16 date;
    s16 volume_index;
    char name_or_path[0x20a];
    u32 aux;
} bda_fs_find_data_t;

/*
 * Storage owned by the caller for one modal file-selector invocation. The
 * selected absolute path remains available in path after the function returns.
 */
typedef struct bda_file_selector {
    char path[BDA_FILE_SELECTOR_PATH_SIZE];
    u8 directory_state[BDA_FILE_SELECTOR_DIRECTORY_STATE_SIZE];
} bda_file_selector_t;

/* Private implementation details. Applications must use the wrappers below. */
typedef struct bda_sdk_internal_file_selector_desc {
    char *path;
    const char *extensions;
    void *directory_state;
    const char *title;
    void *list_head;
    u32 internal14;
    s32 status;
    s32 selected_index;
    s32 sentinel20;
    s32 sentinel24;
    u32 internal28;
    u32 internal2c;
    u32 flags;
    s32 sentinel34;
    s32 sentinel38;
    u32 internal3c;
    u32 list_limit40;
    u32 internal44;
    s32 sentinel48;
    u32 internal4c;
    u32 internal50;
    u32 internal54;
    u32 internal58;
    u32 internal5c;
    u32 internal60;
    u32 result64;
} bda_sdk_internal_file_selector_desc_t;

#define BDA_SDK_INTERNAL_GUI_TABLE_ADDR 0x81c00004u
#define BDA_SDK_INTERNAL_FS_TABLE_ADDR  0x81c00008u
#define BDA_SDK_INTERNAL_SYS_TABLE_ADDR 0x81c0000cu
#define BDA_SDK_INTERNAL_MEM_TABLE_ADDR 0x81c00010u

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
#define BDA_SDK_INTERNAL_GUI_OBJECT_DRAW_BEGIN 0x0e4u
#define BDA_SDK_INTERNAL_GUI_OBJECT_DRAW_END   0x0e8u
#define BDA_SDK_INTERNAL_GUI_CLOSE_FRAME       0x17cu
#define BDA_SDK_INTERNAL_GUI_DRAW_OBJECT       0x2fcu
#define BDA_SDK_INTERNAL_GUI_CURRENT_DRAW      0x304u
#define BDA_SDK_INTERNAL_GUI_END_DRAW          0x30cu
#define BDA_SDK_INTERNAL_GUI_COMPAT_CREATE     0x310u
#define BDA_SDK_INTERNAL_GUI_COMPAT_FREE       0x314u
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
#define BDA_SDK_INTERNAL_GUI_RENDER_PICTURE    0x410u
#define BDA_SDK_INTERNAL_GUI_CONTEXT_COPY      0x418u
#define BDA_SDK_INTERNAL_GUI_DRAW_TEXT         0x4f0u
#define BDA_SDK_INTERNAL_GUI_DRAW_VX           0x540u
#define BDA_SDK_INTERNAL_GUI_INPUT_PACKET      0x5d4u
#define BDA_SDK_INTERNAL_GUI_FILE_SELECTOR_OPEN 0x6a8u
#define BDA_SDK_INTERNAL_GUI_LIST_NTH           0x6b8u
#define BDA_SDK_INTERNAL_GUI_LIST_FREE          0x6bcu
#define BDA_SDK_INTERNAL_GUI_FILE_SELECTOR_RUN  0x6c8u
#define BDA_SDK_INTERNAL_GUI_TICK_COUNT_25MS   0x6d8u

#define BDA_GUI_COLOR_KEY_NONE 0u
#define BDA_GUI_COLOR_KEY_MAGENTA_RGB565 0xf81fu

#define BDA_SDK_INTERNAL_FS_OPEN       0x000u
#define BDA_SDK_INTERNAL_FS_CLOSE      0x004u
#define BDA_SDK_INTERNAL_FS_READ       0x008u
#define BDA_SDK_INTERNAL_FS_WRITE      0x00cu
#define BDA_SDK_INTERNAL_FS_SEEK       0x010u
#define BDA_SDK_INTERNAL_FS_TELL       0x014u
#define BDA_SDK_INTERNAL_FS_ERROR      0x01cu
#define BDA_SDK_INTERNAL_FS_CHDIR      0x02cu
#define BDA_SDK_INTERNAL_FS_MKDIR      0x030u
#define BDA_SDK_INTERNAL_FS_FINDFIRST  0x03cu
#define BDA_SDK_INTERNAL_FS_FINDNEXT   0x040u
#define BDA_SDK_INTERNAL_FS_FINDCLOSE  0x044u

#define BDA_SDK_INTERNAL_MEM_ALLOC 0x008u
#define BDA_SDK_INTERNAL_MEM_FREE  0x00cu

#define BDA_SEEK_SET 0
#define BDA_SEEK_CUR 1
#define BDA_SEEK_END 2

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

static inline void *bda_sdk_internal_mem(void) {
    return bda_sdk_internal_table(BDA_SDK_INTERNAL_MEM_TABLE_ADDR);
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

/* Freestanding helper; this does not call a firmware API. */
static inline void *bda_memcpy(
    void *destination, const void *source, bda_size_t size
) {
    u8 *out = (u8 *)destination;
    const u8 *in = (const u8 *)source;
    while (size-- != 0u) {
        *out++ = *in++;
    }
    return destination;
}

static inline int bda_sdk_internal_copy_string(
    char *destination, bda_size_t capacity, const char *source
) {
    bda_size_t index;
    if (destination == 0 || capacity == 0u || source == 0) {
        return 0;
    }
    for (index = 0u; index < capacity; ++index) {
        destination[index] = source[index];
        if (source[index] == '\0') {
            return 1;
        }
    }
    destination[0] = '\0';
    return 0;
}

static inline int bda_sdk_internal_join_path(
    char *directory, bda_size_t capacity, const char *name
) {
    bda_size_t length = 0u;
    if (directory == 0 || capacity == 0u || name == 0 || name[0] == '\0') {
        return 0;
    }
    if (name[0] == '\\' || name[0] == '/' || name[1] == ':') {
        return bda_sdk_internal_copy_string(directory, capacity, name);
    }
    while (length < capacity && directory[length] != '\0') {
        ++length;
    }
    if (length == capacity) {
        directory[0] = '\0';
        return 0;
    }
    if (length != 0u && directory[length - 1u] != '\\' &&
        directory[length - 1u] != '/') {
        if (length + 1u >= capacity) {
            directory[0] = '\0';
            return 0;
        }
        directory[length++] = '\\';
        directory[length] = '\0';
    }
    return bda_sdk_internal_copy_string(
        directory + length, capacity - length, name
    );
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
    return bda_msgbox_ex(0, title, message, BDA_MSGBOX_TYPE_OK);
}

static inline int bda_confirm(const char *title, const char *message) {
    return bda_msgbox_ex(0, title, message, BDA_MSGBOX_TYPE_YES_NO);
}

/* Basic heap allocation: MEM+0x008/+0x00c. */
static inline void *bda_alloc(bda_size_t size) {
    typedef void *(*fn_t)(bda_size_t);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_mem(), BDA_SDK_INTERNAL_MEM_ALLOC
    );
    return fn(size);
}

static inline void bda_free(void *pointer) {
    typedef void (*fn_t)(void *);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_mem(), BDA_SDK_INTERNAL_MEM_FREE
    );
    fn(pointer);
}

/* File API backed by the verified FS table entries below. */
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

/* Successful seek returns the updated absolute file position. */
static inline int bda_fs_seek_raw(int file, s32 offset, int whence) {
    typedef int (*fn_t)(int, s32, int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_SEEK
    );
    return fn(file, offset, whence);
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

/* Directory API: FS+0x02c/+0x030/+0x03c/+0x040/+0x044. */
static inline int bda_fs_chdir(const char *path) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_CHDIR, (u32)path
    );
}

static inline int bda_fs_mkdir(const char *path) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_MKDIR, (u32)path
    );
}

static inline void bda_fs_find_data_init(bda_fs_find_data_t *find_data) {
    (void)bda_memset(find_data, 0, sizeof(*find_data));
}

static inline int bda_fs_findfirst(
    const char *pattern, u32 attr, bda_fs_find_data_t *find_data
) {
    return bda_sdk_internal_call3(
        bda_sdk_internal_fs(),
        BDA_SDK_INTERNAL_FS_FINDFIRST,
        (u32)pattern,
        attr,
        (u32)find_data
    );
}

static inline int bda_fs_findnext(bda_fs_find_data_t *find_data) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_FINDNEXT, (u32)find_data
    );
}

static inline int bda_fs_findclose(bda_fs_find_data_t *find_data) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_FINDCLOSE, (u32)find_data
    );
}

/*
 * Run the firmware's modal file selector.
 *
 * default_path is normally an absolute directory ending in '\\', for example
 * "A:\\gameboy\\". extensions is a semicolon-separated list without dots,
 * for example "gb;gbc". The selected absolute path is copied into selector.
 */
static inline int bda_gui_select_file(
    bda_file_selector_t *selector,
    const char *default_path,
    const char *extensions,
    const char *title
) {
    bda_sdk_internal_file_selector_desc_t descriptor;
    void *selected_node;
    const char *selected_path;
    int result = BDA_FILE_SELECTOR_CANCELLED;

    if (selector == 0 || extensions == 0 || extensions[0] == '\0' ||
        title == 0 || !bda_sdk_internal_copy_string(
            selector->path, BDA_FILE_SELECTOR_PATH_SIZE, default_path
        )) {
        return BDA_FILE_SELECTOR_ERROR;
    }

    (void)bda_memset(
        selector->directory_state, 0, sizeof(selector->directory_state)
    );
    (void)bda_memset(&descriptor, 0, sizeof(descriptor));
    descriptor.path = selector->path;
    descriptor.extensions = extensions;
    descriptor.directory_state = selector->directory_state;
    descriptor.title = title;
    descriptor.selected_index = -1;
    descriptor.sentinel20 = -1;
    descriptor.sentinel24 = -1;
    descriptor.sentinel34 = -1;
    descriptor.sentinel38 = -1;
    descriptor.list_limit40 = 0x1000u;
    descriptor.sentinel48 = -1;

    if (!bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_FILE_SELECTOR_OPEN, 1u
    )) {
        selector->path[0] = '\0';
        return BDA_FILE_SELECTOR_CANCELLED;
    }

    (void)bda_sdk_internal_call1(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_FILE_SELECTOR_RUN,
        (u32)&descriptor
    );

    if (descriptor.status != 0 && descriptor.status != -1 &&
        descriptor.list_head != 0 && descriptor.selected_index >= 0) {
        selected_node = (void *)bda_sdk_internal_call2(
            bda_sdk_internal_gui(),
            BDA_SDK_INTERNAL_GUI_LIST_NTH,
            (u32)descriptor.list_head,
            (u32)descriptor.selected_index
        );
        if (selected_node != 0) {
            selected_path = *(const char **)selected_node;
            if (bda_sdk_internal_join_path(
                selector->path, BDA_FILE_SELECTOR_PATH_SIZE, selected_path
            )) {
                result = BDA_FILE_SELECTOR_SELECTED;
            } else {
                result = BDA_FILE_SELECTOR_ERROR;
            }
        } else {
            result = BDA_FILE_SELECTOR_ERROR;
        }
    } else {
        selector->path[0] = '\0';
    }

    if (descriptor.list_head != 0) {
        (void)bda_sdk_internal_call1(
            bda_sdk_internal_gui(),
            BDA_SDK_INTERNAL_GUI_LIST_FREE,
            (u32)descriptor.list_head
        );
    }
    return result;
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

/* Monotonic firmware tick. One unsigned tick is 25 ms on kj409588/C200. */
static inline u32 bda_gui_tick_count_25ms(void) {
    typedef u32 (*fn_t)(void);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_TICK_COUNT_25MS
    );
    return fn();
}

/* Unsigned subtraction remains correct across one u32 counter wrap. */
static inline u32 bda_gui_tick_elapsed_25ms(u32 start, u32 end) {
    return end - start;
}

static inline u32 bda_gui_tick_elapsed_ms(u32 start, u32 end) {
    return bda_gui_tick_elapsed_25ms(start, end) * 25u;
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

/* Verified frame lifecycle and event pump; full hardware path is in the V11 doc. */
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

/*
 * Verified object paint scope. The begin result must be returned to end with
 * the same object. This scope shares the visible backend and is not a buffer.
 */
static inline bda_handle_t bda_gui_object_draw_begin(bda_handle_t object) {
    return (bda_handle_t)bda_sdk_internal_call1(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_OBJECT_DRAW_BEGIN,
        (u32)object
    );
}

static inline void bda_gui_object_draw_end(
    bda_handle_t object, bda_handle_t draw
) {
    (void)bda_sdk_internal_call2(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_OBJECT_DRAW_END,
        (u32)object,
        (u32)draw
    );
}

/*
 * Final owner-side teardown after stop/release has made the event pump end.
 * GUI+0x17c has no stable return value, so the public wrapper is void.
 */
static inline void bda_gui_close_frame(bda_handle_t handle) {
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_CLOSE_FRAME, (u32)handle
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

/*
 * Verified dynamic draw guard. Use begin -> draw -> end as one complete pair
 * on an active frame. TouchStageV22 proved that end alone is not a present API.
 */
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

/* GUI+0x2fc is a kind-indexed firmware object-table lookup, not a heap alloc. */
static inline void *bda_gui_draw_object_create(u32 kind) {
    return (void *)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_DRAW_OBJECT, kind
    );
}

static inline bda_handle_t bda_gui_current_draw(bda_handle_t handle) {
    return (bda_handle_t)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_CURRENT_DRAW, (u32)handle
    );
}

/*
 * Release one fixed draw slot returned by bda_gui_current_draw(). Call this
 * exactly once on detach or before discarding the context handle. The target
 * firmware has only five ordinary slots and does not handle exhaustion safely.
 */
static inline void bda_gui_end_draw(bda_handle_t draw_context) {
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_END_DRAW, (u32)draw_context
    );
}

/*
 * Create an off-screen context compatible with an active visible draw context.
 * The returned context owns firmware resources and must be released exactly
 * once with bda_gui_compatible_context_free().
 */
static inline bda_handle_t bda_gui_compatible_context_create(
    bda_handle_t source_context
) {
    return (bda_handle_t)bda_sdk_internal_call1(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_COMPAT_CREATE,
        (u32)source_context
    );
}

static inline void bda_gui_compatible_context_free(bda_handle_t context) {
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_COMPAT_FREE, (u32)context
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

/*
 * Draw one complete RGB565 VX resource block at its native dimensions.
 * Width and height are read from the VX header; this API does not scale.
 */
static inline int bda_gui_draw_vx(
    bda_handle_t context, s32 x, s32 y, const void *vx_resource
) {
    return bda_sdk_internal_call6(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_DRAW_VX,
        (u32)context,
        (u32)x,
        (u32)y,
        0u,
        0u,
        (u32)vx_resource
    );
}

/*
 * Submit a zero-initialized raw RGB565 descriptor at its native dimensions.
 * Set width, height, source_pixels and selected_index=-1. The verified path
 * requires destination width/height to equal the descriptor dimensions.
 */
static inline int bda_gui_render_picture(
    bda_handle_t context,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    const bda_gui_picture_t *picture
) {
    return bda_sdk_internal_call6(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_RENDER_PICTURE,
        (u32)context,
        (u32)x,
        (u32)y,
        (u32)width,
        (u32)height,
        (u32)picture
    );
}

/*
 * Copy a source rectangle to a visible or compatible destination context.
 * Presenting to the visible context must be enclosed by one complete dynamic
 * draw guard. Use BDA_GUI_COLOR_KEY_NONE for an opaque copy.
 */
static inline int bda_gui_context_copy(
    bda_handle_t source_context,
    s32 source_x,
    s32 source_y,
    s32 width,
    s32 height,
    bda_handle_t destination_context,
    s32 destination_x,
    s32 destination_y,
    u32 color_key_rgb565
) {
    typedef int (*fn_t)(u32, u32, u32, u32, u32, u32, u32, u32, u32);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_CONTEXT_COPY
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
        color_key_rgb565
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
