#include "bda_sdk.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define FRAME_BYTES (SCREEN_WIDTH * SCREEN_HEIGHT * 2u)
#define RAW_EVENTS_PER_POLL 8u

static bda_handle_t g_frame;
static bda_gui_framebuffer_t g_framebuffer;
static u16 *g_pixels;
static volatile int g_detached;

static u16 rgb565(u32 red, u32 green, u32 blue)
{
    return (u16)(
        ((red & 0xf8u) << 8) |
        ((green & 0xfcu) << 3) |
        (blue >> 3)
    );
}

static void render_pattern(u32 phase)
{
    u16 colors[4];
    int x;
    int y;

    colors[0] = rgb565(225, 55, 70);
    colors[1] = rgb565(45, 190, 105);
    colors[2] = rgb565(45, 115, 225);
    colors[3] = rgb565(240, 190, 35);
    for (y = 0; y < SCREEN_HEIGHT; ++y) {
        for (x = 0; x < SCREEN_WIDTH; ++x) {
            u32 band = ((u32)x + phase * 8u) / 60u;
            u16 color = colors[band & 3u];

            if (y < 16 || y >= SCREEN_HEIGHT - 16 ||
                x < 8 || x >= SCREEN_WIDTH - 8)
                color = rgb565(238, 242, 245);
            if (((x / 12) + (y / 12) + (int)phase) % 2 == 0 &&
                y >= 112 && y < 208)
                color = rgb565(14, 20, 26);
            g_pixels[y * SCREEN_WIDTH + x] = color;
        }
    }

    g_pixels[8 * SCREEN_WIDTH + 8] = rgb565(255, 0, 0);
    g_pixels[8 * SCREEN_WIDTH + SCREEN_WIDTH - 9] = rgb565(0, 255, 0);
    g_pixels[(SCREEN_HEIGHT - 9) * SCREEN_WIDTH + 8] =
        rgb565(0, 0, 255);
    g_pixels[(SCREEN_HEIGHT - 9) * SCREEN_WIDTH + SCREEN_WIDTH - 9] =
        rgb565(255, 255, 0);
}

static int framebuffer_window_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
)
{
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH)
        g_frame = handle;
    else if (message == BDA_MSG_DRAW_CONTEXT_DETACH)
        g_detached = 1;
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void)
{
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    u32 last_present;
    u32 phase = 0;
    u32 close_wait = 0;
    int close_requested = 0;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    bda_memset(&g_framebuffer, 0, sizeof(g_framebuffer));
    g_pixels = (u16 *)bda_alloc(FRAME_BYTES);
    if (!g_pixels || (s32)(u32)g_pixels == -1)
        return 1;

    descriptor.title = "DirectFB";
    descriptor.wndproc = framebuffer_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    g_frame = bda_gui_register_frame_desc(&descriptor);
    if (!g_frame || (s32)g_frame == -1) {
        bda_free(g_pixels);
        return 2;
    }
    (void)bda_gui_frame_activate(g_frame, 0x100u);
    if (bda_gui_framebuffer_acquire(&g_framebuffer) != 0) {
        (void)bda_msgbox("DirectFB", "Framebuffer layout rejected.");
        close_requested = 1;
    }

    render_pattern(phase);
    if (!close_requested)
        (void)bda_gui_framebuffer_present_rgb565(&g_framebuffer, g_pixels);
    last_present = bda_gui_tick_count_25ms();

    while (!g_detached) {
        int pump_result = 1;

        if (!close_requested) {
            bda_gui_raw_event_t event;
            u32 event_count = 0;
            u32 now = bda_gui_tick_count_25ms();

            while (event_count < RAW_EVENTS_PER_POLL &&
                   bda_gui_raw_event_fetch(&event) >= 0) {
                ++event_count;
                if ((u32)event.code == BDA_INPUT_EVENT_KEY_DOWN &&
                    event.value == 9)
                    close_requested = 1;
            }
            if (bda_gui_tick_elapsed_25ms(last_present, now) >= 4u) {
                ++phase;
                render_pattern(phase);
                (void)bda_gui_framebuffer_present_rgb565(
                    &g_framebuffer, g_pixels
                );
                last_present = now;
            }
        }

        if (close_requested && close_wait == 0u) {
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
        }
        if (close_requested)
            pump_result = bda_gui_event_pump_frame_once(&message, g_frame);
        bda_sys_delay(1u);
        if (close_requested &&
            (!pump_result || ++close_wait >= 128u))
            break;
    }

    if (g_frame)
        bda_gui_close_frame(g_frame);
    bda_free(g_pixels);
    return 0;
}
