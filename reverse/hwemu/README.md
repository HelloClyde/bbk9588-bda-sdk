# BBK 9588 Hardware Emulator

This directory tracks the hardware-level emulator path for the BBK 9588 system
image. It is separate from the native BDA SDK/API shim work: this harness runs
the real boot/system images and models hardware as the firmware demands it.

## Goal

Boot and execute the real low-level images:

- `系统/数据/u_boot_9588_4740.bin`
- `系统/数据/C200.bin`
- later, packed/encrypted images such as `kj409588.bin` and `C200knl.bin`

The practical milestone is a deterministic CPU/MMIO trace that reaches the next
missing JZ4740/BBK peripheral or emulator-core issue, records it, and lets us
implement the model incrementally.

## Current Milestone

The emulator can now cold-boot the real `C200.bin` from `0x80004000` with the
combined raw NAND image, pass the two observed touchscreen calibration points,
close the time-change dialog through the modeled touch controller, and reach the
visible 240x320 portrait main menu.

The current passing cold-boot regression is:

```powershell
python .\reverse\hwemu\run_cold_boot_to_menu_smoke.py `
  --prefix hwemu_cold_boot_to_menu_check3 `
  --timeout 210 `
  --boot-max-seconds 120 `
  --dialog-max-seconds 80
```

The current menu interaction smoke starts from a main-menu checkpoint, sends a
hardware-controller touch at `(210,287)` to the bottom `工具` tab, releases it,
and verifies the IRQ, GUI dispatch, scheduler, task-switch, and framebuffer
state:

```powershell
python .\reverse\hwemu\run_system_menu_smoke.py `
  --state-in .\build\hwemu_cold_boot_to_menu_check3_menu.pkl `
  --no-block-image `
  --nand-image .\build\bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin `
  --prefix hwemu_menu_click_tools_from_coldboot
```

This is not yet a final minimal-hook emulator. The main remaining areas are the
FTL/NAND write model, scheduler/timer/interrupt fidelity, and replacing broad
diagnostic PC accelerators with either device behavior or documented equivalent
loop/function accelerators.

## Current Hardware Assumptions

Evidence from the supplied files:

- Main SoC is Ingenic/JzSOC, likely JZ4740.
- CPU is MIPS32 little-endian, XBurst generation.
- `u_boot_9588_4740.bin` is raw MIPS linked at `0x80900000`.
- `C200.bin` is raw MIPS and is usable as the second-stage payload at
  `0x80004000`.
- Offline C200 disassembly should use `0x80004000` as the file load base for
  this emulator path. Using `0x80000000` shifts every target by `0x4000` and
  produces plausible-looking but wrong function bodies.
- Known boot strings include LCD, NAND, keyboard, touchscreen, I2S, USB disk,
  SDRAM and production diagnostics.

## Usage

Install Unicorn if needed:

```powershell
python -m pip install unicorn capstone
```

Run the local interactive frontend:

```powershell
python .\reverse\hwemu\hwemu_frontend.py --host 127.0.0.1 --port 9588
```

Then open `http://127.0.0.1:9588/`. The frontend keeps one emulator instance
alive, displays the current 240x320 RGB565 framebuffer, and exposes coarse
step/run, key, and touch controls. The boot and continuous-run buttons use a
background worker so the browser can keep polling status and refreshing the
framebuffer while the CPU is running. Current input injection is still based on
the observed C200 idle-loop sampler hooks, so it is useful for UI experiments
but not yet a complete interrupt/timer model.

Useful frontend endpoints while debugging:

- `POST /api/run-start?name=boot&steps=30000000&chunk=100000`
- `POST /api/run-start?name=continuous&steps=0&chunk=100000`
- `POST /api/stop`
- `POST /api/step?steps=250000`
- `GET /screen.png`

Run the current U-Boot + C200 path:

```powershell
python .\reverse\hwemu\bbk9588_hwemu.py `
  --image .\系统\数据\u_boot_9588_4740.bin `
  --base 0x80900000 `
  --pc 0x80900000 `
  --ram-mb 160 `
  --profile bbk9588-uboot `
  --payload .\系统\数据\C200.bin `
  --payload-addr 0x80004000 `
  --steps 30000000 `
  --trace-limit 7500 `
  --json-out .\build\hwemu_payload_c200_idle.json
```

Run and dump the currently modeled framebuffer:

```powershell
python .\reverse\hwemu\bbk9588_hwemu.py `
  --image .\系统\数据\u_boot_9588_4740.bin `
  --base 0x80900000 `
  --pc 0x80900000 `
  --ram-mb 160 `
  --profile bbk9588-uboot `
  --payload .\系统\数据\C200.bin `
  --payload-addr 0x80004000 `
  --steps 30000000 `
  --trace-limit 1000 `
  --idle-stop-hits 256 `
  --fb-dump .\build\c200_idle_fb.png `
  --fb-format rgb565 `
  --fb-orientation rot180 `
  --json-out .\build\hwemu_payload_c200_idle_fb.json
```

Without a raw NAND dump, the emulator preloads `C200.bin` as a second-stage
payload. That is deliberate: the U-Boot NAND model can identify/read status, but
it cannot reconstruct missing page contents from erased flash.

Build a host FAT16 image from the copied filesystem tree:

```powershell
python .\reverse\hwemu\make_fat16_image.py `
  --output .\build\bbk9588_fs_fat16.img `
  .\系统 .\应用
```

The generated image has a simple MBR and places the FAT16 volume at LBA `0x20`.
This matches the firmware's mount probe: `0x80179998` reads sector `0x20` and
checks for the FAT boot jump byte plus the `55 aa` sector signature.

Probe the C200 logical block read hook with that image:

