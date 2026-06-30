# 飞天音乐.bda Analysis Report

## Status

First static report focused on audio/media SDK evidence.

Evidence:

```text
应用/程序/飞天音乐.bda
reverse/reports/music_layout.json
reverse/reports/music_calls.txt
reverse/sdk/media_notes.md
reverse/sdk/gameboy_notes.md
reverse/sdk/system_bin_notes.md
```

## Header And Layout

```text
file size          150,900 bytes
menu title         飞天音乐
category           0x08
entry file offset  0xa3b0
runtime entry VA   0x81c00020
runtime file base  0x81bf5c70
header checksum    ok
```

Cached runtime table globals:

```text
RES  0x81c1a9e0
GUI  0x81c1a9e4
SYS  0x81c1a9e8
FS   0x81c1a9ec
MEM  0x81c1a9f0
```

External DLX references:

```text
\shell\mp3_liba.dlx
\shell\mp3_libc.dlx
\shell\mp3_libb.dlx
\shell\mp3_lyric_help.dlx
```

The entry offset differs from the common `0x95f8` template, so this is a useful
layout counterexample for the builder/analyzer.

## API Usage Summary

`飞天音乐.bda` has 552 classified indirect runtime-table calls:

```text
SYS +0x004  15 calls
SYS +0x020  15 calls
SYS +0x02c   5 calls
SYS +0x034   4 calls
SYS +0x038   4 calls
SYS +0x094   3 calls
SYS +0x000   1 call
SYS +0x00c   1 call
SYS +0x010   1 call
SYS +0x018   1 call
SYS +0x01c   1 call
SYS +0x040   1 call
SYS +0x080   1 call
SYS +0x090   1 call

FS  +0x000  14 calls  open/fopen-like
FS  +0x004  14 calls  close/fclose-like
FS  +0x00c  12 calls  write/fwrite-like
FS  +0x008   7 calls  read/fread-like
FS  +0x048   3 calls  disk/storage info-like
FS  +0x07c   1 call   storage-ready-like

GUI +0x040  89 calls  send/message-like
GUI +0x4f0  18 calls  draw text-like
GUI +0x2fc  14 calls  surface/object create-like
GUI +0x084   4 calls  register frame

RES +0x094 110 calls  trace/log-like
RES +0x090   1 call   resource state-like
```

## Audio/System Table Interpretation

This app is currently the best original sample for the low SYS offsets
`+0x000..+0x040`. These offsets are separate from the later audio stream offsets
seen in GAMEBOY (`SYS+0x06c/+0x074/+0x078/+0x08c/+0x0a0`).

Working interpretation:

- `飞天音乐` likely uses a higher-level packaged music/player interface.
- `GAMEBOY.BDA` uses a lower-level raw audio stream interface.
- The SDK should keep these as two distinct groups until argument contexts are
  recovered.

The repeated pair:

```text
SYS +0x004  15 calls
SYS +0x020  15 calls
```

suggests a start/stop, open/close, or state/update pair in the player backend.
The DLX names (`mp3_*`) make the media role clear, but the exact function names
are not yet proven.

## File And UI Behavior

The app combines media-device calls with normal FS operations:

- opens/reads audio or playlist files,
- writes persistent data (`FS+0x00c` has 12 calls),
- checks disk info and storage readiness,
- draws lyric/help/status text via `GUI+0x4f0`.

`mp3_lyric_help.dlx` plus 18 text draw calls indicate lyric/help UI is native
GUI text, not only bitmap resources.

## Cross-Checks

- `GAMEBOY.BDA` confirms a raw audio path with later SYS offsets.
- `飞天音乐.bda` confirms a separate media-player path with earlier SYS offsets.
- `system_bin_notes.md` contains firmware strings for audio devices and codecs;
  those should be used to name the SYS offsets after context extraction.
- `RES+0x094` appears heavily but hardware probes show this is trace/log-like,
  not a DLX loader. The high count likely reflects debug logging in the music
  player.

## Unknowns

1. Exact names and signatures for SYS `+0x000..+0x040`.
2. Whether the player backend decodes MP3 in firmware or in app code.
3. Playlist/file extension filters.
4. Relationship between `飞天音乐.bda` and `飞天影音.bda`.

## Next Static Tasks

1. Extract context for SYS `+0x004` and `+0x020` call pairs.
2. Compare with `飞天影音.bda` and `飞天影音_.bda` for shared media backend.
3. Search system binaries for strings near MP3/player functions.
4. Add a separate SDK section for high-level media-player SYS calls, distinct
   from GAMEBOY raw audio streaming.

