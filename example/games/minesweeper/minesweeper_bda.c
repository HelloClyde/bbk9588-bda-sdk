#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define VX_HEADER_SIZE 24
#define SCREEN_VX_BYTES (VX_HEADER_SIZE + SCREEN_WIDTH * SCREEN_HEIGHT * 2)

#define BOARD_WIDTH 9
#define BOARD_HEIGHT 9
#define BOARD_CELLS (BOARD_WIDTH * BOARD_HEIGHT)
#define MINE_COUNT 10
#define BOARD_X 12
#define BOARD_Y 52
#define CELL_SIZE 24

#define FLAG_BUTTON_X 12
#define FLAG_BUTTON_Y 280
#define FLAG_BUTTON_W 104
#define FLAG_BUTTON_H 30
#define NEW_BUTTON_X 124
#define NEW_BUTTON_Y 280
#define NEW_BUTTON_W 104
#define NEW_BUTTON_H 30

#define CELL_MINE   0x01u
#define CELL_OPEN   0x02u
#define CELL_FLAG   0x04u
#define CELL_QUEUED 0x08u

#define GAME_PLAYING 0
#define GAME_WON 1
#define GAME_LOST 2

#define TOUCH_QUEUE_SIZE 16
#define TOUCH_PREFIX_MESSAGE 0x0021u

static const char k_window_title[] = "MINES V1";
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\MINESV1.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\MINESV1.TXT";

static const u8 k_font[36][7] = {
    {0x0e, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0e},
    {0x04, 0x0c, 0x04, 0x04, 0x04, 0x04, 0x0e},
    {0x0e, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1f},
    {0x1e, 0x01, 0x01, 0x0e, 0x01, 0x01, 0x1e},
    {0x02, 0x06, 0x0a, 0x12, 0x1f, 0x02, 0x02},
    {0x1f, 0x10, 0x10, 0x1e, 0x01, 0x01, 0x1e},
    {0x0e, 0x10, 0x10, 0x1e, 0x11, 0x11, 0x0e},
    {0x1f, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08},
    {0x0e, 0x11, 0x11, 0x0e, 0x11, 0x11, 0x0e},
    {0x0e, 0x11, 0x11, 0x0f, 0x01, 0x01, 0x0e},
    {0x0e, 0x11, 0x11, 0x1f, 0x11, 0x11, 0x11},
    {0x1e, 0x11, 0x11, 0x1e, 0x11, 0x11, 0x1e},
    {0x0f, 0x10, 0x10, 0x10, 0x10, 0x10, 0x0f},
    {0x1e, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1e},
    {0x1f, 0x10, 0x10, 0x1e, 0x10, 0x10, 0x1f},
    {0x1f, 0x10, 0x10, 0x1e, 0x10, 0x10, 0x10},
    {0x0f, 0x10, 0x10, 0x17, 0x11, 0x11, 0x0f},
    {0x11, 0x11, 0x11, 0x1f, 0x11, 0x11, 0x11},
    {0x0e, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0e},
    {0x01, 0x01, 0x01, 0x01, 0x11, 0x11, 0x0e},
    {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11},
    {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1f},
    {0x11, 0x1b, 0x15, 0x15, 0x11, 0x11, 0x11},
    {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11},
    {0x0e, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0e},
    {0x1e, 0x11, 0x11, 0x1e, 0x10, 0x10, 0x10},
    {0x0e, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0d},
    {0x1e, 0x11, 0x11, 0x1e, 0x14, 0x12, 0x11},
    {0x0f, 0x10, 0x10, 0x0e, 0x01, 0x01, 0x1e},
    {0x1f, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04},
    {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0e},
    {0x11, 0x11, 0x11, 0x11, 0x11, 0x0a, 0x04},
    {0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0a},
    {0x11, 0x11, 0x0a, 0x04, 0x0a, 0x11, 0x11},
    {0x11, 0x11, 0x0a, 0x04, 0x04, 0x04, 0x04},
    {0x1f, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1f}
};

static u8 g_screen_vx[SCREEN_VX_BYTES];
static u8 g_cells[BOARD_CELLS];
static u8 g_flood_queue[BOARD_CELLS];
static u32 g_touch_queue[TOUCH_QUEUE_SIZE];
static volatile u32 g_touch_read;
static volatile u32 g_touch_write;
static bda_handle_t g_frame;
static bda_handle_t g_draw;
static bda_handle_t g_back;
static void *g_draw_object;
static const char *g_log_path;
static char g_log_line[96];
static u32 g_previous_keys;
static u32 g_round;
static u32 g_start_tick;
static u32 g_end_tick;
static u32 g_last_seconds;
static u32 g_key_resume_tick;
static int g_cursor_x;
static int g_cursor_y;
static int g_opened;
static int g_flags;
static int g_state;
static int g_mines_ready;
static int g_flag_mode;
static int g_exploded_index;
static int g_first_present;
static int g_failures;
static volatile int g_touch_active;
static volatile int g_need_render;
static volatile int g_detached;