```powershell
python .\reverse\hwemu\bbk9588_hwemu.py `
  --image .\系统\数据\u_boot_9588_4740.bin `
  --base 0x80900000 `
  --pc 0x80900000 `
  --ram-mb 160 `
  --profile bbk9588-uboot `
  --payload .\系统\数据\C200.bin `
  --payload-addr 0x80004000 `
  --nand-image .\系统\数据\C200.bin `
  --block-image .\build\bbk9588_fs_fat16.img `
  --steps 20000000 `
  --json-out .\build\hwemu_fat16_probe.json
```

## Current Trace Status

The current profile executes through:

- U-Boot early cache/stack/GPIO/serial setup.
- NAND READ ID with ID bytes `ec da 10 95 44`.
- NAND ready and BCH status polling.
- C200 entry at `0x80004000`.
- C200 clock/GPIO/UART setup.
- LCD command/status polling.
- LCD framebuffer/global initialization.
- Keyboard/interrupt setup around `0x800176c8`.
- Graphics/blit engine wait at `0xb0021004`.
- Higher-level UI/resource initialization paths around `0x8018fb50`,
  `0x800a7c18`, `0x801801c8`, `0x80014240`, and `0x800a8810`.
- Main idle/scheduler loop at `0x80008a58..0x80008a8c`.

Latest useful trace:

- `build/hwemu_payload_c200_idle.json`
- stops with `stop_reason = idle_loop`
- idle loop is detected after 256 hits at `0x80008a84`
- instruction count to idle loop is about `12,005,629`
- framebuffer dump `build/c200_idle_fb.png` is not empty:
  `22,492` nonzero pixels, `761` unique RGB565 values
- the confirmed visible screen size is portrait `240x320`; earlier `512x400`
  dumps were internal/provisional surface interpretation, and `320x240` was a
  landscape/game-buffer assumption rather than the real panel direction
- current portrait dump needs a `rot180` display transform; with that transform,
  `build/c200_idle_fb_240x320.png` shows recognizable boot logo content and
  reaches the same idle loop
- `--idle-stop-hits` controls idle-loop stopping; `0` disables this stop, which
  is useful for future timer/key/touch event injection
- `--watch-input-state` traces the currently observed GUI/input state block at
  `0x80473f40..0x80473fbf`
- `--watch-input-nodes` traces the observed GUI/input node pool around
  `0x806c5000`
- `--poke-va addr:size:value@idle_hit` can modify RAM at a selected idle-loop
  hit; this is the current low-level mechanism for event injection experiments
- `--call-va addr[:a0[:a1[:a2[:a3]]]][@idle_hit]` is available as an
  experimental firmware-call probe, but direct asynchronous calls into
  `0x800089b8` are not stable yet
- `--fw-key-sample code@idle_hit` runs C200's own key sampler wrapper
  `0x8005ce48` at an idle-loop hit and forces the next `0x8001b464` scanner
  result. Repeat it with code `0` to model release, for example:
  `--fw-key-sample 7@2 --fw-key-sample 0@4`.
- `--gpio-level addr:value` forces a physical MMIO register read value.
- `--gpio-pulse addr:value@idle_hit[:reads]` forces a physical MMIO register
  read value for a limited number of reads after a selected idle-loop hit.
  Example: `--gpio-pulse 0x10010100:0x40000@2:1`.
- `--key-pulse code@idle_hit[:reads]` injects one of the currently known
  active-low key scanner codes. Confirmed scanner codes are `4`, `5`, `6`,
  `7`, `9`, and `10`.
- `--trace-pc addr` records hit counts and register snapshots for selected
  virtual PCs. This is useful for checking whether a firmware service path is
  reached without relying on the rolling `last_calls` buffer. The snapshot
  includes `$t9`, which is important for native BDA `jalr $t9` API calls.
- `--nand-image path` enables the newer NAND page-read model. Without this
  option the emulator intentionally keeps the legacy erased-NAND behavior that
  reaches the C200 idle loop.
- `--block-image path` serves a logical block-device image through C200's
  `0x80182a90(dest, lba, sector_count)` sector-read path,
  `0x80182bf4(dest, offset, length)` byte-read path, and `0x80182d58()` size
  path. This is separate from raw NAND page modeling and is intended for
  host-built FAT16 filesystem images. It is a temporary firmware-function hook;
  prefer `--no-block-image` with a combined NAND image when testing the
  hardware-level storage path.
- `reverse/hwemu/make_combined_nand.py` builds a raw NAND image that keeps the
  bootable C200 pages and places the FAT image into the NAND page range used by
  C200's FTL cache path. Current verified layout:
  `--fat-page-base 0x1c40`, where logical sector `n` is read from NAND page
  `0x1c40 + n // 4`.
- `reverse/hwemu/stamp_ftl_oob.py` stamps the minimal C200 FTL spare/OOB tags
  needed by the cold raw-NAND path. C200's FTL rebuild scans block first-page
  spare data, reads `spare[-6]` as the generation counter, and reads
  `spare[-4]` as a 32-bit mapping word whose low 16 bits are the logical block
  id. The current diagnostic image is
  `build/bbk9588_nand_c200_fat_page1c40_gbkshort_usbfix_ftloob.bin`; it maps
  logical blocks `0..0x7ff` onto physical blocks starting at page `0x1c40`.
- `reverse/hwemu/inspect_combined_nand_fat.py` inspects that embedded FAT
  without running Unicorn. Use it first when runtime reports imply missing UI
  resources. The current `gbkshort_usbfix` combined NAND has verified entries
  for `系统\Desktop\c200dts1a.dlx`, `系统\Desktop\USB.bmp`,
  `应用\数据\shell\text_A.dlx`, and `应用\数据\shell\Element.dlx`.
