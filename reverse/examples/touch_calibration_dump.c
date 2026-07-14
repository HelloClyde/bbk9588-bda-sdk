#include "bda_sdk.h"

static const char k_log_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\TOUCHCAL.TXT";
static char g_dump[512];

static char hex_digit(u32 value) {
    return (char)(value < 10u ? '0' + value : 'A' + value - 10u);
}

static void build_dump(void) {
    volatile const u8 *source = (volatile const u8 *)0x807f7110u;
    char *out = g_dump;
    int row;
    int column;
    for (row = 0; row < 5; ++row) {
        u32 offset = (u32)(row * 16);
        *out++ = hex_digit((offset >> 4) & 0x0fu);
        *out++ = hex_digit(offset & 0x0fu);
        *out++ = ':';
        for (column = 0; column < 16; ++column) {
            u8 value = source[offset + (u32)column];
            *out++ = ' ';
            *out++ = hex_digit(value >> 4);
            *out++ = hex_digit(value & 0x0fu);
        }
        *out++ = '\r';
        *out++ = '\n';
    }
    *out = 0;
}

static void write_dump(void) {
    int file = bda_fs_fopen_raw(k_log_path, "wb");
    u32 length = 0;
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    while (g_dump[length]) {
        ++length;
    }
    (void)bda_fs_write_raw(file, g_dump, length);
    (void)bda_fs_close_raw(file);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    build_dump();
    write_dump();
    bda_msgbox("TouchCal", "Calibration state dumped");
    return 0;
}
