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

/*
 * Firmware-owned, nominal 1 ms timer. Start it once, take counter snapshots,
 * then stop it exactly once before the BDA exits. It is not reference counted.
 */
static inline void bda_gui_millisecond_timer_start(void) {
    typedef void (*fn_t)(void);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_MILLISECOND_TIMER_START
    );
    fn();
}

static inline void bda_gui_millisecond_timer_stop(void) {
    typedef void (*fn_t)(void);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_MILLISECOND_TIMER_STOP
    );
    fn();
}

/* Read only between the matching start and stop calls. */
static inline u32 bda_gui_millisecond_count(void) {
    typedef u32 (*fn_t)(void);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_MILLISECOND_COUNT
    );
    return fn();
}

/* Unsigned subtraction remains correct across one u32 counter wrap. */
static inline u32 bda_gui_millisecond_elapsed(u32 start, u32 end) {
    return end - start;
}

/* Busy-wait delay exercised by the verified input, touch and graphics BDAs. */
static inline void bda_sys_delay(u32 delay_units) {
    (void)bda_sdk_internal_call1(
        bda_sdk_internal_sys(), BDA_SDK_INTERNAL_SYS_DELAY, delay_units
    );
}

#define BDA_MSG_WINDOW_TIMER 0x0144u
#define BDA_WINDOW_TIMER_MAX_ACTIVE 16u
#define BDA_WINDOW_TIMER_RESOLUTION_MS 10u

/*
 * Start one periodic timer owned by frame. timer_id is returned in wparam of
 * BDA_MSG_WINDOW_TIMER and identifies the timer together with frame.
 * period_ms is rounded up by the firmware's 10 ms scheduler resolution.
 * The return value is 1 on success and 0 on failure; it is not a handle.
 */
static inline int bda_gui_window_timer_start(
    bda_handle_t frame, u32 timer_id, u32 period_ms
) {
    if (period_ms == 0u) {
        return 0;
    }
    return bda_sdk_internal_call3(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_WINDOW_TIMER_START,
        (u32)frame,
        timer_id,
        period_ms
    );
}

/* Stop the active timer identified by the same frame and timer_id pair. */
static inline int bda_gui_window_timer_stop(
    bda_handle_t frame, u32 timer_id
) {
    return bda_sdk_internal_call2(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_WINDOW_TIMER_STOP,
        (u32)frame,
        timer_id
    );
}

/* Return 1 when the frame/timer_id pair is active, otherwise return 0. */
static inline int bda_gui_window_timer_exists(
    bda_handle_t frame, u32 timer_id
) {
    return bda_sdk_internal_call2(
        bda_sdk_internal_gui(),
        BDA_SDK_INTERNAL_GUI_WINDOW_TIMER_EXISTS,
        (u32)frame,
        timer_id
    );
}

/*
 * Safely reset an active timer's period. The native period-update entry can
 * dereference a sparse timer table, so the public API deliberately composes
 * the verified stop/start pair instead.
 */
static inline int bda_gui_window_timer_set_period(
    bda_handle_t frame, u32 timer_id, u32 period_ms
) {
    if (period_ms == 0u) {
        return 0;
    }
    if (bda_gui_window_timer_stop(frame, timer_id) != 1) {
        return 0;
    }
    return bda_gui_window_timer_start(frame, timer_id, period_ms);
}

/* Monotonic raw clock used by the window timer scheduler, in milliseconds. */
static inline u32 bda_gui_window_timer_clock_ms(void) {
    typedef u32 (*fn_t)(void);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_SDK_INTERNAL_GUI_WINDOW_TIMER_CLOCK
    );
    return fn();
}

#endif