- `--no-block-image` disables the logical block hook. With
  `build/bbk9588_nand_c200_fat_page1c40.bin`, C200 reads FAT sectors through
  the lower NAND path (`0x80183d04` / `0xb800` / `0xb801` / `0xb301`) rather
  than through `0x80182a90` short-circuiting.
- Historical raw NAND limitation: older experimental runs used
  `--readonly-nand-page-range` and `--clear-nand-overrides-page-range` to
  protect the injected FAT range from provisional FTL/cache writes. The current
  cold-boot-to-menu check3 artifacts show `erase_count = 0`,
  `recent_program_writes = []`, and `page_override_count = 0`, so the cold boot
  smoke no longer uses that guard. A real FTL write/cache model is still needed
  for later workflows that actually modify NAND.
- USB/resource note: C200 can send event `0x60` to the desktop handler during
  GUI startup. That handler tries to open `A:\...\Desktop\USB.bmp` before
  drawing the USB connection screen. The current exported file tree does not
  contain `USB.bmp`; it does contain `...\shell\usb.dlx` with two 240x320 VX
  images. `build/bbk9588_nand_c200_fat_page1c40_usbfix.bin` is a diagnostic
  image rebuilt after generating `Desktop\USB.bmp` from the first `usb.dlx`
  VX resource. Treat this as a filesystem-data completion test, not as proof
  that the final storage model is correct.
- UDC is modeled as disconnected by default. Use `--usb-connected` only for
  explicit USB-plug experiments. This prevents normal UDC configuration writes
  from being read back as cable/status/interrupt state.
- `--nand-loop-accelerator` is an optional diagnostic speedup for long raw-NAND
  runs. It folds the known C200 `lbu 0xb8000000; sb ...` NAND data-port copy
  loops into equivalent bulk data-port reads, including the FTL rebuild loops
  around `0x80183e0c`, `0x80183fa4`, `0x80184140`, `0x801841bc`,
  `0x801843d8`, and `0x80184530`. It is disabled by default because it is
  still a PC-level accelerator, not part of the final minimal-hook target.
  The accelerator uses the same data-window helpers as scalar MMIO reads and
  therefore advances `nand_read_index`, `data_window_read_count`, and program
  buffers. Recent loop events record mode, PC, destination/source, page/column,
  read index, and preview bytes. `build/hwemu_nand_loop_event_probe.json`
  verifies the current cold-start read path with `invalid = 0`, `1965`
  accelerated loops, and no program-buffer growth.
- `--resource-cache16-accelerator` models the hot `0x8017ca10` 16-bit
  FAT/resource sector-cache lookup. It now checks the firmware's eight cache
  slots first; on a clean miss it loads the backing sector into the selected
  lowest-hit cache buffer, updates the sector/hit/dirty fields, and returns the
  requested halfword. Dirty misses are left to the firmware path until writeback
  is modeled. This remains a PC-level accelerator, but it preserves the cache
  table side effects observed by later firmware code.
- Current fast-hook boundary for the raw-system menu path:
  `0x8012c3d0` / `0x8012c1bc` bulk-copy surface rectangles using the same
  source/destination buffers as the firmware surface vtable; `0x80006658`
  accelerates the allocator's linear free-block lookup and resumes at the
  original hit/miss branch. These are narrow equivalent loop/function
  accelerators. The remaining non-equivalent areas to reduce are the
  logical-block filesystem hook and the CP0 WAIT/interrupt return model. The
  raw-system menu interaction regression no longer requires
  `--scheduler-tick-clamp` or `--resource-cache16-accelerator`.
- `--launch-bda path[@idle_hit]` directly loads a native BDA tail at
  `0x81c00020`, copies the runtime table from `0x80281680` to `0x81c00000`,
  seeds the app display callback context normally prepared by `0x8012d20c`,
  and jumps to the BDA entry. Current legacy regression:
  `build/hwemu_launch_element_appidle_fb.json`, launching
  `应用\程序\元素周期表.bda@2`, reaches `0x81c00020`, passes the display
  callback dereference at `0x800d6a30`, and stops at the observed application
  repaint loop with `stop_reason = app_repaint_loop`.
- `--app-idle-stop-hits n` stops after `n` hits of the observed application
  repaint loop at `0x800bd840`. This is separate from `--idle-stop-hits` so
  existing system-idle scheduling remains unchanged.
- `--preset direct-bda-msgbox` applies the current direct-BDA smoke settings:
  U-Boot at `0x80900000`, C200 payload at `0x80004000`, 160 MB RAM, FAT16
  block image, direct BDA launch at idle hit 2, the common msgbox trace PCs,
  and a 240x320 framebuffer dump. Use `--out-prefix .\build\name` to set both
  `.\build\name.json` and `.\build\name.png`. In native text mode the preset
  now selects `rows-lsb-vscale2` and `hflip` unless those options are explicitly
  overridden.
- `--quiet` suppresses the full JSON report on stdout and prints a one-line
  summary while still writing `--json-out` / `--out-prefix` files.
- `--bda-text-mode native|ascii-hook` controls direct-BDA text rendering.
  `ascii-hook` is the temporary visible 5x7 ASCII renderer used for smoke
  tests. `native` disables it and leaves the firmware font provider path
  exposed for reverse engineering. In native mode, `0x8011a3c4` emits
  `native-text-draw` events with the text pointer, x/y cursor, font object,
  provider, vtable, and metrics pointers.
- `--bda-native-glyph-layout` selects the synthetic ASCII glyph buffer packing
  used by native text recovery experiments. `rows-lsb-vscale2` plus
  `--fb-orientation hflip` is currently the most readable native-firmware view
  for the msgbox smoke case and is selected automatically by the direct-BDA
  preset when `--bda-text-mode native` is used.
