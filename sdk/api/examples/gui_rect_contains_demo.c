#include "bda_sdk.h"

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_rect_like_t rect;
    int inside;
    int outside;

    bda_gui_rect_prepare_like(&rect, 10, 20, 110, 80);
    inside = bda_gui_rect_contains_like(&rect, 30, 40);
    outside = bda_gui_rect_contains_like(&rect, 5, 40);

    if (inside == 1 && outside == 0) {
        bda_msgbox("GUI RECT", "rect helper ok");
    } else {
        bda_msgbox("GUI RECT", "rect helper failed");
    }
    return 0;
}