static char *append_text(char *out, char *end, const char *text) {
    while (*text && out < end) {
        *out++ = *text++;
    }
    return out;
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char hex[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        if (out < end) {
            *out++ = hex[(value >> shift) & 0x0fu];
        }
    }
    return out;
}

static int open_log(const char *mode) {
    int file;

    if (g_log_path) {
        return bda_fs_fopen_raw(g_log_path, mode);
    }
    file = bda_fs_fopen_raw(k_log_path_a, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = k_log_path_a;
        return file;
    }
    file = bda_fs_fopen_raw(k_log_path_root, mode);
    if (bda_fs_file_is_valid(file)) {
        g_log_path = k_log_path_root;
    }
    return file;
}

static void reset_log(void) {
    int file;

    g_log_path = 0;
    file = open_log("wb");
    if (bda_fs_file_is_valid(file)) {
        (void)bda_fs_close_raw(file);
    }
}

static void write_log_line(char *out) {
    int file;
    u32 length;
    char *end = g_log_line + sizeof(g_log_line) - 1;

    out = append_text(out, end, "\r\n");
    *out = 0;
    length = (u32)(out - g_log_line);
    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_log_line, length);
    (void)bda_fs_close_raw(file);
}

static void log_text(const char *text) {
    write_log_line(append_text(
        g_log_line, g_log_line + sizeof(g_log_line) - 1, text
    ));
}

static void log_value(const char *label, u32 value) {
    char *out = g_log_line;
    char *end = g_log_line + sizeof(g_log_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, value);
    write_log_line(out);
}

static void write_u16_le(u8 *out, u16 value) {
    out[0] = (u8)value;
    out[1] = (u8)(value >> 8);
}

static void write_u32_le(u8 *out, u32 value) {
    out[0] = (u8)value;
    out[1] = (u8)(value >> 8);
    out[2] = (u8)(value >> 16);
    out[3] = (u8)(value >> 24);
}

static u16 rgb565(u32 red, u32 green, u32 blue) {
    return (u16)(((red & 0xf8u) << 8) | ((green & 0xfcu) << 3) | (blue >> 3));
}

static void init_screen_vx(void) {
    int index;

    bda_memset(g_screen_vx, 0, sizeof(g_screen_vx));
    g_screen_vx[0] = 'V';
    g_screen_vx[1] = 'X';
    for (index = 2; index < 6; ++index) {
        g_screen_vx[index] = 0xcc;
    }
    write_u32_le(g_screen_vx + 6, SCREEN_WIDTH);
    write_u32_le(g_screen_vx + 10, SCREEN_HEIGHT);
    for (index = 14; index < 20; ++index) {
        g_screen_vx[index] = 0xcc;
    }
    for (index = 20; index < VX_HEADER_SIZE; ++index) {
        g_screen_vx[index] = 0xff;
    }
}

static void put_pixel(int x, int y, u16 color) {
    u32 offset;

    if (x < 0 || x >= SCREEN_WIDTH || y < 0 || y >= SCREEN_HEIGHT) {
        return;
    }
    offset = VX_HEADER_SIZE + (u32)(y * SCREEN_WIDTH + x) * 2u;
    write_u16_le(g_screen_vx + offset, color);
}

static void fill_rect(int x, int y, int width, int height, u16 color) {
    int px;
    int py;

    for (py = y; py < y + height; ++py) {
        for (px = x; px < x + width; ++px) {
            put_pixel(px, py, color);
        }
    }
}

static void frame_rect(int x, int y, int width, int height, u16 color) {
    int i;

    for (i = 0; i < width; ++i) {
        put_pixel(x + i, y, color);
        put_pixel(x + i, y + height - 1, color);
    }
    for (i = 1; i + 1 < height; ++i) {
        put_pixel(x, y + i, color);
        put_pixel(x + width - 1, y + i, color);
    }
}

static int glyph_index(char character) {
    if (character >= '0' && character <= '9') {
        return character - '0';
    }
    if (character >= 'A' && character <= 'Z') {
        return 10 + character - 'A';
    }
    return -1;
}

