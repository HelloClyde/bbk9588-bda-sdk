# Native BDA API smoke test.
# Uses the imported memory table:
#   memory_table = *(0x81c00010)
#   ptr = memory_table->alloc(0x40)      # observed at +0x8
#   memory_table->free(ptr)              # observed at +0xc

lui   $s0, 0x81c0
lw    $s0, 0x10($s0)

lw    $v0, 0x8($s0)
jalr  $v0
addiu $a0, $zero, 0x40

move  $a0, $v0
lw    $v1, 0xc($s0)
jalr  $v1
nop

jr    $ra
nop
