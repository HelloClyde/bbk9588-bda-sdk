#include "bda_dialogs.h"
#include "bda_filesystem.h"
#include "bda_input.h"
#include "bda_time.h"

/*
 * Historical fixed-address probe. FastTouchV2 proved that this address does
 * not contain the same function on the tested hardware and may hang the unit.
 */
static int unsafe_touch_pressed_fixed_va(void) {
    typedef int (*fn_t)(void);
    return ((fn_t)0x80059f68u)();
}

static const char k_log_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHPRESS.TXT";
static const char k_result[] = "PRESS=1 RELEASE=1";

static void write_result(void) {
    int file = bda_fs_fopen_raw(k_log_path, "wb");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, k_result, sizeof(k_result) - 1u);
    (void)bda_fs_close_raw(file);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_msgbox("Touch", "Press and release the screen");

    while (!unsafe_touch_pressed_fixed_va()) {
        bda_sys_delay(1);
    }
    while (unsafe_touch_pressed_fixed_va()) {
        bda_sys_delay(1);
    }

    write_result();
    bda_msgbox("Touch", "PRESS + RELEASE OK");
    return 0;
}
