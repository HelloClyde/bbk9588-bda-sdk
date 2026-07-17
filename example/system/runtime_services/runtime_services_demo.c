#include "bda_sdk.h"

static const char k_data_root[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7";
static const char k_demo_dir[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RUNTIME";
static const char k_payload[] = "0123456789ABCDEF";

static int bytes_equal(const char *left, const char *right, u32 size)
{
    while (size-- != 0u) {
        if (*left++ != *right++)
            return 0;
    }
    return 1;
}

static int verify_heap(void)
{
    u8 *memory = (u8 *)bda_alloc(4096u);
    int ok;

    if (!memory || (u32)memory == 0xffffffffu)
        return 0;
    memory[0] = 0x12u;
    memory[2048] = 0x34u;
    memory[4095] = 0x56u;
    ok = memory[0] == 0x12u && memory[2048] == 0x34u &&
        memory[4095] == 0x56u;
    bda_free(memory);
    return ok;
}

static int create_test_file(void)
{
    int file = bda_fs_fopen_raw("SEEK.TST", "wb");
    int wrote;

    if (!bda_fs_file_is_valid(file))
        return 0;
    wrote = bda_fs_write_raw(file, k_payload, sizeof(k_payload) - 1u);
    (void)bda_fs_close_raw(file);
    return wrote == (int)(sizeof(k_payload) - 1u);
}

static int verify_seek(void)
{
    char readback[4];
    int file = bda_fs_fopen_raw("SEEK.TST", "rb");
    int ok;

    if (!bda_fs_file_is_valid(file))
        return 0;
    ok = bda_fs_seek_raw(file, 0, BDA_SEEK_END) == 16 &&
        bda_fs_tell_raw(file) == 16 &&
        bda_fs_seek_raw(file, 4, BDA_SEEK_SET) == 4 &&
        bda_fs_read_raw(file, readback, sizeof(readback)) == 4 &&
        bytes_equal(readback, "4567", sizeof(readback)) &&
        bda_fs_seek_raw(file, -2, BDA_SEEK_CUR) == 6;
    (void)bda_fs_close_raw(file);
    return ok;
}

static int verify_find(void)
{
    bda_fs_find_data_t find_data;
    int result;
    int close_result;

    bda_fs_find_data_init(&find_data);
    result = bda_fs_findfirst("*.TST", 0x27u, &find_data);
    if (result == -1)
        return 0;
    close_result = bda_fs_findclose(&find_data);
    return close_result == 0;
}

__attribute__((section(".text.bda_main")))
int bda_main(void)
{
    int ok = verify_heap();

    (void)bda_fs_mkdir(k_demo_dir);
    ok = ok && bda_fs_chdir(k_demo_dir) == 0;
    ok = ok && create_test_file();
    ok = ok && verify_seek();
    ok = ok && verify_find();
    (void)bda_fs_chdir(k_data_root);
    bda_msgbox("Runtime API", ok ? "PASS" : "FAIL");
    return ok ? 0 : 1;
}
