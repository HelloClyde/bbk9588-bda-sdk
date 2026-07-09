# BBK 9588 Emulator

This is the Windows runtime package for the BBK 9588 QEMU system emulator.

## Contents

- `bin/bbk9588-qemu-system-mipsel.exe` and the DLLs needed to run it.
- `start-web.ps1` and `start-web.cmd` launchers.
- The packaged web frontend under `emu/web/`.
- The Python image-building and runtime tools under `emu/tools/`.
- A bundled `python/` runtime when the package is produced by GitHub Actions.

## Start

Double-click `start-web.cmd`, or run:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-web.ps1
```

The frontend opens at:

```text
http://127.0.0.1:8000/
```

## Required Local Data

Public release packages do not include dumped firmware, NAND images, or BDA
applications. Put the local dump next to `start-web.ps1`:

```text
系统/
  数据/
    C200.bin
应用/
```

On first launch, the script builds:

```text
build/bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin
```

You can force a rebuild with:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-web.ps1 -RebuildImages
```

Extra frontend arguments can be appended after the launcher options, for
example:

```powershell
powershell -ExecutionPolicy Bypass -File .\start-web.ps1 -Port 8010 --no-auto-calibration
```
