# Native BDA API smoke test.
# Calls the resource/DLX loader shape observed in bundled apps, then returns.
#
# Observed original pattern after startup copies the 0x81c000xx words into BSS:
#   v0 = *( *(0x81c00014) + 0x94 )
#   a0 = path
#   a1 = 0x81c00000
#   jalr v0

lui   $v1, 0x81c0
lw    $a1, 0x14($v1)
lw    $v0, 0x94($a1)
la    $a0, path
jalr  $v0
lui   $a1, 0x81c0

jr    $ra
nop

path:
.asciiz "\\shell\\normal_A.dlx"
