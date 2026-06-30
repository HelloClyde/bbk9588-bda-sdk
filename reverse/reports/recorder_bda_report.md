# Recorder BDA report

Target: `应用/程序/数码录音.bda`

Generated evidence:

- `reverse/reports/recorder_layout.json`
- `reverse/reports/recorder_calls.txt`
- `reverse/reports/recorder_sys_context.txt`
- `reverse/reports/recorder_fs_context.txt`
- `reverse/reports/recorder_media.txt`
- `reverse/reports/recorder_dlx.txt`

## Header and layout

```text
title              数码录音
category           0x08
file size          82364 bytes
entry offset       0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
BSS/global range   0x81c0abe0..0x81e35731
checksum           ok in inventory
```

The BSS range is much larger than the code file. That fits a recorder/player
app that keeps large buffers or backend state in BSS.

Runtime table globals detected from startup:

```text
RES 0x81c0abe0
GUI 0x81c0abe4
SYS 0x81c0abe8
FS  0x81c0abec
MEM 0x81c0abf0
```

## External resources

The BDA references two DLX skin files:

```text
\shell\record_A.dlx
\shell\record_B.dlx
```

Both files are present under `应用/数据/shell`. `dlx_inspect.py` identifies both
as variant-3 DLX packages with 18 resources. Every resource is type 1 and
decodes as a VX RGB565 image. Important dimensions include:

```text
240x320 full-screen background
126x30 status/button strips
110x34 labels/buttons
47x50 controls
32x30 and 19x19 icons
45x3 progress-line fragments
```

No non-image resource type is required for this app based on current DLX
inspection.

## Strings and file model

Relevant strings:

```text
*.wav
.wav
recorder
Rec%5.5d.wav
 play ====>>>%d,%d,%d
###g_RecorderFileName=%s###RecorderCurrPath=%s###
```

This strongly suggests:

- file list filter: `*.wav`
- generated filenames: `Rec00000.wav` style
- current recorder directory/path global
- separate playback path with diagnostic logging

## API usage summary

Classified indirect calls:

```text
FS      40 calls
GUI     58 calls
SYS     77 calls
MEM      5 calls
RES     11 calls
total  181 calls
```

Hot system/media offsets:

```text
SYS +0x004  28
SYS +0x020  25
SYS +0x02c  13
SYS +0x040   2
SYS +0x08c   2
SYS +0x090   2
RES +0x094  11
```

The `SYS +0x004/+0x020/+0x02c` cluster matches the high-level media backend
cluster already seen in `飞天音乐.bda`, not the raw PCM path from `GAMEBOY.BDA`.
For now these should be named as recorder/music backend candidates rather than
final audio ABI names.

`RES +0x094` is used 11 times. Hardware probes already showed this offset is
trace/log-like, not a DLX loader. The recorder strings with format placeholders
fit that interpretation.

## File-system behavior

The recorder uses:

```text
FS +0x000  fopen-like
FS +0x004  fclose-like
FS +0x008  fread-like
FS +0x010  fseek-like
FS +0x024  remove/delete-like
FS +0x02c  chdir/dir-exists-like
FS +0x030  mkdir-like
FS +0x03c  findfirst-like
FS +0x040  findnext-like
FS +0x044  findclose-like
FS +0x048  disk-info/free-space-like
FS +0x078  unknown storage/path helper
FS +0x07c  storage-ready-like
```

The first helper opens a file, reads `0x24` bytes, and checks for the DLX magic
when loading UI resources. Separate later FS call sites handle WAV list
enumeration, deletion, and generated recording names.

The repeated `FS +0x024` call sites are a useful cross-check for the delete-like
meaning already inferred from other file-manager style apps.

## GUI/event behavior

The app uses the normal event loop offsets:

```text
GUI +0x030  poll-like
GUI +0x050  step-like
GUI +0x054  dispatch-like
GUI +0x17c  destroy/close frame-like
```

It also uses common window/control/resource offsets:

```text
GUI +0x074, +0x03c
GUI +0x0e4/+0x0e8
GUI +0x1ac/+0x1b0
GUI +0x338/+0x33c/+0x378/+0x4f0
GUI +0x46c
```

The text offsets are lighter here than in Notepad/Ebook, but present enough to
confirm the recorder UI uses the same GUI stack rather than a fully custom game
framebuffer.

## Cross-checks

- With `飞天音乐.bda`: shares the SYS high-level media cluster
  `+0x004/+0x020/+0x02c` and trace-heavy `RES +0x094`.
- With `记事本.bda` and FS probes: confirms the FS table has normal C-like
  file operations plus find/delete/storage helpers.
- With DLX work: confirms another production app whose DLX resources are only
  type-1 VX images.

## Open questions

- Exact signatures for `SYS +0x004`, `SYS +0x020`, and `SYS +0x02c` are still
  unresolved. They are likely backend state/player-recorder operations.
- `SYS +0x08c/+0x090` appear only twice each here; compare against
  `GAMEBOY.BDA`, video, and music before naming.
- The WAV header/write path still needs closer function-level slicing to find
  whether recording uses `FS +0x00c` directly or delegates most output to the
  SYS media backend.
