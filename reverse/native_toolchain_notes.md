# Native BDA toolchain notes

This is deliberately for native `*.bda`, not BB virtual-machine programs.

## Loader model observed so far

- Most app files contain the standard startup signature at file offset `0x95f8`.
- The startup stub is MIPS32 little-endian.
- The system binary `C200.bin` copies 8 words from `0x80281680` to `0x81c00000`.
  Those words point at small system/libgcc helper routines around `0x800ab370`.
- The system then copies the native BDA code image to `0x81c00020` and calls it with `jalr`.
  The normal app entry mapping is therefore:

```text
file offset 0x95f8 -> runtime VA 0x81c00020
```

- Common startup code reads words from `0x81c00004`, `0x81c00008`, `0x81c0000c`, `0x81c00010`, and `0x81c00014`,
  then stores them into app BSS/global slots. Later bundled code treats the `0x81c00014` value as a table pointer and calls
  the function at offset `0x94` with `.dlx` path strings, which still looks like the resource/DLX loader path after startup
  has replaced or repurposed that slot.
- Writable globals and BSS are placed just past the file-backed image.

For the calculator-sized template, the startup stores those imported pointers at:

```text
0x81c24030 = *(0x81c00014)   resource/DLX table, +0x94 loads/binds a DLX path
0x81c24034 = *(0x81c00004)   GUI/window/control table, used at +0x30/+0x50/+0x54/+0xe4/+0xe8/+0x17c/+0x378...
0x81c24038 = *(0x81c0000c)   secondary system table, still unmapped
0x81c2403c = *(0x81c00008)   file/resource stream table, likely +0 open, +4 close, +8 read
0x81c24040 = *(0x81c00010)   memory table, likely +0x8 alloc and +0xc free
```

This split is from bundled BDA call sites plus matching system-code usage of
the same table shape. Treat names as provisional until tested on hardware.

System-bin probe:

```powershell
python reverse\system_bin_probe.py --root .
python reverse\bda_api_scan.py --root .
```

## Current practical build path

The first useful target is a template-based native patcher:

1. Keep an existing `.bda` header and pre-code resource area.
2. Replace the native MIPS code entry with custom code.
3. Keep file size unchanged until checksum/header fields are fully understood.

`bda_make_noop.py` creates a minimal native BDA whose entry is:

```asm
jr   $ra
nop
```

This is a smoke test for the native loader path. It does not use BB VM.

`native_bda_build.py` is a tiny assembly-based builder. It copies a native BDA
template, uses `0x81c00020` as the native entry VA, assembles a small MIPS source
file, and patches it into the native entry area.

Examples:

```powershell
python reverse\native_bda_build.py reverse\examples\noop.s --root . -o build\native_noop_from_asm.bda
python reverse\native_bda_build.py reverse\examples\load_dlx_then_return.s --root . -o build\native_load_dlx_then_return.bda
python reverse\native_bda_build.py reverse\examples\alloc_free_then_return.s --root . -o build\native_alloc_free_then_return.bda
python reverse\native_bda_build.py reverse\examples\hello_msgbox.s --root . -o build\HelloWorld_msgbox.bda
python reverse\bda_set_title.py build\HelloWorld_msgbox.bda -o build\HelloWorld_msgbox.bda --title HelloMsg
```

The current mini assembler supports a deliberately small MIPS32 little-endian
subset: `nop`, `jr`, `jalr`, `j`, `jal`, `lui`, `ori`, `addiu`, `lw`, `sw`,
`move`, `addu`, `la`, `.word`, `.ascii`, `.space`, `.align`, and `.asciiz`.

## GUI table offsets observed

`*(0x81c00004)` is the GUI/window/control table. These names are inferred from
bundled app call sites and should be verified on hardware:

