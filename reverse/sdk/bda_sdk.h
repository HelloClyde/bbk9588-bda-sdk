#ifndef BDA_SDK_H
#define BDA_SDK_H

typedef unsigned int u32;
typedef int s32;
typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int bda_size_t;

#define BDA_GUI_TABLE_ADDR 0x81c00004u
#define BDA_FS_TABLE_ADDR 0x81c00008u
#define BDA_SYS_TABLE_ADDR 0x81c0000cu
#define BDA_MEM_TABLE_ADDR 0x81c00010u
#define BDA_RES_TABLE_ADDR 0x81c00014u

#define BDA_RUNTIME_BASE 0x81c00000u

#define BDA_GUI_MSGBOX 0x2b8u
#define BDA_GUI_CREATE 0x1a4u
#define BDA_GUI_SEND   0x040u
#define BDA_GUI_NOTIFY_LIKE 0x03cu
#define BDA_GUI_PUMP_PRESENT_LIKE 0x074u
#define BDA_GUI_REGISTER_FRAME_LIKE 0x084u
#define BDA_GUI_FRAME_STOP_LIKE     0x088u
#define BDA_GUI_DEFAULT_PROC_LIKE   0x08cu
#define BDA_GUI_FRAME_ACTIVATE_LIKE 0x098u
#define BDA_GUI_EVENT_POLL_LIKE     0x030u
#define BDA_GUI_EVENT_STEP_LIKE     0x050u
#define BDA_GUI_EVENT_DISPATCH_LIKE 0x054u
#define BDA_GUI_FRAME_RELEASE_LIKE  0x04cu
#define BDA_GUI_CLOSE_FRAME_LIKE    0x17cu
#define BDA_GUI_DESTROY_LIKE 0x1a8u
#define BDA_GUI_OBJECT_OP_LIKE 0x0e0u
#define BDA_GUI_DRAW_OBJECT_CREATE_LIKE 0x2fcu
#define BDA_GUI_CURRENT_DRAW_LIKE    0x304u
#define BDA_GUI_BEGIN_DRAW_LIKE      0x308u
#define BDA_GUI_END_DRAW_LIKE        0x30cu
#define BDA_GUI_SET_TEXT_MODE_LIKE  0x338u
#define BDA_GUI_SET_TEXT_COLOR_LIKE 0x33cu
#define BDA_GUI_OBJECT_BIND_LIKE    0x35cu
#define BDA_GUI_PUT_PIXEL_LIKE      0x368u
#define BDA_GUI_RGB_LIKE            0x378u
#define BDA_GUI_DRAW_VX_LIKE        0x540u
#define BDA_GUI_REGION_DRAW_LIKE    0x40cu
#define BDA_GUI_RENDER_HELPER_LIKE  0x414u
#define BDA_GUI_RENDER_FINISH_LIKE  0x418u
#define BDA_GUI_DRAW_TEXT_LIKE      0x4f0u
#define BDA_GUI_DECODE_BMP_LIKE     0x670u
#define BDA_GUI_DECODE_JPEG_LIKE    0x808u

/* Experimental framebuffer/region drawing calls used by bundled games. */
#define BDA_GUI_BLIT_LIKE     0x3f8u
#define BDA_GUI_BLIT_ALT_LIKE 0x400u

/* Experimental game/front-end calls observed in GAMEBOY.BDA. */
#define BDA_GUI_DRAW_PACKET_LIKE       0x5d4u
#define BDA_GUI_SCREEN_ALLOC_LIKE      0x6b0u
#define BDA_GUI_BLIT_STATE_LIKE        0x6e0u
#define BDA_GUI_STATE_QUERY_LIKE       0x72cu
#define BDA_GUI_SCREEN_MODE_QUERY_LIKE 0x738u
#define BDA_GUI_EVENT_FETCH_LIKE       0x750u

/* Experimental high-level file selector calls observed in GAMEBOY.BDA. */
#define BDA_GUI_FILE_SELECTOR_OPEN_LIKE   0x6a8u
#define BDA_GUI_FILE_SELECTOR_GET_LIKE    0x6b8u
#define BDA_GUI_FILE_SELECTOR_CLOSE_LIKE  0x6bcu
#define BDA_GUI_FILE_SELECTOR_UPDATE_LIKE 0x6c8u

