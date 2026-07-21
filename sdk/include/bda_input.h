#ifndef BDA_INPUT_H
#define BDA_INPUT_H

#include "bda/detail/runtime.h"

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

#define BDA_INPUT_EVENT_TOUCH_DOWN 8u
#define BDA_INPUT_EVENT_KEY_DOWN   9u
#define BDA_INPUT_EVENT_KEY_UP     10u
#define BDA_INPUT_EVENT_TOUCH_UP   11u
#define BDA_INPUT_EVENT_TOUCH_MOVE 12u

typedef struct bda_gui_input_packet {
    u8 bytes[BDA_GUI_INPUT_PACKET_SIZE];
} bda_gui_input_packet_t;

typedef struct bda_gui_raw_event {
    s32 code;
    s32 value;
} bda_gui_raw_event_t;

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

/*
 * Consume one item from the firmware's global raw-input stream. This stream
 * is shared with higher-level GUI input handling, so do not mix this function
 * with a window event pump. Limit the number consumed per game iteration:
 * periodic code 3 events may keep the stream continuously non-empty.
 *
 * For touch events, value is not a coordinate. Read the latest logical X/Y
 * with bda_gui_touch_position(). The event pointer must be valid.
 */
static inline int bda_gui_raw_event_fetch(bda_gui_raw_event_t *event) {
    typedef int (*fn_t)(s32 *out_code, s32 *out_value);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_RAW_EVENT_FETCH
    );
    return fn(&event->code, &event->value);
}

/*
 * Read the latest calibrated logical touch coordinate. This is a cached
 * position getter, not a pressed-state query. Track the touch lifetime with
 * either window messages 1/2 or raw events 8/11; do not mix the two streams.
 * Both output pointers must be valid.
 */
static inline void bda_gui_touch_position(u16 *x, u16 *y) {
    (void)bda_sdk_internal_call2(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_TOUCH_POSITION,
        (u32)x,
        (u32)y
    );
}

#endif
