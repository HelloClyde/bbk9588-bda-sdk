# BBK 9588 BDA reverse notes

This directory contains early probes for the BBK 9588 application format.

## Current findings

- Application files are `*.bda` under the app-program directory. The user mentioned `*.dba`; the dump uses `*.bda`.
- Resource files are mostly `*.dlx`. Their first bytes are plain `44 4C 58`, i.e. `DLX`.
- The system image contains `u_boot_9588_4740.bin` with an `Ingenic` string, which matches the likely Ingenic JZ4740 family.
- `*.bda` is not an ELF file. It has a custom header followed by MIPS32 little-endian code and data.
- Code disassembles cleanly around file offset `0x95f8` in most samples.
- The system image shows the loader calling native app code at runtime VA `0x81c00020`.
  For normal apps, file offset `0x95f8` maps to `0x81c00020`.
- The startup code at `0x95f8` calls an address near `0x81c00050`; with the corrected entry mapping this points back into the same BDA rather than outside the file.
- The BDA files contain C runtime/libm strings such as `malloc`, `acos: DOMAIN error`, `pow(0,0): DOMAIN error`, plus UI names and `\shell\*.dlx` resource paths.
- The bundled BB virtual-machine app is a separate practical route for custom programs through BBasic/BBasm/BBin, but that creates BB VM programs, not native BDA applications.

## Commands

Install the disassembler dependency:

```powershell
python -m pip install --user capstone
```

Probe BDA files:

```powershell
python reverse\bda_probe.py path\to\calculator.bda path\to\bb-vm.bda
```

Preview disassembly:

```powershell
python reverse\bda_disasm_preview.py path\to\calculator.bda --count 80
```

## Likely toolchain shape

Native BDA probably needs three pieces:

1. A MIPS32 little-endian GCC/binutils toolchain targeting Ingenic/XBurst/JZ4740 style code.
2. A linker script that places text/data at the same addresses the BBK loader expects.
3. A BDA packer that writes the custom header, resource metadata, optional relocation/import tables, and the raw linked image.

The missing piece is not GCC itself; it is the BDA loader ABI and packer format. The next reverse step is to decode the header words that describe load base, entry point, text/data/BSS sizes, and any import/API table.
