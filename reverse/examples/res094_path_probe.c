#include "bda_sdk.h"

static char g_msg[192];

static char *put(char *p, const char *s) {
    while (*s) {
        *p++ = *s++;
    }
    return p;
}

static char *hex8(char *p, unsigned int v) {
    static const char h[] = "0123456789ABCDEF";
    for (int i = 7; i >= 0; --i) {
        *p++ = h[(v >> (i * 4)) & 0xf];
    }
    return p;
}

static char *put_hex_line(char *p, const char *name, unsigned int v) {
    p = put(p, name);
    *p++ = '=';
    p = hex8(p, v);
    *p++ = '\n';
    return p;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    unsigned int res = (unsigned int)bda_res_table();
    void *gui_table = bda_gui_table();
    unsigned int gui = (unsigned int)gui_table;

    bda_msgbox("RES094P", "path-style calls begin");

    int r0 = bda_res_entry_094_like("\\shell\\commonframe_A.dlx", 0);
    bda_msgbox("RES094P", "call 1 returned");

    int r1 = bda_res_entry_094_like("\\shell\\MessageBoxBlue.dlx", gui_table);
    bda_msgbox("RES094P", "call 2 returned");

    char *p = g_msg;
    p = put_hex_line(p, "res", res);
    p = put_hex_line(p, "gui", gui);
    p = put_hex_line(p, "path0", (unsigned int)r0);
    p = put_hex_line(p, "path1", (unsigned int)r1);
    *p = 0;

    bda_msgbox("RES094 Path", g_msg);
    return 0;
}
