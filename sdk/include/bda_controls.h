#ifndef BDA_CONTROLS_H
#define BDA_CONTROLS_H

#include "bda_sdk.h"

/* Dynamically verified control classes on the kj409588/C200 firmware. */
#define BDA_CONTROL_CLASS_STATIC      "static"
#define BDA_CONTROL_CLASS_BUTTON      "button"
#define BDA_CONTROL_CLASS_EDIT        "edit"
#define BDA_CONTROL_CLASS_SLEDIT      "sledit"
#define BDA_CONTROL_CLASS_MEDIT       "medit"
#define BDA_CONTROL_CLASS_MLEDIT      "mledit"
#define BDA_CONTROL_CLASS_LISTBOX     "listbox"
#define BDA_CONTROL_CLASS_COMBOBOX    "combobox"
#define BDA_CONTROL_CLASS_PROGRESSBAR "progressbar"
#define BDA_CONTROL_CLASS_TOOLBAR     "toolbar"
#define BDA_CONTROL_CLASS_GIFCTRL     "gifctrl"

/* Per-class defaults used by the emulator admission probes. */
#define BDA_STATIC_STYLE_DEFAULT      0x08000000u
#define BDA_BUTTON_STYLE_DEFAULT      0x08000001u
#define BDA_EDIT_STYLE_DEFAULT        0x08000001u
#define BDA_SLEDIT_STYLE_DEFAULT      0x08000001u
#define BDA_MEDIT_STYLE_DEFAULT       0x08083001u
#define BDA_MLEDIT_STYLE_DEFAULT      0x08083001u
#define BDA_LISTBOX_STYLE_DEFAULT     0x08090001u
#define BDA_COMBOBOX_STYLE_DEFAULT    0x08000001u
#define BDA_PROGRESSBAR_STYLE_DEFAULT 0x08000000u
#define BDA_TOOLBAR_STYLE_DEFAULT     0x08000000u
#define BDA_GIFCTRL_STYLE_EMPTY       0x08000000u
#define BDA_GIFCTRL_STYLE_ANIMATED    0x08000001u

#define BDA_CONTROL_MSG_COMMAND 0x0120u

#define BDA_TEXT_CONTROL_MSG_GET_TEXT       0x0133u
#define BDA_TEXT_CONTROL_MSG_SET_TEXT       0x0134u
#define BDA_TEXT_CONTROL_MSG_SET_MAX_LENGTH 0xf0c5u

#define BDA_LISTBOX_MSG_APPEND_ITEM   0xf180u
#define BDA_LISTBOX_MSG_SET_SELECTION 0xf186u
#define BDA_LISTBOX_MSG_GET_SELECTION 0xf188u
#define BDA_LISTBOX_MSG_GET_ITEM_TEXT 0xf189u
#define BDA_LISTBOX_MSG_GET_COUNT     0xf18bu

#define BDA_MEDIT_MSG_SET_BACKGROUND_VX  0xf0ddu
#define BDA_MEDIT_MSG_SET_DRAW_OBJECT   0xf0dfu
#define BDA_LISTBOX_MSG_SET_BACKGROUND_VX 0xf1b4u
#define BDA_LISTBOX_MSG_SET_DRAW_OBJECT  0xf1b5u

#define BDA_COMBOBOX_MSG_APPEND_ITEM   0xf143u
#define BDA_COMBOBOX_MSG_GET_COUNT     0xf146u
#define BDA_COMBOBOX_MSG_GET_SELECTION 0xf147u
#define BDA_COMBOBOX_MSG_SET_SELECTION 0xf14eu

#define BDA_PROGRESSBAR_MSG_SET_RANGE    0xf0a0u
#define BDA_PROGRESSBAR_MSG_SET_STEP     0xf0a1u
#define BDA_PROGRESSBAR_MSG_SET_POSITION 0xf0a3u
#define BDA_PROGRESSBAR_MSG_STEP         0xf0a4u

typedef struct bda_control_desc {
    const char *class_name;
    const char *caption;
    u32 style;
    u32 flags;
    u32 id;
    s32 x;
    s32 y;
    s32 width;
    s32 height;
    bda_handle_t parent;
    u32 extra;
} bda_control_desc_t;