static void draw_character(int x, int y, char character, int scale, u16 color) {
    int index = glyph_index(character);
    int row;
    int column;

    if (index < 0) {
        return;
    }
    for (row = 0; row < 7; ++row) {
        u8 bits = k_font[index][row];
        for (column = 0; column < 5; ++column) {
            if (bits & (1u << (4 - column))) {
                fill_rect(
                    x + column * scale,
                    y + row * scale,
                    scale,
                    scale,
                    color
                );
            }
        }
    }
}

static int text_width(const char *text, int scale) {
    int count = 0;

    while (*text++) {
        ++count;
    }
    return count ? count * 6 * scale - scale : 0;
}

static void draw_text(int x, int y, const char *text, int scale, u16 color) {
    while (*text) {
        draw_character(x, y, *text++, scale, color);
        x += 6 * scale;
    }
}

static void draw_text_centered(
    int center_x,
    int y,
    const char *text,
    int scale,
    u16 color
) {
    draw_text(center_x - text_width(text, scale) / 2, y, text, scale, color);
}

static void format_fixed(char *out, u32 value, int digits) {
    int index;

    for (index = digits - 1; index >= 0; --index) {
        out[index] = (char)('0' + value % 10u);
        value /= 10u;
    }
    out[digits] = 0;
}

static int cell_index(int x, int y) {
    return y * BOARD_WIDTH + x;
}

static int inside_board(int x, int y) {
    return x >= 0 && x < BOARD_WIDTH && y >= 0 && y < BOARD_HEIGHT;
}

static int neighbor_mines(int x, int y) {
    int dx;
    int dy;
    int count = 0;

    for (dy = -1; dy <= 1; ++dy) {
        for (dx = -1; dx <= 1; ++dx) {
            int nx = x + dx;
            int ny = y + dy;

            if ((dx || dy) && inside_board(nx, ny) &&
                (g_cells[cell_index(nx, ny)] & CELL_MINE)) {
                ++count;
            }
        }
    }
    return count;
}

static u32 next_random(u32 *state) {
    u32 value = *state;

    value ^= value << 13;
    value ^= value >> 17;
    value ^= value << 5;
    if (!value) {
        value = 0x6d2b79f5u;
    }
    *state = value;
    return value;
}

static void log_mine_masks(void) {
    u32 masks[3] = {0, 0, 0};
    int index;

    for (index = 0; index < BOARD_CELLS; ++index) {
        if (g_cells[index] & CELL_MINE) {
            masks[index / 32] |= 1u << (index & 31);
        }
    }
    log_value("MINES LOW=", masks[0]);
    log_value("MINES MID=", masks[1]);
    log_value("MINES HIGH=", masks[2]);
}

static void place_mines(int safe_x, int safe_y) {
    u32 random_state = bda_gui_tick_count_25ms() ^
        ((u32)(safe_x + 1) * 0x9e3779b9u) ^
        ((u32)(safe_y + 3) * 0x85ebca6bu) ^
        (g_round * 0xc2b2ae35u);
    int placed = 0;

    while (placed < MINE_COUNT) {
        int index = (int)(next_random(&random_state) % BOARD_CELLS);
        int x = index % BOARD_WIDTH;
        int y = index / BOARD_WIDTH;

        if ((x >= safe_x - 1 && x <= safe_x + 1 &&
             y >= safe_y - 1 && y <= safe_y + 1) ||
            (g_cells[index] & CELL_MINE)) {
            continue;
        }
        g_cells[index] |= CELL_MINE;
        ++placed;
    }
    g_mines_ready = 1;
    g_start_tick = bda_gui_tick_count_25ms();
    g_last_seconds = 0;
    log_mine_masks();
}

static u32 game_seconds(u32 now) {
    u32 end;
    u32 seconds;

    if (!g_mines_ready) {
        return 0;
    }
    end = g_state == GAME_PLAYING ? now : g_end_tick;
    seconds = bda_gui_tick_elapsed_25ms(g_start_tick, end) / 40u;
    return seconds > 999u ? 999u : seconds;
}

static void new_game(void) {
    bda_memset(g_cells, 0, sizeof(g_cells));
    ++g_round;
    g_cursor_x = BOARD_WIDTH / 2;
    g_cursor_y = BOARD_HEIGHT / 2;
    g_opened = 0;
    g_flags = 0;
    g_state = GAME_PLAYING;
    g_mines_ready = 0;
    g_flag_mode = 0;
    g_exploded_index = -1;
    g_start_tick = 0;
    g_end_tick = 0;
    g_last_seconds = 0;
    g_need_render = 1;
    log_value("NEW ROUND=", g_round);
}

