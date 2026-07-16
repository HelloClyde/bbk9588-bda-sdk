#include "../bda_research_sdk.h"

typedef int (*bda_system_printf_fn)(const char *fmt, ...);

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_system_printf_fn print = (bda_system_printf_fn)0x800098c0u;

    print("\n[StdoutProbe] hello from native BDA\n");
    print("[StdoutProbe] value=%d hex=0x%08x\n", 12345, 0x81c00020u);
    print("[StdoutProbe] gui=%08x fs=%08x sys=%08x mem=%08x res=%08x\n",
          (u32)bda_gui_table(),
          (u32)bda_fs_table(),
          (u32)bda_sys_table(),
          (u32)bda_mem_table(),
          (u32)bda_res_table());

    bda_msgbox("StdoutProbe", "printf-like output sent.\nCheck serial/debug log.");
    return 0;
}
