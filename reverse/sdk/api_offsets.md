# BBK 9588 native BDA API offsets

These offsets are inferred from bundled native BDA call sites and system code.

## Runtime table pointers

```text
0x81c00004  GUI table pointer
0x81c00008  file-system table pointer
0x81c0000c  secondary/system/device table pointer
0x81c00010  memory/CRT table pointer
0x81c00014  resource/DLX table pointer
```

## Confirmed calls

```text
GUI +0x2b8  message box
  a0 = parent/window handle, often 0
  a1 = message/body string
  a2 = title string
  a3 = flags/button mode

GUI +0x1a4  create control/window-like call
  currently inferred args:
    a0 = class name, for example "edit", "medit", "EB_SCROLL"
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

GUI +0x1a8  destroy window/control-like call
  a0 = handle

GUI +0x03c  notify/post/send message-like call
GUI +0x040  send/set message/property-like call
  observed args:
    a0 = handle
    a1 = message/property id
    a2 = value/param
    a3 = value/param

GUI +0x074  pump/present/update-like call seen frequently in bundled games

GUI +0x0e0  object/window operation-like call seen in bundled games

GUI +0x2fc  draw/resource object create-or-fetch-like call seen in bundled games

GUI +0x35c  object/resource bind-like call seen in bundled games

GUI +0x3f8  framebuffer/region blit-like call seen in bundled games
GUI +0x400  alternate framebuffer/region blit-like call seen in bundled games
  observed full-screen args:
    a0 = x
    a1 = y
    a2 = 0xf0  (240)
    a3 = 0x140 (320)
    stack+0x10 = buffer pointer

GUI +0x378  RGB/color-create-like call
  observed args:
    a0 = drawing/window handle
    a1 = red
    a2 = green
    a3 = blue

GUI +0x40c  region draw/copy-like call seen in bundled games

GUI +0x414  render helper-like call seen in bundled games

GUI +0x418  render finish/helper-like call seen in bundled games

GUI +0x33c  set text/foreground color-like call
  observed args:
    a0 = drawing/window handle
    a1 = color returned by GUI +0x378 or another color helper

GUI +0x338  set text mode/background mode-like call
  observed args:
    a0 = drawing/window handle
    a1 = mode, often 1 before drawing text

GUI +0x368  put pixel/draw point-like call
  strongest evidence: 电子画板.bda calls it in rectangle/line loops
  observed args:
    a0 = surface/canvas handle
    a1 = x
    a2 = y
    a3 = RGB565 color, for example 0xf800 red
  wrapper:
    bda_gui_put_pixel_like(surface, x, y, rgb565)

GUI +0x4f0  draw text-like call
  observed args:
    a0 = drawing/window handle
    a1 = x
    a2 = y
    a3 = GBK/ASCII string
    stack+0x10 = extra/width/flags, often -1

GUI +0x670  BMP decode-like call observed in the bundled photo album app
  observed args:
    a0 = owner/window/image handle
    a1 = bda_picture_like_t output descriptor
    a2 = path string
    a3 = scratch/work pointer

GUI +0x808  JPEG decode-like call observed in the bundled photo album app
  observed args:
    a0 = owner/window/image handle
    a1 = bda_picture_like_t output descriptor
    a2 = path string
    a3 = mode byte, observed 0

GUI +0x5d4  draw/update packet-like call observed in GAMEBOY.BDA
  observed args:
    a0 = small caller-provided stack packet/buffer

GUI +0x6b0  large screen/frame-buffer allocation-like call observed in GAMEBOY.BDA

GUI +0x72c  state/query-like call observed in GAMEBOY.BDA

GUI +0x738  screen mode/size query-like call observed in GAMEBOY.BDA
  one branch compares the result with 0x131

GUI +0x750  event/key fetch-like call observed in GAMEBOY.BDA

GUI +0x6a8  file-selector/session open-like call observed in GAMEBOY.BDA
  observed args:
    a0 = 1

GUI +0x6c8  file-selector update/pump-like call observed in GAMEBOY.BDA
  observed args:
    a0 = selector descriptor pointer

GUI +0x6b8  file-selector selected-object/path fetch-like call observed in GAMEBOY.BDA

GUI +0x6bc  file-selector close/cancel/return-like call observed in GAMEBOY.BDA

The selector descriptor starts with:

```text
+0x00  output path/name buffer
+0x04  extension filter string, for example "gb;gbc"
+0x08  directory/current-state buffer
+0x0c  title string, for example "请选择游戏文件" in GBK
+0x10.. provisional state fields; GAMEBOY initializes several to 0 or -1
+0x40  observed as 0x1000 in a bundled selector/list descriptor
+0x48  observed as -1 in a bundled selector/list descriptor
+0x64  observed as 0 in a bundled selector/list descriptor
```

This is a high-level GUI/shell picker, not a file-system enumeration call. The
stable low-level listing interface is still the `FS +0x03c/+0x040/+0x044`
findfirst group.

MEM +0x008  allocate
MEM +0x00c  free

RES +0x090  get resource/picture state-like call observed in 我的相册.bda
  observed args:
    a0 = output buffer pointer
  caller reads output+0 as a handle/state value

RES +0x094  printf/trace-like helper in 元素周期表.bda.
            True-device RES094TraceProbe result:
            literal trace, gui=%x, fs=%x all returned 0 and the app continued.
            True-device RES094PathProbe result:
            "\\shell\\commonframe_A.dlx" and "\\shell\\MessageBoxBlue.dlx"
            also returned 0 and the app continued, with no visible load effect.
            This strongly supports "trace/log output" semantics.
            The previous DLX-loader name is misleading and should not be used for new code.

In `元素周期表.bda`, external DLX files are opened and parsed by app code using
FS calls. See `element_bda_notes.md`.
```

