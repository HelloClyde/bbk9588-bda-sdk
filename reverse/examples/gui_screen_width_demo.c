#include "bda_sdk.h"

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int width = bda_gui_screen_width_like();

    if (width == 0x130) {
        bda_msgbox("GUI WIDTH", "screen width 0x130");
    } else {
        bda_msgbox("GUI WIDTH", "unexpected width");
    }
    return 0;
}
