# Window/control creation notes

`GUI +0x1a4` creates controls or windows. The clearest call sites are notepad,
ebook, and settings.

## Create call

Current inferred ABI:

```text
a0 = class name
a1 = caption/title string or 0
a2 = style
a3 = flags/extended style, often 0
stack+0x10 = control id
stack+0x14 = x
stack+0x18 = y
stack+0x1c = width
stack+0x20 = height
stack+0x24 = parent/window handle
stack+0x28 = extra/user data
```

Observed classes:

```text
"listbox"    notepad app
"ListBox"    notepad app, used as a caption/string with listbox
"edit"       settings app
"medit"      notepad app, likely multiline edit
"EB_SCROLL"  ebook app scroll bar
```

Examples from bundled apps:

```text
create("medit", 0, 0x08000000, 0, 0x6e, 0x3c, 0x1b, 0xa8, 0x14, parent, 0)
create("listbox", "ListBox", 0x08090001, 0, 0x6a, 0, 0xda, 0xf0, 0x109, parent, 0)
create("EB_SCROLL", 0, 0x08000000, 0, 0x400, 0x0b, 0x7a, 0xa0, 0x12, parent, 0)
create("edit", caption, 1, 0, 2, 0, 0, 0, 0, parent, 0)
create(schedule-class, 0, 0x08000000-family, 0, id, x, y, w, h, parent, 0)
create(ninecourse-class, same-title, 0x08080000-family, 0, id, x, y, w, h, parent, 0)
```

The SDK wrapper is:

```c
bda_handle_t bda_gui_create_window_like(
    const char *class_name,
    const char *caption,
    u32 style,
    u32 flags,
    u32 id,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    bda_handle_t parent,
    u32 extra
);
```

The older `bda_gui_create_ex` wrapper is kept for compatibility but its argument
order is less well matched to the call sites.

Do not call this from a bare main function with a null parent and arbitrary
class/caption strings. Hardware tests that attempted to create an edit-like
control directly from startup rebooted. Original apps create child controls
from an existing app/window context and then attach properties with `GUI+0x040`.

## Drawing lifecycle

Notepad paint paths use this pattern before drawing images or text:

```text
draw = GUI+0x308(window_or_control_handle)
GUI+0x074(1)
... draw images/text with draw ...
GUI+0x074(0)
GUI+0x30c(draw)
```

`GUI+0x308` is currently wrapped as `bda_gui_begin_draw_like()`, and
`GUI+0x30c` as `bda_gui_end_draw_like()`. The lock/present function at
`GUI+0x074` is still named `bda_gui_pump_present_like()`.

## Top-level frame descriptor

Calculator provides the cleanest top-level frame creation path. It builds a
0x34-byte descriptor and passes it to `GUI+0x084`:

```text
+0x00 style, calculator uses 0x08000000
+0x04 reserved/zero
+0x08 title/name string
+0x0c reserved/zero
+0x10 reserved/zero
+0x14 reserved/zero
+0x18 window procedure pointer
+0x1c reserved/zero
+0x20 reserved/zero
+0x24 height, calculator uses 240
+0x28 width, calculator uses 320
+0x2c surface/object from GUI+0x2fc(15)
+0x30 reserved/zero
```

The resulting handle is then used with the event loop:

```text
GUI+0x030(message_buffer, frame_handle)  -> loop while nonzero
GUI+0x050()
GUI+0x054(message_buffer)
GUI+0x17c(frame_handle)                 -> close/destroy frame
```

`WindowTextProbe.bda` and `WindowTextCbOnly.bda` are first hardware probes for
this model. They patch the calculator main to register a custom frame descriptor
whose window procedure is compiled from C.

Hardware result:

```text
Text printed to the display, one character at a time, then the screen became
white.
```

This confirms the custom frame and C window procedure are active. Two likely
causes of the white screen are:

```text
1. The probe drew text before calling the default window procedure, and the
   default procedure cleared/repainted over it.
2. The event loop exited and the probe called GUI+0x17c, closing/clearing the
   frame.
```

`WindowTextV2.bda` tests the calculator order more closely:

```text
register frame -> GUI+0x098(frame, 0x100) -> default proc -> draw text
```

`WindowTextNoClose.bda` is the same style, but skips `GUI+0x17c` after the
event loop to test whether the close call is responsible for the white screen.

`WindowTextV2.bda` still printed text one character at a time and then went
white. A stronger suspect is the explicit `GUI+0x040(frame, 0x66, 0, 0)` used
by early probes. Several bundled apps send message `0x66` when closing/aborting
a view, so it should be treated as a close/exit-like message until proven
otherwise.

Follow-up probes:

```text
WindowTextV3NoSend.bda  activate + draw, but does not send message 0x66
WindowTextV3NC.bda      same, and also skips GUI+0x17c after the event loop
```

Hardware result:

```text
WindowTextV3NoSend.bda went directly to a white screen and did not show text.
```

This means message `0x66` is likely required to enter a useful paint/update path
for this minimal frame, but the default handling or the subsequent return path
still clears the display.

Follow-up probes:

```text
WindowTextV4Intercept.bda  sends 0x66, but intercepts it in the custom window
                           procedure, draws text, returns 1, and does not call
                           GUI+0x17c.
WindowTextV4Keep.bda       same, then redraws repeatedly after the event loop
                           to test whether returning to the shell clears it.
```

