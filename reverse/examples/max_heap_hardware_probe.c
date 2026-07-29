#include "bda_dialogs.h"
#include "bda_filesystem.h"

/*
 * Conservative true-hardware probe for the largest single firmware-heap block.
 *
 * The result excludes a 256 KiB recovery reserve kept alive during every test.
 * Each candidate is freed before the next candidate. This measures contiguous
 * single-block capacity, not total heap capacity.
 */

#define KIB(value) ((u32)(value) * 1024u)
#define MIB(value) ((u32)(value) * 1024u * 1024u)

#define RECOVERY_RESERVE_BYTES KIB(256)
#define COARSE_STEP_BYTES      MIB(1)
#define FINE_STEP_BYTES        KIB(64)
#define PROBE_CAP_BYTES        MIB(16)
#define PAGE_BYTES             KIB(4)

#define PROBE_ALLOC_FAILED 0
#define PROBE_ALLOC_PASSED 1
#define PROBE_FATAL_ERROR (-1)

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\MAXHEAP.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\MAXHEAP.TXT";

static const char *g_log_path;
static int g_log_ok;
static char g_line[192];
static char g_summary[160];

static char *append_char(char *out, char *end, char value)
{
    if (out < end)
        *out++ = value;
    return out;
}

static char *append_text(char *out, char *end, const char *text)
{
    while (*text && out < end)
        *out++ = *text++;
    return out;
}

static char *append_u32(char *out, char *end, u32 value)
{
    char digits[10];
    int count = 0;

    do {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    } while (value != 0u && count < (int)sizeof(digits));

    while (count > 0)
        out = append_char(out, end, digits[--count]);
    return out;
}

static char *append_hex32(char *out, char *end, u32 value)
{
    static const char digits[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4)
        out = append_char(out, end, digits[(value >> shift) & 0x0fu]);
    return out;
}

static int open_log(const char *mode)
{
    int file;

    if (g_log_path)
        return bda_fs_fopen_raw(g_log_path, mode);

    file = bda_fs_fopen_raw(k_log_path_a, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = k_log_path_a;
        return file;
    }

    file = bda_fs_fopen_raw(k_log_path_root, mode);
    if (bda_fs_file_is_valid(file))
        g_log_path = k_log_path_root;
    return file;
}

static int reset_log(void)
{
    int file;

    g_log_path = 0;
    g_log_ok = 0;
    file = open_log("wb");
    if (!bda_fs_file_is_valid(file))
        return 0;
    (void)bda_fs_close_raw(file);
    g_log_ok = 1;
    return 1;
}

static void write_line(char *out)
{
    int file;
    u32 length;

    if (!g_log_ok)
        return;

    out = append_text(out, g_line + sizeof(g_line) - 1, "\r\n");
    *out = 0;
    length = (u32)(out - g_line);

    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        g_log_ok = 0;
        return;
    }
    if (bda_fs_write_raw(file, g_line, length) != (int)length)
        g_log_ok = 0;
    (void)bda_fs_close_raw(file);
}

static void log_text(const char *text)
{
    write_line(append_text(g_line, g_line + sizeof(g_line) - 1, text));
}

static void log_decimal(const char *label, u32 value)
{
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_u32(out, end, value);
    write_line(out);
}

static void log_pointer(const char *label, const void *pointer)
{
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, (u32)pointer);
    write_line(out);
}

static void log_try(const char *phase, u32 size)
{
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "BEFORE ");
    out = append_text(out, end, phase);
    out = append_text(out, end, " SIZE=");
    out = append_u32(out, end, size);
    out = append_text(out, end, " HEX=");
    out = append_hex32(out, end, size);
    write_line(out);
}

static void log_probe_result(
    const char *phase, u32 size, const void *pointer, const char *result
)
{
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, phase);
    out = append_text(out, end, " SIZE=");
    out = append_u32(out, end, size);
    out = append_text(out, end, " PTR=");
    out = append_hex32(out, end, (u32)pointer);
    out = append_text(out, end, " PAGE_TOUCH=");
    out = append_text(out, end, result);
    write_line(out);
}

static int allocation_pointer_valid(const void *pointer)
{
    u32 value = (u32)pointer;

    return value >= 0x80000000u && value < 0x82000000u &&
        (value & 3u) == 0u;
}

static int touch_and_verify_pages(void *pointer, u32 size, u8 seed)
{
    volatile u8 *memory = (volatile u8 *)pointer;
    u32 offset;

    for (offset = 0; offset < size; offset += PAGE_BYTES)
        memory[offset] = (u8)(seed ^ (u8)(offset >> 12));
    memory[size - 1u] = (u8)(seed ^ 0xa5u);

    for (offset = 0; offset < size; offset += PAGE_BYTES) {
        if (memory[offset] != (u8)(seed ^ (u8)(offset >> 12)))
            return 0;
    }
    return memory[size - 1u] == (u8)(seed ^ 0xa5u);
}

static int probe_single_size(const char *phase, u32 size, u8 seed)
{
    void *pointer;
    int page_ok;

    log_try(phase, size);
    if (!g_log_ok)
        return PROBE_FATAL_ERROR;

    pointer = bda_alloc(size);
    if (!allocation_pointer_valid(pointer)) {
        log_probe_result(phase, size, pointer, "ALLOC_FAIL");
        return pointer == 0 || (u32)pointer == 0xffffffffu
            ? PROBE_ALLOC_FAILED
            : PROBE_FATAL_ERROR;
    }

    page_ok = touch_and_verify_pages(pointer, size, seed);
    bda_free(pointer);
    log_probe_result(phase, size, pointer, page_ok ? "PASS" : "CORRUPT");
    return page_ok ? PROBE_ALLOC_PASSED : PROBE_FATAL_ERROR;
}