#define BDA_MEM_ALLOC 0x008u
#define BDA_MEM_FREE  0x00cu

#define BDA_RES_GET_STATE_LIKE 0x090u
/* 元素周期表 uses this with printf-style strings. The old load_dlx name was
   an early, unconfirmed interpretation kept only for experiment compatibility. */
#define BDA_RES_ENTRY_094_LIKE 0x094u
#define BDA_RES_TRACE_LIKE BDA_RES_ENTRY_094_LIKE
/* Deprecated historical misname: true-device probes show RES+0x094 is
   trace/log-like, not a confirmed DLX loader. */
#define BDA_RES_LOAD_DLX BDA_RES_ENTRY_094_LIKE

#define BDA_FS_OPEN  0x000u
#define BDA_FS_CLOSE 0x004u
#define BDA_FS_READ  0x008u
#define BDA_FS_WRITE 0x00cu
#define BDA_FS_SEEK  0x010u
#define BDA_FS_TELL  0x014u
#define BDA_FS_REMOVE 0x024u
#define BDA_FS_CHDIR_LIKE 0x02cu
#define BDA_FS_MKDIR_LIKE 0x030u
#define BDA_FS_FINDFIRST_LIKE 0x03cu
#define BDA_FS_FINDNEXT_LIKE  0x040u
#define BDA_FS_FINDCLOSE_LIKE 0x044u
#define BDA_FS_DISKINFO_LIKE  0x048u
#define BDA_FS_STAT_LIKE      0x06cu
#define BDA_FS_STORAGE_READY_LIKE 0x07cu

#define BDA_SEEK_SET 0
#define BDA_SEEK_CUR 1
#define BDA_SEEK_END 2

/* Experimental device/audio calls observed in GAMEBOY.BDA. */
#define BDA_SYS_CLOSE_LIKE       0x004u
#define BDA_SYS_AUDIO_OPEN_LIKE  0x06cu
#define BDA_SYS_AUDIO_READY_LIKE 0x074u
#define BDA_SYS_AUDIO_WRITE_LIKE 0x078u
#define BDA_SYS_AUDIO_RESET_LIKE 0x08cu
#define BDA_SYS_PACKAGE_SOUND_LOAD_LIKE 0x050u
#define BDA_SYS_PACKAGE_SOUND_OP58_LIKE 0x058u
#define BDA_SYS_PACKAGE_SOUND_OP5C_LIKE 0x05cu
#define BDA_SYS_PACKAGE_SOUND_OP60_LIKE 0x060u
#define BDA_SYS_PACKAGE_SOUND_OP64_LIKE 0x064u
#define BDA_SYS_PACKAGE_SOUND_OP68_LIKE 0x068u
#define BDA_SYS_TIMER_LIKE       0x09cu
#define BDA_SYS_AUDIO_FLUSH_LIKE 0x0a0u
#define BDA_SYS_DELAY_LIKE       0x080u
#define BDA_SYS_ALARM_COMMIT_LIKE 0x0a8u
#define BDA_SYS_ALARM_SET_LIKE   0x0acu
#define BDA_SYS_ALARM_GET_LIKE   0x0b0u
#define BDA_SYS_TIME_GET_LIKE    0x0b8u

typedef void *bda_handle_t;
typedef int (*bda_wndproc_t)(bda_handle_t hwnd, u32 message, u32 wparam, u32 lparam);

/*
 * Experimental selector descriptor. GAMEBOY.BDA initializes these fields before
 * calling GUI+0x6c8. Hardware tests show the fuller initialization below fixes
 * the file selector's unreadable black-on-black text, so some reserved-looking
 * words are display/theme/state parameters rather than harmless padding.
 */
typedef struct bda_file_selector_like {
    char *out_path;
    const char *extensions;
    void *dir_state;
    const char *title;
    u32 reserved10;
    u32 reserved14;
    u32 status18;
    s32 reserved1c;
    s32 reserved20;
    s32 reserved24;
    u32 reserved28;
    u32 reserved2c;
    u32 reserved30;
    u32 reserved34;
    u32 reserved38;
    u32 reserved3c;
    u32 reserved40;
    u32 reserved44;
    s32 reserved48;
    u32 reserved4c;
    u32 reserved50;
    u32 reserved54;
    u32 reserved58;
    u32 reserved5c;
    u32 reserved60;
    u32 reserved64;
} bda_file_selector_like_t;

