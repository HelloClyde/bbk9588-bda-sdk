#ifndef BDA_SDK_H
#define BDA_SDK_H

typedef unsigned int u32;
typedef int s32;
typedef unsigned char u8;
typedef signed short s16;
typedef unsigned short u16;
typedef unsigned int bda_size_t;
typedef unsigned long long u64;

#define BDA_GUI_TABLE_ADDR 0x81c00004u
#define BDA_FS_TABLE_ADDR 0x81c00008u
#define BDA_SYS_TABLE_ADDR 0x81c0000cu
#define BDA_MEM_TABLE_ADDR 0x81c00010u
#define BDA_RES_TABLE_ADDR 0x81c00014u

#define BDA_RUNTIME_BASE 0x81c00000u

#define BDA_GUI_MESSAGE_SIZE 0x1cu
#define BDA_GUI_INPUT_PACKET_SIZE 6u

/* Linux input keycodes used by the built-in game shell. */
#define BDA_KEY_ESCAPE 0x01u
#define BDA_KEY_ENTER  0x1cu
#define BDA_KEY_UP     0x67u
#define BDA_KEY_LEFT   0x69u
#define BDA_KEY_RIGHT  0x6au
#define BDA_KEY_DOWN   0x6cu

/* GUI+0x5d4 packet byte layout recovered from Eros and C200. */
#define BDA_INPUT_PACKET_RIGHT_INDEX  0u
#define BDA_INPUT_PACKET_LEFT_INDEX   1u
#define BDA_INPUT_PACKET_DOWN_INDEX   2u
#define BDA_INPUT_PACKET_UP_INDEX     3u
#define BDA_INPUT_PACKET_ESCAPE_INDEX 4u
#define BDA_INPUT_PACKET_ENTER_INDEX  5u

#define BDA_GUI_MSGBOX 0x2b8u
#define BDA_GUI_CREATE 0x1a4u
#define BDA_GUI_SEND   0x040u
#define BDA_GUI_NOTIFY_LIKE 0x03cu
#define BDA_GUI_PUMP_PRESENT_LIKE 0x074u
#define BDA_GUI_OBJECT_FLAGS_CLEAR_LIKE 0x07cu
#define BDA_GUI_OBJECT_FLAGS_OR_LIKE    0x080u
#define BDA_GUI_REGISTER_FRAME_LIKE 0x084u
#define BDA_GUI_FRAME_STOP_LIKE     0x088u
#define BDA_GUI_DEFAULT_PROC_LIKE   0x08cu
#define BDA_GUI_FRAME_ACTIVATE_LIKE 0x098u
#define BDA_GUI_OBJECT_RECT_LIKE    0x0a4u
#define BDA_GUI_EVENT_POLL_LIKE     0x030u
#define BDA_GUI_EVENT_STEP_LIKE     0x050u
#define BDA_GUI_EVENT_DISPATCH_LIKE 0x054u
#define BDA_GUI_FRAME_RELEASE_LIKE  0x04cu
#define BDA_GUI_CLOSE_FRAME_LIKE    0x17cu
#define BDA_GUI_DESTROY_LIKE 0x1a8u
#define BDA_GUI_OBJECT_OP_LIKE 0x0e0u
#define BDA_GUI_OBJECT_DRAW_BEGIN_LIKE 0x0e4u
#define BDA_GUI_OBJECT_DRAW_END_LIKE   0x0e8u
#define BDA_GUI_OBJECT_FLAGS_GET_LIKE  0x0b0u
#define BDA_GUI_OBJECT_USERDATA0_GET_LIKE 0x0b8u
#define BDA_GUI_OBJECT_USERDATA0_SET_LIKE 0x0bcu
#define BDA_GUI_OBJECT_USERDATA1_GET_LIKE 0x0c0u
#define BDA_GUI_OBJECT_USERDATA1_SET_LIKE 0x0c4u
#define BDA_GUI_OBJECT_PAYLOAD_WORD_GET_LIKE 0x0c8u
#define BDA_GUI_OBJECT_PAYLOAD_WORD_SET_LIKE 0x0ccu
#define BDA_GUI_OBJECT_RESOURCE_PTR_GET_LIKE 0x0d0u
#define BDA_GUI_OBJECT_CALLBACK_PTR_GET_LIKE 0x0d8u
#define BDA_GUI_OBJECT_CALLBACK_PTR_SET_LIKE 0x0dcu
#define BDA_GUI_ACCUMULATE_ORIGIN_LIKE 0x0f4u
#define BDA_GUI_SUBTRACT_ORIGIN_LIKE   0x0f8u
#define BDA_GUI_ACTIVE_FRAME_SET_LIKE  0x134u
#define BDA_GUI_ACTIVE_FRAME_GET_LIKE  0x13cu
#define BDA_GUI_OBJECT_UPDATE3_LIKE    0x1acu
#define BDA_GUI_OBJECT_UPDATE2_LIKE    0x1b0u
#define BDA_GUI_OBJECT_PAIR_EXISTS_LIKE 0x1b4u
#define BDA_GUI_DRAW_OBJECT_CREATE_LIKE 0x2fcu
#define BDA_GUI_DISPLAY_METRIC_LIKE  0x300u
#define BDA_GUI_CURRENT_DRAW_LIKE    0x304u
#define BDA_GUI_BEGIN_DRAW_LIKE      0x308u
#define BDA_GUI_END_DRAW_LIKE        0x30cu
#define BDA_GUI_COMPAT_CONTEXT_CREATE_LIKE 0x310u
#define BDA_GUI_SURFACE_FLUSH_LIKE   0x314u
#define BDA_GUI_SET_FILL_COLOR_LIKE  0x334u
#define BDA_GUI_SET_TEXT_MODE_LIKE  0x338u
#define BDA_GUI_SET_TEXT_COLOR_LIKE 0x33cu
#define BDA_GUI_SELECT_DRAW_OBJECT_LIKE 0x358u
#define BDA_GUI_OBJECT_BIND_LIKE    0x35cu
#define BDA_GUI_PUT_PIXEL_LIKE      0x368u
#define BDA_GUI_PUT_PIXEL_RGB_LIKE  0x36cu
#define BDA_GUI_RGB_LIKE            0x378u
#define BDA_GUI_LINE_TO_LIKE        0x37cu
#define BDA_GUI_MOVE_TO_LIKE        0x380u
#define BDA_GUI_CIRCLE_LIKE         0x388u
#define BDA_GUI_RECTANGLE_LIKE      0x38cu
#define BDA_GUI_DRAW_VX_LIKE        0x540u
#define BDA_GUI_REGION_DRAW_LIKE    0x40cu
/*
 * low-level render helper 常量。C200 的 +0x410/+0x414/+0x418 都读取多个 stack 参数、
 * draw context 和 resource/bitmap descriptor，并会调用 backend callback。+0x410
 * 在 clipping 后宽度变化时可能临时分配裁剪 buffer，结束后释放；SDK 暂不提供
 * high-level wrapper。
 */
#define BDA_GUI_RENDER_COPY_LIKE    0x410u
#define BDA_GUI_RENDER_HELPER_LIKE  0x414u
#define BDA_GUI_RENDER_FINISH_LIKE  0x418u /* source context first; visible destination at stack arg 6 */
/*
 * low-level rect writer。C200 的 +0x430 是 5 参数 ABI：rect,x0,y0,x1,y1；
 * 第五参数从 stack+0x10 读取；wrapper 已用 bda_call5 封装。
 */
#define BDA_GUI_RECT_PREPARE_LIKE   0x430u
#define BDA_GUI_CURRENT_FONT_LIKE   0x4a4u
#define BDA_GUI_FONT_CELL_WIDTH_LIKE  0x4d0u
#define BDA_GUI_FONT_CELL_HEIGHT_LIKE 0x4d4u
#define BDA_GUI_DRAW_TEXT_LIKE      0x4f0u
#define BDA_GUI_RECT_CONTAINS_LIKE  0x46cu
#define BDA_GUI_DECODE_BMP_LIKE     0x670u
#define BDA_GUI_DECODE_JPEG_LIKE    0x808u

/* 原机游戏使用的 framebuffer/region draw 调用。 */
#define BDA_GUI_BLIT_LIKE     0x3f8u
#define BDA_GUI_CAPTURE_REGION_ALLOC_LIKE 0x3fcu
#define BDA_GUI_BLIT_ALT_LIKE 0x400u

/* GAMEBOY.BDA 和内置小游戏 shell 中观察到的游戏/前端调用。 */
#define BDA_GUI_INPUT_PACKET_LIKE      0x5d4u
#define BDA_GUI_SCREEN_BUFFER_LIKE     0x6b0u
#define BDA_GUI_TOUCH_POSITION_LIKE    0x6c0u
#define BDA_GUI_GAME_DISPLAY_PUMP_LIKE 0x6e0u
#define BDA_GUI_STATE_QUERY_LIKE       0x72cu
#define BDA_GUI_SCREEN_WIDTH_LIKE      0x738u
#define BDA_GUI_EVENT_FETCH_LIKE       0x750u

/* GAMEBOY.BDA 中观察到的 file selector/session 调用。 */
#define BDA_GUI_FILE_SELECTOR_OPEN_LIKE   0x6a8u
#define BDA_GUI_LIST_NTH_LIKE             0x6b8u
#define BDA_GUI_LIST_FREE_LIKE            0x6bcu
#define BDA_GUI_FILE_SELECTOR_UPDATE_LIKE 0x6c8u

/* GUI+0x300 metric index used by Thunder/Tank framebuffer allocation. */
#define BDA_GUI_DISPLAY_METRIC_PIXEL_BYTES_LIKE 6u

#define BDA_MEM_TRACK_ALLOC_LIKE 0x000u
#define BDA_MEM_TRACK_FREE_LIKE  0x004u
#define BDA_MEM_ALLOC 0x008u
#define BDA_MEM_FREE  0x00cu
#define BDA_MEM_CALLOC_LIKE 0x010u
#define BDA_MEM_REALLOC_LIKE 0x014u
#define BDA_MEM_TRACK_BEGIN_LIKE 0x01cu
#define BDA_MEM_TRACK_REPORT_LIKE 0x020u
#define BDA_MEM_TRACK_FINISH_LIKE 0x024u
#define BDA_MEM_TRACK_RETAIN_LIKE 0x028u
#define BDA_MEM_TRACK_RELEASE_LIKE 0x02cu

#define BDA_RES_GET_STATE_LIKE 0x090u
/* 元素周期表会把 printf-style 字符串传给该 table entry；真机 probe 显示它不是 DLX loader。 */
#define BDA_RES_ENTRY_094_LIKE 0x094u
#define BDA_RES_TRACE_LIKE BDA_RES_ENTRY_094_LIKE

#define BDA_FS_OPEN  0x000u
#define BDA_FS_CLOSE 0x004u
#define BDA_FS_READ  0x008u
#define BDA_FS_WRITE 0x00cu
#define BDA_FS_SEEK  0x010u
#define BDA_FS_TELL  0x014u
#define BDA_FS_EOF_LIKE 0x018u
#define BDA_FS_ERROR_LIKE 0x01cu
#define BDA_FS_CLEAR_ERROR_LIKE 0x020u
#define BDA_FS_REMOVE 0x024u
#define BDA_FS_RENAME_LIKE 0x028u
#define BDA_FS_CHDIR_LIKE 0x02cu
#define BDA_FS_MKDIR_LIKE 0x030u
#define BDA_FS_RMDIR_LIKE 0x034u
#define BDA_FS_FINDFIRST_LIKE 0x03cu
#define BDA_FS_FINDNEXT_LIKE  0x040u
#define BDA_FS_FINDCLOSE_LIKE 0x044u
#define BDA_FS_DISKINFO_LIKE  0x048u
#define BDA_FS_GETCWD_LIKE    0x050u
#define BDA_FS_PATH_INFO_LIKE 0x054u
#define BDA_FS_STAT_LIKE      0x06cu
#define BDA_FS_MEDIA_PRESENT_RAW_LIKE 0x078u
#define BDA_FS_STORAGE_READY_LIKE 0x07cu

#define BDA_SEEK_SET 0
#define BDA_SEEK_CUR 1
#define BDA_SEEK_END 2