```text
+0x1a4  create control/window
        a0 = class string such as "listbox" or "medit"
        a1 = caption/name string or zero
        a2 = style flags
        a3 = parent/extra, often zero
        stack +0x10/+0x14/+0x18/+0x1c/+0x20/+0x24/+0x28 carry geometry/id/parent fields

+0x2b8  message box
        a0 = parent/window handle, often zero
        a1 = message/body string
        a2 = title string
        a3 = flags/button mode, 0 for simple OK-style boxes and 2 for yes/no-style call sites

+0x40   send/set message/property on a control
        a0 = handle
        a1 = message/property id such as 0xf0dd or 0xf0c5
        a2/a3 = value/pointer depending on message id
```

`build\HelloWorld_msgbox.bda` currently tests `+0x2b8`.

## Menu title behavior

Hardware tests show that patching code behind the original calculator title is
accepted by the menu and runs. Patching only the title at header offset `0x2c`
can make the app disappear from the menu.

Confirmed header detail:

```text
header words 0x00..0x28 are decoded with 0x44525744
header word at 0x10 ^ 0x44525744 == file size
header word at 0x0c ^ 0x44525744 == category/menu group
header checksum: word[0x84] ^ 0x322d464b == byte_sum(decoded 0x00..0x2b + raw 0x2c..0x83)
```

Icon resources:

```text
decoded word 0x18: icon/resource start, usually 0x88
decoded word 0x1c: icon0 size, usually 0x3218 = 24 + 80*80*2
decoded word 0x20: icon1 size, usually 0x3218 = 24 + 80*80*2
decoded word 0x24: icon2 size, usually 0x16e0 = 24 + 54*54*2
decoded word 0x28: icon3 size, usually 0x1a60 = 24 + 58*58*2
```

Each icon chunk starts with `VX`, then a 24-byte header and little-endian
RGB565 pixels. `bda_extract_icons.py` exports these chunks to PNG,
`bda_copy_icons.py` copies icon chunks from another BDA, and
`bda_set_icon_png.py` builds the four icon chunks from an RGB/RGBA PNG.

One-shot builder:

```powershell
python reverse\bda_build.py `
  --template "应用\程序\计算器.bda" `
  --source reverse\examples\hello_msgbox_after_startup.s `
  --title ToolDemo `
  --category 0x09 `
  --icon-png build\custom_H_icon.png `
  --icon-background 14245c `
  -o build\ToolDemo_full_build.bda
```

This keeps the template container layout, patches the startup-called main
function, updates the menu title/category, generates all four VX icons, and
recomputes the header checksum.

Raw-binary path for external compilers:

```powershell
python reverse\bda_build.py `
  --template "应用\程序\计算器.bda" `
  --raw-bin build\app.bin `
  --title RawLoop `
  --category 0x09 `
  --icon-png build\custom_H_icon.png `
  -o build\RawLoop_full_build.bda
```

`bda_compile_c.py` wraps a future `mipsel-elf-gcc` or `mipsel-linux-gnu-gcc`
installation: it links `bda_main` at the template main address, extracts a raw
binary with `objcopy`, then calls `bda_build.py`.

Installed compiler path:

```text
tools\g++-mipsel-none-elf-15.2.0\bin\mipsel-none-elf-gcc.exe
```

`bda_compile_c.py` now auto-detects the bundled `tools\g++-mipsel-none-elf-*`
toolchain, so `--prefix` is optional.

C SDK example:

```powershell
python reverse\bda_compile_c.py reverse\examples\hello_msgbox.c `
  --template "应用\程序\计算器.bda" `
  --title CAuto `
  --category 0x09 `
  --icon-png build\custom_H_icon.png `
  --icon-background 14245c `
  -o build\CAuto_gcc.bda
