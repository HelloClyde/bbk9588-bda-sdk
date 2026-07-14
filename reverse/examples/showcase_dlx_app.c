#include "bda_sdk.h"

#define SCREEN_W 320
#define SCREEN_H 240
#define MAX_VX_BYTES (320u * 240u * 2u + 24u)

static const char k_custom_dlx_path[] =
    "\x41\x3a\x5c\xd3\xa6\xd3\xc3\x5c\xca\xfd\xbe\xdd\x5c"
    "\x73\x68\x65\x6c\x6c\x5c\x53\x68\x6f\x77\x63\x61\x73\x65\x44\x65\x6d\x6f\x2e\x64\x6c\x78";

static const char k_fallback_dlx_path[] =
    "\x41\x3a\x5c\xd3\xa6\xd3\xc3\x5c\xca\xfd\xbe\xdd\x5c"
    "\x73\x68\x65\x6c\x6c\x5c\x74\x65\x78\x74\x5f\x41\x2e\x64\x6c\x78";


static bda_handle_t g_frame;
static bda_handle_t g_draw;
static u8 *g_vx;
static u32 g_vx_width;
static u32 g_vx_height;
static int g_exit;

static u32 rd32(const u8 *p) {
    return ((u32)p[0]) | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

static int read_full_vx_resource(const char *path, u32 index) {
    int f;
    u8 head[0x24];
    u8 ent[12];
    u8 vx_head[24];
    u32 count;
    u32 header_size;
    u32 rel;
    u32 size;
    u32 off;
    u8 *vx;

    f = bda_fs_fopen_raw(path, "rb");
    if (!bda_fs_file_is_valid(f)) {
        return -1;
    }
    if (bda_fs_fread_raw(head, 1, sizeof(head), f) != (int)sizeof(head)) {
        bda_fs_close_raw(f);
        return -2;
    }
    if (head[0] != 'D' || head[1] != 'L' || head[2] != 'X') {
        bda_fs_close_raw(f);
        return -3;
    }
    count = head[3];
    header_size = rd32(head + 0x0c);
    if (index >= count || header_size < 0x24) {
        bda_fs_close_raw(f);
        return -4;
    }
    bda_fs_seek_raw(f, 0x24 + index * 12, BDA_SEEK_SET);
    if (bda_fs_fread_raw(ent, 1, sizeof(ent), f) != (int)sizeof(ent)) {
        bda_fs_close_raw(f);
        return -5;
    }
    if (rd32(ent + 0) != 1) {
        bda_fs_close_raw(f);
        return -6;
    }
    rel = rd32(ent + 4);
    size = rd32(ent + 8);
    off = header_size + rel;
    if (size < sizeof(vx_head) || size > MAX_VX_BYTES) {
        bda_fs_close_raw(f);
        return -7;
    }
    bda_fs_seek_raw(f, (s32)off, BDA_SEEK_SET);
    if (bda_fs_fread_raw(vx_head, 1, sizeof(vx_head), f) != (int)sizeof(vx_head)) {
        bda_fs_close_raw(f);
        return -8;
    }
    if (vx_head[0] != 'V' || vx_head[1] != 'X') {
        bda_fs_close_raw(f);
        return -9;
    }
    g_vx_width = rd32(vx_head + 6);
    g_vx_height = rd32(vx_head + 10);
    if (!g_vx_width || !g_vx_height || g_vx_width > SCREEN_W || g_vx_height > SCREEN_H) {
        bda_fs_close_raw(f);
        return -10;
    }
    vx = (u8 *)bda_alloc(size);
    if (!vx) {
        bda_fs_close_raw(f);
        return -11;
    }
    bda_memcpy(vx, vx_head, sizeof(vx_head));
    if (bda_fs_fread_raw(vx + sizeof(vx_head), 1, size - sizeof(vx_head), f) != (int)(size - sizeof(vx_head))) {
        bda_free(vx);
        bda_fs_close_raw(f);
        return -12;
    }
    bda_fs_close_raw(f);
    g_vx = vx;
    return 0;
}

static int load_showcase_image(void) {
    int err;
    g_vx = 0;
    g_vx_width = 0;
    g_vx_height = 0;

#ifndef SHOWCASE_FORCE_FALLBACK
    err = read_full_vx_resource(k_custom_dlx_path, 0);
    if (!err) {
        return 0;
    }
#endif
    return read_full_vx_resource(k_fallback_dlx_path, 4);
}

static void draw_showcase(void) {
    s32 x;
    s32 y;
    if (!g_vx) {
        return;
    }
    if (!g_draw) {
        g_draw = bda_gui_current_draw_like(handle);
    }
    if (!g_draw) {
        return;
    }
    x = (240 - (s32)g_vx_width) / 2;
    y = (320 - (s32)g_vx_height) / 2;
    if (x < 0) {
        x = 0;
    }
    if (y < 0) {
        y = 0;
    }
    bda_gui_pump_present_arg_like(1);
    bda_gui_draw_vx_like(g_draw, x, y, g_vx);
    bda_gui_pump_present_arg_like(0);
}

static int showcase_window_proc(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    if (message == 1 || message == 0x10 || message == 0xb1 || message == 0x844 || message == 0x7fd) {
        draw_showcase();
    }
#ifndef SHOWCASE_DISPLAY_ONLY
    if (message == BDA_MSG_KEYDOWN_LIKE || message == 0x66) {
        g_exit = 1;
        return 1;
    }
#endif
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t desc;
    bda_gui_message_like_t msg;
    int err;
    int idle_draws;

    bda_memset(&desc, 0, sizeof(desc));
    bda_memset(&msg, 0, sizeof(msg));
    g_frame = 0;
    g_draw = 0;
    g_exit = 0;
    idle_draws = 0;

    err = load_showcase_image();
    if (err) {
        bda_msgbox("Showcase", "DLX image load failed");
        return err;
    }

    desc.style = 0x08000000u;
    desc.title = "Showcase";
    desc.wndproc = showcase_window_proc;
    desc.height = SCREEN_H;
    desc.width = SCREEN_W;
    desc.surface = (u32)bda_gui_frame_surface_like(15);

    g_frame = (bda_handle_t)bda_gui_register_frame_like(&desc);
    if ((s32)g_frame == -1 || !g_frame) {
        bda_free(g_vx);
        bda_msgbox("Showcase", "frame failed");
        return 2;
    }

    while (!g_exit) {
        if (bda_gui_event_poll_like(&msg, 0)) {
            bda_gui_event_step_like(&msg);
            bda_gui_event_dispatch_like(&msg);
            idle_draws = 0;
        } else {
            draw_showcase();
            ++idle_draws;
            bda_sys_delay_like(10000);
        }
    }

    if (g_vx) {
        bda_free(g_vx);
    }
    return 0;
}
