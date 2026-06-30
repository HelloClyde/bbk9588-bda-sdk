# Link Game BDA report

Target: `应用/程序/连连看.bda`

Generated evidence:

- `reverse/reports/linkgame_layout.json`
- `reverse/reports/linkgame_calls.txt`
- `reverse/reports/linkgame_fs_context.txt`
- `reverse/reports/linkgame_gui414_context.txt`
- `reverse/reports/linkgame_media.txt`
- `reverse/reports/linkgame_strings_vx.txt`

## Header and layout

```text
title              连连看
category           0x04
file size          82732 bytes
entry offset       0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
BSS/global range   0x81c0ad50..0x81c0ba91
checksum           ok in inventory
```

Runtime table globals:

```text
RES 0x81c0ad50
GUI 0x81c0ad54
SYS 0x81c0ad58
FS  0x81c0ad5c
MEM 0x81c0ad60
```

## Embedded resources and strings

No external `\shell\*.dlx` resources are referenced. The app embeds the same
four VX resources as `Eros方块.bda`:

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
\LLKData.dat
```

`LLKData.dat` is the game-specific save/high-score file. `SysPet.yzj` is shared
with `Eros方块.bda`, confirming a common small-game framework dependency.

## API usage summary

Classified indirect calls:

```text
GUI   128
FS     41
MEM    25
RES    12
total 213
```

The call table is almost identical to `Eros方块.bda`; the small differences are
mostly `MEM +0x008/+0x00c` counts and app-specific data.

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

## File/save behavior

The FS call set matches `Eros方块.bda` exactly:

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

Contexts show the same pattern:

```text
open shared/system data path with "rb"
prepare directory if missing
delete/recreate save file when needed
copy/write fixed 0x44-byte records
```

The record-copy loops and save helper are structurally the same as Eros, with
different global offsets and the `LLKData.dat` filename.

## GUI/game rendering

The app uses the same standard event loop:

```text
GUI +0x030  poll-like
GUI +0x050  step-like
GUI +0x054  dispatch-like
GUI +0x17c  close/release-like
```

`GUI +0x414` call contexts match Eros instruction-for-instruction except for
global addresses. This is strong evidence that `+0x414` belongs to the shared
game/render helper, not to Eros-specific game logic.

It also uses:

```text
GUI +0x418  region/render finish-like
GUI +0x368  put-pixel-like, low count
GUI +0x4f0  text draw-like
GUI +0x2b8  message box-like
```

## Cross-checks

- With `Eros方块.bda`: confirms a shared small-game BDA framework and save-file
  helper.
- With `电子画板.bda`: confirms `GUI +0x368/+0x40c/+0x414/+0x418` are related to
  rendering rather than text/window setup.
- With `game_framework_notes.md`: these two apps should be treated as the
  smallest known examples of that framework.

## Open questions

- `FS +0x068` appears once in both games and needs comparison with other game
  BDAs before naming.
- `GUI +0x414` stack layout is still unresolved.
- Identify the exact structure of the 0x44-byte save/high-score record.
