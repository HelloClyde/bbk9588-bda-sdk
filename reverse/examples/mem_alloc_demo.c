#include "../bda_research_sdk.h"

static char g_text[96];

static void append_char(char **out, char *end, char c) {
    if (*out < end) {
        **out = c;
        *out += 1;
    }
}

static void append_text(char **out, char *end, const char *s) {
    while (*s) {
        append_char(out, end, *s++);
    }
}

static void append_hex_nibble(char **out, char *end, u32 value) {
    value &= 0x0fu;
    append_char(out, end, (char)(value < 10 ? ('0' + value) : ('A' + value - 10)));
}

static void append_hex32(char **out, char *end, u32 value) {
    int shift;
    append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        append_hex_nibble(out, end, value >> shift);
    }
}

static void finish_text(char **out, char *end) {
    if (*out >= end) {
        end[-1] = 0;
    } else {
        **out = 0;
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u8 *buffer = (u8 *)bda_alloc(64);
    char *out = g_text;
    char *end = g_text + sizeof(g_text) - 1;
    u32 checksum = 0;
    int i;

    if (buffer == 0) {
        bda_msgbox("MemDemo", "alloc failed");
        return 0;
    }

    for (i = 0; i < 64; ++i) {
        buffer[i] = (u8)(i + 1);
        checksum += buffer[i];
    }

    append_text(&out, end, "alloc=ok\nsum=");
    append_hex32(&out, end, checksum);
    append_text(&out, end, "\nfree=done");
    finish_text(&out, end);

    bda_free(buffer);
    bda_msgbox("MemDemo", g_text);
    return 0;
}
