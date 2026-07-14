#include "bda_sdk.h"

static char g_message[256];
static bda_fs_find_data_like_t g_find_data;

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

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_fs_find_data_init_like(&g_find_data);
    int ret = bda_fs_findfirst_like("\\*.*", 0x00, &g_find_data);

    char *out = g_message;
    append_text(&out, "ret=");
    append_hex32(&out, (unsigned int)ret);
    append_text(&out, "\ndata=");
    for (int i = 0; i < 16; ++i) {
        append_hex8(&out, ((const unsigned char *)&g_find_data)[i]);
        append_char(&out, ' ');
    }
    if (ret != -1) {
        bda_fs_findclose_like(&g_find_data);
    }
    append_char(&out, 0);
    bda_msgbox("FSFindOne", g_message);
    return 0;
}