static void lose_game(int exploded_index) {
    g_state = GAME_LOST;
    g_exploded_index = exploded_index;
    g_end_tick = bda_gui_tick_count_25ms();
    g_need_render = 1;
    log_value("LOST CELL=", (u32)exploded_index);
}

static void check_win(void) {
    int index;

    if (g_opened != BOARD_CELLS - MINE_COUNT) {
        return;
    }
    g_state = GAME_WON;
    g_end_tick = bda_gui_tick_count_25ms();
    g_flags = MINE_COUNT;
    for (index = 0; index < BOARD_CELLS; ++index) {
        if (g_cells[index] & CELL_MINE) {
            g_cells[index] |= CELL_FLAG;
        }
    }
    g_need_render = 1;
    log_value("WON TICKS=", g_end_tick - g_start_tick);
}

static void flood_open(int start_x, int start_y) {
    int head = 0;
    int tail = 0;
    int start = cell_index(start_x, start_y);

    if (g_cells[start] & (CELL_OPEN | CELL_FLAG | CELL_MINE)) {
        return;
    }
    g_cells[start] |= CELL_QUEUED;
    g_flood_queue[tail++] = (u8)start;
    while (head < tail) {
        int index = g_flood_queue[head++];
        int x = index % BOARD_WIDTH;
        int y = index / BOARD_WIDTH;
        int dx;
        int dy;

        g_cells[index] &= (u8)~CELL_QUEUED;
        if (g_cells[index] & (CELL_OPEN | CELL_FLAG | CELL_MINE)) {
            continue;
        }
        g_cells[index] |= CELL_OPEN;
        ++g_opened;
        if (neighbor_mines(x, y) != 0) {
            continue;
        }
        for (dy = -1; dy <= 1; ++dy) {
            for (dx = -1; dx <= 1; ++dx) {
                int nx = x + dx;
                int ny = y + dy;
                int next;

                if (!inside_board(nx, ny) || (!dx && !dy)) {
                    continue;
                }
                next = cell_index(nx, ny);
                if (!(g_cells[next] &
                      (CELL_OPEN | CELL_FLAG | CELL_MINE | CELL_QUEUED))) {
                    g_cells[next] |= CELL_QUEUED;
                    g_flood_queue[tail++] = (u8)next;
                }
            }
        }
    }
}

static void open_cell(int x, int y) {
    int index;

    if (g_state != GAME_PLAYING || !inside_board(x, y)) {
        return;
    }
    index = cell_index(x, y);
    if (g_cells[index] & CELL_FLAG) {
        return;
    }
    if (!g_mines_ready) {
        place_mines(x, y);
        log_value("FIRST CELL=", (u32)index);
    }
    if (g_cells[index] & CELL_OPEN) {
        int near = neighbor_mines(x, y);
        int adjacent_flags = 0;
        int dx;
        int dy;

        if (!near) {
            return;
        }
        for (dy = -1; dy <= 1; ++dy) {
            for (dx = -1; dx <= 1; ++dx) {
                int nx = x + dx;
                int ny = y + dy;

                if ((dx || dy) && inside_board(nx, ny) &&
                    (g_cells[cell_index(nx, ny)] & CELL_FLAG)) {
                    ++adjacent_flags;
                }
            }
        }
        if (adjacent_flags != near) {
            return;
        }
        for (dy = -1; dy <= 1 && g_state == GAME_PLAYING; ++dy) {
            for (dx = -1; dx <= 1 && g_state == GAME_PLAYING; ++dx) {
                int nx = x + dx;
                int ny = y + dy;
                int next;

                if (!inside_board(nx, ny) || (!dx && !dy)) {
                    continue;
                }
                next = cell_index(nx, ny);
                if (g_cells[next] & (CELL_OPEN | CELL_FLAG)) {
                    continue;
                }
                if (g_cells[next] & CELL_MINE) {
                    lose_game(next);
                } else {
                    flood_open(nx, ny);
                }
            }
        }
    } else if (g_cells[index] & CELL_MINE) {
        lose_game(index);
    } else {
        flood_open(x, y);
    }
    check_win();
    g_need_render = 1;
}

