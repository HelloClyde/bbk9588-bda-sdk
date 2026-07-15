#include "bda_sdk.h"

#define BOARD_W 8
#define BOARD_H 8
#define BOARD_CELLS (BOARD_W * BOARD_H)
#define MINE_COUNT 10

#define CELL_MINE 0x01u
#define CELL_OPEN 0x02u
#define CELL_FLAG 0x04u

#define GAME_PLAYING 0
#define GAME_WON 1
#define GAME_LOST 2

#define KEY_UP 4
#define KEY_DOWN 5
#define KEY_LEFT 6
#define KEY_RIGHT 7
#define KEY_FLAG 9
#define KEY_OK 10

#define KE_ESC_LIKE 0x01
#define KE_ENTER_LIKE 0x1c
#define KE_UP_LIKE 0x67
#define KE_LEFT_LIKE 0x69
#define KE_RIGHT_LIKE 0x6a
#define KE_DOWN_LIKE 0x6c

#define SCREEN_W 240
#define SCREEN_H 320
#define BOARD_X 32
#define BOARD_Y 55
#define CELL_SIZE 22

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static void *g_draw_object;
static u8 g_cells[BOARD_CELLS];
static u8 g_queue[BOARD_CELLS];
static int g_cursor_x;
static int g_cursor_y;
static int g_opened;
static int g_flags;
static int g_state;
static int g_key_latch;
static int g_dirty;
static int g_first_draw;
static u32 g_dirty_cells_low;
static u32 g_dirty_cells_high;

static const u8 k_mines[MINE_COUNT] = {
    3, 7, 10, 20, 25, 34, 43, 49, 54, 61
};

static int cell_index(int x, int y) {
    return y * BOARD_W + x;
}

static void mark_cell_dirty(int index) {
    if (index < 32) {
        g_dirty_cells_low |= 1u << index;
    } else {
        g_dirty_cells_high |= 1u << (index - 32);
    }
    g_dirty = 1;
}

static void mark_all_cells_dirty(void) {
    g_dirty_cells_low = 0xffffffffu;
    g_dirty_cells_high = 0xffffffffu;
    g_dirty = 1;
}

static int in_board(int x, int y) {
    return x >= 0 && x < BOARD_W && y >= 0 && y < BOARD_H;
}

static int neighbor_mines(int x, int y) {
    int dx;
    int dy;
    int count = 0;
    for (dy = -1; dy <= 1; ++dy) {
        for (dx = -1; dx <= 1; ++dx) {
            int nx = x + dx;
            int ny = y + dy;
            if ((dx || dy) && in_board(nx, ny) &&
                (g_cells[cell_index(nx, ny)] & CELL_MINE)) {
                ++count;
            }
        }
    }
    return count;
}

static void reset_game(void) {
    int i;
    bda_memset(g_cells, 0, sizeof(g_cells));
    for (i = 0; i < MINE_COUNT; ++i) {
        g_cells[k_mines[i]] |= CELL_MINE;
    }
    g_cursor_x = 0;
    g_cursor_y = 0;
    g_opened = 0;
    g_flags = 0;
    g_state = GAME_PLAYING;
    g_key_latch = 0;
    mark_all_cells_dirty();
}

static void reveal_all_mines(void) {
    int i;
    for (i = 0; i < BOARD_CELLS; ++i) {
        if (g_cells[i] & CELL_MINE) {
            g_cells[i] |= CELL_OPEN;
            mark_cell_dirty(i);
        }
    }
}

static void open_from(int start_x, int start_y) {
    int head = 0;
    int tail = 0;
    int start = cell_index(start_x, start_y);

    if (g_cells[start] & (CELL_OPEN | CELL_FLAG)) {
        return;
    }
    if (g_cells[start] & CELL_MINE) {
        g_cells[start] |= CELL_OPEN;
        mark_cell_dirty(start);
        reveal_all_mines();
        g_state = GAME_LOST;
        return;
    }

    g_queue[tail++] = (u8)start;
    while (head < tail) {
        int idx = g_queue[head++];
        int x = idx % BOARD_W;
        int y = idx / BOARD_W;
        int dx;
        int dy;

        if (g_cells[idx] & (CELL_OPEN | CELL_FLAG | CELL_MINE)) {
            continue;
        }
        g_cells[idx] |= CELL_OPEN;
        mark_cell_dirty(idx);
        ++g_opened;

        if (neighbor_mines(x, y) != 0) {
            continue;
        }
        for (dy = -1; dy <= 1; ++dy) {
            for (dx = -1; dx <= 1; ++dx) {
                int nx = x + dx;
                int ny = y + dy;
                int nidx;
                if (!in_board(nx, ny) || (!dx && !dy)) {
                    continue;
                }
                nidx = cell_index(nx, ny);
                if (!(g_cells[nidx] & (CELL_OPEN | CELL_FLAG | CELL_MINE)) &&
                    tail < BOARD_CELLS) {
                    g_queue[tail++] = (u8)nidx;
                }
            }
        }
    }

    if (g_opened == BOARD_CELLS - MINE_COUNT) {
        g_state = GAME_WON;
    }
}

