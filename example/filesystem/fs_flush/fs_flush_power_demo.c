#include "bda_dialogs.h"
#include "bda_filesystem.h"

#define PAYLOAD_SIZE 4096u

static const char k_stage_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\F74STG.DAT";
static const char k_flush_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\F74YES.DAT";
static const char k_control_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\F74NO.DAT";
static const char k_stage_marker[] = "phase2";

static char g_payload[PAYLOAD_SIZE];
static char g_readback[PAYLOAD_SIZE];
static char g_message[224];
static int g_flush_file;
static int g_control_file;

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

static char *append_int(char *out, char *end, int value) {
    char digits[12];
    u32 magnitude;
    int count = 0;

    if (value < 0) {
        out = append_char(out, end, '-');
        magnitude = 0u - (u32)value;
    } else {
        magnitude = (u32)value;
    }
    do {
        digits[count++] = (char)('0' + magnitude % 10u);
        magnitude /= 10u;
    } while (magnitude != 0);
    while (count > 0) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static void make_payload(void) {
    u32 index;

    for (index = 0; index < PAYLOAD_SIZE; ++index) {
        g_payload[index] = (char)((index * 29u + 7u) & 0xffu);
    }
}

static int payload_matches(void) {
    u32 index;

    for (index = 0; index < PAYLOAD_SIZE; ++index) {
        if (g_readback[index] != g_payload[index]) {
            return 0;
        }
    }
    return 1;
}

static int stage_marker_exists(void) {
    int file = bda_fs_fopen_raw(k_stage_path, "rb");

    if (!bda_fs_file_is_valid(file)) {
        return 0;
    }
    (void)bda_fs_close_raw(file);
    return 1;
}

static int create_stage_marker(void) {
    int file = bda_fs_fopen_raw(k_stage_path, "wb");
    int wrote;
    int closed;

    if (!bda_fs_file_is_valid(file)) {
        return 0;
    }
    wrote = bda_fs_write_raw(
        file, k_stage_marker, sizeof(k_stage_marker) - 1u
    );
    closed = bda_fs_close_raw(file);
    return wrote == (int)(sizeof(k_stage_marker) - 1u) && closed == 0;
}

static int read_and_check(const char *path, int *read_result) {
    int file = bda_fs_fopen_raw(path, "rb");

    *read_result = -1;
    if (!bda_fs_file_is_valid(file)) {
        return 0;
    }
    *read_result = bda_fs_read_raw(file, g_readback, PAYLOAD_SIZE);
    (void)bda_fs_close_raw(file);
    return *read_result == (int)PAYLOAD_SIZE && payload_matches();
}

static int run_phase1(void) {
    char *out = g_message;
    char *end = g_message + sizeof(g_message) - 1;
    int flushed_write;
    int flushed_error;
    int control_write;
    int control_error;

    if (!create_stage_marker()) {
        bda_msgbox("FS074 Power", "PHASE1 FAIL: stage marker");
        return 1;
    }

    g_flush_file = bda_fs_fopen_raw(k_flush_path, "wb");
    if (!bda_fs_file_is_valid(g_flush_file)) {
        bda_msgbox("FS074 Power", "PHASE1 FAIL: flush file open");
        return 1;
    }
    flushed_write = bda_fs_write_raw(
        g_flush_file, g_payload, PAYLOAD_SIZE
    );
    bda_fs_flush_all();
    flushed_error = bda_fs_error(g_flush_file);

    g_control_file = bda_fs_fopen_raw(k_control_path, "wb");
    if (bda_fs_file_is_valid(g_control_file)) {
        control_write = bda_fs_write_raw(
            g_control_file, g_payload, PAYLOAD_SIZE
        );
        control_error = bda_fs_error(g_control_file);
    } else {
        control_write = -1;
        control_error = -1;
    }

    out = append_text(out, end, "PHASE1 READY\nyes write=");
    out = append_int(out, end, flushed_write);
    out = append_text(out, end, " flush=done");
    out = append_text(out, end, " err=");
    out = append_int(out, end, flushed_error);
    out = append_text(out, end, "\nno write=");
    out = append_int(out, end, control_write);
    out = append_text(out, end, " err=");
    out = append_int(out, end, control_error);
    out = append_text(out, end, "\nFORCE STOP NOW");
    *out = 0;

    bda_msgbox("FS074 Power", g_message);
    return 0;
}

static int run_phase2(void) {
    char *out = g_message;
    char *end = g_message + sizeof(g_message) - 1;
    int flushed_read;
    int control_read;
    int flushed_match = read_and_check(k_flush_path, &flushed_read);
    int control_match = read_and_check(k_control_path, &control_read);

    out = append_text(out, end, "PHASE2 RESULT\nflushed read=");
    out = append_int(out, end, flushed_read);
    out = append_text(out, end, " match=");
    out = append_int(out, end, flushed_match);
    out = append_text(out, end, "\ncontrol read=");
    out = append_int(out, end, control_read);
    out = append_text(out, end, " match=");
    out = append_int(out, end, control_match);
    if (flushed_match && !control_match) {
        out = append_text(out, end, "\nSTRONG PASS");
    } else if (flushed_match) {
        out = append_text(out, end, "\nPASS, control also survived");
    } else {
        out = append_text(out, end, "\nFLUSH FAILED");
    }
    *out = 0;

    bda_msgbox("FS074 Power", g_message);
    return flushed_match ? 0 : 1;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    make_payload();
    return stage_marker_exists() ? run_phase2() : run_phase1();
}

