# 我的相册.bda Analysis Report

## Status

First static report focused on picture display and image-related SDK evidence.

Evidence:

```text
应用/程序/我的相册.bda
reverse/reports/album_layout.json
reverse/reports/album_calls.txt
reverse/sdk/picture_notes.md
reverse/sdk/media_notes.md
reverse/sdk/fs_notes.md
```

## Header And Layout

```text
file size          317,052 bytes
menu title         我的相册
category           0x08
entry file offset  0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
header checksum    ok
```

Cached runtime table globals:

```text
RES  0x81c440a0
GUI  0x81c440a4
SYS  0x81c440a8
FS   0x81c440ac
MEM  0x81c440b0
```

The generic layout script did not infer BSS start/end for this app, but
`bda_table_globals.py` confirms the runtime table cache block at `0x81c440a0`.

## API Usage Summary

`我的相册.bda` has 269 classified indirect runtime-table calls:

```text
GUI +0x418   31 calls  render/finish-like helper
GUI +0x40c   11 calls  region draw-like helper
GUI +0x35c   11 calls  object/resource bind-like helper
GUI +0x368    8 calls  picture/display helper candidate
GUI +0x410    5 calls  render helper candidate
GUI +0x030    8 calls  event poll
GUI +0x050    8 calls  event step
GUI +0x054    8 calls  event dispatch
GUI +0x084    8 calls  register frame
GUI +0x17c    8 calls  frame close/release

FS  +0x000    3 calls  open/fopen-like
FS  +0x010    3 calls  seek-like
FS  +0x014    3 calls  tell/size-like
FS  +0x03c    2 calls  findfirst-like
FS  +0x040    2 calls  findnext-like
FS  +0x044    2 calls  findclose-like
FS  +0x07c    1 call   storage-ready-like

RES +0x090    2 calls  resource/picture state-like
RES +0x094   55 calls  trace/log-like or diagnostics
SYS +0x08c    1 call   media/device helper candidate
SYS +0x090    1 call   media/device helper candidate
```

## Picture Pipeline Evidence

This app is currently the strongest original-BDA evidence for the picture
display path. The call pattern is different from Element's simple VX draw path:

```text
RES +0x090  -> returns/fills picture state-like data
GUI +0x35c  -> bind object/resource-like
GUI +0x40c  -> draw region-like
GUI +0x418  -> render finish/present-like
```

This cross-checks `picture_notes.md`, where `RES+0x090` was already suspected
as a decoded-picture/resource state helper. Because `我的相册` uses only a few
FS open/seek/tell calls but many GUI render helper calls, image decoding is
probably not a raw app-local DLX parser like Element. It likely relies on system
picture decode/display services.

## File-System Behavior

The app uses:

```text
FS+0x07c        storage-ready/media-present check
FS+0x03c/040/044 directory scan group
FS+0x000/010/014 open/seek/tell for image files
```

This makes `我的相册` a good sample for finishing directory-listing semantics
for user media directories. It is weaker than Notepad for ordinary file editing,
but stronger for media scanning.

## Cross-Checks

- `元素周期表.bda` displays VX images from DLX using app-local parsing and
  `GUI+0x540`.
- `我的相册.bda` does not show the same `GUI+0x540` path in the current scan; it
  clusters around `GUI+0x35c/+0x40c/+0x418` and `RES+0x090`.
- Therefore there are at least two image paths in the firmware:
  1. direct VX resource draw (`GUI+0x540`)
  2. decoded/user-picture display path (`RES+0x090` + GUI render helpers)

## Unknowns

1. Exact argument layout for `RES+0x090`.
2. Whether `GUI+0x368`, `+0x40c`, `+0x410`, and `+0x418` operate on a common
   picture descriptor.
3. Which image formats are accepted by the system decoder in this app.
4. Exact user-photo directory and filename filter strings. The generic string
   extractor is polluted by embedded image data, so this needs function-context
   extraction rather than raw strings.

## Next Static Tasks

1. Extract instruction context for both `RES+0x090` calls.
2. Recover the struct passed through `GUI+0x35c/+0x40c/+0x418`.
3. Compare with `飞天影音.bda` and `电子图书.bda` image/video paths.
4. Build a probe that calls `RES+0x090` only after copying the Album argument
   layout, not as a guessed standalone call.

