#include "../bda_research_sdk.h"

static const char *CFG_PATH = "A:\\gba\\gba.cfg";
static const char *CFG_PATH_ALT = "a:\\gba\\gba.cfg";

static char g_text[192];

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

static void append_dec(char **out, char *end, u32 value) {
    char tmp[10];
    int n = 0;
    if (value == 0) {
        append_char(out, end, '0');
        return;
    }
    while (value && n < (int)sizeof(tmp)) {
        tmp[n++] = (char)('0' + (value % 10));
        value /= 10;
    }
    while (n > 0) {
        append_char(out, end, tmp[--n]);
    }
}

static void finish_text(char **out, char *end) {
    if (*out >= end) {
        end[-1] = 0;
    } else {
        **out = 0;
    }
}

static int open_cfg(void) {
    int file = bda_fs_fopen_raw(CFG_PATH, "rb");
    if (!bda_fs_file_is_valid(file)) {
        file = bda_fs_fopen_raw(CFG_PATH_ALT, "rb");
    }
    return file;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    char buffer[32];
    char *out = g_text;
    char *end = g_text + sizeof(g_text) - 1;
    int file;
    int got;

    file = open_cfg();
    if (!bda_fs_file_is_valid(file)) {
        append_text(&out, end, "open failed\nready=");
        append_dec(&out, end, (u32)bda_fs_storage_ready_like());
        finish_text(&out, end);
        bda_msgbox("FSRaw", g_text);
        return 0;
    }

    bda_memset(buffer, 0, sizeof(buffer));
    got = bda_fs_read_raw(file, buffer, sizeof(buffer) - 1);
    bda_fs_close_raw(file);

    append_text(&out, end, "read_raw=");
    append_dec(&out, end, got > 0 ? (u32)got : 0);
    append_text(&out, end, "\nfirst=");
    if (got > 0) {
        append_dec(&out, end, (u32)(unsigned char)buffer[0]);
    } else {
        append_text(&out, end, "none");
    }
    finish_text(&out, end);
    bda_msgbox("FSRaw", g_text);
    return 0;
}
