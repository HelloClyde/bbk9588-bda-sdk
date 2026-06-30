# Eros Blocks BDA report

Target: `应用/程序/Eros方块.bda`

Generated evidence:

- `reverse/reports/eros_layout.json`
- `reverse/reports/eros_calls.txt`
- `reverse/reports/eros_fs_context.txt`
- `reverse/reports/eros_gui414_context.txt`
- `reverse/reports/eros_gui418_context.txt`
- `reverse/reports/eros_media.txt`
- `reverse/reports/eros_strings_vx.txt`

## Header and layout

```text
title              Eros方块
category           0x04
file size          83996 bytes
entry offset       0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
BSS/global range   0x81c0b240..0x81c0b561
checksum           ok in inventory
```

Runtime table globals:

```text
RES 0x81c0b240
GUI 0x81c0b244
SYS 0x81c0b248
FS  0x81c0b24c
MEM 0x81c0b250
```

## Embedded resources and strings

No external `\shell\*.dlx` resources are referenced. The BDA embeds the same
four VX resources seen in other small game BDAs:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

Relevant strings:

```text
rb
wb
rbf
a:\
\SysPet.yzj
A:\
\ErosData.dat
eros
Game Over
```

The `SysPet.yzj` path is shared with `连连看.bda`, indicating a common small
game system/settings or pet/skin data file. `ErosData.dat` is this app's own
save/high-score data file.

## API usage summary

Classified indirect calls:

```text
GUI   128
FS     41
MEM    21
RES    12
total 209
```

Hot offsets:

```text
GUI +0x0e0  13
GUI +0x074  10
GUI +0x414   8
GUI +0x2fc   7
GUI +0x418   6
GUI +0x338   6
GUI +0x358   6
FS  +0x000/+0x004/+0x010
RES +0x094   9
```

This is a compact representative of the shared native small-game framework.

## File/save behavior

The app uses stdio-like FS calls for resource/save files:

```text
FS +0x000  fopen-like
FS +0x004  fclose-like
FS +0x008  fread-like
FS +0x00c  fwrite-like
FS +0x010  fseek-like
FS +0x014  ftell-like
FS +0x024  remove-like
FS +0x02c  directory exists/chdir-like
FS +0x030  mkdir-like
FS +0x03c  findfirst-like
FS +0x044  findclose-like
FS +0x068  unknown helper
```

Context around the save init path:

```text
open a:\... with "rb"
if missing, FS+0x02c / FS+0x030 directory preparation
delete/recreate via FS+0x024 and open with "wb"
copy 0x44-byte records into memory and write them back
```

The fixed 0x44-byte record size appears several times, likely the game save or
score record size.

## GUI/game rendering

The app uses the standard event loop:

```text
GUI +0x030  poll-like
GUI +0x050  step-like
GUI +0x054  dispatch-like
GUI +0x17c  close/release-like
```

`GUI +0x414` is called 8 times. The call shape is a multi-argument region
render helper:

```text
a0 = surface/object
a1 = x/source-x-like
a2 = y/source-y-like
a3 = width/height/index-like
stack+0x10..0x24 = extra rectangle/color/resource fields
```

The call is often followed by `GUI +0x0e8` or `GUI +0x074`, suggesting it
prepares or copies a render region before presenting/pumping.

`GUI +0x418` is called 6 times and takes a larger stack argument block. Some
call sites pass `0x140` and `0xf0`, matching 320x240 screen dimensions. This
matches the region/render family also seen in `电子画板.bda` and Album.

The app also uses:

```text
GUI +0x368  put-pixel-like, low count here
GUI +0x4f0  text draw-like, for labels/game-over text
GUI +0x2b8  message box-like
```

## Cross-checks

- With `连连看.bda`: near-identical layout, globals, FS calls, GUI render calls,
  embedded VX resources, and `\SysPet.yzj` usage.
- With `电子画板.bda`: confirms `GUI +0x414/+0x418` belong to the broader
  region/render family; `GUI +0x368` remains put-pixel-like.
- With FS notes: confirms small games use the same stdio/directory/save-file
  table as tools and readers.

## Open questions

- Name `FS +0x018/+0x01c/+0x020/+0x028/+0x068`; these appear in the game save
  helper area and may be FAT support functions.
- Determine exact `GUI +0x414` and `GUI +0x418` stack argument layouts.
- Compare this shell with more games (`黑白棋`, `九宫格`, `雷霆战机`) to identify
  which code is framework and which code is game-specific.
