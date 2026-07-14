#include "bda_sdk.h"

static char g_message[96];

static void append_char(char **out, char value) {
    **out = value;
    *out += 1;
}

static void append_text(char **out, const char *text) {
    while (*text) {
        append_char(out, *text++);
    }
}

static void append_hex_nibble(char **out, unsigned int value) {
    value &= 0x0f;
    append_char(out, (char)(value < 10 ? ('0' + value) : ('A' + value - 10)));
}

static void append_hex32(char **out, unsigned int value) {
    for (int shift = 28; shift >= 0; shift -= 4) {
        append_hex_nibble(out, value >> shift);
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_handle_t edit = bda_gui_create_window_like(
        "edit",
        "Hello native BDA",
        1,
        0,
        2,
        0,
        0,
        160,
        32,
        0,
        0
    );

    char *out = g_message;
    append_text(&out, "edit handle=0x");
    append_hex32(&out, (unsigned int)edit);
    append_char(&out, 0);
    bda_msgbox("WinProbe", g_message);
    return 0;
}
