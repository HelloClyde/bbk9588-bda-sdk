# JiuMenKeCheng / Nine Courses.bda Report

`九门课程.bda` is a category-0x05 learning/content app. It is larger and more
stateful than `课程表.bda`, and it is currently one of the better examples of a
non-game app that mixes file data, external DLX skins, GUI controls, text, and
large-region drawing.

## Identity and Layout

```text
file size      143,868 bytes
menu title     九门课程
category       0x05
entry offset   0x95f8
entry VA       0x81c00020
image base     0x81bf6a28
BSS range      0x81c19c20..0x81c52991
checksum       ok
```

Runtime table globals:

```text
RES  0x81c19c20
GUI  0x81c19c24
SYS  0x81c19c28
FS   0x81c19c2c
MEM  0x81c19c30
```

## External Resources

Visible strings include:

```text
\Shell\JiuMenKeCheng.dlx
\Shell\JiuMenKeChengHeiSeTuPian.dlx
rb
wb
```

It also embeds the same four common shell VX resources:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

The app repeatedly references the two external DLX names, so these are probably
normal/dark skin packages or per-view artwork packages.

## API Use

The current indirect-call scan finds 708 runtime table calls:

```text
FS  +0x000  9   fopen-like
FS  +0x004  9   fclose-like
FS  +0x008 23   fread-like
FS  +0x00c  4   fwrite-like
FS  +0x010 21   fseek-like
FS  +0x02c  2   directory-exists/chdir-like
FS  +0x030  2   mkdir-like
FS  +0x048  3   disk info-like
FS  +0x064  2   unresolved FS helper

GUI +0x030/+0x050/+0x054  event poll/step/dispatch
GUI +0x084/+0x088/+0x08c/+0x17c  frame lifecycle
GUI +0x1a4/+0x1a8/+0x1ac/+0x1b0  control/object family
GUI +0x308/+0x30c  begin/end draw
GUI +0x338/+0x33c/+0x378/+0x4f0  text mode, color, draw text
GUI +0x3f8/+0x400  framebuffer/large-region draw family
GUI +0x430/+0x46c  rectangle/resource helper family
GUI +0x540  VX/resource draw appears in resource-draw branches

MEM +0x008 25  allocation-like
MEM +0x00c 23  free-like
RES +0x090  3  resource state/helper-like
RES +0x094 18  trace/log-like
```

## GUI Object Model

The app creates a top-level object through `GUI+0x1a4` with a style value in the
`0x08000000` family and stores the returned handle in app globals. It then uses
additional control/object calls:

```text
GUI+0x1ac(handle, 0x64, 0x190)
GUI+0x1b0(handle, 0x64)
```

These appear in scroll/page-change or view-rebuild paths. They are not used by
the minimal Element image probe, so they are important candidates for why a
simple custom Showcase app can draw once but cannot behave like a full app.

## Drawing Model

Nine Courses heavily uses both normal draw handles and large-region helpers:

```text
GUI+0x308/+0x30c       draw lifetime
GUI+0x074              draw/present guard
GUI+0x3f8/+0x400       large-region/framebuffer-like pair
GUI+0x430/+0x46c       rectangle/resource helper family
GUI+0x4f0              text draw-like
```

`GUI+0x4f0` appears 50 times. Some calls pass static strings, while others draw
dynamic text buffers built from course data. The app frequently sets text mode
and text colors before drawing, matching Notepad, Time, Ebook, and BBVM.

The `GUI+0x3f8/+0x400` cluster is also used by small games, but here it appears
inside a learning/content UI. So this pair should be described as
large-region/framebuffer-like, not game-only.

## File and Storage Flow

The app reads and writes more data than Schedule. It uses:

```text
open/read/seek/write/close for fixed records
FS+0x02c / FS+0x030 directory preparation
FS+0x048 disk info checks
FS+0x064 unresolved helper calls
```

At `FS+0x048` call sites it reads words from the returned info buffer and
computes storage capacity-like values, same general pattern as Settings and
Time.

`FS+0x064` is still unresolved. Two call sites pass stack buffers and then test
bytes from the returned structure against app globals. This does not fit the
plain stdio group and should stay provisional.

## SDK Implications

1. Custom display apps need a stable object/frame lifecycle before using text
   and image helpers.
2. `GUI+0x1ac/+0x1b0` should be added as a provisional control/object update
   pair; Nine Courses is currently the strongest source.
3. `GUI+0x3f8/+0x400` should not be labeled game-only.
4. `FS+0x064` needs a dedicated probe or deeper static pass before exposing it
   as a public SDK helper.

## Open Items

1. Exact semantics of `GUI+0x1ac` and `GUI+0x1b0`.
2. Exact struct/record format for the course data files.
3. Exact role of `FS+0x064`.
4. Whether the DLX normal/dark pair is theme-driven or selected by a display
   mode flag.
