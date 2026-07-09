# Firmware and Runtime Images

The repository intentionally does not publish dumped firmware, NAND images, or
commercial application resources. Keep those files local and ignored by Git.

## Expected Local Layout

From the repository root:

```text
系统/
  数据/
    C200.bin
    u_boot_9588_4740.bin
  ...
应用/
  程序/
    *.bda
  ...
```

The Python launchers search the workspace for `C200.bin` and
`u_boot_9588_4740.bin`. Non-ASCII paths are copied into
`build/qemu_payloads/` before QEMU launch because QEMU command-line path
handling is more reliable with ASCII paths on Windows.

## Build FAT and NAND Images

Use the wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\tools\build_runtime_images.ps1
```

Manual equivalent:

```powershell
python .\emu\tools\make_fat16_image.py `
  --output .\build\bbk9588_fat_page1c40.img `
  .\系统 .\应用

python .\emu\tools\make_combined_nand.py `
  --base-nand .\系统\数据\C200.bin `
  --fat-image .\build\bbk9588_fat_page1c40.img `
  --output .\build\bbk9588_nand_c200_fat_page1c40.bin `
  --fat-page-base 0x1c40

python .\emu\tools\stamp_ftl_oob.py `
  .\build\bbk9588_nand_c200_fat_page1c40.bin `
  .\build\bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin `
  --fat-page-base 0x1c40
```

The final `_ftloob` image is the one used by the QEMU frontend by default.

## Runtime Copy Behavior

QEMU receives a writable copy of the NAND image under
`build/qemu_nand_runs/`. The source image in `build/` is not mutated during a
normal frontend session.

## GitHub Publishing Rule

Do not commit:

- `系统/`
- `应用/`
- `build/`
- `*.bin`
- `*.bda`
- generated screenshots or traces

The `.gitignore` already excludes these paths and extensions.