/*
 * Experimental decoded picture descriptor observed in the bundled photo album
 * app. The album code treats pixel data as 16-bit RGB565 and may create
 * rotated/copied buffers depending on the orientation mode.
 */
typedef struct bda_picture_like {
    void *pixels;
    u32 dim_a;
    u32 dim_b;
    u32 aux0c;
    u8 mode10;
    u8 mode11;
    u8 reserved12;
    u8 reserved13;
    void *owned_pixels;
    s32 selected_index;
} bda_picture_like_t;

#define BDA_LOWORD(x) ((u32)(x) & 0xffffu)
#define BDA_HIWORD(x) (((u32)(x) >> 16) & 0xffffu)
#define BDA_MAKEWORD(lo, hi) ((((u32)(hi) & 0xffffu) << 16) | ((u32)(lo) & 0xffffu))

/*
 * Experimental message IDs observed in bundled window procedures. The callback
 * convention is hwnd/message/wparam/lparam in a0/a1/a2/a3.
 */
#define BDA_MSG_CREATE        0x0010u
#define BDA_MSG_COMMAND_LIKE  0x083eu
#define BDA_MSG_TOUCH_A_LIKE  0x00b0u
#define BDA_MSG_REDRAW_INPUT_LIKE 0x00b1u
#define BDA_MSG_TOUCH_B_LIKE  BDA_MSG_REDRAW_INPUT_LIKE /* deprecated misname */
#define BDA_MSG_INPUT_0842_LIKE 0x0842u
#define BDA_MSG_KEYDOWN_LIKE  0x0844u
#define BDA_MSG_FOCUS_LIKE    0x0841u

/*
 * Experimental command/control IDs seen in message wparam low/high words.
 * Keep raw names until hardware probes map them to exact GUI messages.
 */
#define BDA_CMD_LBUTTON_DOWN_LIKE 0x047eu
#define BDA_CMD_LBUTTON_UP_LIKE   0x047fu
#define BDA_CMD_PEN_AREA_LIKE     0x0501u

static inline void *bda_table(u32 addr) {
    return *(void **)addr;
}

static inline void *bda_api(void *table, u32 offset) {
    return *(void **)((u8 *)table + offset);
}

static inline int bda_call0(void *table, u32 offset) {
    typedef int (*fn_t)(void);
    return ((fn_t)bda_api(table, offset))();
}

static inline int bda_call1(void *table, u32 offset, u32 a0) {
    typedef int (*fn_t)(u32);
    return ((fn_t)bda_api(table, offset))(a0);
}

static inline int bda_call2(void *table, u32 offset, u32 a0, u32 a1) {
    typedef int (*fn_t)(u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1);
}

static inline int bda_call3(void *table, u32 offset, u32 a0, u32 a1, u32 a2) {
    typedef int (*fn_t)(u32, u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1, a2);
}

static inline int bda_call4(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3) {
    typedef int (*fn_t)(u32, u32, u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1, a2, a3);
}

static inline int bda_call5(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3, u32 a4) {
    typedef int (*fn_t)(u32, u32, u32, u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1, a2, a3, a4);
}

static inline int bda_call6(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3, u32 a4, u32 a5) {
    typedef int (*fn_t)(u32, u32, u32, u32, u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1, a2, a3, a4, a5);
}

static inline void *bda_gui_table(void) {
    return bda_table(BDA_GUI_TABLE_ADDR);
}

static inline void *bda_fs_table(void) {
    return bda_table(BDA_FS_TABLE_ADDR);
}

static inline void *bda_sys_table(void) {
    return bda_table(BDA_SYS_TABLE_ADDR);
}

static inline void *bda_mem_table(void) {
    return bda_table(BDA_MEM_TABLE_ADDR);
}

static inline void *bda_res_table(void) {
    return bda_table(BDA_RES_TABLE_ADDR);
}

static inline void *bda_memcpy(void *dst, const void *src, bda_size_t n) {
    u8 *d = (u8 *)dst;
    const u8 *s = (const u8 *)src;
    while (n--) {
        *d++ = *s++;
    }
    return dst;
}

