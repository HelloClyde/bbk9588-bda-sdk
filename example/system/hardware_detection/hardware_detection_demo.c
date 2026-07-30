/* Public read-only device and chip identification example. */
#include "bda_hardware.h"
#include "bda_dialogs.h"

static char g_message[256];

static char *append_text(char *out, const char *text) {
    while (*text != '\0') {
        *out++ = *text++;
    }
    return out;
}

static char *append_hex32(char *out, u32 value) {
    static const char digits[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        *out++ = digits[(value >> shift) & 0x0fu];
    }
    return out;
}

static char *append_line(char *out, const char *name, const char *value) {
    out = append_text(out, name);
    out = append_text(out, value);
    *out++ = '\n';
    return out;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_hardware_info_t info;
    char *out;

    bda_detect_hardware(&info);

    out = g_message;
    out = append_line(
        out, "DEVICE=", bda_device_model_name(info.device_model)
    );
    out = append_line(
        out, "CHIP=", bda_chip_model_name(info.chip_model)
    );
    out = append_text(out, "OS_SIG=");
    out = append_hex32(out, info.os_signature_address);
    *out++ = '\n';
    out = append_text(out, "ROM_SIG=");
    out = append_hex32(out, info.boot_rom_signature_address);
    *out++ = '\n';
    out = append_text(out, "GUI_738=");
    if (
        info.gui_screen_width_value ==
        BDA_HARDWARE_VALUE_NOT_QUERIED
    ) {
        out = append_text(out, "NOT_QUERIED");
    } else {
        out = append_hex32(out, (u32)info.gui_screen_width_value);
    }
    *out++ = '\n';
    out = append_text(
        out,
        info.device_model != BDA_DEVICE_MODEL_UNKNOWN &&
                info.chip_model != BDA_CHIP_MODEL_UNKNOWN
            ? "RESULT=DETECTED"
            : "RESULT=UNKNOWN"
    );
    *out = '\0';

    (void)bda_msgbox("Hardware Detect", g_message);
    return 0;
}
