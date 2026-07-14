#include "bda_sdk.h"

static const char p0[] = "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p1[] = "a:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p2[] = "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p3[] = "\\shell\\text_A.dlx";
static const char p4[] = "\\Shell\\text_A.dlx";
static const char p5[] = "A:\\\xcf\xb5\xcd\xb3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p6[] = "a:\\\xcf\xb5\xcd\xb3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p7[] = "\\\xcf\xb5\xcd\xb3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";

static char g_msg[384];

static char *append_char(char *out, char *end, char c) {
    if (out < end) {
        *out++ = c;
    }
    return out;
}

static char *append_str(char *out, char *end, const char *s) {
    while (*s && out < end) {
        *out++ = *s++;
    }
    return out;
}

static char *append_hex8(char *out, char *end, unsigned int value) {
    static const char hex[] = "0123456789ABCDEF";
    for (int i = 7; i >= 0; --i) {
        out = append_char(out, end, hex[(value >> (i * 4)) & 0xf]);
    }
    return out;
}

static int try_open(const char *path) {
    int f = bda_fs_fopen_raw(path, "rb");
    if (f != 0 && (unsigned int)f != 0xffffffffu) {
        bda_fs_close_raw(f);
    }
    return f;
}

static const char *path_at(int index) {
    switch (index) {
    case 0:
        return p0;
    case 1:
        return p1;
    case 2:
        return p2;
    case 3:
        return p3;
    case 4:
        return p4;
    case 5:
        return p5;
    case 6:
        return p6;
    default:
        return p7;
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    char *out = g_msg;
    char *end = g_msg + sizeof(g_msg) - 1;

    out = append_str(out, end, "text_A open matrix\n");
    for (int i = 0; i < 8; ++i) {
        int r = try_open(path_at(i));
        out = append_char(out, end, '0' + i);
        out = append_char(out, end, '=');
        out = append_hex8(out, end, (unsigned int)r);
        out = append_char(out, end, '\n');
    }
    *out = 0;
    bda_msgbox("TextAPath", g_msg);
    return 0;
}