static void toggle_flag(void) {
    int idx;
    if (g_state != GAME_PLAYING) {
        return;
    }
    idx = cell_index(g_cursor_x, g_cursor_y);
    if (g_cells[idx] & CELL_OPEN) {
        return;
    }
    if (g_cells[idx] & CELL_FLAG) {
        g_cells[idx] &= (u8)~CELL_FLAG;
        --g_flags;
    } else if (g_flags < MINE_COUNT) {
        g_cells[idx] |= CELL_FLAG;
        ++g_flags;
    }
    mark_cell_dirty(idx);
}

static u32 rgb(u32 r, u32 g, u32 b) {
    return (u32)bda_gui_rgb_like(g_draw, r, g, b);
}

static void set_text_color(u32 color) {
    bda_gui_set_text_color_like(g_draw, color);
}

static void draw_label(s32 x, s32 y, const char *text, u32 color) {
    set_text_color(color);
    bda_gui_draw_text_like(g_draw, x, y, text, -1);
}

static void fill_box(s32 left, s32 top, s32 right, s32 bottom, u32 color) {
    bda_gui_set_fill_color_like(g_draw, color);
    bda_gui_rectangle_like(g_draw, left, top, right, bottom);
}

static void make_status(char *out) {
    const char *prefix;
    int pos = 0;
    int i;

    if (g_state == GAME_WON) {
        prefix = "WIN  F ";
    } else if (g_state == GAME_LOST) {
        prefix = "BOOM F ";
    } else {
        prefix = "PLAY F ";
    }
    for (i = 0; prefix[i]; ++i) {
        out[pos++] = prefix[i];
    }
    out[pos++] = (char)('0' + (g_flags / 10));
    out[pos++] = (char)('0' + (g_flags % 10));
    out[pos++] = '/';
    out[pos++] = '1';
    out[pos++] = '0';
    out[pos] = 0;
}

static void compose_cell(int x, int y) {
    int idx = cell_index(x, y);
    int left = BOARD_X + x * CELL_SIZE;
    int top = BOARD_Y + y * CELL_SIZE;
    int right = left + CELL_SIZE - 3;
    int bottom = top + CELL_SIZE - 3;
    int selected = x == g_cursor_x && y == g_cursor_y;
    u8 cell = g_cells[idx];
    u32 bg;

    if (cell & CELL_OPEN) {
        if (cell & CELL_MINE) {
            bg = rgb(190, 45, 55);
        } else {
            bg = rgb(225, 232, 238);
        }
    } else if (cell & CELL_FLAG) {
        bg = selected ? rgb(255, 205, 45) : rgb(235, 150, 35);
    } else {
        bg = selected ? rgb(55, 195, 210) : rgb(65, 95, 120);
    }

    fill_box(left, top, right, bottom, bg);
}

static void draw_cell_text(int x, int y) {
    int idx = cell_index(x, y);
    int left = BOARD_X + x * CELL_SIZE;
    int top = BOARD_Y + y * CELL_SIZE;
    int right = left + CELL_SIZE - 3;
    int selected = x == g_cursor_x && y == g_cursor_y;
    u8 cell = g_cells[idx];
    u32 fg = rgb(245, 250, 255);
    char text[2];

    text[0] = 0;
    text[1] = 0;
    if (cell & CELL_OPEN) {
        if (cell & CELL_MINE) {
            text[0] = '*';
        } else {
            int near = neighbor_mines(x, y);
            fg = near == 1 ? rgb(20, 85, 200) :
                 near == 2 ? rgb(20, 135, 70) :
                 near >= 3 ? rgb(190, 45, 55) : rgb(85, 95, 105);
            if (near) {
                text[0] = (char)('0' + near);
            }
        }
    } else if (cell & CELL_FLAG) {
        fg = rgb(80, 35, 10);
        text[0] = 'F';
    }
    if (text[0]) {
        draw_label(left + 8, top + 4, text, fg);
    }
    if (selected) {
        draw_label(left + 2, top + 3, "[", rgb(255, 255, 255));
        draw_label(right - 5, top + 3, "]", rgb(255, 255, 255));
    }
}

