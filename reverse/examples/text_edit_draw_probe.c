#include "bda_sdk.h"

static char g_message[160];

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

static void append_line(char **out, const char *name, unsigned int value) {
    append_text(out, name);
    append_text(out, "=0x");
    append_hex32(out, value);
    append_char(out, '\n');
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_handle_t edit = bda_gui_create_window_like(
        "edit",
        "edit control text",
        1,
        0,
        103,
        16,
        16,
        210,
        30,
        0,
        0
    );

    int draw = bda_gui_draw_text_like(edit, 4, 4, "draw on edit", -1);

    char *out = g_message;
    append_line(&out, "edit", (unsigned int)edit);
    append_line(&out, "draw", (unsigned int)draw);
    append_char(&out, 0);
    bda_msgbox("TextEditDraw", g_message);
    return 0;
}
