#include "bda_dialogs.h"

static const char g_help_body[] =
    "This page is created by the firmware help service.\n"
    "\n"
    "Use a short title and put the full instructions in the body.\n"
    "The call returns after the user closes the help page.\n"
    "\n"
    "In a window procedure, pass the current frame as parent.\n";

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int result = bda_help_page(0, "Help page demo", g_help_body);

    if (result == BDA_HELP_PAGE_COMPLETED) {
        (void)bda_msgbox("Help page demo", "RETURNED: PASS");
        return 0;
    }
    (void)bda_msgbox("Help page demo", "HELP PAGE ERROR");
    return 1;
}
