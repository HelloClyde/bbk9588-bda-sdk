#include "bda_dialogs.h"

static u32 first_pressed_key(const bda_gui_input_packet_t *packet) {
    static const u32 keys[] = {
        BDA_KEY_UP,
        BDA_KEY_DOWN,
        BDA_KEY_LEFT,
        BDA_KEY_RIGHT,
        BDA_KEY_ENTER,
        BDA_KEY_ESCAPE,
    };
    u32 i;

    for (i = 0; i < sizeof(keys) / sizeof(keys[0]); ++i) {
        if (bda_gui_input_packet_key_pressed(packet, keys[i])) {
            return keys[i];
        }
    }
    return 0;
}

static const char *key_name(u32 keycode) {
    switch (keycode) {
        case BDA_KEY_UP: return "UP";
        case BDA_KEY_DOWN: return "DOWN";
        case BDA_KEY_LEFT: return "LEFT";
        case BDA_KEY_RIGHT: return "RIGHT";
        case BDA_KEY_ENTER: return "ENTER";
        case BDA_KEY_ESCAPE: return "ESC";
        default: return "UNKNOWN";
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u32 latched = 0;

    bda_msgbox("KeyInput", "Press a device key");
    for (;;) {
        bda_gui_input_packet_t packet;
        u32 keycode;

        (void)bda_gui_input_packet(&packet);
        keycode = first_pressed_key(&packet);
        if (keycode == 0) {
            latched = 0;
        } else if (latched == 0) {
            latched = keycode;
            do {
                (void)bda_gui_input_packet(&packet);
                bda_sys_delay(1);
            } while (bda_gui_input_packet_key_pressed(&packet, keycode));
            bda_msgbox("KeyInput", key_name(keycode));
            if (keycode == BDA_KEY_ESCAPE) {
                return 0;
            }
        }
        bda_sys_delay(1);
    }
}
