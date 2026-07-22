#include "bda_audio.h"
#include "bda_dialogs.h"
#include "bda_filesystem.h"
#include "bda_graphics.h"
#include "bda_input.h"
#include "bda_memory.h"
#include "bda_time.h"
#include "bda_window.h"

#define SCREEN_WIDTH 240
#define SCREEN_HEIGHT 320
#define PLOT_LEFT 10
#define PLOT_RIGHT 229
#define PLOT_TOP 54
#define PLOT_BOTTOM 276
#define PLOT_CENTER ((PLOT_TOP + PLOT_BOTTOM) / 2)
#define PLOT_AMPLITUDE 96
#define PLOT_COLUMNS (PLOT_RIGHT - PLOT_LEFT + 1)
#define CAPTURE_SAMPLE_COUNT \
    (BDA_AUDIO_CAPTURE_BLOCK_BYTES / (u32)sizeof(s16))
#define CAPTURE_MAX_BLOCKS 128u

static const char k_window_title[] = "CAPTURE";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\AUDCAP.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\AUDCAP.RAW";
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\AUDCAP.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\AUDCAP.TXT";

static bda_handle_t g_frame;
static bda_handle_t g_draw;
static bda_handle_t g_draw_owner;
static void *g_draw_object;
static volatile int g_exit;
static volatile int g_need_redraw;
static int g_has_waveform;
static s16 g_pcm[CAPTURE_SAMPLE_COUNT];
static s16 g_wave_y[PLOT_COLUMNS];
static s16 g_painted_y[PLOT_COLUMNS];
static const char *g_log_path;
static char g_log_line[96];

static char *append_text(char *out, char *end, const char *text) {
    while (*text && out < end) {
        *out++ = *text++;
    }
    return out;
}

static char *append_u32(char *out, char *end, u32 value) {
    char digits[10];
    int count = 0;

    do {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    } while (value && count < (int)sizeof(digits));
    while (count > 0 && out < end) {
        *out++ = digits[--count];
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
    char *end = g_log_line + sizeof(g_log_line) - 1;
    int file;

    out = append_text(out, end, "\r\n");
    *out = 0;
    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_log_line, (u32)(out - g_log_line));
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
    out = append_u32(out, end, value);
    write_log_line(out);
}

