#include "../bda_research_sdk.h"

typedef signed short probe_s16;

#define RECORD_BLOCK_BYTES 0x1000u
#define RECORD_BLOCK_SAMPLES (RECORD_BLOCK_BYTES / (u32)sizeof(probe_s16))
#define RECORD_BLOCK_COUNT 8u
#define READY_TIMEOUT_TICKS 200u
#define READY_POLL_LIMIT 12000000u

#if defined(RECORD_STREAM_PROBE_V13)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM13.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM13.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM13.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM13.RAW";
#elif defined(RECORD_STREAM_PROBE_V12)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM12.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM12.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM12.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM12.RAW";
#elif defined(RECORD_STREAM_PROBE_V11)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM11.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM11.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM11.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM11.RAW";
#elif defined(RECORD_STREAM_PROBE_V10)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM10.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM10.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM10.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM10.RAW";
#elif defined(RECORD_STREAM_PROBE_V9)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM9.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM9.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM9.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM9.RAW";
#elif defined(RECORD_STREAM_PROBE_V8)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM8.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM8.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM8.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM8.RAW";
#elif defined(RECORD_STREAM_PROBE_V7)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM7.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM7.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM7.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM7.RAW";
#elif defined(RECORD_STREAM_PROBE_V6)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM6.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM6.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM6.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM6.RAW";
#elif defined(RECORD_STREAM_PROBE_V5)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM5.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM5.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM5.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM5.RAW";
#elif defined(RECORD_STREAM_PROBE_V4)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM4.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM4.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM4.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM4.RAW";
#elif defined(RECORD_STREAM_PROBE_V3)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM3.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM3.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM3.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM3.RAW";
#elif defined(RECORD_STREAM_PROBE_V2)
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM2.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM2.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM2.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM2.RAW";
#else
static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM.TXT";
static const char k_raw_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM.RAW";
static const char k_raw_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\RECPCM.RAW";
#endif

static const char *g_log_path;
static char g_line[192];
static probe_s16 g_pcm[RECORD_BLOCK_SAMPLES];

#if defined(RECORD_STREAM_PROBE_V2) || defined(RECORD_STREAM_PROBE_V4) || \
    defined(RECORD_STREAM_PROBE_V6)
static u32 g_capture_open_address;
static u32 g_capture_ready_address;
static u32 g_capture_read_address;
#ifdef RECORD_STREAM_PROBE_V6
static u32 g_capture_config_wrapper_address;
#endif
#endif

static char *append_char(char *out, char *end, char value) {
    if (out < end) {
        *out++ = value;
    }
    return out;
}

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
    while (count > 0) {
        out = append_char(out, end, digits[--count]);
    }
    return out;
}

static char *append_s32(char *out, char *end, s32 value) {
    u32 magnitude;

    if (value < 0) {
        out = append_char(out, end, '-');
        magnitude = (u32)(-(value + 1)) + 1u;
    } else {
        magnitude = (u32)value;
    }
    return append_u32(out, end, magnitude);
}

static char *append_hex32(char *out, char *end, u32 value) {
    static const char hex[] = "0123456789ABCDEF";
    int shift;

    out = append_text(out, end, "0x");
    for (shift = 28; shift >= 0; shift -= 4) {
        out = append_char(out, end, hex[(value >> shift) & 0x0fu]);
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

static int open_raw(void) {
    int file = bda_fs_fopen_raw(k_raw_path_a, "wb");

    if (!bda_fs_file_is_valid(file)) {
        file = bda_fs_fopen_raw(k_raw_path_root, "wb");
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

static void write_line(char *out) {
    char *end = g_line + sizeof(g_line) - 1;
    u32 length;
    int file;

    out = append_text(out, end, "\r\n");
    *out = 0;
    length = (u32)(out - g_line);
    file = open_log("ab");
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_write_raw(file, g_line, length);
    (void)bda_fs_close_raw(file);
}

static void log_text(const char *text) {
    write_line(append_text(g_line, g_line + sizeof(g_line) - 1, text));
}

static void log_hex(const char *label, u32 value) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, value);
    write_line(out);
}

#if defined(RECORD_STREAM_PROBE_V2) || defined(RECORD_STREAM_PROBE_V3) || \
    defined(RECORD_STREAM_PROBE_V4) || defined(RECORD_STREAM_PROBE_V5) || \
    defined(RECORD_STREAM_PROBE_V6) || defined(RECORD_STREAM_PROBE_V7) || \
    defined(RECORD_STREAM_PROBE_V8) || defined(RECORD_STREAM_PROBE_V9) || \
    defined(RECORD_STREAM_PROBE_V10) || defined(RECORD_STREAM_PROBE_V11)
static void log_code_word(const char *label, u32 address, u32 word) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, address);
    out = append_text(out, end, " WORD=");
    out = append_hex32(out, end, word);
    write_line(out);
}

static void log_code_window(const char *label, u32 center) {
    u32 address;

    for (address = center - 0x20u; address <= center + 0x20u; address += 4u) {
        log_code_word(label, address, *(const volatile u32 *)address);
    }
}

static int is_stack_frame_entry(u32 word) {
    return (word & 0xffff0000u) == 0x27bd0000u &&
        (word & 0x00008000u) != 0u;
}

#ifdef RECORD_STREAM_PROBE_V3
static void analyze_capture_layout(
    u32 playback_open,
    u32 ready_address,
    u32 old_open_guess
) {
    u32 address;
    u32 nearest = 0u;
    u32 prologue_count = 0u;

    for (address = playback_open + 4u;
         address < ready_address;
         address += 4u) {
        const volatile u32 *code = (const volatile u32 *)address;

        if (is_stack_frame_entry(code[0])) {
            u32 index;

            ++prologue_count;
            if (address <= old_open_guess) {
                nearest = address;
            }
            for (index = 0u; index < 6u; ++index) {
                log_code_word(
                    "ENTRY WORD ADDRESS=",
                    address + index * 4u,
                    code[index]
                );
            }
        }
    }
    log_hex("PROLOGUE COUNT=", prologue_count);
    log_hex("NEAREST BEFORE OLD GUESS=", nearest);

    if (nearest != 0u) {
        for (address = nearest; address < nearest + 0xc0u; address += 4u) {
            log_code_word(
                "CANDIDATE WORD ADDRESS=",
                address,
                *(const volatile u32 *)address
            );
        }
        for (address = nearest; address < ready_address; address += 4u) {
            if (*(const volatile u32 *)address == 0x03e00008u) {
                log_hex("JR RA ADDRESS=", address);
            }
        }
    }
}
#endif

#if defined(RECORD_STREAM_PROBE_V5) || defined(RECORD_STREAM_PROBE_V7) || \
    defined(RECORD_STREAM_PROBE_V8) || defined(RECORD_STREAM_PROBE_V9) || \
    defined(RECORD_STREAM_PROBE_V10) || defined(RECORD_STREAM_PROBE_V11)
static void dump_code_range(const char *label, u32 start, u32 end) {
    u32 address;

    for (address = start; address < end; address += 4u) {
        log_code_word(label, address, *(const volatile u32 *)address);
    }
}

static u32 find_previous_prologue(u32 callsite, u32 scan_start) {
    u32 lower = callsite > 0x400u ? callsite - 0x400u : scan_start;
    u32 address = callsite;

    if (lower < scan_start) {
        lower = scan_start;
    }
    for (;;) {
        if (is_stack_frame_entry(*(const volatile u32 *)address)) {
            return address;
        }
        if (address < lower + 4u) {
            break;
        }
        address -= 4u;
    }
    return 0u;
}

static u32 direct_jal_word(u32 target) {
    return 0x0c000000u | ((target >> 2) & 0x03ffffffu);
}

static void scan_direct_callers(
    const char *label,
    u32 scan_start,
    u32 scan_end,
    u32 target
) {
    u32 expected = direct_jal_word(target);
    u32 address;
    u32 matches = 0u;

    log_text(label);
    log_hex("TARGET ADDRESS=", target);
    log_hex("JAL WORD=", expected);
    for (address = scan_start; address < scan_end; address += 4u) {
        if (*(const volatile u32 *)address == expected) {
            ++matches;
            log_hex("CALL ADDRESS=", address);
            log_hex(
                "CALL OWNER PROLOGUE=",
                find_previous_prologue(address, scan_start)
            );
            log_code_window("CALL WORD ADDRESS=", address);
        }
    }
    log_hex("CALL MATCHES=", matches);
}

#if defined(RECORD_STREAM_PROBE_V7) || defined(RECORD_STREAM_PROBE_V8) || \
    defined(RECORD_STREAM_PROBE_V9) || defined(RECORD_STREAM_PROBE_V10) || \
    defined(RECORD_STREAM_PROBE_V11)
