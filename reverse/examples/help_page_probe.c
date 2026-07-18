#include "bda_research_sdk.h"

static const char g_help_document[] =
    "Help page probe\r\n"
    "This page is rendered by the firmware help service.\n"
    "\n"
    "Use the arrow keys to scroll the text.\n"
    "Press ESC or tap the close button to return.\n"
    "\n"
    "Line 1: GUI+0x5A8 creates the page.\n"
    "Line 2: the call owns a modal event loop.\n"
    "Line 3: closing the page returns to the BDA.\n"
    "Line 4: the caller does not release its frame.\n"
    "Line 5: this final line verifies scrolling.\n";

static void write_log(const char *mode, const char *text) {
    bda_size_t length = 0u;
    int file;

    while (text[length] != '\0') {
        ++length;
    }
    file = bda_fs_fopen_raw("A:\\HELP_PAGE.LOG", mode);
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, text, length);
    (void)bda_fs_close_raw(file);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    write_log("wb", "BEFORE GUI+0x5A8\n");
    (void)bda_gui_help_page_like(0, g_help_document);
    write_log("ab", "RETURNED FROM GUI+0x5A8\n");
    (void)bda_msgbox("Help page probe", "RETURNED: PASS");
    return 0;
}
