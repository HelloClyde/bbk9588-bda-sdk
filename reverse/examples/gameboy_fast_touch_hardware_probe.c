#include "../bda_research_sdk.h"

static const char k_log_path[] = "A:\\FASTTOUCH.TXT";
static char g_line[192];

#define GPIOC_PIN_REGISTER 0xb0010100u
#define GPIOC_TOUCH_PEN_MASK 0x00040000u

static u32 read_u32(u32 address) {
    return *(volatile const u32 *)address;
}

static int read_pen_gpio(u32 *out_gpio_word) {
    u32 value = read_u32(GPIOC_PIN_REGISTER);

    *out_gpio_word = value;
    return (value & GPIOC_TOUCH_PEN_MASK) == 0u;
}

static char *append_char(char *out, char *end, char value) {
    if (out < end) {
        *out++ = value;
    }
    return out;
}

static char *append_text(char *out, char *end, const char *text) {
    while (*text) {
        out = append_char(out, end, *text++);
    }
    return out;
}

static char *append_u32(char *out, char *end, u32 value) {
    char digits[10];
    int count = 0;

    if (value == 0u) {
        return append_char(out, end, '0');
    }
    while (value != 0u && count < (int)sizeof(digits)) {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    }
    while (count > 0) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char digits[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        out = append_char(out, end, digits[(value >> shift) & 0x0fu]);
    }
    return out;
}

static u32 text_length(const char *text) {
    u32 length = 0u;

    while (text[length] != 0) {
        ++length;
    }
    return length;
}

static void write_line(const char *mode, const char *text) {
    static const char newline[] = "\r\n";
    int file = bda_fs_fopen_raw(k_log_path, mode);

    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, text, text_length(text));
    (void)bda_fs_write_raw(file, newline, 2u);
    (void)bda_fs_close_raw(file);
}

static void log_fixed_function_words(void) {
    u32 address;
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "FIXED VA WORDS");
    for (address = 0x80059f68u; address < 0x80059f80u; address += 4u) {
        out = append_char(out, end, ' ');
        out = append_hex32(out, end, read_u32(address));
    }
    *out = 0;
    write_line("ab", g_line);
}

static void log_first_gpio(u32 gpio_word, int pen_down) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "FIRST GPIO=");
    out = append_hex32(out, end, gpio_word);
    out = append_text(out, end, " PEN=");
    out = append_u32(out, end, (u32)pen_down);
    *out = 0;
    write_line("ab", g_line);
}

static void log_sample(const char *prefix, u32 tick, u16 x, u16 y) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, prefix);
    out = append_text(out, end, " TICK=");
    out = append_u32(out, end, tick);
    out = append_text(out, end, " X=");
    out = append_u32(out, end, (u32)x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, (u32)y);
    *out = 0;
    write_line("ab", g_line);
}

static void log_heartbeat(
    u32 ticks,
    u32 loops,
    u32 pen_reads,
    u32 position_reads,
    u32 coordinate_changes,
    u32 gpio_word,
    u16 x,
    u16 y
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "HEARTBEAT TICKS=");
    out = append_u32(out, end, ticks);
    out = append_text(out, end, " LOOPS=");
    out = append_u32(out, end, loops);
    out = append_text(out, end, " PEN_READS=");
    out = append_u32(out, end, pen_reads);
    out = append_text(out, end, " POS_READS=");
    out = append_u32(out, end, position_reads);
    out = append_text(out, end, " XYCHG=");
    out = append_u32(out, end, coordinate_changes);
    out = append_text(out, end, " GPIO=");
    out = append_hex32(out, end, gpio_word);
    out = append_text(out, end, " X=");
    out = append_u32(out, end, (u32)x);
    out = append_text(out, end, " Y=");
    out = append_u32(out, end, (u32)y);
    *out = 0;
    write_line("ab", g_line);
}

static void log_exit_value(const char *prefix, u32 value) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, prefix);
    out = append_hex32(out, end, value);
    *out = 0;
    write_line("ab", g_line);
}

static void wait_escape_release(void) {
    bda_gui_input_packet_like_t packet;

    do {
        (void)bda_gui_input_packet_like(&packet);
    } while (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE));
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_gui_input_packet_like_t packet;
    u32 start_tick;
    u32 last_heartbeat_tick;
    u32 loops = 0u;
    u32 pen_reads = 0u;
    u32 position_reads = 0u;
    u32 coordinate_changes = 0u;
    u32 gpio_word = 0u;
    int last_pen;
    u16 last_x = 0xffffu;
    u16 last_y = 0xffffu;

    write_line("wb", "START GAMEBOY FAST TOUCH HARDWARE PROBE V3");
    write_line("ab", "PATH=DIRECT GPIOC MMIO + GUI POSITION; NO FIXED VA CALL");
    log_fixed_function_words();
    write_line("ab", "BEFORE FIRST GPIO MMIO");
    last_pen = read_pen_gpio(&gpio_word);
    ++pen_reads;
    log_first_gpio(gpio_word, last_pen);

    start_tick = bda_gui_tick_count_25ms_like();
    last_heartbeat_tick = start_tick;

    if (last_pen) {
        write_line("ab", "BEFORE FIRST POSITION");
        bda_gui_touch_position_like(&last_x, &last_y);
        ++position_reads;
        log_sample("FIRST POSITION", 0u, last_x, last_y);
    }
    write_line("ab", "READY TOUCH SCREEN; ESC TO EXIT");

    for (;;) {
        u32 now_tick = bda_gui_tick_count_25ms_like();
        u32 elapsed_ticks = now_tick - start_tick;
        int pen_down;

        ++loops;
        pen_down = read_pen_gpio(&gpio_word);
        ++pen_reads;

        if (pen_down) {
            u16 x = last_x;
            u16 y = last_y;

            if (position_reads == 0u) {
                write_line("ab", "PEN DOWN; BEFORE FIRST POSITION");
            }
            bda_gui_touch_position_like(&x, &y);
            ++position_reads;
            if (!last_pen) {
                log_sample("PEN DOWN", elapsed_ticks, x, y);
            }
            if (x != last_x || y != last_y) {
                ++coordinate_changes;
            }
            last_x = x;
            last_y = y;
        } else if (!pen_down && last_pen) {
            log_sample("PEN UP", elapsed_ticks, last_x, last_y);
        }
        last_pen = pen_down;

        if ((loops & 0x3fu) == 0u) {
            (void)bda_gui_input_packet_like(&packet);
            if (bda_gui_input_packet_key_pressed_like(&packet, BDA_KEY_ESCAPE)) {
                write_line("ab", "ESC DOWN");
                wait_escape_release();
                write_line("ab", "ESC UP");
                break;
            }
        }

        if (now_tick - last_heartbeat_tick >= 40u) {
            log_heartbeat(
                elapsed_ticks,
                loops,
                pen_reads,
                position_reads,
                coordinate_changes,
                gpio_word,
                last_x,
                last_y
            );
            last_heartbeat_tick = now_tick;
        }
    }

    log_exit_value("FINAL TICK=", bda_gui_tick_count_25ms_like() - start_tick);
    write_line("ab", "RESULT=PASS");
    write_line("ab", "END GAMEBOY FAST TOUCH HARDWARE PROBE V3");
    return 0;
}
