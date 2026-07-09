# QEMU Source Overlay

This directory contains the full QEMU source files that differ from upstream
QEMU for the BBK9588 emulator.

It is intentionally an overlay, not a vendored full QEMU checkout:

- `hw/mips/bbk9588.c` is the custom board/machine model.
- The other files are the small QEMU MIPS/Kconfig/build-system changes needed
  by the current emulator backend and diagnostics.

Install this overlay into a QEMU checkout with:

```powershell
python .\emu\qemu\scripts\install_qemu_overlay.py --qemu-source E:\qemu-src
```

The generated patch in `emu/qemu/patches/` is kept for normal setup and code
review. This overlay is kept so the repository also contains the complete
modified source files.
