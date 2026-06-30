# 九宫格.bda Report

`九宫格.bda` is a bundled category-0x04 puzzle game. It uses the same native
game shell as `Eros方块.bda`, `连连看.bda`, and `黑白子.bda`, but has slightly
heavier file and memory activity.

## Identity and Layout

```text
file size      102028 bytes
entry offset   0x95f8
entry VA       0x81c00020
image base     0x81bf6a28
BSS range      0x81c0f8b0..0x81c0fda1
```

Runtime table globals:

```text
RES  0x81c0f8b0
GUI  0x81c0f8b4
SYS  0x81c0f8b8
FS   0x81c0f8bc
MEM  0x81c0f8c0
```

## External Files

Relevant strings:

```text
\SdData.dat
\GamSdSave.Sav
\SysPet.yzj
rb
wb
wb+
rbf
a:\
```

`\SdData.dat` and `\GamSdSave.Sav` are app-specific data/save files. The
presence of both `wb+` and `rb` paths explains the larger FS call count compared
with the smaller games.

## Embedded VX Resources

The app embeds the same four common VX resources:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

No external `.dlx` package string appears in the current scan.

## API Use

The raw call scan has 227 indirect calls.

Important families:

```text
FS +0x000  8 calls
FS +0x004  10 calls
FS +0x008  4 calls
FS +0x00c  5 calls
FS +0x010  6 calls
FS +0x014  2 calls

GUI +0x074/+0x0e0/+0x2fc/+0x35c/+0x40c/+0x414/+0x418
MEM +0x008/+0x00c
RES +0x090/+0x094
```

The GUI call shape matches the common game shell. The extra FS/MEM traffic is
most likely level/save-data handling, not a different application framework.

## Current Interpretation

`九宫格.bda` strengthens the shared-shell conclusion and adds a second save-file
pattern:

```text
1. direct embedded VX resources for shell visuals
2. normal FS table for app-specific data/save files
3. no evidence of a generic DLX loader in the app path
4. same GUI render-helper cluster as the other small games
```

Follow-up value: inspect call sites around `\SdData.dat` and `\GamSdSave.Sav`
to separate level data loading from save/high-score records.
