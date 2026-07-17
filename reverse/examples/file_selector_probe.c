#include "../bda_research_sdk.h"

static char g_message[512];
static char g_path[260];
static unsigned char g_dir_state[512];

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

static void append_result(char **out, const char *name, int value) {
    append_text(out, name);
    append_text(out, "=0x");
    append_hex32(out, (unsigned int)value);
    append_char(out, '\n');
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_file_selector_like_t selector;
    bda_memset(&selector, 0, sizeof(selector));
    bda_memset(g_path, 0, sizeof(g_path));
    bda_memset(g_dir_state, 0, sizeof(g_dir_state));

    selector.out_path = g_path;
    selector.extensions = "gba";
    selector.dir_state = g_dir_state;
    selector.title = "Select game";
    selector.selected_index = -1;
    selector.sentinel20 = -1;
    selector.sentinel24 = -1;

    int r_open = bda_gui_file_selector_open_like(1);
    int r_update = 0;
    for (int i = 0; i < 16; ++i) {
        r_update = bda_gui_file_selector_update_like(&selector);
        if (g_path[0] || r_update != 0) {
            break;
        }
        bda_sys_delay_like(0x1000);
    }
    void *nth0 = bda_gui_list_nth_like(0, 0);

    char *out = g_message;
    append_result(&out, "open", r_open);
    append_result(&out, "update", r_update);
    append_result(&out, "nth0", (int)nth0);
    append_text(&out, "close=not-selector-close\n");
    append_text(&out, "path=");
    append_text(&out, g_path[0] ? g_path : "(empty)");
    append_char(&out, 0);

    bda_msgbox("FileSelectProbe", g_message);
    return 0;
}
