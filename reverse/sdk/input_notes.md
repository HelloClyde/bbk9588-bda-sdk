# Touch and Key Input Notes

These notes are inferred from bundled native BDA window procedures and the
system full-screen diagnostic/window procedure in `C200.bin`.

## Callback ABI

Bundled code strongly suggests the GUI window procedure/callback uses:

```c
int wndproc(void *hwnd, u32 message, u32 wparam, u32 lparam);
```

MIPS argument registers:

```text
a0 = window/control handle
a1 = message id
a2 = wparam or packed command/touch data
a3 = lparam or extra event data
```

For packed values, bundled code commonly does:

```text
low  = value & 0xffff
high = value >> 16
```

`bda_sdk.h` provides:

```c
BDA_LOWORD(x)
BDA_HIWORD(x)
BDA_MAKEWORD(lo, hi)
typedef int (*bda_wndproc_t)(bda_handle_t hwnd, u32 message, u32 wparam, u32 lparam);
```

## Observed Message-Like Constants

These constants appear in bundled window procedures and are currently exposed
with `_LIKE` suffixes until hardware probes confirm exact names:

```text
0x0010  create/setup style message in many call sites
0x00b0  touch/pen-like branch in the system diagnostic window procedure
0x00b1  redraw/input-like in 元素周期表; touch/pen-like in one system diagnostic branch
0x083e  command-like branch
0x0841  focus-like branch
0x0842  input/touch-like branch in the system diagnostic window procedure
0x0844  keydown-like branch
```

One bundled app compares the message argument with `0x083e` and `0x0844`, then
splits `wparam` into low/high 16-bit fields. `C200.bin` also has a system
full-screen diagnostic/window procedure around `0x8000f718` that branches on
`0x00b0`, `0x00b1`, `0x0842`, and `0x0844`.

Important correction from the Showcase experiment: do not treat `0x00b1` as an
exit/touch-up event in generic app code. `元素周期表.bda` uses it as a redraw or
input-refresh trigger. Exiting on `0x00b1` can close an app during startup before
the first image is drawn.

## Touch/Pen Leads

The system binaries contain diagnostic strings:

```text
The MSG_LBUTTONDOWN x=%d y=%d
The MSG_MOUSEMOVE x=%d y=%d
The MSG_LBUTTONUP x=%d y=%d
pen up!
MSG_LBUTTON
```

This confirms the firmware has touch/pen down, move, and up messages. The exact
coordinate packing is still being mapped. `C200.bin` uses a global touch/input
state structure around `0x80477d54` in the diagnostic path.

Observed command/control-like IDs in app code:

```text
0x047e
0x047f
0x0501
```

They are currently exposed as:

```c
BDA_CMD_LBUTTON_DOWN_LIKE
BDA_CMD_LBUTTON_UP_LIKE
BDA_CMD_PEN_AREA_LIKE
```

## Key Leads

The system binaries contain diagnostic strings:

```text
MSG_KEYDOWN
SCANCODE_ESCAPE
The key is ENTER
The key is BACK
The key is SHIFT
The key is HOME
The key is UP
The key is LEFT
The key is RIGHT
The key is END
The key is DOWN
The key is INS
The key is DEL
```

This confirms both physical key and scancode handling are present. The next
step is a small hardware probe that displays `message/wparam/lparam` from a
custom window procedure.

## GUI Table Offsets Relevant To Events

Input-heavy apps frequently use these GUI offsets:

```text
+0x030
+0x03c
+0x040
+0x050
+0x054
+0x074
+0x084
+0x088
+0x08c
+0x0e0
+0x0e4
+0x0e8
+0x134
+0x17c
+0x1a4
+0x1a8
+0x1ac
+0x1b0
+0x1b4
+0x2fc
+0x308
+0x30c
+0x338
+0x33c
+0x35c
+0x368
+0x378
+0x40c
+0x418
+0x4f0
```

Known or likely roles so far:

```text
+0x040  send/set message or property
+0x1a4  create control/window
+0x2b8  message box
+0x338  set text/background mode-like
+0x33c  set text/foreground color-like
+0x378  RGB/color helper-like
```

The remaining offsets need callback-focused probes before getting stable SDK
names.