static u32 decode_direct_jal_target(u32 callsite, u32 word) {
    return ((callsite + 4u) & 0xf0000000u) |
        ((word & 0x03ffffffu) << 2);
}

static int is_direct_jal(u32 word) {
    return (word & 0xfc000000u) == 0x0c000000u;
}

static int is_indirect_jalr(u32 word) {
    return (word & 0xfc00003fu) == 0x00000009u;
}

static u32 find_previous_prologue_v7(u32 callsite, u32 scan_start) {
    u32 lower = callsite > 0x1000u ? callsite - 0x1000u : scan_start;
    u32 address = callsite;

    if (lower < scan_start) {
        lower = scan_start;
    }
    for (;;) {
        if (is_stack_frame_entry(*(const volatile u32 *)address)) {
            return address;
        }
        if (address < lower + 4u) {
            break;
        }
        address -= 4u;
    }
    return 0u;
}

static u32 find_direct_caller_owner_v7(
    u32 scan_start,
    u32 scan_end,
    u32 target,
    u32 *match_count
) {
    u32 expected = direct_jal_word(target);
    u32 address;
    u32 owner = 0u;
    u32 count = 0u;

    for (address = scan_start; address < scan_end; address += 4u) {
        if (*(const volatile u32 *)address == expected) {
            ++count;
            if (owner == 0u) {
                owner = find_previous_prologue_v7(address, scan_start);
            }
        }
    }
    *match_count = count;
    return owner;
}

static void log_call_record_v7(
    const char *label,
    u32 address,
    u32 target,
    u32 owner,
    u32 delay_word
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, label);
    out = append_hex32(out, end, address);
    out = append_text(out, end, " TARGET=");
    out = append_hex32(out, end, target);
    out = append_text(out, end, " OWNER=");
    out = append_hex32(out, end, owner);
    out = append_text(out, end, " DELAY=");
    out = append_hex32(out, end, delay_word);
    write_line(out);
}

static void scan_manager_range_v7(
    const char *label,
    u32 start,
    u32 end,
    u32 driver_start,
    u32 driver_end
) {
    u32 address;
    u32 entry_count = 0u;
    u32 direct_count = 0u;
    u32 audio_count = 0u;
    u32 indirect_count = 0u;

    log_text(label);
    log_hex("RANGE START=", start);
    log_hex("RANGE END=", end);
    for (address = start; address < end; address += 4u) {
        u32 word = *(const volatile u32 *)address;

        if (is_stack_frame_entry(word)) {
            u32 index;

            ++entry_count;
            for (index = 0u; index < 6u; ++index) {
                log_code_word(
                    "MANAGER ENTRY WORD ADDRESS=",
                    address + index * 4u,
                    *(const volatile u32 *)(address + index * 4u)
                );
            }
        }
        if (is_direct_jal(word)) {
            u32 target = decode_direct_jal_target(address, word);
            u32 owner = find_previous_prologue_v7(address, start);

            ++direct_count;
            log_call_record_v7(
                "MANAGER JAL ADDRESS=",
                address,
                target,
                owner,
                *(const volatile u32 *)(address + 4u)
            );
            if (target >= driver_start && target < driver_end) {
                ++audio_count;
                log_code_window("AUDIO CALL WORD ADDRESS=", address);
                log_code_window("AUDIO TARGET WORD ADDRESS=", target);
            }
        } else if (is_indirect_jalr(word)) {
            ++indirect_count;
            log_call_record_v7(
                "MANAGER JALR ADDRESS=",
                address,
                word,
                find_previous_prologue_v7(address, start),
                *(const volatile u32 *)(address + 4u)
            );
            log_code_window("JALR WORD ADDRESS=", address);
        }
    }
    log_hex("MANAGER ENTRY COUNT=", entry_count);
    log_hex("MANAGER JAL COUNT=", direct_count);
    log_hex("AUDIO TARGET JAL COUNT=", audio_count);
    log_hex("MANAGER JALR COUNT=", indirect_count);
}

#if defined(RECORD_STREAM_PROBE_V9) || defined(RECORD_STREAM_PROBE_V10)
static int is_capture_state_reference_v9(u32 word) {
    u32 opcode = word >> 26;
    u32 offset = word & 0xffffu;

    if (opcode < 0x20u || opcode > 0x2bu) {
        return 0;
    }
    return offset == 0xd4f0u || offset == 0xd498u ||
        offset == 0xd4a8u || offset == 0xd4ccu ||
        offset == 0xd4d8u || offset == 0xd500u ||
        offset == 0xd510u || offset == 0xd520u ||
        offset == 0xd524u || offset == 0xd530u ||
        offset == 0xd540u;
}

#ifdef RECORD_STREAM_PROBE_V9
static void scan_capture_state_references_v9(u32 start, u32 end) {
    u32 address;
    u32 count = 0u;

    log_hex("STATE SCAN START=", start);
    log_hex("STATE SCAN END=", end);
    for (address = start; address < end; address += 4u) {
        u32 word = *(const volatile u32 *)address;

        if (is_capture_state_reference_v9(word)) {
            ++count;
            log_code_word("STATE REF ADDRESS=", address, word);
            log_hex(
                "STATE REF OWNER=",
                find_previous_prologue_v7(address, start)
            );
            log_code_window("STATE REF WORD ADDRESS=", address);
        }
    }
    log_hex("STATE REF COUNT=", count);
}
#endif

#ifdef RECORD_STREAM_PROBE_V10
static void log_capture_state_reference_v10(
    u32 address,
    u32 word,
    u32 owner
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "STATE REF A=");
    out = append_hex32(out, end, address);
    out = append_text(out, end, " W=");
    out = append_hex32(out, end, word);
    out = append_text(out, end, " O=");
    out = append_hex32(out, end, owner);
    out = append_text(out, end, " P=");
    out = append_hex32(out, end, *(const volatile u32 *)(address - 4u));
    out = append_text(out, end, " N=");
    out = append_hex32(out, end, *(const volatile u32 *)(address + 4u));
    write_line(out);
}

static void scan_capture_state_references_v10(u32 start, u32 end) {
    u32 address;
    u32 count = 0u;

    log_hex("COMPACT STATE SCAN START=", start);
    log_hex("COMPACT STATE SCAN END=", end);
    for (address = start; address < end; address += 4u) {
        u32 word = *(const volatile u32 *)address;

        if (is_capture_state_reference_v9(word)) {
            ++count;
            log_capture_state_reference_v10(
                address,
                word,
                find_previous_prologue_v7(address, start)
            );
        }
    }
    log_hex("COMPACT STATE REF COUNT=", count);
}
#endif
#endif

#ifdef RECORD_STREAM_PROBE_V11
static void scan_direct_callers_compact_v11(
    const char *label,
    u32 scan_start,
    u32 scan_end,
    u32 target
) {
    u32 expected = direct_jal_word(target);
    u32 address;
    u32 matches = 0u;

    log_text(label);
    log_hex("TARGET=", target);
    for (address = scan_start; address < scan_end; address += 4u) {
        if (*(const volatile u32 *)address == expected) {
            ++matches;
            log_call_record_v7(
                "CALL A=",
                address,
                target,
                find_previous_prologue_v7(address, scan_start),
                *(const volatile u32 *)(address + 4u)
            );
        }
    }
    log_hex("COMPACT CALL MATCHES=", matches);
}

static void log_pointer_reference_v11(
    u32 address,
    u32 word,
    u32 owner
) {
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    out = append_text(out, end, "CALLBACK PTR A=");
    out = append_hex32(out, end, address);
    out = append_text(out, end, " W=");
    out = append_hex32(out, end, word);
    out = append_text(out, end, " O=");
    out = append_hex32(out, end, owner);
    out = append_text(out, end, " P=");
    out = append_hex32(out, end, *(const volatile u32 *)(address - 4u));
    out = append_text(out, end, " N=");
    out = append_hex32(out, end, *(const volatile u32 *)(address + 4u));
    write_line(out);
}

static int is_callback_pointer_reference_v11(
    u32 address,
    u32 word,
    u32 target
) {
    u32 opcode = word >> 26;
    u32 previous = *(const volatile u32 *)(address - 4u);
    u32 previous_opcode = previous >> 26;
    u32 source_register = (word >> 21) & 0x1fu;
    u32 previous_target_register = (previous >> 16) & 0x1fu;
    u32 expected_high;

    if (word == target) {
        return 1;
    }
    if ((word & 0xffffu) != (target & 0xffffu) ||
        previous_opcode != 0x0fu ||
        source_register != previous_target_register) {
        return 0;
    }
    if (opcode == 0x09u) {
        expected_high = ((target + 0x8000u) >> 16) & 0xffffu;
    } else if (opcode == 0x0du) {
        expected_high = (target >> 16) & 0xffffu;
    } else {
        return 0;
    }
    return (previous & 0xffffu) == expected_high;
}

