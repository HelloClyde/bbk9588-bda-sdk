# QEMU bbk9588 Machine

The QEMU backend uses a custom `bbk9588` MIPS system machine. The project does
not vendor the full QEMU tree, but it does include the complete modified source
files as an overlay plus a patch that can be applied to a clean QEMU checkout.

Source overlay:

```text
emu/qemu/source-overlay/
```

Patch file:

```text
emu/qemu/patches/qemu-v11.0.0-bbk9588.patch
```

Patch target:

```text
QEMU v11.0.0
```

## Apply Patch

```powershell
python .\emu\qemu\scripts\apply_qemu_patch.py --qemu-source E:\qemu-src
```

## Install Source Overlay

The overlay copies the full modified files into a QEMU checkout:

```powershell
python .\emu\qemu\scripts\install_qemu_overlay.py --qemu-source E:\qemu-src
```

Check whether a checkout already matches the overlay:

```powershell
python .\emu\qemu\scripts\install_qemu_overlay.py --qemu-source E:\qemu-src --check
```

Dry check only:

```powershell
python .\emu\qemu\scripts\apply_qemu_patch.py --qemu-source E:\qemu-src --check
```

Reverse check/remove:

```powershell
python .\emu\qemu\scripts\apply_qemu_patch.py --qemu-source E:\qemu-src --reverse --check
python .\emu\qemu\scripts\apply_qemu_patch.py --qemu-source E:\qemu-src --reverse
```

## Build on Windows

Install MSYS2 and UCRT64 dependencies, then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\qemu\scripts\build_qemu_windows.ps1 `
  -QemuSource E:\qemu-src `
  -BuildDir E:\qemu-src\build-bbk9588-win
```

To build after installing the source overlay instead of applying the patch:

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\qemu\scripts\build_qemu_windows.ps1 `
  -QemuSource E:\qemu-src `
  -BuildDir E:\qemu-src\build-bbk9588-win `
  -UseOverlay
```

The script runs QEMU configure if the build directory does not already contain
`build.ninja`, then builds `qemu-system-mipsel.exe`.

Default output:

```text
E:\qemu-src\build-bbk9588-win\qemu-system-mipsel.exe
```

## Launcher Integration

`emu.qemu.system.find_qemu()` searches these locations before `PATH`:

```text
E:\qemu-src\build-bbk9588-win
E:\qemu-src\build
E:\qemu
C:\Program Files\qemu
C:\Program Files (x86)\qemu
%USERPROFILE%\AppData\Local\qemu
```

The Web frontend should usually be started with:

```powershell
python -m emu.web.frontend `
  --boot-mode uboot `
  --qemu E:\qemu-src\build-bbk9588-win\qemu-system-mipsel.exe
```

## Notes

- `hw/mips/bbk9588.c` models the board, RAM, firmware loading, LCD/frame
  chardev, input chardev, NAND/MSC/FTL-facing storage behavior, timers,
  interrupts, GPIO/SADC touch state, and compatibility diagnostics.
- The patch also contains small target/mips instrumentation/helper changes used
  by the current machine model and diagnostics.
- Machine options can be passed through the frontend with repeated
  `--qemu-machine-option`.
