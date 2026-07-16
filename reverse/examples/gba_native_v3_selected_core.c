#include "../bda_research_sdk.h"

#define SCREEN_W 320
#define SCREEN_H 240
#define FB_BYTES (SCREEN_W * SCREEN_H * 2)

#define ROM_LOAD_MAX (2u * 1024u * 1024u)
#define EWRAM_SIZE   (256u * 1024u)
#define IWRAM_SIZE   (32u * 1024u)
#define VRAM_SIZE    (96u * 1024u)

#define ARM_N 0x80000000u
#define ARM_Z 0x40000000u
#define ARM_C 0x20000000u
#define ARM_V 0x10000000u
#define ARM_I 0x00000080u
#define ARM_F 0x00000040u
#define ARM_T 0x00000020u
#define ARM_SYS_MODE 0x1fu

typedef unsigned short u16;

typedef struct {
    u32 r[16];
    u32 cpsr;
    u32 steps;
    u32 unsupported_pc;
    u32 unsupported_op;
    u32 last_status;
} gba_cpu_t;

typedef struct {
    u8 *rom;
    u32 rom_size;
    u8 *ewram;
    u8 *iwram;
    u8 *vram;
    gba_cpu_t cpu;
} gba_core_t;

static const char *ROM_PATH = "A:\\gba\\gba.gba";
static const char *ROM_PATH_ALT = "a:\\gba\\gba.gba";
static char g_selected_path[80];

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

static void append_hex_digit(char **out, char *end, u32 v) {
    static const char hex[] = "0123456789ABCDEF";
    append_char(out, end, hex[v & 0xfu]);
}

static void append_hex8(char **out, char *end, u32 v) {
    append_hex_digit(out, end, v >> 4);
    append_hex_digit(out, end, v);
}

