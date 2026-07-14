#include "bda_sdk.h"

static char g_message[900];
static bda_fs_find_data_like_t g_find_data;

typedef struct find_case {
    const char *name;
    const char *pattern;
    u32 attr;
} find_case_t;

static const find_case_t g_cases[] = {
    {"root00", "\\*.*", 0x00},
    {"root01", "\\*.*", 0x01},
    {"root06", "\\*.*", 0x06},
    {"root10", "\\*.*", 0x10},
    {"root27", "\\*.*", 0x27},
    {"bda01", "\\*.bda", 0x01},
    {"bda06", "\\*.bda", 0x06},
    {"bda27", "\\*.bda", 0x27},
    {"Aroot", "A:\\*.*", 0x27},
    {"aroot", "a:\\*.*", 0x27},
    {"Broot", "B:\\*.*", 0x27},
    {"dot", "*.*", 0x27},
};

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

static void append_line(char **out, const char *name, int value) {
    append_text(out, name);
    append_char(out, '=');
    append_hex32(out, (unsigned int)value);
    append_char(out, '\n');
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    char *out = g_message;
    append_line(&out, "ready", bda_fs_storage_ready_like());

    for (unsigned int i = 0; i < sizeof(g_cases) / sizeof(g_cases[0]); ++i) {
        bda_fs_find_data_init_like(&g_find_data);
        int ret = bda_fs_findfirst_like(g_cases[i].pattern, g_cases[i].attr, &g_find_data);
        append_line(&out, g_cases[i].name, ret);
        if (ret != -1) {
            bda_fs_findclose_like(&g_find_data);
        }
    }

    append_char(&out, 0);
    bda_msgbox("FSFindMatrix", g_message);
    return 0;
}
