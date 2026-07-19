#include "bda_dialogs.h"
#include "bda_filesystem.h"

static const char k_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\SDKWRA.TXT";
static const char k_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\SDKWRR.TXT";
static const char k_payload[] = "BDA-FS-WRITE-9588\r\n";
static char g_message[224];

typedef struct write_result {
    int open_write;
    int write_count;
    int tell_after_write;
    int error_after_write;
    int close_write;
    int open_read;
    int read_count;
    int close_read;
    int content_match;
} write_result_t;

static char *append_char(char *out, char *end, char value) {
    if (out < end) {
        *out++ = value;
    }
    return out;
}

static char *append_text(char *out, char *end, const char *text) {
    while (*text != 0) {
        out = append_char(out, end, *text++);
    }
    return out;
}

static char *append_dec(char *out, char *end, int value) {
    char digits[12];
    u32 magnitude;
    int count = 0;

    if (value < 0) {
        out = append_char(out, end, '-');
        magnitude = (u32)(0 - value);
    } else {
        magnitude = (u32)value;
    }
    if (magnitude == 0) {
        return append_char(out, end, '0');
    }
    while (magnitude != 0 && count < (int)sizeof(digits)) {
        digits[count++] = (char)('0' + magnitude % 10u);
        magnitude /= 10u;
    }
    while (count > 0) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static int bytes_equal(const char *left, const char *right, bda_size_t size) {
    while (size-- != 0) {
        if (*left++ != *right++) {
            return 0;
        }
    }
    return 1;
}

static void run_write_test(const char *path, write_result_t *result) {
    char readback[sizeof(k_payload)];
    int file;

    bda_memset(result, 0, sizeof(*result));
    bda_memset(readback, 0, sizeof(readback));
    result->open_write = bda_fs_fopen_raw(path, "wb");
    if (!bda_fs_file_is_valid(result->open_write)) {
        return;
    }

    file = result->open_write;
    result->write_count = bda_fs_fwrite_raw(
        k_payload,
        1,
        sizeof(k_payload) - 1,
        file
    );
    result->tell_after_write = bda_fs_tell_raw(file);
    result->error_after_write = bda_fs_error(file);
    result->close_write = bda_fs_close_raw(file);

    result->open_read = bda_fs_fopen_raw(path, "rb");
    if (!bda_fs_file_is_valid(result->open_read)) {
        return;
    }
    file = result->open_read;
    result->read_count = bda_fs_fread_raw(
        readback,
        1,
        sizeof(k_payload) - 1,
        file
    );
    result->close_read = bda_fs_close_raw(file);
    result->content_match =
        result->read_count == (int)(sizeof(k_payload) - 1) &&
        bytes_equal(readback, k_payload, sizeof(k_payload) - 1);
}

static char *append_result(
    char *out,
    char *end,
    const char *label,
    const write_result_t *result
) {
    out = append_text(out, end, label);
    out = append_text(out, end, " o=");
    out = append_dec(out, end, result->open_write);
    out = append_text(out, end, " w=");
    out = append_dec(out, end, result->write_count);
    out = append_text(out, end, " t=");
    out = append_dec(out, end, result->tell_after_write);
    out = append_text(out, end, " e=");
    out = append_dec(out, end, result->error_after_write);
    out = append_text(out, end, " r=");
    out = append_dec(out, end, result->read_count);
    out = append_text(out, end, " m=");
    out = append_dec(out, end, result->content_match);
    return append_text(out, end, "\n");
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    write_result_t result_a;
    write_result_t result_root;
    char *out = g_message;
    char *end = g_message + sizeof(g_message) - 1;

    run_write_test(k_path_a, &result_a);
    run_write_test(k_path_root, &result_root);
    out = append_result(out, end, "A", &result_a);
    out = append_result(out, end, "R", &result_root);
    *out = 0;
    bda_msgbox("FSWrite", g_message);
    return result_a.content_match || result_root.content_match ? 0 : 1;
}