static void scan_callback_pointer_references_v11(
    u32 scan_start,
    u32 scan_end,
    u32 target
) {
    u32 address;
    u32 matches = 0u;

    log_hex("CALLBACK PTR TARGET=", target);
    for (address = scan_start + 4u; address < scan_end - 4u; address += 4u) {
        u32 word = *(const volatile u32 *)address;

        if (is_callback_pointer_reference_v11(address, word, target)) {
            ++matches;
            log_pointer_reference_v11(
                address,
                word,
                find_previous_prologue_v7(address, scan_start)
            );
        }
    }
    log_hex("CALLBACK PTR MATCHES=", matches);
}
#endif
#endif
#endif
#endif

#if defined(RECORD_STREAM_PROBE_V2) || defined(RECORD_STREAM_PROBE_V4) || \
    defined(RECORD_STREAM_PROBE_V6)
#ifdef RECORD_STREAM_PROBE_V2
static u32 resolve_capture_open(u32 ready_address, u32 *match_count) {
    const u32 shift_a1_to_s8 = 0x00052e00u;
    const u32 shift_a2_to_s8 = 0x00063600u;
    u32 address;
    u32 found = 0u;
    u32 count = 0u;

    for (address = ready_address - 0x800u;
         address < ready_address - 0x20u;
         address += 4u) {
        const volatile u32 *code = (const volatile u32 *)address;

        if (is_stack_frame_entry(code[0]) &&
            code[1] == shift_a1_to_s8 &&
            code[2] == shift_a2_to_s8) {
            found = address;
            ++count;
        }
    }
    *match_count = count;
    return count == 1u ? found : 0u;
}
#endif

#if defined(RECORD_STREAM_PROBE_V4) || defined(RECORD_STREAM_PROBE_V6)
static u32 resolve_capture_open_v4(
    u32 playback_open,
    u32 ready_address,
    u32 *match_count
) {
    u32 address;
    u32 found = 0u;
    u32 count = 0u;

    for (address = playback_open + 4u;
         address < ready_address;
         address += 4u) {
        const volatile u32 *code = (const volatile u32 *)address;

        if (code[0] == 0x27bdffe0u &&
            code[1] == 0xafbf001cu &&
            code[2] == 0x0c0669f2u &&
            code[3] == 0xafb00018u &&
            code[4] == 0x0c066d1au &&
            code[5] == 0x00000000u &&
            code[0x1b4u / 4u] == 0x03e00008u &&
            code[0x1bcu / 4u] == 0x27bdffe8u) {
            found = address;
            ++count;
        }
    }
    *match_count = count;
    return count == 1u ? found : 0u;
}
#endif

#ifdef RECORD_STREAM_PROBE_V6
static u32 resolve_capture_config_wrapper_v6(
    u32 scan_start,
    u32 scan_end,
    u32 config_target,
    u32 *match_count
) {
    u32 expected_jal =
        0x0c000000u | ((config_target >> 2) & 0x03ffffffu);
    u32 address;
    u32 found = 0u;
    u32 count = 0u;

    for (address = scan_start + 0x44u;
         address < scan_end;
         address += 4u) {
        const volatile u32 *owner;

        if (*(const volatile u32 *)address != expected_jal) {
            continue;
        }
        owner = (const volatile u32 *)(address - 0x44u);
        if (owner[0] == 0x27bdffe8u &&
            owner[9] == 0x3c048030u &&
            owner[10] == 0x2484f360u &&
            owner[11] == 0x3c01804cu &&
            owner[12] == 0xac301840u &&
            owner[13] == 0xafbf0014u &&
            owner[14] == 0x0c001463u &&
            owner[15] == 0x3210ffffu &&
            owner[16] == 0x02002821u &&
            owner[17] == expected_jal &&
            owner[18] == 0x24040003u) {
            found = address - 0x44u;
            ++count;
        }
    }
    *match_count = count;
    return count == 1u ? found : 0u;
}

static int capture_init_v6(void) {
    typedef int (*capture_init_fn)(void);
    return ((capture_init_fn)g_capture_open_address)();
}

static int capture_config_v6(u32 sample_rate) {
    typedef int (*capture_config_fn)(u32);
    return ((capture_config_fn)g_capture_config_wrapper_address)(sample_rate);
}
#endif

static u32 resolve_capture_read(u32 guess, u32 *match_count) {
    u32 address;
    u32 found = 0u;
    u32 count = 0u;

    for (address = guess - 0x20u; address <= guess + 0x20u; address += 4u) {
        const volatile u32 *code = (const volatile u32 *)address;

        if (code[0] == BDA_C200_RECORD_READ_SIGNATURE0_LIKE &&
            code[1] == BDA_C200_RECORD_READ_SIGNATURE1_LIKE) {
            found = address;
            ++count;
        }
    }
    *match_count = count;
    return count == 1u ? found : 0u;
}

static int capture_ready(void) {
    typedef int (*capture_ready_fn)(void);
    return ((capture_ready_fn)g_capture_ready_address)();
}

static void capture_open(void) {
#if defined(RECORD_STREAM_PROBE_V4) || defined(RECORD_STREAM_PROBE_V6)
    typedef void (*capture_open_fn)(void);
    ((capture_open_fn)g_capture_open_address)();
#else
    typedef void (*capture_open_fn)(u32, u32, u32);
    ((capture_open_fn)g_capture_open_address)(16000u, 16u, 1u);
#endif
}

static int capture_read(void *buffer, u32 bytes) {
    typedef int (*capture_read_fn)(void *, u32);
    return ((capture_read_fn)g_capture_read_address)(buffer, bytes);
}
#else
static int capture_ready(void) {
    return bda_c200_record_stream_ready_like();
}

static void capture_open(void) {
    bda_c200_record_stream_open_like(16000u, 16u, 1u);
}

static int capture_read(void *buffer, u32 bytes) {
    return bda_c200_record_stream_read_like(buffer, bytes);
}
#endif

static int wait_capture_ready(u32 *polls_out, u32 *ticks_out) {
    u32 start = bda_gui_tick_count_25ms_like();
    u32 now = start;
    u32 polls = 0;

    while (!capture_ready() &&
           bda_gui_tick_elapsed_25ms_like(start, now) < READY_TIMEOUT_TICKS &&
           polls < READY_POLL_LIMIT) {
        bda_sys_delay_like(1u);
        now = bda_gui_tick_count_25ms_like();
        ++polls;
    }
    *polls_out = polls;
    *ticks_out = bda_gui_tick_elapsed_25ms_like(start, now);
    return capture_ready() != 0;
}

static void log_block_stats(
    u32 block,
    int got,
    u32 polls,
    u32 ticks,
    int raw_written
) {
    s32 minimum = 32767;
    s32 maximum = -32768;
    u32 peak = 0;
    u32 sum_abs = 0;
    u32 nonzero = 0;
    u32 samples = got > 0 ? (u32)got / 2u : 0;
    u32 i;
    char *out = g_line;
    char *end = g_line + sizeof(g_line) - 1;

    if (samples > RECORD_BLOCK_SAMPLES) {
        samples = RECORD_BLOCK_SAMPLES;
    }
    for (i = 0; i < samples; ++i) {
        s32 sample = g_pcm[i];
        u32 magnitude = sample < 0 ? (u32)(-sample) : (u32)sample;

        if (sample < minimum) {
            minimum = sample;
        }
        if (sample > maximum) {
            maximum = sample;
        }
        if (magnitude > peak) {
            peak = magnitude;
        }
        sum_abs += magnitude;
        if (sample != 0) {
            ++nonzero;
        }
    }

    out = append_text(out, end, "BLOCK=");
    out = append_u32(out, end, block);
    out = append_text(out, end, " GOT=");
    out = append_s32(out, end, got);
    out = append_text(out, end, " POLLS=");
    out = append_u32(out, end, polls);
    out = append_text(out, end, " TICKS=");
    out = append_u32(out, end, ticks);
    out = append_text(out, end, " MIN=");
    out = append_s32(out, end, minimum);
    out = append_text(out, end, " MAX=");
    out = append_s32(out, end, maximum);
    out = append_text(out, end, " PEAK=");
    out = append_u32(out, end, peak);
    out = append_text(out, end, " AVGABS=");
    out = append_u32(out, end, samples ? sum_abs / samples : 0u);
    out = append_text(out, end, " NZ=");
    out = append_u32(out, end, nonzero);
    out = append_text(out, end, " RAW=");
    out = append_s32(out, end, raw_written);
    write_line(out);
}

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    const volatile u32 *open_code;
    const volatile u32 *ready_code;
    const volatile u32 *read_code;
