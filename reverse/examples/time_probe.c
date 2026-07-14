#include "bda_sdk.h"

static bda_sys_alarm_record_like_t g_due_alarm_data;
static bda_sys_alarm_record_like_t g_alarm_data[3];
static char g_msg[760];

static char *append_char(char *p, char c) {
    *p++ = c;
    *p = 0;
    return p;
}

static char *append_str(char *p, const char *s) {
    while (*s) {
        *p++ = *s++;
    }
    *p = 0;
    return p;
}

static char *append_hex8(char *p, unsigned int v) {
    static const char hex[] = "0123456789ABCDEF";
    *p++ = hex[(v >> 4) & 15];
    *p++ = hex[v & 15];
    *p = 0;
    return p;
}

static char *append_hex32(char *p, unsigned int v) {
    p = append_str(p, "0x");
    p = append_hex8(p, (v >> 24) & 255);
    p = append_hex8(p, (v >> 16) & 255);
    p = append_hex8(p, (v >> 8) & 255);
    return append_hex8(p, v & 255);
}

static char *append_dump(char *p, const unsigned char *buf, unsigned int n) {
    unsigned int i;
    for (i = 0; i < n; ++i) {
        if (i && ((i & 15) == 0)) {
            p = append_char(p, '\n');
        } else if (i) {
            p = append_char(p, ' ');
        }
        p = append_hex8(p, buf[i]);
    }
    return p;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int rt;
    int ra0;
    int ra1;
    int ra2;
    char *p = g_msg;

    bda_memset(&g_due_alarm_data, 0, sizeof(g_due_alarm_data));
    bda_memset(g_alarm_data, 0, sizeof(g_alarm_data));
    bda_memset(g_msg, 0, sizeof(g_msg));

    rt = bda_sys_alarm_due_get_like(&g_due_alarm_data);
    ra0 = bda_sys_alarm_get_like(&g_alarm_data[0], 0);
    ra1 = bda_sys_alarm_get_like(&g_alarm_data[1], 1);
    ra2 = bda_sys_alarm_get_like(&g_alarm_data[2], 2);

    p = append_str(p, "due ret=");
    p = append_hex32(p, (unsigned int)rt);
    p = append_char(p, '\n');
    p = append_dump(p, g_due_alarm_data.raw, 48);

    p = append_str(p, "\nA0 ret=");
    p = append_hex32(p, (unsigned int)ra0);
    p = append_char(p, '\n');
    p = append_dump(p, g_alarm_data[0].raw, 32);

    p = append_str(p, "\nA1 ret=");
    p = append_hex32(p, (unsigned int)ra1);
    p = append_char(p, '\n');
    p = append_dump(p, g_alarm_data[1].raw, 32);

    p = append_str(p, "\nA2 ret=");
    p = append_hex32(p, (unsigned int)ra2);
    p = append_char(p, '\n');
    p = append_dump(p, g_alarm_data[2].raw, 32);

    bda_msgbox("TimeProbe", g_msg);
    return 0;
}
