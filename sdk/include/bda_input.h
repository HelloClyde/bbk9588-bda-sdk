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

typedef struct bda_gui_input_packet {
    u8 bytes[BDA_GUI_INPUT_PACKET_SIZE];
} bda_gui_input_packet_t;

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

#endif
