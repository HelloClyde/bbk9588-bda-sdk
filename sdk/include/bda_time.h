#ifndef BDA_TIME_H
#define BDA_TIME_H

#include "bda/detail/runtime.h"

/* Monotonic firmware tick. One unsigned tick is 25 ms on kj409588/C200. */
static inline u32 bda_gui_tick_count_25ms(void) {
    typedef u32 (*fn_t)(void);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_TICK_COUNT_25MS
    );
    return fn();
}

/* Unsigned subtraction remains correct across one u32 counter wrap. */
static inline u32 bda_gui_tick_elapsed_25ms(u32 start, u32 end) {
    return end - start;
}

static inline u32 bda_gui_tick_elapsed_ms(u32 start, u32 end) {
    return bda_gui_tick_elapsed_25ms(start, end) * 25u;
}

/* Busy-wait delay exercised by the verified input, touch and graphics BDAs. */
static inline void bda_sys_delay(u32 delay_units) {
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_sys(), BDA_SDK_INTERNAL_SYS_DELAY, delay_units
    );
}

#endif
