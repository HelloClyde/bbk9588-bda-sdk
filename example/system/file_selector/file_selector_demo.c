#include "bda_sdk.h"

static bda_file_selector_t g_selector;

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int result = bda_gui_select_file(
        &g_selector,
        "A:\\gameboy\\",
        "gb;gbc",
        "Select GB/GBC"
    );

    if (result == BDA_FILE_SELECTOR_SELECTED) {
        (void)bda_msgbox("Selected file", g_selector.path);
    } else if (result == BDA_FILE_SELECTOR_CANCELLED) {
        (void)bda_msgbox("File selector", "Selection cancelled");
    } else {
        (void)bda_msgbox("File selector", "Invalid selector arguments or result");
    }
    return 0;
}
