# Native GBA.BDA Work Notes

## Current Builds

```text
build\GBA.BDA       current test build, currently same as v3 selector build
build\GBA_v1.BDA    native GBA host/core skeleton
build\GBA_v2.BDA    ROM selection + larger ARM/THUMB probe core
build\GBA_v3_select.BDA  GAMEBOY.BDA file selector + appended GBA core
build\gba_native_v0.bda  ROM-header and framebuffer probe
build\gba.cfg.example    sample ROM selector config
```

## v1 Scope

`reverse\examples\gba_native_v1.c` is not yet a playable GBA emulator. It is a
native BDA skeleton that validates the BBK host-side pieces before a larger core
is ported.

Implemented:

```text
ROM path          A:\gba\gba.gba, fallback a:\gba\gba.gba
ROM load cap      2 MiB for this early probe
EWRAM             256 KiB heap allocation
IWRAM             32 KiB heap allocation
VRAM              96 KiB heap allocation
Framebuffer       320x240 RGB565 via GUI+0x3f8 wrapper
Header parser     title, game code/checksum
CPU state         r0-r15 + CPSR
ARM probe loop    starts at 0x08000000, runs 2048 ARM instructions max
```

The ARM interpreter currently supports only a tiny subset:

```text
B / BL
BX
MOV immediate
ADD immediate
SUB immediate
CMP immediate
LDR / STR word immediate offset
condition codes
```

The message box reports:

```text
ROM title
file size / loaded size
header checksum result
PC after probe
executed step count
first unsupported opcode and PC
```

## Expected Hardware Results

Without a ROM:

```text
ROM not found:
A:\gba\gba.gba
```

With a ROM:

```text
ROM: <title>
Size/load: <file>/<loaded>
Chk OK/BAD <header byte>/<calculated>
PC=<after probe> steps=<count>
```

Most commercial ROMs will stop quickly on an unsupported ARM opcode. That is
expected for v1; the point of the build is to validate loading, memory
allocation, initial ARM dispatch, and framebuffer/audio-safe host plumbing.

## v2 Scope

`reverse\examples\gba_native_v2.c` adds ROM selection and a larger CPU probe
core. It is still not a playable emulator.

ROM selection uses:

```text
A:\gba\gba.cfg
```

The first line can be a file name under `A:\gba\` or a full path:

```text
demo.gba
A:\gba\demo.gba
```

If `gba.cfg` is missing or empty, it falls back to `A:\gba\gba.gba`, then
`a:\gba\gba.gba`. The current selected path is shown in the message box.

Additional v2 CPU coverage:

```text
ARM/THUMB mode bit and BX switching
THUMB MOV/CMP/ADD/SUB immediate
THUMB add/sub register/immediate
THUMB ALU AND/EOR/LSL/CMP/NEG/ORR/MUL subset
THUMB literal LDR
THUMB LDR/STR byte/halfword/word immediate
THUMB conditional/unconditional branch
ARM data processing immediate and register operand forms
ARM byte/word LDR/STR immediate
ARM LDM/STM increment-after subset
```

## v3 Selector Build

`build\GBA_v3_select.BDA` keeps the original `GAMEBOY.BDA` front end and file
selector flow, then redirects the selected ROM path into the appended GBA core.

Patch strategy:

```text
template          应用\程序\GAMEBOY.BDA
original selector GAMEBOY main at 0x81c0f90c
hooked function   gbmain(path) at 0x81c10158
new core VA       0x81c25338, after original BSS clear range
filter patch      gb;gbc -> gba
title patch       GameBoy -> GBA
config patch      a:\gameboy\gb.cfg -> a:\gba\gba.cfg
```

This is the closest current copy of the bundled Game Boy behavior: the file
picker is not reimplemented in our code; it is the original extended GUI
selector. The selected path is passed as `a0` to the appended GBA core.

The original front end still references:

```text
a:\gameboy\gameboy.dlx
```

Keep that resource available if the original Game Boy app requires it on the
device. It likely contains the selector/front-end resources.

## Next Core Tasks

```text
1. Add THUMB long BL pair, PUSH/POP, and high-register operations.
2. Add ARM multiply, halfword/signed transfer, swap, and richer shifts.
3. Finish ARM block transfer addressing modes.
4. Stub key IO, DISPCNT, VCOUNT, timers, IRQ flags, and DMA.
5. Add PPU mode 3 first, then mode 4/5.
6. Add palette/OAM/tile rendering.
7. Add sound core and save type handling.
8. Raise ROM cap after heap behavior is proven on hardware.
```
