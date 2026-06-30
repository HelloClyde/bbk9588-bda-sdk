# Picture decode and display notes

Additional supporting report: `reverse/reports/ebook_bda_report.md` covers a
DLX/resource-heavy reading app that uses related GUI picture/resource helpers.
`reverse/reports/paint_bda_report.md` covers a canvas-heavy app and is the
strongest current source for `GUI+0x368` pixel drawing and the
`GUI+0x35c/+0x40c/+0x418/+0x314` draw/refresh family.
`reverse/reports/schedule_bda_report.md` and
`reverse/reports/ninecourse_bda_report.md` add content-app evidence for
external shell DLX skin pairs and the `GUI+0x430/+0x46c` rectangle/resource
helper family.
Small-game display cross-check reports:

```text
reverse/reports/eros_bda_report.md
reverse/reports/linkgame_bda_report.md
reverse/reports/blackwhite_bda_report.md
reverse/reports/jiugongge_bda_report.md
reverse/reports/thunder_bda_report.md
reverse/reports/tank_bda_report.md
reverse/reports/sango_bda_report.md
```

Together they show games embedding the same four VX resources directly in the
BDA resource area instead of external DLX packages.

See also `reverse/reports/album_bda_report.md` for the first per-BDA static
report on `我的相册.bda`.

These notes are from `我的相册.bda`, especially its `LoaderPicture` routine.
Names are provisional, but the offsets and argument shapes are grounded in the
album call sites.

## High-level flow

The system file manager routes `jpg` and `bmp` files to the bundled album app:

```text
A:\应用\程序\我的相册.bda
*.bmp
*.jpg
bmp;jpg
LoaderPicture
LoaderPicture FileName = %s
开始解码
ret = %d
---Width = %d, Height = %d---
成功
失败
```

The album opens the selected image through the file-system table first:

```text
FS +0x000  fopen(path, "rb")
FS +0x010  fseek(file, 0, SEEK_END)
FS +0x014  ftell(file)
FS +0x004  fclose(file)
```

It rejects empty files and files larger than `0x400000` bytes before decoding.

## LoaderPicture ABI

The app-level `LoaderPicture` entry is at `0x81c0683c` in `我的相册.bda`.
One observed caller passes:

```text
a0 = owner/window/image handle
a1 = full path buffer
a2 = output picture descriptor
a3 = preview/extra flag
stack+0x10 = mode byte, observed 0
```

The routine finds the final `.` in the filename. Extensions beginning with
`b` or `B` take the BMP path; all other extensions take the JPEG-like path.

## Decode APIs

Two GUI-table calls are now exposed by `bda_sdk.h`:

```text
GUI +0x670  BMP decode-like
  a0 = owner/window/image handle
  a1 = bda_picture_like_t *out
  a2 = path
  a3 = work/output scratch pointer

GUI +0x808  JPEG decode-like
  a0 = owner/window/image handle
  a1 = bda_picture_like_t *out
  a2 = path
  a3 = mode byte
```

`LoaderPicture` logs and propagates the decoder return value. The surrounding
branching suggests `0` is success and `1` is failure, but this still needs a
hardware probe with known-good BMP/JPEG files.

The provisional output struct:

```c
typedef struct bda_picture_like {
    void *pixels;       /* +0x00 RGB565 pixels */
    u32 dim_a;          /* +0x04 width/height-like */
    u32 dim_b;          /* +0x08 width/height-like */
    u32 aux0c;          /* +0x0c stride/orientation-like */
    u8 mode10;          /* +0x10 */
    u8 mode11;          /* +0x11 */
    u8 reserved12;      /* +0x12 */
    u8 reserved13;      /* +0x13 */
    void *owned_pixels; /* +0x14 rotated/copied RGB565 buffer, if allocated */
    s32 selected_index; /* +0x18 initialized to -1 by album helper */
} bda_picture_like_t;
```

## Post-decode rendering

Ebook cross-check: the ebook app adds supporting evidence for `GUI +0x46c`.
Many call sites load `a1` and `a2` from adjacent words in small resource records
before calling `GUI+0x46c`. Several sites then query or draw with neighboring
GUI helpers. This makes `+0x46c` more likely to be a resource/image lookup or
draw helper than a plain text routine.

Schedule and Nine Courses cross-check this interpretation. They call
`GUI+0x430` to build or normalize rectangle-like stack records, then call
`GUI+0x46c` with calculated coordinates/resource values. This pair should be
treated as a normal content-app image/resource path, separate from the direct
VX block draw helper at `GUI+0x540`.

The album reads the descriptor fields at `+0x00`, `+0x04`, `+0x08`, `+0x0c`,
`+0x10`, `+0x14`, and `+0x18`. It compares dimensions against `240` and `320`
to choose centering or scaling.

The helper at `0x81c014d0` normalizes a decoded RGB565 image into this
descriptor. Depending on a global orientation byte, it either points directly at
the decoder buffer or allocates a copied/rotated RGB565 buffer with `MEM+0x008`.

Display then goes through the same region/render family already seen in games:

```text
GUI +0x40c  region draw/copy-like
GUI +0x410  helper used by album render path
GUI +0x418  render finish/scale-helper-like
```

The dispatcher at `0x81c06f78` selects render/crop/scale modes `0..7` through a
jump table and calls `GUI+0x418` heavily.

## SDK status

`bda_sdk.h` currently provides:

```c
int bda_gui_decode_bmp_like(void *owner, bda_picture_like_t *out,
                            const char *path, void *work);
int bda_gui_decode_jpeg_like(void *owner, bda_picture_like_t *out,
                             const char *path, u32 mode);
```

These are suitable for experiments. For robust custom apps, the next missing
piece is a tested helper that creates/obtains a valid owner handle and renders
the returned RGB565 buffer with the correct scaling mode.
