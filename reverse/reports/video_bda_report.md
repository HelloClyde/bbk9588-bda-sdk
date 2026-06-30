# 飞天影音.bda / 飞天影音_.bda Analysis Report

## Status

First static report focused on the video/player architecture. These two large
BDAs are treated together because they share the same `player.bin`/`player.cfg`
model and very similar scanner profiles.

Evidence:

```text
应用/程序/飞天影音.bda
应用/程序/飞天影音_.bda
reverse/reports/video_layout.json
reverse/reports/video_alt_layout.json
reverse/reports/video_calls.txt
reverse/reports/video_alt_calls.txt
reverse/sdk/media_notes.md
reverse/sdk/system_bin_notes.md
```

## Header And Layout

`飞天影音.bda`:

```text
file size          3,172,572 bytes
menu title         飞天影音
category           0x80000008
entry file offset  0x95f8
runtime file base  0x81bf6a28
BSS                0x81efd300..0x81f0ed20
header checksum    ok
```

Cached runtime table globals:

```text
RES  0x81efd300
GUI  0x81efd304
SYS  0x81efd308
FS   0x81efd30c
MEM  0x81efd310
```

`飞天影音_.bda`:

```text
file size          2,878,316 bytes
menu title         飞天影音_
category           0x80000008
entry file offset  0x95f8
runtime file base  0x81bf6a28
BSS                0x81eb5590..0x81ed4c40
header checksum    ok
```

Cached runtime table globals:

```text
GUI  0x81eb5594
SYS  0x81eb5598
FS   0x81eb559c
MEM  0x81eb55a0
```

The alternate build does not expose a RES table cache through the current
detector, but still has the common GUI/SYS/FS/MEM tables.

## Player Resources

Both files reference:

```text
\player.bin
\player.cfg
```

The primary build contains MP3-related strings; the alternate build contains
MP4/3GP/MP3 extension markers. Neither app uses DLX shell resources in the
current path scan.

This supports the existing hypothesis in `media_notes.md`: video playback is
not exposed as one small `play_video()` SDK function. The app bundles or launches
a larger player runtime, likely through `player.bin` and configuration.

## API Usage Summary

`飞天影音.bda` classified table calls:

```text
FS  +0x008  25 calls
FS  +0x010  28 calls
FS  +0x000   7 calls
FS  +0x068   2 calls

SYS +0x040   4 calls
SYS +0x06c   3 calls
SYS +0x070   1 call
SYS +0x074   1 call
SYS +0x078   1 call
SYS +0x07c   1 call
SYS +0x080   1 call
SYS +0x084   1 call
SYS +0x088   1 call
SYS +0x08c   1 call
SYS +0x090   1 call
SYS +0x0a0   1 call
```

`飞天影音_.bda` classified table calls:

```text
FS  +0x07c  19 calls
FS  +0x068   3 calls
FS  +0x000   2 calls

SYS +0x06c   1 call
SYS +0x070   5 calls
SYS +0x074   1 call
SYS +0x078   1 call
SYS +0x080   3 calls
SYS +0x084   1 call
SYS +0x08c   1 call
SYS +0x090   1 call
SYS +0x094   1 call
SYS +0x09c   1 call
SYS +0x0a0   1 call
```

Both have only a tiny native GUI shell:

```text
GUI+0x084/+0x030/+0x050/+0x054/+0x17c  about 2 windows/loops
GUI+0x2b8  1 message box
```

## UNKNOWN Calls Are Expected

The scanner reports thousands of `UNKNOWN` calls, especially:

```text
UNKNOWN +0x040  ~1350 calls
UNKNOWN +0x010  hundreds of calls
UNKNOWN +0x000  hundreds of calls
```

These should not be interpreted as missing system SDK offsets. They are most
likely calls through internal codec/player function tables embedded in or loaded
by the BDA. This is exactly what one would expect from an MPlayer/FFmpeg-like
runtime.

## Cross-Checks

- `飞天音乐.bda` uses high-level media-player SYS offsets `+0x004/+0x020/...`.
- `GAMEBOY.BDA` uses raw audio streaming offsets `SYS+0x06c/+0x074/+0x078`.
- `飞天影音.bda` uses `SYS+0x06c/+0x074/+0x078/+0x0a0` but also a huge private
  player table, suggesting it bridges native firmware device/audio/video APIs
  with a bundled player engine.

## SDK Implication

For custom BDA apps, the practical video strategy is probably:

1. learn how `飞天影音` invokes/configures `player.bin`, or
2. reuse the firmware device/audio primitives for simpler media tasks,
3. avoid trying to implement full video playback through one guessed API call.

## Unknowns

1. Whether `player.bin` is extracted from the BDA body or exists on disk.
2. Exact format and role of `player.cfg`.
3. Whether SYS `+0x06c/+0x070/+0x074/+0x078` include video device setup or only
   audio output.
4. Meaning of `FS+0x068`, which appears in both video builds and game framework
   notes.

## Next Static Tasks

1. Locate embedded `player.bin` boundaries and compare with filesystem copy.
2. Extract strings around MPlayer/codec code to identify imported function
   tables.
3. Compare `飞天影音` with `飞天音乐` around SYS calls to separate audio vs video
   device operations.
4. Update `media_notes.md` with `player.bin` invocation details once the launch
   sequence is mapped.

