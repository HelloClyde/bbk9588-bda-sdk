# DLX resource container notes

DLX files are simple resource containers used by shell skins, app artwork, and
some app modules. The files scanned so far contain embedded `VX` RGB565 images
or standard BMP files.

## Header

All observed files start with:

```text
00  3 bytes  "DLX"
03  u8       resource count
04  u8       major/version byte, observed 1
05  u8       variant, observed 0 or 3
06  u16      reserved, observed 0
08  u32      stamp/constant, observed 0x19811108
0c  u32      header size / first resource file offset
```

Variant 0:

```text
10  char[20] name/stamp string, often "Vrix 06/07/17 19:25"
24  resource table
```

Variant 3:

```text
10  u32      payload size, equal to file_size - header_size
14  char[16] name string, often "Vrix.Ipona"
24  resource table
```

`variant 3` has four reserved bytes at `0x20..0x23` before the table.

## Resource table

Each resource table entry is 12 bytes:

```text
u32 type          observed 1 for image resources
u32 rel_offset    relative to header_size
u32 size          resource byte length
```

The absolute resource file offset is:

```text
file_offset = header_size + rel_offset
```

Across 168 DLX files in this dump, 3580 resources parsed cleanly:

```text
VX   3509
BMP    71
```

## Resource payloads

### VX

`VX` is an uncompressed RGB565 image resource:

```text
00  char[2] "VX"
02  4 bytes usually cc cc cc cc
06  u32 width
0a  u32 height
0e  10 bytes padding/color-key-looking fields
18  RGB565 little-endian pixels, width * height * 2 bytes
```

### BMP

Some older `variant 0` DLX files embed normal BMP files directly. Examples:

```text
系统/数据/shell/sanjiao.dlx
应用/翻译/alltran.dlx
```

## Tools

Current tools:

```powershell
python reverse\dlx_inspect.py path\to\file.dlx
python reverse\dlx_extract.py path\to\file.dlx -o build\dlx_extract
```

Build a simple DLX from existing BMP/VX resources:

```powershell
python reverse\dlx_build.py --resource image.bmp -o build\custom.dlx
```

Build a DLX with PNG converted to VX:

```powershell
python reverse\dlx_build.py --resource image.png:66:72 -o build\custom_icon.dlx
```

This builder currently emits simple type-1 resources. That is enough for image
resource experiments; executable/module-like DLX behavior still needs separate
reverse engineering.
