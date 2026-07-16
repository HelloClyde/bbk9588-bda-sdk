#include "../bda_research_sdk.h"

static const char *CFG_PATH = "A:\\gba\\gba.cfg";
static const char *CFG_PATH_ALT = "a:\\gba\\gba.cfg";

static char g_text[224];
static char g_cwd[64];
static bda_fs_path_info_like_t g_info;

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

static void append_signed(char **out, char *end, int value) {
    if (value < 0) {
        append_char(out, end, '-');
        append_dec(out, end, (u32)(-value));
    } else {
        append_dec(out, end, (u32)value);
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
    char *out = g_text;
    char *end = g_text + sizeof(g_text) - 1;
    int media = bda_fs_media_present_raw_like();
    int ready = bda_fs_storage_ready_like();
    int cwd_need = bda_fs_getcwd_like(g_cwd, sizeof(g_cwd));
    int info_a;
    int stat_a = bda_fs_stat_like(CFG_PATH, 0);
    int stat_b = bda_fs_stat_like(CFG_PATH_ALT, 0);
    bda_fs_path_info_init_like(&g_info);
    info_a = bda_fs_path_info_like(CFG_PATH, &g_info);

    append_text(&out, end, "media=");
    append_signed(&out, end, media);
    append_text(&out, end, "\nready=");
    append_signed(&out, end, ready);
    append_text(&out, end, "\ncwd need=");
    append_signed(&out, end, cwd_need);
    append_text(&out, end, "\ncwd=");
    append_text(&out, end, g_cwd);
    append_text(&out, end, "\nstat A=");
    append_signed(&out, end, stat_a);
    append_text(&out, end, " info=");
    append_signed(&out, end, info_a);
    append_text(&out, end, " size=");
    append_dec(&out, end, bda_fs_path_info_size_like(&g_info));
    append_text(&out, end, "\nstat a=");
    append_signed(&out, end, stat_b);
    append_text(&out, end, "\n-1 means missing/fail");
    finish_text(&out, end);

    bda_msgbox("FSStatus", g_text);
    return 0;
}
