#include "bda_sdk.h"

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_msgbox("C SDK", "Hello from freestanding C");
    return 0;
}
