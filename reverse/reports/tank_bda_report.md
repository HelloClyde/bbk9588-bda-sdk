# 决战坦克.bda Report

`决战坦克.bda` is a bundled category-0x04 game. It is the strongest current
cross-check for the `雷霆战机.bda` packed sound-effect path: both apps use the
same `SYS+0x040..0x068` cluster, the same `0x20`-byte descriptor stride, and the
same `0x14` chunk upper bound.

## Identity and Layout

```text
file size      114204 bytes
entry offset   0x95f8
entry VA       0x81c00020
image base     0x81bf6a28
BSS range      0x81c12840..0x81c13f31
```

Runtime table globals:

```text
RES  0x81c12840
GUI  0x81c12844
SYS  0x81c12848
FS   0x81c1284c
MEM  0x81c12850
```

## External Files

Relevant strings:

```text
\SysPet.yzj
\maptank\map
.map
\TankData.dat
\TankSound.lib
rb
wb
rbf
GeneralDLTable GUI_Address :%x
GeneralDLTable FS_Address :%x
GeneralDLTable Media_Address :%x
```

The app uses at least three kinds of external data:

```text
\maptank\map*.map   map/level data
\TankData.dat       save or game data
\TankSound.lib      packed sound-effect package
```

## Embedded VX Resources

The app embeds the same four common small-game shell VX resources:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

## API Use

The raw call scan has 296 indirect calls. It contains the common game shell plus
the packed sound-effect SYS cluster:

```text
FS +0x000  11 calls
FS +0x004  13 calls
FS +0x008  14 calls
FS +0x010  19 calls
FS +0x014  5 calls
FS +0x018/+0x01c/+0x020/+0x024/+0x028  extra stdio-like helpers

GUI +0x030/+0x050/+0x054  event loop
GUI +0x084/+0x088/+0x08c/+0x17c  frame lifecycle
GUI +0x2fc/+0x35c/+0x40c/+0x414/+0x418  render-helper family
GUI +0x3f8/+0x400  framebuffer/region blit-like pair
GUI +0x4f0  text-like draw

SYS +0x040/+0x044/+0x050/+0x054/+0x058/+0x05c/+0x060/+0x064/+0x068/+0x08c
SYS +0x090  one additional system/media-like call
```

## Packed Sound Flow

`SYS+0x050` at `0x81c04548` is the key loader call. The surrounding loop:

```text
stores two words into the descriptor
calls SYS+0x050
increments descriptor pointer by 0x20
loops while chunk index < 0x14
stores descriptor base around 0x81c12a10/0x81c12a20
```

This is instruction-for-instruction comparable to `雷霆战机.bda`'s package
loader around `0x81c11188`.

`SYS+0x054` at `0x81c04b98` walks descriptors with the same `0x20` stride and
frees/releases them. `SYS+0x064` and `SYS+0x068` are repeatedly paired, just as
in `雷霆战机.bda`.

`SYS+0x044` stores a byte at `0x81c1288c`. Later `SYS+0x040` receives either
that byte or a computed id of the form:

```text
sound_id = 0x75 - (index * 13)
```

This matches the same selection/control pattern seen in `雷霆战机.bda`.

## Current Interpretation

`决战坦克.bda` confirms that `SYS+0x040..0x068` is not a one-off Thunder helper.
It is a reusable system-level packed sound-effect interface used by bundled
native games.

Practical SDK implication:

```text
1. keep raw GAMEBOY audio and packed game sound separate
2. represent the packed sound descriptor as a 0x20-byte record for experiments
3. treat .lib game files as runtime packages, not host link libraries
4. use Tank + Thunder together before naming individual SYS operations as final
```
