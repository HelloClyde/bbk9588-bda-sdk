#include "../bda_research_sdk.h"

#define ARRAY_COUNT(a) ((u32)(sizeof(a) / sizeof((a)[0])))

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEAPI.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\GAMEAPI.TXT";

static const u32 k_alloc_sizes[] = {
    64u,
    4096u,
    64u * 1024u,
    256u * 1024u,
    1024u * 1024u,
    2u * 1024u * 1024u,
    4u * 1024u * 1024u,
};

static const char *g_log_path;
static char g_line[160];

static char *append_char(char *out, char *end, char value) {
    if (out < end) {
        *out++ = value;
    }
    return out;
}

static char *append_text(char *out, char *end, const char *text) {
    while (*text && out < end) {
        *out++ = *text++;
    }
    return out;
}

static char *append_u32(char *out, char *end, u32 value) {
    char digits[10];
    int count = 0;

    do {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    } while (value && count < (int)sizeof(digits));
    while (count > 0) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char hex[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        out = append_char(out, end, hex[(value >> shift) & 0x0fu]);
    }
    return out;
}

static int open_log(const char *mode) {
    int file;

    if (g_log_path) {
        return bda_fs_fopen_raw(g_log_path, mode);
    }
    file = bda_fs_fopen_raw(k_log_path_a, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = k_log_path_a;
        return file;
    }
    file = bda_fs_fopen_raw(k_log_path_root, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = k_log_path_root;
    }
    return file;
}

static void reset_log(void) {
    int file;

    g_log_path = 0;
    file = open_log("wb");
    if (bda_fs_file_is_valid(file)) {
        (void)bda_fs_close_raw(file);
    }
}

static void write_line(char *end) {
    int file;
    u32 length;

    end = append_text(end, g_line + sizeof(g_line) - 1, "\r\n");
    *end = 0;
    length = (u32)(end - g_line);
    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_line, length);
    (void)bda_fs_close_raw(file);
}

static void log_text(const char *text) {
    write_line(append_text(g_line, g_line + sizeof(g_line) - 1, text));
}

static void log_value(const char *label, u32 value) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, value);
    write_line(out);
}

static u32 read_cp0_count(void) {
    u32 value;

    __asm__ volatile("mfc0 %0, $9" : "=r"(value));
    return value;
}

static int probe_display_metrics(void) {
    u32 metric;
    int failures = 0;

    log_text("[DISPLAY]");
    for (metric = 0; metric <= 7u; ++metric) {
        int value = bda_gui_display_metric_like(0, metric);
        char *out = g_line;
        char *end = g_line + sizeof(g_line) - 1;

        out = append_text(out, end, "METRIC ");
        out = append_u32(out, end, metric);
        out = append_text(out, end, "=");
        out = append_hex32(out, end, (u32)value);
        write_line(out);
        if (metric == BDA_GUI_DISPLAY_METRIC_PIXEL_BYTES_LIKE && value <= 0) {
            ++failures;
        }
        if (metric == 7u && value != -1) {
            ++failures;
        }
    }
    return failures;
}

static int probe_cp0_count(void) {
    static const u32 delays[] = {1u, 100u, 1000u};
    u32 i;
    int failures = 0;

    log_text("[COUNT]");
    for (i = 0; i < ARRAY_COUNT(delays); ++i) {
        u32 before = read_cp0_count();
        u32 after;
        char *out;
        char *end;

        bda_sys_delay_like(delays[i]);
        after = read_cp0_count();
        out = g_line;
        end = g_line + sizeof(g_line) - 1;
        out = append_text(out, end, "DELAY ");
        out = append_u32(out, end, delays[i]);
        out = append_text(out, end, " COUNT_DELTA=");
        out = append_hex32(out, end, after - before);
        write_line(out);
        if (after == before) {
            ++failures;
        }
    }
    return failures;
}

