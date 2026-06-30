# 三国霸业.bda Report

`三国霸业.bda` is a bundled category-0x04 game. It shares the same native game
shell and embedded VX header resources as the other games, but its external
`\sango.lib` package is not handled through the `SYS+0x040..0x068` packed sound
cluster. It is instead parsed by app code through FS and MEM helpers.

## Identity and Layout

```text
file size      214700 bytes
entry offset   0x95f8
entry VA       0x81c00020
image base     0x81bf6a28
BSS range      0x81c2b0d0..0x81c2ba71
```

Runtime table globals:

```text
RES  0x81c2b0d0
GUI  0x81c2b0d4
SYS  0x81c2b0d8
FS   0x81c2b0dc
MEM  0x81c2b0e0
```

## External Files

Relevant strings:

```text
\sango.lib
rbf
```

The string xref around `0x81c13d80` builds a path into a stack buffer, opens it
through the FS wrapper, seeks to the end, takes the file size, allocates memory,
and reads data back into app-owned buffers. Later code reopens numbered or
derived package entries and copies fixed-size pieces into many BSS structures.

Unlike `雷霆战机.bda` and `决战坦克.bda`, there are no `SYS+0x040..0x068` calls in
the raw scan. That makes `\sango.lib` a different kind of game data package, not
currently evidence for the packed sound-effect system API.

## Embedded VX Resources

The app embeds the same four common small-game shell VX resources:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

## API Use

The raw call scan has 176 indirect calls:

```text
FS +0x000/+0x004/+0x008/+0x00c/+0x010/+0x014  package I/O
FS +0x018/+0x01c/+0x020/+0x028                 extra stdio-like helpers
FS +0x030                                     mkdir-like helper
FS +0x068/+0x06c                              stat/access-like helpers

GUI +0x030/+0x050/+0x054  event loop
GUI +0x084/+0x088/+0x08c/+0x17c  frame lifecycle
GUI +0x074  frequent pump/present/update-like call
GUI +0x2fc/+0x35c/+0x40c/+0x414/+0x418  render-helper family
GUI +0x3f8/+0x400  framebuffer/region blit-like pair

MEM +0x008/+0x00c  allocation/free
RES +0x094         trace/log-like helper
```

FS contexts around `0x81c1653c`, `0x81c16754`, `0x81c16884`, and
`0x81c16b20` repeatedly build small numbered paths, open package entries, read
records, and copy them into globals. This looks like scenario/save/resource
state rather than a generic system loader.

## Current Interpretation

`三国霸业.bda` is useful precisely because it is a counterexample:

```text
1. it proves that not every game .lib file means SYS package sound
2. it confirms the common game GUI/VX shell without the sound cluster
3. it shows another app-owned package format built on plain FS/MEM calls
4. it provides extra evidence for FS+0x068/+0x06c as access/stat-like helpers
```

Practical SDK implication: expose the FS/MEM primitives and leave `sango.lib`
as an app-private package format until the package header/chunk table is mapped.