static void release_draw_context(void) {
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

static int acquire_draw_context(bda_handle_t owner) {
    if (g_draw && g_draw_owner == owner) {
        return 1;
    }
    release_draw_context();
    g_draw = bda_gui_current_draw(owner);
    if (!g_draw || (s32)g_draw == -1) {
        g_draw = 0;
        return 0;
    }
    g_draw_owner = owner;
    return 1;
}

static u32 draw_color(u32 red, u32 green, u32 blue) {
    return (u32)bda_gui_rgb(g_draw, red, green, blue);
}

static void draw_segment(s32 x0, s32 y0, s32 x1, s32 y1, u32 color) {
    s32 dx = x1 > x0 ? x1 - x0 : x0 - x1;
    s32 sx = x0 < x1 ? 1 : -1;
    s32 dy_abs = y1 > y0 ? y1 - y0 : y0 - y1;
    s32 dy = -dy_abs;
    s32 sy = y0 < y1 ? 1 : -1;
    s32 error = dx + dy;

    for (;;) {
        (void)bda_gui_put_pixel(g_draw, x0, y0, color);
        if (x0 == x1 && y0 == y1) {
            break;
        }
        {
            s32 doubled = error * 2;

            if (doubled >= dy) {
                error += dy;
                x0 += sx;
            }
            if (doubled <= dx) {
                error += dx;
                y0 += sy;
            }
        }
    }
}

static void draw_grid(u32 color) {
    s32 x;
    s32 y;

    for (x = PLOT_LEFT; x <= PLOT_RIGHT; ++x) {
        (void)bda_gui_put_pixel(g_draw, x, PLOT_TOP, color);
        (void)bda_gui_put_pixel(g_draw, x, PLOT_BOTTOM, color);
        if ((x & 3) == 0) {
            (void)bda_gui_put_pixel(g_draw, x, PLOT_CENTER, color);
        }
    }
    for (y = PLOT_TOP; y <= PLOT_BOTTOM; ++y) {
        (void)bda_gui_put_pixel(g_draw, PLOT_LEFT, y, color);
        (void)bda_gui_put_pixel(g_draw, PLOT_RIGHT, y, color);
        if ((y & 3) == 0) {
            for (x = PLOT_LEFT + 40; x < PLOT_RIGHT; x += 40) {
                (void)bda_gui_put_pixel(g_draw, x, y, color);
            }
        }
    }
}

static void draw_waveform(const s16 *points, u32 color) {
    s32 column;

    for (column = 1; column < PLOT_COLUMNS; ++column) {
        draw_segment(
            PLOT_LEFT + column - 1,
            points[column - 1],
            PLOT_LEFT + column,
            points[column],
            color
        );
    }
}

static void calculate_waveform(void) {
    s32 sum = 0;
    s32 mean;
    s32 peak = 1;
    s32 index;
    s32 column;

    for (index = 0; index < (s32)CAPTURE_SAMPLE_COUNT; ++index) {
        sum += (s32)g_pcm[index];
    }
    mean = sum / (s32)CAPTURE_SAMPLE_COUNT;
    for (index = 0; index < (s32)CAPTURE_SAMPLE_COUNT; ++index) {
        s32 centered = (s32)g_pcm[index] - mean;
        s32 magnitude = centered < 0 ? -centered : centered;

        if (magnitude > peak) {
            peak = magnitude;
        }
    }
    if (peak < 64) {
        peak = 64;
    }

    for (column = 0; column < PLOT_COLUMNS; ++column) {
        s32 begin = column * (s32)CAPTURE_SAMPLE_COUNT / PLOT_COLUMNS;
        s32 end = (column + 1) * (s32)CAPTURE_SAMPLE_COUNT / PLOT_COLUMNS;
        s32 bucket_sum = 0;
        s32 sample;
        s32 average;
        s32 y;

        for (sample = begin; sample < end; ++sample) {
            bucket_sum += (s32)g_pcm[sample];
        }
        average = bucket_sum / (end - begin) - mean;
        y = PLOT_CENTER - average * PLOT_AMPLITUDE / peak;
        if (y < PLOT_TOP + 1) {
            y = PLOT_TOP + 1;
        } else if (y > PLOT_BOTTOM - 1) {
            y = PLOT_BOTTOM - 1;
        }
        g_wave_y[column] = (s16)y;
    }
}

static void draw_static_scene(void) {
    bda_handle_t base_draw;
    bda_handle_t object_draw;
    int object_draw_active;
    void *old_object;
    u32 foreground;
    u32 muted;

    if (!g_draw || !g_draw_object) {
        return;
    }
    base_draw = g_draw;
    object_draw = bda_gui_object_draw_begin(g_frame);
    object_draw_active = object_draw && (s32)(u32)object_draw != -1;
    if (object_draw_active) {
        g_draw = object_draw;
    }

    foreground = draw_color(235, 245, 250);
    muted = draw_color(145, 165, 175);
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    (void)bda_gui_set_text_mode(g_draw, 1);
    (void)bda_gui_set_text_color(g_draw, foreground);
    (void)bda_gui_draw_text(g_draw, 44, 10, "LIVE MIC WAVEFORM", -1);
    (void)bda_gui_set_text_color(g_draw, muted);
    (void)bda_gui_draw_text(g_draw, 72, 31, "16 KHZ MONO", -1);
    (void)bda_gui_draw_text(g_draw, 82, 299, "ESC STOP", -1);
    (void)bda_gui_select_draw_object(g_draw, old_object);

    if (object_draw_active) {
        bda_gui_object_draw_end(g_frame, object_draw);
        g_draw = base_draw;
    }
}

static void redraw_scene(void) {
    void *old_object;
    u32 grid;
    u32 wave;

    if (!g_draw || !g_draw_object) {
        return;
    }
    draw_static_scene();
    grid = draw_color(55, 75, 85);
    wave = draw_color(45, 235, 125);
    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    draw_grid(grid);
    if (g_has_waveform) {
        draw_waveform(g_painted_y, wave);
    }
    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
    g_need_redraw = 0;
}

static void present_waveform(void) {
    void *old_object;
    u32 background;
    u32 grid;
    u32 wave;
    s32 column;

    if (!g_draw || !g_draw_object) {
        return;
    }
    background = draw_color(0, 0, 0);
    grid = draw_color(55, 75, 85);
    wave = draw_color(45, 235, 125);
    (void)bda_gui_draw_guard_begin();
    old_object = bda_gui_select_draw_object(g_draw, g_draw_object);
    if (g_has_waveform) {
        draw_waveform(g_painted_y, background);
    }
    draw_grid(grid);
    draw_waveform(g_wave_y, wave);
    for (column = 0; column < PLOT_COLUMNS; ++column) {
        g_painted_y[column] = g_wave_y[column];
    }
    g_has_waveform = 1;
    (void)bda_gui_select_draw_object(g_draw, old_object);
    (void)bda_gui_draw_guard_end();
}

static int capture_window_proc(
    bda_handle_t handle, u32 message, u32 wparam, u32 lparam
) {
    if (message == BDA_MSG_DRAW_CONTEXT_ATTACH) {
        g_frame = handle;
        (void)acquire_draw_context(handle);
        if (!g_draw_object) {
            g_draw_object = bda_gui_draw_object_create(7);
        }
        g_need_redraw = 1;
    } else if (message == BDA_MSG_REDRAW_INPUT) {
        g_need_redraw = 1;
    } else if (message == BDA_MSG_DRAW_CONTEXT_DETACH) {
        if (!g_draw_owner || g_draw_owner == handle) {
            release_draw_context();
        }
        g_exit = 1;
    }
    return bda_gui_default_proc(handle, message, wparam, lparam);
}

static int open_raw(void) {
    int file = bda_fs_fopen_raw(k_raw_path_a, "wb");

    if (!bda_fs_file_is_valid(file)) {
        file = bda_fs_fopen_raw(k_raw_path_root, "wb");
    }
    return file;
}

static void wait_escape_release(void) {
    bda_gui_input_packet_t packet;

    do {
        (void)bda_gui_input_packet(&packet);
        bda_sys_delay(1u);
    } while (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ESCAPE));
}

