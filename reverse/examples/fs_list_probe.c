#include "../sdk/bda_sdk.h"

static char g_message[640];
static unsigned char g_find_data[512];

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

static void append_hex_byte(char **out, unsigned int value) {
    append_hex_nibble(out, value >> 4);
    append_hex_nibble(out, value);
}

static void append_hex32(char **out, unsigned int value) {
    for (int shift = 28; shift >= 0; shift -= 4) {
        append_hex_nibble(out, value >> shift);
    }
}

static void append_dump(char **out, const unsigned char *data, unsigned int count) {
    for (unsigned int i = 0; i < count; ++i) {
        if (i && (i % 16) == 0) {
            append_char(out, '\n');
        }
        append_hex_byte(out, data[i]);
        append_char(out, ' ');
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    char *out = g_message;
    bda_memset(g_find_data, 0, sizeof(g_find_data));

    append_text(&out, "ready=");
    append_hex32(&out, (unsigned int)bda_fs_storage_ready_like());
    append_char(&out, '\n');

    int first = bda_fs_findfirst_like("a:\\*.*", 0x27, g_find_data);
    append_text(&out, "findfirst=");
    append_hex32(&out, (unsigned int)first);
    append_char(&out, '\n');
    append_dump(&out, g_find_data, 96);

    if (first != -1) {
        int next = bda_fs_findnext_like(g_find_data);
        append_text(&out, "\nnext=");
        append_hex32(&out, (unsigned int)next);
        append_char(&out, '\n');
        append_dump(&out, g_find_data, 64);
        bda_fs_findclose_like(g_find_data);
    }

    append_char(&out, 0);
    bda_msgbox("FSProbe", g_message);
    return 0;
}