```

The current C entry point is a freestanding function named `bda_main`.
`reverse\sdk\bda_sdk.h` exposes the confirmed message-box API as
`bda_msgbox(title, message)`.

The earlier disappearing-title/category tests were caused by stale or incorrect
header checksum/key handling. Hardware confirmed
`calc_title_HelloMsg_fix84_exact.bda` appears in the menu as `HelloMsg`.

## No-template packer

`bda_pack_minimal.py` builds a simple native BDA without copying an existing BDA
file as a template. It creates:

```text
0x0000..0x0087  native BDA header
0x0088..0x95f7  four VX icon chunks
0x95f8          native entry code, linked for VA 0x81c00020
```

The generated header keeps the confirmed original layout:

```text
decoded word 0x00 = 0x004b4242
decoded word 0x04 = 0x5d245562
decoded word 0x08 = 0x01000102
decoded word 0x0c = category
decoded word 0x10 = file size - 4
decoded word 0x14 = 0x95f8
decoded word 0x18 = 0x88
decoded word 0x1c/0x20/0x24/0x28 = VX icon sizes
checksum: word[0x84] ^ 0x322d464b == byte_sum(decoded header bytes 0x00..0x83)
```

The first test builds are:

```powershell
python reverse\bda_pack_minimal.py reverse\examples\hello_msgbox.s `
  --title NoTplAsm --category 9 -o build\NoTemplateHelloAsm.bda

python reverse\bda_pack_minimal.py reverse\examples\hello_msgbox.c `
  --title NoTplC --category 9 -o build\NoTemplateHelloC.bda
```

Static verification:

```text
build\NoTemplateHelloAsm.bda  size 0x9650, checksum ok, entry 0x95f8
build\NoTemplateHelloC.bda    size 0x9678, checksum ok, entry 0x95f8
```

Hardware result:

```text
NoTemplateHelloAsm.bda  appears in the menu and runs
NoTemplateHelloC.bda    appears in the menu and runs
```

This confirms the template dependency is not required for simple native apps.
`NoTemplateHelloAsm.bda` was the preferred first hardware test because its entry
starts with the same standard MIPS prologue shape seen in bundled BDAs:

```text
addiu sp, sp, -0x18
sw    ra, 0x10(sp)
```

`NoTemplateHelloC.bda` confirms the same from-scratch container also works with
GCC-generated code.

`bda_compile_c.py` now supports the no-template path directly:

```powershell
python reverse\bda_compile_c.py reverse\examples\hello_msgbox.c `
  --no-template `
  --title CNoTpl `
  --category 9 `
  -o build\CNoTemplateViaCompile.bda
```

Custom PNG icons are supported on both no-template entry points:

```powershell
python reverse\bda_pack_minimal.py reverse\examples\hello_msgbox.s `
  --title IconAsm `
  --category 9 `
  --icon-png build\custom_H_icon.png `
  --icon-background 14245c `
  -o build\NoTemplateIconAsm.bda

python reverse\bda_compile_c.py reverse\examples\hello_msgbox.c `
  --no-template `
  --title IconC `
  --category 9 `
  --icon-png build\custom_H_icon.png `
  --icon-background 14245c `
  -o build\NoTemplateIconC.bda
```

Static verification:

```text
build\NoTemplateIconAsm.bda  size 0x9650, checksum ok, custom VX icons export correctly
build\NoTemplateIconC.bda    size 0x9678, checksum ok, custom VX icons export correctly
```

Full C + no-template + custom icon smoke test:

```powershell
python reverse\bda_compile_c.py reverse\examples\notpl_demo_msgbox.c `
  --no-template `
  --title NoTplDemo `
  --category 9 `
  --icon-png build\custom_H_icon.png `
  --icon-background 14245c `
  -o build\NoTplDemo.bda
```

Hardware result:

```text
NoTplDemo.bda appears in the menu, shows the custom icon, and runs the GCC
message-box app.
```

Use the no-template path for simple standalone apps. Keep the template patch
path for apps that intentionally borrow a bundled app's richer GUI/window
lifecycle while those SDK pieces are still being reverse engineered.

## Next milestones

1. Move more example programs from template patching to no-template builds.
2. Add a no-template DLX/image display demo once the standalone GUI lifecycle is
   stable.
3. Decode the remaining system/API table offsets beyond the confirmed GUI and
   DLX calls.
4. Decode `Config.inf` registration for downloaded/extra apps.