#define BDA_SYS_ALARM_RECORD_SIZE 0x2b8u
#define BDA_SYS_ALARM_CONFIRMED_SLOTS 3u
#define BDA_SYS_ALARM_DB_FIRST_RECORD_OFFSET 0x578u
#define BDA_SYS_ALARM_SLOT_TAG_OFFSET 0x00u
#define BDA_SYS_ALARM_ENABLE_FLAG_OFFSET 0x10u
#define BDA_SYS_ALARM_DUE_MISS_TAG 0xffffffffu

typedef struct bda_sys_alarm_record_like {
    u8 raw[BDA_SYS_ALARM_RECORD_SIZE];
} bda_sys_alarm_record_like_t;

static inline void bda_sys_alarm_record_init_like(bda_sys_alarm_record_like_t *record) {
    bda_size_t i;
    for (i = 0; i < sizeof(*record); ++i) {
        record->raw[i] = 0;
    }
}

static inline int bda_sys_alarm_slot_confirmed_like(u32 slot) {
    return slot < BDA_SYS_ALARM_CONFIRMED_SLOTS;
}

static inline u32 bda_sys_alarm_record_file_offset_like(u32 slot) {
    return BDA_SYS_ALARM_DB_FIRST_RECORD_OFFSET + slot * BDA_SYS_ALARM_RECORD_SIZE;
}

static inline u32 bda_sys_alarm_record_slot_tag_like(const bda_sys_alarm_record_like_t *record) {
    const u8 *p = record->raw + BDA_SYS_ALARM_SLOT_TAG_OFFSET;
    return (u32)p[0] | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

static inline int bda_sys_alarm_due_miss_like(const bda_sys_alarm_record_like_t *record) {
    return bda_sys_alarm_record_slot_tag_like(record) == BDA_SYS_ALARM_DUE_MISS_TAG;
}

static inline u8 bda_sys_alarm_record_enable_flag_like(const bda_sys_alarm_record_like_t *record) {
    return record->raw[BDA_SYS_ALARM_ENABLE_FLAG_OFFSET];
}

/*
 * 内部 system resource close table entry。C200 的 SYS+0x004 使用 resource_id 范围 1..10
 * 查询 firmware resource table 并调用对应 close callback；它不是 app exit，也不是 raw audio
 * 专用 stop。SDK 暂不提供 high-level wrapper。
 */
#define BDA_SYS_CLOSE_LIKE       0x004u
/* GAMEBOY.BDA 中观察到的设备/音频调用。 */
#define BDA_SYS_AUDIO_OPEN_LIKE  0x06cu
#define BDA_SYS_AUDIO_READY_LIKE 0x074u
#define BDA_SYS_AUDIO_WRITE_LIKE 0x078u
#define BDA_SYS_KEYCODE_RAW_LIKE 0x088u
#define BDA_SYS_AUDIO_RESET_LIKE 0x08cu
#define BDA_SYS_AUDIO_STATE_LIKE 0x090u
#define BDA_SYS_PACKAGE_SOUND_OP40_LIKE 0x040u
#define BDA_SYS_PACKAGE_SOUND_OP44_LIKE 0x044u
#define BDA_SYS_PACKAGE_SOUND_OP58_LIKE 0x058u
#define BDA_SYS_PACKAGE_SOUND_OP5C_LIKE 0x05cu
#define BDA_SYS_PACKAGE_SOUND_OP60_LIKE 0x060u
#define BDA_SYS_PACKAGE_SOUND_OP64_LIKE 0x064u
#define BDA_SYS_PACKAGE_SOUND_OP68_LIKE 0x068u
#define BDA_SYS_TIMER_LIKE       0x09cu
#define BDA_SYS_AUDIO_FLUSH_LIKE 0x0a0u
#define BDA_SYS_DELAY_LIKE       0x080u
#define BDA_SYS_ALARM_SET_LIKE   0x0acu
#define BDA_SYS_ALARM_GET_LIKE   0x0b0u
#define BDA_SYS_ALARM_DUE_GET_LIKE 0x0b8u

typedef void *bda_handle_t;
typedef int (*bda_wndproc_t)(bda_handle_t hwnd, u32 message, u32 wparam, u32 lparam);

typedef struct bda_rect_like {
    s32 x0;
    s32 y0;
    s32 x1;
    s32 y1;
} bda_rect_like_t;

/*
 * 顶层 frame descriptor。C200 的 GUI+0x084 会读取这些字段并创建约 0x114 byte
 * 的内部 window object。该 struct size 为 0x34；未确认 field 用 internal/aux 命名，
 * 已确认样本用途的 width/height 和 surface/object offset 直接命名。
 */
typedef struct bda_frame_desc_like {
    u32 style;                  /* +0x00 */
    u32 internal28;             /* +0x04: 写入内部 object +0x28 */
    const char *title;          /* +0x08 */
    u32 internal44;             /* +0x0c: 写入内部 object +0x44 */
    u32 internal48;             /* +0x10: 写入内部 object +0x48 */
    u32 helper_arg14;           /* +0x14: 注册前传给内部 helper */
    bda_wndproc_t wndproc;      /* +0x18 */
    s32 x;                      /* +0x1c */
    s32 y;                      /* +0x20 */
    s32 height;                 /* +0x24 */
    s32 width;                  /* +0x28 */
    u32 surface;                /* +0x2c: no-template 可为 0；原机复杂窗口常见 GUI+0x2fc(15) */
    u32 aux30;                  /* +0x30: 写入内部 object +0x80，常见为 0 */
} bda_frame_desc_like_t;

/*
 * GUI event loop message buffer。C200 的 GUI+0x030 会先清零 BDA_GUI_MESSAGE_SIZE byte，再写入
 * handle/message/wparam/lparam；GUI+0x050/+0x054 继续读取同一个 buffer。
 */
typedef struct bda_gui_message_like {
    bda_handle_t handle;        /* +0x00 */
    u32 message;                /* +0x04 */
    u32 wparam;                 /* +0x08 */
    u32 lparam;                 /* +0x0c */
    u32 aux10;                  /* +0x10: 内部派生/dispatch 状态 */
    u32 aux14;                  /* +0x14 */
    u32 aux18;                  /* +0x18 */
} bda_gui_message_like_t;

typedef struct bda_gui_input_packet_like {
    u8 bytes[BDA_GUI_INPUT_PACKET_SIZE];
} bda_gui_input_packet_like_t;

typedef struct bda_gui_event_fetch_like {
    s32 code;                   /* record+0x04，失败或无事件时为 -1 */
    s32 value;                  /* record+0x00，失败或无事件时为 -1 */
} bda_gui_event_fetch_like_t;

/*
 * file selector descriptor。GAMEBOY.BDA 在调用 GUI+0x6c8 前会初始化这些字段。
 * 硬件测试显示，下面这组较完整初始化能修复 file selector 黑底黑字不可读的问题；
 * 因此部分看似 reserved 的 word 实际是显示/主题/状态参数，不是无害 padding。
 */
typedef struct bda_file_selector_like {
    char *out_path;
    const char *extensions;
    void *dir_state;
    const char *title;
    u32 internal10;
    u32 internal14;
    u32 status18;
    s32 sentinel1c;
    s32 sentinel20;
    s32 sentinel24;
    u32 internal28;
    u32 internal2c;
    u32 internal30;
    u32 sentinel34;
    u32 sentinel38;
    u32 internal3c;
    u32 list_limit40;
    u32 internal44;
    s32 sentinel48;
    u32 internal4c;
    u32 internal50;
    u32 internal54;
    u32 internal58;
    u32 internal5c;
    u32 internal60;
    u32 result64;
} bda_file_selector_like_t;

/*
 * album-backed picture decode descriptor，来自原机“我的相册”。相册代码把 pixel data
 * 视为 16-bit RGB565，并可能按方向模式创建旋转/复制后的 buffer。
 */
typedef struct bda_picture_like {
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
} bda_picture_like_t;

/*
 * RES+0x090 输出的 resource/picture state struct。C200 从 `0xb0003004` 读取状态源，
 * 通过内部 helper 写 7 个 word，其中 +0x10 写入后再减 1。该 table entry 只适合
 * 读取 snapshot；没有稳定 return value。
 */
typedef struct bda_res_state_like {
    u32 aux00;
    u32 aux04;
    u32 aux08;
    u32 aux0c;
    u32 aux10_minus1;
    u32 aux14;
    u32 aux18;
} bda_res_state_like_t;

#define BDA_FS_FIND_DATA_SIZE 0x220u

/*
 * C200-backed directory enumeration struct。C200 的 findfirst 成功路径会写到 +0x21c，
 * 因此旧 probe 使用的 512 byte raw buffer 偏小。field name 只覆盖当前从 FS+0x03c/0x040/0x044
 * function-level disasm 确认的位置；filename/path 区仍按原始 byte 处理，通常是 GBK/ASCII。
 */
typedef struct bda_fs_find_data_like {
    void *cursor;              /* +0x000: findnext/findclose 使用并最终释放 */
    u32 size_or_aux04;         /* +0x004 */
    u32 attr_or_flags08;       /* +0x008 */
    u16 time_like0c;           /* +0x00c */
    u16 date_like0e;           /* +0x00e */
    s16 volume_index10;        /* +0x010: findnext/findclose 会先检查此索引 */
    char name_or_path12[0x20a]; /* +0x012..+0x21b */
    u32 aux21c;                /* +0x21c */
} bda_fs_find_data_like_t;

/*
 * FS+0x048 输出的 disk/storage 容量信息。C200 只取 drive 的低 8 位，当前确认
 * drive 0/1 两类路径；其他值返回 -1 并设置内部 error 9。成功路径只写这四个
 * word，其中 bytes_per_sector 固定写入 0x200。原机系统设置用 free_clusters *
 * sectors_per_cluster * bytes_per_sector 估算剩余空间。
 */
typedef struct bda_fs_disk_info_like {
    u32 total_clusters;
    u32 free_clusters;
    u32 sectors_per_cluster;
    u32 bytes_per_sector;
} bda_fs_disk_info_like_t;

/*
 * FS+0x054 输出的 path info 结构。C200 会写到 +0x14，因此固定 0x18 byte。
 * attr bit 0x4000 表示 directory-like；size_like 只在普通文件路径上可靠。
 * time_like* 字段来自 C200 内部转换，暂不命名为标准 FAT 时间。
 */
typedef struct bda_fs_path_info_like {
    s16 volume_index0;
    u16 attr_like;
    s16 volume_index4;
    u16 reserved6;
    u32 size_like;
    u32 time_like0c;
    u32 time_like10;
    u32 time_like14;
} bda_fs_path_info_like_t;

#define BDA_LOWORD(x) ((u32)(x) & 0xffffu)
#define BDA_HIWORD(x) (((u32)(x) >> 16) & 0xffffu)
#define BDA_MAKEWORD(lo, hi) ((((u32)(hi) & 0xffffu) << 16) | ((u32)(lo) & 0xffffu))

/*
 * 原机 window procedure 中观察到的 provisional message ID。callback 约定是
 * hwnd/message/wparam/lparam 对应 a0/a1/a2/a3。
 */
#define BDA_MSG_CREATE        0x0010u
#define BDA_MSG_TOUCH_COORDINATE 0x0001u
#define BDA_MSG_TOUCH_RELEASE    0x0002u
#define BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE 0x0060u
#define BDA_MSG_DRAW_CONTEXT_DETACH_LIKE 0x0066u
#define BDA_MSG_INPUT_BEGIN_LIKE 0x0010u
#define BDA_MSG_INPUT_DERIVED_LIKE 0x0011u
#define BDA_MSG_INPUT_END_LIKE 0x0013u
#define BDA_MSG_INPUT_END_DERIVED_LIKE 0x0014u
#define BDA_MSG_COMMAND_LIKE  0x083eu
#define BDA_MSG_TOUCH_A_LIKE  0x00b0u
#define BDA_MSG_REDRAW_INPUT_LIKE 0x00b1u
#define BDA_MSG_INPUT_0842_LIKE 0x0842u
#define BDA_MSG_KEYDOWN_LIKE  0x0844u
#define BDA_MSG_FOCUS_LIKE    0x0841u

/*
 * 在 message wparam 低/高 16 位中见到的 provisional command/control ID。
 * 保持原始保守命名，直到硬件 probe 能映射到精确 GUI message。
 */
#define BDA_CMD_LBUTTON_DOWN_LIKE 0x047eu
#define BDA_CMD_LBUTTON_UP_LIKE   0x047fu
#define BDA_CMD_PEN_AREA_LIKE     0x0501u

/*
 * runtime table 访问 helper。BDA_RUNTIME_BASE 前几个 word 是 GUI/FS/SYS/MEM/RES
 * table pointer；表内 offset 单位是 byte，bda_api() 返回该 slot 中的 function pointer。
 */
static inline void *bda_table(u32 addr) {
    return *(void **)addr;
}

static inline void *bda_api(void *table, u32 offset) {
    return *(void **)((u8 *)table + offset);
}

/*
 * low-level table call helper，用于 controlled probe 或复刻尚未封装的原机 table entry。
 * C ABI 会把前四个参数放入 MIPS a0..a3，第五/第六参数放在 caller stack；
 * 开发者应优先使用已命名 wrapper。
 */
static inline int bda_call0(void *table, u32 offset) {
    typedef int (*fn_t)(void);
    return ((fn_t)bda_api(table, offset))();
}

static inline int bda_call1(void *table, u32 offset, u32 a0) {
    typedef int (*fn_t)(u32);
    return ((fn_t)bda_api(table, offset))(a0);
}

static inline int bda_call2(void *table, u32 offset, u32 a0, u32 a1) {
    typedef int (*fn_t)(u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1);
}

static inline int bda_call3(void *table, u32 offset, u32 a0, u32 a1, u32 a2) {
    typedef int (*fn_t)(u32, u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1, a2);
}

static inline int bda_call4(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3) {
    typedef int (*fn_t)(u32, u32, u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1, a2, a3);
}

static inline int bda_call5(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3, u32 a4) {
    typedef int (*fn_t)(u32, u32, u32, u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1, a2, a3, a4);
}

static inline int bda_call6(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3, u32 a4, u32 a5) {
    typedef int (*fn_t)(u32, u32, u32, u32, u32, u32);
    return ((fn_t)bda_api(table, offset))(a0, a1, a2, a3, a4, a5);
}

/*
 * 固件 runtime table accessor。return value 来自 0x81c00004..0x81c00014 的 table pointer，
 * 不是可释放内存，也不要写入。
 */
static inline void *bda_gui_table(void) {
    return bda_table(BDA_GUI_TABLE_ADDR);
}

static inline void *bda_fs_table(void) {
    return bda_table(BDA_FS_TABLE_ADDR);
}

static inline void *bda_sys_table(void) {
    return bda_table(BDA_SYS_TABLE_ADDR);
}

static inline void *bda_mem_table(void) {
    return bda_table(BDA_MEM_TABLE_ADDR);
}

static inline void *bda_res_table(void) {
    return bda_table(BDA_RES_TABLE_ADDR);
}

/*
 * freestanding 环境下的最小 libc helper，避免依赖外部 libc 符号。
 */
static inline void *bda_memcpy(void *dst, const void *src, bda_size_t n) {
    u8 *d = (u8 *)dst;
    const u8 *s = (const u8 *)src;
    while (n--) {
        *d++ = *s++;
    }
    return dst;
}

static inline void *bda_memset(void *dst, int value, bda_size_t n) {
    u8 *d = (u8 *)dst;
    while (n--) {
        *d++ = (u8)value;
    }
    return dst;
}

static inline void bda_fs_find_data_init_like(bda_fs_find_data_like_t *find_data) {
    bda_memset(find_data, 0, sizeof(*find_data));
}

static inline bda_size_t bda_strlen(const char *s) {
    const char *p = s;
    while (*p) {
        ++p;
    }
    return (bda_size_t)(p - s);
}

/*
 * MEM 表分配器。MEM+0x000/+0x004 是 firmware debug/track alloc/free wrapper；
 * MEM+0x008/+0x00c 是基础 alloc/free。普通开发优先使用 bda_alloc()/bda_free()。
 * MEM+0x010 是 calloc-like helper，a0=count、a1=size；MEM+0x014 是 realloc-like
 * helper，a0=ptr、a1=new_size。释放必须用同一 MEM table 的 free，不要和 compiler
 * libc malloc/free 混用。
 */
static inline void *bda_track_alloc_like(bda_size_t size) {
    typedef void *(*alloc_fn)(bda_size_t size);
    alloc_fn alloc = (alloc_fn)bda_api(bda_mem_table(), BDA_MEM_TRACK_ALLOC_LIKE);
    return alloc(size);
}

static inline void bda_track_free_like(void *ptr) {
    typedef void (*free_fn)(void *ptr);
    free_fn freep = (free_fn)bda_api(bda_mem_table(), BDA_MEM_TRACK_FREE_LIKE);
    freep(ptr);
}

/*
 * Firmware heap tracking debug helpers。MEM+0x01c 开启 tracking 并清记录计数；
 * MEM+0x020 只读取记录表并返回当前记录计数；MEM+0x024 结束 tracking。
 * MEM+0x028/+0x02c 操作记录表中的 refcount-like 字段；release 递减到 0 时
 * 会调用基础 free helper 释放 pointer。如果 begin 时 free_on_finish 非 0，
 * finish 也可能释放仍记录的 pointer。
 * 普通开发不需要调用它们。
 */
static inline void bda_mem_track_begin_like(u32 free_on_finish) {
    (void)bda_call1(bda_mem_table(), BDA_MEM_TRACK_BEGIN_LIKE, free_on_finish);
}

static inline int bda_mem_track_report_like(u32 summary_only) {
    return bda_call1(bda_mem_table(), BDA_MEM_TRACK_REPORT_LIKE, summary_only);
}

static inline void bda_mem_track_finish_like(void) {
    (void)bda_call0(bda_mem_table(), BDA_MEM_TRACK_FINISH_LIKE);
}

static inline void *bda_mem_track_retain_like(void *ptr) {
    return (void *)bda_call1(bda_mem_table(), BDA_MEM_TRACK_RETAIN_LIKE, (u32)ptr);
}

static inline void bda_mem_track_release_like(void *ptr) {
    (void)bda_call1(bda_mem_table(), BDA_MEM_TRACK_RELEASE_LIKE, (u32)ptr);
}

static inline void *bda_alloc(bda_size_t size) {
    typedef void *(*alloc_fn)(bda_size_t size);
    alloc_fn alloc = (alloc_fn)bda_api(bda_mem_table(), BDA_MEM_ALLOC);
    return alloc(size);
}

static inline void bda_free(void *ptr) {
    typedef void (*free_fn)(void *ptr);
    free_fn freep = (free_fn)bda_api(bda_mem_table(), BDA_MEM_FREE);
    freep(ptr);
}

/*
 * Firmware heap calloc-like helper。C200 的 MEM+0x010 会按 count * align4(size)
 * 分配，并把实际分配区域清零；count==0 或 size==0 返回 0。它不做 C 标准库
 * calloc 的 overflow 语义保证，只用于 firmware heap。
 */
static inline void *bda_calloc_like(bda_size_t count, bda_size_t size) {
    typedef void *(*calloc_fn)(bda_size_t count, bda_size_t size);
    calloc_fn callocp = (calloc_fn)bda_api(bda_mem_table(), BDA_MEM_CALLOC_LIKE);
    return callocp(count, size);
}

/*
 * Firmware heap realloc-like helper。C200 的 MEM+0x014 行为：
 * - ptr==0 && new_size!=0：退化为 bda_alloc(new_size)。
 * - ptr!=0 && new_size==0：释放 ptr，返回 0。
 * - ptr!=0 && new_size!=0：分配新块，按 min(old_size, align4(new_size)) copy，
 *   再释放旧块；分配或旧块 size 查询失败时返回 0。
 * 只能传 firmware heap pointer，不要传 stack/static buffer 或 file handle。
 */
static inline void *bda_realloc_like(void *ptr, bda_size_t new_size) {
    typedef void *(*realloc_fn)(void *ptr, bda_size_t new_size);
    realloc_fn reallocp = (realloc_fn)bda_api(bda_mem_table(), BDA_MEM_REALLOC_LIKE);
    return reallocp(ptr, new_size);
}

/*
 * message box wrapper。开发者 API 使用 title,message 顺序；C200 实际 table entry 参数顺序
 * 是 parent,message,title,flags，这里已做转换。standalone app 可把它作为首个
 * GUI smoke；动态验证范围和复现步骤见 doc/verified/msgbox_api.md。
 */
static inline int bda_msgbox_ex(void *parent, const char *title, const char *message, u32 flags) {
    typedef int (*msgbox_fn)(void *parent, const char *message, const char *title, u32 flags);
    msgbox_fn msgbox = (msgbox_fn)bda_api(bda_gui_table(), BDA_GUI_MSGBOX);
    return msgbox(parent, message, title, flags);
}

static inline int bda_msgbox(const char *title, const char *message) {
    return bda_msgbox_ex(0, title, message, 0);
}

/*
 * control/window create wrapper。参数顺序来自 C200 和原机 call site；class_name 常见值包括
 * "butn"、"tbar"、"sbar"、"medit"。这个 wrapper 只固定 ABI；创建复杂 control
 * 仍需要真实 parent/frame lifecycle。不要在裸 bda_main() 中用 parent=0 创建
 * edit/listbox 当作 GUI bootstrap；这类 probe 已有真机重启记录。
 * 返回 handle 后才能在同一生命周期内 send/notify/destroy。
 */
static inline bda_handle_t bda_gui_create_window_like(
    const char *class_name,
    const char *caption,
    u32 style,
    u32 flags,
    u32 id,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    bda_handle_t parent,
    u32 extra
) {
    typedef bda_handle_t (*create_fn)(
        const char *class_name,
        const char *caption,
        u32 style,
        u32 flags,
        u32 id,
        s32 x,
        s32 y,
        s32 width,
        s32 height,
        bda_handle_t parent,
        u32 extra
    );
    create_fn create = (create_fn)bda_api(bda_gui_table(), BDA_GUI_CREATE);
    return create(class_name, caption, style, flags, id, x, y, width, height, parent, extra);
}

/*
 * 同步向 window/control 发送 message。C200 的 GUI+0x040 会直接调用 handle+0x88
 * wndproc；handle==0 时走 default callback，handle==-1 直接返回 -1。
 */
static inline int bda_gui_send(bda_handle_t handle, u32 message, u32 a, u32 b) {
    typedef int (*send_fn)(bda_handle_t handle, u32 message, u32 a, u32 b);
    send_fn send = (send_fn)bda_api(bda_gui_table(), BDA_GUI_SEND);
    return send(handle, message, a, b);
}

/*
 * 异步 notify/post。C200 的 GUI+0x03c 会把 handle,message,a,b 写入目标 frame
 * queue；message==0xb1 时只置 redraw/input pending flag。queue 满或无目标返回负值。
 */
static inline int bda_gui_notify_like(bda_handle_t handle, u32 message, u32 a, u32 b) {
    typedef int (*notify_fn)(bda_handle_t handle, u32 message, u32 a, u32 b);
    notify_fn notify = (notify_fn)bda_api(bda_gui_table(), BDA_GUI_NOTIFY_LIKE);
    return notify(handle, message, a, b);
}

/*
 * 销毁 control/object。C200 只处理 object kind=1 且 subtype=0x12 的 handle，
 * 先同步发送内部 0x64 message，再从 parent/manager 链接中摘除并释放资源。
 * 顶层 frame 仍用 bda_gui_close_frame_like()。
 */
static inline int bda_gui_destroy_like(bda_handle_t handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_DESTROY_LIKE, (u32)handle);
}