static inline void *bda_memset(void *dst, int value, bda_size_t n) {
    u8 *d = (u8 *)dst;
    while (n--) {
        *d++ = (u8)value;
    }
    return dst;
}

static inline bda_size_t bda_strlen(const char *s) {
    const char *p = s;
    while (*p) {
        ++p;
    }
    return (bda_size_t)(p - s);
}

static inline void *bda_alloc(bda_size_t size) {
    typedef void *(*alloc_fn)(bda_size_t size);
    alloc_fn alloc = (alloc_fn)bda_api(bda_mem_table(), BDA_MEM_ALLOC);
    return alloc(size);
}

static inline void bda_free(void *ptr) {
    typedef void (*free_fn)(void *ptr);
    free_fn freep = (free_fn)bda_api(bda_mem_table(), BDA_MEM_FREE);
    freep(ptr);
}

static inline int bda_msgbox_ex(void *parent, const char *title, const char *message, u32 flags) {
    typedef int (*msgbox_fn)(void *parent, const char *message, const char *title, u32 flags);
    msgbox_fn msgbox = (msgbox_fn)bda_api(bda_gui_table(), BDA_GUI_MSGBOX);
    return msgbox(parent, message, title, flags);
}

static inline int bda_msgbox(const char *title, const char *message) {
    return bda_msgbox_ex(0, title, message, 0);
}

static inline bda_handle_t bda_gui_create_ex(
    const char *class_name,
    const char *caption,
    u32 style,
    bda_handle_t parent,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    u32 id,
    u32 extra
) {
    typedef bda_handle_t (*create_fn)(
        const char *class_name,
        const char *caption,
        u32 style,
        bda_handle_t parent,
        s32 x,
        s32 y,
        s32 width,
        s32 height,
        u32 id,
        u32 extra
    );
    create_fn create = (create_fn)bda_api(bda_gui_table(), BDA_GUI_CREATE);
    return create(class_name, caption, style, parent, x, y, width, height, id, extra);
}

static inline bda_handle_t bda_gui_create_window_like(
    const char *class_name,
    const char *caption,
    u32 style,
    u32 flags,
    u32 id,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    bda_handle_t parent,
    u32 extra
) {
    typedef bda_handle_t (*create_fn)(
        const char *class_name,
        const char *caption,
        u32 style,
        u32 flags,
        u32 id,
        s32 x,
        s32 y,
        s32 width,
        s32 height,
        bda_handle_t parent,
        u32 extra
    );
    create_fn create = (create_fn)bda_api(bda_gui_table(), BDA_GUI_CREATE);
    return create(class_name, caption, style, flags, id, x, y, width, height, parent, extra);
}

static inline int bda_gui_send(bda_handle_t handle, u32 message, u32 a, u32 b) {
    typedef int (*send_fn)(bda_handle_t handle, u32 message, u32 a, u32 b);
    send_fn send = (send_fn)bda_api(bda_gui_table(), BDA_GUI_SEND);
    return send(handle, message, a, b);
}

static inline int bda_gui_notify_like(bda_handle_t handle, u32 message, u32 a, u32 b) {
    typedef int (*notify_fn)(bda_handle_t handle, u32 message, u32 a, u32 b);
    notify_fn notify = (notify_fn)bda_api(bda_gui_table(), BDA_GUI_NOTIFY_LIKE);
    return notify(handle, message, a, b);
}

static inline int bda_gui_destroy_like(bda_handle_t handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_DESTROY_LIKE, (u32)handle);
}

static inline int bda_gui_blit_like(s32 x, s32 y, s32 height, s32 width, const void *buffer) {
    return bda_call5(bda_gui_table(), BDA_GUI_BLIT_LIKE, (u32)x, (u32)y, (u32)height, (u32)width, (u32)buffer);
}

static inline int bda_gui_blit_alt_like(s32 x, s32 y, s32 height, s32 width, const void *buffer) {
    return bda_call5(bda_gui_table(), BDA_GUI_BLIT_ALT_LIKE, (u32)x, (u32)y, (u32)height, (u32)width, (u32)buffer);
}

static inline int bda_gui_pump_present_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_PUMP_PRESENT_LIKE);
}

