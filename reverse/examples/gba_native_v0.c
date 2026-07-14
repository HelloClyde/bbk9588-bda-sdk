#include "bda_sdk.h"

#define SCREEN_W 320
#define SCREEN_H 240
#define FB_BYTES (SCREEN_W * SCREEN_H * 2)

typedef unsigned short u16;

static const char *ROM_PATH = "A:\\gba\\gba.gba";
static const char *ROM_PATH_ALT = "a:\\gba\\gba.gba";

static u16 rgb565(u32 r, u32 g, u32 b) {
    return (u16)(((r & 0xf8u) << 8) | ((g & 0xfcu) << 3) | ((b & 0xf8u) >> 3));
}

static void append_char(char **out, char *end, char c) {
    if (*out < end) {
        **out = c;
        *out += 1;
    }
}

static void append_text(char **out, char *end, const char *s) {
    while (*s) {
        append_char(out, end, *s++);
    }
}

static void append_hex8(char **out, char *end, u32 v) {
    static const char hex[] = "0123456789ABCDEF";
    append_char(out, end, hex[(v >> 4) & 0xf]);
    append_char(out, end, hex[v & 0xf]);
}

static void append_dec(char **out, char *end, u32 v) {
    char tmp[10];
    int n = 0;
    if (v == 0) {
        append_char(out, end, '0');
        return;
    }
    while (v && n < (int)sizeof(tmp)) {
        tmp[n++] = (char)('0' + (v % 10));
        v /= 10;
    }
    while (n > 0) {
        append_char(out, end, tmp[--n]);
    }
}

static void finish_text(char **out, char *end) {
    if (*out >= end) {
        end[-1] = 0;
    } else {
        **out = 0;
    }
}

static void copy_gba_title(char *dst, const u8 *hdr) {
    int i;
    for (i = 0; i < 12; ++i) {
        u8 c = hdr[0xa0 + i];
        if (c < 0x20 || c > 0x7e) {
            break;
        }
        dst[i] = (char)c;
    }
    dst[i] = 0;
    if (i == 0) {
        dst[0] = '?';
        dst[1] = 0;
    }
}

static u32 gba_header_checksum(const u8 *hdr) {
    u32 sum = 0;
    u32 i;
    for (i = 0xa0; i <= 0xbc; ++i) {
        sum += hdr[i];
    }
    return (0x100u - ((sum + 0x19u) & 0xffu)) & 0xffu;
}

static void draw_status_frame(u16 *fb, u32 ok) {
    int x;
    int y;
    u16 bg0 = rgb565(18, 24, 38);
    u16 bg1 = rgb565(24, 36, 54);
    u16 accent = ok ? rgb565(64, 210, 138) : rgb565(230, 83, 83);
    u16 gold = rgb565(238, 190, 74);

    for (y = 0; y < SCREEN_H; ++y) {
        for (x = 0; x < SCREEN_W; ++x) {
            u32 band = ((u32)x + (u32)y) >> 4;
            fb[y * SCREEN_W + x] = (band & 1u) ? bg0 : bg1;
        }
    }

    for (y = 28; y < 212; ++y) {
        for (x = 38; x < 282; ++x) {
            if (x < 42 || x >= 278 || y < 32 || y >= 208) {
                fb[y * SCREEN_W + x] = accent;
            } else if (y < 78) {
                fb[y * SCREEN_W + x] = rgb565(42, 55, 77);
            }
        }
    }

    for (y = 48; y < 62; ++y) {
        for (x = 72; x < 248; ++x) {
            fb[y * SCREEN_W + x] = gold;
        }
    }
    for (y = 120; y < 150; ++y) {
        for (x = 112; x < 208; ++x) {
            fb[y * SCREEN_W + x] = accent;
        }
    }
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    u8 hdr[0xc0];
    char title[13];
    char msg[192];
    char *out = msg;
    char *end = msg + sizeof(msg);
    int f;
    int got = 0;
    u32 calc = 0;
    u32 ok = 0;
    u16 *fb;

    fb = (u16 *)bda_alloc(FB_BYTES);
    if (fb) {
        draw_status_frame(fb, 0);
        bda_gui_blit_like(0, 0, SCREEN_H, SCREEN_W, fb);
    }

    bda_memset(hdr, 0, sizeof(hdr));
    f = bda_fs_fopen_raw(ROM_PATH, "rb");
    if (!f) {
        f = bda_fs_fopen_raw(ROM_PATH_ALT, "rb");
    }

    if (f) {
        got = bda_fs_fread_raw(hdr, 1, sizeof(hdr), f);
        bda_fs_close_raw(f);
    }

    append_text(&out, end, "GBA native v0\n");
    if (!f) {
        append_text(&out, end, "ROM not found:\nA:\\gba\\gba.gba");
    } else if (got < (int)sizeof(hdr)) {
        append_text(&out, end, "ROM header read failed, bytes=");
        append_dec(&out, end, (u32)got);
    } else {
        copy_gba_title(title, hdr);
        calc = gba_header_checksum(hdr);
        ok = (calc == hdr[0xbd]);
        append_text(&out, end, "ROM: ");
        append_text(&out, end, title);
        append_text(&out, end, "\nCode: ");
        append_char(&out, end, (char)hdr[0xac]);
        append_char(&out, end, (char)hdr[0xad]);
        append_char(&out, end, (char)hdr[0xae]);
        append_char(&out, end, (char)hdr[0xaf]);
        append_text(&out, end, "\nHeader chk ");
        append_text(&out, end, ok ? "OK " : "BAD ");
        append_text(&out, end, "got=");
        append_hex8(&out, end, hdr[0xbd]);
        append_text(&out, end, " calc=");
        append_hex8(&out, end, calc);
    }
    finish_text(&out, end);

    if (fb) {
        draw_status_frame(fb, ok);
        bda_gui_blit_like(0, 0, SCREEN_H, SCREEN_W, fb);
        bda_free(fb);
    }

    bda_msgbox("GBA", msg);
    return 0;
}