/*
 * 原机游戏路径中出现的 low-level framebuffer blit。C200 table entry 会把参数转发给
 * 全局 draw backend 的 +0x84 callback：x, y, height, width, buffer。
 * 注意 height 在 width 前；buffer 通常是 RGB565 pixel data。
 *
 * 真机反馈显示：在硬编码时间入口替换/no-template 上直接调用这组 blit，即使只在
 * 循环外统一 draw_guard_end，也会逐块 flip，完整绘制后可能死机。它依赖原机游戏
 * 已建立的 surface/context 生命周期；SDK 暂把它列为 unsafe probe API，不能作为
 * 可玩 tile 游戏或扫雷的绘图接口。
 */
static inline int bda_gui_blit_like(s32 x, s32 y, s32 height, s32 width, const void *buffer) {
    return bda_call5(bda_gui_table(), BDA_GUI_BLIT_LIKE, (u32)x, (u32)y, (u32)height, (u32)width, (u32)buffer);
}

/*
 * 分配并抓取一块 screen/backend region。C200 参数为 x,y,width,height，会按
 * width*height*bytes_per_pixel 调 bda_alloc()，再通过全局 draw backend +0x84 把区域
 * 写入新 buffer。返回的 buffer 必须用 bda_free() 释放；失败返回 0。注意这里是
 * width,height 顺序，不同于 blit_like 的 height,width,buffer。
 */
