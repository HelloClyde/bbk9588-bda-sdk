# BDA Analysis Reports

This directory is the workspace for per-application native BDA reports.

## Generated Index

- `bda_inventory.json`: machine-readable inventory for all original
  `应用/程序/*.bda` files.
- `bda_inventory.md`: compact human-readable table with header/category/layout,
  DLX references, and raw indirect API offset counts.

The inventory is only an index. A complete per-BDA report still needs:

```text
1. Header and menu identity
2. Runtime layout, entry, BSS, important globals
3. External resources and data files
4. Main startup flow
5. GUI/window/event behavior
6. FS/media/time/input API usage
7. Cross-checks against other BDAs and hardware probes
8. Unknowns and follow-up probes
```

## Deep Reports Already Started

- `reverse/reports/notepad_bda_report.md`
- `reverse/reports/album_bda_report.md`
- `reverse/reports/time_bda_report.md`
- `reverse/reports/music_bda_report.md`
- `reverse/reports/alarm_bda_report.md`
- `reverse/reports/video_bda_report.md`
- `reverse/reports/recorder_bda_report.md`
- `reverse/reports/ebook_bda_report.md`
- `reverse/reports/settings_bda_report.md`
- `reverse/reports/paint_bda_report.md`
- `reverse/reports/eros_bda_report.md`
- `reverse/reports/linkgame_bda_report.md`
- `reverse/reports/blackwhite_bda_report.md`
- `reverse/reports/jiugongge_bda_report.md`
- `reverse/reports/thunder_bda_report.md`
- `reverse/reports/tank_bda_report.md`
- `reverse/reports/sango_bda_report.md`
- `reverse/reports/schedule_bda_report.md`
- `reverse/reports/ninecourse_bda_report.md`
- `reverse/sdk/element_bda_notes.md`
- `reverse/sdk/gameboy_notes.md`
- `reverse/sdk/bbvm_notes.md`
- `reverse/sdk/game_framework_notes.md`
- `reverse/sdk/picture_notes.md`
- `reverse/sdk/paint_notes.md`
- `reverse/sdk/showcase_notes.md`
- `reverse/sdk/usb_debug_notes.md`

These are SDK-facing notes rather than final per-BDA reports. The next pass
should convert them into one report per original application and link each SDK
claim back to the BDA evidence that supports it.
