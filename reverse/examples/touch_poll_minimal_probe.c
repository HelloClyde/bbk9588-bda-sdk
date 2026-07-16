#include "../bda_research_sdk.h"

static const char k_log_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHAPI.TXT";
static char g_message[80];

static int firmware_pen_down(void) {
    typedef int (*pen_down_fn)(void);
    pen_down_fn fn = (pen_down_fn)0x80059f68u;
    return fn();
}

static char *append_text(char *out, const char *text) {
    while (*text) {
        *out++ = *text++;
    }
    return out;
}

static char *append_dec(char *out, u32 value) {
    char digits[10];
    int count = 0;
    if (value == 0) {
        *out++ = '0';
        return out;
    }
    while (value) {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    }
    while (count) {
        *out++ = digits[--count];
    }
    return out;
}

static void build_message(u16 x, u16 y) {
    char *out = g_message;
    out = append_text(out, "DOWN=1 X=");
    out = append_dec(out, x);
    out = append_text(out, " Y=");
    out = append_dec(out, y);
    *out = 0;
}

static void write_log(void) {
    int file = bda_fs_fopen_raw(k_log_path, "wb");
    u32 length = 0;
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    while (g_message[length]) {
        ++length;
    }
    (void)bda_fs_write_raw(file, g_message, length);
    (void)bda_fs_close_raw(file);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u16 x = 0xffffu;
    u16 y = 0xffffu;
    int retry;

    bda_msgbox("Touch", "Press the screen");
    for (;;) {
        if (firmware_pen_down()) {
            for (retry = 0; retry < 16; ++retry) {
                bda_sys_delay_like(2);
                bda_gui_touch_position_like(&x, &y);
                if (x < 239u && y < 319u) {
                    break;
                }
            }
            build_message(x, y);
            write_log();
            bda_msgbox("Touch", g_message);
            while (firmware_pen_down()) {
                bda_sys_delay_like(1);
            }
            return 0;
        }
        bda_sys_delay_like(1);
    }
}