static inline void *bda_gui_capture_region_alloc_like(s32 x, s32 y, s32 width, s32 height) {
    return (void *)bda_call4(bda_gui_table(), BDA_GUI_CAPTURE_REGION_ALLOC_LIKE, (u32)x, (u32)y, (u32)width, (u32)height);
}

/*
 * alternate blit helper。C200 会先用全局 surface 宽高调用 draw backend 的
 * +0x44 clip/prepare callback，再把 x, y, height, width, buffer 转发给 +0x80。
 * 真机 TileBlit 反馈显示它不是独立可用的 high-level blit：在没有原机游戏
 * surface/context 的路径中会逐块 flip 并可能死机。仅用于复核 ABI 和原机路径，
 * 不要作为新 BDA 的绘图基础。雷霆战机/决战坦克的全屏路径是
 * GUI+0x3f8 -> GUI+0x6e0 -> GUI+0x400 -> MEM+0x00c，并非单独调用 +0x400。
 */
static inline int bda_gui_blit_alt_like(s32 x, s32 y, s32 height, s32 width, const void *buffer) {
    return bda_call5(bda_gui_table(), BDA_GUI_BLIT_ALT_LIKE, (u32)x, (u32)y, (u32)height, (u32)width, (u32)buffer);
}

/*
 * GUI+0x074 会把 a0 写入全局绘图/present guard 状态。原机常用
 * 1 -> draw -> 0 包围 draw 调用；a0==0 时 C200 还可能触发一次内部 present/update。
 * TouchStageV22 真机确认单独调用 a0=0 即使返回 0 也不会提交动态图元；V23 确认完整
 * 1/0 区间可以可靠提交十字与点阵坐标。因此 begin/end 必须作为一对使用。
 * 不要把 draw_guard_end_like() 放在逐 tile 循环中。当前真机 TileBlit 结果还显示：
 * 即使循环外只调用一次，缺少原机 surface/context 时也可能逐块刷新、白屏或死机。
 * 原机 game shell 中常见的是 GUI+0x414 render helper -> GUI+0x0e8 object draw end
 * -> GUI+0x074(0)，说明它依赖已建立的 object/draw context。
 */
static inline int bda_gui_pump_present_arg_like(u32 draw_guard_enabled) {
    return bda_call1(bda_gui_table(), BDA_GUI_PUMP_PRESENT_LIKE, draw_guard_enabled);
}

static inline int bda_gui_draw_guard_begin_like(void) {
    return bda_gui_pump_present_arg_like(1);
}

/*
 * draw_guard_end 会用 a0=0 调 GUI+0x074。它只结束配对的 guard，不是独立 present API。
 */
static inline int bda_gui_draw_guard_end_like(void) {
    return bda_gui_pump_present_arg_like(0);
}

/*
 * frame descriptor register wrapper。它不是单步显示 API，也不是硬编码时间入口下的
 * 通用 GUI bootstrap；调用者必须按真实 frame lifecycle 处理 create/activate/event
 * loop/close。优先使用 bda_gui_register_frame_desc_like() 保留 return type。
 */
static inline int bda_gui_register_frame_like(void *descriptor) {
    return bda_call1(bda_gui_table(), BDA_GUI_REGISTER_FRAME_LIKE, (u32)descriptor);
}

static inline bda_handle_t bda_gui_register_frame_desc_like(bda_frame_desc_like_t *descriptor) {
    return (bda_handle_t)bda_call1(bda_gui_table(), BDA_GUI_REGISTER_FRAME_LIKE, (u32)descriptor);
}

/*
 * 填一个能被 C200 GUI+0x084 接受的 frame descriptor。原机复杂应用常用
 * style=0x08000000 和 GUI+0x2fc(15) surface；普通 no-template frame probe 应先用
 * style=0/surface=0 收窄变量。真机反馈显示时间入口替换路径不是 GUI bootstrap，
 * 不能把 register_frame 当作无需 event loop 的安全绘图入口。需要完全复刻原机窗口
 * 行为时再显式改 style/surface。
 */
static inline void bda_frame_desc_init_like(
    bda_frame_desc_like_t *descriptor,
    const char *title,
    bda_wndproc_t wndproc,
    s32 width,
    s32 height,
    void *surface
) {
    u8 *p = (u8 *)descriptor;
    bda_size_t n = sizeof(*descriptor);
    while (n--) {
        *p++ = 0;
    }
    descriptor->style = 0;
    descriptor->title = title;
    descriptor->wndproc = wndproc;
    descriptor->height = height;
    descriptor->width = width;
    descriptor->surface = (u32)surface;
    descriptor->aux30 = 0;
}

/*
 * 停止/收尾 frame。C200 只读取 handle，会解析内部 frame object，向 child object 发送
 * 内部 0x66/0xf1 message 并释放若干关联资源；成功路径返回 1。
 */
static inline int bda_gui_frame_stop_like(bda_handle_t handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_FRAME_STOP_LIKE, (u32)handle);
}

/*
 * frame release/request wrapper。C200 会解析 handle 或 default frame slot，并给目标 object
 * 设置高位状态 flag；它不是释放内存的 close_frame，也不等价于普通 control destroy。
 */
static inline int bda_gui_frame_release_like(bda_handle_t handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_FRAME_RELEASE_LIKE, (u32)handle);
}

/*
 * default window procedure fallback。签名与 bda_wndproc_t 一致：handle,message,
 * wparam,lparam。C200 会处理一组 system message 和 0xb0..0xb3 input/redraw message；
 * 未处理 message 通常返回 0。custom wndproc 可把未消费的 message 交给它。
 */
static inline int bda_gui_default_proc_like(bda_handle_t handle, u32 message, u32 wparam, u32 lparam) {
    return bda_call4(bda_gui_table(), BDA_GUI_DEFAULT_PROC_LIKE, (u32)handle, message, wparam, lparam);
}

/*
 * 激活/状态切换 helper。C200 参数为 handle,mode；mode 0/0x10/0x100 等会走
 * 不同内部 message 路径。它不是普通 show flag setter。
 */
static inline int bda_gui_frame_activate_like(bda_handle_t handle, u32 mode) {
    return bda_call2(bda_gui_table(), BDA_GUI_FRAME_ACTIVATE_LIKE, (u32)handle, mode);
}

/*
 * event poll helper。message 必须指向 BDA_GUI_MESSAGE_SIZE(0x1c) byte buffer；
 * handle 通常是已注册且已进入 lifecycle 的 frame handle。传 0 走全局/default slot，
 * 但这不等价于创建 GUI 上下文，也不能让 bare bda_main() 变成稳定 event loop。
 */
static inline int bda_gui_event_poll_like(bda_gui_message_like_t *message, bda_handle_t handle) {
    return bda_call2(bda_gui_table(), BDA_GUI_EVENT_POLL_LIKE, (u32)message, (u32)handle);
}

/*
 * 全局/default frame slot poll。仅用于复刻原机已有 GUI 上下文或 controlled probe；
 * 新 BDA 不应把它当成无需 frame handle 的通用 message pump。
 */
static inline int bda_gui_event_poll_global_like(bda_gui_message_like_t *message) {
    return bda_gui_event_poll_like(message, 0);
}

/*
 * message loop step helper。C200 读取 a0=message_buffer，只在 message id 为
 * 0x10/0x13 时派生内部 0x11/0x14 message；不是无参数 pump。
 */
static inline int bda_gui_event_step_like(bda_gui_message_like_t *message) {
    return bda_call1(bda_gui_table(), BDA_GUI_EVENT_STEP_LIKE, (u32)message);
}

/*
 * dispatch helper。C200 会按 message buffer 中的 handle/message 调 wndproc；这要求
 * buffer 来自 event_poll 或按同一内部 layout 构造。不要手写一个短 struct 后直接 dispatch。
 */
static inline int bda_gui_event_dispatch_like(bda_gui_message_like_t *message) {
    return bda_call1(bda_gui_table(), BDA_GUI_EVENT_DISPATCH_LIKE, (u32)message);
}

/* Execute poll/step/dispatch for a specific registered frame. */
static inline int bda_gui_event_pump_frame_once_like(
    bda_gui_message_like_t *message,
    bda_handle_t frame
) {
    if (!bda_gui_event_poll_like(message, frame)) {
        return 0;
    }
    (void)bda_gui_event_step_like(message);
    (void)bda_gui_event_dispatch_like(message);
    return 1;
}

/*
 * Compatibility helper for original game shells that use the global/default
 * frame slot. A newly registered custom frame should use
 * bda_gui_event_pump_frame_once_like(message, frame) instead.
 */
static inline int bda_gui_event_pump_once_like(bda_gui_message_like_t *message) {
    return bda_gui_event_pump_frame_once_like(message, 0);
}

/*
 * 关闭并释放顶层 frame/window。C200 会清理 handle+0x8c、+0x44、+0x4c、
 * +0x74/+0x54 等关联 object，释放 frame 本体，并清空全局 frame record。该表项
 * 无稳定返回值；公开 SDK 的已验证 wrapper 使用 void bda_gui_close_frame(handle)。
 */
static inline int bda_gui_close_frame_like(bda_handle_t handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_CLOSE_FRAME_LIKE, (u32)handle);
}

/*
 * object refresh/notify wrapper。C200 先执行 object-specific prepare，再发送内部
 * 0xb1 message；旧的 op/arg 参数不会被该 table entry 读取。TouchStageV20 真机把
 * standalone 顶层 frame 传入后在 prepare 内死机，因此这里只能传原机已确认可刷新的
 * child object，不能作为通用 frame invalidate API。
 */
static inline int bda_gui_object_op_like(bda_handle_t object) {
    return bda_call1(bda_gui_table(), BDA_GUI_OBJECT_OP_LIKE, (u32)object);
}

/*
 * Rockchip GUI source calls this behavior WindowInvalidateWindow(). This alias
 * has the same child-object restriction as bda_gui_object_op_like(); it is not
 * safe for a standalone top-level frame and does not synchronously present.
 */
static inline int bda_gui_invalidate_window_like(bda_handle_t window) {
    return bda_gui_object_op_like(window);
}

/*
 * control/object draw 生命周期 wrapper。C200 的 +0x0e4 先要求 object kind halfword 为 1，
 * 再调用 GUI+0x308 对应函数取得 draw_handle，并递增 object+0x54+0x1c 的 draw 计数；
 * object+0x7c 存在时还会走附加描述符的准备路径。+0x0e8 必须传回同一个 object 和
 * begin 返回的 draw_handle，它会收尾 object 状态、递减 draw 计数，再调用 GUI+0x30c
 * 结束 draw context。应在 window callback 或已激活 frame 生命周期中调用；不要把它当作
 * 独立的 framebuffer/present API。雷霆战机/决战坦克样本里 +0x414 render helper
 * 后会接 +0x0e8(object, draw)，随后才调用 +0x074(0)。
 */
static inline bda_handle_t bda_gui_object_draw_begin_like(bda_handle_t handle) {
    return (bda_handle_t)bda_call1(bda_gui_table(), BDA_GUI_OBJECT_DRAW_BEGIN_LIKE, (u32)handle);
}

static inline void bda_gui_object_draw_end_like(bda_handle_t handle, bda_handle_t draw_handle) {
    (void)bda_call2(bda_gui_table(), BDA_GUI_OBJECT_DRAW_END_LIKE, (u32)handle, (u32)draw_handle);
}

/*
 * kind=1 object 的 +0x24 flags helper。get 失败返回 0；or/clear 成功返回 1，
 * 失败返回 0。or 只置位，clear 只清除 mask 对应 bit；它们不是 show/enable API。
 */
static inline u32 bda_gui_object_flags_get_like(bda_handle_t handle) {
    return (u32)bda_call1(bda_gui_table(), BDA_GUI_OBJECT_FLAGS_GET_LIKE, (u32)handle);
}

static inline int bda_gui_object_flags_or_like(bda_handle_t handle, u32 mask) {
    return bda_call2(bda_gui_table(), BDA_GUI_OBJECT_FLAGS_OR_LIKE, (u32)handle, mask);
}

static inline int bda_gui_object_flags_clear_like(bda_handle_t handle, u32 mask) {
    return bda_call2(bda_gui_table(), BDA_GUI_OBJECT_FLAGS_CLEAR_LIKE, (u32)handle, mask);
}

