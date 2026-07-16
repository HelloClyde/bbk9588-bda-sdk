#include "../bda_research_sdk.h"

static char g_text[192];

static void append_char(char **out, char *end, char c) {
    if (*out < end) {
        **out = c;
        *out += 1;
    }
}

static void append_text(char **out, char *end, const char *s) {
    while (*s) {
        append_char(out, end, *s++);
    }
}

static void append_dec(char **out, char *end, u32 value) {
    char tmp[10];
    int n = 0;
    if (value == 0) {
        append_char(out, end, '0');
        return;
    }
    while (value && n < (int)sizeof(tmp)) {
        tmp[n++] = (char)('0' + (value % 10));
        value /= 10;
    }
    while (n > 0) {
        append_char(out, end, tmp[--n]);
    }
}

static void append_signed(char **out, char *end, s32 value) {
    if (value < 0) {
        append_char(out, end, '-');
        append_dec(out, end, (u32)(0 - value));
    } else {
        append_dec(out, end, (u32)value);
    }
}

static void finish_text(char **out, char *end) {
    if (*out >= end) {
        end[-1] = 0;
    } else {
        **out = 0;
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_gui_input_packet_like_t packet;
    bda_gui_event_fetch_like_t event;
    char *out = g_text;
    char *end = g_text + sizeof(g_text) - 1;
    int packet_ret;
    int event_ret;
    int state;

    bda_memset(&packet, 0, sizeof(packet));
    bda_memset(&event, 0, sizeof(event));

    packet_ret = bda_gui_input_packet_like(&packet);
    event_ret = bda_gui_event_fetch_like(&event);
    state = bda_gui_state_query_like();

    append_text(&out, end, "packet=");
    append_signed(&out, end, packet_ret);
    append_text(&out, end, "\nevent=");
    append_signed(&out, end, event_ret);
    append_text(&out, end, "\ncode=");
    append_signed(&out, end, event.code);
    append_text(&out, end, "\nvalue=");
    append_signed(&out, end, event.value);
    append_text(&out, end, "\nstate=");
    append_signed(&out, end, state);
    finish_text(&out, end);

    bda_msgbox("Input", g_text);
    return 0;
}
