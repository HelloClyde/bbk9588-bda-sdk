# Bundled Game BDA Framework Notes

These notes summarize common patterns in bundled native games:

```text
Eros方块.bda
连连看.bda
黑白子.bda
九宫格.bda
雷霆战机.bda
决战坦克.bda
三国霸业.bda
```

Most of these share a common framework. Their startup code caches runtime API
tables in five adjacent globals, but the global addresses differ per BDA. Use:

```powershell
python reverse\bda_table_globals.py "应用\程序\Eros方块.bda"
python reverse\bda_table_call_scan.py "应用\程序\Eros方块.bda"
```

`bda_table_call_scan.py` now auto-detects these globals.

Per-BDA reports now available:

```text
reverse/reports/eros_bda_report.md
reverse/reports/linkgame_bda_report.md
reverse/reports/blackwhite_bda_report.md
reverse/reports/jiugongge_bda_report.md
reverse/reports/thunder_bda_report.md
reverse/reports/tank_bda_report.md
reverse/reports/sango_bda_report.md
```

The first two are the smallest confirmed examples of the shared framework.
`blackwhite_bda_report.md` and `jiugongge_bda_report.md` confirm the same shell
in more bundled puzzle games. `thunder_bda_report.md` and `tank_bda_report.md`
confirm the packed sound-effect package path. `sango_bda_report.md` is an
important counterexample: it has a `.lib` package but no SYS sound cluster.

## Common Table Order

The startup cache order is:

```text
RES
GUI
SYS
FS
MEM
```

Example, `Eros方块.bda`:

```text
RES  0x81c0b240
GUI  0x81c0b244
SYS  0x81c0b248
FS   0x81c0b24c
MEM  0x81c0b250
```

## Shared GUI Calls

Common high-frequency GUI offsets across these games:

```text
GUI +0x074  very frequent; likely pump/present/update/event-ish
GUI +0x0e0  frequent; called with handle/pointer plus two zero-ish args
GUI +0x2fc  creates or fetches a drawing/resource object
GUI +0x35c  object/bitmap select or bind-like call
GUI +0x40c  region draw/copy-like call
GUI +0x414  render helper, often called through t0
GUI +0x418  paired with +0x414 in drawing paths
GUI +0x3f8  region/frame blit-like call with 5 arguments
GUI +0x400  alternate blit-like call with same argument shape
```

`Eros方块.bda` and `连连看.bda` add concrete `GUI+0x414` evidence. Both call it
8 times with the same instruction structure:

```text
a0 = surface/object
a1 = x/source-x-like
a2 = y/source-y-like
a3 = width/height/index-like
stack+0x10..0x24 = extra rectangle/color/resource fields
```

They also call `GUI+0x418` with larger stack argument blocks. Some call sites
pass screen constants `0x140` and `0xf0`, matching 320x240. Treat
`GUI+0x414/+0x418` as part of the region/render family alongside the paint and
album evidence.

The strongest framebuffer lead is `GUI+0x3f8/+0x400`. `雷霆战机.bda` and
`决战坦克.bda` call these with screen-sized constants:

```text
a0 = x
a1 = y
a2 = 0xf0  (240)
a3 = 0x140 (320)
stack+0x10 = buffer pointer
```

This suggests a call shape like:

```c
gui_blit_like(x, y, height, width, buffer);
```

The exact pixel format still needs a hardware probe. Given the icon format and
other code, RGB565 is a strong first candidate.

`bda_sdk.h` exposes provisional wrappers:

```c
bda_gui_pump_present_like();                              /* GUI +0x074 */
bda_gui_draw_object_create_like(a0, a1, a2, a3);          /* GUI +0x2fc */
bda_gui_object_bind_like(object, resource);               /* GUI +0x35c */
bda_gui_region_draw_like(a0, a1, a2, a3);                 /* GUI +0x40c */
bda_gui_blit_like(x, y, height, width, buffer);      /* GUI +0x3f8 */
bda_gui_blit_alt_like(x, y, height, width, buffer);  /* GUI +0x400 */
```