/*
 * kind=1 object 的两个 caller data word。C200 只检查 handle 非空且 *(s16*)handle==1；
 * get 失败返回 0，set 失败也返回 0；set 成功返回旧值。字段真实业务语义依赖
 * object/control 类型，SDK 只固定 +0x80/+0x84 两个 word 的 getter/setter ABI。
 */
static inline u32 bda_gui_object_userdata0_get_like(bda_handle_t handle) {
    return (u32)bda_call1(bda_gui_table(), BDA_GUI_OBJECT_USERDATA0_GET_LIKE, (u32)handle);
}

static inline u32 bda_gui_object_userdata0_set_like(bda_handle_t handle, u32 value) {
    return (u32)bda_call2(bda_gui_table(), BDA_GUI_OBJECT_USERDATA0_SET_LIKE, (u32)handle, value);
}

static inline u32 bda_gui_object_userdata1_get_like(bda_handle_t handle) {
    return (u32)bda_call1(bda_gui_table(), BDA_GUI_OBJECT_USERDATA1_GET_LIKE, (u32)handle);
}

static inline u32 bda_gui_object_userdata1_set_like(bda_handle_t handle, u32 value) {
    return (u32)bda_call2(bda_gui_table(), BDA_GUI_OBJECT_USERDATA1_SET_LIKE, (u32)handle, value);
}

/*
 * subtype=0x12 object 的 payload word。C200 要求 handle 非空、kind=1、subtype=0x12，
 * 然后通过 handle+0xec 指针访问 payload+0x1c。get 失败返回 0；set 成功返回旧值。
 * payload 结构仍未完整命名，调用前应确认 object 类型来自原机同类 control。
 */
static inline u32 bda_gui_object_payload_word_get_like(bda_handle_t handle) {
    return (u32)bda_call1(bda_gui_table(), BDA_GUI_OBJECT_PAYLOAD_WORD_GET_LIKE, (u32)handle);
}

static inline u32 bda_gui_object_payload_word_set_like(bda_handle_t handle, u32 value) {
    return (u32)bda_call2(bda_gui_table(), BDA_GUI_OBJECT_PAYLOAD_WORD_SET_LIKE, (u32)handle, value);
}

/*
 * kind=1 object 的 +0x8c pointer getter。C200 只读取 handle+0x8c；失败返回 0。
 * 相邻的 +0x0d4 setter 会按 subtype 分配/释放资源或发送 message，SDK 暂不公开。
 */
static inline void *bda_gui_object_resource_ptr_get_like(bda_handle_t handle) {
    return (void *)bda_call1(bda_gui_table(), BDA_GUI_OBJECT_RESOURCE_PTR_GET_LIKE, (u32)handle);
}

/*
 * kind=1 object 的 +0x88 pointer getter/setter。C200 setter 只有 value 非 0 时才写入，
 * 成功返回旧值；失败或 value==0 返回 0。这个字段接近 wndproc/callback 指针，
 * 不要在不了解 control lifecycle 时改写。
 */
static inline void *bda_gui_object_callback_ptr_get_like(bda_handle_t handle) {
    return (void *)bda_call1(bda_gui_table(), BDA_GUI_OBJECT_CALLBACK_PTR_GET_LIKE, (u32)handle);
}

static inline void *bda_gui_object_callback_ptr_set_like(bda_handle_t handle, void *value) {
    return (void *)bda_call2(bda_gui_table(), BDA_GUI_OBJECT_CALLBACK_PTR_SET_LIKE, (u32)handle, (u32)value);
}

/*
 * 从 object 向父级累加坐标原点。x/y 是 in/out 参数；调用后会被加上 object 层级 offset。
 */
static inline void bda_gui_accumulate_origin_like(bda_handle_t handle, s32 *x, s32 *y) {
    typedef void (*accumulate_origin_fn)(u32, s32 *, s32 *);
    accumulate_origin_fn fn = (accumulate_origin_fn)bda_api(bda_gui_table(), BDA_GUI_ACCUMULATE_ORIGIN_LIKE);
    fn((u32)handle, x, y);
}

/*
 * 从累计坐标反向减去 object 父链坐标原点。x/y 是 in/out 参数，必须是有效 pointer。
 */
static inline void bda_gui_subtract_origin_like(bda_handle_t handle, s32 *x, s32 *y) {
    typedef void (*subtract_origin_fn)(u32, s32 *, s32 *);
    subtract_origin_fn fn = (subtract_origin_fn)bda_api(bda_gui_table(), BDA_GUI_SUBTRACT_ORIGIN_LIKE);
    fn((u32)handle, x, y);
}

/*
 * 设置当前 active frame。C200 会读取/写入内部 manager +0xd8，并向旧 frame 发
 * 0x31、向新 frame 发 0x30；return value 来自内部 message/send 路径或 0，
 * 不是新 handle 本身的稳定别名。
 */
static inline int bda_gui_active_frame_set_like(bda_handle_t handle) {
    return bda_call1(bda_gui_table(), BDA_GUI_ACTIVE_FRAME_SET_LIKE, (u32)handle);
}

/*
 * 查询 context 所属 frame/container 的 active child。C200 会读取 a0=context：顶层
 * frame 直接使用自身，普通 object 先取 +0xcc parent，再返回 container+0xd8。
 * context 必须是有效 handle；把它当无参函数调用会让未定义的 a0 被解引用。
 */
static inline bda_handle_t bda_gui_active_child_get_like(bda_handle_t context) {
    return (bda_handle_t)bda_call1(
        bda_gui_table(), BDA_GUI_ACTIVE_FRAME_GET_LIKE, (u32)context
    );
}

/*
 * object update helper。C200 把参数写成 stack message packet 后通过 GUI+0x040 同步发送
 * 内部 0x162/0x163 message；参数语义依赖具体 control，SDK 只固定 ABI。
 */
static inline int bda_gui_object_update3_like(bda_handle_t handle, u32 a1, u32 a2) {
    return bda_call3(bda_gui_table(), BDA_GUI_OBJECT_UPDATE3_LIKE, (u32)handle, a1, a2);
}

static inline int bda_gui_object_update2_like(bda_handle_t handle, u32 a1) {
    return bda_call2(bda_gui_table(), BDA_GUI_OBJECT_UPDATE2_LIKE, (u32)handle, a1);
}

/*
 * 只读 object pair 查询。C200 扫描 0x804a6b40 起的 GUI 全局记录表，比较记录
 * +0/+4 两个 word 是否等于 a0/a1，命中返回 1，否则返回 0。它不验证 handle
 * 是否适合绘制，也不是通用 high-level exists API。
 */
static inline int bda_gui_object_pair_exists_like(u32 a0, u32 a1) {
    return bda_call2(bda_gui_table(), BDA_GUI_OBJECT_PAIR_EXISTS_LIKE, a0, a1);
}

/*
 * frame 级 draw 生命周期。C200 从 6 个 draw context slot 中取/初始化 context，
 * 并用 mode=1 调内部 helper；begin 返回 draw/surface handle，end 只接收该 handle。
 * 与 object_draw_begin/object_draw_end 不是同一组 ABI。handle 应来自有效 frame/window；
 * 在 bare bda_main()、硬编码时间入口替换或 create callback 早期阶段直接 begin_draw
 * 可能白屏、逐块刷新、重启或死机。
 */
static inline bda_handle_t bda_gui_begin_draw_like(bda_handle_t handle) {
    return (bda_handle_t)bda_call1(bda_gui_table(), BDA_GUI_BEGIN_DRAW_LIKE, (u32)handle);
}

/*
 * 结束 frame draw context。传入 begin_draw/current_draw 返回的 draw_handle；不是 frame handle。
 */
static inline void bda_gui_end_draw_like(bda_handle_t draw_handle) {
    (void)bda_call1(bda_gui_table(), BDA_GUI_END_DRAW_LIKE, (u32)draw_handle);
}

/*
 * flush 并释放 draw/surface context。C200 走 backend +0x34 后清理 context+0x94/+0xb0，
 * 再释放该 context；调用后不要继续复用这个 handle。
 */
static inline void bda_gui_surface_flush_like(bda_handle_t context) {
    (void)bda_call1(bda_gui_table(), BDA_GUI_SURFACE_FLUSH_LIKE, (u32)context);
}

/*
 * Query one of seven backend display metrics. C200 uses context=0 for its
 * default draw context and rejects metric >= 7 with -1. Thunder calls
 * metric=6 and multiplies the result by width*height before allocating its
 * temporary screen buffer, so metric 6 is the pixel byte-size factor on this
 * firmware. Keep the generic query name because the other metric indices are
 * not named yet.
 */
static inline int bda_gui_display_metric_like(bda_handle_t context, u32 metric) {
    return bda_call2(bda_gui_table(), BDA_GUI_DISPLAY_METRIC_LIKE, (u32)context, metric);
}

static inline int bda_gui_display_pixel_bytes_like(void) {
    return bda_gui_display_metric_like(0, BDA_GUI_DISPLAY_METRIC_PIXEL_BYTES_LIKE);
}

/*
 * Create a 0xd4-byte draw context compatible with source_context. C200 copies
 * the source drawable bounds and backend state into the new context. Release
 * it with bda_gui_surface_flush_like(); that call flushes and frees the object.
 * Both calls require an already valid game/window draw lifecycle.
 */
static inline bda_handle_t bda_gui_compat_context_create_like(bda_handle_t source_context) {
    return (bda_handle_t)bda_call1(
        bda_gui_table(), BDA_GUI_COMPAT_CONTEXT_CREATE_LIKE, (u32)source_context
    );
}

/*
 * 查询 low-level draw object/surface table。C200 只读取 kind/index；kind >= 0x11 返回 -1。
 * 原机 window descriptor 常用 kind=15 作为 surface/object，但该 object 仍依赖完整
 * frame lifecycle；不要把 bda_gui_draw_object_create_like(15)+register_frame 当成最小绘图 demo。
 * Thunder/Tank 还会查询 kind=7/8/15/0x10；其中 kind=0x10 的返回值会传给
 * set_fill/text_color，不是 game surface 或 context handle。
 */
static inline void *bda_gui_draw_object_create_like(u32 kind) {
    return (void *)bda_call1(bda_gui_table(), BDA_GUI_DRAW_OBJECT_CREATE_LIKE, kind);
}

/*
 * 取/初始化当前 draw handle。C200 会读取 a0=handle，从同一组 6 个 draw context
 * slot 中取/初始化 context，并以 mode=0 调内部 draw helper。与
 * begin_draw_like(handle) 相邻；后者使用 mode=1。它不是无参数 getter，也不会
 * 创建 frame/window 生命周期。Thunder/Tank 是在
 * BDA_MSG_DRAW_CONTEXT_ATTACH_LIKE 中用 callback 传入的 object 调用它，并保存
 * 返回 context；不要在裸 bda_main() 中自造 object。
 */
static inline bda_handle_t bda_gui_current_draw_like(bda_handle_t handle) {
    return (bda_handle_t)bda_call1(bda_gui_table(), BDA_GUI_CURRENT_DRAW_LIKE, (u32)handle);
}

/*
 * Select a pen/brush-like draw object into context+0x30 and return the old
 * object. Thunder saves the return value, performs primitive drawing, then
 * restores it with a second call. The exact object subtype still comes from
 * the firmware draw-object table, so arbitrary pointers are invalid.
 */
static inline void *bda_gui_select_draw_object_like(bda_handle_t context, void *object) {
    return (void *)bda_call2(
        bda_gui_table(), BDA_GUI_SELECT_DRAW_OBJECT_LIKE, (u32)context, (u32)object
    );
}

/*
 * 设置 draw context 的 resource/image slot。C200 参数为 context,value；context 为 0
 * 时使用 default context 0x80825690。wrapper 返回旧 context+0x20，再把 value 写入
 * context+0x20。它更像 current bitmap/resource setter，不负责创建或释放 object。
 * Thunder/Tank 样本里它后面紧接 bda_gui_region_draw_like(context, ...)，说明调用者
 * 已经持有有效 context。
 */
static inline int bda_gui_object_bind_like(u32 context, u32 value) {
    return bda_call2(bda_gui_table(), BDA_GUI_OBJECT_BIND_LIKE, context, value);
}

/*
 * 在 draw context 上写一个 pixel。C200 参数为 context,x,y,color；context 为 0 时
 * 使用 default context，随后按 origin/clipping 状态处理坐标，最终走 draw backend
 * 的 +0xb0 callback。color 应使用当前 context 可接受的内部颜色值。
 */