#if defined(RECORD_STREAM_PROBE_V2) || defined(RECORD_STREAM_PROBE_V4) || \
    defined(RECORD_STREAM_PROBE_V6)
    u32 open_matches;
    u32 read_matches;
#ifdef RECORD_STREAM_PROBE_V6
    u32 config_matches;
#endif
#endif
    int raw_file = 0;
    int capture_started = 0;
    int failures = 0;
    u32 block;

    reset_log();
#if defined(RECORD_STREAM_PROBE_V13)
    log_text("START RECORD STREAM HARDWARE PROBE V13");
#elif defined(RECORD_STREAM_PROBE_V12)
    log_text("START RECORD STREAM HARDWARE PROBE V12");
#elif defined(RECORD_STREAM_PROBE_V11)
    log_text("START RECORD STREAM HARDWARE PROBE V11");
#elif defined(RECORD_STREAM_PROBE_V10)
    log_text("START RECORD STREAM HARDWARE PROBE V10");
#elif defined(RECORD_STREAM_PROBE_V9)
    log_text("START RECORD STREAM HARDWARE PROBE V9");
#elif defined(RECORD_STREAM_PROBE_V8)
    log_text("START RECORD STREAM HARDWARE PROBE V8");
#elif defined(RECORD_STREAM_PROBE_V7)
    log_text("START RECORD STREAM HARDWARE PROBE V7");
#elif defined(RECORD_STREAM_PROBE_V6)
    log_text("START RECORD STREAM HARDWARE PROBE V6");
#elif defined(RECORD_STREAM_PROBE_V5)
    log_text("START RECORD STREAM HARDWARE PROBE V5");
#elif defined(RECORD_STREAM_PROBE_V4)
    log_text("START RECORD STREAM HARDWARE PROBE V4");
#elif defined(RECORD_STREAM_PROBE_V3)
    log_text("START RECORD STREAM HARDWARE PROBE V3");
#elif defined(RECORD_STREAM_PROBE_V2)
    log_text("START RECORD STREAM HARDWARE PROBE V2");
#else
    log_text("START RECORD STREAM HARDWARE PROBE V1");
#endif
    log_hex("OPEN ADDRESS=", bda_c200_record_open_address_like());
    log_hex("READY ADDRESS=", bda_c200_record_ready_address_like());
    log_hex("READ ADDRESS=", bda_c200_record_read_address_like());
    open_code = (const volatile u32 *)bda_c200_record_open_address_like();
    ready_code = (const volatile u32 *)bda_c200_record_ready_address_like();
    read_code = (const volatile u32 *)bda_c200_record_read_address_like();
    log_hex("OPEN SIG0=", open_code[0]);
    log_hex("OPEN SIG1=", open_code[1]);
    log_hex("READY SIG0=", ready_code[0]);
    log_hex("READY SIG1=", ready_code[1]);
    log_hex("READ SIG0=", read_code[0]);
    log_hex("READ SIG1=", read_code[1]);