static inline int bda_gui_pump_present_arg_like(u32 value) {
    return bda_call1(bda_gui_table(), BDA_GUI_PUMP_PRESENT_LIKE, value);
}

static inline int bda_gui_register_frame_like(void *descriptor) {
    return bda_call1(bda_gui_table(), BDA_GUI_REGISTER_FRAME_LIKE, (u32)descriptor);
}

static inline int bda_gui_frame_stop_like(bda_handle_t handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_FRAME_STOP_LIKE, (u32)handle);
}

static inline int bda_gui_frame_release_like(bda_handle_t handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_FRAME_RELEASE_LIKE, (u32)handle);
}

static inline int bda_gui_default_proc_like(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    return bda_call4(bda_gui_table(), BDA_GUI_DEFAULT_PROC_LIKE, (u32)handle, message, wparam, lparam);
}

static inline int bda_gui_frame_activate_like(bda_handle_t handle, u32 mode) {
    return bda_call2(bda_gui_table(), BDA_GUI_FRAME_ACTIVATE_LIKE, (u32)handle, mode);
}

static inline int bda_gui_event_poll_like(void *message, bda_handle_t handle) {
    return bda_call2(bda_gui_table(), BDA_GUI_EVENT_POLL_LIKE, (u32)message, (u32)handle);
}

static inline int bda_gui_event_poll_global_like(void *message) {
    return bda_gui_event_poll_like(message, 0);
}

static inline int bda_gui_event_step_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_EVENT_STEP_LIKE);
}

static inline int bda_gui_event_dispatch_like(void *message) {
    return bda_call1(bda_gui_table(), BDA_GUI_EVENT_DISPATCH_LIKE, (u32)message);
}

static inline int bda_gui_close_frame_like(bda_handle_t handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_CLOSE_FRAME_LIKE, (u32)handle);
}

static inline int bda_gui_object_op_like(u32 object, u32 op, u32 arg) {
    return bda_call3(bda_gui_table(), BDA_GUI_OBJECT_OP_LIKE, object, op, arg);
}

static inline bda_handle_t bda_gui_begin_draw_like(bda_handle_t handle) {
    return (bda_handle_t)bda_call1(bda_gui_table(), BDA_GUI_BEGIN_DRAW_LIKE, (u32)handle);
}

static inline int bda_gui_end_draw_like(bda_handle_t draw_handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_END_DRAW_LIKE, (u32)draw_handle);
}

static inline void *bda_gui_draw_object_create_like(u32 a0, u32 a1, u32 a2, u32 a3) {
    typedef void *(*draw_object_create_fn)(u32, u32, u32, u32);
    draw_object_create_fn fn = (draw_object_create_fn)bda_api(bda_gui_table(), BDA_GUI_DRAW_OBJECT_CREATE_LIKE);
    return fn(a0, a1, a2, a3);
}

static inline void *bda_gui_frame_surface_like(u32 kind) {
    return (void *)bda_call1(bda_gui_table(), BDA_GUI_DRAW_OBJECT_CREATE_LIKE, kind);
}

static inline bda_handle_t bda_gui_current_draw_like(void) {
    return (bda_handle_t)bda_call0(bda_gui_table(), BDA_GUI_CURRENT_DRAW_LIKE);
}

static inline int bda_gui_object_bind_like(u32 object, u32 resource) {
    return bda_call2(bda_gui_table(), BDA_GUI_OBJECT_BIND_LIKE, object, resource);
}

static inline int bda_gui_put_pixel_like(bda_handle_t surface, s32 x, s32 y, u16 rgb565) {
    return bda_call4(bda_gui_table(), BDA_GUI_PUT_PIXEL_LIKE, (u32)surface, (u32)x, (u32)y, rgb565);
}

static inline int bda_gui_region_draw_like(u32 a0, u32 a1, u32 a2, u32 a3) {
    return bda_call4(bda_gui_table(), BDA_GUI_REGION_DRAW_LIKE, a0, a1, a2, a3);
}

static inline void *bda_gui_screen_alloc_like(u32 a0, u32 a1, u32 a2, u32 a3) {
    typedef void *(*screen_alloc_fn)(u32, u32, u32, u32);
    screen_alloc_fn fn = (screen_alloc_fn)bda_api(bda_gui_table(), BDA_GUI_SCREEN_ALLOC_LIKE);
    return fn(a0, a1, a2, a3);
}