static inline int bda_gui_put_pixel_like(bda_handle_t context, s32 x, s32 y, u32 color) {
    return bda_call4(bda_gui_table(), BDA_GUI_PUT_PIXEL_LIKE, (u32)context, (u32)x, (u32)y, color);
}

/*
 * Direct RGB point primitive. C200 reads context,x,y,r,g,b, truncates each
 * component to 8 bits, converts through the active backend, then submits one
 * pixel. The last two o32 arguments are placed at stack+0x10/+0x14 by
 * bda_call6().
 */
static inline int bda_gui_put_pixel_rgb_like(
    bda_handle_t context,
    s32 x,
    s32 y,
    u32 red,
    u32 green,
    u32 blue
) {
    return bda_call6(
        bda_gui_table(), BDA_GUI_PUT_PIXEL_RGB_LIKE,
        (u32)context, (u32)x, (u32)y, red, green, blue
    );
}

/*
 * Primitive drawing ABI recovered from C200 and Thunder call pairs. move_to
 * writes context+0x34/+0x38. line_to saves the previous point, stores the new
 * endpoint, clips the segment and calls the backend. circle uses center/radius.
 * rectangle uses left,top,right,bottom; right/bottom are passed as the fifth
 * o32 stack argument where required. These need a valid draw context and a
 * selected firmware draw object.
 */
static inline void bda_gui_move_to_like(bda_handle_t context, s32 x, s32 y) {
    (void)bda_call3(bda_gui_table(), BDA_GUI_MOVE_TO_LIKE, (u32)context, (u32)x, (u32)y);
}

static inline void bda_gui_line_to_like(bda_handle_t context, s32 x, s32 y) {
    (void)bda_call3(bda_gui_table(), BDA_GUI_LINE_TO_LIKE, (u32)context, (u32)x, (u32)y);
}

static inline void bda_gui_circle_like(bda_handle_t context, s32 center_x, s32 center_y, s32 radius) {
    (void)bda_call4(
        bda_gui_table(), BDA_GUI_CIRCLE_LIKE,
        (u32)context, (u32)center_x, (u32)center_y, (u32)radius
    );
}

static inline void bda_gui_rectangle_like(
    bda_handle_t context, s32 left, s32 top, s32 right, s32 bottom
) {
    (void)bda_call5(
        bda_gui_table(), BDA_GUI_RECTANGLE_LIKE,
        (u32)context, (u32)left, (u32)top, (u32)right, (u32)bottom
    );
}

/*
 * Current font and cell metrics. +0x4a4 returns context+0x54. +0x4d0 reads
 * its primary cell-width field; +0x4d4 queries primary/fallback font height
 * callbacks and returns the larger value. Names remain _LIKE because the
 * complete font descriptor layout is not recovered.
 */
static inline void *bda_gui_current_font_like(bda_handle_t context) {
    return (void *)bda_call1(bda_gui_table(), BDA_GUI_CURRENT_FONT_LIKE, (u32)context);
}

static inline int bda_gui_font_cell_width_like(bda_handle_t context) {
    return bda_call1(bda_gui_table(), BDA_GUI_FONT_CELL_WIDTH_LIKE, (u32)context);
}

static inline int bda_gui_font_cell_height_like(bda_handle_t context) {
    return bda_call1(bda_gui_table(), BDA_GUI_FONT_CELL_HEIGHT_LIKE, (u32)context);
}

/*
 * 查询 object/default client rect。C200 参数为 handle,rect；rect 至少 16 byte。
 * handle=0 时复制 firmware default/global rect 并返回 1；有效 object(kind==1) 时写
 * x0=0,y0=0,x1=right-left,y1=bottom-top 并返回 1；无效 handle 返回 0。
 * 原机常把结果立刻传给 bda_gui_rect_contains_like() 做 hit test。
 */
static inline int bda_gui_object_rect_like(bda_handle_t handle, bda_rect_like_t *rect) {
    return bda_call2(bda_gui_table(), BDA_GUI_OBJECT_RECT_LIKE, (u32)handle, (u32)rect);
}

/*
 * render helper 簇中的 region draw wrapper。C200 使用 context,x,y,width,height 五参数，
 * 第五参数 height 放在 caller stack+0x10。函数会按当前 draw context 的 origin、
 * scaling 和 clipping 状态处理目标区域，并通过 draw backend 提交 clipped region。
 * 它不适合作为独立通用 rectangle draw API 使用。
 */
static inline int bda_gui_region_draw_like(bda_handle_t context, s32 x, s32 y, s32 width, s32 height) {
    return bda_call5(bda_gui_table(), BDA_GUI_REGION_DRAW_LIKE, (u32)context, (u32)x, (u32)y, (u32)width, (u32)height);
}

/*
 * 写入 16 byte rect record。C200 的 GUI+0x430 使用 rect,x0,y0,x1,y1 五参数，
 * 不排序、不 clipping，也不检查空 pointer。
 */
static inline void bda_gui_rect_prepare_like(bda_rect_like_t *rect, s32 x0, s32 y0, s32 x1, s32 y1) {
    (void)bda_call5(bda_gui_table(), BDA_GUI_RECT_PREPARE_LIKE, (u32)rect, (u32)x0, (u32)y0, (u32)x1, (u32)y1);
}

/*
 * 判断点是否落在 rect 内。该 helper 不需要 window handle，适合作为 GUI table smoke test。
 */
static inline int bda_gui_rect_contains_like(const bda_rect_like_t *rect, s32 x, s32 y) {
    return bda_call3(bda_gui_table(), BDA_GUI_RECT_CONTAINS_LIKE, (u32)rect, (u32)x, (u32)y);
}

/*
 * GUI+0x6b0 的 C200 table entry 无参数，直接返回内部 screen/framebuffer pointer。
 * 它不是 4 参数分配函数；真正的屏幕初始化逻辑在相邻内部函数中。这个 pointer
 * 属于 firmware display state，不是 SDK 分配的稳定 framebuffer；普通 BDA
 * 不要直接写入，也不要把它和 GUI+0x3f8/+0x400 拼成自定义 present 路径。
 */
static inline void *bda_gui_screen_buffer_like(void) {
    typedef void *(*screen_buffer_fn)(void);
    screen_buffer_fn fn = (screen_buffer_fn)bda_api(bda_gui_table(), BDA_GUI_SCREEN_BUFFER_LIKE);
    return fn();
}

/*
 * Invoke C200's raw-to-logical coordinate converter. It writes one u16 to
 * each output and clamps to 240x320. Static ABI is known; direct polling from
 * a custom BDA has not yet been dynamically validated.
 */
static inline void bda_gui_touch_position_like(u16 *x, u16 *y) {
    (void)bda_call2(
        bda_gui_table(),
        BDA_GUI_TOUCH_POSITION_LIKE,
        (u32)x,
        (u32)y
    );
}

/*
 * GAMEBOY 前端相关状态查询。C200 table entry 当前无参数，返回并更新内部状态 word。
 */
static inline int bda_gui_state_query_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_STATE_QUERY_LIKE);
}

/*
 * C200 当前直接返回 0x130，可作为 GUI table smoke test。
 */
static inline int bda_gui_screen_width_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_SCREEN_WIDTH_LIKE);
}

/*
 * Firmware-bound pen GPIO query for the kj409588/C200 image. This is not a
 * runtime-table entry and must not be assumed portable to another firmware.
 */
static inline int bda_touch_pressed_9588(void) {
    typedef int (*touch_pressed_fn)(void);
    touch_pressed_fn fn = (touch_pressed_fn)0x80059f68u;
    return fn();
}

/*
 * GAMEBOY/input 事件获取 helper。C200 的 ABI 是两个 s32 output pointer；
 * SDK 包成 typed result，避免调用侧写反 code/value。
 */
static inline int bda_gui_event_fetch_like(bda_gui_event_fetch_like_t *out_event) {
    typedef int (*event_fetch_fn)(s32 *out_code, s32 *out_value);
    event_fetch_fn fn = (event_fetch_fn)bda_api(bda_gui_table(), BDA_GUI_EVENT_FETCH_LIKE);
    return fn(&out_event->code, &out_event->value);
}

/*
 * GAMEBOY/input 按键包 helper。C200 会先清零 BDA_GUI_INPUT_PACKET_SIZE byte
 * 再写入按键状态。
 */
static inline int bda_gui_input_packet_like(bda_gui_input_packet_like_t *packet) {
    return bda_call1(bda_gui_table(), BDA_GUI_INPUT_PACKET_LIKE, (u32)packet);
}

static inline int bda_gui_input_packet_key_pressed_like(
    const bda_gui_input_packet_like_t *packet,
    u32 keycode
) {
    u32 index;
    switch (keycode) {
        case BDA_KEY_DOWN: index = BDA_INPUT_PACKET_DOWN_INDEX; break;
        case BDA_KEY_LEFT: index = BDA_INPUT_PACKET_LEFT_INDEX; break;
        case BDA_KEY_RIGHT: index = BDA_INPUT_PACKET_RIGHT_INDEX; break;
        case BDA_KEY_UP: index = BDA_INPUT_PACKET_UP_INDEX; break;
        case BDA_KEY_ESCAPE: index = BDA_INPUT_PACKET_ESCAPE_INDEX; break;
        case BDA_KEY_ENTER: index = BDA_INPUT_PACKET_ENTER_INDEX; break;
        default: return 0;
    }
    return packet->bytes[index] == 1u;
}

/*
 * Poll one physical key without a window or event loop. Eros uses this exact
 * GUI+0x5d4 packet query for all six built-in keys.
 */
static inline int bda_gui_key_pressed_like(u32 keycode) {
    bda_gui_input_packet_like_t packet;
    (void)bda_gui_input_packet_like(&packet);
    return bda_gui_input_packet_key_pressed_like(&packet, keycode);
}

/*
 * game/display 状态推进 helper。C200 table entry 无参数；内部检查时间/状态阈值
 * 0x1068，必要时写全局 display state 并调用 update helper。GAMEBOY、雷霆战机、
 * 决战坦克的 screen/blit 路径附近都出现该入口。return value 是状态推进结果，
 * 不是 framebuffer pointer，也不是 blit status getter。Thunder/Tank 的全屏 buffer
 * 路径在 +0x3f8 后调用它，并只在特定返回路径继续 +0x400 和释放临时 buffer。
 */
static inline int bda_gui_game_display_pump_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_GAME_DISPLAY_PUMP_LIKE);
}

/*
 * image file decode wrapper。out 指向 bda_picture_like_t；BMP table entry 的 out_source_buffer
 * 是一个 output pointer slot。C200 的 VX 快路径会把读取到的 file buffer 写回
 * *out_source_buffer，其他路径通常写 0；不要传 NULL。
 */
static inline int bda_gui_decode_bmp_like(void *owner, bda_picture_like_t *out, const char *path, void **out_source_buffer) {
    return bda_call4(bda_gui_table(), BDA_GUI_DECODE_BMP_LIKE, (u32)owner, (u32)out, (u32)path, (u32)out_source_buffer);
}

/*
 * JPEG table entry 会把 mode 截成 signed 8-bit；mode==1 先走 path/format check，其他
 * mode 直接进入 JPEG decoder。return value 来自内部 decoder/错误路径。
 */
static inline int bda_gui_decode_jpeg_like(void *owner, bda_picture_like_t *out, const char *path, u32 mode) {
    return bda_call4(bda_gui_table(), BDA_GUI_DECODE_JPEG_LIKE, (u32)owner, (u32)out, (u32)path, mode);
}

/*
 * file selector open/session wrapper。C200 只从 a0 读取 mode，不接收 selector/descriptor
 * pointer；descriptor 和 modal frame 都由系统内部 stack/global 状态构造。
 * 已确认 mode 0/1/2/3 会选择不同的内部状态 byte，return value 来自对应 selector 状态。
 */
static inline int bda_gui_file_selector_open_like(u32 mode) {
    return bda_call1(bda_gui_table(), BDA_GUI_FILE_SELECTOR_OPEN_LIKE, mode);
}

/*
 * GUI+0x6c8 的 C200 table entry 无参数，只调用内部 selector pump helper。
 * selector 描述符仍由 open/update 内部全局状态间接使用，不通过 a0 传入。
 */
static inline int bda_gui_file_selector_update_like(void) {
    return bda_call0(bda_gui_table(), BDA_GUI_FILE_SELECTOR_UPDATE_LIKE);
}

