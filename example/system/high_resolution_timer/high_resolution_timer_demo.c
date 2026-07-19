#include "bda_dialogs.h"
#include "bda_time.h"

static char *append_text(char *out, const char *text)
{
    while (*text)
        *out++ = *text++;
    return out;
}

static char *append_u32(char *out, u32 value)
{
    char digits[10];
    int count = 0;

    do {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    } while (value != 0u);
    while (count > 0)
        *out++ = digits[--count];
    return out;
}

__attribute__((section(".text.bda_main")))
int bda_main(void)
{
    char message[48];
    char *out;
    u32 coarse_start;
    u32 timer_start;
    u32 timer_end;
    u32 elapsed;

    bda_gui_millisecond_timer_start();
    coarse_start = bda_gui_tick_count_25ms();
    timer_start = bda_gui_millisecond_count();
    while (bda_gui_tick_elapsed_25ms(
        coarse_start, bda_gui_tick_count_25ms()
    ) < 8u) {
    }
    timer_end = bda_gui_millisecond_count();
    elapsed = bda_gui_millisecond_elapsed(timer_start, timer_end);
    bda_gui_millisecond_timer_stop();

    out = append_text(message, "8 x 25 ms = ");
    out = append_u32(out, elapsed);
    out = append_text(out, " timer counts");
    *out = '\0';
    bda_msgbox("1 ms Timer", message);
    return 0;
}
