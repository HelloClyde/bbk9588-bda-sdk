# BBK 9588 Native BDA SDK and Toolchain

An experimental native `*.bda` SDK and build toolchain for the BBK / Bubugao
9588 learning device, with reverse-engineering notes used to discover the app
format and system APIs.

The project currently covers:

- native BDA header decoding and checksum repair
- no-template native BDA packaging
- menu title/category/icon experiments
- DLX resource inspection, extraction, and rebuilding
- a freestanding MIPS little-endian C SDK draft
- hardware-tested probes for filesystem, GUI, input, text, image, audio, and
  emulator-related APIs
- a separate hardware-emulator work area for booting the real system image
- an experimental USB mass-storage debug bridge for faster hardware probing
- per-application reverse-engineering reports for bundled apps

## Repository Layout

```text
reverse/                 Python build/reverse-engineering tools
reverse/examples/        Freestanding C/ASM BDA probe sources
emu/                     Hardware emulator app, frontend, hooks, tools, tests
reverse/sdk/             Experimental native SDK header and API notes
reverse/reports/         Per-BDA analysis reports and indexes
tools/                   Toolchain notes and local install/cache location
scripts/                 Setup/helper scripts
requirements.txt         Python package requirements
DATA_NOTICE.md           What should not be committed
```

Local-only directories are intentionally ignored:

```text
system-dump/              local device system dump, ignored
app-dump/                 local device application/data dump, ignored
build/                    generated BDA/DLX/probe outputs
tools/g++-.../            extracted local compiler directory
```

## Status

This is research code. Some APIs are confirmed on real hardware; many are still
named with `_LIKE` because their ABI or lifetime rules are not fully proven.

Hardware-confirmed highlights:

- BDA apps are MIPS32 little-endian native code, not ELF.
- Common native entry is file offset `0x95f8`, runtime VA `0x81c00020`.
- BDA headers use an XOR-encoded metadata area plus a byte-sum checksum.
- No-template C and ASM BDAs can be built from scratch and shown in the menu.
- Custom menu title, category, and icon generation works.
- DLX files are resource containers whose image entries often contain VX blocks.
- `text_A.dlx` can be opened and decoded from a custom app; VX drawing works.

See [reverse/sdk/README.md](reverse/sdk/README.md) for SDK details and
[reverse/native_toolchain_notes.md](reverse/native_toolchain_notes.md) for the
toolchain notes. The hardware emulator lives in
[emu/](emu/) with its own
[README](emu/README.md), `app.py` frontend entry point, hook modules, NAND image
helpers, and smoke-test entry points.

## Setup

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

For C builds, download and unpack the MIPS little-endian toolchain:

```powershell
.\scripts\setup_toolchain.ps1
```

It provides:

```text
mipsel-none-elf-gcc
mipsel-none-elf-objcopy
```

The setup script downloads `g++-mipsel-none-elf-15.2.0.zip` from the public
grumpycoder/PCSX-Redux toolchain mirror when it is not already cached locally.
The build scripts then search `tools/g++-mipsel-none-elf-*/bin/` automatically,
or you can pass `--prefix` to use another compatible toolchain.

## Build a Minimal Native BDA

```powershell
python reverse\bda_compile_c.py reverse\examples\hello_msgbox.c `
  --no-template `
  --title HelloBDA `
  --category 9 `
  -o build\HelloBDA.bda
```

With a custom icon:

```powershell
python reverse\bda_compile_c.py reverse\examples\notpl_demo_msgbox.c `
  --no-template `
  --title NoTplDemo `
  --category 9 `
  --icon-png path\to\icon.png `
  --icon-background 14245c `
  -o build\NoTplDemo.bda
```

## Inspect BDA and DLX Files

```powershell
python reverse\bda_probe.py path\to\calculator.bda
python reverse\bda_disasm_preview.py path\to\calculator.bda --count 80
python reverse\dlx_inspect.py path\to\text_A.dlx
python reverse\dlx_extract.py path\to\text_A.dlx -o build\text_A_extract
```

## USB Debug Bridge

Build the resident debug bridge:

```powershell
python reverse\bda_compile_c.py reverse\examples\usb_debug_bridge.c `
  --no-template `
  --title UsbDebug `
  --category 9 `
  -o build\UsbDebugBridge.bda
```

Copy it to the device application directory, run it on the device, then use the
host helper:

```powershell
python tools\usb_debug_host.py --drive F: --tail
python tools\usb_debug_host.py --drive F: -c status
python tools\usb_debug_host.py --drive F: -c "msg hello"
python tools\usb_debug_host.py --drive F: -c quit
```

See [reverse/sdk/usb_debug_notes.md](reverse/sdk/usb_debug_notes.md).

## Publishing Notes

Before pushing to GitHub, check:

```powershell
git status --short
```

Source, scripts, and documentation should appear. Original dump contents,
generated BDAs/DLXs, downloaded toolchain archives, and extracted local
toolchains should remain ignored. See
[DATA_NOTICE.md](DATA_NOTICE.md).

## License

No license has been selected yet. Add a `LICENSE` file before accepting outside
contributions or redistributing substantial code.
