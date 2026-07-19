#ifndef BDA_GRAPHICS_H
#define BDA_GRAPHICS_H

#include "bda/detail/runtime.h"

#define BDA_GUI_COLOR_KEY_NONE 0u
#define BDA_GUI_COLOR_KEY_MAGENTA_RGB565 0xf81fu

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