static inline int bda_gui_state_query_like(u32 a0) {
    return bda_call1(bda_gui_table(), BDA_GUI_STATE_QUERY_LIKE, a0);
}

static inline int bda_gui_screen_mode_query_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_SCREEN_MODE_QUERY_LIKE);
}

static inline int bda_gui_event_fetch_like(u32 a0) {
    return bda_call1(bda_gui_table(), BDA_GUI_EVENT_FETCH_LIKE, a0);
}

static inline int bda_gui_draw_packet_like(void *packet) {
    return bda_call1(bda_gui_table(), BDA_GUI_DRAW_PACKET_LIKE, (u32)packet);
}

static inline int bda_gui_blit_state_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_BLIT_STATE_LIKE);
}

static inline int bda_gui_decode_bmp_like(void *owner, bda_picture_like_t *out, const char *path, void *work) {
    return bda_call4(bda_gui_table(), BDA_GUI_DECODE_BMP_LIKE, (u32)owner, (u32)out, (u32)path, (u32)work);
}

static inline int bda_gui_decode_jpeg_like(void *owner, bda_picture_like_t *out, const char *path, u32 mode) {
    return bda_call4(bda_gui_table(), BDA_GUI_DECODE_JPEG_LIKE, (u32)owner, (u32)out, (u32)path, mode);
}

static inline int bda_gui_file_selector_open_like(u32 mode) {
    return bda_call1(bda_gui_table(), BDA_GUI_FILE_SELECTOR_OPEN_LIKE, mode);
}

static inline int bda_gui_file_selector_update_like(bda_file_selector_like_t *selector) {
    return bda_call1(bda_gui_table(), BDA_GUI_FILE_SELECTOR_UPDATE_LIKE, (u32)selector);
}

static inline int bda_gui_file_selector_get_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_FILE_SELECTOR_GET_LIKE);
}

static inline int bda_gui_file_selector_close_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_FILE_SELECTOR_CLOSE_LIKE);
}

static inline int bda_gui_set_text_mode_like(bda_handle_t handle, u32 mode) {
    return bda_call2(bda_gui_table(), BDA_GUI_SET_TEXT_MODE_LIKE, (u32)handle, mode);
}

static inline int bda_gui_rgb_like(bda_handle_t handle, u32 r, u32 g, u32 b) {
    return bda_call4(bda_gui_table(), BDA_GUI_RGB_LIKE, (u32)handle, r, g, b);
}

static inline int bda_gui_set_text_color_like(bda_handle_t handle, u32 color) {
    return bda_call2(bda_gui_table(), BDA_GUI_SET_TEXT_COLOR_LIKE, (u32)handle, color);
}

static inline int bda_gui_draw_text_like(bda_handle_t handle, s32 x, s32 y, const char *text, s32 extra) {
    return bda_call5(bda_gui_table(), BDA_GUI_DRAW_TEXT_LIKE, (u32)handle, (u32)x, (u32)y, (u32)text, (u32)extra);
}

static inline int bda_gui_draw_vx_like(bda_handle_t handle, s32 x, s32 y, s32 width, s32 height, const void *vx_resource) {
    return bda_call6(
        bda_gui_table(),
        BDA_GUI_DRAW_VX_LIKE,
        (u32)handle,
        (u32)x,
        (u32)y,
        (u32)width,
        (u32)height,
        (u32)vx_resource
    );
}

static inline int bda_res_entry_094_like(const char *text_or_path, void *arg) {
    typedef int (*entry_fn)(const char *text_or_path, void *arg);
    entry_fn fn = (entry_fn)bda_api(bda_res_table(), BDA_RES_ENTRY_094_LIKE);
    return fn(text_or_path, arg);
}

static inline int bda_res_trace_like(const char *format, void *arg) {
    return bda_res_entry_094_like(format, arg);
}

static inline int bda_load_dlx_ex(const char *path, void *arg) {
    /* Deprecated historical misname. This calls RES+0x094 trace/log-like entry,
       not a confirmed DLX loader. Kept only so older probes still compile. */
    return bda_res_entry_094_like(path, arg);
}

static inline int bda_res_get_state_like(void *out_state) {
    return bda_call1(bda_res_table(), BDA_RES_GET_STATE_LIKE, (u32)out_state);
}