The provisional decoded-picture descriptor used by the album is:

```text
+0x00  RGB565 pixel pointer
+0x04  width/height-like dimension
+0x08  width/height-like dimension
+0x0c  stride/orientation-like auxiliary value
+0x10  mode byte
+0x11  mode byte
+0x14  owned rotated/copied RGB565 buffer, if allocated
+0x18  selected/index field, initialized to -1 by the album helper
```

See `picture_notes.md` for the `LoaderPicture` path and post-decode render
flow.

## File-system calls

The file-system table behaves mostly like a small C stdio/FAT wrapper. Bundled
apps pass string modes such as `rb` and `wb` to `FS +0x000`.

```text
FS +0x000  fopen-like
  a0 = path
  a1 = mode string, for example "rb" or "wb"
  returns file handle, 0/null on open failure

FS +0x004  fclose-like
  a0 = file handle

FS +0x008  fread-like
  a0 = buffer
  a1 = element size
  a2 = element count
  a3 = file handle

FS +0x00c  fwrite-like
  a0 = buffer
  a1 = element size
  a2 = element count
  a3 = file handle

FS +0x010  fseek-like
  a0 = file handle
  a1 = offset
  a2 = whence, where 0/1/2 match SET/CUR/END

FS +0x014  ftell-like
  a0 = file handle

FS +0x024  remove/unlink-like
  a0 = path

FS +0x02c  chdir/existing-directory check-like
  a0 = directory path
  observed failure value = -1

FS +0x030  mkdir-like
  a0 = directory path

FS +0x03c  findfirst/search-open-like
  a0 = path or pattern
  a1 = attribute/filter value
  a2 = caller-provided find-data buffer

FS +0x040  findnext-like
  a0 = find-data buffer

FS +0x044  findclose-like
  a0 = find-data buffer

FS +0x048  disk-info/free-space-like
  a0 = drive index, usually 0
  a1 = output buffer
  bundled apps multiply words at output+4, output+8, output+0xc

FS +0x06c  stat/access-like
  a0 = path
  a1 = flags, often 0
  a2 = optional output buffer in some call sites
  observed failure value = -1

FS +0x07c  storage-ready/media-present-like
  no arguments observed
```