- `--bda-native-raster-mode firmware|synth` controls the `0x8011b054` native
  glyph raster path. The default `firmware` mode runs C200's raster routine and
  is the stable regression path. `synth` is an experimental direct raster model
  for ASCII glyphs and is not used by default because skipping the firmware
  function can expose additional Unicorn/control-flow instability.
- `reverse/hwemu/run_bda_smoke.py` runs the current direct-BDA smoke suite and
  writes `build/hwemu_smoke_summary.json`. Use `--case msgbox` or
  `--case sdkinput` to run a single case. In `--text-mode native`, the smoke
  runner defaults to the readable `rows-lsb-vscale2` + `hflip` view. It also
  forwards direct-BDA event-loop injections, for example:
  `python .\reverse\hwemu\run_bda_smoke.py --case msgbox --bda-key-event 7:9@1 --bda-key-event 7:10@3`.
  The summary records the requested BDA events, the BDA event poll count, and
  the actual injection log.
- Native BDA startup is confirmed under direct launch: the standard entry calls
  `0x81c00050` to populate imports at `0x81c24030`, then calls the app main at
  `0x81c0383c` for calculator-template builds. A hardware-passing msgbox test
  reaches the patched main and dispatches through the runtime GUI table. The GUI
  table is patched by C200 at runtime; in the current trace
  `*(0x81c24034) + 0x2b8` resolves to `0x800c6544`, not the static word found in
  raw `C200.bin`.
- JSON output includes `execution.mmio_snapshot.bda_runtime`, which records the
  BDA import slots and key runtime GUI table offsets such as
  `create_control+0x1a4`, `message_box+0x2b8`, and `event_loop+0x378`.
- `reverse/hwemu/make_fat16_image.py` builds a FAT16 image with standard VFAT
  long-file-name entries, so Chinese paths such as `A:\系统\数据\Config.inf`
  can be represented without relying on guessed 8.3 aliases.
- UART capture is wired, but this boot path currently writes only three carriage
  returns to `0x10030000`
- `0xa1f81000` and `0xa1f82000` currently contain near-identical contents, with
  a 4-line vertical offset
- RGB565 and BGR565 dumps both look like horizontal fragmented bands, so the
  remaining issue is likely framebuffer layout/LCD DMA window interpretation or
  an incomplete display peripheral model, not just red/blue channel order
- Direct BDA launch can now produce visible app pixels for msgbox-style apps
  through the modeled dirty-rect/display path plus the temporary ASCII text
  hook. Native font-provider rendering is still incomplete; use
  `--bda-text-mode native` to disable the temporary ASCII hook while debugging
  the real firmware font path.

## Modeled MMIO

Important modeled physical ranges:

- `0x10000000..`: clock/reset/PLL-like registers
- `0x10001008`: interrupt/GPIO mask/ack-like register
- `0x10010000..0x100103ff`: GPIO port configuration/status registers
  (`0x10010300` idle level includes `0x20000000`; the NAND-backed resource path
  waits for this bit at `0x8005ba50`)
- `0x10030014`: UART status register, returns ready bits `0x60`
- `0x10003000`: timer/counter status register, returns ready bit `0x80`
- `0x10021004`: C200 graphics/blit status, returns done bit `0x800`
- `0x10030000..`: UART-like byte registers
- `0x1004300c`: LCD command/status, returns ready bit `0x80`
- `0x13010114`: BCH/ECC done bit `0x8`
- `0x18000000..0x18010000`: external NAND bus data/command/address windows

Seeded display globals:

- `0x8033c0b4 = 0x0f0`
- `0x8033c0b8 = 0x140`
- `0x8033c0bc = 0x10`
- `0x8033c0e4 = 0xa1f81000`
- `0x8033c0e8 = 0xa1f82000`

## Emulator Workarounds

Unicorn's MIPS core raises or mishandles several branch/delay-slot paths in
this firmware. The profile currently includes targeted recovery for:

- `j`, `jal`, `jr`
- `beq`, `bne`, `blez`, `bgtz`
- `bltz`, `bgez`
- selected delay-slot instructions used by these paths
- pure LCD getter functions at `0x80010d70..0x80010da0`
- palette/conversion early-return patches at `0x800a91f4` and call-site
  `0x800a88e8`
- narrow stack corrections at `0x800176e0` and `0x800de5bc`
- idle-loop detection at `0x80008a84`
- immediate wake from the MIPS `wait` instruction at `0x8005bcd4`, resuming at
  `0x8005bce8`, until the corresponding interrupt source is modeled
- narrow stack/epilogue fixes around `0x80183304` and `0x8017a860`, seen when
  the NAND-backed resource/cache reader runs deeper than the legacy idle path
- a narrow `0x801737b8` large-frame epilogue fix, needed after FAT directory
  scanning when SP is observed `0x20` bytes too low and the adjacent saved RA is
  valid

These are trace-enabling emulator workarounds, not confirmed hardware behavior.
The broad `repeat-sp-fix` helper is especially provisional: it keeps progress
moving when Unicorn presents the same stack prologue twice, but it can mask
real control-flow bugs. Treat traces after deep UI initialization as tentative
until this is replaced by a more robust MIPS execution backend or a stricter
delay-slot model.

## Next Work

The current emulator can reach the OS idle loop. The next useful work is to
make that loop interactive:

- add a timer/interrupt source instead of only polling idle;
- model keyboard and touchscreen events. `--gui-key-event code@idle_hit` now
  injects a GUI-level key event through the observed C200 pending-bitset path:
  it marks `0x80473f38/0x80473f40+slot`, sets the key table node flag, clears
  the `0x80473f08` gate byte, and pumps firmware dispatcher `0x800080f0` from
  the idle context;
