#include "../sdk/bda_sdk.h"

static char g_message[640];
static unsigned char g_find_data[512];
static const char g_app_program_dir[] = "\\\xd3\xa6\xd3\xc3\\\xb3\xcc\xd0\xf2";

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

static void try_find(char **out, const char *name, const char *pattern, u32 attr) {
    bda_memset(g_find_data, 0, sizeof(g_find_data));
    int ret = bda_fs_findfirst_like(pattern, attr, g_find_data);
    append_line(out, name, ret);
    if (ret != -1) {
        bda_fs_findclose_like(g_find_data);
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    char *out = g_message;
    append_line(&out, "ready", bda_fs_storage_ready_like());
    append_line(&out, "chRoot", bda_fs_chdir_like("\\"));
    try_find(&out, "rootStar", "\\*.*", 0x27);
    try_find(&out, "dotStar", "*.*", 0x27);
    append_line(&out, "chApp", bda_fs_chdir_like(g_app_program_dir));
    try_find(&out, "appBda", "*.bda", 0x27);
    try_find(&out, "appAll", "*.*", 0x27);
    append_char(&out, 0);
    bda_msgbox("FSFindChdir", g_message);
    return 0;
}
