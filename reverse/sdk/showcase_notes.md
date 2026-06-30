# Showcase / Element-Style Display Notes

This file records the current display-app experiments based on
`元素周期表.bda`.

## Confirmed Baseline

`DLXImageElementStyle_Rebuild.bda` was rebuilt from
`reverse/examples/dlx_image_element_style_probe.c` and still displays a VX image
through the Element-style path:

```text
FS fopen/read DLX -> keep full VX resource block -> GUI+0x540(draw, x, y, w, h, vx)
```

It displays the image, but it does not show a system-managed window chrome and
cannot close cleanly yet.

True-device update:

```text
DLXImageElementStyle_Rebuild.bda  displays image, no window chrome, cannot close
ShowcaseDisplayOnly.bda           reboots immediately
ShowcaseDemo.bda                  reboots immediately
```

So the header/category/build path is not the issue. The known-good baseline and
the failing Showcase builds share the same template and patch point, but differ
in resource source and lifecycle logic.

Cross-check from `reverse/reports/schedule_bda_report.md` and
`reverse/reports/ninecourse_bda_report.md`: bundled display/content apps do not
just draw a bitmap from startup. They create/register GUI objects, run the
normal event pump, and draw from callbacks or object-owned draw handles. Nine
Courses also uses `GUI+0x1ac/+0x1b0` object update calls. This makes the current
Showcase failure more likely a lifecycle/object-model mismatch than a BDA header
or DLX parser problem.

## Showcase Regression

`ShowcaseDisplayOnly.bda` and `ShowcaseDemo.bda` initially rebooted before
showing the image. The strongest current explanation is file-open error
handling:

```c
f = bda_fs_fopen_raw(path, "rb");
if (!f) ...
```

is unsafe. Native FS calls can return `-1` on failure. If a custom DLX is not
found and `-1` is treated as a valid handle, the following `fread` can reboot
the device. The wrapper/probe code must test:

```c
if (f <= 0) {
    return -1;
}
```

This is an SDK correction for all file-opening code, not just Showcase.

The later Showcase builds already use `f <= 0`, so the remaining reboot is
probably after or beyond file open. New staged probes were added:

```text
build/ShowcaseStage1Load.bda   opens system text_A.dlx, reads VX, then exits
build/ShowcaseStage2Frame.bda  stage 1 plus frame registration
build/ShowcaseStage3Draw.bda   stage 2 plus one GUI+0x540 draw
```

All three use the Element template and known system `text_A.dlx` resource, not
the custom 320x240 `ShowcaseDemo.dlx`. This isolates the failure point:

```text
Stage1 fails  -> file/DLX/VX loading path is still wrong
Stage2 fails  -> frame descriptor/register path is wrong
Stage3 fails  -> draw handle or GUI+0x540 call timing is wrong
all pass      -> Showcase reboot is likely custom DLX size/path or event-loop logic
```

Hardware update:

```text
ShowcaseStage1Load.bda:
  clicked app
  showed "open text_A"
  showed "open failed"
  exited normally
```

This proves the Stage1 failure is the `FS+0x000` path form, not a header issue
and not a crash in DLX parsing. The original Stage1 path was the full
`A:\应用\数据\shell\text_A.dlx` GBK path. A new path matrix probe was added to
test the native FS path spelling actually accepted by the device.

New no-template probes:

```text
build/TextAPathMatrix.bda
  tries eight path spellings for text_A.dlx and reports raw fopen handles

build/ShowcaseStage1LoadMulti.bda
  tries the same path spellings, then reads DLX/VX if any path opens

build/ShowcaseStage2FrameMulti.bda
  Stage1Multi plus frame registration

build/ShowcaseStage3DrawMulti.bda
  Stage2Multi plus one GUI+0x540 draw
```

For `TextAPathMatrix.bda` / `TextAPathClassify.bda`, `00000000` and
`FFFFFFFF` are failure. Other non-zero values can be valid handles even when
their high bit is set and they look negative as signed integers.

Hardware result for `TextAPathClassify.bda`:

