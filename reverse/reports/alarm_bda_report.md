# 闹钟.bda Analysis Report

## Status

First static report focused on RTC/alarm APIs. This report cross-checks
`时间.bda` and `time_notes.md`.

Evidence:

```text
应用/程序/闹钟.bda
reverse/reports/alarm_layout.json
reverse/reports/alarm_calls.txt
reverse/sdk/time_notes.md
reverse/sdk/window_notes.md
```

## Header And Layout

```text
file size          88,476 bytes
menu title         闹钟
category           0x09
entry file offset  0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
BSS                0x81c0c3c0..0x81e0d301
header checksum    ok
```

Cached runtime table globals:

```text
RES  0x81c0c3c0
GUI  0x81c0c3c4
SYS  0x81c0c3c8
FS   0x81c0c3cc
MEM  0x81c0c3d0
```

External resources:

```text
\shell\naoling_A.dlx
\shell\naoling_B.dlx
```

## API Usage Summary

`闹钟.bda` has 443 classified indirect runtime-table calls:

```text
SYS +0x080   6 calls  delay/sleep-like
SYS +0x0a8   4 calls  alarm/time commit or refresh-like
SYS +0x0ac   3 calls  alarm set-like
SYS +0x0b0   3 calls  alarm get-like
SYS +0x0b8   4 calls  time/RTC get-like

GUI +0x074  42 calls  draw/present guard
GUI +0x4f0  27 calls  draw text-like
GUI +0x308  23 calls  begin draw
GUI +0x30c  21 calls  end draw
GUI +0x084   5 calls  register frame
GUI +0x030   5 calls  event poll
GUI +0x050   5 calls  event step
GUI +0x054   5 calls  event dispatch
GUI +0x17c   5 calls  frame close/release

FS  +0x000  15 calls  open/fopen-like
FS  +0x004  15 calls  close/fclose-like
FS  +0x03c   2 calls  findfirst-like
FS  +0x044   2 calls  findclose-like
FS  +0x07c   2 calls  storage-ready-like
```

## RTC And Alarm API Evidence

This app is the clearest sample for clock/alarm SDK calls:

```text
SYS+0x0b8  time/RTC get-like
SYS+0x0b0  alarm get-like
SYS+0x0ac  alarm set-like
SYS+0x0a8  alarm/time commit/refresh-like
```

This cross-checks the earlier `time_probe.c` design: probes should read
`SYS+0x0b8` and `SYS+0x0b0`, but avoid `SYS+0x0ac` and `SYS+0x0a8` unless the
struct layout is fully known, because those likely write settings.

`时间.bda` uses many `SYS+0x080` delay calls but does not expose the direct
`SYS+0x0b8` path in the current scanner. Therefore `闹钟.bda` should be treated
as the authoritative sample for RTC/alarm function signatures.

## UI Behavior

The app uses a normal native window lifecycle:

```text
GUI+0x084  register frame
GUI+0x030  event poll
GUI+0x050  event step
GUI+0x054  event dispatch
GUI+0x17c  frame close/release
```

It also uses the same text drawing cluster seen in `记事本.bda` and `时间.bda`:

```text
GUI+0x338  text mode-like
GUI+0x378  RGB/color helper-like
GUI+0x33c  set text color-like
GUI+0x4f0  draw text-like
```

## File-System Behavior

The FS calls are mostly configuration/resource related, not heavy media
scanning. The presence of `FS+0x03c/+0x044` without much `FS+0x040` suggests
short directory checks or one-shot scans.

## Unknowns

1. Exact RTC struct layout returned by `SYS+0x0b8`.
2. Exact alarm struct layout used by `SYS+0x0b0/+0x0ac`.
3. Meaning of `SYS+0x0a8` arguments and whether it commits to persistent
   storage or refreshes firmware alarm state.
4. Alarm sound file/resource selection path.

## Next Static Tasks

1. Extract contexts around all `SYS+0x0b8/+0x0b0/+0x0ac/+0x0a8` calls.
2. Compare with `系统设置.bda` for date/time setting UI.
3. Update `time_probe.c` output interpretation after struct fields are mapped.

