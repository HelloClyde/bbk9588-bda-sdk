# Media and Picture API Notes

These notes are inferred from bundled native BDA files. Treat them as a map for
hardware experiments, not as final API names yet.

## Audio

`应用\程序\飞天音乐.bda` contains a native MP3/WAV/WMA player UI.

Relevant strings:

```text
mp3;wav;wma;blm
\shell\mp3_liba.dlx
\shell\mp3_libc.dlx
\shell\mp3_libb.dlx
\shell\mp3_lyric_help.dlx
KEYDOWN PLAY_STOP
KEYDOWN PLAY_PAUSE
KEYDOWN PLAY_PLAY
```

Hot indirect call offsets in this app:

```text
RES +0x094  trace/log-like, heavily used by this app
GUI +0x040  send/message-like
SYS +0x004, +0x020  repeated media-player backend pair
SYS +0x02c, +0x034, +0x038, +0x094  media-player backend candidates
GUI +0x4f0, +0x378, +0x2fc, +0x338, +0x308, +0x30c, +0x33c  UI/text helpers
```

See `reverse/reports/music_bda_report.md`. Important correction: hardware
`RES094TraceProbe` and `RES094PathProbe` show `RES+0x094` is not a DLX loader.
The high count in `飞天音乐.bda` is more likely debug/trace logging.

`应用\程序\数码录音.bda` contains recorder/player behavior.

Relevant strings:

```text
*.wav
\shell\record_A.dlx
\shell\record_B.dlx
recorder
Rec%5.5d.wav
```

See `reverse/reports/recorder_bda_report.md`. The recorder shares the same
early SYS media-backend cluster seen in the music player:

```text
SYS +0x004  28 calls
SYS +0x020  25 calls
SYS +0x02c  13 calls
```

This is stronger evidence that the `SYS +0x004/+0x020/+0x02c` group is a
high-level audio/media backend used by player/recorder apps. Keep it separate
from the raw audio streaming path used by `GAMEBOY.BDA`.

Bundled games provide a third audio path: packed sound-effect packages. Current
evidence comes from `reverse/reports/thunder_bda_report.md`. `闆烽渾鎴樻満.bda`
opens `\FlySound.lib`, builds `0x20`-byte chunk descriptors, and uses:

```text
SYS +0x040/+0x044/+0x050/+0x054/+0x058/+0x05c/+0x060/+0x064/+0x068/+0x08c
```

This is distinct from both the music/recorder high-level media backend and
`GAMEBOY.BDA`'s raw sample stream. Treat these as packed game sound-effect
helpers until hardware probes pin the descriptor layout.

Update from `reverse/reports/tank_bda_report.md`:

```text
\TankSound.lib
SYS+0x050 at 0x81c04548
SYS+0x054 at 0x81c04b98
descriptor stride 0x20
loop bound 0x14 chunks
SYS+0x044 stores a byte at 0x81c1288c
SYS+0x040 receives that byte or 0x75 - (index * 13)
```

So the packed sound-effect cluster is now cross-checked by both Thunder and
Tank. `reverse/reports/sango_bda_report.md` is the counterexample:
`三国霸业.bda` references `\sango.lib`, but it does not use
`SYS+0x040..0x068`; that `.lib` is app-owned package data loaded through FS/MEM
code.

## Video

`应用\程序\飞天影音_.bda` embeds an MPlayer/FFmpeg-style player. It references:

```text
avi;mp4;3gp
\player.bin
\player.cfg
Starting playback...
Open stream, file name:%s
MPlayer  (C) 2000-2005 MPlayer Team
```

This looks more like a large bundled player runtime than a tiny system API.
The practical SDK path may be launching or reusing `player.bin`/config rather
than calling one small `play_video()` function.

See `reverse/reports/video_bda_report.md` for the current per-BDA comparison
between the two bundled video apps. Both variants reference `\player.bin` and
`\player.cfg`, and both have very large unknown indirect-call clusters. Treat
those clusters as probable private player/codec function tables until a call is
cross-checked against other apps or `C200.bin`; do not promote them into public
SDK wrappers just because the offset is hot in the video app.

## Pictures

`应用\程序\我的相册.bda` references:

```text
LoaderPicture
LoaderPicture FileName = %s
*.bmp
*.jpg
bmp;jpg
```

`应用\程序\电子画板.bda` also saves or loads:

```text
.jpg
.bmp
bmp;jpg
```

Picture-heavy apps commonly use GUI/table offsets:

```text
+0x35c, +0x368, +0x40c, +0x410, +0x418, +0x46c, +0x4f0
```

`电子图书.bda` calls `+0x46c` with pointer-like arguments in image/resource
flow; this offset is a good candidate for a picture/resource drawing helper,
but the exact signature still needs hardware tests. See
`reverse/reports/ebook_bda_report.md` for concrete call contexts where `a1/a2`
are loaded from adjacent resource-record words before `GUI+0x46c`.

See `reverse/reports/album_bda_report.md` and `reverse/sdk/picture_notes.md`
for the stronger Album-specific picture pipeline evidence.

## SDK Experiment Helpers

`bda_sdk.h` exposes generic table calls:

```c
bda_call0(table, offset);
bda_call1(table, offset, a0);
bda_call2(table, offset, a0, a1);
bda_call3(table, offset, a0, a1, a2);
bda_call4(table, offset, a0, a1, a2, a3);
```

Historical note: the helpers below call `RES+0x094`. Later analysis of
`元素周期表.bda` shows that this offset is used with printf-style trace strings.
The `load_dlx` names are therefore an early unconfirmed interpretation, not a
confirmed generic DLX loader. See `element_bda_notes.md`.

True-device `RES094TraceProbe.bda` result:

```
literal=00000000
gui_fmt=00000000
fs_fmt=00000000
res_tbl=80253E60
```

The app continued normally after all three calls, which strongly supports
trace/log semantics for `RES+0x094`. Do not use the historical `bda_load_dlx_*`
aliases for new code.

True-device `RES094PathProbe.bda` then passed two DLX path-looking strings:

```
res=80253E60
gui=80253F90
path0=00000000
path1=00000000
```

Those calls also returned normally with `0` and had no visible loading behavior.
This closes the earlier "maybe path strings dispatch to resource loading" theory
for this entry.

```c
bda_res_entry_094_like(text_or_path, arg);
bda_res_trace_like(format, arg);
bda_load_dlx_ex(path, arg);
bda_load_dlx(path);      /* arg = 0x81c00000 */
bda_load_dlx_gui(path);  /* arg = GUI table */
bda_load_dlx_fs(path);   /* arg = FS table */
bda_load_dlx_mem(path);  /* arg = MEM table */
bda_load_dlx_res(path);  /* arg = RES table */
```