## BBVM Window/Draw Model

`BB虚拟机.bda` gives the clearest native wrapper for text drawing.

Its window procedure handles these messages:

```text
0x60:
    global_frame = hwnd
    global_draw = GUI+0x304()
    then call default proc GUI+0x08c(hwnd, msg, wparam, lparam)

0x66:
    GUI+0x30c(global_draw)
    GUI+0x088(global_frame)
    GUI+0x04c(global_frame)
    return 0
```

Its high-level text draw wrapper does not call `GUI+0x308`. Instead it uses the
draw handle captured from `GUI+0x304`:

```text
GUI+0x074(1)
GUI+0x4f0(global_draw, x, y, text, -1)
GUI+0x0e0(global_frame, 0, 0)
GUI+0x074(0)
```

Color and text mode are set on `global_draw`:

```text
color = GUI+0x378(global_draw, r, g, b)
GUI+0x334(global_draw, color)     background/fill color-like
GUI+0x33c(global_draw, color)     foreground/text color-like
GUI+0x338(global_draw, mode)
```

`WindowTextBBVMStyle.bda` and `WindowTextBBVMSend60.bda` are probes that use
this BBVM-style drawing path instead of the earlier `GUI+0x308` path.

Hardware result:

```text
WindowTextBBVMStyle.bda printed two white lines, but the background was also
white and the app then returned to a white screen.
```

This confirms the `GUI+0x304` draw-handle path works. The probe used white
foreground by mistake; BBVM initializes a white background and black foreground.

Follow-up probes:

```text
WindowTextBBVMBlack.bda  black text using the same BBVM-style draw path
WindowTextBBVMHold.bda   black text plus a short redraw/hold loop to separate
                         "drawing works" from "demo returned to shell"
```

Hardware result:

```text
WindowTextBBVMBlack.bda showed two black lines on a white background, then
crashed immediately. Text still appeared one character at a time, which appears
to be the platform font renderer behavior rather than our code drawing one
character at a time.
```

The crash was likely caused by cleanup mismatch:

```text
The probe called GUI+0x30c(draw) on message 0x66, then still passed 0x66 to
the default window procedure, and then called GUI+0x30c(draw) again after the
event loop.

BBVM does not do that. On 0x66 it calls:
    GUI+0x30c(global_draw)
    GUI+0x088(global_frame)
    GUI+0x04c(global_frame)
    return 0
```

Follow-up probes:

```text
WindowTextBBVMExactClose.bda  exact BBVM-style 0x66 cleanup, no duplicate end
WindowTextBBVMNoEndHold.bda   suppresses cleanup and redraws for a while, to
                              verify the crash is cleanup-related
```

Hardware result:

```text
WindowTextBBVMExactClose.bda still showed black text on a white background and
then crashed immediately.
```

Stop point / open problem:

```text
Text drawing itself is confirmed:
    BBVM-style frame creation works.
    Message 0x60 can capture a draw handle via GUI+0x304.
    GUI+0x074(1), GUI+0x4f0, GUI+0x0e0(frame,0,0), GUI+0x074(0) displays text.

The unresolved issue is the frame/window lifetime after drawing:
    Our standalone probe returns/crashes after display.
    Replicating only the local 0x66 cleanup is not sufficient.
    More blind hardware probes are not useful until the surrounding BBVM
    event/state machine is understood.
```

Next reverse target, when returning to this:

```text
Do not guess more probe variants first.
Trace BBVM's caller/state machine around the frame loop:
    frame descriptor setup at 0x81c032f4..0x81c03360 and 0x81c03530..0x81c0359c
    window proc at 0x81c006bc
    loop at 0x81c03488..0x81c034f4 and 0x81c036b0..0x81c03720
    globals 0x81c43c78(frame), 0x81c43c80(draw), 0x81c43d68(message scratch)

Specifically determine what higher-level state tells BBVM to leave the loop,
what owns GUI+0x088/+0x04c cleanup, and whether the VM has an outer dispatcher
that re-enters/returns differently than our patched calculator main.
```

## Message calls

`GUI +0x03c` and `GUI +0x040` are both message/property calls with the shape:

```text
a0 = handle
a1 = message/property id
a2 = value
a3 = value
```

`GUI +0x040` is heavily used for edit-control properties and command messages.
Examples include `0xf184`, `0xf186`, `0xf0dd`, `0xf0df`, `0xf1b5`, and `0x864`.

`GUI +0x03c` appears to be a related notify/post/send path. It is commonly used
with message `0x66`, `0x10`, `0x120`, `0x805`, and `0x806`.

## Destroy

`GUI +0x1a8(handle)` is used before removing controls and when closing views.

## Object update pair

`九门课程.bda` adds strong evidence for two nearby object/control helpers:

```text
GUI+0x1ac(handle, 0x64, 0x190)
GUI+0x1b0(handle, 0x64)
```

They appear during view rebuild, scroll/page, or object refresh paths. Keep the
names provisional, but do not ignore them when cloning a full display app: they
are absent from the minimal Element image probe and may be part of the missing
Showcase lifecycle.

## Remaining gap

We still need the top-level app window/bootstrap callback path. Apps use parent
handles supplied by the runtime or by earlier framework code, then create child
controls. Direct custom drawing is mapped, but a standalone text demo still
needs a reliable parent/drawing handle.
