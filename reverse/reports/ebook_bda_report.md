# Ebook BDA report

Target: `应用/程序/电子图书.bda`

Generated evidence:

- `reverse/reports/ebook_layout.json`
- `reverse/reports/ebook_calls.txt`
- `reverse/reports/ebook_text_context.txt`
- `reverse/reports/ebook_img_context.txt`
- `reverse/reports/ebook_media.txt`
- `reverse/reports/ebook_dlx.txt`
- `reverse/reports/ebook_extra_dlx.txt`

## Header and layout

```text
title              电子图书
category           0x08
file size          147116 bytes
entry offset       0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
BSS/global range   0x81c1a8d0..0x81c1f861
checksum           ok in inventory
```

Runtime table globals detected from startup:

```text
RES 0x81c1a8d0
GUI 0x81c1a8d4
SYS 0x81c1a8d8
FS  0x81c1a8dc
MEM 0x81c1a8e0
```

## External resources

The BDA directly references:

```text
\shell\ebook_res_black.dlx
\shell\ebook_res_blue.dlx
```

Both resources are present under `应用/数据/shell`. Each package has 22 type-1
VX resources. The package is UI-heavy:

```text
240x320 full-screen pages/backgrounds
240x69 header/footer regions
240x30 bars/list rows
236x178 panels
65x92 illustration/icon blocks
17x19 / 17x20 small icons
```

Related resources also exist and have very similar structures:

```text
\shell\ebook_A.dlx
\shell\ebook_B.dlx
\shell\ebookpic.dlx
\shell\newebookpic.dlx
```

The app analyzed here references the `ebook_res_*` pair directly. The extra
ebook DLX files are likely older or alternate skins used by other launch paths.

## API usage summary

Classified indirect calls:

```text
GUI      446 calls
FS        63 calls
MEM       14 calls
RES       12 calls
SYS        5 calls
UNKNOWN   12 calls
total    532 calls
```

The app is overwhelmingly GUI-driven. Its strongest SDK value is text,
window/control, picture/resource drawing, and file navigation behavior.

Hot GUI offsets:

```text
GUI +0x03c  34
GUI +0x2fc  29
GUI +0x4f0  27
GUI +0x40c  24
GUI +0x33c  22
GUI +0x0e0  22
GUI +0x040  22
GUI +0x46c  20
GUI +0x274  16
GUI +0x4a8  13
GUI +0x35c  12
```

## Text drawing evidence

`GUI +0x4f0` is called 27 times. The call context is consistent with the text
draw helper also seen in Notepad:

```text
lw   v0, 0x4f0(gui)
a0 = draw/window/context
a1 = x
a2 = y
a3 = string pointer
sp+0x10 = -1 or style/color-like value
jalr v0
```

Examples:

```text
0x81c0054c: a1=s4, a2=s0, a3=s2, sp+0x10=-1
0x81c02d20: a1=0x20, a2=4, a3=0x81c16d88
0x81c02da8: a1=0xa8, a2=0x12d, a3=0x81c16d90
0x81c0a79c: a1=0x34, a2=0x22, a3=s1
```

This is better evidence than the earlier standalone text probes because the
calls occur inside the app's normal window/draw lifecycle. The old crashy text
probes likely used the correct helper with an incomplete frame lifecycle.

## Resource/image drawing evidence

`GUI +0x46c` is called 20 times. The contexts repeatedly pass two adjacent
values from small resource records:

```text
lw a1, 0(record)
lw a2, 4(record)
lw v0, 0x46c(gui)
jalr v0
```

Other call sites use stack pairs and then immediately call `GUI +0x0f8` or
helper code that works with the returned dimensions. This strengthens the
current interpretation of `GUI +0x46c` as a resource/image-related helper used
by reading apps, picture apps, and DLX-backed UI screens.

The app also uses `GUI +0x35c/+0x40c/+0x410/+0x418`-adjacent picture pipeline
offsets, overlapping with the photo album evidence.

## File-system behavior

The ebook app uses a broad but conventional FS set:

```text
FS +0x000  fopen-like
FS +0x004  fclose-like
FS +0x008  fread-like
FS +0x00c  fwrite-like
FS +0x010  fseek-like
FS +0x014  ftell-like
FS +0x024  remove/delete-like
FS +0x02c  chdir/dir-exists-like
FS +0x030  mkdir-like
FS +0x048  disk-info/free-space-like
FS +0x07c  storage-ready-like
```

Compared with Notepad and Recorder, this confirms the same C-like file API
surface is used by readers as well as tools.

## Event/window behavior

The standard event loop is present:

```text
GUI +0x030  poll-like
GUI +0x050  step-like
GUI +0x054  dispatch-like
GUI +0x17c  destroy/close frame-like
```

Window/control offsets are dense:

```text
GUI +0x1a4/+0x1a8/+0x1ac/+0x1b0
GUI +0x270/+0x274/+0x27c
GUI +0x2fc/+0x304/+0x308/+0x30c
GUI +0x338/+0x33c/+0x378
GUI +0x490/+0x498/+0x4a8
```

This is a good target for the next window/control SDK pass because it is more
feature-rich than Element but much smaller than Notepad.

## Cross-checks

- With `记事本.bda`: confirms `GUI +0x4f0` text drawing inside a real lifecycle.
- With `我的相册.bda`: overlaps with picture/resource offsets
  `GUI +0x35c/+0x40c/+0x410/+0x418`.
- With Element/DLX image probes: confirms production apps use VX-only DLX
  packages for complex screens, not just simple image tests.
- With FS notes: confirms reader apps use `fopen/fread/fseek/ftell` style calls
  plus storage helpers.

## Open questions

- The exact control descriptors around `GUI +0x270/+0x274/+0x27c` need a
  dedicated control-creation pass.
- The meaning of `RES +0x064` appears once and is not yet named.
- `UNKNOWN` table calls are probably app-local function-pointer tables or GUI
  callback records; they should not be promoted to SDK APIs without xrefs.