static inline int bda_load_dlx(const char *path) {
    return bda_load_dlx_ex(path, (void *)BDA_RUNTIME_BASE);
}

static inline int bda_load_dlx_gui(const char *path) {
    return bda_load_dlx_ex(path, bda_gui_table());
}

static inline int bda_load_dlx_fs(const char *path) {
    return bda_load_dlx_ex(path, bda_fs_table());
}

static inline int bda_load_dlx_mem(const char *path) {
    return bda_load_dlx_ex(path, bda_mem_table());
}

static inline int bda_load_dlx_res(const char *path) {
    return bda_load_dlx_ex(path, bda_res_table());
}

static inline void bda_file_selector_init_like(
    bda_file_selector_like_t *selector,
    char *out_path,
    const char *extensions,
    void *dir_state,
    const char *title
) {
    bda_memset(selector, 0, sizeof(*selector));
    selector->out_path = out_path;
    selector->extensions = extensions;
    selector->dir_state = dir_state;
    selector->title = title;
    selector->reserved1c = -1;
    selector->reserved20 = -1;
    selector->reserved24 = -1;
    selector->reserved34 = (u32)-1;
    selector->reserved38 = (u32)-1;
    selector->reserved40 = 0x1000;
    selector->reserved48 = -1;
    selector->reserved64 = 0;
}

static inline void bda_file_selector_load_default_skin_like(void) {
    /* Deprecated historical misname. RES+0x094 probes show these calls do not
       load skins; correct selector colors came from struct initialization. */
    bda_load_dlx_gui("\\Shell\\guihelp_A.dlx");
    bda_load_dlx_gui("\\shell\\commonframe_A.dlx");
    bda_load_dlx_gui("\\shell\\MessageBoxBlue.dlx");
    bda_load_dlx_gui("\\shell\\NLB_ICON.dlx");
}

static inline int bda_fs_open_raw(const char *path, u32 mode) {
    typedef int (*open_fn)(const char *path, u32 mode);
    open_fn openp = (open_fn)bda_api(bda_fs_table(), BDA_FS_OPEN);
    return openp(path, mode);
}

static inline int bda_fs_fopen_raw(const char *path, const char *mode) {
    typedef int (*open_fn)(const char *path, const char *mode);
    open_fn openp = (open_fn)bda_api(bda_fs_table(), BDA_FS_OPEN);
    return openp(path, mode);
}

static inline int bda_fs_close_raw(int fd) {
    typedef int (*close_fn)(int fd);
    close_fn closep = (close_fn)bda_api(bda_fs_table(), BDA_FS_CLOSE);
    return closep(fd);
}

static inline int bda_fs_fread_raw(void *buffer, bda_size_t size, bda_size_t count, int file) {
    typedef int (*read_fn)(void *buffer, bda_size_t size, bda_size_t count, int file);
    read_fn readp = (read_fn)bda_api(bda_fs_table(), BDA_FS_READ);
    return readp(buffer, size, count, file);
}

static inline int bda_fs_read_raw(int file, void *buffer, bda_size_t size) {
    return bda_fs_fread_raw(buffer, 1, size, file);
}

static inline int bda_fs_fwrite_raw(const void *buffer, bda_size_t size, bda_size_t count, int file) {
    typedef int (*write_fn)(const void *buffer, bda_size_t size, bda_size_t count, int file);
    write_fn writep = (write_fn)bda_api(bda_fs_table(), BDA_FS_WRITE);
    return writep(buffer, size, count, file);
}

static inline int bda_fs_write_raw(int file, const void *buffer, bda_size_t size) {
    return bda_fs_fwrite_raw(buffer, 1, size, file);
}

static inline int bda_fs_seek_raw(int file, s32 offset, int whence) {
    typedef int (*seek_fn)(int file, s32 offset, int whence);
    seek_fn seekp = (seek_fn)bda_api(bda_fs_table(), BDA_FS_SEEK);
    return seekp(file, offset, whence);
}

static inline int bda_fs_tell_raw(int file) {
    typedef int (*tell_fn)(int file);
    tell_fn tellp = (tell_fn)bda_api(bda_fs_table(), BDA_FS_TELL);
    return tellp(file);
}