static void draw_game(void) {
    int x;
    int y;
    u32 dirty_low;
    u32 dirty_high;
    char status[24];
    u32 background;
    u32 white;
    u32 muted;

    if (!g_draw || !g_dirty) {
        return;
    }
    dirty_low = g_dirty_cells_low;
    dirty_high = g_dirty_cells_high;
    g_dirty_cells_low = 0;
    g_dirty_cells_high = 0;
    g_dirty = 0;
    if (g_first_draw) {
        bda_gui_draw_guard_begin_like();
    }
    bda_gui_set_text_mode_like(g_draw, 1);

    background = rgb(18, 29, 42);
    white = rgb(245, 248, 250);
    muted = rgb(145, 170, 190);
    (void)background;

    for (y = 0; y < BOARD_H; ++y) {
        for (x = 0; x < BOARD_W; ++x) {
            int index = cell_index(x, y);
            int dirty = index < 32 ? (int)((dirty_low >> index) & 1u) :
                                      (int)((dirty_high >> (index - 32)) & 1u);
            if (dirty) {
                compose_cell(x, y);
                draw_cell_text(x, y);
            }
        }
    }

    draw_label(58, 8, "MINESWEEPER", white);
    make_status(status);
    draw_label(58, 30, status, muted);
    if (g_state == GAME_PLAYING) {
        draw_label(32, 250, "ARROWS MOVE  OK OPEN", white);
        draw_label(72, 278, "BACK FLAG", muted);
    } else {
        draw_label(45, 250, "OK STARTS NEW GAME", white);
        draw_label(65, 278, g_state == GAME_WON ? "BOARD CLEARED" : "MINE DETONATED", muted);
    }

    if (g_frame) {
        bda_gui_invalidate_window_like(g_frame);
    }
    if (g_first_draw) {
        bda_gui_draw_guard_end_like();
        g_first_draw = 0;
    }
    g_dirty = 0;
}

static void handle_key(int key) {
    int old_index;

    if (key == KEY_OK) {
        if (g_state == GAME_PLAYING) {
            open_from(g_cursor_x, g_cursor_y);
        } else {
            reset_game();
        }
        return;
    }
    if (key == KEY_FLAG) {
        toggle_flag();
        return;
    }
    if (g_state != GAME_PLAYING) {
        return;
    }
    old_index = cell_index(g_cursor_x, g_cursor_y);
    if (key == KEY_UP && g_cursor_y > 0) {
        --g_cursor_y;
    } else if (key == KEY_DOWN && g_cursor_y + 1 < BOARD_H) {
        ++g_cursor_y;
    } else if (key == KEY_LEFT && g_cursor_x > 0) {
        --g_cursor_x;
    } else if (key == KEY_RIGHT && g_cursor_x + 1 < BOARD_W) {
        ++g_cursor_x;
    } else {
        return;
    }
    mark_cell_dirty(old_index);
    mark_cell_dirty(cell_index(g_cursor_x, g_cursor_y));
}

static int normalize_game_key(int key) {
    switch (key) {
        case KE_UP_LIKE:
            return KEY_UP;
        case KE_DOWN_LIKE:
            return KEY_DOWN;
        case KE_LEFT_LIKE:
            return KEY_LEFT;
        case KE_RIGHT_LIKE:
            return KEY_RIGHT;
        case KE_ESC_LIKE:
            return KEY_FLAG;
        case KE_ENTER_LIKE:
            return KEY_OK;
        default:
            return key >= KEY_UP && key <= KEY_OK ? key : 0;
    }
}

static int read_game_key(void) {
    bda_gui_input_packet_like_t packet;
    bda_gui_event_fetch_like_t event;

    (void)bda_gui_state_query_like();
    event.code = -1;
    event.value = -1;
    (void)bda_gui_event_fetch_like(&event);
    if (normalize_game_key(event.value)) {
        return normalize_game_key(event.value);
    }
    bda_memset(&packet, 0, sizeof(packet));
    (void)bda_gui_input_packet_like(&packet);
    if (packet.bytes[3]) {
        return KEY_UP;
    }
    if (packet.bytes[2]) {
        return KEY_DOWN;
    }
    if (packet.bytes[1]) {
        return KEY_LEFT;
    }
    if (packet.bytes[0]) {
        return KEY_RIGHT;
    }
    if (packet.bytes[4]) {
        return KEY_FLAG;
    }
    if (packet.bytes[5]) {
        return KEY_OK;
    }
    return 0;
}

