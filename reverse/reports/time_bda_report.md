# 时间.bda Analysis Report

## Status

First static report focused on time UI, clock resources, and system delay/time
API leads.

Evidence:

```text
应用/程序/时间.bda
reverse/reports/time_layout.json
reverse/reports/time_calls.txt
reverse/sdk/time_notes.md
reverse/sdk/text_notes.md
reverse/sdk/window_notes.md
```

## Header And Layout

```text
file size          244,860 bytes
menu title         时间
category           0x09
entry file offset  0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
BSS                0x81c326a0..0x81c367e1
header checksum    ok
```

Cached runtime table globals:

```text
RES  0x81c326a0
GUI  0x81c326a4
SYS  0x81c326a8
FS   0x81c326ac
MEM  0x81c326b0
```

External DLX references:

```text
\shell\newtimepic.dlx
\shell\timepic.dlx
```

## API Usage Summary

`时间.bda` has 736 classified indirect runtime-table calls:

```text
GUI +0x074  104 calls  draw/present state guard
GUI +0x308   60 calls  begin draw
GUI +0x30c   50 calls  end draw
GUI +0x040   51 calls  send/message-like
GUI +0x4f0   23 calls  draw text-like
GUI +0x378   16 calls  RGB/color helper-like
GUI +0x33c   15 calls  set text/foreground color-like
GUI +0x084   13 calls  register frame
GUI +0x030   13 calls  event poll
GUI +0x050   13 calls  event step
GUI +0x054   13 calls  event dispatch
GUI +0x17c   12 calls  close/release frame

FS  +0x048    4 calls  disk/storage information
FS  +0x000   13 calls  open/fopen-like
FS  +0x008   19 calls  read/fread-like

SYS +0x080   42 calls  delay/sleep-like
RES +0x08c    4 calls  resource helper candidate
RES +0x090    1 call   resource/picture state-like
RES +0x094   24 calls  trace/log-like
```

## Time/Clock Interpretation

Despite being the clock app, the current scan shows only `SYS+0x080` strongly
classified in the SYS table. That offset is already known as delay/sleep-like
from other apps and probes. Time retrieval may be:

- hidden behind a different table/call shape not caught by the current scanner,
- implemented through data files and GUI timers,
- or present in a nearby SYS offset that needs context-level analysis.

The app is still valuable because it uses a clock-specific DLX pair and many
text/color calls. It likely formats time/date strings itself after retrieving
state through an unclassified call.

## Text And Drawing

The app uses a stable text drawing cluster:

```text
GUI+0x338  text mode-like
GUI+0x378  RGB/color helper
GUI+0x33c  set text color-like
GUI+0x4f0  draw text-like
```

This cross-checks Notepad: both normal apps use `GUI+0x4f0` in a complete
window/draw lifecycle. Text probes that crashed should be rewritten from these
contexts rather than using standalone calls.

## Storage/Disk Calls

`FS+0x048` appears four times. In `fs_notes.md`, this offset is disk/storage
info-like. In a time app it may be used to check persistent settings storage
before reading/writing clock/world-time configuration.

## Cross-Checks

- Same event-loop family as Element and Notepad:
  `GUI+0x084`, `+0x030`, `+0x050`, `+0x054`, `+0x17c`.
- Same text cluster as Notepad, supporting SDK text wrappers.
- Uses clock-specific DLX resources, supporting the DLX-as-skin/artwork model.

## Unknowns

1. Exact time-get API used by this app.
2. Meaning of `RES+0x08c`, which appears four times here.
3. Settings file paths for time/alarm/world clock configuration.
4. Whether `SYS+0x080` is only delay here or also participates in timer ticks.

## Next Static Tasks

1. Extract context around all SYS-table calls, not only scanner-classified ones.
2. Search for packed date/time format constants and string formats.
3. Compare with `闹钟.bda`, which should expose alarm set/get paths.
4. Update `time_notes.md` only after the exact SYS offsets are verified.

