start:
    addiu $sp, $sp, -0x18
    sw $ra, 0x10($sp)

    lui $t0, 0x81c2
    lw $t0, 0x4034($t0)
    lw $t9, 0x2b8($t0)

    move $a0, $zero
    la $a1, title
    la $a2, message
    jalr $t9
    move $a3, $zero

    lw $ra, 0x10($sp)
    jr $ra
    addiu $sp, $sp, 0x18

    .align 2
title:
    .asciiz "Hello"
message:
    .asciiz "HelloWorld native BDA"