static int poll_game_key(void) {
    int key = normalize_game_key(read_game_key());
    if (!key) {
        key = normalize_game_key(bda_sys_keycode_raw_like());
    }

    if (!key) {
        g_key_latch = 0;
    } else if (!g_key_latch) {
        g_key_latch = key;
        handle_key(key);
        draw_game();
        return 1;
    }
    return 0;
}

typedef struct thunder_app_event {
    u32 message;
    u32 wparam;
    u32 lparam;
} thunder_app_event_t;

/*
 * Thunder's static bridge runs the GUI poll/step/dispatch sequence, then copies
 * the translated application event from 0x81c17598..0x81c175a0.
 */
static int thunder_event_fetch(thunder_app_event_t *event) {
    typedef int (*event_fetch_fn)(thunder_app_event_t *);
    return ((event_fetch_fn)0x81c0fdb8u)(event);
}

/* Thunder's preserved outer event loop calls this helper for raw 0x844 input events. */
int mines_key_event_hook(void *input_state) {
    (void)input_state;
    (void)poll_game_key();
    return 1;
}

static int mines_window_proc(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE) {
        g_frame = handle;
        g_draw = bda_gui_current_draw_like(handle);
        g_draw_object = bda_gui_draw_object_create_like(7);
        if (g_draw && g_draw_object) {
            bda_gui_select_draw_object_like(g_draw, g_draw_object);
        }
        g_first_draw = 1;
        g_dirty = 1;
        draw_game();
    } else if (message == BDA_MSG_INPUT_BEGIN_LIKE ||
               message == BDA_MSG_INPUT_DERIVED_LIKE ||
               message == BDA_MSG_KEYDOWN_LIKE) {
        int key = normalize_game_key(bda_sys_keycode_raw_like());
        int low = normalize_game_key((int)BDA_LOWORD(wparam));
        int high = normalize_game_key((int)BDA_HIWORD(wparam));
        if (key) {
            handle_key(key);
            draw_game();
            return 1;
        }
        if (low) {
            handle_key(low);
            draw_game();
            return 1;
        }
        if (high) {
            handle_key(high);
            draw_game();
            return 1;
        }
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH_LIKE) {
        int result;
        if (g_draw) {
            bda_gui_end_draw_like(g_draw);
            g_draw = 0;
        }
        result = bda_gui_default_proc_like(handle, message, wparam, lparam);
        g_frame = 0;
        return result;
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

int mines_run_loop(void) {
    thunder_app_event_t event;

    while (g_frame) {
        int key;
        (void)poll_game_key();
        bda_memset(&event, 0, sizeof(event));
        if (!thunder_event_fetch(&event)) {
            continue;
        }
        key = normalize_game_key((int)BDA_LOWORD(event.wparam));
        if (event.message == BDA_MSG_INPUT_BEGIN_LIKE && key) {
            handle_key(key);
            draw_game();
        }
    }
    return 0;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t desc;

    bda_memset(&desc, 0, sizeof(desc));
    g_frame = 0;
    g_draw = 0;
    g_draw_object = 0;
    g_first_draw = 1;
    reset_game();
    desc.style = 0x08000000u;
    desc.title = 0;
    desc.wndproc = mines_window_proc;
    desc.height = 240;
    desc.width = 320;
    desc.surface = (u32)bda_gui_draw_object_create_like(15);

    g_frame = bda_gui_register_frame_desc_like(&desc);
    if ((s32)g_frame == -1 || !g_frame) {
        bda_msgbox("Mines", "frame registration failed");
        return 1;
    }
    bda_gui_frame_activate_like(g_frame, 0x100);
    g_draw = bda_gui_current_draw_like(g_frame);
    g_draw_object = bda_gui_draw_object_create_like(7);
    if (g_draw && g_draw_object) {
        bda_gui_select_draw_object_like(g_draw, g_draw_object);
    }
    g_first_draw = 1;
    mark_all_cells_dirty();
    draw_game();
    return mines_run_loop();
}