static inline int bda_fs_remove_raw(const char *path) {
    return bda_call1(bda_fs_table(), BDA_FS_REMOVE, (u32)path);
}

static inline int bda_fs_chdir_like(const char *path) {
    return bda_call1(bda_fs_table(), BDA_FS_CHDIR_LIKE, (u32)path);
}

static inline int bda_fs_mkdir_like(const char *path) {
    return bda_call1(bda_fs_table(), BDA_FS_MKDIR_LIKE, (u32)path);
}

static inline int bda_fs_findfirst_like(const char *pattern, u32 attr, void *find_data) {
    return bda_call3(bda_fs_table(), BDA_FS_FINDFIRST_LIKE, (u32)pattern, attr, (u32)find_data);
}

static inline int bda_fs_findnext_like(void *find_data) {
    return bda_call1(bda_fs_table(), BDA_FS_FINDNEXT_LIKE, (u32)find_data);
}

static inline int bda_fs_findclose_like(void *find_data) {
    return bda_call1(bda_fs_table(), BDA_FS_FINDCLOSE_LIKE, (u32)find_data);
}

static inline int bda_fs_diskinfo_like(u32 drive, void *info) {
    return bda_call2(bda_fs_table(), BDA_FS_DISKINFO_LIKE, drive, (u32)info);
}

static inline int bda_fs_stat_like(const char *path, u32 flags, void *stat_data) {
    return bda_call3(bda_fs_table(), BDA_FS_STAT_LIKE, (u32)path, flags, (u32)stat_data);
}

static inline int bda_fs_storage_ready_like(void) {
    return bda_call0(bda_fs_table(), BDA_FS_STORAGE_READY_LIKE);
}

static inline int bda_sys_audio_open_like(u32 device, u32 format, u32 channels, u32 buffer_hint) {
    return bda_call4(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE, device, format, channels, buffer_hint);
}

static inline int bda_sys_audio_ready_like(void) {
    return bda_call0(bda_sys_table(), BDA_SYS_AUDIO_READY_LIKE);
}

static inline int bda_sys_audio_write_like(const void *buffer, bda_size_t bytes) {
    return bda_call2(bda_sys_table(), BDA_SYS_AUDIO_WRITE_LIKE, (u32)buffer, bytes);
}

static inline int bda_sys_package_sound_load_like(void *descriptor) {
    return bda_call1(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_LOAD_LIKE, (u32)descriptor);
}

static inline int bda_sys_package_sound_op58_like(u32 a0, u32 a1) {
    return bda_call2(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP58_LIKE, a0, a1);
}

static inline int bda_sys_package_sound_op5c_like(u32 a0) {
    return bda_call1(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP5C_LIKE, a0);
}

static inline int bda_sys_package_sound_op60_like(u32 a0) {
    return bda_call1(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP60_LIKE, a0);
}

static inline int bda_sys_package_sound_op64_like(u32 a0) {
    return bda_call1(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP64_LIKE, a0);
}

static inline int bda_sys_package_sound_op68_like(u32 a0) {
    return bda_call1(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP68_LIKE, a0);
}

static inline int bda_sys_delay_like(u32 ticks_or_us) {
    return bda_call1(bda_sys_table(), BDA_SYS_DELAY_LIKE, ticks_or_us);
}

static inline int bda_sys_timer_like(u32 ticks) {
    return bda_call1(bda_sys_table(), BDA_SYS_TIMER_LIKE, ticks);
}

static inline int bda_sys_time_get_like(void *time_data) {
    return bda_call1(bda_sys_table(), BDA_SYS_TIME_GET_LIKE, (u32)time_data);
}

static inline int bda_sys_alarm_commit_like(u32 index_or_flags) {
    return bda_call1(bda_sys_table(), BDA_SYS_ALARM_COMMIT_LIKE, index_or_flags);
}

static inline int bda_sys_alarm_set_like(void *alarm_data, u32 index) {
    return bda_call2(bda_sys_table(), BDA_SYS_ALARM_SET_LIKE, (u32)alarm_data, index);
}

static inline int bda_sys_alarm_get_like(void *alarm_data, u32 index) {
    return bda_call2(bda_sys_table(), BDA_SYS_ALARM_GET_LIKE, (u32)alarm_data, index);
}

#endif