/*
 * GUI+0x6b8 不是无参数“获取选择结果”wrapper。C200 读取 a0=head、a1=index，
 * 沿 linked list +0x04 pointer 返回第 index 项；当前仅作为 low-level helper 暴露。
 */
static inline void *bda_gui_list_nth_like(void *head, s32 index) {
    typedef void *(*list_nth_fn)(void *head, s32 index);
    list_nth_fn fn = (list_nth_fn)bda_api(bda_gui_table(), BDA_GUI_LIST_NTH_LIKE);
    return fn(head, index);
}

/*
 * GUI+0x6bc 不是无参数 file selector close。C200 table entry 直接 tail into
 * 0x8003e868(head)，该 helper 按 linked list 释放节点和节点里的 data pointer。
 * 传 NULL 是 no-op；不要用旧的 no-arg wrapper。
 */
static inline void bda_gui_list_free_like(void *head) {
    (void)bda_call1(bda_gui_table(), BDA_GUI_LIST_FREE_LIKE, (u32)head);
}

/*
 * draw color/text state helper。handle 为 0 时 C200 使用 default draw context
 * 0x80825690；非 0 时使用调用者传入的 draw/context。set_fill/text_mode/
 * text_color 会写入 context 字段并返回旧值。
 * Thunder/Tank 中有 `bda_gui_draw_object_create_like(0x10)` 后接 fill/text color
 * setter 的序列；这里的返回值应看作 firmware table 中的 color-like value，
 * 不能解释为 surface/context handle。
 */
static inline int bda_gui_set_fill_color_like(bda_handle_t handle, u32 color) {
    return bda_call2(bda_gui_table(), BDA_GUI_SET_FILL_COLOR_LIKE, (u32)handle, color);
}

static inline int bda_gui_set_text_mode_like(bda_handle_t handle, u32 mode) {
    return bda_call2(bda_gui_table(), BDA_GUI_SET_TEXT_MODE_LIKE, (u32)handle, mode);
}

/*
 * 用 draw/context 的 color conversion callback 生成内部颜色值。C200 只取 r/g/b 的低 8 位；
 * return value 不是裸 RGB565 常量，通常再传给 set_fill/text_color。
 */
static inline int bda_gui_rgb_like(bda_handle_t handle, u32 r, u32 g, u32 b) {
    return bda_call4(bda_gui_table(), BDA_GUI_RGB_LIKE, (u32)handle, r, g, b);
}

static inline int bda_gui_set_text_color_like(bda_handle_t handle, u32 color) {
    return bda_call2(bda_gui_table(), BDA_GUI_SET_TEXT_COLOR_LIKE, (u32)handle, color);
}

/*
 * text draw helper。C200 参数为 handle,x,y,text,extra；extra==0 直接返回 0，
 * extra<0 时按 bda_strlen(text) 计算长度。text 通常为 GBK/ASCII 字符串。
 * 需要有效 draw/context；不要在 bare bda_main() 中用 handle=0 做 probe。
 */
static inline int bda_gui_draw_text_like(bda_handle_t handle, s32 x, s32 y, const char *text, s32 extra) {
    return bda_call5(bda_gui_table(), BDA_GUI_DRAW_TEXT_LIKE, (u32)handle, (u32)x, (u32)y, (u32)text, (u32)extra);
}

/*
 * 绘制完整 VX resource block。C200 的 GUI+0x540 ABI 会从第 6 个参数读取
 * vx_resource，但实际 width/height 来自 VX header 的 +0x06/+0x0a；旧 wrapper
 * 暴露的 width/height 不会控制缩放。SDK 因此只暴露 handle,x,y,vx_resource。
 */
static inline int bda_gui_draw_vx_like(bda_handle_t handle, s32 x, s32 y, const void *vx_resource) {
    return bda_call6(
        bda_gui_table(),
        BDA_GUI_DRAW_VX_LIKE,
        (u32)handle,
        (u32)x,
        (u32)y,
        0,
        0,
        (u32)vx_resource
    );
}

/*
 * RES+0x094 在元素周期表中表现为 printf/trace-style table entry，不是 DLX loader。
 */
static inline int bda_res_entry_094_like(const char *text_or_path, void *arg) {
    typedef int (*entry_fn)(const char *text_or_path, void *arg);
    entry_fn fn = (entry_fn)bda_api(bda_res_table(), BDA_RES_ENTRY_094_LIKE);
    return fn(text_or_path, arg);
}

static inline int bda_res_trace_like(const char *format, void *arg) {
    return bda_res_entry_094_like(format, arg);
}

/*
 * RES 状态读取 helper。out_state 至少需要 bda_res_state_like_t 大小。
 * C200 table entry 只写 out_state；尾部调用 unlock stub，不提供稳定 return value。
 */
static inline void bda_res_get_state_like(bda_res_state_like_t *out_state) {
    typedef void (*get_state_fn)(bda_res_state_like_t *out_state);
    get_state_fn fn = (get_state_fn)bda_api(bda_res_table(), BDA_RES_GET_STATE_LIKE);
    fn(out_state);
}

/*
 * file selector descriptor 初始化。这个 helper 只填 struct；open/update/close 仍通过
 * file_selector_open/update/close 这组全局 selector wrapper 完成。
 */
static inline void bda_file_selector_init_like(
    bda_file_selector_like_t *selector,
    char *out_path,
    const char *extensions,
    void *dir_state,
    const char *title
) {
    bda_memset(selector, 0, sizeof(*selector));
    selector->out_path = out_path;
    selector->extensions = extensions;
    selector->dir_state = dir_state;
    selector->title = title;
    selector->sentinel1c = -1;
    selector->sentinel20 = -1;
    selector->sentinel24 = -1;
    selector->sentinel34 = (u32)-1;
    selector->sentinel38 = (u32)-1;
    selector->list_limit40 = 0x1000;
    selector->sentinel48 = -1;
    selector->result64 = 0;
}

/*
 * fopen-style wrapper。成功值是高地址 file-object pointer，作为 signed int 时通常
 * 为负数；失败值是 0 或 0xffffffff。使用 bda_fs_file_is_valid() 判断。
 */
static inline int bda_fs_fopen_raw(const char *path, const char *mode) {
    typedef int (*open_fn)(const char *path, const char *mode);
    open_fn openp = (open_fn)bda_api(bda_fs_table(), BDA_FS_OPEN);
    return openp(path, mode);
}

static inline int bda_fs_file_is_valid(int file) {
    return file != 0 && (u32)file != 0xffffffffu;
}

/*
 * fclose-style wrapper。C200 只读取 a0=file，进入内部 close helper 后返回其结果。
 * 只关闭 bda_fs_fopen_raw() 成功返回的 fd。
 */
static inline int bda_fs_close_raw(int fd) {
    typedef int (*close_fn)(int fd);
    close_fn closep = (close_fn)bda_api(bda_fs_table(), BDA_FS_CLOSE);
    return closep(fd);
}

/*
 * fread/fwrite 风格 raw IO。C200 参数顺序是 buffer,size,count,file；file
 * 是 a3。handle index 非法或 filesystem backend 未就绪时返回 0，不是 -1。size/count
 * 乘积由调用者负责控制，file 必须是 bda_fs_fopen_raw() 返回的有效 fd。
 */
static inline int bda_fs_fread_raw(void *buffer, bda_size_t size, bda_size_t count, int file) {
    typedef int (*read_fn)(void *buffer, bda_size_t size, bda_size_t count, int file);
    read_fn readp = (read_fn)bda_api(bda_fs_table(), BDA_FS_READ);
    return readp(buffer, size, count, file);
}

/*
 * 便捷 read wrapper。return value 为底层 fread-like 调用结果，0 表示没有读到数据或失败。
 */
static inline int bda_fs_read_raw(int file, void *buffer, bda_size_t size) {
    return bda_fs_fread_raw(buffer, 1, size, file);
}

/*
 * 破坏性 raw write。参数顺序同 C200 table entry：buffer,size,count,file；便捷
 * bda_fs_write_raw() 才是 file,buffer,size。只对明确以写模式打开的有效 fd 调用，
 * 并检查 return value 是否等于期望写入数量；不要在只读 probe 中调用。
 */
static inline int bda_fs_fwrite_raw(const void *buffer, bda_size_t size, bda_size_t count, int file) {
    typedef int (*write_fn)(const void *buffer, bda_size_t size, bda_size_t count, int file);
    write_fn writep = (write_fn)bda_api(bda_fs_table(), BDA_FS_WRITE);
    return writep(buffer, size, count, file);
}

/* 便捷 write wrapper。它仍会修改存储；失败/部分写入时按底层 fwrite-like return value 判断。 */
static inline int bda_fs_write_raw(int file, const void *buffer, bda_size_t size) {
    return bda_fs_fwrite_raw(buffer, 1, size, file);
}

/*
 * fseek-style wrapper。C200 参数顺序是 file,offset,whence；whence 只接受
 * BDA_SEEK_SET/BDA_SEEK_CUR/BDA_SEEK_END，其他值返回 -1。
 */
static inline int bda_fs_seek_raw(int file, s32 offset, int whence) {
    typedef int (*seek_fn)(int file, s32 offset, int whence);
    seek_fn seekp = (seek_fn)bda_api(bda_fs_table(), BDA_FS_SEEK);
    return seekp(file, offset, whence);
}

/*
 * ftell-style wrapper。C200 会先检查 file handle object +0x48 的 16-bit index；
 * 索引非法或 backend 未就绪时返回 0，并设置内部错误码。有效路径返回 +0x44
 * 的当前位置/size-like word，常与 seek END 配合取文件大小。
 */
static inline int bda_fs_tell_raw(int file) {
    typedef int (*tell_fn)(int file);
    tell_fn tellp = (tell_fn)bda_api(bda_fs_table(), BDA_FS_TELL);
    return tellp(file);
}

/*
 * file 状态 helper。C200 的 FS+0x018/+0x01c/+0x020 都先检查 file+0x48
 * index 和 backend pointer。eof_like() 通过 file+0x44 当前位置和 file+0x20
 * size-like word 判断是否到末尾；error_like() 读取 file+0x4a 的 0x1000 flag；
 * clear_error_like() 清掉同一个 flag。file 必须是有效 fopen handle。
 */
static inline int bda_fs_eof_like(int file) {
    typedef int (*eof_fn)(int file);
    eof_fn eofp = (eof_fn)bda_api(bda_fs_table(), BDA_FS_EOF_LIKE);
    return eofp(file);
}

static inline int bda_fs_error_like(int file) {
    typedef int (*error_fn)(int file);
    error_fn errorp = (error_fn)bda_api(bda_fs_table(), BDA_FS_ERROR_LIKE);
    return errorp(file);
}

static inline int bda_fs_clear_error_like(int file) {
    typedef int (*clear_error_fn)(int file);
    clear_error_fn clear_error = (clear_error_fn)bda_api(bda_fs_table(), BDA_FS_CLEAR_ERROR_LIKE);
    return clear_error(file);
}

/*
 * 破坏性删除：删除 path 指向的文件。C200 的 FS+0x024 只读取 a0=path，内部会申请
 * 0x20a byte 临时 path buffer 并解析路径；失败返回 -1。path encoding 和 fopen 相同，
 * 通常使用 GBK/ASCII。不要传 directory path、空 pointer 或未终止字符串。
 */
static inline int bda_fs_remove_raw(const char *path) {
    return bda_call1(bda_fs_table(), BDA_FS_REMOVE, (u32)path);
}

/*
 * 破坏性 rename/move：把 old_path 指向的文件或目录项重命名为 new_path。
 * C200 会分别解析两个 path，要求 backend 可用，并调用内部 rename helper。
 * 不要跨不确定 volume 使用；失败通常返回 -1 并设置内部错误码。
 */
static inline int bda_fs_rename_like(const char *old_path, const char *new_path) {
    return bda_call2(bda_fs_table(), BDA_FS_RENAME_LIKE, (u32)old_path, (u32)new_path);
}

/*
 * directory wrapper。FS+0x02c 会解析 path 并检查 directory attr bit 0x4000，成功后更新
 * current directory state；NULL 返回 -1，空字符串返回 0。FS+0x030 解析 path 后走内部
 * mkdir helper，会修改 filesystem。path encoding 通常是 GBK/ASCII。
 */
static inline int bda_fs_chdir_like(const char *path) {
    return bda_call1(bda_fs_table(), BDA_FS_CHDIR_LIKE, (u32)path);
}

