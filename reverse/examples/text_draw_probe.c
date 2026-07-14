#include "bda_sdk.h"

static char g_message[320];

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

static void append_hex8(char **out, unsigned int value) {
    append_hex_nibble(out, value >> 4);
    append_hex_nibble(out, value);
}

static void append_hex32(char **out, unsigned int value) {
    append_hex8(out, value >> 24);
    append_hex8(out, value >> 16);
    append_hex8(out, value >> 8);
    append_hex8(out, value);
}

static void append_line(char **out, const char *name, unsigned int value) {
    append_text(out, name);
    append_char(out, '=');
    append_hex32(out, value);
    append_char(out, '\n');
}

static void short_wait(void) {
    for (int i = 0; i < 40; ++i) {
        bda_gui_draw_guard_end_like();
        bda_sys_delay_like(0xc350);
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_handle_t edit = bda_gui_create_window_like(
        "edit",
        "edit control text",
        1,
        0,
        101,
        16,
        16,
        210,
        30,
        0,
        0
    );

    int mode0 = bda_gui_set_text_mode_like(0, 1);
    int color0 = bda_gui_rgb_like(0, 255, 255, 255);
    int set0 = bda_gui_set_text_color_like(0, color0);
    int draw0 = bda_gui_draw_text_like(0, 20, 70, "draw_text handle 0", -1);

    int mode_edit = bda_gui_set_text_mode_like(edit, 1);
    int color_edit = bda_gui_rgb_like(edit, 255, 0, 0);
    int set_edit = bda_gui_set_text_color_like(edit, color_edit);
    int draw_edit = bda_gui_draw_text_like(edit, 20, 110, "draw_text edit handle", -1);

    bda_gui_draw_guard_end_like();
    short_wait();

    char *out = g_message;
    append_line(&out, "edit", (unsigned int)edit);
    append_line(&out, "mode0", (unsigned int)mode0);
    append_line(&out, "color0", (unsigned int)color0);
    append_line(&out, "set0", (unsigned int)set0);
    append_line(&out, "draw0", (unsigned int)draw0);
    append_line(&out, "modeE", (unsigned int)mode_edit);
    append_line(&out, "colorE", (unsigned int)color_edit);
    append_line(&out, "setE", (unsigned int)set_edit);
    append_line(&out, "drawE", (unsigned int)draw_edit);
    append_char(&out, 0);

    bda_msgbox("TextDrawProbe", g_message);
    return 0;
}
