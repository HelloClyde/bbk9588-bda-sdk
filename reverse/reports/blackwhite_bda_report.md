# 黑白子.bda Report

`黑白子.bda` is a bundled category-0x04 game. It is another compact sample of
the shared native game framework already seen in `Eros方块.bda` and `连连看.bda`.

## Identity and Layout

```text
file size      151276 bytes
entry offset   0x95f8
entry VA       0x81c00020
image base     0x81bf6a28
BSS range      0x81c1b910..0x81c27271
```

Runtime table globals:

```text
RES  0x81c1b910
GUI  0x81c1b914
SYS  0x81c1b918
FS   0x81c1b91c
MEM  0x81c1b920
```

## External Files

Relevant strings:

```text
\SysPet.yzj
\BlackData.dat
rb
wb
rbf
a:\
```

`\BlackData.dat` is the app-specific data/save file. `\SysPet.yzj` is shared
with the other small game framework samples.

## Embedded VX Resources

The BDA embeds five VX images:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
0x0194e4  240x95
```

The first four match the common small-game shell resources. The extra 240x95
resource is game-specific and likely part of the board/title/help UI.

## API Use

The raw call scan has 210 indirect calls. Its GUI/FS/MEM/RES distribution is
very close to `Eros方块.bda` and `连连看.bda`, which makes this a good third
confirmation that those apps share the same framework rather than coincidental
code structure.

Important families:

```text
FS +0x000/+0x004/+0x008/+0x00c/+0x010/+0x014  stdio-like save/data I/O
GUI +0x074/+0x0e0/+0x2fc/+0x35c/+0x40c/+0x414/+0x418  game render shell
MEM +0x008/+0x00c  allocation/free
RES +0x090/+0x094  resource-state and trace/log-like helpers
```

## Current Interpretation

`黑白子.bda` should be treated as another baseline for the shared small-game
shell. It reinforces these points:

```text
1. small games can embed VX resources directly in the BDA, without external DLX
2. game save/data files are opened through the normal FS table
3. GUI+0x414/+0x418 belong to the same render-helper family across many games
4. RES+0x094 appearing here does not imply resource loading; hardware probes
   already support trace/log semantics
```

Follow-up value: compare the 240x95 resource use with the game's draw call
sites to pin one more concrete signature for `GUI+0x414/+0x418`.
