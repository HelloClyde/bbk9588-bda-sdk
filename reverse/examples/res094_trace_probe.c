#include "../sdk/bda_sdk.h"

static char g_msg[192];

static void hex8(char *out, u32 v) {
    static const char h[] = "0123456789ABCDEF";
    int i;
    for (i = 0; i < 8; ++i) {
        out[i] = h[(v >> (28 - i * 4)) & 0xfu];
    }
    out[8] = 0;
}

static char *put(char *p, const char *s) {
    while (*s) {
        *p++ = *s++;
    }
    return p;
}

static char *put_hex_line(char *p, const char *label, u32 value) {
    p = put(p, label);
    hex8(p, value);
    p += 8;
    *p++ = '\n';
    *p = 0;
    return p;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int r0;
    int r1;
    int r2;
    char *p = g_msg;

    bda_msgbox("RES094", "trace calls begin");
    r0 = bda_res_entry_094_like("RES094 literal trace\n", 0);
    r1 = bda_res_entry_094_like("RES094 gui=%x\n", bda_gui_table());
    r2 = bda_res_entry_094_like("RES094 fs=%x\n", bda_fs_table());

    p = put_hex_line(p, "literal=", (u32)r0);
    p = put_hex_line(p, "gui_fmt=", (u32)r1);
    p = put_hex_line(p, "fs_fmt=", (u32)r2);
    p = put_hex_line(p, "res_tbl=", (u32)bda_res_table());
    bda_msgbox("RES094 Trace", g_msg);
    return 0;
}