- `--bda-key-event code[:event_type]@event_hit` injects a key-like event into
  the direct-BDA event loop itself, after a BDA has already been launched.
  Event type `9` behaves as key-down and type `10` behaves as key-up in the
  observed `0x8012cc7c` loop. This is separate from system-idle
  `--gui-key-event`: direct-launched BDAs can reach their own event idle before
  the system idle loop is hit again. Current regression:
  `build/hwemu_direct_bda_bdakey_downup_probe.json`,
  `--bda-key-event 7:9@1 --bda-key-event 7:10@3`,
  `stop_reason = bda_event_idle`, no invalid memory access. JSON output records
  `execution.watch.bda_event_poll_hits`,
  `execution.watch.bda_key_events`, and
  `execution.watch.bda_key_event_log`;
- `--bda-event event_type[:word0[:word2[:word3]]]@event_hit` injects a raw
  16-byte event object into the same direct-BDA loop. This is useful for
  testing non-key events without adding another narrow CLI option. The loop at
  `0x8012cc7c` reads event type from `event + 4`; type `4` returns flag `0x20`,
  type `5` returns `0x40`, type `9` returns `0x400`, type `10` returns `0x800`,
  type `8` returns `0x1000`, type `11` returns `0x4000`, and type `12` can
  return `0x2000` when the firmware touch/pen predicate at `0x8001a6c8`
  succeeds. Types `9` and `10` additionally copy `lbu event[0]` into
  `0x8047408a`. Current raw-event regression:
  `build/hwemu_direct_bda_raw_event4_probe.json`, `--bda-event 4@1`,
  `stop_reason = bda_event_idle`, no invalid memory access;
- `--bda-touch-event x:y:down[:event_type]@event_hit` injects a direct-BDA
  touch event and seeds the known touch globals at `0x80370fc0..0x80370fd4`
  plus `0x8048dd00/04/08`. The default event type is `4` for down and `5` for
  up, which the event loop maps to flags `0x20` and `0x40`. Current regression:
  `build/hwemu_direct_bda_touch_downup_noop0_probe.json`,
  `--bda-touch-event 120:160:1@1 --bda-touch-event 120:160:0@3`,
  `stop_reason = bda_event_idle`, no invalid memory access. The final snapshot
  shows `touch_x_80370fc8 = 0x78`, `touch_y_80370fcc = 0xa0`,
  `touch_flag_8048dd00 = 1`, `touch_flag_8048dd04 = 0`, and
  `release_state_80370fd0 = 1`;
- `--bda-idle-stop-polls n` controls how many empty direct-BDA event polls are
  allowed after the last scheduled BDA event before stopping with
  `bda_event_idle`. The default is `1` for fast smoke tests; larger values are
  useful when tracing internal event queue consumption.
- JSON output now includes
  `execution.mmio_snapshot.display_event_queue`, a snapshot of the direct-BDA
  display/internal event ring at `0x80825840`. The ring object uses
  `+0x10 = buffer`, `+0x14 = capacity`, `+0x18 = read index`, and
  `+0x1c = write index`; each queued record is seven 32-bit words. In the
  current touch regression the direct-BDA touch down/up pair becomes internal
  event codes `0x83f` and `0x840`, and final read/write indices both advance to
  `3`, proving the ring consumed both touch events. In the msgbox case those
  codes are handled by the `0x800e0d68` dialog/control callback path and do not
  hit the generic window handlers at `0x8008f9a4`, `0x8008fc50`, or
  `0x8008fd80`;
- direct-BDA no-op event polling now uses synthetic event type `0`, not type
  `0x0a`. Type `0x0a` is a real key-up path in `0x8012cc7c`, so using it as
  an empty event produced a spurious `0x800` key flag in later dispatcher
  traces;
- key sampling now has a stable firmware-level probe:
  `--fw-key-sample 7@2 --fw-key-sample 0@4` reaches idle, forces two
  `0x8001b464` scans through `0x8005ce48`, and leaves
  `key_down_flag_8048dd0c = 0`, `last_key_code_8048dd10 = 7`,
  `release_state_80370fd0 = 1`. This proves the sampler/global-state layer,
  but it is not yet a complete GUI event injection path;
- touch sampling now has a stable firmware-level probe:
  `--touch-sample x:y:down@idle_hit` calls C200 sampler `0x8005ccf4` from the
  idle context and forces `0x8001a6b0` pen state plus `0x8001a3a0` coordinates.
  The screen coordinate space is 240x320 portrait. Current verified regression:
  `build/hwemu_fat16_touch_down_up_sample.json`,
  `--touch-sample 120:160:1@2 --touch-sample 120:160:0@4`,
  `stop_reason = idle_loop`, no invalid memory access. Press sets
  `touch_x_80370fc8 = 0x78`, `touch_y_80370fcc = 0xa0`,
  `touch_flag_8048dd04 = 1`; release clears `touch_flag_8048dd04` and sets
  `touch_flag_8048dd00 = 1`;
