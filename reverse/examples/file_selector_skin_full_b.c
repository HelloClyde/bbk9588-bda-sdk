#include "../bda_research_sdk.h"

static char g_path[260];
static unsigned char g_dir_state[512];

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_file_selector_like_t selector;
    bda_memset(&selector, 0, sizeof(selector));
    bda_memset(g_path, 0, sizeof(g_path));
    bda_memset(g_dir_state, 0, sizeof(g_dir_state));

    /* 文件名保留历史含义；当前结论是不要用 RES+0x094 加载 skin。 */
    bda_file_selector_init_like(&selector, g_path, "gba", g_dir_state, "Select game");

    bda_gui_file_selector_open_like(1);
    bda_gui_file_selector_update_like();
    return 0;
}