```text
0: OK 80A8CFF0
1: OK 80A8D048
2: OK 80A8D0A0
3: ZERO 00000000
4: ZERO 00000000
5: ZERO 00000000
6: ZERO 00000000
7: ZERO 00000000
```

This corrected the Stage loader bug: it had treated `0x80xxxxxx` handles as
failure because it used signed `f > 0` checks. `ShowcaseStage1LoadMulti.bda`,
`ShowcaseStage2FrameMulti.bda`, and `ShowcaseStage3DrawMulti.bda` were rebuilt
to accept any handle except `0` and `0xffffffff`.

Hardware result after that fix:

```text
Stage1Mu:
  open text_A -> open ok path 0 -> load ok -> exits normally

Stage2Mu:
  open text_A -> open ok path 0 -> load ok -> register frame
  screen becomes white, frame ok, dialog disappears, cannot exit

Stage3Mu:
  open text_A -> open ok path 0 -> load ok -> register frame
  screen becomes white, frame ok, dialog disappears, then crashes/reboots
```

Interpretation:

```text
Stage1 proves DLX path/parse/VX extraction is correct.
Stage2 proves frame registration succeeds, but returning without an event loop
or GUI+0x17c cleanup leaves the shell in an owned white frame state.
Stage3 draws from mainline and then frees VX/returns while the frame can still
receive callbacks; that lifetime mismatch can explain the crash.
```

Follow-up probes:

```text
build/ShowcaseStage2Close.bda  registers the frame, then immediately calls GUI+0x17c
build/ShowcaseStage3Loop.bda   captures draw state in the callback and runs a bounded event loop
```

Hardware result:

```text
ShowcaseStage2Close.bda:
  frame/image display succeeds, but GUI+0x17c does not close/return cleanly.

ShowcaseStage3Loop.bda:
  image displays, then the app crashes/reboots after the display phase.
```

This confirms the image path itself works. The remaining issue is frame
ownership and cleanup. Two narrower probes were built:

```text
build/ShowcaseStage2StopRel.bda  uses the BBVM-observed GUI+0x088 then GUI+0x04c cleanup
build/ShowcaseStage3Hold.bda     displays via event loop but intentionally skips frame/VX cleanup
```

## Window Lifecycle Difference From Element

Element does not rely on a system-drawn title bar. It draws its own UI from DLX
resources and handles touch hot zones in the window proc. For close/back actions
it sends command-like messages such as `0x66`/`0x7fd` and then lets the GUI event
loop and default proc progress naturally.

Known stable Element loop:

```c
while (GUI+0x030(msg, 0)) {
    GUI+0x050();
    GUI+0x054(msg);
}
GUI+0x17c(frame);
```

Do not assume that setting a local `g_exit` from inside a window proc is
equivalent to Element's close path. It can break while GUI dispatch is still
active.

## Message Naming Correction

`0x00b1` is not a generic touch-exit message. In Element it behaves like an
input/redraw trigger. Treat the old SDK name `BDA_MSG_TOUCH_B_LIKE` as a
deprecated misname and prefer `BDA_MSG_REDRAW_INPUT_LIKE`.

## Current Test Builds

```text
build/DLXImageElementStyle_Rebuild.bda  known display baseline
build/ShowcaseFallbackOnly.bda          display-only, forces system text_A.dlx
build/ShowcaseDisplayOnly.bda           display-only, tries ShowcaseDemo.dlx then fallback
build/ShowcaseDemo.bda                  display plus experimental close handling
build/ShowcaseDemo.dlx                  custom VX resource container
build/ShowcaseStage1Load.bda            staged diagnostic: load only
build/ShowcaseStage2Frame.bda           staged diagnostic: load + frame
build/ShowcaseStage3Draw.bda            staged diagnostic: load + frame + draw once
build/TextAPathMatrix.bda               no-template path-form matrix for text_A.dlx
build/TextAPathClassify.bda             clearer path matrix: labels OK/ZERO/NEG1
build/ShowcaseStage1LoadMulti.bda       no-template Stage1 with path fallback
build/ShowcaseStage2FrameMulti.bda      no-template Stage2 with path fallback
build/ShowcaseStage3DrawMulti.bda       no-template Stage3 with path fallback
```
