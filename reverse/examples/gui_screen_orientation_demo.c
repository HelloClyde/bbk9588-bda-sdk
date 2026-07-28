#include "../bda_research_sdk.h"

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int orientation = bda_gui_screen_orientation_like();

    if (orientation == 0x130) {
        bda_msgbox("ORIENTATION", "rotate 180");
    } else if (orientation == 0x131) {
        bda_msgbox("ORIENTATION", "normal");
    } else {
        bda_msgbox("ORIENTATION", "unexpected value");
    }
    return 0;
}
