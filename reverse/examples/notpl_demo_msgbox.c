#include "bda_sdk.h"

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_msgbox("NoTplDemo", "Built from scratch with GCC");
    return 0;
}