static void append_hex32(char **out, char *end, u32 v) {
    int i;
    for (i = 7; i >= 0; --i) {
        append_hex_digit(out, end, v >> (i * 4));
    }
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

static u32 read_le32(const u8 *p) {
    return (u32)p[0] | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

static u32 read_le16_mem(const u8 *p) {
    return (u32)p[0] | ((u32)p[1] << 8);
}

static void copy_text(char *dst, const char *src, u32 max) {
    u32 i = 0;
    if (!max) {
        return;
    }
    while (i + 1 < max && src[i]) {
        dst[i] = src[i];
        i++;
    }
    dst[i] = 0;
}

static void append_path_name(char *dst, const char *name, u32 max) {
    u32 i = 0;
    u32 j = 0;
    const char prefix[] = "A:\\gba\\";
    while (i + 1 < max && prefix[i]) {
        dst[i] = prefix[i];
        i++;
    }
    while (i + 1 < max && name[j]) {
        dst[i++] = name[j++];
    }
    dst[i] = 0;
}

static void trim_cfg_line(char *s) {
    u32 i = 0;
    while (s[i]) {
        if (s[i] == '\r' || s[i] == '\n' || s[i] == ' ' || s[i] == '\t') {
            s[i] = 0;
            return;
        }
        i++;
    }
}

static void set_selected_path(const char *selected_path) {
    if (selected_path && selected_path[0]) {
        if ((selected_path[1] == ':') || (selected_path[0] == '\\') || (selected_path[0] == '/')) {
            copy_text(g_selected_path, selected_path, sizeof(g_selected_path));
        } else {
            append_path_name(g_selected_path, selected_path, sizeof(g_selected_path));
        }
    } else {
        copy_text(g_selected_path, ROM_PATH, sizeof(g_selected_path));
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

static void draw_status_frame(u16 *fb, u32 phase) {
    int x;
    int y;
    u16 bg0 = rgb565(15, 22, 34);
    u16 bg1 = rgb565(23, 35, 52);
    u16 accent = phase ? rgb565(68, 204, 145) : rgb565(232, 94, 80);
    u16 blue = rgb565(72, 132, 224);
    u16 gold = rgb565(238, 190, 74);

    for (y = 0; y < SCREEN_H; ++y) {
        for (x = 0; x < SCREEN_W; ++x) {
            u32 band = ((u32)x + ((u32)y << 1)) >> 5;
            fb[y * SCREEN_W + x] = (band & 1u) ? bg0 : bg1;
        }
    }
    for (y = 28; y < 212; ++y) {
        for (x = 36; x < 284; ++x) {
            if (x < 40 || x >= 280 || y < 32 || y >= 208) {
                fb[y * SCREEN_W + x] = accent;
            } else if (y < 78) {
                fb[y * SCREEN_W + x] = rgb565(37, 52, 74);
            }
        }
    }
    for (y = 48; y < 62; ++y) {
        for (x = 72; x < 248; ++x) {
            fb[y * SCREEN_W + x] = gold;
        }
    }
    for (y = 114; y < 154; ++y) {
        for (x = 94; x < 226; ++x) {
            fb[y * SCREEN_W + x] = (phase == 2) ? accent : blue;
        }
    }
}

static u8 mem_read8(gba_core_t *g, u32 addr) {
    u32 region = addr >> 24;
    if (region == 0x02) {
        return g->ewram[addr & (EWRAM_SIZE - 1u)];
    }
    if (region == 0x03) {
        return g->iwram[addr & (IWRAM_SIZE - 1u)];
    }
    if (region == 0x06) {
        return g->vram[addr % VRAM_SIZE];
    }
    if (region >= 0x08 && region <= 0x0d) {
        u32 off = addr - 0x08000000u;
        if (off < g->rom_size) {
            return g->rom[off];
        }
    }
    return 0;
}

static u32 mem_read32(gba_core_t *g, u32 addr) {
    addr &= ~3u;
    return (u32)mem_read8(g, addr) |
           ((u32)mem_read8(g, addr + 1) << 8) |
           ((u32)mem_read8(g, addr + 2) << 16) |
           ((u32)mem_read8(g, addr + 3) << 24);
}

static u32 mem_read16(gba_core_t *g, u32 addr) {
    addr &= ~1u;
    return (u32)mem_read8(g, addr) | ((u32)mem_read8(g, addr + 1) << 8);
}

static void mem_write8(gba_core_t *g, u32 addr, u8 value) {
    u32 region = addr >> 24;
    if (region == 0x02) {
        g->ewram[addr & (EWRAM_SIZE - 1u)] = value;
    } else if (region == 0x03) {
        g->iwram[addr & (IWRAM_SIZE - 1u)] = value;
    } else if (region == 0x06) {
        g->vram[addr % VRAM_SIZE] = value;
    }
}

static void mem_write16(gba_core_t *g, u32 addr, u32 value) {
    addr &= ~1u;
    mem_write8(g, addr, (u8)value);
    mem_write8(g, addr + 1, (u8)(value >> 8));
}

static void mem_write32(gba_core_t *g, u32 addr, u32 value) {
    addr &= ~3u;
    mem_write8(g, addr, (u8)value);
    mem_write8(g, addr + 1, (u8)(value >> 8));
    mem_write8(g, addr + 2, (u8)(value >> 16));
    mem_write8(g, addr + 3, (u8)(value >> 24));
}

static u32 ror32(u32 v, u32 n) {
    n &= 31u;
    if (!n) {
        return v;
    }
    return (v >> n) | (v << (32u - n));
}

static u32 condition_passed(gba_cpu_t *c, u32 cond) {
    u32 n = (c->cpsr & ARM_N) != 0;
    u32 z = (c->cpsr & ARM_Z) != 0;
    u32 cc = (c->cpsr & ARM_C) != 0;
    u32 v = (c->cpsr & ARM_V) != 0;
    switch (cond) {
    case 0x0: return z;
    case 0x1: return !z;
    case 0x2: return cc;
    case 0x3: return !cc;
    case 0x4: return n;
    case 0x5: return !n;
    case 0x6: return v;
    case 0x7: return !v;
    case 0x8: return cc && !z;
    case 0x9: return !cc || z;
    case 0xa: return n == v;
    case 0xb: return n != v;
    case 0xc: return !z && (n == v);
    case 0xd: return z || (n != v);
    case 0xe: return 1;
    default: return 0;
    }
}

static void set_nz(gba_cpu_t *c, u32 value) {
    c->cpsr &= ~(ARM_N | ARM_Z);
    if (value & 0x80000000u) {
        c->cpsr |= ARM_N;
    }
    if (value == 0) {
        c->cpsr |= ARM_Z;
    }
}

static u32 add_set_flags(gba_cpu_t *c, u32 a, u32 b) {
    u32 r = a + b;
    c->cpsr &= ~(ARM_N | ARM_Z | ARM_C | ARM_V);
    if (r & 0x80000000u) c->cpsr |= ARM_N;
    if (r == 0) c->cpsr |= ARM_Z;
    if (r < a) c->cpsr |= ARM_C;
    if (((~(a ^ b)) & (a ^ r) & 0x80000000u) != 0) c->cpsr |= ARM_V;
    return r;
}

static u32 sub_set_flags(gba_cpu_t *c, u32 a, u32 b) {
    u32 r = a - b;
    c->cpsr &= ~(ARM_N | ARM_Z | ARM_C | ARM_V);
    if (r & 0x80000000u) c->cpsr |= ARM_N;
    if (r == 0) c->cpsr |= ARM_Z;
    if (a >= b) c->cpsr |= ARM_C;
    if (((a ^ b) & (a ^ r) & 0x80000000u) != 0) c->cpsr |= ARM_V;
    return r;
}

static u32 arm_reg_operand(gba_cpu_t *c, u32 op) {
    u32 rm = op & 0xfu;
    u32 value = c->r[rm];
    u32 type = (op >> 5) & 3u;
    u32 shift;
    if (op & 0x10u) {
        shift = c->r[(op >> 8) & 0xfu] & 0xffu;
    } else {
        shift = (op >> 7) & 0x1fu;
    }
    if (rm == 15) {
        value += 8;
    }
    if (shift == 0) {
        return value;
    }
    if (type == 0) return value << shift;
    if (type == 1) return value >> shift;
    if (type == 2) return (u32)((s32)value >> shift);
    return ror32(value, shift);
}

static u32 gba_step_thumb(gba_core_t *g) {
    gba_cpu_t *c = &g->cpu;
    u32 pc = c->r[15] & ~1u;
    u32 op = mem_read16(g, pc);
    c->r[15] = pc + 2;

    if ((op & 0xf800u) == 0x2000u) {
        u32 rd = (op >> 8) & 7u;
        u32 imm = op & 0xffu;
        c->r[rd] = imm;
        set_nz(c, imm);
    } else if ((op & 0xf800u) == 0x3000u) {
        u32 rd = (op >> 8) & 7u;
        c->r[rd] = add_set_flags(c, c->r[rd], op & 0xffu);
    } else if ((op & 0xf800u) == 0x3800u) {
        u32 rd = (op >> 8) & 7u;
        c->r[rd] = sub_set_flags(c, c->r[rd], op & 0xffu);
    } else if ((op & 0xf800u) == 0x2800u) {
        u32 rn = (op >> 8) & 7u;
        sub_set_flags(c, c->r[rn], op & 0xffu);
    } else if ((op & 0xf800u) == 0x1800u) {
        u32 rd = op & 7u;
        u32 rn = (op >> 3) & 7u;
        u32 rhs = (op >> 6) & 7u;
        if ((op & 0x0400u) == 0) {
            rhs = c->r[rhs];
        }
        if (op & 0x0200u) {
            c->r[rd] = sub_set_flags(c, c->r[rn], rhs);
        } else {
            c->r[rd] = add_set_flags(c, c->r[rn], rhs);
        }
    } else if ((op & 0xfc00u) == 0x4000u) {
        u32 rd = op & 7u;
        u32 rs = (op >> 3) & 7u;
        u32 kind = (op >> 6) & 0xfu;
        if (kind == 0x0) c->r[rd] &= c->r[rs];
        else if (kind == 0x1) c->r[rd] ^= c->r[rs];
        else if (kind == 0x2) c->r[rd] <<= (c->r[rs] & 0xffu);
        else if (kind == 0x8) sub_set_flags(c, c->r[rd], c->r[rs]);
        else if (kind == 0xa) c->r[rd] = sub_set_flags(c, c->r[rd], c->r[rs]);
        else if (kind == 0xc) c->r[rd] |= c->r[rs];
        else if (kind == 0xd) c->r[rd] *= c->r[rs];
        else {
            c->unsupported_pc = pc | 1u;
            c->unsupported_op = op;
            return 0;
        }
        if (kind != 0x8) set_nz(c, c->r[rd]);
    } else if ((op & 0xff87u) == 0x4700u) {
        u32 rm = ((op >> 3) & 0xfu);
        u32 target = c->r[rm];
        if (target & 1u) c->cpsr |= ARM_T;
        else c->cpsr &= ~ARM_T;
        c->r[15] = target & (target & 1u ? ~1u : ~3u);
    } else if ((op & 0xf800u) == 0x4800u) {
        u32 rd = (op >> 8) & 7u;
        u32 addr = (c->r[15] & ~2u) + ((op & 0xffu) << 2);
        c->r[rd] = mem_read32(g, addr);
    } else if ((op & 0xf800u) == 0x6000u) {
        u32 rb = (op >> 3) & 7u;
        u32 rd = op & 7u;
        mem_write32(g, c->r[rb] + (((op >> 6) & 0x1fu) << 2), c->r[rd]);
    } else if ((op & 0xf800u) == 0x6800u) {
        u32 rb = (op >> 3) & 7u;
        u32 rd = op & 7u;
        c->r[rd] = mem_read32(g, c->r[rb] + (((op >> 6) & 0x1fu) << 2));
    } else if ((op & 0xf800u) == 0x7000u) {
        u32 rb = (op >> 3) & 7u;
        u32 rd = op & 7u;
        mem_write8(g, c->r[rb] + ((op >> 6) & 0x1fu), (u8)c->r[rd]);
    } else if ((op & 0xf800u) == 0x7800u) {
        u32 rb = (op >> 3) & 7u;
        u32 rd = op & 7u;
        c->r[rd] = mem_read8(g, c->r[rb] + ((op >> 6) & 0x1fu));
    } else if ((op & 0xf800u) == 0x8000u) {
        u32 rb = (op >> 3) & 7u;
        u32 rd = op & 7u;
        mem_write16(g, c->r[rb] + (((op >> 6) & 0x1fu) << 1), c->r[rd]);
    } else if ((op & 0xf800u) == 0x8800u) {
        u32 rb = (op >> 3) & 7u;
        u32 rd = op & 7u;
        c->r[rd] = mem_read16(g, c->r[rb] + (((op >> 6) & 0x1fu) << 1));
    } else if ((op & 0xf800u) == 0x9000u) {
        u32 rd = (op >> 8) & 7u;
        mem_write32(g, c->r[13] + ((op & 0xffu) << 2), c->r[rd]);
    } else if ((op & 0xf800u) == 0x9800u) {
        u32 rd = (op >> 8) & 7u;
        c->r[rd] = mem_read32(g, c->r[13] + ((op & 0xffu) << 2));
    } else if ((op & 0xf000u) == 0xd000u && (op & 0x0f00u) != 0x0f00u) {
        u32 cond = (op >> 8) & 0xfu;
        s32 off = (s32)(op & 0xffu);
        if (off & 0x80) off |= (s32)0xffffff00u;
        if (condition_passed(c, cond)) c->r[15] = c->r[15] + ((u32)off << 1);
    } else if ((op & 0xf800u) == 0xe000u) {
        s32 off = (s32)(op & 0x7ffu);
        if (off & 0x400) off |= (s32)0xfffff800u;
        c->r[15] = c->r[15] + ((u32)off << 1);
    } else {
        c->unsupported_pc = pc | 1u;
        c->unsupported_op = op;
        return 0;
    }
    c->steps++;
    return 1;
}

static u32 gba_step_arm(gba_core_t *g) {
    gba_cpu_t *c = &g->cpu;
    u32 pc = c->r[15] & ~3u;
    u32 op = mem_read32(g, pc);
    u32 cond = op >> 28;
    c->r[15] = pc + 4;

    if (!condition_passed(c, cond)) {
        c->steps++;
        return 1;
    }

    if ((op & 0x0e000000u) == 0x0a000000u) {
        s32 off = (s32)(op & 0x00ffffffu);
        if (off & 0x00800000) {
            off |= (s32)0xff000000u;
        }
        off <<= 2;
        if (op & 0x01000000u) {
            c->r[14] = c->r[15] + 4;
        }
        c->r[15] = c->r[15] + 4 + (u32)off;
        c->steps++;
        return 1;
    }

    if ((op & 0x0ffffff0u) == 0x012fff10u) {
        u32 target = c->r[op & 0xfu];
        if (target & 1u) {
            c->cpsr |= ARM_T;
            c->r[15] = target & ~1u;
        } else {
            c->cpsr &= ~ARM_T;
            c->r[15] = target & ~3u;
        }
        c->steps++;
        return 1;
    }

    if ((op & 0x0c000000u) == 0x00000000u) {
        u32 opcode = (op >> 21) & 0xfu;
        u32 set_flags = (op >> 20) & 1u;
        u32 rn = (op >> 16) & 0xfu;
        u32 rd = (op >> 12) & 0xfu;
        u32 imm = (op & 0x02000000u) ? ror32(op & 0xffu, ((op >> 8) & 0xfu) * 2u) : arm_reg_operand(c, op);
        u32 a = c->r[rn];
        u32 result = 0;

        switch (opcode) {
        case 0x0:
            result = a & imm;
            c->r[rd] = result;
            break;
        case 0x1:
            result = a ^ imm;
            c->r[rd] = result;
            break;
        case 0x2:
            result = set_flags ? sub_set_flags(c, a, imm) : (a - imm);
            c->r[rd] = result;
            break;
        case 0x4:
            result = set_flags ? add_set_flags(c, a, imm) : (a + imm);
            c->r[rd] = result;
            break;
        case 0x8:
            result = a & imm;
            set_flags = 1;
            break;
        case 0x9:
            result = a ^ imm;
            set_flags = 1;
            break;
        case 0xa:
            result = sub_set_flags(c, a, imm);
            set_flags = 1;
            break;
        case 0xc:
            result = a | imm;
            c->r[rd] = result;
            break;
        case 0xd:
            result = imm;
            c->r[rd] = result;
            break;
        case 0xe:
            result = a & ~imm;
            c->r[rd] = result;
            break;
        case 0xf:
            result = ~imm;
            c->r[rd] = result;
            break;
        default:
            c->unsupported_pc = pc;
            c->unsupported_op = op;
            return 0;
        }
        if (set_flags && opcode != 0x2 && opcode != 0x4 && opcode != 0xa) {
            set_nz(c, result);
        }
        c->steps++;
        return 1;
    }

    if ((op & 0x0c000000u) == 0x04000000u) {
        u32 load = (op >> 20) & 1u;
        u32 rn = (op >> 16) & 0xfu;
        u32 rd = (op >> 12) & 0xfu;
        u32 up = (op >> 23) & 1u;
        u32 off = op & 0xfffu;
        u32 addr = up ? (c->r[rn] + off) : (c->r[rn] - off);
        if (load) {
            c->r[rd] = (op & 0x00400000u) ? mem_read8(g, addr) : mem_read32(g, addr);
        } else {
            if (op & 0x00400000u) mem_write8(g, addr, (u8)c->r[rd]);
            else mem_write32(g, addr, c->r[rd]);
        }
        c->steps++;
        return 1;
    }

    if ((op & 0x0e000000u) == 0x08000000u) {
        u32 load = (op >> 20) & 1u;
        u32 rn = (op >> 16) & 0xfu;
        u32 list = op & 0xffffu;
        u32 addr = c->r[rn];
        u32 i;
        for (i = 0; i < 16; ++i) {
            if (list & (1u << i)) {
                if (load) c->r[i] = mem_read32(g, addr);
                else mem_write32(g, addr, c->r[i]);
                addr += 4;
            }
        }
        if (op & 0x00200000u) {
            c->r[rn] = addr;
        }
        c->steps++;
        return 1;
    }

    c->unsupported_pc = pc;
    c->unsupported_op = op;
    return 0;
}

static u32 gba_run_probe(gba_core_t *g, u32 max_steps) {
    u32 i;
    g->cpu.cpsr = ARM_I | ARM_F | ARM_SYS_MODE;
    g->cpu.r[13] = 0x03007f00u;
    g->cpu.r[14] = 0x08000000u;
    g->cpu.r[15] = 0x08000000u;
    g->cpu.steps = 0;
    g->cpu.unsupported_pc = 0;
    g->cpu.unsupported_op = 0;
    g->cpu.last_status = 0;

    for (i = 0; i < max_steps; ++i) {
        if (!((g->cpu.cpsr & ARM_T) ? gba_step_thumb(g) : gba_step_arm(g))) {
            g->cpu.last_status = 2;
            return 0;
        }
    }
    g->cpu.last_status = 1;
    return 1;
}

static int load_rom(gba_core_t *g, u8 *hdr, u32 *file_size_out, const char *selected_path) {
    int f;
    int got;
    u32 size;
    set_selected_path(selected_path);
    f = bda_fs_fopen_raw(g_selected_path, "rb");
    if (!f) {
        f = bda_fs_fopen_raw(ROM_PATH_ALT, "rb");
        if (f) {
            copy_text(g_selected_path, ROM_PATH_ALT, sizeof(g_selected_path));
        }
    }
    if (!f) {
        return 0;
    }

    bda_fs_seek_raw(f, 0, BDA_SEEK_END);
    size = (u32)bda_fs_tell_raw(f);
    bda_fs_seek_raw(f, 0, BDA_SEEK_SET);
    *file_size_out = size;
    if (size > ROM_LOAD_MAX) {
        size = ROM_LOAD_MAX;
    }
    g->rom_size = size;
    g->rom = (u8 *)bda_alloc(size);
    if (!g->rom) {
        bda_fs_close_raw(f);
        return -1;
    }
    got = bda_fs_fread_raw(g->rom, 1, size, f);
    bda_fs_close_raw(f);
    if (got < 0xc0) {
        return -2;
    }
    bda_memcpy(hdr, g->rom, 0xc0);
    return got;
}

__attribute__((section(".text.bda_main")))
int bda_main(const char *selected_path) {
    gba_core_t g;
    u8 hdr[0xc0];
    char title[13];
    char msg[256];
    char *out = msg;
    char *end = msg + sizeof(msg);
    u32 file_size = 0;
    int loaded;
    u32 calc = 0;
    u32 header_ok = 0;
    u16 *fb = (u16 *)bda_alloc(FB_BYTES);

    bda_memset(&g, 0, sizeof(g));
    bda_memset(hdr, 0, sizeof(hdr));

    if (fb) {
        draw_status_frame(fb, 0);
        bda_gui_blit_like(0, 0, SCREEN_H, SCREEN_W, fb);
    }

    g.ewram = (u8 *)bda_alloc(EWRAM_SIZE);
    g.iwram = (u8 *)bda_alloc(IWRAM_SIZE);
    g.vram = (u8 *)bda_alloc(VRAM_SIZE);
    if (g.ewram) bda_memset(g.ewram, 0, EWRAM_SIZE);
    if (g.iwram) bda_memset(g.iwram, 0, IWRAM_SIZE);
    if (g.vram) bda_memset(g.vram, 0, VRAM_SIZE);

    loaded = load_rom(&g, hdr, &file_size, selected_path);
    if (loaded > 0 && g.ewram && g.iwram && g.vram) {
        calc = gba_header_checksum(hdr);
        header_ok = (calc == hdr[0xbd]);
        gba_run_probe(&g, 2048);
    }

    if (fb) {
        draw_status_frame(fb, g.cpu.last_status ? 2 : header_ok);
        bda_gui_blit_like(0, 0, SCREEN_H, SCREEN_W, fb);
    }

    append_text(&out, end, "GBA native v3\n");
    if (loaded == 0) {
        append_text(&out, end, "ROM not found:\nA:\\gba\\gba.gba");
    } else if (loaded < 0) {
        append_text(&out, end, "ROM load/mem failed: ");
        append_dec(&out, end, (u32)(-loaded));
    } else {
        copy_gba_title(title, hdr);
        append_text(&out, end, "Path: ");
        append_text(&out, end, g_selected_path);
        append_char(&out, end, '\n');
        append_text(&out, end, "ROM: ");
        append_text(&out, end, title);
        append_text(&out, end, "\nSize/load: ");
        append_dec(&out, end, file_size);
        append_char(&out, end, '/');
        append_dec(&out, end, (u32)loaded);
        append_text(&out, end, "\nChk ");
        append_text(&out, end, header_ok ? "OK " : "BAD ");
        append_hex8(&out, end, hdr[0xbd]);
        append_char(&out, end, '/');
        append_hex8(&out, end, calc);
        append_text(&out, end, "\nPC=");
        append_hex32(&out, end, g.cpu.r[15]);
        append_text(&out, end, " steps=");
        append_dec(&out, end, g.cpu.steps);
        if (g.cpu.last_status == 2) {
            append_text(&out, end, "\nUNSUP pc=");
            append_hex32(&out, end, g.cpu.unsupported_pc);
            append_text(&out, end, " op=");
            append_hex32(&out, end, g.cpu.unsupported_op);
        }
    }
    finish_text(&out, end);

    if (fb) bda_free(fb);
    if (g.rom) bda_free(g.rom);
    if (g.ewram) bda_free(g.ewram);
    if (g.iwram) bda_free(g.iwram);
    if (g.vram) bda_free(g.vram);

    bda_msgbox("GBA", msg);
    return 0;
}
