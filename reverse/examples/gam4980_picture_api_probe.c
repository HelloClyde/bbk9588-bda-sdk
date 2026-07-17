#include "bda_sdk.h"

/* Independent admission probe for GUI+0x410 raw RGB565 picture submission. */

#define PROBE_GUI_TABLE_ADDR 0x81c00004u
#define PROBE_GUI_RENDER_PICTURE 0x410u

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define PICTURE_WIDTH 160
#define PICTURE_HEIGHT 96
#define PICTURE_X 40
#define PICTURE_Y 70

typedef struct probe_picture {
    void *pixels;
    u32 width;
    u32 height;
    u32 stride_bytes;
    u8 mode10;
    u8 bits_per_pixel11;
    u8 internal12;
    u8 internal13;
    void *source_pixels;
    s32 selected_index;
} probe_picture_t;

typedef char probe_picture_size_must_be_0x1c[
    sizeof(probe_picture_t) == 0x1cu ? 1 : -1
];
typedef char probe_picture_source_offset_must_be_0x14[
    __builtin_offsetof(probe_picture_t, source_pixels) == 0x14u ? 1 : -1
];
typedef char probe_picture_index_offset_must_be_0x18[
    __builtin_offsetof(probe_picture_t, selected_index) == 0x18u ? 1 : -1
];

static const char k_window_title[] = "G498 Picture";
static const char k_log_path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\G498PIC.TXT";

static u16 g_pixels[PICTURE_WIDTH * PICTURE_HEIGHT];
static probe_picture_t g_picture;
static bda_handle_t g_frame;
static bda_handle_t g_draw;
static bda_handle_t g_draw_owner;
static void *g_draw_object;
static u32 g_phase;
static u32 g_phase_mask;
static u32 g_submissions;
static u32 g_previous_keys;
static int g_failures;
static int g_exit;

static void *probe_gui_table(void)
{
    return *(void **)PROBE_GUI_TABLE_ADDR;
}

static int probe_render_picture(
    bda_handle_t context,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    const probe_picture_t *picture
)
{
    typedef int (*fn_t)(u32, u32, u32, u32, u32, u32);
    fn_t fn = (fn_t)*(void **)(
        (u8 *)probe_gui_table() + PROBE_GUI_RENDER_PICTURE
    );
    return fn(
        (u32)context,
        (u32)x,
        (u32)y,
        (u32)width,
        (u32)height,
        (u32)picture
    );
}

static u16 rgb565(u32 red, u32 green, u32 blue)
{
    return (u16)(((red & 0xf8u) << 8) | ((green & 0xfcu) << 3) | (blue >> 3));
}

static char *append_char(char *out, char *end, char value)
{
    if (out < end)
        *out++ = value;
    return out;
}

static char *append_text(char *out, char *end, const char *text)
{
    while (*text)
        out = append_char(out, end, *text++);
    return out;
}

static char *append_dec(char *out, char *end, int value)
{
    char digits[12];
    u32 magnitude;
    int count = 0;

    if (value < 0) {
        out = append_char(out, end, '-');
        magnitude = (u32)(0 - value);
    } else {
        magnitude = (u32)value;
    }
    do {
        digits[count++] = (char)('0' + magnitude % 10u);
        magnitude /= 10u;
    } while (magnitude && count < (int)sizeof(digits));
    while (count > 0)
        out = append_char(out, end, digits[--count]);
    return out;
}

static void log_line(const char *text)
{
    static const char newline[] = "\r\n";
    u32 length = 0;
    int file;

    while (text[length])
        ++length;
    file = bda_fs_fopen_raw(k_log_path, "ab");
    if (!bda_fs_file_is_valid(file))
        return;
    (void)bda_fs_write_raw(file, text, length);
    (void)bda_fs_write_raw(file, newline, 2u);
    (void)bda_fs_close_raw(file);
}

static void log_submission(
    u32 phase, int render_result, int guard_begin, int guard_end
)
{
    char line[128];
    char *out = line;
    char *end = line + sizeof(line) - 1;

    out = append_text(out, end, "PHASE=");
    out = append_dec(out, end, (int)phase);
    out = append_text(out, end, " RETURN=");
    out = append_dec(out, end, render_result);
    out = append_text(out, end, " GUARD_BEGIN=");
    out = append_dec(out, end, guard_begin);
    out = append_text(out, end, " GUARD_END=");
    out = append_dec(out, end, guard_end);
    *out = 0;
    log_line(line);
}

