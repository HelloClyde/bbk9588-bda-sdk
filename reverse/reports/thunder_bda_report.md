# 雷霆战机.bda Report

`雷霆战机.bda` is a bundled category-0x04 game. It uses the same small-game
shell as the puzzle games, but adds a higher-level package sound path backed by
`\FlySound.lib`.

## Identity and Layout

```text
file size      131452 bytes
entry offset   0x95f8
entry VA       0x81c00020
image base     0x81bf6a28
BSS range      0x81c16ba0..0x81c178f1
```

Runtime table globals:

```text
RES  0x81c16ba0
GUI  0x81c16ba4
SYS  0x81c16ba8
FS   0x81c16bac
MEM  0x81c16bb0
```

## External Files

Relevant strings:

```text
\Flydata.dat
\FlySound.lib
\GamFlyInfo.Sav
\SysPet.yzj
gFly_soundState = %d
rb
wb
wb+
rbf
```

`\Flydata.dat` and `\GamFlyInfo.Sav` are app data/save paths. `\FlySound.lib`
is the notable extra package. Despite the `.lib` suffix, this is not a host
link library; the app opens and parses it as runtime data.

## Embedded VX Resources

The app embeds the same four common VX resources:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

## API Use

The raw call scan has 291 indirect calls. It contains the common game shell plus
extra system-table sound calls:

```text
FS +0x000/+0x004/+0x008/+0x00c/+0x010/+0x014  data/save/package I/O
GUI +0x074/+0x0e0/+0x2fc/+0x35c/+0x3f8/+0x400/+0x40c/+0x414/+0x418
MEM +0x008/+0x00c
RES +0x090/+0x094

SYS +0x040  3 calls
SYS +0x044  1 call
SYS +0x050  1 call
SYS +0x054  1 call
SYS +0x058  2 calls
SYS +0x05c  4 calls
SYS +0x060  2 calls
SYS +0x064  4 calls
SYS +0x068  4 calls
SYS +0x08c  1 call
```

## Sound Package Flow

The code around `0x81c11188` iterates up to `0x14` sound/package chunks. It
fills descriptors spaced by `0x20` bytes, then calls `SYS+0x050`.

Later functions call a tight operation cluster:

```text
SYS+0x058  state/start/check-like operation
SYS+0x05c  descriptor operation, often after passing four zero-ish args
SYS+0x060  returns status; caller stores state when non-zero
SYS+0x064  paired before SYS+0x068
SYS+0x068  paired after SYS+0x064, likely stop/commit/drain-like
```

`SYS+0x044` stores a byte at `0x81c16bc4`, and later `SYS+0x040` receives either
that byte or a computed small sound id. This looks like sound effect selection
or channel/state control.

The names above are intentionally provisional. The important stable finding is
that this is a separate high-level packed sound-effect path, distinct from
`GAMEBOY.BDA`'s raw audio streaming calls.

## Current Interpretation

`雷霆战机.bda` is the best current bridge between the shared game render shell
and the game-specific sound package API:

```text
1. display shell still uses the same embedded VX and GUI render-helper cluster
2. package audio goes through SYS+0x040..0x068, not the raw GAMEBOY audio path
3. .lib files in these games are runtime data packages
4. a future custom game can likely ignore this package path and use raw audio,
   but reproducing native game sound effects should target this cluster
```

Follow-up value: compare with `决战坦克.bda`, which appears to use the same
sound package framework with `TankSound.lib`.
