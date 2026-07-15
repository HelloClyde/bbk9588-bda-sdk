#include "bda_sdk.h"

#define SCREEN_W 320
#define SCREEN_H 240
#define DLX_RESOURCE_INDEX 4
#define MAX_IMAGE_BYTES (320u * 240u * 2u)

static const char k_dlx_path[] =
    "\x41\x3a\x5c\xd3\xa6\xd3\xc3\x5c\xca\xfd\xbe\xdd\x5c"
    "\x73\x68\x65\x6c\x6c\x5c\x74\x65\x78\x74\x5f\x41\x2e\x64\x6c\x78";


typedef struct image_state {
    u16 *pixels;
    u32 width;
    u32 height;
    int loaded;
} image_state_t;

static bda_handle_t g_frame;
static int g_exit;
static image_state_t g_image;
static u16 *g_framebuffer;

static u32 rd32(const u8 *p) {
    return ((u32)p[0]) | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

static void fill_error_pattern(u16 *fb, u32 code) {
    u32 x;
    u32 y;
    for (y = 0; y < SCREEN_H; ++y) {
        for (x = 0; x < SCREEN_W; ++x) {
            u16 c = ((x ^ y ^ code) & 16u) ? 0xf800u : 0x001fu;
            fb[y * SCREEN_W + x] = c;
        }
    }
}

static void fill_framebuffer(u16 *fb, u16 color) {
    u32 i;
    for (i = 0; i < SCREEN_W * SCREEN_H; ++i) {
        fb[i] = color;
    }
}

static void compose_centered_image(u16 *fb, const image_state_t *img) {
    s32 x0;
    s32 y0;
    u32 x;
    u32 y;

    fill_framebuffer(fb, 0xffffu);
    if (!img->loaded || !img->pixels) {
        return;
    }

    x0 = (SCREEN_W - (s32)img->width) / 2;
    y0 = (SCREEN_H - (s32)img->height) / 2;
    if (x0 < 0 || y0 < 0) {
        return;
    }

    for (y = 0; y < img->height; ++y) {
        for (x = 0; x < img->width; ++x) {
            fb[(y0 + (s32)y) * SCREEN_W + (x0 + (s32)x)] =
                img->pixels[y * img->width + x];
        }
    }
}

static int load_dlx_vx_resource(image_state_t *img) {
    int f;
    u8 head[0x24];
    u8 ent[12];
    u8 vx[24];
    u32 count;
    u32 header_size;
    u32 rel;
    u32 size;
    u32 off;
    u32 w;
    u32 h;
    u32 bytes;
    u16 *pixels;

    bda_memset(img, 0, sizeof(*img));
    f = bda_fs_fopen_raw(k_dlx_path, "rb");
    if (!f) {
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
    if (count <= DLX_RESOURCE_INDEX || header_size < 0x24) {
        bda_fs_close_raw(f);
        return -4;
    }

    bda_fs_seek_raw(f, 0x24 + DLX_RESOURCE_INDEX * 12, BDA_SEEK_SET);
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
    if (size < sizeof(vx)) {
        bda_fs_close_raw(f);
        return -7;
    }

    bda_fs_seek_raw(f, (s32)off, BDA_SEEK_SET);
    if (bda_fs_fread_raw(vx, 1, sizeof(vx), f) != (int)sizeof(vx)) {
        bda_fs_close_raw(f);
        return -8;
    }
    if (vx[0] != 'V' || vx[1] != 'X') {
        bda_fs_close_raw(f);
        return -9;
    }

    w = rd32(vx + 6);
    h = rd32(vx + 10);
    bytes = w * h * 2u;
    if (!w || !h || w > SCREEN_W || h > SCREEN_H || bytes > MAX_IMAGE_BYTES || size < 24u + bytes) {
        bda_fs_close_raw(f);
        return -10;
    }

    pixels = (u16 *)bda_alloc(bytes);
    if (!pixels) {
        bda_fs_close_raw(f);
        return -11;
    }

    if (bda_fs_fread_raw(pixels, 1, bytes, f) != (int)bytes) {
        bda_free(pixels);
        bda_fs_close_raw(f);
        return -12;
    }
    bda_fs_close_raw(f);

    img->pixels = pixels;
    img->width = w;
    img->height = h;
    img->loaded = 1;
    return 0;
}

static void show_framebuffer(void) {
    if (g_framebuffer) {
        bda_gui_pump_present_arg_like(1);
        bda_gui_blit_like(0, 0, SCREEN_H, SCREEN_W, g_framebuffer);
        if (bda_gui_game_display_pump_like()) {
            bda_gui_blit_alt_like(0, 0, SCREEN_H, SCREEN_W, g_framebuffer);
        }
        bda_gui_pump_present_arg_like(0);
    }
}

static int probe_window_proc(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    (void)wparam;
    (void)lparam;
    if (message == BDA_MSG_KEYDOWN_LIKE ||
        message == BDA_MSG_TOUCH_A_LIKE ||
        message == BDA_MSG_REDRAW_INPUT_LIKE ||
        message == 0x66) {
        g_exit = 1;
        return 1;
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_frame_desc_like_t desc;
    bda_gui_message_like_t msg;
    int err;
    u16 *fallback;

    bda_memset(&desc, 0, sizeof(desc));
    bda_memset(&msg, 0, sizeof(msg));
    g_exit = 0;

    desc.style = 0x08000000u;
    desc.title = "DLXImg";
    desc.wndproc = probe_window_proc;
    desc.height = SCREEN_H;
    desc.width = SCREEN_W;
    desc.surface = (u32)bda_gui_draw_object_create_like(15);

    g_frame = (bda_handle_t)bda_gui_register_frame_like(&desc);
    if ((s32)g_frame != -1 && g_frame) {
        bda_gui_frame_activate_like(g_frame, 0x100);
    }

    err = load_dlx_vx_resource(&g_image);
    g_framebuffer = (u16 *)bda_alloc(SCREEN_W * SCREEN_H * 2u);
    if (!g_framebuffer) {
        bda_msgbox("DLXImage", "fb alloc failed");
        return 2;
    }

    if (err) {
        fill_error_pattern(g_framebuffer, (u32)(-err));
        show_framebuffer();
        bda_msgbox("DLXImage", "load failed");
        bda_free(g_framebuffer);
        g_framebuffer = 0;
        return 1;
    }

    compose_centered_image(g_framebuffer, &g_image);
    show_framebuffer();
#ifdef BDA_IMAGE_MSGBOX_WAIT
    bda_msgbox("DLXImage", "press key");
    g_exit = 1;
#endif
    while (!g_exit) {
        if (g_frame && bda_gui_event_poll_like(&msg, g_frame)) {
            bda_gui_event_step_like(&msg);
            bda_gui_event_dispatch_like(&msg);
        } else {
            bda_sys_delay_like(10000);
        }
        show_framebuffer();
    }

    if (g_framebuffer) {
        bda_free(g_framebuffer);
        g_framebuffer = 0;
    }
    if (g_image.pixels) {
        bda_free(g_image.pixels);
    }
    return 0;
}