#ifdef RECORD_STREAM_PROBE_V13
    {
        typedef int (*capture_init_fn)(void);
        typedef int (*capture_read_fn)(void *, u32);
        typedef void (*capture_stop_fn)(void);
        u32 init_target = bda_c200_record_open_address_like() - 0x30u;
        u32 read_target = bda_c200_record_read_address_like() - 4u;
        u32 stop_target = init_target - 0x2e0u;
        const volatile u32 *init_entry =
            (const volatile u32 *)init_target;
        const volatile u32 *read_entry =
            (const volatile u32 *)read_target;
        const volatile u32 *stop_entry =
            (const volatile u32 *)stop_target;
        u32 read_bytes;
        u32 blocks_per_cycle;
        u32 cycle_count;
        u32 cycle;

        read_bytes = 0x400u;
        blocks_per_cycle = 8u;
        cycle_count = 2u;
        log_text("PATH=RESTART + 1024-BYTE BLOCKING READ");
        log_hex("INIT TARGET=", init_target);
        log_hex("INIT SIG0=", init_entry[0]);
        log_hex("INIT SIG1=", init_entry[1]);
        log_hex("READ TARGET=", read_target);
        log_hex("READ SIG0 TRUE=", read_entry[0]);
        log_hex("READ SIG1 TRUE=", read_entry[1]);
        log_hex("STOP TARGET=", stop_target);
        log_hex("STOP SIG0=", stop_entry[0]);
        log_hex("STOP SIG1=", stop_entry[1]);
        if (init_entry[0] != 0x27bdffe0u ||
            init_entry[1] != 0xafbf001cu ||
            read_entry[0] != BDA_C200_RECORD_READ_SIGNATURE0_LIKE ||
            read_entry[1] != BDA_C200_RECORD_READ_SIGNATURE1_LIKE ||
            stop_entry[0] != 0x3c03b001u ||
            stop_entry[1] != 0x34630080u) {
            log_text("TRUE HARDWARE PRIME SIGNATURE FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }
        log_text("TRUE HARDWARE PRIME SIGNATURE PASS");

        raw_file = open_raw();
        log_hex("RAW FILE=", (u32)raw_file);
        log_hex("READ BYTES=", read_bytes);
        log_hex("BLOCKS PER CYCLE=", blocks_per_cycle);
        log_hex("CYCLE COUNT=", cycle_count);

        for (cycle = 0u; failures == 0 && cycle < cycle_count; ++cycle) {
            int init_return;

            capture_started = 0;
            log_hex("CYCLE BEGIN=", cycle);
            log_text("BEFORE CAPTURE INIT");
            init_return = ((capture_init_fn)init_target)();
            log_hex("CAPTURE INIT RETURN=", (u32)init_return);
            if (init_return != 0) {
                ++failures;
            } else {
                capture_started = 1;
            }
            log_hex("QUEUE FREE BEFORE READ=", *(const volatile u32 *)0x8058d520u);
            log_hex("QUEUE DONE BEFORE READ=", *(const volatile u32 *)0x8058d530u);
            log_hex("QUEUE ACTIVE BEFORE READ=", *(const volatile u32 *)0x8058d540u);

            for (block = 0u;
                 failures == 0 && block < blocks_per_cycle;
                 ++block) {
                u32 start_tick = bda_gui_tick_count_25ms_like();
                u32 elapsed;
                u32 sequence = cycle * blocks_per_cycle + block;
                int got;
                int raw_written = -1;

                log_hex("BEFORE BLOCKING READ BLOCK=", sequence);
                got = ((capture_read_fn)read_target)(g_pcm, read_bytes);
                elapsed = bda_gui_tick_elapsed_25ms_like(
                    start_tick,
                    bda_gui_tick_count_25ms_like()
                );
                log_hex("AFTER BLOCKING READ BLOCK=", sequence);
                if (bda_fs_file_is_valid(raw_file) && got > 0) {
                    raw_written = bda_fs_write_raw(
                        raw_file,
                        g_pcm,
                        (u32)got
                    );
                }
                log_block_stats(
                    sequence,
                    got,
                    0u,
                    elapsed,
                    raw_written
                );
                if (got != (int)read_bytes) {
                    ++failures;
                }
            }

            log_hex("QUEUE FREE AFTER READ=", *(const volatile u32 *)0x8058d520u);
            log_hex("QUEUE DONE AFTER READ=", *(const volatile u32 *)0x8058d530u);
            log_hex("QUEUE ACTIVE AFTER READ=", *(const volatile u32 *)0x8058d540u);
            if (capture_started) {
                log_text("BEFORE CAPTURE-SPECIFIC STOP");
                ((capture_stop_fn)stop_target)();
                capture_started = 0;
                log_text("CAPTURE-SPECIFIC STOP RETURNED");
            }
            log_hex("CYCLE END=", cycle);
        }
        if (bda_fs_file_is_valid(raw_file)) {
            log_text("BEFORE RAW CLOSE");
            (void)bda_fs_close_raw(raw_file);
            log_text("RAW CLOSE RETURNED");
        }
    }
    log_hex("FAILURES=", (u32)failures);
    log_text(failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END RECORD STREAM HARDWARE PROBE V13");
    return failures ? 1 : 0;
#elif defined(RECORD_STREAM_PROBE_V12)
    {
        typedef int (*capture_init_fn)(void);
        typedef int (*capture_read_fn)(void *, u32);
        typedef void (*capture_stop_fn)(void);
        u32 init_target = bda_c200_record_open_address_like() - 0x30u;
        u32 read_target = bda_c200_record_read_address_like() - 4u;
        u32 stop_target = init_target - 0x2e0u;
        const volatile u32 *init_entry =
            (const volatile u32 *)init_target;
        const volatile u32 *read_entry =
            (const volatile u32 *)read_target;
        const volatile u32 *stop_entry =
            (const volatile u32 *)stop_target;
        int init_return;

        log_text("PATH=INIT THEN BLOCKING READ; READ PRIMES DMA");
        log_hex("INIT TARGET=", init_target);
        log_hex("INIT SIG0=", init_entry[0]);
        log_hex("INIT SIG1=", init_entry[1]);
        log_hex("READ TARGET=", read_target);
        log_hex("READ SIG0 TRUE=", read_entry[0]);
        log_hex("READ SIG1 TRUE=", read_entry[1]);
        log_hex("STOP TARGET=", stop_target);
        log_hex("STOP SIG0=", stop_entry[0]);
        log_hex("STOP SIG1=", stop_entry[1]);
        if (init_entry[0] != 0x27bdffe0u ||
            init_entry[1] != 0xafbf001cu ||
            read_entry[0] != BDA_C200_RECORD_READ_SIGNATURE0_LIKE ||
            read_entry[1] != BDA_C200_RECORD_READ_SIGNATURE1_LIKE ||
            stop_entry[0] != 0x3c03b001u ||
            stop_entry[1] != 0x34630080u) {
            log_text("TRUE HARDWARE PRIME SIGNATURE FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }
        log_text("TRUE HARDWARE PRIME SIGNATURE PASS");

        raw_file = open_raw();
        log_hex("RAW FILE=", (u32)raw_file);
        log_text("BEFORE CAPTURE INIT");
        init_return = ((capture_init_fn)init_target)();
        log_hex("CAPTURE INIT RETURN=", (u32)init_return);
        if (init_return != 0) {
            ++failures;
        } else {
            capture_started = 1;
        }
        log_hex("QUEUE FREE BEFORE READ=", *(const volatile u32 *)0x8058d520u);
        log_hex("QUEUE DONE BEFORE READ=", *(const volatile u32 *)0x8058d530u);
        log_hex("QUEUE ACTIVE BEFORE READ=", *(const volatile u32 *)0x8058d540u);

        for (block = 0u; failures == 0 && block < 4u; ++block) {
            u32 start_tick = bda_gui_tick_count_25ms_like();
            u32 elapsed;
            int got;
            int raw_written = -1;

            log_hex("BEFORE BLOCKING READ BLOCK=", block);
            got = ((capture_read_fn)read_target)(g_pcm, RECORD_BLOCK_BYTES);
            elapsed = bda_gui_tick_elapsed_25ms_like(
                start_tick,
                bda_gui_tick_count_25ms_like()
            );
            log_hex("AFTER BLOCKING READ BLOCK=", block);
            if (bda_fs_file_is_valid(raw_file) && got > 0) {
                raw_written = bda_fs_write_raw(
                    raw_file,
                    g_pcm,
                    (u32)got
                );
            }
            log_block_stats(block, got, 0u, elapsed, raw_written);
            log_hex("QUEUE FREE AFTER READ=", *(const volatile u32 *)0x8058d520u);
            log_hex("QUEUE DONE AFTER READ=", *(const volatile u32 *)0x8058d530u);
            log_hex("QUEUE ACTIVE AFTER READ=", *(const volatile u32 *)0x8058d540u);
            if (got != (int)RECORD_BLOCK_BYTES) {
                ++failures;
            }
        }

        if (capture_started) {
            log_text("BEFORE CAPTURE-SPECIFIC STOP");
            ((capture_stop_fn)stop_target)();
            log_text("CAPTURE-SPECIFIC STOP RETURNED");
        }
        if (bda_fs_file_is_valid(raw_file)) {
            log_text("BEFORE RAW CLOSE");
            (void)bda_fs_close_raw(raw_file);
            log_text("RAW CLOSE RETURNED");
        }
    }
    log_hex("FAILURES=", (u32)failures);
    log_text(failures ? "RESULT=FAIL" : "RESULT=PASS");
    log_text("END RECORD STREAM HARDWARE PROBE V12");
    return failures ? 1 : 0;
#elif defined(RECORD_STREAM_PROBE_V11)
    {
        u32 scan_start = (u32)bda_api(
            bda_sys_table(), BDA_SYS_SESSION_OPEN_LIKE
        );
        u32 playback_open =
            (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE);
        u32 ready_target = bda_c200_record_ready_address_like();
        u32 read_target = bda_c200_record_read_address_like() - 4u;
        u32 read_matches = 0u;
        u32 worker_owner = find_direct_caller_owner_v7(
            scan_start, playback_open, read_target, &read_matches
        );
        u32 wait_call_a = worker_owner + 0x28cu;
        u32 wait_call_b = worker_owner + 0x2f8u;
        u32 wait_call_a_again = worker_owner + 0x304u;
        u32 wait_target_a = 0u;
        u32 wait_target_b = 0u;
        u32 callback_target = ready_target + 0x518u;
        u32 callback_end = callback_target + 0x228u;
        u32 scan_end = ready_target + 0x2000u;
        const volatile u32 *read_entry =
            (const volatile u32 *)read_target;
        const volatile u32 *callback_code =
            (const volatile u32 *)callback_target;

        log_hex("CALL SCAN START=", scan_start);
        log_hex("CALL SCAN END=", scan_end);
        log_hex("PLAYBACK OPEN ADDRESS=", playback_open);
        log_hex("READ TARGET=", read_target);
        log_hex("READ MATCHES=", read_matches);
        log_hex("WORKER OWNER=", worker_owner);
        if (worker_owner != 0u &&
            is_direct_jal(*(const volatile u32 *)wait_call_a) &&
            is_direct_jal(*(const volatile u32 *)wait_call_b) &&
            is_direct_jal(*(const volatile u32 *)wait_call_a_again)) {
            wait_target_a = decode_direct_jal_target(
                wait_call_a,
                *(const volatile u32 *)wait_call_a
            );
            wait_target_b = decode_direct_jal_target(
                wait_call_b,
                *(const volatile u32 *)wait_call_b
            );
        }
        log_hex("WAIT CALL A=", wait_call_a);
        log_hex("WAIT TARGET A=", wait_target_a);
        log_hex("WAIT CALL B=", wait_call_b);
        log_hex("WAIT TARGET B=", wait_target_b);
        log_hex("WAIT CALL A AGAIN=", wait_call_a_again);
        log_hex("CAPTURE CALLBACK=", callback_target);
        log_hex("CAPTURE CALLBACK END=", callback_end);
        log_hex("CALLBACK SIG0=", callback_code[0]);
        log_hex("CALLBACK END SIG0=", *(const volatile u32 *)callback_end);

        if (scan_start < 0x80000000u || scan_start >= playback_open ||
            scan_end <= ready_target || scan_end >= 0x80200000u ||
            read_matches < 1u || worker_owner == 0u ||
            wait_target_a < scan_start || wait_target_a >= scan_end ||
            wait_target_b < scan_start || wait_target_b >= scan_end ||
            wait_target_a != decode_direct_jal_target(
                wait_call_a_again,
                *(const volatile u32 *)wait_call_a_again
            ) ||
            ready_code[0] != BDA_C200_RECORD_READY_SIGNATURE0_LIKE ||
            ready_code[1] != BDA_C200_RECORD_READY_SIGNATURE1_LIKE ||
            read_entry[0] != BDA_C200_RECORD_READ_SIGNATURE0_LIKE ||
            read_entry[1] != BDA_C200_RECORD_READ_SIGNATURE1_LIKE ||
            !is_stack_frame_entry(callback_code[0]) ||
            !is_stack_frame_entry(*(const volatile u32 *)callback_end)) {
            log_text("READ-ONLY MAP GUARD FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }

        dump_code_range(
            "WAIT CODE A=",
            wait_target_a - 0x20u,
            wait_target_b + 0xa0u
        );
        dump_code_range(
            "CAPTURE CALLBACK CODE A=",
            callback_target,
            callback_end
        );
        scan_direct_callers_compact_v11(
            "CALLERS WAIT TARGET A",
            scan_start,
            scan_end,
            wait_target_a
        );
        scan_direct_callers_compact_v11(
            "CALLERS WAIT TARGET B",
            scan_start,
            scan_end,
            wait_target_b
        );
        scan_direct_callers_compact_v11(
            "DIRECT CALLERS CAPTURE CALLBACK",
            scan_start,
            scan_end,
            callback_target
        );
        scan_callback_pointer_references_v11(
            scan_start,
            scan_end,
            callback_target
        );
    }
    log_text("DIAGNOSTIC ONLY; NO AUDIO CALLS");
    log_text("RESULT=MAP_ONLY");
    log_text("END RECORD STREAM HARDWARE PROBE V11");
    return 0;
#elif defined(RECORD_STREAM_PROBE_V10)
    {
        u32 scan_start = (u32)bda_api(
            bda_sys_table(), BDA_SYS_SESSION_OPEN_LIKE
        );
        u32 playback_open =
            (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE);
        u32 ready_target = bda_c200_record_ready_address_like();
        u32 read_target = bda_c200_record_read_address_like() - 4u;
        u32 driver_start = read_target - 0x2000u;
        u32 driver_end = ready_target + 0x2000u;
        const volatile u32 *read_entry =
            (const volatile u32 *)read_target;

        log_hex("CALL SCAN START=", scan_start);
        log_hex("PLAYBACK OPEN ADDRESS=", playback_open);
        log_hex("READY TARGET=", ready_target);
        log_hex("READ TARGET=", read_target);
        log_hex("AUDIO DRIVER RANGE START=", driver_start);
        log_hex("AUDIO DRIVER RANGE END=", driver_end);
        if (scan_start < 0x80000000u || scan_start >= playback_open ||
            driver_start <= scan_start || driver_end <= ready_target ||
            ready_code[0] != BDA_C200_RECORD_READY_SIGNATURE0_LIKE ||
            ready_code[1] != BDA_C200_RECORD_READY_SIGNATURE1_LIKE ||
            read_entry[0] != BDA_C200_RECORD_READ_SIGNATURE0_LIKE ||
            read_entry[1] != BDA_C200_RECORD_READ_SIGNATURE1_LIKE) {
            log_text("COMPACT MAP GUARD FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }
        scan_capture_state_references_v10(driver_start, driver_end);
    }
    log_text("DIAGNOSTIC ONLY; NO AUDIO CALLS");
    log_text("RESULT=MAP_ONLY");
    log_text("END RECORD STREAM HARDWARE PROBE V10");
    return 0;
#elif defined(RECORD_STREAM_PROBE_V9)
    {
        u32 playback_open =
            (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE);
        u32 scan_start = (u32)bda_api(
            bda_sys_table(), BDA_SYS_SESSION_OPEN_LIKE
        );
        u32 init_target = bda_c200_record_open_address_like() - 0x30u;
        u32 ready_target = bda_c200_record_ready_address_like();
        u32 read_target = bda_c200_record_read_address_like() - 4u;
        u32 init_matches;
        u32 ready_matches;
        u32 read_matches;
        u32 stream_matches;
        u32 init_owner;
        u32 ready_owner;
        u32 read_owner;
        u32 stream_owner;
        u32 hardware_wrapper;
        u32 hardware_target_a;
        u32 hardware_target_b;
        u32 stream_target = read_target + 0x490u;
        u32 driver_start = read_target - 0x2000u;
        u32 driver_end = ready_target + 0x2000u;
        const volatile u32 *init_code =
            (const volatile u32 *)init_target;
        const volatile u32 *read_entry =
            (const volatile u32 *)read_target;
        const volatile u32 *hardware_code;
        const volatile u32 *stream_code =
            (const volatile u32 *)stream_target;

        log_hex("PLAYBACK OPEN ADDRESS=", playback_open);
        log_hex("CALL SCAN START=", scan_start);
        log_hex("INIT TARGET=", init_target);
        log_hex("READY TARGET=", ready_target);
        log_hex("READ TARGET=", read_target);
        log_hex("STREAM TARGET=", stream_target);
        if (scan_start < 0x80000000u || scan_start >= playback_open ||
            read_target <= scan_start || read_target >= playback_open ||
            init_target <= playback_open || init_target >= ready_target ||
            stream_target <= read_target || stream_target >= playback_open ||
            driver_start <= scan_start || driver_end <= ready_target) {
            log_text("MAP RANGE GUARD FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }
        if (init_code[0] != 0x27bdffe0u ||
            init_code[1] != 0xafbf001cu ||
            ready_code[0] != BDA_C200_RECORD_READY_SIGNATURE0_LIKE ||
            ready_code[1] != BDA_C200_RECORD_READY_SIGNATURE1_LIKE ||
            read_entry[0] != BDA_C200_RECORD_READ_SIGNATURE0_LIKE ||
            read_entry[1] != BDA_C200_RECORD_READ_SIGNATURE1_LIKE ||
            stream_code[0] != 0x27bdffb8u) {
            log_text("TRUE HARDWARE SIGNATURE FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }

        init_owner = find_direct_caller_owner_v7(
            scan_start, playback_open, init_target, &init_matches
        );
        ready_owner = find_direct_caller_owner_v7(
            scan_start, playback_open, ready_target, &ready_matches
        );
        read_owner = find_direct_caller_owner_v7(
            scan_start, playback_open, read_target, &read_matches
        );
        stream_owner = find_direct_caller_owner_v7(
            scan_start, playback_open, stream_target, &stream_matches
        );
        hardware_wrapper = init_owner + 0x28u;
        hardware_code = (const volatile u32 *)hardware_wrapper;
        hardware_target_a = decode_direct_jal_target(
            hardware_wrapper + 8u, hardware_code[2]
        );
        hardware_target_b = decode_direct_jal_target(
            hardware_wrapper + 0x10u, hardware_code[4]
        );

        log_hex("INIT CALL MATCHES=", init_matches);
        log_hex("INIT OWNER=", init_owner);
        log_hex("READY CALL MATCHES=", ready_matches);
        log_hex("READY OWNER=", ready_owner);
        log_hex("READ CALL MATCHES=", read_matches);
        log_hex("READ FIRST OWNER=", read_owner);
        log_hex("STREAM CALL MATCHES=", stream_matches);
        log_hex("STREAM OWNER=", stream_owner);
        log_hex("HARDWARE WRAPPER=", hardware_wrapper);
        log_hex("HARDWARE TARGET A=", hardware_target_a);
        log_hex("HARDWARE TARGET B=", hardware_target_b);
        log_hex("AUDIO DRIVER RANGE START=", driver_start);
        log_hex("AUDIO DRIVER RANGE END=", driver_end);

        if (init_matches != 1u || ready_matches != 1u ||
            read_matches < 1u || stream_matches != 1u ||
            init_owner == 0u || ready_owner == 0u ||
            read_owner == 0u || stream_owner == 0u ||
            hardware_code[0] != 0x27bdffe8u ||
            hardware_code[1] != 0xafbf0010u ||
            !is_direct_jal(hardware_code[2]) ||
            !is_direct_jal(hardware_code[4]) ||
            hardware_target_a < driver_start ||
            hardware_target_a >= driver_end ||
            hardware_target_b < driver_start ||
            hardware_target_b >= driver_end) {
            log_text("DEEP MAP RESOLUTION FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }

        dump_code_range(
            "WORKER DEEP WORD ADDRESS=",
            read_owner,
            read_owner + 0x4c0u
        );
        dump_code_range(
            "CONTROL WRAPPER WORD ADDRESS=",
            init_owner - 0x40u,
            init_owner + 0xc0u
        );
        dump_code_range(
            "STREAM CONTROL WORD ADDRESS=",
            stream_owner,
            ready_owner + 0x20u
        );
        dump_code_range(
            "STREAM DRIVER WORD ADDRESS=",
            stream_target,
            playback_open
        );
        dump_code_range(
            "HARDWARE DRIVER WORD ADDRESS=",
            hardware_target_a,
            hardware_target_b + 0x80u
        );
        scan_direct_callers(
            "CALLERS HARDWARE WRAPPER",
            scan_start,
            playback_open,
            hardware_wrapper
        );
        scan_direct_callers(
            "CALLERS HARDWARE TARGET A",
            scan_start,
            playback_open,
            hardware_target_a
        );
        scan_direct_callers(
            "CALLERS HARDWARE TARGET B",
            scan_start,
            playback_open,
            hardware_target_b
        );
        scan_direct_callers(
            "CALLERS STREAM OWNER",
            scan_start,
            playback_open,
            stream_owner
        );
        scan_direct_callers(
            "CALLERS STREAM TARGET",
            scan_start,
            playback_open,
            stream_target
        );
        scan_capture_state_references_v9(driver_start, driver_end);
    }
    log_text("DIAGNOSTIC ONLY; NO AUDIO CALLS");
    log_text("RESULT=MAP_ONLY");
    log_text("END RECORD STREAM HARDWARE PROBE V9");
    return 0;
#elif defined(RECORD_STREAM_PROBE_V7) || defined(RECORD_STREAM_PROBE_V8)
    {
        u32 playback_open =
            (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE);
        u32 scan_start = (u32)bda_api(
            bda_sys_table(), BDA_SYS_SESSION_OPEN_LIKE
        );
        u32 init_target = bda_c200_record_open_address_like() - 0x30u;
        u32 config_target = init_target + 0x1bcu;
        u32 ready_target = bda_c200_record_ready_address_like();
        u32 read_target = bda_c200_record_read_address_like() - 4u;
        u32 init_matches;
        u32 config_matches;
        u32 ready_matches;
        u32 read_matches;
        u32 init_owner;
        u32 config_owner;
        u32 ready_owner;
        u32 read_owner;
        u32 control_start;
        u32 control_end;
        u32 worker_end;
        u32 driver_start;
        u32 driver_end;
        int read_signature_ok;
        const volatile u32 *init_code =
            (const volatile u32 *)init_target;
        const volatile u32 *config_code =
            (const volatile u32 *)config_target;
        const volatile u32 *read_entry =
            (const volatile u32 *)read_target;

        log_hex("PLAYBACK OPEN ADDRESS=", playback_open);
        log_hex("CALL SCAN START=", scan_start);
        log_hex("CALL SCAN END=", playback_open);
        log_hex("INIT TARGET=", init_target);
        log_hex("CONFIG TARGET=", config_target);
        log_hex("READY TARGET=", ready_target);
        log_hex("READ TARGET=", read_target);
#ifdef RECORD_STREAM_PROBE_V8
        log_hex("INIT ENTRY SIG0=", init_code[0]);
        log_hex("INIT ENTRY SIG1=", init_code[1]);
        log_hex("CONFIG ENTRY SIG0=", config_code[0]);
        log_hex("CONFIG ENTRY SIG1=", config_code[1]);
        log_hex("READY ENTRY SIG0=", ready_code[0]);
        log_hex("READY ENTRY SIG1=", ready_code[1]);
        log_hex("READ ENTRY SIG0=", read_entry[0]);
        log_hex("READ ENTRY SIG1=", read_entry[1]);
#endif

        if (scan_start < 0x80000000u || scan_start >= playback_open ||
            read_target <= scan_start || read_target >= playback_open + 0x2000u ||
            init_target <= playback_open || init_target >= ready_target ||
            config_target <= init_target || config_target >= ready_target) {
            log_text("MAP RANGE GUARD FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }
#ifdef RECORD_STREAM_PROBE_V8
        read_signature_ok =
            read_entry[0] == BDA_C200_RECORD_READ_SIGNATURE0_LIKE &&
            read_entry[1] == BDA_C200_RECORD_READ_SIGNATURE1_LIKE;
#else
        read_signature_ok =
            *(const volatile u32 *)read_target == 0x27bdffb8u &&
            read_code[0] == BDA_C200_RECORD_READ_SIGNATURE0_LIKE &&
            read_code[1] == BDA_C200_RECORD_READ_SIGNATURE1_LIKE;
#endif
        if (init_code[0] != 0x27bdffe0u ||
            init_code[1] != 0xafbf001cu ||
            init_code[2] != 0x0c0669f2u ||
            init_code[3] != 0xafb00018u ||
            config_code[0] != 0x27bdffe8u ||
            config_code[1] != 0x2c820005u ||
            ready_code[0] != BDA_C200_RECORD_READY_SIGNATURE0_LIKE ||
            ready_code[1] != BDA_C200_RECORD_READY_SIGNATURE1_LIKE ||
            !read_signature_ok) {
            log_text("TRUE HARDWARE SIGNATURE FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }

        init_owner = find_direct_caller_owner_v7(
            scan_start, playback_open, init_target, &init_matches
        );
        config_owner = find_direct_caller_owner_v7(
            scan_start, playback_open, config_target, &config_matches
        );
        ready_owner = find_direct_caller_owner_v7(
            scan_start, playback_open, ready_target, &ready_matches
        );
        read_owner = find_direct_caller_owner_v7(
            scan_start, playback_open, read_target, &read_matches
        );
        log_hex("INIT CALL MATCHES=", init_matches);
        log_hex("INIT OWNER=", init_owner);
        log_hex("CONFIG CALL MATCHES=", config_matches);
        log_hex("CONFIG OWNER=", config_owner);
        log_hex("READY CALL MATCHES=", ready_matches);
        log_hex("READY OWNER=", ready_owner);
        log_hex("READ CALL MATCHES=", read_matches);
        log_hex("READ FIRST OWNER=", read_owner);

        if (init_matches != 1u || config_matches != 1u ||
            ready_matches != 1u || read_matches < 1u ||
            init_owner == 0u || config_owner == 0u ||
            ready_owner == 0u || read_owner == 0u) {
            log_text("CALLER RESOLUTION FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }

        control_start = init_owner > scan_start + 0x800u ?
            init_owner - 0x800u : scan_start;
        control_end = ready_owner + 0x1000u;
        if (control_end > playback_open) {
            control_end = playback_open;
        }
        worker_end = read_owner + 0x600u;
        if (worker_end > control_start) {
            worker_end = control_start;
        }
        driver_start = read_target > 0x2000u ?
            read_target - 0x2000u : read_target;
        driver_end = ready_target + 0x2000u;
        log_hex("AUDIO DRIVER RANGE START=", driver_start);
        log_hex("AUDIO DRIVER RANGE END=", driver_end);

        scan_manager_range_v7(
            "PCM WORKER CALL GRAPH",
            read_owner,
            worker_end,
            driver_start,
            driver_end
        );
        scan_manager_range_v7(
            "RECORD CONTROL CALL GRAPH",
            control_start,
            control_end,
            driver_start,
            driver_end
        );
    }
    log_text("DIAGNOSTIC ONLY; NO AUDIO CALLS");
    log_text("RESULT=MAP_ONLY");
#ifdef RECORD_STREAM_PROBE_V8
    log_text("END RECORD STREAM HARDWARE PROBE V8");
#else
    log_text("END RECORD STREAM HARDWARE PROBE V7");
#endif
    return 0;
#elif defined(RECORD_STREAM_PROBE_V5)
    {
        u32 playback_open =
            (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE);
        u32 old_open_guess = bda_c200_record_open_address_like();
        u32 init_candidate = old_open_guess - 0x30u;
        u32 config_candidate = init_candidate + 0x1bcu;
        u32 ready_address = bda_c200_record_ready_address_like();
        u32 pre_ready_helper = ready_address - 0x38u;
        u32 read_address = bda_c200_record_read_address_like() - 4u;
        u32 scan_start = (u32)bda_api(
            bda_sys_table(), BDA_SYS_SESSION_OPEN_LIKE
        );
        u32 scan_end = ready_address + 0x400u;

        log_hex("PLAYBACK OPEN ADDRESS=", playback_open);
        log_hex("INIT CANDIDATE ADDRESS=", init_candidate);
        log_hex("CONFIG CANDIDATE ADDRESS=", config_candidate);
        log_hex("PRE READY HELPER ADDRESS=", pre_ready_helper);
        log_hex("CAPTURE READY ADDRESS=", ready_address);
        log_hex("CAPTURE READ ADDRESS=", read_address);
        log_hex("CALL SCAN START=", scan_start);
        log_hex("CALL SCAN END=", scan_end);

        if (scan_start < 0x80000000u || scan_start >= playback_open ||
            init_candidate <= playback_open ||
            config_candidate >= pre_ready_helper ||
            pre_ready_helper >= ready_address) {
            log_text("MAP RANGE GUARD FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }

        dump_code_range(
            "INIT TAIL WORD ADDRESS=",
            init_candidate + 0xc0u,
            config_candidate
        );
        dump_code_range(
            "CONFIG WORD ADDRESS=",
            config_candidate,
            pre_ready_helper
        );
        dump_code_range(
            "PRE READY WORD ADDRESS=",
            pre_ready_helper,
            ready_address
        );
        scan_direct_callers(
            "CALLERS INIT CANDIDATE",
            scan_start,
            scan_end,
            init_candidate
        );
        scan_direct_callers(
            "CALLERS CONFIG CANDIDATE",
            scan_start,
            scan_end,
            config_candidate
        );
        scan_direct_callers(
            "CALLERS PRE READY HELPER",
            scan_start,
            scan_end,
            pre_ready_helper
        );
        scan_direct_callers(
            "CALLERS CAPTURE READY",
            scan_start,
            scan_end,
            ready_address
        );
        scan_direct_callers(
            "CALLERS CAPTURE READ",
            scan_start,
            scan_end,
            read_address
        );
    }
    log_text("DIAGNOSTIC ONLY; NO AUDIO CALLS");
    log_text("RESULT=MAP_ONLY");
    log_text("END RECORD STREAM HARDWARE PROBE V5");
    return 0;
#elif defined(RECORD_STREAM_PROBE_V3)
    log_hex(
        "PLAYBACK OPEN ADDRESS=",
        (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE)
    );
    analyze_capture_layout(
        (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE),
        bda_c200_record_ready_address_like(),
        bda_c200_record_open_address_like()
    );
    log_text("DIAGNOSTIC ONLY; NO AUDIO CALLS");
    log_text("RESULT=MAP_ONLY");
    log_text("END RECORD STREAM HARDWARE PROBE V3");
    return 0;
#elif defined(RECORD_STREAM_PROBE_V6)
    {
        u32 playback_open =
            (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE);
        u32 config_target;
        const volatile u32 *config_code;

        log_hex("PLAYBACK OPEN ADDRESS=", playback_open);
        g_capture_ready_address = bda_c200_record_ready_address_like();
        g_capture_open_address = resolve_capture_open_v4(
            playback_open,
            g_capture_ready_address,
            &open_matches
        );
        config_target = g_capture_open_address != 0u ?
            g_capture_open_address + 0x1bcu : 0u;
        g_capture_config_wrapper_address = config_target != 0u ?
            resolve_capture_config_wrapper_v6(
                (u32)bda_api(bda_sys_table(), BDA_SYS_SESSION_OPEN_LIKE),
                playback_open,
                config_target,
                &config_matches
            ) : 0u;
        if (config_target == 0u) {
            config_matches = 0u;
        }
        g_capture_read_address = resolve_capture_read(
            bda_c200_record_read_address_like(),
            &read_matches
        );
        log_hex("INIT MATCHES=", open_matches);
        log_hex("INIT RESOLVED=", g_capture_open_address);
        log_hex("CONFIG TARGET=", config_target);
        log_hex("CONFIG WRAPPER MATCHES=", config_matches);
        log_hex(
            "CONFIG WRAPPER RESOLVED=",
            g_capture_config_wrapper_address
        );
        log_hex("READ MATCHES=", read_matches);
        log_hex("READ RESOLVED=", g_capture_read_address);

        config_code = (const volatile u32 *)config_target;
        if (ready_code[0] != BDA_C200_RECORD_READY_SIGNATURE0_LIKE ||
            ready_code[1] != BDA_C200_RECORD_READY_SIGNATURE1_LIKE ||
            g_capture_open_address == 0u ||
            config_target == 0u ||
            config_code[0] != 0x27bdffe8u ||
            config_code[1] != 0x2c820005u ||
            config_code[2] != 0xafbf0014u ||
            config_code[3] != 0xafb00010u ||
            g_capture_config_wrapper_address == 0u ||
            g_capture_read_address == 0u) {
            log_text("TRUE HARDWARE SEQUENCE SIGNATURE FAILED");
            log_text("RESULT=UNSUPPORTED");
            return 2;
        }
    }
    log_text("TRUE HARDWARE SEQUENCE SIGNATURE PASS");
#elif defined(RECORD_STREAM_PROBE_V4)
    log_hex(
        "PLAYBACK OPEN ADDRESS=",
        (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE)
    );
    g_capture_ready_address = bda_c200_record_ready_address_like();
    g_capture_open_address = resolve_capture_open_v4(
        (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE),
        g_capture_ready_address,
        &open_matches
    );
    g_capture_read_address = resolve_capture_read(
        bda_c200_record_read_address_like(),
        &read_matches
    );
    log_hex("OPEN MATCHES=", open_matches);
    log_hex("OPEN RESOLVED=", g_capture_open_address);
    log_hex("READ MATCHES=", read_matches);
    log_hex("READ RESOLVED=", g_capture_read_address);

    if (ready_code[0] != BDA_C200_RECORD_READY_SIGNATURE0_LIKE ||
        ready_code[1] != BDA_C200_RECORD_READY_SIGNATURE1_LIKE ||
        g_capture_open_address == 0u ||
        g_capture_read_address == 0u) {
        log_text("TRUE HARDWARE SIGNATURE FAILED");
        log_text("RESULT=UNSUPPORTED");
        return 2;
    }
    log_text("TRUE HARDWARE SIGNATURE PASS");
#elif defined(RECORD_STREAM_PROBE_V2)
    log_code_window("OPEN WINDOW ADDRESS=", bda_c200_record_open_address_like());
    log_code_window("READ WINDOW ADDRESS=", bda_c200_record_read_address_like());

    g_capture_ready_address = bda_c200_record_ready_address_like();
    g_capture_open_address = resolve_capture_open(
        g_capture_ready_address,
        &open_matches
    );
    g_capture_read_address = resolve_capture_read(
        bda_c200_record_read_address_like(),
        &read_matches
    );
    log_hex("OPEN MATCHES=", open_matches);
    log_hex("OPEN RESOLVED=", g_capture_open_address);
    log_hex("READ MATCHES=", read_matches);
    log_hex("READ RESOLVED=", g_capture_read_address);

    if (g_capture_open_address ==
        (u32)bda_api(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE)) {
        log_text("OPEN RESOLVED TO PLAYBACK ENTRY");
        g_capture_open_address = 0u;
    }

    if (ready_code[0] != BDA_C200_RECORD_READY_SIGNATURE0_LIKE ||
        ready_code[1] != BDA_C200_RECORD_READY_SIGNATURE1_LIKE ||
        g_capture_open_address == 0u ||
        g_capture_read_address == 0u) {
        log_text("STRUCTURAL RESOLUTION FAILED");
        log_text("RESULT=UNSUPPORTED");
        return 2;
    }
    log_text("STRUCTURAL RESOLUTION PASS");
#else
    if (!bda_c200_record_stream_supported_like()) {
        log_text("SIGNATURE MISMATCH");
        log_text("RESULT=UNSUPPORTED");
        return 2;
    }
    log_text("SIGNATURE PASS");
#endif

    raw_file = open_raw();
    log_hex("RAW FILE=", (u32)raw_file);
#ifdef RECORD_STREAM_PROBE_V6
    {
        int init_return;
        int config_return;

        log_text("BEFORE CAPTURE INIT NOARGS");
        init_return = capture_init_v6();
        capture_started = 1;
        log_hex("CAPTURE INIT RETURN=", (u32)init_return);
        if (init_return != 0) {
            ++failures;
        }
        if (failures == 0) {
            log_text("BEFORE CONFIG WRAPPER 16000");
            config_return = capture_config_v6(16000u);
            log_hex("CONFIG WRAPPER RETURN=", (u32)config_return);
            if (config_return != 0) {
                ++failures;
            }
        }
    }
#elif defined(RECORD_STREAM_PROBE_V4)
    log_text("BEFORE CAPTURE OPEN NOARGS");
    capture_open();
    capture_started = 1;
    log_text("CAPTURE OPEN RETURNED");
#else
    log_text("BEFORE CAPTURE OPEN 16000/16/1");
    capture_open();
    capture_started = 1;
    log_text("CAPTURE OPEN RETURNED");
#endif

    for (block = 0;
         failures == 0 && block < RECORD_BLOCK_COUNT;
         ++block) {
        u32 polls;
        u32 ticks;
        int got;
        int raw_written = -1;

        if (!wait_capture_ready(&polls, &ticks)) {
            log_hex("READY TIMEOUT BLOCK=", block);
            log_hex("READY TIMEOUT POLLS=", polls);
            log_hex("READY TIMEOUT TICKS=", ticks);
            ++failures;
            break;
        }
        log_hex("BEFORE READ BLOCK=", block);
        got = capture_read(g_pcm, RECORD_BLOCK_BYTES);
        if (bda_fs_file_is_valid(raw_file) && got > 0) {
            raw_written = bda_fs_write_raw(raw_file, g_pcm, (u32)got);
        }
        log_block_stats(block, got, polls, ticks, raw_written);
        if (got != (int)RECORD_BLOCK_BYTES) {
            ++failures;
            break;
        }
    }

    if (capture_started) {
        log_text("BEFORE CAPTURE STOP");
        bda_c200_record_stream_stop_like();
        log_text("CAPTURE STOP RETURNED");
    }
    if (bda_fs_file_is_valid(raw_file)) {
        log_text("BEFORE RAW CLOSE");
        (void)bda_fs_close_raw(raw_file);
        log_text("RAW CLOSE RETURNED");
    }
    log_hex("FAILURES=", (u32)failures);
    log_text(failures ? "RESULT=FAIL" : "RESULT=PASS");
#ifdef RECORD_STREAM_PROBE_V6
    log_text("END RECORD STREAM HARDWARE PROBE V6");
#elif defined(RECORD_STREAM_PROBE_V4)
    log_text("END RECORD STREAM HARDWARE PROBE V4");
#elif defined(RECORD_STREAM_PROBE_V2)
    log_text("END RECORD STREAM HARDWARE PROBE V2");
#else
    log_text("END RECORD STREAM HARDWARE PROBE V1");
#endif
    return failures ? 1 : 0;
}
