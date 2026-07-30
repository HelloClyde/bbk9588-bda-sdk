#ifndef BDA_HARDWARE_H
#define BDA_HARDWARE_H

#include "bda/detail/runtime.h"

/*
 * Public read-only hardware identification derived from the factory 9588
 * V3.30 and 9688 V2.32 recovery applications.  The address ranges are the
 * same ranges read by those applications; no MMIO or NAND registers are
 * written.
 *
 * The BBK 9588/JZ4730 path is verified on real hardware: the OS signature was
 * found at 0x80253710, no JZ4740 Boot ROM marker was present, and GUI+0x738 was
 * correctly left unqueried.  See docs/verified/hardware_detection_api.md for
 * the verified scope and remaining model/chip combinations.  Unknown firmware
 * is deliberately left unknown instead of being guessed as JZ4730.
 */

#define BDA_DEVICE_MODEL_UNKNOWN 0u
#define BDA_DEVICE_MODEL_9588    9588u
#define BDA_DEVICE_MODEL_9688    9688u

#define BDA_CHIP_MODEL_UNKNOWN 0u
#define BDA_CHIP_MODEL_JZ4720  4720u
#define BDA_CHIP_MODEL_JZ4730  4730u
#define BDA_CHIP_MODEL_JZ4740  4740u

#define BDA_HARDWARE_OS_IMAGE_ADDR       0x80004000u
#define BDA_HARDWARE_OS_IMAGE_SCAN_SIZE  0x00500000u
#define BDA_HARDWARE_BOOT_ROM_ADDR       0xbfc00000u
#define BDA_HARDWARE_BOOT_ROM_SCAN_SIZE  0x00001000u
#define BDA_HARDWARE_GUI_SCREEN_WIDTH    0x738u
#define BDA_HARDWARE_JZ4720_WIDTH_VALUE  0x131
#define BDA_HARDWARE_VALUE_NOT_QUERIED   (-1)

typedef struct bda_hardware_info {
    u32 device_model;
    u32 chip_model;
    u32 os_signature_address;
    u32 boot_rom_signature_address;
    s32 gui_screen_width_value;
} bda_hardware_info_t;

static inline int bda_hardware_internal_match_ascii(
    const volatile u8 *memory, const char *text, u32 text_size
) {
    u32 index;

    for (index = 0u; index < text_size; ++index) {
        if (memory[index] != (u8)text[index]) {
            return 0;
        }
    }
    return 1;
}

static inline u32 bda_hardware_internal_find_wide_ascii(
    u32 address, u32 size, const char *text, u32 text_size
) {
    const volatile u8 *memory = (const volatile u8 *)address;
    u32 required_size;
    u32 offset;
    u32 index;

    if (text_size == 0u) {
        return address;
    }
    required_size = (text_size - 1u) * 2u + 1u;
    if (size < required_size) {
        return 0u;
    }

    for (offset = 0u; offset <= size - required_size; ++offset) {
        if (memory[offset] != (u8)text[0]) {
            continue;
        }
        for (index = 1u; index < text_size; ++index) {
            if (memory[offset + index * 2u] != (u8)text[index]) {
                break;
            }
        }
        if (index == text_size) {
            return address + offset;
        }
    }
    return 0u;
}

static inline u32 bda_hardware_internal_screen_width_value(void) {
    typedef int (*fn_t)(void);
    fn_t fn = (fn_t)bda_sdk_internal_api(
        bda_sdk_internal_gui(), BDA_HARDWARE_GUI_SCREEN_WIDTH
    );
    return (u32)fn();
}

/*
 * Scan the loaded OS image once for the factory product signature.
 * When a signature is found, its address is optionally returned.
 */
