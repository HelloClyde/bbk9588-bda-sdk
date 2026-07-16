#include "../bda_research_sdk.h"

#define SCREEN_W 320
#define SCREEN_H 240
#define DLX_RESOURCE_INDEX 4
#define MAX_VX_BYTES (320u * 240u * 2u + 24u)

#ifndef SHOWCASE_IDLE_LIMIT
#define SHOWCASE_IDLE_LIMIT 120
#endif

static const char p0[] = "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p1[] = "a:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p2[] = "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p3[] = "\\shell\\text_A.dlx";
static const char p4[] = "\\Shell\\text_A.dlx";
static const char p5[] = "A:\\\xcf\xb5\xcd\xb3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p6[] = "a:\\\xcf\xb5\xcd\xb3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char p7[] = "\\\xcf\xb5\xcd\xb3\\\xca\xfd\xbe\xdd\\shell\\text_A.dlx";
static const char ok0[] = "open ok path 0";
static const char ok1[] = "open ok path 1";
static const char ok2[] = "open ok path 2";
static const char ok3[] = "open ok path 3";
static const char ok4[] = "open ok path 4";
static const char ok5[] = "open ok path 5";
static const char ok6[] = "open ok path 6";
static const char ok7[] = "open ok path 7";

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static int g_exit;
static u8 *g_vx;
static u32 g_vx_width;
static u32 g_vx_height;

