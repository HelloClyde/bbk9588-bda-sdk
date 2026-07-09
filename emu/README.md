# BBK 9588 Emulator

This directory contains the emulator runtime that should be published with the
project:

- Python launcher and Web frontend for the emulator.
- QEMU process backend for the `bbk9588` system machine.
- Image-building tools for the local firmware/resource dump.
- QEMU patch and build scripts needed to reproduce the custom
  `qemu-system-mipsel.exe`.
- User-facing docs for setup, images, launch commands, and current limits.

The public repository should not include dumped firmware, NAND images, or BDA
applications. Those files stay under ignored local paths such as `系统/`,
`应用/`, and `build/`.

## Layout

```text
emu/
  app.py                         Web frontend entry point
  qemu_app.py                    QEMU command/probe entry point
  core/                          Shared framebuffer helpers
  web/                           Local browser frontend and HTTP API
  tools/                         FAT/NAND image construction tools
  qemu/
    system.py                    QEMU process backend and command builder
    source-overlay/              Full modified QEMU source files
    patches/                     Patch for the custom QEMU machine
    scripts/                     QEMU patch/build scripts
    README.md                    QEMU build and integration guide
  docs/
    images.md                    Firmware/resource image preparation guide
```

## Requirements

- Windows 10/11.
- Python 3.11+.
- MSYS2 UCRT64 toolchain for building custom QEMU.
- A QEMU source checkout matching the patch target. Current patch target:
  QEMU `v11.0.0`.
- Local device dump files:
  - `系统/数据/C200.bin`
  - `系统/数据/u_boot_9588_4740.bin`
  - `系统/` and `应用/` resource trees

Install Python dependencies from the repository root:

```powershell
python -m pip install -r requirements.txt
```

## Build QEMU

Apply the bundled QEMU patch:

```powershell
python .\emu\qemu\scripts\apply_qemu_patch.py --qemu-source E:\qemu-src
```

The same modified files are also stored as a full source overlay under
`emu/qemu/source-overlay/`. To install by copying the overlay instead of using
`git apply`:

```powershell
python .\emu\qemu\scripts\install_qemu_overlay.py --qemu-source E:\qemu-src
```

Build the patched `qemu-system-mipsel.exe` on Windows/MSYS2:

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\qemu\scripts\build_qemu_windows.ps1 `
  -QemuSource E:\qemu-src `
  -BuildDir E:\qemu-src\build-bbk9588-win
```

The launcher also searches `E:\qemu-src\build-bbk9588-win` automatically, so
the default Web command works after a successful build.

See [qemu/README.md](qemu/README.md) for details.

## Build Runtime Images

The QEMU backend expects a disposable NAND image generated from the local
firmware/resource dump. Build it from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\tools\build_runtime_images.ps1
```

Default output:

```text
build/bbk9588_fat_page1c40.img
build/bbk9588_nand_c200_fat_page1c40.bin
build/bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin
```

The frontend uses
`build/bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin` when present.

See [docs/images.md](docs/images.md) for the source file layout and manual
commands.

## Run Web Frontend

Start the QEMU Web frontend:

```powershell
python -m emu.web.frontend `
  --host 127.0.0.1 `
  --port 8000 `
  --boot-mode uboot `
  --qemu E:\qemu-src\build-bbk9588-win\qemu-system-mipsel.exe
```

Then open:

```text
http://127.0.0.1:8000
```

For diagnostics, add QEMU machine options with repeated
`--qemu-machine-option name=value`.

## Probe QEMU Without Web

Print the generated QEMU command:

```powershell
python .\emu\qemu_app.py --boot-mode uboot --dry-run
```

Run a bounded smoke launch:

```powershell
python .\emu\qemu_app.py --boot-mode uboot --timeout 10
```

## Package and Release

Create a local emulator package:

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\tools\package_emulator.ps1 -Version emu-local
```

Default output:

```text
build/dist/bbk9588-emulator-emu-local.zip
build/dist/bbk9588-emulator-emu-local.zip.sha256
```

GitHub Actions publishes the same package to the repository Releases page from
`.github/workflows/release-emulator.yml`.

- Push a tag named `emu-v*` or `v*` to publish automatically.
- Or run the `Release emulator` workflow manually and provide a version.
- Release archives intentionally exclude dumped firmware, NAND images, BDA
  applications, and local build output.

## Current Status

The QEMU backend reaches the system UI, supports framebuffer output through the
QEMU frame chardev, accepts frontend touch/key input, and can launch multiple
built-in applications. It is still an in-progress SoC model:

- Some menu icon/resource rendering paths are still imperfect.
- The storage/NAND/FTL/FAT/cache model needs more work before all app resource
  paths match real hardware.
- Diagnostic machine properties and TCG helpers remain in the QEMU patch, but
  the default launcher path should not rely on Python/GDB firmware hooks.
