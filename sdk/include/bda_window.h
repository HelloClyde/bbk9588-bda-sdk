#ifndef BDA_WINDOW_H
#define BDA_WINDOW_H

#include "bda/detail/runtime.h"

#define BDA_GUI_MESSAGE_SIZE 0x1cu

#define BDA_MSG_DRAW_CONTEXT_ATTACH 0x0060u
#define BDA_MSG_DRAW_CONTEXT_DETACH 0x0066u
#define BDA_MSG_REDRAW_INPUT        0x00b1u
#define BDA_MSG_TOUCH_COORDINATE    0x0001u
#define BDA_MSG_TOUCH_RELEASE       0x0002u

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

#endif
