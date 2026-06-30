# Text and simple drawing notes

The GUI table has direct text drawing helpers. These are inferred from notepad
and ebook call sites where the string argument points at visible UI labels such
as search prompts, note titles, and bookmark labels. See
`reverse/reports/notepad_bda_report.md` and
`reverse/reports/ebook_bda_report.md` for the current per-BDA evidence.

## Draw text

`GUI +0x4f0` is currently named `draw_text_like`:

```text
a0 = drawing/window handle
a1 = x
a2 = y
a3 = GBK/ASCII string
stack+0x10 = extra/width/flags, often -1
```

Examples:

```text
draw_text_like(handle, 0x20, 0x04, "search", -1)
draw_text_like(handle, 0x04, 0x1c, "label", -1)
draw_text_like(handle, 0x04, 0x30, "label", -1)
ebook call sites:
  GUI+0x4f0(handle, 0x20, 0x04, str_at_0x81c16d88, style)
  GUI+0x4f0(handle, 0xa8, 0x12d, str_at_0x81c16d90, style)
  GUI+0x4f0(handle, 0x34, 0x22, dynamic_string, -1)
```

The SDK wrapper is:

```c
int bda_gui_draw_text_like(bda_handle_t handle, s32 x, s32 y, const char *text, s32 extra);
```

## Text color

`GUI +0x378` appears to create or select an RGB color for a drawing handle:

```text
a0 = drawing/window handle
a1 = red
a2 = green
a3 = blue
return = color object/value
```

The returned value is passed to `GUI +0x33c`:

```text
a0 = drawing/window handle
a1 = color
```

Common patterns:

```text
color = GUI +0x378(handle, 255, 255, 255)
GUI +0x33c(handle, color)

color = GUI +0x378(handle, 0, 0, 0)
GUI +0x33c(handle, color)
```

The SDK wrappers are:

```c
int bda_gui_rgb_like(bda_handle_t handle, u32 r, u32 g, u32 b);
int bda_gui_set_text_color_like(bda_handle_t handle, u32 color);
```

## Text mode

`GUI +0x338(handle, 1)` is commonly called immediately before selecting a color
and drawing text. It is probably a text background/transparent mode setter.

The SDK wrapper is:

```c
int bda_gui_set_text_mode_like(bda_handle_t handle, u32 mode);
```

## Practical status

The main missing piece is a clean way to obtain the drawing/window handle for a
new app without borrowing a full bundled window procedure. Existing apps use
their own window/control handles, then call the text helpers from paint or event
handlers. For now these wrappers are best used inside a GUI callback or in a
probe that already has a valid handle.

Hardware probe note:

```text
TextDraw.bda called set_text/rgb/draw_text with handle 0 and rebooted.
TextEditOnly.bda, TextEditColor.bda, and TextEditDraw.bda all rebooted too.
Those probes called GUI+0x1a4 to create an edit/control directly from the
app's bare main function, so direct standalone control creation is unsafe or
the argument layout is still incomplete.
```

Treat `handle=0` as unsafe for these drawing calls. Use a real control/window
handle, or call them from a paint/event callback that receives a valid handle.

`TextNativePatch.bda` is a safer follow-up probe. It is based on the original
notepad BDA and only replaces the strings drawn by existing notepad paint/event
code:

```text
查找到的文件 -> TEXTAPI-OK!!
查找         -> TEXT
```

If that probe appears and shows the replacement labels, the screen text drawing
chain is confirmed and the remaining work is window/control creation, not text
rendering itself.

Confirmed on hardware:

```text
The search window title changed to TEXT.
The search-result window title changed to TEXTAPI-OK!!.
```

`TextBodyPatch.bda` is an additional body-label probe. It changes the notepad
"new note" dialog labels drawn by `GUI+0x4f0`:

```text
名  称: -> NAME-OK
内  容: -> BODY-OK
```

Confirmed on hardware:

```text
The edit-note window displayed NAME-OK and BODY-OK in the body label area.
```

Additional bundled-app cross-checks:

```text
课程表.bda      GUI+0x4f0: 13 calls
九门课程.bda    GUI+0x4f0: 50 calls
```

Both use the same text/color cluster from a real app lifecycle. Nine Courses
draws dynamic course text buffers as well as static labels, so `GUI+0x4f0`
should be considered a general GBK/ASCII text renderer once a valid draw handle
and window/control lifecycle exist.
