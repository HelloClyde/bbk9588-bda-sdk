#include "../sdk/bda_sdk.h"

static char g_path[260];
static unsigned char g_dir_state[512];

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_file_selector_like_t selector;
    bda_memset(&selector, 0, sizeof(selector));
    bda_memset(g_path, 0, sizeof(g_path));
    bda_memset(g_dir_state, 0, sizeof(g_dir_state));

    bda_load_dlx_gui("\\Shell\\guihelp_A.dlx");
    bda_load_dlx_gui("\\shell\\commonframe_A.dlx");
    bda_load_dlx_gui("\\shell\\MessageBoxBlue.dlx");
    bda_load_dlx_gui("\\shell\\NLB_ICON.dlx");

    selector.out_path = g_path;
    selector.extensions = "gba";
    selector.dir_state = g_dir_state;
    selector.title = "Select game";
    selector.reserved1c = -1;
    selector.reserved20 = -1;
    selector.reserved24 = -1;

    bda_gui_file_selector_open_like(1);
    bda_gui_file_selector_update_like(&selector);
    return 0;
}
