#include "bda_sdk.h"

static char g_result_message[128];

static void append_char(char **out, char value) {
    **out = value;
    *out += 1;
}

static void append_text(char **out, const char *text) {
    while (*text) {
        append_char(out, *text++);
    }
}

static void append_hex32(char **out, unsigned int value) {
    static const char digits[] = "0123456789ABCDEF";
    for (int shift = 28; shift >= 0; shift -= 4) {
        append_char(out, digits[(value >> shift) & 0x0f]);
    }
}

static void append_result(char **out, const char *label, int value) {
    append_text(out, label);
    append_text(out, "=0x");
    append_hex32(out, (unsigned int)value);
    append_char(out, '\n');
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int yes_result = bda_confirm(
        "Confirm 1/2",
        "Press the LEFT button (YES)"
    );
    int no_result = bda_confirm(
        "Confirm 2/2",
        "Press the RIGHT button (NO)"
    );

    char *out = g_result_message;
    append_result(&out, "LEFT", yes_result);
    append_result(&out, "RIGHT", no_result);
    append_text(
        &out,
        yes_result == BDA_DIALOG_RESULT_YES &&
                no_result == BDA_DIALOG_RESULT_NO
            ? "RESULT=PASS"
            : "RESULT=FAIL"
    );
    append_char(&out, 0);

    bda_msgbox("Confirm result", g_result_message);
    return 0;
}