static void toggle_flag_at(int x, int y) {
    int index;

    if (g_state != GAME_PLAYING || !inside_board(x, y)) {
        return;
    }
    index = cell_index(x, y);
    if (g_cells[index] & CELL_OPEN) {
        return;
    }
    if (g_cells[index] & CELL_FLAG) {
        g_cells[index] &= (u8)~CELL_FLAG;
        --g_flags;
    } else if (g_flags < MINE_COUNT) {
        g_cells[index] |= CELL_FLAG;
        ++g_flags;
    }
    g_need_render = 1;
    log_value((g_cells[index] & CELL_FLAG) ? "FLAG CELL=" : "UNFLAG CELL=", (u32)index);
}

static void draw_flag(int x, int y, u16 pole, u16 cloth) {
    int row;

    fill_rect(x + 7, y + 4, 2, 14, pole);
    fill_rect(x + 4, y + 17, 9, 2, pole);
    for (row = 0; row < 8; ++row) {
        fill_rect(x + 9, y + 4 + row, 8 - row, 1, cloth);
    }
}

static void draw_mine(int x, int y, u16 body, u16 center) {
    fill_rect(x + 7, y + 5, 8, 14, body);
    fill_rect(x + 4, y + 8, 14, 8, body);
    fill_rect(x + 10, y + 3, 2, 18, body);
    fill_rect(x + 2, y + 11, 18, 2, body);
    fill_rect(x + 9, y + 9, 4, 4, center);
}

static u16 number_color(int number) {
    switch (number) {
        case 1: return rgb565(30, 90, 210);
        case 2: return rgb565(20, 135, 75);
        case 3: return rgb565(210, 55, 55);
        case 4: return rgb565(90, 55, 180);
        case 5: return rgb565(155, 55, 55);
        case 6: return rgb565(20, 145, 155);
        default: return rgb565(45, 55, 65);
    }
}

static void draw_cell(int x, int y) {
    int index = cell_index(x, y);
    int left = BOARD_X + x * CELL_SIZE;
    int top = BOARD_Y + y * CELL_SIZE;
    u8 cell = g_cells[index];
    u16 border = rgb565(12, 29, 40);
    u16 closed = rgb565(45, 91, 112);
    u16 highlight = rgb565(78, 145, 158);
    u16 shadow = rgb565(24, 54, 72);
    u16 opened = rgb565(218, 226, 228);
    u16 grid = rgb565(132, 148, 155);
    u16 cursor = rgb565(250, 194, 45);

    fill_rect(left, top, CELL_SIZE, CELL_SIZE, border);
    if (cell & CELL_OPEN) {
        fill_rect(left + 1, top + 1, CELL_SIZE - 2, CELL_SIZE - 2, opened);
        fill_rect(left + 1, top + CELL_SIZE - 2, CELL_SIZE - 2, 1, grid);
        fill_rect(left + CELL_SIZE - 2, top + 1, 1, CELL_SIZE - 2, grid);
        if (cell & CELL_MINE) {
            u16 blast = index == g_exploded_index
                ? rgb565(230, 65, 55)
                : rgb565(188, 202, 205);
            fill_rect(left + 2, top + 2, CELL_SIZE - 4, CELL_SIZE - 4, blast);
            draw_mine(left + 1, top + 1, rgb565(25, 30, 34), rgb565(245, 245, 245));
        } else {
            int near = neighbor_mines(x, y);
            if (near) {
                char digit[2];
                digit[0] = (char)('0' + near);
                digit[1] = 0;
                draw_text(left + 7, top + 5, digit, 2, number_color(near));
            }
        }
    } else {
        fill_rect(left + 1, top + 1, CELL_SIZE - 2, CELL_SIZE - 2, closed);
        fill_rect(left + 2, top + 2, CELL_SIZE - 4, 2, highlight);
        fill_rect(left + 2, top + 2, 2, CELL_SIZE - 4, highlight);
        fill_rect(left + 2, top + CELL_SIZE - 4, CELL_SIZE - 4, 2, shadow);
        fill_rect(left + CELL_SIZE - 4, top + 2, 2, CELL_SIZE - 4, shadow);
        if (cell & CELL_FLAG) {
            if (g_state == GAME_LOST && !(cell & CELL_MINE)) {
                int i;
                for (i = 0; i < 14; ++i) {
                    fill_rect(left + 5 + i, top + 5 + i, 2, 2, rgb565(235, 65, 55));
                    fill_rect(left + 18 - i, top + 5 + i, 2, 2, rgb565(235, 65, 55));
                }
            } else {
                draw_flag(left + 1, top + 1, rgb565(235, 240, 235), rgb565(238, 74, 55));
            }
        } else if (g_state == GAME_LOST && (cell & CELL_MINE)) {
            draw_mine(left + 1, top + 1, rgb565(20, 25, 30), rgb565(238, 74, 55));
        }
    }
    if (x == g_cursor_x && y == g_cursor_y) {
        frame_rect(left + 2, top + 2, CELL_SIZE - 4, CELL_SIZE - 4, cursor);
        frame_rect(left + 3, top + 3, CELL_SIZE - 6, CELL_SIZE - 6, cursor);
    }
}