static void reset_log(void)
{
    int file = bda_fs_fopen_raw(k_log_path, "wb");
    if (bda_fs_file_is_valid(file))
        (void)bda_fs_close_raw(file);
}

static void fill_phase(u32 phase)
{
    int x;
    int y;

    for (y = 0; y < PICTURE_HEIGHT; ++y) {
        for (x = 0; x < PICTURE_WIDTH; ++x) {
            u16 color;
            if (phase == 0u) {
                if (y < PICTURE_HEIGHT / 2)
                    color = x < PICTURE_WIDTH / 2 ?
                        rgb565(248, 32, 32) : rgb565(32, 232, 72);
                else
                    color = x < PICTURE_WIDTH / 2 ?
                        rgb565(32, 96, 248) : rgb565(248, 248, 248);
            } else if (phase == 1u) {
                int stripe = x / 40;
                if (stripe == 0)
                    color = rgb565(248, 216, 32);
                else if (stripe == 1)
                    color = rgb565(32, 224, 224);
                else if (stripe == 2)
                    color = rgb565(240, 40, 216);
                else
                    color = rgb565(16, 20, 24);
            } else {
                color = (((x / 12) + (y / 12)) & 1) ?
                    rgb565(240, 240, 240) : rgb565(24, 28, 32);
                if (x >= 56 && x < 104 && y >= 24 && y < 72)
                    color = rgb565(248, 128, 24);
            }
            g_pixels[y * PICTURE_WIDTH + x] = color;
        }
    }
}

static void release_draw_context(void)
{
    bda_handle_t draw = g_draw;
    if (!draw || (s32)draw == -1) {
        g_draw = 0;
        g_draw_owner = 0;
        return;
    }
    g_draw = 0;
    g_draw_owner = 0;
    bda_gui_end_draw(draw);
}

static int acquire_draw_context(bda_handle_t owner)
{
    if (g_draw && g_draw_owner == owner)
        return 1;
    release_draw_context();
    g_draw = bda_gui_current_draw(owner);
    if (!g_draw || (s32)g_draw == -1) {
        g_draw = 0;
        return 0;
    }
    g_draw_owner = owner;
    return 1;
}

static void draw_labels(void)
{
    void *old_object;
    u32 foreground;
    u32 accent;

    if (!g_draw || !g_draw_object)
        return;
    foreground = (u32)bda_gui_rgb(g_draw, 242, 246, 248);
    accent = (u32)bda_gui_rgb(g_draw, 32, 205, 205);
    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    (void)bda_gui_set_text_mode(g_draw, 1u);
    (void)bda_gui_set_text_color(g_draw, foreground);
    (void)bda_gui_draw_text(g_draw, 34, 16, "RAW RGB565 PICTURE", -1);
    (void)bda_gui_set_text_color(g_draw, accent);
    (void)bda_gui_draw_text(g_draw, 36, 198, "ENTER: NEXT PHASE", -1);
    (void)bda_gui_set_text_color(g_draw, foreground);
    (void)bda_gui_draw_text(g_draw, 72, 238, "ESC: EXIT", -1);
    bda_gui_rectangle(
        g_draw,
        PICTURE_X - 2,
        PICTURE_Y - 2,
        PICTURE_X + PICTURE_WIDTH + 1,
        PICTURE_Y + PICTURE_HEIGHT + 1
    );
    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
}

static void present_phase(void)
{
    void *old_object;
    int guard_begin;
    int render_result;
    int guard_end;

    fill_phase(g_phase);
    guard_begin = bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    render_result = probe_render_picture(
        g_draw,
        PICTURE_X,
        PICTURE_Y,
        PICTURE_WIDTH,
        PICTURE_HEIGHT,
        &g_picture
    );
    (void)bda_gui_select_draw_object(g_draw, old_object);
    guard_end = bda_gui_draw_guard_end();
    ++g_submissions;
    g_phase_mask |= 1u << g_phase;
    if (render_result != 0)
        ++g_failures;
    log_submission(g_phase, render_result, guard_begin, guard_end);
    if (g_phase_mask == 7u && g_failures == 0)
        log_line("THREE_PHASES=PASS");
}