static void close_window(bda_gui_message_t *message) {
    u32 close_wait;

    if (!g_frame) {
        return;
    }
    if (!g_exit) {
        (void)bda_gui_frame_stop(g_frame);
        (void)bda_gui_frame_release(g_frame);
        for (close_wait = 0u; close_wait < 128u; ++close_wait) {
            if (!bda_gui_event_pump_frame_once(message, g_frame) || g_exit) {
                break;
            }
            bda_sys_delay(1u);
        }
    }
    release_draw_context();
    bda_gui_close_frame(g_frame);
    g_frame = 0;
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_audio_capture_t capture = BDA_AUDIO_CAPTURE_INITIALIZER;
    bda_frame_desc_t descriptor;
    bda_gui_message_t message;
    bda_gui_input_packet_t packet;
    u32 block;
    int file;
    int result;
    int capture_open = 0;
    int escape_pressed = 0;
    int failed = 0;

    reset_log();
    log_text("START AUDIO CAPTURE WAVEFORM V1");
    log_value("FIRMWARE=", bda_audio_capture_firmware());
    if (!bda_audio_capture_is_supported()) {
        log_text("RESULT=UNSUPPORTED");
        bda_msgbox("Audio Capture", "Unsupported firmware");
        return 0;
    }
    file = open_raw();
    if (!bda_fs_file_is_valid(file)) {
        log_text("RAW OPEN FAILED");
        bda_msgbox("Audio Capture", "Cannot create AUDCAP.RAW");
        return 1;
    }
    log_text("RAW OPENED");

    bda_memset(&descriptor, 0, sizeof(descriptor));
    bda_memset(&message, 0, sizeof(message));
    g_frame = 0;
    g_draw = 0;
    g_draw_owner = 0;
    g_draw_object = 0;
    g_exit = 0;
    g_need_redraw = 1;
    g_has_waveform = 0;
    descriptor.style = 0;
    descriptor.title = k_window_title;
    descriptor.wndproc = capture_window_proc;
    descriptor.height = SCREEN_WIDTH;
    descriptor.width = SCREEN_HEIGHT;
    descriptor.surface = 0;

    log_text("BEFORE FRAME REGISTER");
    g_frame = bda_gui_register_frame_desc(&descriptor);
    if (!g_frame || (s32)g_frame == -1) {
        (void)bda_fs_close_raw(file);
        log_text("FRAME REGISTER FAILED");
        bda_msgbox("Audio Capture", "Frame registration failed");
        return 2;
    }
    log_text("FRAME REGISTERED");
    (void)bda_gui_frame_activate(g_frame, 0x100u);
    (void)acquire_draw_context(g_frame);
    if (!g_draw_object) {
        g_draw_object = bda_gui_draw_object_create(7);
    }
    if (!g_draw || !g_draw_object || (s32)(u32)g_draw_object == -1) {
        log_text("DRAW CONTEXT FAILED");
        failed = 1;
    } else {
        redraw_scene();
        log_text("INITIAL SCENE DRAWN");
    }

    if (!failed) {
        log_text("BEFORE CAPTURE OPEN");
        result = bda_audio_capture_open(&capture);
        log_value("CAPTURE OPEN RESULT=", (u32)result);
        if (result == BDA_AUDIO_CAPTURE_OK) {
            capture_open = 1;
        } else {
            failed = 1;
        }
    }

    for (block = 0u;
         !failed && !g_exit && block < CAPTURE_MAX_BLOCKS;
         ++block) {
        if ((block & 7u) == 0u) {
            log_value("BEFORE READ BLOCK=", block);
        }
        result = bda_audio_capture_read(
            &capture, g_pcm, BDA_AUDIO_CAPTURE_BLOCK_BYTES
        );
        if ((block & 7u) == 0u) {
            log_value("READ RESULT=", (u32)result);
        }
        if (result != (int)BDA_AUDIO_CAPTURE_BLOCK_BYTES ||
            bda_fs_write_raw(file, g_pcm, BDA_AUDIO_CAPTURE_BLOCK_BYTES) !=
                (int)BDA_AUDIO_CAPTURE_BLOCK_BYTES) {
            failed = 1;
            break;
        }
        calculate_waveform();
        (void)bda_gui_event_pump_frame_once(&message, g_frame);
        if (g_need_redraw) {
            redraw_scene();
        }
        present_waveform();
        if (block == 0u) {
            log_text("FIRST WAVEFORM PRESENTED");
        }
        (void)bda_gui_input_packet(&packet);
        if (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ESCAPE)) {
            escape_pressed = 1;
            break;
        }
    }

    if (capture_open) {
        log_text("BEFORE CAPTURE STOP");
        result = bda_audio_capture_stop(&capture);
        log_value("CAPTURE STOP RESULT=", (u32)result);
        if (result != BDA_AUDIO_CAPTURE_OK) {
            failed = 1;
        }
        capture_open = 0;
    }
    (void)bda_fs_close_raw(file);
    if (escape_pressed) {
        wait_escape_release();
    }
    log_text("BEFORE WINDOW CLOSE");
    close_window(&message);
    log_text("WINDOW CLOSED");
    log_text(failed ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END AUDIO CAPTURE WAVEFORM V1");
    bda_msgbox(
        "Audio Capture",
        failed ? "Capture failed" : "Waveform PCM saved to AUDCAP.RAW"
    );
    return failed;
}