typedef struct bda_control_class_desc {
    const char *class_name;
    u32 reserved04;
    u32 reserved08;
    void *draw_object;
    bda_wndproc_t wndproc;
} bda_control_class_desc_t;

/*
 * gifctrl reads GIF89a bytes directly from data for its full lifetime.
 * Keep data and this descriptor alive until bda_control_destroy().
 */
typedef struct bda_gifctrl_resource {
    const u8 *data;
    u32 reserved04;
    u32 timer_id;
} bda_gifctrl_resource_t;

#define BDA_CONTROLS_INTERNAL_GUI_SEND             0x040u
#define BDA_CONTROLS_INTERNAL_GUI_SET_ACTIVE       0x134u
#define BDA_CONTROLS_INTERNAL_GUI_CLASS_REGISTER   0x190u
#define BDA_CONTROLS_INTERNAL_GUI_CLASS_UNREGISTER 0x194u
#define BDA_CONTROLS_INTERNAL_GUI_CREATE            0x1a4u
#define BDA_CONTROLS_INTERNAL_GUI_DESTROY           0x1a8u

static inline int bda_control_is_valid(bda_handle_t control) {
    return control != 0 && (u32)control != 0xffffffffu;
}

static inline bda_handle_t bda_control_create(
    const bda_control_desc_t *descriptor
) {
    typedef bda_handle_t (*fn_t)(
        const char *, const char *, u32, u32, u32,
        s32, s32, s32, s32, bda_handle_t, u32
    );
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_CONTROLS_INTERNAL_GUI_CREATE
    );

    return fn(
        descriptor->class_name,
        descriptor->caption,
        descriptor->style,
        descriptor->flags,
        descriptor->id,
        descriptor->x,
        descriptor->y,
        descriptor->width,
        descriptor->height,
        descriptor->parent,
        descriptor->extra
    );
}

static inline int bda_control_send(
    bda_handle_t control,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    typedef int (*fn_t)(bda_handle_t, u32, u32, u32);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_CONTROLS_INTERNAL_GUI_SEND
    );
    return fn(control, message, wparam, lparam);
}

static inline int bda_control_set_active(bda_handle_t control) {
    typedef int (*fn_t)(bda_handle_t);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_CONTROLS_INTERNAL_GUI_SET_ACTIVE
    );
    return fn(control);
}

static inline int bda_control_destroy(bda_handle_t control) {
    typedef int (*fn_t)(bda_handle_t);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_CONTROLS_INTERNAL_GUI_DESTROY
    );
    return fn(control);
}

static inline int bda_control_class_register(
    bda_control_class_desc_t *descriptor
) {
    typedef int (*fn_t)(bda_control_class_desc_t *);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_CONTROLS_INTERNAL_GUI_CLASS_REGISTER
    );
    return fn(descriptor);
}

static inline int bda_control_class_unregister(const char *class_name) {
    typedef int (*fn_t)(const char *);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_CONTROLS_INTERNAL_GUI_CLASS_UNREGISTER
    );
    return fn(class_name);
}

static inline u32 bda_control_command_id(u32 wparam) {
    return wparam & 0xffffu;
}

static inline u32 bda_control_command_code(u32 wparam) {
    return wparam >> 16;
}

static inline int bda_text_control_set_max_length(
    bda_handle_t control,
    u32 max_length
) {
    return bda_control_send(
        control, BDA_TEXT_CONTROL_MSG_SET_MAX_LENGTH, max_length, 0
    );
}

static inline int bda_text_control_set_text(
    bda_handle_t control,
    const char *text
) {
    return bda_control_send(
        control, BDA_TEXT_CONTROL_MSG_SET_TEXT, 0, (u32)text
    );
}

static inline int bda_text_control_get_text(
    bda_handle_t control,
    char *buffer,
    u32 buffer_size
) {
    return bda_control_send(
        control, BDA_TEXT_CONTROL_MSG_GET_TEXT, buffer_size, (u32)buffer
    );
}

