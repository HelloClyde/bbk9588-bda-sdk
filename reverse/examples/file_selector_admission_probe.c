#include "bda_dialogs.h"

static bda_file_selector_t g_selector;

static void create_fixture(const char *path, const char *contents) {
    int file = bda_fs_fopen_raw(path, "wb");
    const char *cursor = contents;
    bda_size_t size = 0u;
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    while (cursor[size] != '\0') {
        ++size;
    }
    (void)bda_fs_write_raw(file, contents, size);
    (void)bda_fs_close_raw(file);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int result;

    (void)bda_fs_mkdir("A:\\gameboy");
    create_fixture("A:\\gameboy\\SELECT.GB", "selector fixture\n");
    create_fixture("A:\\gameboy\\SECOND.GBC", "selector fixture\n");
    create_fixture("A:\\gameboy\\HIDDEN.TXT", "must not be listed\n");

    result = bda_gui_select_file(
        &g_selector,
        "A:\\gameboy\\",
        "gb;gbc",
        "Select GB/GBC"
    );
    if (result == BDA_FILE_SELECTOR_SELECTED) {
        (void)bda_msgbox("SELECTED", g_selector.path);
    } else if (result == BDA_FILE_SELECTOR_CANCELLED) {
        (void)bda_msgbox("CANCELLED", "No file selected");
    } else {
        (void)bda_msgbox("ERROR", "File selector failed");
    }
    return 0;
}
