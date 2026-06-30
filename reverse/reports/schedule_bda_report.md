# KeChengBiao / Schedule.bda Report

`课程表.bda` is a category-0x09 tool/content app. It is a useful cross-check
for the window/event lifecycle used by non-game display apps: it opens external
DLX skin files, creates GUI objects, uses the normal event pump, and draws text
and resource images from inside that lifecycle.

## Identity and Layout

```text
file size      83,020 bytes
menu title     课程表
category       0x09
entry offset   0x95f8
entry VA       0x81c00020
image base     0x81bf6a28
BSS range      0x81c0ae70..0x81c0b001
checksum       ok
```

Runtime table globals:

```text
RES  0x81c0ae70
GUI  0x81c0ae74
SYS  0x81c0ae78
FS   0x81c0ae7c
MEM  0x81c0ae80
```

## External Resources

Visible resource paths:

```text
\Shell\KeChengBiao.dlx
\Shell\KeChengBiaoHeiSeTuPian.dlx
rb
wb+
```

It also embeds the four common shell VX resources directly in the BDA image:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

The `HeiSeTuPian` resource name mirrors other normal apps and probably means a
black/dark image variant, not a separate executable module.

## API Use

The current indirect-call scan finds 304 runtime table calls:

```text
FS  +0x000  4   fopen-like
FS  +0x004  6   fclose-like
FS  +0x008  6   fread-like
FS  +0x00c  1   fwrite-like
FS  +0x010  3   fseek-like
FS  +0x02c  1   directory-exists/chdir-like
FS  +0x030  1   mkdir-like
FS  +0x048  1   disk info-like

GUI +0x030/+0x050/+0x054  event poll/step/dispatch
GUI +0x084/+0x088/+0x08c/+0x17c  frame lifecycle
GUI +0x1a4/+0x1a8  control/window create and destroy
GUI +0x308/+0x30c  begin/end draw
GUI +0x338/+0x33c/+0x378/+0x4f0  text mode, color, draw text
GUI +0x430/+0x46c  rectangle/resource helper family
GUI +0x35c/+0x40c  image/region helper family

SYS +0x080  22  delay/sleep-like
RES +0x090   2  resource state/helper-like
RES +0x094   5  trace/log-like
MEM +0x008/+0x00c allocation/free-like
```

## Window and Event Flow

`课程表.bda` uses the normal app event pump:

```text
GUI+0x030(message, frame_or_context)
GUI+0x050()
GUI+0x054(message)
...
GUI+0x17c(frame)
```

This matches Element, BBVM, Time, Notepad, and other full apps. A custom display
program that only performs a one-shot draw from startup is missing this
lifecycle, which explains why the current Showcase experiments can display in
one narrow Element-style case but cannot close or can reboot in fuller variants.

The app creates at least one GUI object through `GUI+0x1a4`. The call shape is
consistent with the existing create-window/control ABI:

```text
a0 = class/name pointer
a1 = title/caption or 0
a2 = style, observed high bits in the 0x08000000 family
a3 = flags/extra, often 0
stack fields = id, x, y, width, height, parent, extra
```

## Drawing Behavior

The draw path combines:

```text
GUI+0x308 / GUI+0x30c       drawing handle lifetime
GUI+0x074                  draw/present guard
GUI+0x430                  rectangle setup/helper-like
GUI+0x46c                  resource/image helper-like
GUI+0x4f0                  text draw-like
```

`GUI+0x430` is called with stack-backed records and rectangle-like arguments
such as x/y/width/height. Several `GUI+0x46c` calls immediately follow these
records, with `a1`/`a2` coming from calculated coordinates. This strengthens the
interpretation that `GUI+0x46c` is a resource/image lookup or draw helper used
by normal apps, not a generic DLX loader.

## File Flow

The FS pattern is standard:

```text
open DLX or data file with "rb"
read fixed records
seek as needed
write/update with "wb+"
close handles
prepare app data directory with FS+0x02c / FS+0x030
```

No evidence suggests `RES+0x094` loads these DLX files. Hardware probes showed
`RES+0x094` path-style calls returning without visible resource effects, while
this app plainly uses FS calls for the resource/data path.

## SDK Implications

1. Showcase-style custom apps should use the full frame/control event lifecycle,
   not just the one-shot `GUI+0x540` image draw path.
2. `GUI+0x430` should be tracked as a rectangle/paint helper candidate.
3. `GUI+0x46c` remains resource/image helper-like, with Schedule adding more
   evidence alongside Ebook.
4. `RES+0x094` should stay named trace/log-like.

## Open Items

1. Exact struct passed to `GUI+0x430`.
2. Exact object/class string used by the `GUI+0x1a4` call.
3. The persistent file format for the timetable data.
4. Whether the black-image DLX is chosen by theme, display mode, or a resource
   fallback path.
