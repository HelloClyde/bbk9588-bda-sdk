#include "../bda_research_sdk.h"

/*
 * Tile blit hardware probe.
 *
 * 这个示例只保留为 ABI/build probe。真机反馈显示：
 * draw guard begin -> 批量 low-level blit -> 一次 draw guard end/present
 * 仍会逐块 flip，并在全部 tile 渲染后死机。
 *
 * 结论：GUI+0x074/+0x400 依赖原机游戏已建立的 surface/context 生命周期；
 * 不要把这个 probe 当作可玩的 tile 游戏、扫雷或通用 framebuffer 示例。
 */

#define TILE_W 16
#define TILE_H 16
#define GRID_W 8
#define GRID_H 6

static u16 g_tiles[GRID_W * GRID_H][TILE_W * TILE_H];

static void fill_tile(u16 *tile, u16 base, u16 alt, int index) {
    int y;
    int x;

    for (y = 0; y < TILE_H; ++y) {
        for (x = 0; x < TILE_W; ++x) {
            int border = (x == 0) || (y == 0) || (x == TILE_W - 1) || (y == TILE_H - 1);
            int stripe = ((x + y + index) & 4) != 0;
            int marker = ((x == (index & 15)) || (y == ((index >> 1) & 15))) && x > 2 && y > 2;
            tile[y * TILE_W + x] = border ? 0xffffu : (stripe ? alt : base);
            if (marker) {
                tile[y * TILE_W + x] ^= 0xffffu;
            }
        }
    }
}

static void prepare_tiles(void) {
    static const u16 colors[][2] = {
        {0xf800u, 0x7800u},
        {0x07e0u, 0x03e0u},
        {0x001fu, 0x000fu},
        {0xffe0u, 0x7be0u},
        {0xf81fu, 0x780fu},
        {0x07ffu, 0x03efu},
    };
    int i;

    for (i = 0; i < GRID_W * GRID_H; ++i) {
        fill_tile(g_tiles[i], colors[i % 6][0], colors[i % 6][1], i);
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int row;
    int col;

    prepare_tiles();

    bda_gui_draw_guard_begin_like();
    for (row = 0; row < GRID_H; ++row) {
        for (col = 0; col < GRID_W; ++col) {
            int index = row * GRID_W + col;
            (void)bda_gui_blit_alt_like(16 + col * 18, 28 + row * 18, TILE_H, TILE_W, g_tiles[index]);
        }
    }
    bda_gui_draw_guard_end_like();

    return 0;
}