static inline int bda_fs_mkdir_like(const char *path) {
    return bda_call1(bda_fs_table(), BDA_FS_MKDIR_LIKE, (u32)path);
}

/*
 * rmdir/remove-directory helper，会修改 filesystem。C200 的 FS+0x034 只读取 a0=path，
 * 解析后调用内部 directory removal helper。只传空目录 path；不要传 file path、
 * NULL 或未终止字符串。
 */
static inline int bda_fs_rmdir_like(const char *path) {
    return bda_call1(bda_fs_table(), BDA_FS_RMDIR_LIKE, (u32)path);
}

/*
 * directory enumeration wrapper。find_data 必须至少是 bda_fs_find_data_like_t 大小，并建议先用
 * bda_fs_find_data_init_like() 清零；findfirst 会申请 0x20a byte 临时 path buffer，
 * 解析 pattern 后调用内部 helper 写回 find_data；成功后用 findclose 收尾。
 * C200 的 findnext/findclose 都读取 find_data+0x10 的 volume index；findnext
 * 调内部 helper 更新下一项，findclose 会释放 find_data+0x00 cursor，不能当作
 * 可省略的 no-op。
 */
static inline int bda_fs_findfirst_like(const char *pattern, u32 attr, bda_fs_find_data_like_t *find_data) {
    return bda_call3(bda_fs_table(), BDA_FS_FINDFIRST_LIKE, (u32)pattern, attr, (u32)find_data);
}

/* 更新 find_data 到下一项；失败/结束通常返回 -1，index/backend 错误也返回 -1。 */
static inline int bda_fs_findnext_like(bda_fs_find_data_like_t *find_data) {
    return bda_call1(bda_fs_table(), BDA_FS_FINDNEXT_LIKE, (u32)find_data);
}

/* 释放 findfirst 分配/绑定的 cursor；失败时返回 -1，并可能设置内部错误码 9/0x10。 */
static inline int bda_fs_findclose_like(bda_fs_find_data_like_t *find_data) {
    return bda_call1(bda_fs_table(), BDA_FS_FINDCLOSE_LIKE, (u32)find_data);
}

/*
 * 读取磁盘容量信息。C200 只使用 drive & 0xff，当前确认 drive=0/1；其他值返回 -1。
 * 成功后可用 bda_fs_disk_free_bytes_like() 做原机兼容的 32-bit 估算；
 * 新代码需要实际剩余 byte 数时优先用 bda_fs_disk_free_bytes64_like()。
 */
static inline int bda_fs_diskinfo_like(u32 drive, bda_fs_disk_info_like_t *info) {
    return bda_call2(bda_fs_table(), BDA_FS_DISKINFO_LIKE, drive, (u32)info);
}

static inline u32 bda_fs_disk_free_bytes_like(const bda_fs_disk_info_like_t *info) {
    return info->free_clusters * info->sectors_per_cluster * info->bytes_per_sector;
}

static inline u64 bda_fs_disk_free_bytes64_like(const bda_fs_disk_info_like_t *info) {
    return (u64)info->free_clusters * (u64)info->sectors_per_cluster * (u64)info->bytes_per_sector;
}

/*
 * current directory getter。C200 的 FS+0x050 使用 buffer,size，返回写入当前路径所需
 * byte 数（含 drive 前缀和 NUL）。buffer 为 NULL 或 size 太小时仍返回 required size；
 * 成功写入形态类似 "A:\\" 或 "A:\\dir"。只读 helper，不会切换目录。
 */
static inline int bda_fs_getcwd_like(char *buffer, bda_size_t size) {
    return bda_call2(bda_fs_table(), BDA_FS_GETCWD_LIKE, (u32)buffer, size);
}

static inline void bda_fs_path_info_init_like(bda_fs_path_info_like_t *info) {
    bda_memset(info, 0, sizeof(*info));
}

/*
 * path info getter。C200 的 FS+0x054 使用 path,info，先申请 0x20a byte 临时 path
 * buffer 解析路径，再填充 bda_fs_path_info_like_t。失败通常返回 -1；info 不能为空。
 */
static inline int bda_fs_path_info_like(const char *path, bda_fs_path_info_like_t *info) {
    return bda_call2(bda_fs_table(), BDA_FS_PATH_INFO_LIKE, (u32)path, (u32)info);
}

static inline int bda_fs_path_info_is_dir_like(const bda_fs_path_info_like_t *info) {
    return (info->attr_like & 0x4000u) != 0;
}

static inline u32 bda_fs_path_info_size_like(const bda_fs_path_info_like_t *info) {
    return info->size_like;
}

/*
 * path/flags 存在性或属性检查。C200 的 FS+0x06c wrapper 只使用 a0=path、a1=flags；
 * 没有读取 a2，也不会向调用者填充 stat 结构。
 */
static inline int bda_fs_stat_like(const char *path, u32 flags) {
    return bda_call2(bda_fs_table(), BDA_FS_STAT_LIKE, (u32)path, flags);
}

/*
 * Raw media-present bit 查询。C200 的 FS+0x078 不读取 a0..a3，调用底层 helper
 * 后返回 0/1；内部路径会读取 0xb0010300 的 0x01000000 bit。它比
 * bda_fs_storage_ready_like() 更 low-level，不保证具体 FS 操作一定可用。
 */
static inline int bda_fs_media_present_raw_like(void) {
    return bda_call0(bda_fs_table(), BDA_FS_MEDIA_PRESENT_RAW_LIKE);
}

/*
 * 无参数存储介质就绪查询。C200 的 FS+0x07c 不读取 a0..a3，只返回内部检测
 * 结果的低 8 位；适合在进入文件读写/枚举流程前做轻量检查。
 */
static inline int bda_fs_storage_ready_like(void) {
    return bda_call0(bda_fs_table(), BDA_FS_STORAGE_READY_LIKE);
}

/*
 * GAMEBOY.BDA 使用的 raw audio open/init wrapper。C200 只读取 a0=device、
 * a1=format、a2=channels；format/channels 会截成 signed 8-bit，未见 a3 读取。
 * 函数尾部固定返回 0，SDK 暴露为 void，普通 UI 程序不需要调用它。
 */
static inline void bda_sys_audio_open_like(u32 device, u32 format, u32 channels) {
    (void)bda_call3(bda_sys_table(), BDA_SYS_AUDIO_OPEN_LIKE, device, format, channels);
}

/*
 * raw audio ready query。C200 table entry 无参数，读取 `0x8058+0x6e8`，返回该 queue
 * 计数是否大于 0 的 bool 值。
 */
static inline int bda_sys_audio_ready_like(void) {
    return bda_call0(bda_sys_table(), BDA_SYS_AUDIO_READY_LIKE);
}

/*
 * 向 raw audio 后端写入 bytes byte。调用前应确认 audio_ready/open 状态，
 * 避免在普通消息循环里阻塞或写入无效 buffer。C200 bytes<=0 返回 -1；
 * 正常路径按最多 0x8000 byte chunk 提交，return value 是已消费 byte 数。
 */
static inline int bda_sys_audio_write_like(const void *buffer, bda_size_t bytes) {
    return bda_call2(bda_sys_table(), BDA_SYS_AUDIO_WRITE_LIKE, (u32)buffer, bytes);
}

/*
 * raw keycode query。C200 的 SYS+0x088 无参数，直接读取硬件输入寄存器并返回
 * raw code；当前只确认返回值形状，不把 code 过早命名为具体按键。
 */
static inline int bda_sys_keycode_raw_like(void) {
    return bda_call0(bda_sys_table(), BDA_SYS_KEYCODE_RAW_LIKE);
}

static inline void bda_sys_audio_reset_like(void) {
    typedef void (*reset_fn)(void);
    reset_fn fn = (reset_fn)bda_api(bda_sys_table(), BDA_SYS_AUDIO_RESET_LIKE);
    fn();
}

/*
 * raw audio reset/flush 没有稳定 return value 约定，因此 wrapper 是 void。
 */
static inline void bda_sys_audio_flush_like(void) {
    typedef void (*flush_fn)(void);
    flush_fn fn = (flush_fn)bda_api(bda_sys_table(), BDA_SYS_AUDIO_FLUSH_LIKE);
    fn();
}

/*
 * raw audio 内部 state pointer getter。C200 的 SYS+0x090 不读取参数，直接返回
 * 固件全局结构 0x80362830；用于 probe/状态观察，不要写入该结构，也不要把它当作
 * high-level 播放器对象或 audio open API。
 */
static inline void *bda_sys_audio_state_like(void) {
    typedef void *(*state_fn)(void);
    state_fn fn = (state_fn)bda_api(bda_sys_table(), BDA_SYS_AUDIO_STATE_LIKE);
    return fn();
}

/*
 * 原机游戏的打包音效操作簇。descriptor/slot 布局未完全确认，因此只暴露
 * 按 offset 命名的 low-level wrapper；不要把它们当作稳定的 high-level sound API。
 * OP40 会把 sound_id clamp 到 0..0x62 后写入固件全局状态；OP44 不读取参数，
 * 只触发内部 helper。二者都没有稳定 return value。
 */
static inline void bda_sys_package_sound_op40_like(u32 sound_id) {
    (void)bda_call1(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP40_LIKE, sound_id);
}

static inline void bda_sys_package_sound_op44_like(void) {
    (void)bda_call0(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP44_LIKE);
}

static inline int bda_sys_package_sound_op58_like(const void *descriptor) {
    return bda_call1(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP58_LIKE, (u32)descriptor);
}

static inline int bda_sys_package_sound_op5c_like(u32 slot, const void *descriptor, u32 a2, u32 flags) {
    return bda_call4(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP5C_LIKE, slot, (u32)descriptor, a2, flags);
}

static inline int bda_sys_package_sound_op60_like(void) {
    return bda_call0(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP60_LIKE);
}

static inline int bda_sys_package_sound_op64_like(void) {
    return bda_call0(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP64_LIKE);
}

static inline int bda_sys_package_sound_op68_like(void) {
    return bda_call0(bda_sys_table(), BDA_SYS_PACKAGE_SOUND_OP68_LIKE);
}

/*
 * 阻塞式 busy-wait delay。C200 会读取系统校准值，把 a0 换算成循环次数后
 * 原地忙等；不要在 GUI 主消息循环里长时间调用。该 wrapper 不提供稳定 return value。
 */
static inline void bda_sys_delay_like(u32 delay_units) {
    (void)bda_call1(bda_sys_table(), BDA_SYS_DELAY_LIKE, delay_units);
}

/*
 * timer/rate preset 选择。C200 会把 a0 clamp 到 0..14，然后按 index 读取 firmware
 * 内部 table entry 再调用下游函数；参数不是任意 tick 数。该 wrapper 不提供稳定 return value。
 */
static inline void bda_sys_timer_like(u32 preset_index) {
    (void)bda_call1(bda_sys_table(), BDA_SYS_TIMER_LIKE, preset_index);
}

/*
 * 扫描 alarm.db，按当前日期/星期/时间选择可能到期的 alarm record。
 * C200 会向 out_alarm_data 复制 BDA_SYS_ALARM_RECORD_SIZE byte；不要传 short buffer。
 * 失败或没有可用记录时会把 out_alarm_data+0x00 写成 -1。
 */
static inline int bda_sys_alarm_due_get_like(bda_sys_alarm_record_like_t *out_alarm_data) {
    return bda_call1(bda_sys_table(), BDA_SYS_ALARM_DUE_GET_LIKE, (u32)out_alarm_data);
}

/*
 * alarm set/get。C200 按 slot * 0x2b8 访问持久化 alarm record；当前只在
 * 原机闹钟应用中见到 slot 0/1/2。get 从配置文件 offset
 * 0x578 + slot * 0x2b8 复制 record；set 会把 record+0x00 写成 slot+2，
 * record+0x10 写成 1，再把 0x2b8 byte 写回配置文件。未见 slot bounds check。
 */
static inline int bda_sys_alarm_set_like(bda_sys_alarm_record_like_t *alarm_data, u32 slot) {
    return bda_call2(bda_sys_table(), BDA_SYS_ALARM_SET_LIKE, (u32)alarm_data, slot);
}

static inline int bda_sys_alarm_get_like(bda_sys_alarm_record_like_t *alarm_data, u32 slot) {
    return bda_call2(bda_sys_table(), BDA_SYS_ALARM_GET_LIKE, (u32)alarm_data, slot);
}

#endif
