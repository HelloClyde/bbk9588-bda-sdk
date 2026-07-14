#include "bda_sdk.h"

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

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_fs_disk_info_like_t info;
    char *out = g_text;
    char *end = g_text + sizeof(g_text) - 1;
    int ready;
    int ret;

    bda_memset(&info, 0, sizeof(info));
    ready = bda_fs_storage_ready_like();
    ret = bda_fs_diskinfo_like(0, &info);

    append_text(&out, end, "ready=");
    append_dec(&out, end, (u32)ready);
    append_text(&out, end, "\ndiskinfo=");
    append_dec(&out, end, ret >= 0 ? (u32)ret : 0);
    append_text(&out, end, "\nfree=");
    append_dec(&out, end, ret == 0 ? bda_fs_disk_free_bytes_like(&info) : 0);
    append_text(&out, end, "\nsector=");
    append_dec(&out, end, info.bytes_per_sector);

    finish_text(&out, end);
    bda_msgbox("FSDisk", g_text);
    return 0;
}
