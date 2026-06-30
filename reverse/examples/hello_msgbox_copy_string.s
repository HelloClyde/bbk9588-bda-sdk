start:
    addiu $sp, $sp, -0x80
    sw $ra, 0x70($sp)
    sw $s0, 0x6c($sp)
    sw $s1, 0x68($sp)

    la $s0, message
    addiu $s1, $sp, 0x20

copy_loop:
    lbu $t0, 0($s0)
    sb $t0, 0($s1)
    addiu $s0, $s0, 1
    addiu $s1, $s1, 1
    bnez $t0, copy_loop
    nop

    lui $t0, 0x81c2
    lw $t0, 0x4034($t0)
    lw $t9, 0x2b8($t0)

    move $a0, $zero
    addiu $a1, $sp, 0x20
    la $a2, title
    jalr $t9
    move $a3, $zero

    lw $s1, 0x68($sp)
    lw $s0, 0x6c($sp)
    lw $ra, 0x70($sp)
    jr $ra
    addiu $sp, $sp, 0x80

    .align 2
title:
    .asciiz "SDK"
message:
    .asciiz "Copied string via loop"