static void draw_button(
    int x,
    int y,
    int width,
    int height,
    const char *label,
    int active
) {
    u16 outer = active ? rgb565(242, 181, 45) : rgb565(55, 76, 88);
    u16 inner = active ? rgb565(183, 80, 48) : rgb565(31, 51, 62);
    u16 text = rgb565(245, 247, 239);

    fill_rect(x, y, width, height, outer);
    fill_rect(x + 2, y + 2, width - 4, height - 4, inner);
    draw_text_centered(x + width / 2, y + 8, label, 2, text);
}

static void render_screen(void) {
    int x;
    int y;
    char mines_text[3];
    char seconds_text[4];
    u32 seconds = game_seconds(bda_gui_tick_count_25ms());
    u32 remaining = (u32)(MINE_COUNT - g_flags);
    u16 background = rgb565(10, 21, 30);
    u16 header = rgb565(20, 39, 52);
    u16 white = rgb565(238, 244, 242);
    u16 cyan = rgb565(44, 196, 196);
    u16 muted = rgb565(138, 166, 173);

    fill_rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, background);
    fill_rect(0, 0, SCREEN_WIDTH, 48, header);
    fill_rect(0, 46, SCREEN_WIDTH, 2, cyan);
    draw_text_centered(SCREEN_WIDTH / 2, 7, "MINESWEEPER", 2, white);
    format_fixed(mines_text, remaining, 2);
    format_fixed(seconds_text, seconds, 3);
    draw_text(12, 33, "MINES", 1, muted);
    draw_text(48, 33, mines_text, 1, white);
    draw_text(162, 33, "TIME", 1, muted);
    draw_text(192, 33, seconds_text, 1, white);

    fill_rect(BOARD_X - 2, BOARD_Y - 2,
              BOARD_WIDTH * CELL_SIZE + 4,
              BOARD_HEIGHT * CELL_SIZE + 4,
              rgb565(5, 12, 18));
    for (y = 0; y < BOARD_HEIGHT; ++y) {
        for (x = 0; x < BOARD_WIDTH; ++x) {
            draw_cell(x, y);
        }
    }

    if (g_state != GAME_PLAYING) {
        u16 banner = g_state == GAME_WON
            ? rgb565(22, 118, 76)
            : rgb565(164, 49, 48);
        fill_rect(28, 137, 184, 36, rgb565(4, 12, 17));
        fill_rect(31, 140, 178, 30, banner);
        draw_text_centered(
            SCREEN_WIDTH / 2,
            148,
            g_state == GAME_WON ? "YOU WIN" : "BOOM",
            2,
            white
        );
    }

    draw_button(
        FLAG_BUTTON_X, FLAG_BUTTON_Y, FLAG_BUTTON_W, FLAG_BUTTON_H,
        g_flag_mode ? "FLAG ON" : "FLAG", g_flag_mode
    );
    draw_button(
        NEW_BUTTON_X, NEW_BUTTON_Y, NEW_BUTTON_W, NEW_BUTTON_H,
        "NEW", g_state != GAME_PLAYING
    );
    draw_text_centered(SCREEN_WIDTH / 2, 313, "ESC EXIT", 1, muted);
}

static int present_screen(void) {
    void *old_object;
    int draw_result;
    int copy_result;

    if (!g_draw || !g_back || !g_draw_object) {
        return 0;
    }
    render_screen();
    draw_result = bda_gui_draw_vx(g_back, 0, 0, g_screen_vx);
    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    copy_result = bda_gui_context_copy(
        g_back, 0, 0, SCREEN_WIDTH, SCREEN_HEIGHT,
        g_draw, 0, 0, 0
    );
    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
    if (g_first_present) {
        log_value("FIRST VX DRAW=", (u32)draw_result);
        log_value("FIRST PRESENT=", (u32)copy_result);
        g_first_present = 0;
    }
    if (draw_result || copy_result) {
        ++g_failures;
        log_text("PRESENT FAILURE");
        return 0;
    }
    g_need_render = 0;
    g_last_seconds = game_seconds(bda_gui_tick_count_25ms());
    return 1;
}