The exact layout of the find-data and disk-info structs is still being mapped.
The `findfirst/findnext/findclose` group is the API to use for listing files.

## Experimental device/audio calls

`GAMEBOY.BDA` uses the secondary table heavily for audio streaming:

```text
0x004  close/release-like call, passed the handle/global at 0x81c2052c
+0x06c  audio/device open-like call
        observed args: a0=0x5622, a1=0x10, a2=1, a3=0x64
+0x074  ready/wait-like call before writing buffered samples
+0x078  write-like call
        observed args: a0=sample_buffer, a1=0x400 bytes
+0x08c  reset/init-like call before audio setup retry
+0x040  package sound id/channel operation-like call used by bundled games
+0x044  package sound state/query-like call used by bundled games
+0x050  package/chunk sound loader-like call used by bundled games
+0x054  package/chunk sound release-like call used by bundled games
+0x058  package sound operation-like call used by bundled games
+0x05c  package sound operation-like call used by bundled games
+0x060  package sound operation-like call used by bundled games
+0x064  package sound operation-like call used by bundled games
+0x068  package sound operation-like call used by bundled games
+0x09c  timer/rate-like call, passed computed frame/sample timing
+0x0a0  flush/drain-like call
```

These names are intentionally provisional. They are grounded in the Game Boy
emulator's sound path, not in system symbols.

## Experimental time/alarm calls

`时间.bda` mostly calls `SYS +0x080` with `0xc350`, which strongly suggests a
delay/sleep helper used during display refresh. `闹钟.bda` uses the neighboring
`SYS +0x0a8..0x0b8` group for alarm/time structures:

```text
SYS +0x080  delay/sleep-like
  observed args: a0 = 0xc350

SYS +0x0b8  time/RTC get-like
  a0 = output buffer
  observed caller reads bytes at buffer+0x11 and buffer+0x12 and word at
  buffer+0 after the call

SYS +0x0b0  alarm get-like
  a0 = output buffer
  a1 = alarm slot/index, observed 0, 1, and 2

SYS +0x0ac  alarm set-like
  a0 = input buffer
  a1 = alarm slot/index, observed 0, 1, and 2

SYS +0x0a8  alarm/time commit or refresh-like
  observed arg: a0 = 0
```

See `time_notes.md` and `reverse/examples/time_probe.c` for the current safe
read-only probe.

## SDK wrappers

`bda_sdk.h` currently exposes:

```text
bda_msgbox(title, message)
bda_msgbox_ex(parent, title, message, flags)
bda_alloc(size)
bda_free(ptr)
bda_gui_create_ex(class_name, caption, style, parent, x, y, width, height, id, extra)
bda_gui_create_window_like(class_name, caption, style, flags, id, x, y, width, height, parent, extra)
bda_gui_send(handle, message, a, b)
bda_gui_notify_like(handle, message, a, b)
bda_gui_destroy_like(handle)
bda_gui_pump_present_like()
bda_gui_draw_object_create_like(a0, a1, a2, a3)
bda_gui_object_bind_like(object, resource)
bda_gui_region_draw_like(a0, a1, a2, a3)
bda_gui_blit_like(x, y, height, width, buffer)
bda_gui_blit_alt_like(x, y, height, width, buffer)
bda_gui_screen_alloc_like(a0, a1, a2, a3)
bda_gui_state_query_like(a0)
bda_gui_screen_mode_query_like()
bda_gui_event_fetch_like(a0)
bda_gui_draw_packet_like(packet)
bda_gui_file_selector_open_like(mode)
bda_gui_file_selector_update_like(selector)
bda_gui_file_selector_get_like()
bda_gui_file_selector_close_like()
bda_file_selector_init_like(selector, out_path, extensions, dir_state, title)
bda_file_selector_load_default_skin_like()  /* deprecated misname; no confirmed skin load */
bda_gui_decode_bmp_like(owner, out, path, work)
bda_gui_decode_jpeg_like(owner, out, path, mode)
bda_gui_set_text_mode_like(handle, mode)
bda_gui_rgb_like(handle, r, g, b)
bda_gui_set_text_color_like(handle, color)
bda_gui_draw_text_like(handle, x, y, text, extra)
bda_gui_draw_vx_like(handle, x, y, width, height, vx_resource)
bda_gui_event_poll_global_like(message)
bda_res_entry_094_like(text_or_path, arg)
bda_res_trace_like(format, arg)
bda_load_dlx(path)  /* deprecated provisional alias for RES+0x094 */
bda_res_get_state_like(out_state)
bda_memcpy(dst, src, n)
bda_memset(dst, value, n)
bda_strlen(s)
BDA_LOWORD(x), BDA_HIWORD(x), BDA_MAKEWORD(lo, hi)
```