static inline int bda_listbox_append_item(
    bda_handle_t control,
    const char *text
) {
    return bda_control_send(
        control, BDA_LISTBOX_MSG_APPEND_ITEM, 0, (u32)text
    );
}

static inline int bda_listbox_set_selection(
    bda_handle_t control,
    s32 index
) {
    return bda_control_send(
        control, BDA_LISTBOX_MSG_SET_SELECTION, (u32)index, 0
    );
}

static inline int bda_listbox_get_selection(bda_handle_t control) {
    return bda_control_send(
        control, BDA_LISTBOX_MSG_GET_SELECTION, 0, 0
    );
}

static inline int bda_listbox_get_item_text(
    bda_handle_t control,
    s32 index,
    char *buffer
) {
    return bda_control_send(
        control, BDA_LISTBOX_MSG_GET_ITEM_TEXT, (u32)index, (u32)buffer
    );
}

static inline int bda_listbox_get_count(bda_handle_t control) {
    return bda_control_send(control, BDA_LISTBOX_MSG_GET_COUNT, 0, 0);
}

/*
 * The control stores background_vx instead of copying it. Keep the complete
 * VX resource alive until bda_control_destroy() returns.
 */
static inline int bda_medit_set_background_vx(
    bda_handle_t control,
    const void *background_vx
) {
    return bda_control_send(
        control,
        BDA_MEDIT_MSG_SET_BACKGROUND_VX,
        (u32)background_vx,
        0
    );
}

static inline int bda_medit_set_draw_object(
    bda_handle_t control,
    u32 slot,
    void *draw_object
) {
    return bda_control_send(
        control,
        BDA_MEDIT_MSG_SET_DRAW_OBJECT,
        slot,
        (u32)draw_object
    );
}

static inline int bda_listbox_set_background_vx(
    bda_handle_t control,
    const void *background_vx
) {
    return bda_control_send(
        control,
        BDA_LISTBOX_MSG_SET_BACKGROUND_VX,
        (u32)background_vx,
        0
    );
}

static inline int bda_listbox_set_draw_object(
    bda_handle_t control,
    u32 slot,
    void *draw_object
) {
    return bda_control_send(
        control,
        BDA_LISTBOX_MSG_SET_DRAW_OBJECT,
        slot,
        (u32)draw_object
    );
}

static inline int bda_combobox_append_item(
    bda_handle_t control,
    const char *text
) {
    return bda_control_send(
        control, BDA_COMBOBOX_MSG_APPEND_ITEM, 0, (u32)text
    );
}

static inline int bda_combobox_set_selection(
    bda_handle_t control,
    s32 index
) {
    return bda_control_send(
        control, BDA_COMBOBOX_MSG_SET_SELECTION, (u32)index, 0
    );
}

static inline int bda_combobox_get_selection(bda_handle_t control) {
    return bda_control_send(
        control, BDA_COMBOBOX_MSG_GET_SELECTION, 0, 0
    );
}

static inline int bda_combobox_get_count(bda_handle_t control) {
    return bda_control_send(control, BDA_COMBOBOX_MSG_GET_COUNT, 0, 0);
}

static inline int bda_progressbar_set_range(
    bda_handle_t control,
    s32 minimum,
    s32 maximum
) {
    return bda_control_send(
        control, BDA_PROGRESSBAR_MSG_SET_RANGE,
        (u32)minimum, (u32)maximum
    );
}

static inline int bda_progressbar_set_step(
    bda_handle_t control,
    s32 step
) {
    return bda_control_send(
        control, BDA_PROGRESSBAR_MSG_SET_STEP, (u32)step, 0
    );
}

static inline int bda_progressbar_set_position(
    bda_handle_t control,
    s32 position
) {
    return bda_control_send(
        control, BDA_PROGRESSBAR_MSG_SET_POSITION, (u32)position, 0
    );
}

static inline int bda_progressbar_step(bda_handle_t control) {
    return bda_control_send(control, BDA_PROGRESSBAR_MSG_STEP, 0, 0);
}

#endif