static u32 rd32(const u8 *p) {
    return ((u32)p[0]) | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

static const char *path_at(int index) {
    switch (index) {
    case 0:
        return p0;
    case 1:
        return p1;
    case 2:
        return p2;
    case 3:
        return p3;
    case 4:
        return p4;
    case 5:
        return p5;
    case 6:
        return p6;
    default:
        return p7;
    }
}

static const char *ok_text_at(int index) {
    switch (index) {
    case 0:
        return ok0;
    case 1:
        return ok1;
    case 2:
        return ok2;
    case 3:
        return ok3;
    case 4:
        return ok4;
    case 5:
        return ok5;
    case 6:
        return ok6;
    default:
        return ok7;
    }
}

static int proc_passthrough(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    if (message == 0x60 || message == 0x10) {
        g_draw = bda_gui_current_draw_like(handle);
    }
    if (message == 1 || message == 0x10 || message == 0x60 || message == 0xb1 || message == 0x844 || message == 0x7fd) {
        if (g_vx) {
            if (!g_draw) {
                g_draw = bda_gui_current_draw_like(handle);
            }
        }
        if (g_vx && g_draw) {
            bda_gui_pump_present_arg_like(1);
            bda_gui_draw_vx_like(g_draw, 0, 40, g_vx);
            bda_gui_pump_present_arg_like(0);
        }
    }
    if (message == 0x66 || message == 0x7fd || message == BDA_MSG_KEYDOWN_LIKE) {
        g_exit = 1;
        return 1;
    }
    return bda_gui_default_proc_like(handle, message, wparam, lparam);
}

static int load_text_a_vx(void) {
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

    bda_msgbox("STAGE", "open text_A");
    f = -1;
    for (int i = 0; i < 8; ++i) {
        f = bda_fs_fopen_raw(path_at(i), "rb");
        if (f != 0 && (unsigned int)f != 0xffffffffu) {
            bda_msgbox("STAGE", ok_text_at(i));
            break;
        }
    }
    if (f == 0 || (unsigned int)f == 0xffffffffu) {
        bda_msgbox("STAGE", "open failed");
        return -1;
    }
    if (bda_fs_fread_raw(head, 1, sizeof(head), f) != (int)sizeof(head)) {
        bda_fs_close_raw(f);
        bda_msgbox("STAGE", "read dlx head failed");
        return -2;
    }
    count = head[3];
    header_size = rd32(head + 0x0c);
    if (head[0] != 'D' || head[1] != 'L' || head[2] != 'X' ||
        count <= DLX_RESOURCE_INDEX || header_size < 0x24) {
        bda_fs_close_raw(f);
        bda_msgbox("STAGE", "bad dlx head");
        return -3;
    }
    bda_fs_seek_raw(f, 0x24 + DLX_RESOURCE_INDEX * 12, BDA_SEEK_SET);
    if (bda_fs_fread_raw(ent, 1, sizeof(ent), f) != (int)sizeof(ent)) {
        bda_fs_close_raw(f);
        bda_msgbox("STAGE", "read entry failed");
        return -4;
    }
    rel = rd32(ent + 4);
    size = rd32(ent + 8);
    off = header_size + rel;
    if (rd32(ent) != 1 || size < sizeof(vx_head) || size > MAX_VX_BYTES) {
        bda_fs_close_raw(f);
        bda_msgbox("STAGE", "bad entry");
        return -5;
    }
    bda_fs_seek_raw(f, (s32)off, BDA_SEEK_SET);
    if (bda_fs_fread_raw(vx_head, 1, sizeof(vx_head), f) != (int)sizeof(vx_head)) {
        bda_fs_close_raw(f);
        bda_msgbox("STAGE", "read vx head failed");
        return -6;
    }
    g_vx_width = rd32(vx_head + 6);
    g_vx_height = rd32(vx_head + 10);
    if (vx_head[0] != 'V' || vx_head[1] != 'X' ||
        !g_vx_width || !g_vx_height || g_vx_width > SCREEN_W || g_vx_height > SCREEN_H) {
        bda_fs_close_raw(f);
        bda_msgbox("STAGE", "bad vx head");
        return -7;
    }
    vx = (u8 *)bda_alloc(size);
    if (!vx) {
        bda_fs_close_raw(f);
        bda_msgbox("STAGE", "alloc failed");
        return -8;
    }
    bda_memcpy(vx, vx_head, sizeof(vx_head));
    if (bda_fs_fread_raw(vx + sizeof(vx_head), 1, size - sizeof(vx_head), f) != (int)(size - sizeof(vx_head))) {
        bda_free(vx);
        bda_fs_close_raw(f);
        bda_msgbox("STAGE", "read vx body failed");
        return -9;
    }
    bda_fs_close_raw(f);
    g_vx = vx;
    bda_msgbox("STAGE", "load ok");
    return 0;
}

static int create_stage_frame(void) {
    bda_frame_desc_like_t desc;
    bda_memset(&desc, 0, sizeof(desc));
    desc.style = 0x08000000u;
    desc.title = "Stage";
    desc.wndproc = proc_passthrough;
    desc.height = SCREEN_H;
    desc.width = SCREEN_W;
    desc.surface = (u32)bda_gui_draw_object_create_like(15);
    bda_msgbox("STAGE", "register frame");
    g_frame = (bda_handle_t)bda_gui_register_frame_like(&desc);
    if ((s32)g_frame == -1 || !g_frame) {
        bda_msgbox("STAGE", "frame failed");
        return -1;
    }
    bda_msgbox("STAGE", "frame ok");
    return 0;
}

static void draw_once(void) {
    g_draw = bda_gui_current_draw_like(g_frame);
    if (!g_draw) {
        bda_msgbox("STAGE", "draw handle null");
        return;
    }
    bda_msgbox("STAGE", "draw begin");
    bda_gui_pump_present_arg_like(1);
    bda_gui_draw_vx_like(g_draw, 0, 40, g_vx);
    bda_gui_pump_present_arg_like(0);
    bda_msgbox("STAGE", "draw returned");
}

static void run_event_loop_limited(void) {
    bda_gui_message_like_t msg;
    int idle = 0;

    bda_memset(&msg, 0, sizeof(msg));
    g_exit = 0;
    bda_gui_frame_activate_like(g_frame, 0x100);
    bda_gui_send(g_frame, 0x60, 0, 0);

    while (!g_exit && idle < SHOWCASE_IDLE_LIMIT) {
        if (bda_gui_event_poll_like(&msg, 0)) {
            idle = 0;
            bda_gui_event_step_like(&msg);
            bda_gui_event_dispatch_like(&msg);
        } else {
            ++idle;
            if (g_vx && g_draw) {
                bda_gui_pump_present_arg_like(1);
                bda_gui_draw_vx_like(g_draw, 0, 40, g_vx);
                bda_gui_pump_present_arg_like(0);
            }
            bda_sys_delay_like(10000);
        }
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    int r;
    g_frame = 0;
    g_draw = 0;
    g_exit = 0;
    g_vx = 0;
    g_vx_width = 0;
    g_vx_height = 0;

    r = load_text_a_vx();
    if (r) {
        return r;
    }

#if SHOWCASE_STAGE >= 2
    r = create_stage_frame();
    if (r) {
        return r;
    }
#endif

#if SHOWCASE_STAGE >= 3
#ifdef SHOWCASE_EVENT_LOOP
    run_event_loop_limited();
#else
    draw_once();
#endif
#endif

#ifdef SHOWCASE_CLOSE_AFTER_FRAME
    if (g_frame) {
        bda_msgbox("STAGE", "close frame");
        bda_gui_close_frame_like(g_frame);
        g_frame = 0;
        bda_msgbox("STAGE", "closed");
    }
#elif defined(SHOWCASE_STOP_RELEASE_AFTER_FRAME)
    if (g_frame) {
        bda_msgbox("STAGE", "stop/release");
        bda_gui_frame_stop_like(g_frame);
        bda_gui_frame_release_like(g_frame);
        g_frame = 0;
        bda_msgbox("STAGE", "released");
    }
#elif defined(SHOWCASE_EVENT_LOOP)
#ifndef SHOWCASE_NO_CLEANUP
    if (g_frame) {
        bda_gui_close_frame_like(g_frame);
        g_frame = 0;
    }
#endif
#endif

#ifndef SHOWCASE_NO_CLEANUP
    if (g_vx) {
        bda_free(g_vx);
        g_vx = 0;
    }
#endif
    return 0;
}