static int point_in_rect(int x, int y, int left, int top, int width, int height) {
    return x >= left && x < left + width && y >= top && y < top + height;
}

static void handle_touch(u32 packed) {
    int x = (s32)(short)(packed & 0xffffu);
    int y = (s32)(short)((packed >> 16) & 0xffffu);

    log_value("TOUCH=", packed);
    if (point_in_rect(x, y, BOARD_X, BOARD_Y,
                      BOARD_WIDTH * CELL_SIZE, BOARD_HEIGHT * CELL_SIZE)) {
        int board_x = (x - BOARD_X) / CELL_SIZE;
        int board_y = (y - BOARD_Y) / CELL_SIZE;

        g_cursor_x = board_x;
        g_cursor_y = board_y;
        if (g_flag_mode) {
            toggle_flag_at(board_x, board_y);
        } else {
            open_cell(board_x, board_y);
        }
        g_need_render = 1;
    } else if (point_in_rect(
        x, y, FLAG_BUTTON_X, FLAG_BUTTON_Y, FLAG_BUTTON_W, FLAG_BUTTON_H
    )) {
        if (g_state == GAME_PLAYING) {
            g_flag_mode = !g_flag_mode;
            g_need_render = 1;
            log_value("FLAG MODE=", (u32)g_flag_mode);
        }
    } else if (point_in_rect(
        x, y, NEW_BUTTON_X, NEW_BUTTON_Y, NEW_BUTTON_W, NEW_BUTTON_H
    )) {
        new_game();
    }
}

static void queue_touch(u32 packed) {
    u32 write = g_touch_write;
    u32 next = (write + 1u) % TOUCH_QUEUE_SIZE;

    if (next == g_touch_read) {
        return;
    }
    g_touch_queue[write] = packed;
    g_touch_write = next;
}

static void drain_touches(void) {
    while (g_touch_read != g_touch_write) {
        u32 packed = g_touch_queue[g_touch_read];
        g_touch_read = (g_touch_read + 1u) % TOUCH_QUEUE_SIZE;
        handle_touch(packed);
    }
}

static u32 packet_mask(const bda_gui_input_packet_t *packet) {
    u32 mask = 0;

    if (packet->bytes[BDA_INPUT_PACKET_RIGHT_INDEX] == 1u) mask |= 1u << 0;
    if (packet->bytes[BDA_INPUT_PACKET_LEFT_INDEX] == 1u) mask |= 1u << 1;
    if (packet->bytes[BDA_INPUT_PACKET_DOWN_INDEX] == 1u) mask |= 1u << 2;
    if (packet->bytes[BDA_INPUT_PACKET_UP_INDEX] == 1u) mask |= 1u << 3;
    if (packet->bytes[BDA_INPUT_PACKET_ESCAPE_INDEX] == 1u) mask |= 1u << 4;
    if (packet->bytes[BDA_INPUT_PACKET_ENTER_INDEX] == 1u) mask |= 1u << 5;
    return mask;
}

static int poll_keys(void) {
    bda_gui_input_packet_t packet;
    u32 now = bda_gui_tick_count_25ms();
    u32 current;
    u32 pressed;

    if (g_touch_active || (s32)(now - g_key_resume_tick) < 0) {
        g_previous_keys = 0;
        return 0;
    }
    (void)bda_gui_input_packet(&packet);
    current = packet_mask(&packet);
    pressed = current & ~g_previous_keys;
    g_previous_keys = current;
    if (pressed & (1u << 4)) {
        return 1;
    }
    if (pressed & (1u << 0)) {
        if (g_cursor_x + 1 < BOARD_WIDTH) ++g_cursor_x;
        g_need_render = 1;
    }
    if (pressed & (1u << 1)) {
        if (g_cursor_x > 0) --g_cursor_x;
        g_need_render = 1;
    }
    if (pressed & (1u << 2)) {
        if (g_cursor_y + 1 < BOARD_HEIGHT) ++g_cursor_y;
        g_need_render = 1;
    }
    if (pressed & (1u << 3)) {
        if (g_cursor_y > 0) --g_cursor_y;
        g_need_render = 1;
    }
    if (pressed & (1u << 5)) {
        if (g_state == GAME_PLAYING) {
            open_cell(g_cursor_x, g_cursor_y);
        } else {
            new_game();
        }
    }
    return 0;
}