- raw-system touchscreen calibration now uses controller-state injection, not
  the old sampler call path. `--touch-state x:y:1` updates the low-level
  `0x807f7110` touch latch and clears GPIO C bit 27 at physical `0x10010200`;
  `--touch-state x:y:0` restores that bit and mirrors the C200 touch-release
  ISR side effects by setting `0x80477d84 = 1` and `0x80362794 = 0x28`. This
  is required by the calibration wait loop after a valid coordinate. It no
  longer writes the higher GUI event globals directly.
  `--touch-controller-event x:y:down@idle_hit` applies
  the same hardware-controller state at a scheduled system idle hit, so down/up
  sequences can be modeled without GUI injection. The NAND-ready bit on the
  same GPIO word remains generated by the MMIO model. Pending IRQs can now be
  serviced from the system idle point through C200's own IRQ table, which is an
  equivalent acceleration for the currently incomplete CP0/EPC exception model.
  In `build/c200_touch_hw_idleirq.json`, a hardware-level touch at `(150,205)`
  reaches IRQ12 `0x8001a8fc`, SADC conversion `0x8001ac40`, queue post
  `0x8000b3dc`, and GUI dispatch `0x800dd380 -> 0x800e0d68`; the resulting
  internal queue records include screen coordinate `(150,204)` and local dialog
  coordinate `(100,103)`. This confirms the modal "否" click path at the
  hardware/driver layer. The next issue is continuing the post-dialog boot/menu
  path quickly and getting the redraw/flush state current, not touch dispatch
  parameter corruption.
- `0x10010100 & 0x40000` is GPIO B bit 18, used by the firmware USB-detect
  helper at `0x80059f68`; disconnected state must keep this bit high. A trace
  with `build/c200_usbret_trace.json` shows GPIOB reads `0x78040000` and the
  helper returns `0`, so touchscreen presses must not clear this bit. The
  firmware sleep/wait path at `0x8005bba4..0x8005bcfc` also calls through this
  helper.
- old checkpoints can contain stale zero GPIO idle levels. State loading now
  seeds `GPIO_KEY_IDLE_LEVELS` first and then synchronizes the touch GPIO bits
  from the saved `touch_down` state. A held touch must be released through
  `--touch-controller-event x:y:0@idle_hit`; otherwise `0x80059f68` sees
  GPIOB bit 18 low and the idle path skips `0x800087c4` timer ticks.
- `--scheduler-tick-clamp` is now a historical diagnostic option, not part of
  the cold-boot regression. When used for old checkpoints it must enter
  `0x800080f0` with `0x80473f08 == 0` and `0x80473f4d == 0`; writing
  `0x80473f08 = 1` before direct dispatch is observably wrong because
  `0x800080f0` immediately returns when the countdown byte is nonzero.
- raw C200 boot can now pass the time-change modal and reach the visible system
  main menu. Repro checkpoint:
  `build/c200_searching_schedfix.json` /
  `build/c200_searching_schedfix.png`, using
  `build/c200_postdialog_freescan.pkl` plus
  `--touch-controller-event 150:205:0@1`. The screen shows the bottom category
  bar and the selected `查词典 / Searching` main-menu item; there is no FAT
  directory scan or block read activity in this state, so `Searching` is the
  selected menu label rather than a storage scan progress message.
- Current raw-NAND cold path reaches the same time-change modal after the
  FAT16 cluster-read and free-FAT-scan accelerators. The modal registers touch
  capture slot 0 at `0x803adcc0` with object `0x80955dc0` and handler
  `0x800e07f4` in `0x804a66e0/0x804a66e4`. Static reversing shows the useful
  path is press then release, not a release-only tap: `0x800e0d68 event=1`
  checks the yes/no button rectangles and queues `event=0x66`, while
  `0x800ca8c0 -> 0x800cad20 -> 0x800cee94 -> 0x800d099c` handles the later
  release. `build/c200_modal_release_after_highlight.png` confirms that
  releasing `(180,220)` after the button highlight closes the dialog and lands
  on the `查询典 / Searching` main menu.
- `reverse/hwemu/run_time_dialog_to_menu_smoke.py` captures that dialog
  interaction as a hardware-touch regression. It starts from
  `build/c200_after_freefat_root256.pkl`, releases the stale calibration touch,
  presses the dialog's `否` button, saves that held-button state, then releases
  through `--touch-state`. The two-phase shape is intentional: the firmware
  must run the synchronous dialog loop between down and up so it can set the
  button state before the release event.
- `reverse/hwemu/run_cold_boot_to_menu_smoke.py` runs the current longest
  system regression: raw `C200.bin` at `0x80004000`, combined raw NAND, the
  two observed calibration touches `(10,10)` and `(229,10)`, the time-change
  dialog `否` button, and finally the main menu. Current passing run:
  `build/hwemu_cold_boot_to_menu_check3_summary.json` with final screenshot
  `build/hwemu_cold_boot_to_menu_check3_menu.png`. The archived check3 JSON
  shows `scheduler-tick-clamp` was not hit in any phase, so the script no
  longer passes that option. The same artifacts show no NAND program/erase or
  page overrides, so the script also no longer passes the historical readonly
  NAND guard. It still uses the raw-NAND copy loop accelerator and the
  `0x8017ca10` resource-cache16 equivalent lookup accelerator.
- `build/hwemu_rescache_missload_probe.json` verifies the refined
  resource-cache16 model from an existing calibration checkpoint: it reaches
  `stop=max_seconds` with no invalid access, records `11590` accelerated
  lookups, and includes `mode=miss-load` events that populate real firmware
  cache buffers such as `0x809517c0` before later cache hits.
- Surface diagnostics now include `mmio_snapshot.surface`, with counters for
  `setpixel`, `hline`, rectangle block copy, and single-pixel read
  accelerators plus rolling `recent_events` and `recent_events_by_mode` lists.
  Each event records the surface object, backing buffer, coordinates,
  dimensions, pitch, optional color, destination/source address, and whether
  LCD mirroring was enabled. `build/hwemu_surface_event_modes_probe.json`
  resumes from the current menu checkpoint, runs with no invalid memory
  access, and records `5284` `setpixel` events plus `38144` `pixel-read`
  events. The combined recent ring can be dominated by high-frequency
  pixel reads, so use `recent_events_by_mode.setpixel` or the per-mode counters
  when checking whether earlier write accelerators ran.
