#include "bda_dialogs.h"

static const char k_log_path[] = "A:\\DIALOG6.LOG";
static char g_result_message[160];

static char *append_char(char *out, char value) {
    *out = value;
    return out + 1;
}

static char *append_text(char *out, const char *text) {
    while (*text) {
        *out++ = *text++;
    }
    return out;
}

static char *append_hex32(char *out, unsigned int value) {
    static const char digits[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        *out++ = digits[(value >> shift) & 0x0f];
    }
    return out;
}

static void reset_log(void) {
    int file = bda_fs_fopen_raw(k_log_path, "wb");
    if (bda_fs_file_is_valid(file)) {
        (void)bda_fs_close_raw(file);
    }
}

static void log_result(const char *position, int result) {
    char line[64];
    char *out = line;
    int file;

    out = append_text(out, position);
    out = append_text(out, "=");
    out = append_hex32(out, (unsigned int)result);
    out = append_text(out, "\r\n");

    file = bda_fs_fopen_raw(k_log_path, "ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, line, (u32)(out - line));
    (void)bda_fs_close_raw(file);
}

static int run_probe(const char *title, const char *message, const char *position) {
    int result = bda_confirm_yes_all_no(title, message);
    log_result(position, result);
    return result;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int left_result;
    int middle_result;
    int right_result;
    char *out;

    reset_log();
    left_result = run_probe("Three 1/3", "Press the LEFT button", "LEFT");
    middle_result = run_probe("Three 2/3", "Press the MIDDLE button", "MIDDLE");
    right_result = run_probe("Three 3/3", "Press the RIGHT button", "RIGHT");

    out = g_result_message;
    out = append_text(out, "L=");
    out = append_hex32(out, (unsigned int)left_result);
    out = append_text(out, " M=");
    out = append_hex32(out, (unsigned int)middle_result);
    out = append_text(out, " R=");
    out = append_hex32(out, (unsigned int)right_result);
    out = append_char(out, '\n');
    out = append_text(
        out,
        left_result == BDA_DIALOG_RESULT_YES &&
                middle_result == BDA_DIALOG_RESULT_ALL &&
                right_result == BDA_DIALOG_RESULT_NO
            ? "RESULT=PASS"
            : "RESULT=FAIL"
    );
    (void)append_char(out, 0);

    (void)bda_msgbox("Three-button result", g_result_message);
    return 0;
}
