# 记事本.bda Analysis Report

## Status

First static report. Evidence comes from:

```text
应用/程序/记事本.bda
reverse/reports/bda_inventory.json
reverse/reports/notepad_calls.txt
reverse/sdk/text_notes.md
reverse/sdk/window_notes.md
reverse/sdk/fs_notes.md
```

This report is not yet function-complete. It is the first pass that anchors
layout, resource files, and SDK/API usage for cross-checking.

## Header And Layout

```text
file size          138,460 bytes
menu title         记事本
category           0x09
entry file offset  0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
BSS                0x81c18700..0x81c32801
header checksum    ok
```

Cached runtime table globals:

```text
RES  0x81c18700
GUI  0x81c18704
SYS  0x81c18708
FS   0x81c1870c
MEM  0x81c18710
```

This layout matches the common native-BDA model used by `元素周期表.bda`: startup
copies runtime table pointers from `0x81c00004..0x81c00014` into app-local BSS
globals, then all SDK calls go through those globals.

## External Resources

Static DLX references:

```text
\shell\FP_PIC_BLUE.dlx
\shell\FP_PIC_BLACK.dlx
\shell\EnoteBlueSearch.dlx
\shell\text_A.dlx
\shell\text_B.dlx
\shell\enote_black_add.dlx
\shell\enote_corner.dlx
```

Interpretation:

- `text_A.dlx` / `text_B.dlx` are shared text UI resources. This cross-checks
  the earlier text/image experiments that used `text_A.dlx`.
- `EnoteBlueSearch.dlx`, `enote_black_add.dlx`, and `enote_corner.dlx` are
  notepad-specific skins or UI fragments.
- The `_BLUE`/`_BLACK` pairs suggest the app supports at least two shell themes.

## API Usage Summary

`记事本.bda` has 955 classified indirect runtime-table calls in the current
scanner. The strongest groups:

```text
GUI +0x040  184 calls  send/message-like
GUI +0x074  139 calls  draw/present state guard
GUI +0x308   77 calls  begin draw
GUI +0x30c   62 calls  end draw
GUI +0x03c   53 calls  notify/message-like
GUI +0x2b8   46 calls  message box
GUI +0x084   12 calls  register frame
GUI +0x030   12 calls  event poll
GUI +0x050   12 calls  event step
GUI +0x054   12 calls  event dispatch
GUI +0x17c   12 calls  close/release frame

FS  +0x000   22 calls  open/fopen-like
FS  +0x004   23 calls  close/fclose-like
FS  +0x024   32 calls  remove/delete-like
FS  +0x03c   10 calls  findfirst-like
FS  +0x040    1 call   findnext-like
FS  +0x044    1 call   findclose-like

SYS +0x080   38 calls  delay/sleep-like
RES +0x094   17 calls  trace/log-like
```

The GUI event loop count is notable: 12 frame registrations and 12 matching
`GUI+0x030/+0x050/+0x054/+0x17c` groups. Unlike `元素周期表`, which has a small
number of windows, Notepad appears to create several modal screens/dialogs.

## Text Rendering Cross-Checks

Text-related calls are present:

```text
GUI +0x338  set text mode-like      6 calls
GUI +0x33c  set text color-like     8 calls
GUI +0x378  RGB/color helper-like   8 calls
GUI +0x4f0  draw text-like         11 calls
```

This supports the earlier hardware observation that patching Notepad window text
can display `NAME-OK` and `BODY-OK`. It also gives a safer source for the text
SDK than the standalone text probes that crashed: Notepad uses text drawing as
part of a normal window/control lifecycle.

Working hypothesis:

- `GUI+0x4f0` is valid for text rendering.
- The unstable probes likely used the wrong lifecycle, wrong handle, or exited
  while GUI dispatch/draw state was still active.
- Future text probes should copy a Notepad call context rather than call
  `draw_text` against arbitrary handles.

## File-System Behavior

Notepad is currently one of the best samples for completing native FS APIs:

- Open/close/read/write/seek/tell all appear.
- `FS+0x024` has 32 calls and is likely delete/remove.
- `FS+0x03c/+0x040/+0x044` appears as the directory listing group.
- Directory setup uses `FS+0x02c/+0x030`.

This cross-checks `fs_notes.md` and should be used before writing more
directory-listing probes. Important correction from Showcase still applies:
file-open failure must be treated as `handle <= 0`, not only `handle == 0`.

## Window/Event Behavior

Notepad uses the same broad window model as Element:

```text
GUI+0x2fc  surface/object creation
GUI+0x084  frame registration
GUI+0x030  event poll
GUI+0x050  event step
GUI+0x054  dispatch
GUI+0x17c  final close/release
```

It also uses many `GUI+0x040` and `GUI+0x03c` calls, supporting the idea that
`0x040` and `0x03c` are distinct send/notify routes. Element uses these routes
for close/back-style commands such as `0x66`; Notepad should be inspected next
for the same command constants.

## Unknowns

1. Exact Notepad document path format and extension filters.
2. Which window procedures correspond to list, edit, search, and confirm
   dialogs.
3. The argument layout for `GUI+0x134`, `+0x138`, `+0x46c`, and bitmap/control
   helper calls.
4. Whether Notepad uses the same `0x00b1` redraw/input message semantics as
   Element.
5. Exact text-control lifecycle needed for stable custom text rendering.

## Next Static Tasks

1. Disassemble `记事本.bda` with function labels around all 12 `GUI+0x084`
   frame registrations.
2. Extract context for `GUI+0x4f0` text calls and compare with
   `text_notes.md`.
3. Extract context for `FS+0x03c/+0x040/+0x044` and update `fs_notes.md` with
   the notepad find-data layout.
4. Compare command constants against `元素周期表.bda` (`0x66`, `0x7fd`, `0x083e`,
   `0x0844`, `0x00b1`).