static inline u32 bda_detect_device_model(u32 *signature_address) {
    static const char model_9588[] = "9588 OS";
    static const char model_9688[] = "9688 OS";
    const volatile u8 *memory =
        (const volatile u8 *)BDA_HARDWARE_OS_IMAGE_ADDR;
    u32 offset;
    u32 model = BDA_DEVICE_MODEL_UNKNOWN;

    if (signature_address != 0) {
        *signature_address = 0u;
    }
    for (
        offset = 0u;
        offset + (sizeof(model_9588) - 1u) <=
            BDA_HARDWARE_OS_IMAGE_SCAN_SIZE;
        ++offset
    ) {
        if (memory[offset] != (u8)'9') {
            continue;
        }
        if (bda_hardware_internal_match_ascii(
            memory + offset, model_9588, sizeof(model_9588) - 1u
        )) {
            model = BDA_DEVICE_MODEL_9588;
        } else if (bda_hardware_internal_match_ascii(
            memory + offset, model_9688, sizeof(model_9688) - 1u
        )) {
            model = BDA_DEVICE_MODEL_9688;
        } else {
            continue;
        }
        if (signature_address != 0) {
            *signature_address = BDA_HARDWARE_OS_IMAGE_ADDR + offset;
        }
        break;
    }
    return model;
}

/*
 * Detect the chip for a previously identified device model.
 *
 * Factory recovery logic maps an absent JZ4740 Boot ROM signature to JZ4730.
 * We only make that mapping after the OS image has been identified as 9588 or
 * 9688.  The 9588 recovery application additionally distinguishes JZ4720 by
 * the GUI+0x738 return value.
 */
static inline u32 bda_detect_chip_model(
    u32 device_model,
    u32 *boot_rom_signature_address,
    s32 *gui_screen_width_value
) {
    static const char jz4740[] = "JZ4740";
    u32 marker;
    s32 width = BDA_HARDWARE_VALUE_NOT_QUERIED;

    if (boot_rom_signature_address != 0) {
        *boot_rom_signature_address = 0u;
    }
    if (gui_screen_width_value != 0) {
        *gui_screen_width_value = BDA_HARDWARE_VALUE_NOT_QUERIED;
    }
    if (
        device_model != BDA_DEVICE_MODEL_9588 &&
        device_model != BDA_DEVICE_MODEL_9688
    ) {
        return BDA_CHIP_MODEL_UNKNOWN;
    }

    marker = bda_hardware_internal_find_wide_ascii(
        BDA_HARDWARE_BOOT_ROM_ADDR,
        BDA_HARDWARE_BOOT_ROM_SCAN_SIZE,
        jz4740,
        sizeof(jz4740) - 1u
    );
    if (boot_rom_signature_address != 0) {
        *boot_rom_signature_address = marker;
    }
    if (marker == 0u) {
        return BDA_CHIP_MODEL_JZ4730;
    }
    if (device_model == BDA_DEVICE_MODEL_9688) {
        return BDA_CHIP_MODEL_JZ4740;
    }

    width = (s32)bda_hardware_internal_screen_width_value();
    if (gui_screen_width_value != 0) {
        *gui_screen_width_value = width;
    }
    return width == BDA_HARDWARE_JZ4720_WIDTH_VALUE
        ? BDA_CHIP_MODEL_JZ4720
        : BDA_CHIP_MODEL_JZ4740;
}

static inline void bda_detect_hardware(bda_hardware_info_t *info) {
    if (info == 0) {
        return;
    }
    info->device_model =
        bda_detect_device_model(&info->os_signature_address);
    info->chip_model = bda_detect_chip_model(
        info->device_model,
        &info->boot_rom_signature_address,
        &info->gui_screen_width_value
    );
}

static inline const char *bda_device_model_name(u32 model) {
    if (model == BDA_DEVICE_MODEL_9588) {
        return "BBK 9588";
    }
    if (model == BDA_DEVICE_MODEL_9688) {
        return "BBK 9688";
    }
    return "UNKNOWN";
}

static inline const char *bda_chip_model_name(u32 model) {
    if (model == BDA_CHIP_MODEL_JZ4720) {
        return "JZ4720";
    }
    if (model == BDA_CHIP_MODEL_JZ4730) {
        return "JZ4730";
    }
    if (model == BDA_CHIP_MODEL_JZ4740) {
        return "JZ4740";
    }
    return "UNKNOWN";
}

#endif
