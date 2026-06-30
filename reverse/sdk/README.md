# Native BDA C SDK

This SDK is for BBK 9588 native `*.bda` apps.

## Entry Point

Define a freestanding C function named `bda_main`:

```c
#include "../sdk/bda_sdk.h"

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_msgbox("BDA SDK", "hello");
    return 0;
}
```

Template-based build, still useful when borrowing an original app lifecycle:

```powershell
python reverse\bda_compile_c.py reverse\examples\hello_msgbox.c `
  --template build\calc_startup_msgbox_origtitle.bda `
  --title MyApp `
  --category 0x0d `
  --icon-png build\custom_H_icon.png `
  -o build\MyApp.bda
```

No-template C build, confirmed on hardware for simple msgbox apps:

```powershell
python reverse\bda_compile_c.py reverse\examples\hello_msgbox.c `
  --no-template `
  --title MyApp `
  --category 9 `
  --icon-png build\custom_H_icon.png `
  --icon-background 14245c `
  -o build\MyApp.bda
```

No-template assembly build:

```powershell
python reverse\bda_pack_minimal.py reverse\examples\hello_msgbox.s `
  --title NoTplAsm `
  --category 9 `
  -o build\NoTemplateHelloAsm.bda
```

This creates the BDA header, four VX icon chunks, and native entry code from
scratch instead of copying an existing app container. Hardware confirmed both
`NoTemplateHelloAsm.bda` and `NoTemplateHelloC.bda` appear in the menu and run.
`--icon-png` generates all four menu icon sizes directly into the no-template
container.

Hardware also confirmed `build\NoTplDemo.bda`, built from
`reverse\examples\notpl_demo_msgbox.c` with `--no-template --icon-png`, appears
in the menu and runs.

## Current Wrappers

Confirmed or low-risk wrappers:

```c
int bda_msgbox(const char *title, const char *message);
int bda_msgbox_ex(void *parent, const char *title, const char *message, u32 flags);
void *bda_alloc(bda_size_t size);
void bda_free(void *ptr);
void *bda_memcpy(void *dst, const void *src, bda_size_t n);
void *bda_memset(void *dst, int value, bda_size_t n);
bda_size_t bda_strlen(const char *s);
```

Experimental wrappers inferred from bundled app call sites:

```c
bda_handle_t bda_gui_create_ex(
    const char *class_name,
    const char *caption,
    u32 style,
    bda_handle_t parent,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    u32 id,
    u32 extra
);

int bda_gui_send(bda_handle_t handle, u32 message, u32 a, u32 b);
int bda_gui_notify_like(bda_handle_t handle, u32 message, u32 a, u32 b);
int bda_gui_destroy_like(bda_handle_t handle);
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
int bda_gui_blit_like(s32 x, s32 y, s32 height, s32 width, const void *buffer);
int bda_gui_blit_alt_like(s32 x, s32 y, s32 height, s32 width, const void *buffer);
int bda_gui_set_text_mode_like(bda_handle_t handle, u32 mode);
int bda_gui_rgb_like(bda_handle_t handle, u32 r, u32 g, u32 b);
int bda_gui_set_text_color_like(bda_handle_t handle, u32 color);
int bda_gui_put_pixel_like(bda_handle_t surface, s32 x, s32 y, u16 rgb565);
int bda_gui_draw_text_like(bda_handle_t handle, s32 x, s32 y, const char *text, s32 extra);
int bda_gui_draw_vx_like(bda_handle_t handle, s32 x, s32 y, s32 width, s32 height, const void *vx_resource);
int bda_gui_event_poll_global_like(void *message);

int bda_res_entry_094_like(const char *text_or_path, void *arg);
int bda_res_trace_like(const char *format, void *arg);
/* Deprecated historical names; RES+0x094 tested as trace/log-like, not DLX load. */
int bda_load_dlx_ex(const char *path, void *arg);
int bda_load_dlx(const char *path);
int bda_load_dlx_gui(const char *path);
int bda_load_dlx_fs(const char *path);
int bda_load_dlx_mem(const char *path);
int bda_load_dlx_res(const char *path);

int bda_fs_fopen_raw(const char *path, const char *mode);
int bda_fs_open_raw(const char *path, u32 mode);
int bda_fs_close_raw(int file);
int bda_fs_fread_raw(void *buffer, bda_size_t size, bda_size_t count, int file);
int bda_fs_read_raw(int file, void *buffer, bda_size_t size);
int bda_fs_fwrite_raw(const void *buffer, bda_size_t size, bda_size_t count, int file);
int bda_fs_write_raw(int file, const void *buffer, bda_size_t size);
int bda_fs_seek_raw(int file, s32 offset, int whence);
int bda_fs_tell_raw(int file);
int bda_fs_remove_raw(const char *path);
int bda_fs_chdir_like(const char *path);
int bda_fs_mkdir_like(const char *path);
int bda_fs_findfirst_like(const char *pattern, u32 attr, void *find_data);
int bda_fs_findnext_like(void *find_data);
int bda_fs_findclose_like(void *find_data);
int bda_fs_diskinfo_like(u32 drive, void *info);
int bda_fs_stat_like(const char *path, u32 flags, void *stat_data);
int bda_fs_storage_ready_like(void);

void *bda_sys_table(void);
int bda_sys_audio_open_like(u32 device, u32 format, u32 channels, u32 buffer_hint);
int bda_sys_audio_ready_like(void);
int bda_sys_audio_write_like(const void *buffer, bda_size_t bytes);
int bda_sys_delay_like(u32 ticks_or_us);
int bda_sys_timer_like(u32 ticks);
int bda_sys_time_get_like(void *time_data);
int bda_sys_alarm_commit_like(u32 index_or_flags);
int bda_sys_alarm_set_like(void *alarm_data, u32 index);
int bda_sys_alarm_get_like(void *alarm_data, u32 index);
```

Generic experimental table calls are available for probing unknown API offsets:

```c
int bda_call0(void *table, u32 offset);
int bda_call1(void *table, u32 offset, u32 a0);
int bda_call2(void *table, u32 offset, u32 a0, u32 a1);
int bda_call3(void *table, u32 offset, u32 a0, u32 a1, u32 a2);
int bda_call4(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3);
int bda_call5(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3, u32 a4);
int bda_call6(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3, u32 a4, u32 a5);
```

The raw file wrappers intentionally keep conservative names until struct layouts
and return-value details are verified on hardware. `findfirst/findnext/findclose`
are the current path for listing files.

Input/event helpers:

```c
typedef int (*bda_wndproc_t)(bda_handle_t hwnd, u32 message, u32 wparam, u32 lparam);
BDA_LOWORD(x);
BDA_HIWORD(x);
BDA_MAKEWORD(lo, hi);
```

See `fs_notes.md` for directory listing and disk-status notes, `window_notes.md`
for window/control creation notes, `text_notes.md` for text rendering notes,
`time_notes.md` for clock/alarm leads, `input_notes.md` for touch/key leads,
`media_notes.md` for current audio, video, and picture leads, `paint_notes.md`
for canvas/pixel drawing leads, `dlx_notes.md`
for DLX resource container notes, `bbvm_notes.md` for BB virtual machine wrapper
clues, `gameboy_notes.md` for emulator-specific reverse engineering notes, and
`game_framework_notes.md` for bundled game display/sound patterns.