## Game Resource Packages

Small games such as `Eros方块.bda` and `连连看.bda` do not reference external
DLX packages. They embed the same four VX images directly in the BDA resource
area:

```text
0x000088  80x80
0x0032a0  80x80
0x0064b8  54x54
0x007b98  58x58
```

They both reference a shared `\SysPet.yzj` file plus an app-specific save file:

```text
\ErosData.dat
\LLKData.dat
\BlackData.dat
\SdData.dat
\GamSdSave.Sav
\Flydata.dat
\GamFlyInfo.Sav
\TankData.dat
\maptank\map*.map
\sango.lib
```

Both contain fixed-size `0x44` byte record copy/read/write loops, likely
save/high-score records.

`blackwhite_bda_report.md` adds one game-specific embedded VX resource at
`0x194e4` with dimensions 240x95. `thunder_bda_report.md`,
`tank_bda_report.md`, and `sango_bda_report.md` confirm the same four common
shell VX resources.

Several games use external package files:

```text
雷霆战机.bda   A:\...\FlySound.lib
决战坦克.bda   A:\...\TankSound.lib
三国霸业.bda   a:\...\sango.lib
```

The package loader pattern commonly reads a small header, checks sums, allocates
memory, then stores a list of chunk descriptors. `雷霆战机.bda` has code that
iterates up to 0x14 chunks and calls `SYS+0x50` after filling descriptors.

These `.lib` files are not standard host libraries. They appear to be game data
or sound/resource packages consumed by the game's BDA framework.

## Sound Leads

`雷霆战机.bda` and `决战坦克.bda` use additional SYS table offsets:

```text
SYS +0x040
SYS +0x044
SYS +0x050
SYS +0x054
SYS +0x058
SYS +0x05c
SYS +0x060
SYS +0x064
SYS +0x068
SYS +0x08c
```

The flow around `雷霆战机.bda` `0x81c11188` and `决战坦克.bda` `0x81c04548`
builds package chunk descriptors and calls `SYS+0x50`. Later paths call
`SYS+0x58/+0x5c/+0x60/+0x64/+0x68` for playback/teardown style operations.

This is distinct from `GAMEBOY.BDA`'s raw PCM-ish `SYS+0x74/+0x78` stream path.
For games, the system may provide a higher-level packed sound effect helper.
`bda_sdk.h` exposes these as `bda_sys_package_sound_*_like()` wrappers, but the
descriptor layout still needs hardware probes.

Additional `thunder_bda_report.md` details:

```text
\FlySound.lib
\TankSound.lib
gFly_soundState = %d
descriptor stride 0x20
loop bound 0x14 chunks
SYS+0x044 stores a byte later reused by SYS+0x040
SYS+0x040 receives either that byte or a computed small sound id
SYS+0x064 and SYS+0x068 are repeatedly paired
```

`tank_bda_report.md` confirms the same details independently:

```text
SYS+0x050 at 0x81c04548
SYS+0x054 at 0x81c04b98
descriptor stride 0x20
loop bound 0x14 chunks
SYS+0x044 stores a byte at 0x81c1288c
SYS+0x040 receives that byte or 0x75 - (index * 13)
```

Do not generalize this to every `.lib` game package. `sango_bda_report.md`
references `\sango.lib` but has no `SYS+0x040..0x068` calls; it parses package
data through FS/MEM code instead.

## GBA Implication

These games are more useful than `GAMEBOY.BDA` for display. They show a compact
way to blit 320x240 buffers or regions through the GUI table. Combined with
`GAMEBOY.BDA`'s raw audio stream path, the remaining SDK gaps for emulator work
are now mostly:

```text
1. confirm RGB565 framebuffer format for GUI+0x3f8/+0x400
2. confirm which of +0x3f8/+0x400 presents vs clears/fallbacks
3. pin stable key/touch input polling or window message delivery
4. decide whether to use raw PCM path or game sound package path
```