static u32 packet_mask(const bda_gui_input_packet_t *packet)
{
    u32 mask = 0;
    if (bda_gui_input_packet_key_pressed(packet, BDA_KEY_ENTER))
        mask |= 1u;
    if (bda_gui_input_packet_key_pressed(packet, BDA_KEY_ESCAPE))
        mask |= 2u;
    return mask;
}

static int picture_window_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
)
{
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        g_frame = handle;
        (void)acquire_draw_context(handle);
        if (!g_draw_object)
            g_draw_object = bda_gui_draw_object_create(7u);
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        if (!g_draw_owner || g_draw_owner == handle)
            release_draw_context();
        g_exit = 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

__attribute__((section(".text.bda_main")))
int bda_main(void)
{
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    bda_gui_input_packet_t initial_packet;
    int close_requested = 0;
    u32 close_wait = 0;

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    bda_memset(&g_picture, 0, sizeof(g_picture));
    g_picture.width = PICTURE_WIDTH;
    g_picture.height = PICTURE_HEIGHT;
    g_picture.source_pixels = g_pixels;
    g_picture.selected_index = -1;
    g_frame = 0;
    g_draw = 0;
    g_draw_owner = 0;
    g_draw_object = 0;
    g_phase = 0;
    g_phase_mask = 0;
    g_submissions = 0;
    g_previous_keys = 0;
    g_failures = 0;
    g_exit = 0;
    reset_log();
    log_line("GAM4980 PICTURE API ADMISSION PROBE V1");
    log_line("DESC_SIZE=28 SOURCE_OFFSET=20 INDEX_OFFSET=24");
    log_line("SOURCE=RGB565 SIZE=160x96 DEST=160x96");

    descriptor.style = 0;
    descriptor.title = k_window_title;
    descriptor.wndproc = picture_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    g_frame = bda_gui_register_frame_desc(&descriptor);
    if (!g_frame || (s32)g_frame == -1) {
        log_line("RESULT=FAIL FRAME");
        return 1;
    }
    (void)bda_gui_frame_activate(g_frame, 0x100u);
    (void)acquire_draw_context(g_frame);
    if (!g_draw_object)
        g_draw_object = bda_gui_draw_object_create(7u);
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        log_line("RESULT=FAIL DRAW");
        (void)bda_gui_frame_stop(g_frame);
        (void)bda_gui_frame_release(g_frame);
        release_draw_context();
        bda_gui_close_frame(g_frame);
        return 2;
    }

    draw_labels();
    present_phase();
    (void)bda_gui_input_packet(&initial_packet);
    g_previous_keys = packet_mask(&initial_packet);

    while (!g_exit) {
        bda_gui_input_packet_t packet;
        int pump_result = bda_gui_event_pump_frame_once(&message, g_frame);
        u32 current;
        u32 pressed;

        (void)bda_gui_input_packet(&packet);
        current = packet_mask(&packet);
        pressed = current & ~g_previous_keys;
        g_previous_keys = current;
        if (!close_requested && (pressed & 1u) && g_phase < 2u) {
            ++g_phase;
            present_phase();
        }
        if (!close_requested && (pressed & 2u)) {
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
            close_requested = 1;
        }
        if (close_requested) {
            ++close_wait;
            if (!pump_result || !g_draw || close_wait >= 128u)
                break;
        }
        bda_sys_delay(1u);
    }

    release_draw_context();
    if (g_frame) {
        if (!close_requested) {
            (void)bda_gui_frame_stop(g_frame);
            (void)bda_gui_frame_release(g_frame);
        }
        bda_gui_close_frame(g_frame);
        g_frame = 0;
    }
    if (g_phase_mask == 7u && g_submissions == 3u && g_failures == 0) {
        log_line("SUBMISSIONS=3");
        log_line("RESULT=PASS");
        return 0;
    }
    log_line("RESULT=FAIL INCOMPLETE");
    return 3;
}
