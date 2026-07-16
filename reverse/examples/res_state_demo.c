#include "../bda_research_sdk.h"

static bda_res_state_like_t g_res_state;

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_res_get_state_like(&g_res_state);

    bda_msgbox("RES090", "state snapshot");
    return 0;
}
