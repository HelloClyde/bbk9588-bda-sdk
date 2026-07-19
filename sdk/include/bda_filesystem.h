#ifndef BDA_FILESYSTEM_H
#define BDA_FILESYSTEM_H

#include "bda_memory.h"

#define BDA_SEEK_SET 0
#define BDA_SEEK_CUR 1
#define BDA_SEEK_END 2

#define BDA_FS_FIND_DATA_SIZE 0x220u

typedef struct bda_fs_find_data {
    void *cursor;
    u32 size_or_aux;
    u32 attr_or_flags;
    u16 time;
    u16 date;
    s16 volume_index;
    char name_or_path[0x20a];
    u32 aux;
} bda_fs_find_data_t;

/* File API backed by the verified FS table entries below. */
static inline int bda_fs_fopen_raw(const char *path, const char *mode) {
    typedef int (*fn_t)(const char *, const char *);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_OPEN
    );
    return fn(path, mode);
}

static inline int bda_fs_file_is_valid(int file) {
    return file != 0 && (u32)file != 0xffffffffu;
}

static inline int bda_fs_close_raw(int file) {
    typedef int (*fn_t)(int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_CLOSE
    );
    return fn(file);
}

static inline int bda_fs_fread_raw(
    void *buffer, bda_size_t size, bda_size_t count, int file
) {
    typedef int (*fn_t)(void *, bda_size_t, bda_size_t, int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_READ
    );
    return fn(buffer, size, count, file);
}

static inline int bda_fs_read_raw(int file, void *buffer, bda_size_t size) {
    return bda_fs_fread_raw(buffer, 1u, size, file);
}

static inline int bda_fs_fwrite_raw(
    const void *buffer, bda_size_t size, bda_size_t count, int file
) {
    typedef int (*fn_t)(const void *, bda_size_t, bda_size_t, int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_WRITE
    );
    return fn(buffer, size, count, file);
}

static inline int bda_fs_write_raw(
    int file, const void *buffer, bda_size_t size
) {
    return bda_fs_fwrite_raw(buffer, 1u, size, file);
}

/* Successful seek returns the updated absolute file position. */
static inline int bda_fs_seek_raw(int file, s32 offset, int whence) {
    typedef int (*fn_t)(int, s32, int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_SEEK
    );
    return fn(file, offset, whence);
}

static inline int bda_fs_tell_raw(int file) {
    typedef int (*fn_t)(int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_TELL
    );
    return fn(file);
}

static inline int bda_fs_error(int file) {
    typedef int (*fn_t)(int);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_ERROR
    );
    return fn(file);
}

/* Directory API: FS+0x02c/+0x030/+0x03c/+0x040/+0x044. */
static inline int bda_fs_chdir(const char *path) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_CHDIR, (u32)path
    );
}

static inline int bda_fs_mkdir(const char *path) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_MKDIR, (u32)path
    );
}

static inline void bda_fs_find_data_init(bda_fs_find_data_t *find_data) {
    (void)bda_memset(find_data, 0, sizeof(*find_data));
}

static inline int bda_fs_findfirst(
    const char *pattern, u32 attr, bda_fs_find_data_t *find_data
) {
    return bda_sdk_internal_call3(
        bda_sdk_internal_fs(),
        BDA_SDK_INTERNAL_FS_FINDFIRST,
        (u32)pattern,
        attr,
        (u32)find_data
    );
}

static inline int bda_fs_findnext(bda_fs_find_data_t *find_data) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_FINDNEXT, (u32)find_data
    );
}

static inline int bda_fs_findclose(bda_fs_find_data_t *find_data) {
    return bda_sdk_internal_call1(
        bda_sdk_internal_fs(), BDA_SDK_INTERNAL_FS_FINDCLOSE, (u32)find_data
    );
}

#endif