- C200 reset now has two narrow equivalent accelerators in the fast-hook set:
  the cache-management loop at `0x8000403c` and the BSS clear loop at
  `0x80004074`. These replace hardware/cache setup and a linear zero-fill with
  the same resulting RAM/register state needed before normal C200 startup.
- `reverse/hwemu/run_system_menu_smoke.py` runs the current raw-system menu
  interaction regression. It starts from `build/c200_searching_schedfix.pkl`,
  sends a hardware-controller touch at `(210,287)` to the bottom `工具` tab,
  releases it, and checks the touch IRQ/queue/GUI path, scheduler activity,
  release flags, framebuffer sanity, and surface draw activity. It
  intentionally does not pass `--scheduler-tick-clamp` or
  `--resource-cache16-accelerator`;
  `0x800087c4`, `0x80007e08`, and `0x800080f0` advance through the normal
  wait/timer/scheduler path. Current passing run:
  `build/hwemu_system_menu_surface_trace_summary.json`,
  `build/hwemu_system_menu_surface_trace_press.png`, and
  `build/hwemu_system_menu_surface_trace_release.png`; the release screenshot
  shows the tools page with `Ver`, pointer, and `USB` icons. The summary now
  includes compact surface counts and verifies that `recent_events_by_mode`
  retains `setpixel` samples for both press and release phases.
- `0x8001b464` is a six-key scanner that returns these active-low GPIO codes:
  code `10` = GPIO B bit 30 (`0x10010100 & 0x40000000`), code `5` = GPIO B
  bit 28, code `7` = GPIO B bit 27, code `6` = GPIO B bit 29, code `9` =
  GPIO C bit 27 (`0x10010200 & 0x08000000`), code `4` = GPIO D bit 21
  (`0x10010300 & 0x00200000`);
- the current key table is at `0x806c5d10`; nonzero entries observed at indices
  `7`, `8`, `9`, `62`, and `63`
- the key pending state is a positive bitset, not active-low state. For example,
  key `7` uses node `0x806c5450`, slot `0`, mask `0x80`, group mask `0x01`, so
  injection writes `0x80473f40 |= 0x80` and `0x80473f38 |= 0x01`. The default
  idle state `0x80473f38 = 0x80`, `0x80473f47 = 0x80` maps to key index `63`;
- observed GUI/input nodes are mostly `0x70` bytes and include callback-like
  words at offset `0x00`, link-like words around `0x18..0x24`, and event/status
  bytes around `0x30..0x3f`
- the touch globals around `0x80370fc0` are:
  previous x/y at `0x80370fc0/0x80370fc4`, current x/y at
  `0x80370fc8/0x80370fcc`, pen/release state at `0x80370fd0`, and auxiliary
  value `0x7f` at `0x80370fd4`. The firmware dispatch path later converts y as
  `320 - y` before calling window touch handlers such as `0x8008f9a4`,
  `0x8008fc50`, and `0x8008fd80`;
- direct `--call-va 0x800089b8:7@2` enters the key-handler-like path but still
  stops with an invalid write, even with scratch stack, so this should remain a
  diagnostic probe rather than the main event model
- current regression:
  `build/hwemu_fat16_gui_keyevent7_autopump.json`, `--gui-key-event 7@2`,
  `stop_reason = idle_loop`, no invalid memory access. The trace shows the
  injected event entering `0x800080f0`, selecting `0x806c5450` through
  `0x80008178`, switching via `0x800a7c18`, then returning to the idle node;
- keep refining the raw NAND FAT path. `build/c200_noblock_combined_nand_2.json`
  verifies `--no-block-image`: `mmio_snapshot.block_image.image = None`, no
  block-read hook events, and recent NAND reads from pages `0x1c57..0x1c60`
  come from `source=image` with FAT table bytes landing in RAM buffers.
- C200's FAT16 BPB must use `root_entries = 256`, not 1024. With 256 entries
  the derived layout is `root_lba = 0x159`, `root_dir_sectors = 0x10`, and
  `first_data_lba = 0x169`, matching firmware globals at `0x80474238`,
  `0x80474254`, and `0x80474260`. The root256 combined images are
  `build/bbk9588_fs_fat16_root256.img` and
  `build/bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin`.
- `0x8017b4e0` is the FAT16 cluster-read/cache function. The raw NAND path now
  models its two-entry cluster cache per cluster parity: cache hits copy from
  the firmware cache buffer and increment the slot counter; clean misses load
  backing FAT sectors into the requested destination and copy them into the
  selected cache slot. This avoids stale in-RAM FAT cache state when resuming
  older checkpoints and fixes the Desktop resource failure:
  `build/c200_desktopres_root256_clusterhook.json` runs past `0x8001e900`,
  with cluster 2 resolving to LBA `0x169` and Desktop cluster 3 resolving to
  LBA `0x179`.
- `build/hwemu_cluster_cache_probe.json` verifies the refined cluster-cache
  model from an existing calibration checkpoint: `invalid = 0`, six accelerated
  cluster reads, two `miss-load` events, and three later `cache-hit` events from
  firmware buffers such as `0x8094a9c0` and `0x809489c0`.
- `0x80175e40` normalizes a FAT directory entry into the firmware's internal
  32-byte layout. The accelerator is a direct field-by-field translation of the
  firmware routine, including the combined 32-bit cluster at output offset
  `0x14` and the `0x05 -> 0xe5` first-byte conversion. Recent events now record
  source/destination, name bytes, attributes, cluster, and file size. Probe
  `build/hwemu_dirent_event_probe.json` reaches `invalid = 0` and records eight
  accelerated copies, including `SYSTEM.CFG` at cluster `0x2312`.
