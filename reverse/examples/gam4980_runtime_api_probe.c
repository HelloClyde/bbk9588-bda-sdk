#include "bda_dialogs.h"

/*
 * Admission probe for the runtime APIs needed by gam4980-9588.
 * Candidate wrappers stay local until this BDA has produced an exported log.
 */

#define PROBE_MEM_TABLE_ADDR 0x81c00010u
#define PROBE_FS_TABLE_ADDR  0x81c00008u

#define PROBE_MEM_ALLOC 0x008u
#define PROBE_MEM_FREE  0x00cu

#define PROBE_FS_SEEK      0x010u
#define PROBE_FS_CHDIR     0x02cu
#define PROBE_FS_MKDIR     0x030u
#define PROBE_FS_FINDFIRST 0x03cu
#define PROBE_FS_FINDNEXT  0x040u
#define PROBE_FS_FINDCLOSE 0x044u

#define PROBE_SEEK_SET 0
#define PROBE_SEEK_CUR 1
#define PROBE_SEEK_END 2

#define ARRAY_COUNT(a) ((u32)(sizeof(a) / sizeof((a)[0])))

typedef signed short probe_s16_t;

typedef struct probe_find_data {
    void *cursor;
    u32 size_or_aux04;
    u32 attr_or_flags08;
    u16 time_like0c;
    u16 date_like0e;
    probe_s16_t volume_index10;
    char name_or_path12[0x20a];
    u32 aux21c;
} probe_find_data_t;

typedef char probe_find_data_size_must_be_0x220[
    sizeof(probe_find_data_t) == 0x220u ? 1 : -1
];

typedef struct probe_allocation {
    const char *name;
    u32 size;
    u8 seed;
    u8 *pointer;
} probe_allocation_t;

