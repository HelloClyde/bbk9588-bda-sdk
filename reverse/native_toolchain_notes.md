# BBK 9588 Standalone BDA Toolchain

## Runtime model

- `kj409588.bin` 的 C200 payload 从文件偏移 `0x40` 开始，加载基址 `0x80004000`。
- BDA loader 从 header 指定的 file offset 读取程序体到固定 VA `0x81c00020`。
- `0x81c00000..0x81c0001f` 由固件填入 runtime table seeds。
- BDA 是 flat MIPS32 little-endian image，不是 ELF；loader 不处理 relocation。
- builder 将 `.bss` 作为零字节写进 flat image。

完整 header 和固件地址见 `reverse/docs/bda_header_notes.md`。

## Build

唯一构建入口：

```powershell
python -m bda_packer reverse\examples\hello_world_msgbox.c `
  --title HelloWorld `
  --category 9 `
  --icon-png path\to\icon.png `
  -o build\HelloWorld.bda
```

输入必须是定义 `bda_main()` 的 freestanding C。脚本使用 bundled
`mipsel-none-elf-gcc` / `objcopy`，链接地址固定为 `0x81c00020`，然后从零生成
header、四个 VX icon 和 flat code/data。

工具链没有基于原机 BDA 的构建、main 猜测、入口覆盖或 passthrough 功能。

## Validate

```powershell
python -m bda_packer.validate build\HelloWorld.bda
python -m unittest reverse.test_bda_header reverse.test_bda_validate reverse.test_sdk_examples
```

动态验证使用原版 NAND 的 frontend persistent worker copy，并只通过
`/api/files/import`、`/api/files/export`、`/api/files/delete` 操作文件。不要手工
制作 NAND，不要直接修改原版或运行中的 worker image。
