#ifndef BDA_MEMORY_H
#define BDA_MEMORY_H

#include "bda/detail/runtime.h"

/* Freestanding helper; this does not call a firmware API. */
static inline void *bda_memset(void *destination, int value, bda_size_t size) {
    u8 *out = (u8 *)destination;
    while (size-- != 0u) {
        *out++ = (u8)value;
    }
    return destination;
}

/* Freestanding helper; this does not call a firmware API. */
static inline void *bda_memcpy(
    void *destination, const void *source, bda_size_t size
) {
    u8 *out = (u8 *)destination;
    const u8 *in = (const u8 *)source;
    while (size-- != 0u) {
        *out++ = *in++;
    }
    return destination;
}

/* Basic heap allocation: MEM+0x008/+0x00c. */
static inline void *bda_alloc(bda_size_t size) {
    typedef void *(*fn_t)(bda_size_t);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_mem(), BDA_SDK_INTERNAL_MEM_ALLOC
    );
    return fn(size);
}

static inline void bda_free(void *pointer) {
    typedef void (*fn_t)(void *);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_mem(), BDA_SDK_INTERNAL_MEM_FREE
    );
    fn(pointer);
}

#endif
