# Paint/canvas API notes

Primary evidence: `reverse/reports/paint_bda_report.md` for the bundled
`电子画板.bda`.

## Put pixel

`GUI +0x368` is currently the strongest mapped canvas helper. The paint app
calls it 157 times, often inside simple line/rectangle loops:

```text
a0 = surface/canvas handle
a1 = x
a2 = y
a3 = RGB565 color
```

Examples from the paint app draw red rectangle borders with `0xf800`:

```text
GUI+0x368(surface, x+i, y,   0xf800)
GUI+0x368(surface, x+i, y2,  0xf800)
GUI+0x368(surface, x,   y+i, 0xf800)
GUI+0x368(surface, x2,  y+i, 0xf800)
```

The SDK wrapper is:

```c
int bda_gui_put_pixel_like(bda_handle_t surface, s32 x, s32 y, u16 rgb565);
```

The helper should be used only with a real drawing surface/window handle from
the GUI lifecycle. Passing `0` or a guessed handle is unsafe.

## Region draw and flush

The paint app heavily uses the same picture/render family seen in Album:

```text
GUI +0x35c  bind/select color or object-like
GUI +0x40c  region draw/copy-like
GUI +0x410  render helper-like
GUI +0x418  larger region/render finish-like
GUI +0x314  flush/present/update candidate
```

`GUI +0x418` call sites are usually followed immediately by `GUI +0x314(surface)`,
so `+0x314` is a strong present/flush candidate. Do not treat it as confirmed
until a controlled hardware probe can redraw a surface without it.

## Picture load/save leads

The paint app references:

```text
.jpg
.bmp
bmp;jpg
```

Its file-size guard matches the photo album:

```text
fopen(path, mode)
fseek(file, 0, SEEK_END)
size = ftell(file)
fclose(file)
if size > 0x400000: reject
```

This cross-checks Album's `LoaderPicture` path, but the paint app's image
encoder/save ABI is not mapped yet.