The file-system wrappers are intentionally named raw until the exact mode and
handle conventions are verified on hardware:

```text
bda_fs_open_raw(path, mode)
bda_fs_fopen_raw(path, mode)
bda_fs_close_raw(fd)
bda_fs_read_raw(fd, buffer, size)
bda_fs_fread_raw(buffer, size, count, file)
bda_fs_write_raw(file, buffer, size)
bda_fs_fwrite_raw(buffer, size, count, file)
bda_fs_seek_raw(file, offset, whence)
bda_fs_tell_raw(file)
bda_fs_remove_raw(path)
bda_fs_chdir_like(path)
bda_fs_mkdir_like(path)
bda_fs_findfirst_like(pattern, attr, find_data)
bda_fs_findnext_like(find_data)
bda_fs_findclose_like(find_data)
bda_fs_diskinfo_like(drive, info)
bda_fs_stat_like(path, flags, stat_data)
bda_fs_storage_ready_like()
```

The secondary/system table is exposed for controlled experiments:

```text
bda_sys_table()
bda_sys_audio_open_like(device, format, channels, buffer_hint)
bda_sys_audio_ready_like()
bda_sys_audio_write_like(buffer, bytes)
bda_sys_package_sound_load_like(descriptor)
bda_sys_package_sound_op58_like(a0, a1)
bda_sys_package_sound_op5c_like(a0)
bda_sys_package_sound_op60_like(a0)
bda_sys_package_sound_op64_like(a0)
bda_sys_package_sound_op68_like(a0)
bda_sys_delay_like(ticks_or_us)
bda_sys_timer_like(ticks)
bda_sys_time_get_like(time_data)
bda_sys_alarm_commit_like(index_or_flags)
bda_sys_alarm_set_like(alarm_data, index)
bda_sys_alarm_get_like(alarm_data, index)
```

## Input/event ABI

Bundled native apps suggest window procedures receive:

```text
a0 = hwnd
a1 = message id
a2 = wparam or packed data
a3 = lparam or extra data
```

Experimental message-like constants currently exposed by `bda_sdk.h`:

```text
BDA_MSG_CREATE        0x0010
BDA_MSG_TOUCH_A_LIKE  0x00b0
BDA_MSG_REDRAW_INPUT_LIKE 0x00b1
BDA_MSG_TOUCH_B_LIKE  0x00b1  /* deprecated misname */
BDA_MSG_COMMAND_LIKE  0x083e
BDA_MSG_KEYDOWN_LIKE  0x0844
BDA_MSG_FOCUS_LIKE    0x0841
BDA_MSG_INPUT_0842_LIKE 0x0842
```

See `input_notes.md` before treating these as stable names.

## Main function convention

The current builder patches the second startup `jal` target in a template BDA.
Your replacement routine should preserve callee-saved registers that it uses and
return with `jr $ra`.
