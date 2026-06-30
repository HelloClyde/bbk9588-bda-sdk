#include "../sdk/bda_sdk.h"

static const char k_debug_dir[] = "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\debug";
static const char k_log_path[] = "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\debug\\usbdebug.log";
static const char k_cmd_path[] = "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\debug\\cmd.txt";

static char g_line[192];
static char g_cmd[128];

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

static char *append_hex8(char *out, char *end, u32 value) {
    static const char hex[] = "0123456789ABCDEF";
    for (int i = 7; i >= 0; --i) {
        out = append_char(out, end, hex[(value >> (i * 4)) & 0xf]);
    }
    return out;
}

static int starts_with(const char *s, const char *prefix) {
    while (*prefix) {
        if (*s++ != *prefix++) {
            return 0;
        }
    }
    return 1;
}

static void strip_newline(char *s) {
    while (*s) {
        if (*s == '\r' || *s == '\n') {
            *s = 0;
            return;
        }
        ++s;
    }
}

static void log_line(const char *tag, const char *text) {
    int f = bda_fs_fopen_raw(k_log_path, "ab");
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;
    if (f == 0 || (u32)f == 0xffffffffu) {
        return;
    }
    out = append_str(out, end, "[BDA] ");
    out = append_str(out, end, tag);
    out = append_str(out, end, " ");
    out = append_str(out, end, text);
    out = append_str(out, end, "\r\n");
    *out = 0;
    bda_fs_fwrite_raw(g_line, 1, (bda_size_t)(out - g_line), f);
    bda_fs_close_raw(f);
}

static void log_hex(const char *tag, u32 value) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;
    out = append_hex8(out, end, value);
    *out = 0;
    log_line(tag, g_line);
}

static int read_command(void) {
    int f;
    int n;
    bda_memset(g_cmd, 0, sizeof(g_cmd));
    f = bda_fs_fopen_raw(k_cmd_path, "rb");
    if (f == 0 || (u32)f == 0xffffffffu) {
        return 0;
    }
    n = bda_fs_fread_raw(g_cmd, 1, sizeof(g_cmd) - 1, f);
    bda_fs_close_raw(f);
    bda_fs_remove_raw(k_cmd_path);
    if (n <= 0) {
        return 0;
    }
    g_cmd[n] = 0;
    strip_newline(g_cmd);
    return 1;
}

static void log_status(void) {
    log_hex("gui", (u32)bda_gui_table());
    log_hex("fs", (u32)bda_fs_table());
    log_hex("sys", (u32)bda_sys_table());
    log_hex("mem", (u32)bda_mem_table());
    log_hex("res", (u32)bda_res_table());
    log_hex("ready", (u32)bda_fs_storage_ready_like());
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u32 tick = 0;

    bda_fs_mkdir_like(k_debug_dir);
    log_line("boot", "UsbDebugBridge start");
    log_status();
    bda_msgbox("UsbDebug", "bridge started");

    for (;;) {
        if (read_command()) {
            log_line("cmd", g_cmd);
            if (starts_with(g_cmd, "quit")) {
                log_line("exit", "quit command");
                bda_msgbox("UsbDebug", "quit");
                return 0;
            }
            if (starts_with(g_cmd, "status")) {
                log_status();
            } else if (starts_with(g_cmd, "msg ")) {
                bda_msgbox("UsbDebug", g_cmd + 4);
                log_line("msg", "shown");
            } else if (starts_with(g_cmd, "ping")) {
                log_line("pong", "ok");
            } else {
                log_line("unknown", g_cmd);
            }
        }

        if ((tick & 0x1fu) == 0) {
            log_hex("tick", tick);
        }
        ++tick;
        bda_sys_delay_like(50000);
    }
}
