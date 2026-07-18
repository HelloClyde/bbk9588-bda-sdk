#include "bda_dialogs.h"

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_msgbox("HelloWorld", "HelloWorld");
    return 0;
}
