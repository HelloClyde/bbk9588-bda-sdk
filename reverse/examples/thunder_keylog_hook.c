#include "bda_sdk.h"

static const char k_log_path_a[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\KEYLOG.TXT";
static const char k_log_path_root[] =
    "\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\KEYLOG.TXT";
static const char k_hex[] = "0123456789ABCDEF";

static const char *key_name(u32 code) {
    switch (code) {
        case 0x01: return "ESC";
        case 0x1c: return "ENTER";
        case 0x67: return "UP";
        case 0x69: return "LEFT";
        case 0x6a: return "RIGHT";
        case 0x6c: return "DOWN";
        default: return "OTHER";
    }
}

static int open_log(void) {
    int file = bda_fs_fopen_raw(k_log_path_a, "r+b");
    if (!bda_fs_file_is_valid(file)) {
        file = bda_fs_fopen_raw(k_log_path_root, "r+b");
    }
    return file;
}

__attribute__((noinline))
void thunder_keylog_record(u32 code) {
    char line[32];
    const char *name = key_name(code);
    char *out = line;
    int file;
    int shift;

    (void)bda_msgbox("KeyHook", name);

    *out++ = 'K';
    *out++ = 'E';
    *out++ = 'Y';
    *out++ = ' ';
    for (shift = 28; shift >= 0; shift -= 4) {
        *out++ = k_hex[(code >> shift) & 0x0f];
    }
    *out++ = ' ';
    while (*name != 0) {
        *out++ = *name++;
    }
    *out++ = '\r';
    *out++ = '\n';

    file = open_log();
    if (!bda_fs_file_is_valid(file)) {
        return;
    }
    (void)bda_fs_fwrite_raw(line, 1, (bda_size_t)(out - line), file);
    (void)bda_fs_close_raw(file);
}

/*
 * Thunder-specific hook for 0x81c01164. The overwritten instructions are
 * replayed before control returns to the original event branch.
 */
__asm__(
    ".set push\n"
    ".set noreorder\n"
    ".set noat\n"
    ".section .text.bda_main,\"ax\",@progbits\n"
    ".globl bda_main\n"
    ".type bda_main,@function\n"
    "bda_main:\n"
    "addiu $sp,$sp,-0x70\n"
    "sw $ra,0x6c($sp)\n"
    "sw $1,0x68($sp)\n"
    "sw $v0,0x64($sp)\n"
    "sw $v1,0x60($sp)\n"
    "sw $a0,0x5c($sp)\n"
    "sw $a1,0x58($sp)\n"
    "sw $a2,0x54($sp)\n"
    "sw $a3,0x50($sp)\n"
    "sw $t0,0x4c($sp)\n"
    "sw $t1,0x48($sp)\n"
    "sw $t2,0x44($sp)\n"
    "sw $t3,0x40($sp)\n"
    "sw $t4,0x3c($sp)\n"
    "sw $t5,0x38($sp)\n"
    "sw $t6,0x34($sp)\n"
    "sw $t7,0x30($sp)\n"
    "sw $t8,0x2c($sp)\n"
    "sw $t9,0x28($sp)\n"
    "sw $gp,0x24($sp)\n"
    "mfhi $t0\n"
    "sw $t0,0x20($sp)\n"
    "mflo $t0\n"
    "sw $t0,0x1c($sp)\n"
    "lw $a0,0xd4($sp)\n"
    "jal thunder_keylog_record\n"
    "nop\n"
    "lw $t0,0x1c($sp)\n"
    "mtlo $t0\n"
    "lw $t0,0x20($sp)\n"
    "mthi $t0\n"
    "lw $gp,0x24($sp)\n"
    "lw $t9,0x28($sp)\n"
    "lw $t8,0x2c($sp)\n"
    "lw $t7,0x30($sp)\n"
    "lw $t6,0x34($sp)\n"
    "lw $t5,0x38($sp)\n"
    "lw $t4,0x3c($sp)\n"
    "lw $t3,0x40($sp)\n"
    "lw $t2,0x44($sp)\n"
    "lw $t1,0x48($sp)\n"
    "lw $t0,0x4c($sp)\n"
    "lw $a3,0x50($sp)\n"
    "lw $a2,0x54($sp)\n"
    "lw $a1,0x58($sp)\n"
    "lw $a0,0x5c($sp)\n"
    "lw $v1,0x60($sp)\n"
    "lw $v0,0x64($sp)\n"
    "lw $1,0x68($sp)\n"
    "lw $ra,0x6c($sp)\n"
    "addiu $sp,$sp,0x70\n"
    "lw $v1,0x64($sp)\n"
    "addiu $v0,$zero,0x67\n"
    "beq $v1,$v0,1f\n"
    "slti $v0,$v1,0x68\n"
    "j 0x81c01174\n"
    "nop\n"
    "1:\n"
    "j 0x81c01214\n"
    "nop\n"
    ".size bda_main,.-bda_main\n"
    ".set pop\n"
);