static int verify_recovery_heap(void)
{
    void *pointer = bda_alloc(PAGE_BYTES);
    int ok;

    if (!allocation_pointer_valid(pointer)) {
        log_pointer("RECOVERY PTR=", pointer);
        return 0;
    }
    ok = touch_and_verify_pages(pointer, PAGE_BYTES, 0x6du);
    bda_free(pointer);
    log_text(ok ? "RECOVERY PAGE=PASS" : "RECOVERY PAGE=CORRUPT");
    return ok;
}

static void build_summary(u32 maximum, u32 first_failure, int cap_reached)
{
    char *out = g_summary;
    char *end = g_summary + sizeof(g_summary) - 1;

    if (cap_reached)
        out = append_text(out, end, "SAFE MAX >= ");
    else
        out = append_text(out, end, "SAFE MAX = ");
    out = append_u32(out, end, maximum);
    out = append_text(out, end, " bytes\n");
    if (first_failure != 0u) {
        out = append_text(out, end, "FIRST FAIL = ");
        out = append_u32(out, end, first_failure);
        out = append_text(out, end, " bytes\n");
    }
    out = append_text(out, end, "See MAXHEAP.TXT");
    *out = 0;
}

__attribute__((section(".text.bda_main")))
int bda_main(void)
{
    void *reserve;
    u32 low = 0u;
    u32 high = 0u;
    u32 size;
    u32 middle;
    int outcome = PROBE_ALLOC_FAILED;
    int cap_reached = 0;
    int recovery_ok;
    u8 seed = 0x31u;

    if (!reset_log()) {
        bda_msgbox("MaxHeapV1", "Cannot create MAXHEAP.TXT");
        return 1;
    }

    log_text("START MAX HEAP HARDWARE PROBE V1");
    log_text("MODE=LARGEST SINGLE CONTIGUOUS BLOCK");
    log_decimal("RECOVERY RESERVE BYTES=", RECOVERY_RESERVE_BYTES);
    log_decimal("COARSE STEP BYTES=", COARSE_STEP_BYTES);
    log_decimal("FINE STEP BYTES=", FINE_STEP_BYTES);
    log_decimal("PROBE CAP BYTES=", PROBE_CAP_BYTES);
    log_text("RESULT EXCLUDES RECOVERY RESERVE");
    log_text("EACH SUCCESS TOUCHES EVERY 4096-BYTE PAGE");

    reserve = bda_alloc(RECOVERY_RESERVE_BYTES);
    log_pointer("RESERVE PTR=", reserve);
    if (!allocation_pointer_valid(reserve)) {
        log_text("RESERVE=FAIL");
        log_text("RESULT=ABORT");
        log_text("END MAX HEAP HARDWARE PROBE V1");
        bda_msgbox("MaxHeapV1", "Recovery reserve failed");
        return 1;
    }
    if (!touch_and_verify_pages(
            reserve, RECOVERY_RESERVE_BYTES, 0x5au
        )) {
        bda_free(reserve);
        log_text("RESERVE PAGE=CORRUPT");
        log_text("RESULT=ABORT");
        log_text("END MAX HEAP HARDWARE PROBE V1");
        bda_msgbox("MaxHeapV1", "Recovery reserve corrupt");
        return 1;
    }
    log_text("RESERVE=PASS");

    for (size = COARSE_STEP_BYTES; size <= PROBE_CAP_BYTES;
         size += COARSE_STEP_BYTES) {
        outcome = probe_single_size("COARSE", size, seed++);
        if (outcome == PROBE_ALLOC_PASSED) {
            low = size;
            continue;
        }
        if (outcome == PROBE_ALLOC_FAILED) {
            high = size;
            break;
        }
        break;
    }

    if (outcome != PROBE_FATAL_ERROR && high != 0u) {
        while (high - low > FINE_STEP_BYTES) {
            middle = low + (high - low) / 2u;
            middle &= ~(FINE_STEP_BYTES - 1u);
            if (middle <= low)
                break;

            outcome = probe_single_size("FINE", middle, seed++);
            if (outcome == PROBE_ALLOC_PASSED)
                low = middle;
            else if (outcome == PROBE_ALLOC_FAILED)
                high = middle;
            else
                break;
        }
    } else if (outcome == PROBE_ALLOC_PASSED &&
               low == PROBE_CAP_BYTES) {
        cap_reached = 1;
    }

    bda_free(reserve);
    log_text("RESERVE RELEASED");
    recovery_ok = verify_recovery_heap();

    log_decimal("MAX SAFE SINGLE BYTES=", low);
    log_decimal("MAX SAFE SINGLE KIB=", low / 1024u);
    if (high != 0u)
        log_decimal("FIRST FAILED CANDIDATE BYTES=", high);
    log_decimal("CAP REACHED=", (u32)cap_reached);

    if (outcome == PROBE_FATAL_ERROR) {
        log_text("RESULT=FATAL");
    } else if (!recovery_ok || low == 0u) {
        log_text("RESULT=FAIL");
    } else if (cap_reached) {
        log_text("RESULT=PASS CAP_REACHED");
    } else {
        log_text("RESULT=PASS");
    }
    log_text("END MAX HEAP HARDWARE PROBE V1");

    if (!g_log_ok) {
        bda_msgbox("MaxHeapV1", "Log write failed");
        return 1;
    }

    build_summary(low, high, cap_reached);
    bda_msgbox("MaxHeapV1", g_summary);
    return outcome == PROBE_FATAL_ERROR || !recovery_ok || low == 0u;
}