- refine LCD/framebuffer layout until the boot UI is visually coherent;
- complete the application draw/commit path after direct BDA launch. The BDA
  startup path now reaches the repaint loop, but current framebuffer dumps from
  `0xa1f81000` and `0xa1f82000` still show the boot logo, so the missing piece
  is likely a timer/dirty-region/display-submit path rather than native BDA
  loading;
- direct BDA msgbox launch is confirmed through the real runtime GUI table:
  calculator-template tests reach app main at `0x81c0383c`, call the message
  box wrapper at `0x800c6544`, then enter `0x800e0be4`. The emulator currently
  observes plausible dialog/window geometry in the UI pool, but the later
  hardware 2D submissions still have zero width/height. The next target is
  therefore the firmware repaint/dirty-region path around
  `0x800bd678`, `0x800bd840`, and `0x800d35f0`.
- direct BDA msgbox rendering now reaches a visible framebuffer result. The
  current regression is:
  `build/hwemu_ascii_text_skipfont.json` / `build/hwemu_ascii_text_skipfont_lcd.png`,
  `stop_reason = bda_event_idle`, no invalid memory access. The emulator seeds
  the direct-launch display/font globals, seeds a full-screen dirty rect for
  the window surface, models the `0x8012a6a8` text stepper for the observed
  call sites, and temporarily hooks `0x8011a3c4` to render 5x7 ASCII glyphs
  directly into the shadow/LCD framebuffers. This proves the BDA dialog,
  cursor-coordinate, and framebuffer paths. It is not complete font support:
  Chinese glyphs and the real firmware font provider/bitmap lookup still need
  to be modeled.
- `build\SDKInputReady_gcc.bda` now also runs under the direct-BDA preset:
  `build/hwemu_preset_sdkinput_branchfull.json` /
  `build/hwemu_preset_sdkinput_branchfull.png`, `stop_reason = bda_event_idle`,
  no invalid memory access. It covers a toolchain-generated BDA with stack-built
  msgbox strings (`BDA SDK` and `SDK probe: alloc/gui ok`). The emulator has a
  narrow workaround for this BDA's GCC string-copy loop at `0x81c038a0` because
  Unicorn mis-executes the branch/delay-slot sequence and corrupts the BDA
  string pointer.
- native firmware font rendering has progressed beyond the temporary ASCII
  hook. The direct-launch font seed now exposes an `SGM` provider header, a
  256-glyph metric count, and a callback that returns the current ASCII byte as
  glyph index. `0x8012be84` is modeled as a pixel read
  (`buffer + y * stride + x * 2`, returning `lhu`), matching the firmware delay
  slot. Current native regression:
  `build/hwemu_smoke_msgbox_native.json` /
  `build/hwemu_smoke_msgbox_native.png`, `stop_reason = bda_event_idle`, no
  invalid memory access, 26 `native-text-draw` events, 26 `font-glyph-index`
  events. `font-glyph-buffer-recover` now converts the shared 5x7 ASCII table
  into a 16x16 1bpp buffer and lets firmware `0x8011b054` perform the blit.
  The remaining issue is still glyph layout/clip fidelity: native output is
  separated and monochrome but not fully readable, so the next target is the
  `0x8011b054` glyph buffer interpretation and text clipping path.
- native text glyph experiments are now reproducible with
  `--bda-native-glyph-layout`. Tested layouts include row/column packing,
  MSB/LSB bit order, y-offset, and horizontal scale variants. The important
  trace finding is that the later raster callback at `0x8011b0cc` consumes
  glyph data from `0x80825af0`, while the earlier recovery point writes the
  synthetic buffer at `0x80825ad0`; the emulator now mirrors synthesized glyph
  data to both addresses. That fixes the buffer-address ambiguity but does not
  make native glyphs fully correct yet, so the remaining problem is not only
  glyph packing. Continue from the correctly based `0x8011b054` raster function
  and the downstream surface-copy path instead of adding more blind layouts.
- Correcting the C200 disassembly base shows `0x8011b054` is the glyph raster
  function itself. For `mode = 2`, it reads a row-major 1bpp glyph stream,
  MSB-first within each byte, and writes RGB565 halfwords to the destination
  surface. Entry stack parameters observed in the msgbox native case are:
  `old_sp+0x10 = dst`, `+0x14 = bg`, `+0x18 = fg`, `+0x1c = opaque`,
  `+0x20/+0x24 = stride/orientation modifiers`; first observed glyph uses
  `dst = 0x80958664`, `fg = 0xffff`, width/height `16x16`, mode `2`, stride
  `0x20`.
- The native msgbox smoke now reaches a partially readable firmware-rendered
  text path without the temporary `ascii-hook`. The best current smoke command
  is now simply:
  `python .\reverse\hwemu\run_bda_smoke.py --case msgbox --text-mode native`.
  For direct emulator use:
  `python .\reverse\hwemu\bbk9588_hwemu.py --preset direct-bda-msgbox --bda-text-mode native --out-prefix build\hwemu_direct_native --quiet`.
  It produces `stop_reason = bda_event_idle`, no invalid memory access, and a
  visible `HELLO...` line in
  `build\hwemu_smoke_msgbox_native_rows-lsb-vscale2_firmware_hflip.png`. This
  also confirms that the remaining visual mismatch is partly framebuffer mirror
  interpretation, not only glyph packing.
- connect touch samples to a live window/application context. On the current
  idle main-screen trace, the application object global used by the
  `0x8008f9a4` window-touch path is zero, so `--touch-sample` intentionally
  proves the hardware/sampler layer only;
- replace broad Unicorn branch/stack workarounds with either stricter
  delay-slot emulation or a more reliable MIPS backend.