static int mines_window_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        g_frame = handle;
        g_draw = bda_gui_current_draw(handle);
        if (!g_draw_object) {
            g_draw_object = bda_gui_draw_object_create(7);
        }
        g_need_render = 1;
    } else if (message == BDA_MSG_REDRAW_INPUT) {
        g_need_render = 1;
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        g_draw = 0;
        g_detached = 1;
    }
    if (message == TOUCH_PREFIX_MESSAGE) {
        g_key_resume_tick = bda_gui_tick_count_25ms() + 4u;
    }
    if (message == BDA_MSG_TOUCH_RELEASE) {
        g_touch_active = 0;
        g_key_resume_tick = bda_gui_tick_count_25ms() + 2u;
        queue_touch(lparam);
        return 1;
    }
    if (message == BDA_MSG_TOUCH_COORDINATE) {
        g_touch_active = 1;
        g_key_resume_tick = bda_gui_tick_count_25ms() + 2u;
        return 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

static void wait_escape_release(void) {
    bda_gui_input_packet_t packet;

    do {
        (void)bda_gui_input_packet(&packet);
        bda_sys_delay(1);
    } while (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ESCAPE));
    g_previous_keys = 0;
    g_key_resume_tick = 0;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    int close_requested = 0;
    u32 close_wait = 0;

    reset_log();
    log_text("START MINESWEEPER V1");
    init_screen_vx();
    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    bda_memset(g_touch_queue, 0, sizeof(g_touch_queue));
    g_touch_read = 0;
    g_touch_write = 0;
    g_frame = 0;
    g_draw = 0;
    g_back = 0;
    g_draw_object = 0;
    g_previous_keys = 0;
    g_round = 0;
    g_first_present = 1;
    g_failures = 0;
    g_touch_active = 0;
    g_need_render = 1;
    g_detached = 0;

    descriptor.style = 0;
    descriptor.title = k_window_title;
    descriptor.wndproc = mines_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = 0;

    log_text("BEFORE REGISTER");
    g_frame = (bda_handle_t)bda_gui_register_frame_desc(&descriptor);
    log_value("REGISTER=", (u32)g_frame);
    if (!g_frame || (s32)g_frame == -1) {
        log_text("RESULT=FRAME FAIL");
        return 1;
    }
    log_value("ACTIVATE=", (u32)bda_gui_frame_activate(g_frame, 0x100));
    if (!g_draw) {
        g_draw = bda_gui_current_draw(g_frame);
    }
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create(7);
    }
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        log_text("RESULT=DRAW FAIL");
        bda_gui_close_frame(g_frame);
        return 2;
    }
    log_text("BEFORE BACK CREATE");
    g_back = bda_gui_compatible_context_create(g_draw);
    log_value("BACK=", (u32)g_back);
    if (!g_back || (s32)g_back == -1) {
        log_text("RESULT=BACK FAIL");
        bda_gui_close_frame(g_frame);
        return 3;
    }

    new_game();
    if (!present_screen()) {
        log_text("RESULT=FIRST PRESENT FAIL");
    }
    log_text("LOOP READY");

    for (;;) {
        int pump_result = bda_gui_event_pump_frame_once(&message, g_frame);

        drain_touches();
        if (!close_requested && poll_keys()) {
            log_text("ESC DOWN");
            wait_escape_release();
            log_text("ESC UP");
            log_value("STOP=", (u32)bda_gui_frame_stop(g_frame));
            log_value("RELEASE=", (u32)bda_gui_frame_release(g_frame));
            close_requested = 1;
        }
        if (!close_requested && g_state == GAME_PLAYING && g_mines_ready) {
            u32 seconds = game_seconds(bda_gui_tick_count_25ms());
            if (seconds != g_last_seconds) {
                g_need_render = 1;
            }
        }
        if (!close_requested && g_need_render && g_draw) {
            (void)present_screen();
        }
        bda_sys_delay(1);
        if (close_requested) {
            ++close_wait;
            if (!pump_result || g_detached || close_wait >= 128u) {
                break;
            }
        }
    }

    log_text("LOOP END");
    if (g_frame) {
        bda_gui_close_frame(g_frame);
        g_frame = 0;
    }
    if (g_back && (s32)g_back != -1) {
        log_text("BEFORE BACK FREE");
        bda_gui_compatible_context_free(g_back);
        g_back = 0;
        log_text("BACK FREED");
    }
    log_value("FAILURES=", (u32)g_failures);
    log_text(g_failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END MINESWEEPER V1");
    return g_failures ? 4 : 0;
}
