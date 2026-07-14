#include "bda_sdk.h"

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    char stack_msg[64];
    const char *prefix = "SDK probe: ";
    const char *body = "alloc/gui ok";
    bda_size_t prefix_len = bda_strlen(prefix);
    bda_size_t body_len = bda_strlen(body);

    bda_memset(stack_msg, 0, sizeof(stack_msg));
    bda_memcpy(stack_msg, prefix, prefix_len);
    bda_memcpy(stack_msg + prefix_len, body, body_len + 1);

    void *tmp = bda_alloc(32);
    if (tmp) {
        bda_memset(tmp, 0x41, 31);
        ((char *)tmp)[31] = 0;
        bda_free(tmp);
    }

    bda_msgbox("BDA SDK", stack_msg);
    return 0;
}