static const char k_data_root[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7";
static const char k_test_dir[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\G498API";
static const char k_log_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\G498API.TXT";
static const char k_one_payload[] = "0123456789ABCDEF";
static const char k_two_payload[] = "second-file";

static probe_allocation_t g_allocations[] = {
    {"RAM",   0x8000u,   0x11u, 0},
    {"FLASH", 0x200000u, 0x22u, 0},
    {"ROM8",  0x200000u, 0x33u, 0},
    {"ROME",  0x200000u, 0x44u, 0},
    {"FRAME", 161u * 96u * 2u, 0x55u, 0},
    {"VX",    24u + 240u * 320u * 2u, 0x66u, 0},
};

static char g_report[3072];
static char *g_report_out;
static int g_failures;

static void *probe_table(u32 address)
{
    return *(void **)address;
}

static void *probe_api(void *table, u32 offset)
{
    return *(void **)((u8 *)table + offset);
}

static void *probe_alloc(u32 size)
{
    typedef void *(*fn_t)(u32);
    return ((fn_t)probe_api(probe_table(PROBE_MEM_TABLE_ADDR), PROBE_MEM_ALLOC))(size);
}

static void probe_free(void *pointer)
{
    typedef void (*fn_t)(void *);
    ((fn_t)probe_api(probe_table(PROBE_MEM_TABLE_ADDR), PROBE_MEM_FREE))(pointer);
}

static int probe_seek(int file, s32 offset, int whence)
{
    typedef int (*fn_t)(int, s32, int);
    return ((fn_t)probe_api(probe_table(PROBE_FS_TABLE_ADDR), PROBE_FS_SEEK))(
        file, offset, whence
    );
}

static int probe_chdir(const char *path)
{
    typedef int (*fn_t)(const char *);
    return ((fn_t)probe_api(probe_table(PROBE_FS_TABLE_ADDR), PROBE_FS_CHDIR))(path);
}

static int probe_mkdir(const char *path)
{
    typedef int (*fn_t)(const char *);
    return ((fn_t)probe_api(probe_table(PROBE_FS_TABLE_ADDR), PROBE_FS_MKDIR))(path);
}

static int probe_findfirst(const char *pattern, u32 attr, probe_find_data_t *data)
{
    typedef int (*fn_t)(const char *, u32, probe_find_data_t *);
    return ((fn_t)probe_api(probe_table(PROBE_FS_TABLE_ADDR), PROBE_FS_FINDFIRST))(
        pattern, attr, data
    );
}

static int probe_findnext(probe_find_data_t *data)
{
    typedef int (*fn_t)(probe_find_data_t *);
    return ((fn_t)probe_api(probe_table(PROBE_FS_TABLE_ADDR), PROBE_FS_FINDNEXT))(data);
}

static int probe_findclose(probe_find_data_t *data)
{
    typedef int (*fn_t)(probe_find_data_t *);
    return ((fn_t)probe_api(probe_table(PROBE_FS_TABLE_ADDR), PROBE_FS_FINDCLOSE))(data);
}

static int valid_pointer(const void *pointer)
{
    return pointer != 0 && (u32)pointer != 0xffffffffu;
}

static char *append_char(char *out, char *end, char value)
{
    if (out < end)
        *out++ = value;
    return out;
}

static char *append_text(char *out, char *end, const char *text)
{
    while (*text)
        out = append_char(out, end, *text++);
    return out;
}

static char *append_dec(char *out, char *end, int value)
{
    char digits[12];
    u32 magnitude;
    int count = 0;

    if (value < 0) {
        out = append_char(out, end, '-');
        magnitude = (u32)(0 - value);
    } else {
        magnitude = (u32)value;
    }
    do {
        digits[count++] = (char)('0' + magnitude % 10u);
        magnitude /= 10u;
    } while (magnitude && count < (int)sizeof(digits));
    while (count > 0)
        out = append_char(out, end, digits[--count]);
    return out;
}

static char *append_hex32(char *out, char *end, u32 value)
{
    static const char hex[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4)
        out = append_char(out, end, hex[(value >> shift) & 0x0fu]);
    return out;
}

static void report_text(const char *text)
{
    g_report_out = append_text(g_report_out, g_report + sizeof(g_report) - 1, text);
    g_report_out = append_text(g_report_out, g_report + sizeof(g_report) - 1, "\r\n");
}

static void report_value(const char *label, int value)
{
    g_report_out = append_text(g_report_out, g_report + sizeof(g_report) - 1, label);
    g_report_out = append_dec(g_report_out, g_report + sizeof(g_report) - 1, value);
    g_report_out = append_text(g_report_out, g_report + sizeof(g_report) - 1, "\r\n");
}

static void report_pointer(const char *label, const void *pointer)
{
    g_report_out = append_text(g_report_out, g_report + sizeof(g_report) - 1, label);
    g_report_out = append_hex32(
        g_report_out, g_report + sizeof(g_report) - 1, (u32)pointer
    );
    g_report_out = append_text(g_report_out, g_report + sizeof(g_report) - 1, "\r\n");
}

static void fail(const char *label)
{
    ++g_failures;
    g_report_out = append_text(g_report_out, g_report + sizeof(g_report) - 1, "FAIL ");
    report_text(label);
}

static int memory_ranges_overlap(
    const probe_allocation_t *left, const probe_allocation_t *right
)
{
    u32 left_begin = (u32)left->pointer;
    u32 right_begin = (u32)right->pointer;
    u32 left_end = left_begin + left->size;
    u32 right_end = right_begin + right->size;
    return left_begin < right_end && right_begin < left_end;
}

static void stamp_allocation(probe_allocation_t *allocation)
{
    u32 offset;
    allocation->pointer[0] = allocation->seed;
    for (offset = 4096u; offset < allocation->size; offset += 4096u)
        allocation->pointer[offset] = (u8)(allocation->seed ^ (u8)(offset >> 12));
    allocation->pointer[allocation->size / 2u] = (u8)(allocation->seed ^ 0x5au);
    allocation->pointer[allocation->size - 1u] = (u8)(allocation->seed ^ 0xa5u);
}

static int verify_allocation(const probe_allocation_t *allocation)
{
    u32 offset;
    if (allocation->pointer[0] != allocation->seed)
        return 0;
    for (offset = 4096u; offset < allocation->size; offset += 4096u) {
        u8 expected = (u8)(allocation->seed ^ (u8)(offset >> 12));
        if (offset == allocation->size / 2u)
            expected = (u8)(allocation->seed ^ 0x5au);
        if (allocation->pointer[offset] != expected)
            return 0;
    }
    return allocation->pointer[allocation->size / 2u] ==
               (u8)(allocation->seed ^ 0x5au) &&
           allocation->pointer[allocation->size - 1u] ==
               (u8)(allocation->seed ^ 0xa5u);
}

static void probe_heap(void)
{
    u32 index;
    u32 other;
    u8 *reuse;

    report_text("[HEAP]");
    for (index = 0; index < ARRAY_COUNT(g_allocations); ++index) {
        probe_allocation_t *allocation = &g_allocations[index];
        allocation->pointer = (u8 *)probe_alloc(allocation->size);
        report_pointer(allocation->name, allocation->pointer);
        if (!valid_pointer(allocation->pointer))
            fail("allocation returned invalid pointer");
    }
    if (g_failures == 0) {
        for (index = 0; index < ARRAY_COUNT(g_allocations); ++index) {
            for (other = index + 1u; other < ARRAY_COUNT(g_allocations); ++other) {
                if (memory_ranges_overlap(&g_allocations[index], &g_allocations[other]))
                    fail("allocation ranges overlap");
            }
            stamp_allocation(&g_allocations[index]);
        }
        for (index = 0; index < ARRAY_COUNT(g_allocations); ++index) {
            if (!verify_allocation(&g_allocations[index]))
                fail("allocation content changed");
        }
    }

    for (index = ARRAY_COUNT(g_allocations); index > 0; --index) {
        probe_allocation_t *allocation = &g_allocations[index - 1u];
        if (valid_pointer(allocation->pointer))
            probe_free(allocation->pointer);
        allocation->pointer = 0;
    }
    reuse = (u8 *)probe_alloc(4096u);
    report_pointer("REUSE", reuse);
    if (!valid_pointer(reuse)) {
        fail("post-free allocation failed");
    } else {
        reuse[0] = 0x3cu;
        reuse[4095] = 0xc3u;
        if (reuse[0] != 0x3cu || reuse[4095] != 0xc3u)
            fail("post-free allocation content failed");
        probe_free(reuse);
    }
    report_text("HEAP COMPLETE");
}

static int bytes_equal(const char *left, const char *right, u32 size)
{
    while (size-- != 0u) {
        if (*left++ != *right++)
            return 0;
    }
    return 1;
}

static int ascii_lower(int value)
{
    if (value >= 'A' && value <= 'Z')
        return value + ('a' - 'A');
    return value;
}

static int name_ends_with(const char *path, const char *suffix)
{
    u32 path_length = 0;
    u32 suffix_length = 0;
    u32 index;

    while (path[path_length] && path_length < 0x209u)
        ++path_length;
    while (suffix[suffix_length])
        ++suffix_length;
    if (path_length < suffix_length)
        return 0;
    for (index = 0; index < suffix_length; ++index) {
        if (ascii_lower(path[path_length - suffix_length + index]) !=
            ascii_lower(suffix[index]))
            return 0;
    }
    return 1;
}

static int create_relative_file(const char *name, const char *payload, u32 size)
{
    int file = bda_fs_fopen_raw(name, "wb");
    int wrote;
    if (!bda_fs_file_is_valid(file))
        return 0;
    wrote = bda_fs_write_raw(file, payload, size);
    (void)bda_fs_close_raw(file);
    return wrote == (int)size;
}

static void probe_seek_and_directories(void)
{
    probe_find_data_t find_data;
    char readback[8];
    int mkdir_result;
    int chdir_result;
    int file;
    int seek_end;
    int seek_set;
    int seek_cur;
    int seek_invalid;
    int tell_end;
    int tell_set;
    int tell_cur;
    int read_first;
    int read_second;
    int first_result;
    int next_result;
    int close_result = -999;
    int found_one = 0;
    int found_two = 0;
    int count = 0;

    report_text("[DIRECTORY]");
    mkdir_result = probe_mkdir(k_test_dir);
    chdir_result = probe_chdir(k_test_dir);
    report_value("MKDIR=", mkdir_result);
    report_value("CHDIR=", chdir_result);
    if (mkdir_result == -1)
        fail("mkdir failed on clean NAND");
    if (chdir_result == -1)
        fail("chdir failed");
    if (!create_relative_file("ONE.TST", k_one_payload, sizeof(k_one_payload) - 1u))
        fail("ONE.TST relative write failed");
    if (!create_relative_file("TWO.TST", k_two_payload, sizeof(k_two_payload) - 1u))
        fail("TWO.TST relative write failed");

    report_text("[SEEK]");
    bda_memset(readback, 0, sizeof(readback));
    file = bda_fs_fopen_raw("ONE.TST", "rb");
    if (!bda_fs_file_is_valid(file)) {
        fail("ONE.TST relative reopen failed");
    } else {
        seek_end = probe_seek(file, 0, PROBE_SEEK_END);
        tell_end = bda_fs_tell_raw(file);
        seek_set = probe_seek(file, 4, PROBE_SEEK_SET);
        tell_set = bda_fs_tell_raw(file);
        read_first = bda_fs_read_raw(file, readback, 4u);
        seek_cur = probe_seek(file, -2, PROBE_SEEK_CUR);
        tell_cur = bda_fs_tell_raw(file);
        read_second = bda_fs_read_raw(file, readback + 4, 2u);
        seek_invalid = probe_seek(file, 0, 99);
        (void)bda_fs_close_raw(file);
        report_value("SEEK_END=", seek_end);
        report_value("TELL_END=", tell_end);
        report_value("SEEK_SET4=", seek_set);
        report_value("TELL_SET4=", tell_set);
        report_value("READ_4567=", read_first);
        report_value("SEEK_CUR_NEG2=", seek_cur);
        report_value("TELL_CUR=", tell_cur);
        report_value("READ_67=", read_second);
        report_value("SEEK_INVALID=", seek_invalid);
        if (seek_end != 16 || tell_end != 16 || seek_set != 4 || tell_set != 4 ||
            read_first != 4 || !bytes_equal(readback, "4567", 4u) ||
            seek_cur != 6 || tell_cur != 6 || read_second != 2 ||
            !bytes_equal(readback + 4, "67", 2u) || seek_invalid != -1)
            fail("seek return, position, or readback mismatch");
    }

    report_text("[FIND]");
    bda_memset(&find_data, 0, sizeof(find_data));
    first_result = probe_findfirst("*.TST", 0x27u, &find_data);
    next_result = first_result;
    report_value("FINDFIRST=", first_result);
    while (next_result != -1 && count < 16) {
        find_data.name_or_path12[sizeof(find_data.name_or_path12) - 1u] = 0;
        if (name_ends_with(find_data.name_or_path12, "ONE.TST"))
            found_one = 1;
        if (name_ends_with(find_data.name_or_path12, "TWO.TST"))
            found_two = 1;
        ++count;
        next_result = probe_findnext(&find_data);
    }
    if (first_result != -1)
        close_result = probe_findclose(&find_data);
    report_value("COUNT=", count);
    report_value("FOUND_ONE=", found_one);
    report_value("FOUND_TWO=", found_two);
    report_value("FINAL_NEXT=", next_result);
    report_value("FINDCLOSE=", close_result);
    if (first_result == -1 || count != 2 || !found_one || !found_two ||
        next_result != -1 || close_result == -1)
        fail("directory enumeration lifecycle mismatch");

    if (probe_chdir(k_data_root) == -1)
        fail("restore data root failed");
}

static void write_report(void)
{
    int file;
    u32 size;

    report_value("FAILURES=", g_failures);
    report_text(g_failures == 0 ? "RESULT=PASS" : "RESULT=FAIL");
    *g_report_out = 0;
    size = (u32)(g_report_out - g_report);
    file = bda_fs_fopen_raw(k_log_path, "wb");
    if (bda_fs_file_is_valid(file)) {
        (void)bda_fs_write_raw(file, g_report, size);
        (void)bda_fs_close_raw(file);
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void)
{
    g_report_out = g_report;
    g_failures = 0;
    report_text("GAM4980 RUNTIME API ADMISSION PROBE V1");
    probe_heap();
    probe_seek_and_directories();
    write_report();
    bda_msgbox(
        "G498 Runtime",
        g_failures == 0 ? "PASS\nG498API.TXT written" : "FAIL\nSee G498API.TXT"
    );
    return g_failures == 0 ? 0 : 1;
}
