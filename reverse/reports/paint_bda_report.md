# Paint BDA report

Target: `应用/程序/电子画板.bda`

Generated evidence:

- `reverse/reports/paint_layout.json`
- `reverse/reports/paint_calls.txt`
- `reverse/reports/paint_fs_context.txt`
- `reverse/reports/paint_gui368_context.txt`
- `reverse/reports/paint_gui35c_context.txt`
- `reverse/reports/paint_gui40c_context.txt`
- `reverse/reports/paint_gui418_context.txt`
- `reverse/reports/paint_gui314_context.txt`
- `reverse/reports/paint_media.txt`

## Header and layout

```text
title              电子画板
category           0x08
file size          1245084 bytes
entry offset       0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
checksum           ok in inventory
```

The generic layout scanner did not find BSS bounds for this app, but startup
does cache the runtime API tables:

```text
RES 0x81d269c0
GUI 0x81d269c4
SYS 0x81d269c8
FS  0x81d269cc
MEM 0x81d269d0
```

## Embedded resources

The app does not reference external `\shell\*.dlx` paths. It does reference
image extensions:

```text
.jpg
.bmp
bmp;jpg
```

Scanning the BDA itself finds four embedded VX images:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

These are probably menu/icon resources stored in the BDA header/resource area.
Most of the app's large size is code/data rather than external DLX skins.

## API usage summary

Classified indirect calls:

```text
GUI      566
FS        11
MEM        9
RES       33
SYS        2
UNKNOWN    4
total    625
```

Hot GUI offsets:

```text
GUI +0x368  157
GUI +0x35c   63
GUI +0x40c   57
GUI +0x378   35
GUI +0x418   30
GUI +0x314   29
GUI +0x46c   27
GUI +0x4f0   13
GUI +0x310   10
```

This is currently the best production app for drawing/canvas APIs.

## Pixel/line drawing

`GUI +0x368` is the strongest newly mapped helper. It is called 157 times, often
inside loops with coordinates and RGB565 colors:

```text
a0 = surface/canvas handle
a1 = x
a2 = y
a3 = RGB565 color
```

Examples:

```text
0x81c04018: GUI+0x368(surface, x+i, y, 0xf800)
0x81c04054: GUI+0x368(surface, x+i, y2, 0xf800)
0x81c04094: GUI+0x368(surface, x, y+i, 0xf800)
0x81c040d0: GUI+0x368(surface, x2, y+i, 0xf800)
```

These four loops form rectangle borders in red (`0xf800`), so `GUI +0x368` can
be named a put-pixel or draw-point helper with high confidence.

Other call sites invert a 16-bit color before passing it:

```text
lhu a3, color
nor a3, zero, a3
andi a3, a3, 0xffff
GUI+0x368(surface, x, y, inverted_rgb565)
```

This fits eraser/selection/invert drawing behavior.

## Region drawing and refresh

`GUI +0x35c` is called before region copy/draw operations and after color
creation. It commonly looks like:

```text
GUI+0x35c(surface, color_or_resource)
```

`GUI +0x40c` is called with rectangular parameters:

```text
a0 = surface
a1 = x
a2 = y
a3 = width/height-like
sp+0x10 = second dimension or style
```

Examples show constant `a3 = 0xf0`, `sp+0x10 = 0xf7`, which looks like
240x247-style canvas or panel refresh regions. Smaller calls use `0x13` and
offset coordinates for tool/UI strips.

`GUI +0x418` appears as a larger-region draw or update helper:

```text
a0 = surface
a1 = x
a2 = y
a3 = 0x13
sp+0x10 = 0x15
sp+0x14 = pointer/handle
sp+0x18 = x2/width-like
sp+0x1c = y2/height-like
sp+0x20 = 0
```

Most `GUI+0x418` calls are immediately followed by:

```text
GUI+0x314(surface)
```

That makes `GUI +0x314` a strong flush/present/update candidate for a drawing
surface.

## File behavior

The app uses very little FS compared with its GUI workload:

```text
FS +0x000  fopen-like
FS +0x004  fclose-like
FS +0x010  fseek-like
FS +0x014  ftell-like
FS +0x02c  directory exists/chdir-like
FS +0x030  mkdir-like
FS +0x03c  findfirst-like
FS +0x044  findclose-like
FS +0x048  disk-info-like
```

The picture load/save path checks file size:

```text
fopen(path, mode)
fseek(file, 0, SEEK_END)
size = ftell(file)
fclose(file)
if size > 0x400000: reject
```

That is the same `0x400000` image-size guard observed in the Album
`LoaderPicture` path.

## Cross-checks

- With Album: confirms the picture extension set `.jpg/.bmp/bmp;jpg` and the
  `0x400000` maximum image size guard.
- With Picture notes: strengthens `GUI +0x35c/+0x40c/+0x410/+0x418` as the
  picture/canvas draw family.
- With Text/Ebook/Notepad: confirms `GUI +0x4f0` text drawing appears even in
  a canvas app for labels/tool UI.
- With Settings: confirms `FS +0x048` disk-info use before storage-dependent
  actions.

## Open questions

- Exact signatures for `GUI +0x35c`, `GUI +0x40c`, and `GUI +0x418` still need
  a controlled hardware probe.
- Determine whether `GUI +0x314` is present/flush or invalidate.
- Identify the bitmap/JPEG save path. The current scan sees extensions and
  file-size checks but not enough direct context to name the encoder calls.