static int verify_edges(u8 *buffer, u32 size, u8 seed) {
    u32 middle = size / 2u;

    buffer[0] = seed;
    buffer[middle] = (u8)(seed ^ 0x5au);
    buffer[size - 1u] = (u8)(seed ^ 0xa5u);
    return buffer[0] == seed &&
        buffer[middle] == (u8)(seed ^ 0x5au) &&
        buffer[size - 1u] == (u8)(seed ^ 0xa5u);
}

static int probe_alloc_free(void) {
    u32 i;
    int failures = 0;

    log_text("[ALLOC_FREE]");
    for (i = 0; i < ARRAY_COUNT(k_alloc_sizes); ++i) {
        u32 size = k_alloc_sizes[i];
        u8 *buffer = (u8 *)bda_alloc(size);
        int edges_ok = buffer && verify_edges(buffer, size, (u8)(0x31u + i));
        char *out = g_line;
        char *end = g_line + sizeof(g_line) - 1;

        out = append_text(out, end, "SIZE=");
        out = append_u32(out, end, size);
        out = append_text(out, end, " PTR=");
        out = append_hex32(out, end, (u32)buffer);
        out = append_text(out, end, " EDGE=");
        out = append_text(out, end, edges_ok ? "PASS" : "FAIL");
        write_line(out);
        if (!edges_ok) {
            ++failures;
        }
        if (buffer) {
            bda_free(buffer);
        }
    }
    return failures;
}

static int probe_calloc(void) {
    u8 *buffer;
    u32 i;
    int zeroed = 1;

    log_text("[CALLOC]");
    buffer = (u8 *)bda_calloc_like(32u, 16u);
    if (!buffer) {
        log_text("CALLOC PTR=0 RESULT=FAIL");
        return 1;
    }
    for (i = 0; i < 512u; ++i) {
        if (buffer[i] != 0) {
            zeroed = 0;
            break;
        }
    }
    log_text(zeroed ? "CALLOC ZERO=PASS" : "CALLOC ZERO=FAIL");
    bda_free(buffer);
    return zeroed ? 0 : 1;
}

static int probe_realloc(void) {
    u8 *buffer;
    u8 *old_buffer;
    u8 *next;
    u32 i;
    int preserved = 1;

    log_text("[REALLOC]");
    buffer = (u8 *)bda_alloc(128u);
    if (!buffer) {
        log_text("REALLOC INITIAL=FAIL");
        return 1;
    }
    for (i = 0; i < 128u; ++i) {
        buffer[i] = (u8)(i ^ 0xa5u);
    }

    old_buffer = buffer;
    next = (u8 *)bda_realloc_like(buffer, 4096u);
    if (!next) {
        log_text("REALLOC GROW=FAIL");
        bda_free(old_buffer);
        return 1;
    }
    buffer = next;
    for (i = 0; i < 128u; ++i) {
        if (buffer[i] != (u8)(i ^ 0xa5u)) {
            preserved = 0;
            break;
        }
    }
    log_text(preserved ? "REALLOC GROW_PRESERVE=PASS" : "REALLOC GROW_PRESERVE=FAIL");

    old_buffer = buffer;
    next = (u8 *)bda_realloc_like(buffer, 64u);
    if (!next) {
        log_text("REALLOC SHRINK=FAIL");
        bda_free(old_buffer);
        return 1;
    }
    buffer = next;
    for (i = 0; i < 64u; ++i) {
        if (buffer[i] != (u8)(i ^ 0xa5u)) {
            preserved = 0;
            break;
        }
    }
    log_text(preserved ? "REALLOC SHRINK_PRESERVE=PASS" : "REALLOC SHRINK_PRESERVE=FAIL");
    bda_free(buffer);
    return preserved ? 0 : 1;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int failures = 0;

    reset_log();
    log_text("START GAME API PROBE V1");
    failures += probe_display_metrics();
    failures += probe_cp0_count();
    failures += probe_alloc_free();
    failures += probe_calloc();
    failures += probe_realloc();
    log_value("FAILURES=", (u32)failures);
    log_text(failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END GAME API PROBE V1");
    return failures ? 1 : 0;
}
