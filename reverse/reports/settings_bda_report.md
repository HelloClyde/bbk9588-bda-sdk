# Settings BDA report

Target: `应用/程序/系统设置.bda`

Generated evidence:

- `reverse/reports/settings_layout.json`
- `reverse/reports/settings_calls.txt`
- `reverse/reports/settings_fs_context.txt`
- `reverse/reports/settings_fs048_context.txt`
- `reverse/reports/settings_gui3f8_context.txt`
- `reverse/reports/settings_media.txt`
- `reverse/reports/settings_dlx.txt`

## Header and layout

```text
title              系统设置
category           0x09
file size          556140 bytes
entry offset       0x95f8
runtime entry VA   0x81c00020
runtime file base  0x81bf6a28
BSS/global range   0x81c7e690..0x81c7fa61
checksum           ok in inventory
```

Runtime table globals:

```text
RES 0x81c7e690
GUI 0x81c7e694
SYS 0x81c7e698
FS  0x81c7e69c
MEM 0x81c7e6a0
```

## External resources

The BDA references five shell resources:

```text
\shell\SysSet.dlx
\shell\SysSetnew.dlx
\shell\sysset_skin.dlx
\shell\sysset_add_blue.dlx
\shell\sysset_add_black.dlx
```

All are present under `应用/数据/shell`. `dlx_inspect.py` reports that every
resource entry in these files is type 1 VX RGB565 image data.

Important packages:

```text
SysSet.dlx / SysSetnew.dlx
  29 VX images
  includes 240x320 full-screen backgrounds, 197x153 panels, 139x59 buttons

sysset_skin.dlx
  2 VX images
  both 240x320

sysset_add_blue.dlx / sysset_add_black.dlx
  3 VX images
  240x30 and 240x25 list/status strips
```

This strengthens the current DLX model: production UI skins are ordinary DLX
containers full of VX images.

## API usage summary

Classified indirect calls:

```text
GUI      777
FS        98
MEM      123
RES       28
SYS        4
UNKNOWN    5
total   1001
```

Hot offsets:

```text
GUI +0x3f8  58
GUI +0x400  44
GUI +0x0f4  58
GUI +0x0e4  49
GUI +0x0e8  44
GUI +0x4f0  30
FS  +0x048  17
FS  +0x000/+0x004/+0x008/+0x00c/+0x010/+0x014
FS  +0x03c/+0x040/+0x044
MEM +0x008/+0x00c
RES +0x090/+0x094
SYS +0x080/+0x09c
```

Settings is mostly a GUI/storage/configuration app. It does not provide strong
audio/video ABI evidence, but it is one of the best current sources for storage
status and skinned settings pages.

## Disk/storage information

`FS +0x048` is called 17 times. The call shape is stable:

```text
a0 = 0
a1 = caller-owned info struct
return = status-like
```

Immediately after the call, the app multiplies three words:

```text
word(info+0x04) * word(info+0x08) * word(info+0x0c)
```

Examples:

```text
0x81c00a6c: FS+0x048(0, sp+0x30)
  uses sp+0x34, sp+0x38, sp+0x3c

0x81c02fa0: FS+0x048(0, sp+0x230)
  uses sp+0x234, sp+0x238, sp+0x23c
  compares total against 0x200000

0x81c03254: FS+0x048(0, sp+0x28)
  uses sp+0x2c, sp+0x30, sp+0x34
```

This pins `FS +0x048` as a disk/storage information helper. The structure is
probably FAT-like, with fields such as bytes-per-sector, sectors-per-cluster,
and cluster count or free-cluster count. Exact field names still need a probe
that prints the returned words on hardware.

## File-system behavior

Settings uses the standard FS group:

```text
FS +0x000  fopen-like
FS +0x004  fclose-like
FS +0x008  fread-like
FS +0x00c  fwrite-like
FS +0x010  fseek-like
FS +0x014  ftell-like
FS +0x024  remove-like
FS +0x02c  directory exists/chdir-like
FS +0x030  mkdir-like
FS +0x03c  findfirst-like
FS +0x040  findnext-like
FS +0x044  findclose-like
FS +0x048  disk-info-like
FS +0x07c  storage-ready-like
```

The app uses file reads/writes for configuration data and scans files by
extension:

```text
.bmp
.jpg
.wav
.wma
.mp3
```

This cross-checks the file selector/media-extension behavior seen in Album,
Music, Recorder, and Ebook.

## GUI behavior

Settings uses many complete event loops:

```text
GUI +0x030  poll-like
GUI +0x050  step-like
GUI +0x054  dispatch-like
GUI +0x17c  destroy/close-like
```

`GUI +0x3f8` appears 58 times. Typical calls:

```text
a0 = destination/surface
a1 = source/resource pointer
a2 = width-like, often 0x27 or 0x28
a3 = height-like, often 0x10..0x12
sp+0x10 = buffer/style pointer
```

The caller often inverts a small output buffer byte-by-byte right after the
call, suggesting `GUI +0x3f8` is an image/text-to-buffer or bitmap-copy helper
used for highlighted/disabled settings items. It should stay provisional until
compared with games and system code.

The app also uses the established text and color helpers:

```text
GUI +0x338/+0x33c/+0x378/+0x4f0
```

## Cross-checks

- Confirms `FS +0x048` disk-info semantics more strongly than previous apps.
- Confirms `FS +0x03c/+0x040/+0x044` directory enumeration in a settings UI.
- Confirms `RES +0x094` is logging/trace-like, not DLX loading.
- Confirms DLX UI skins are VX-only packages.

## Open questions

- Name each field returned by `FS +0x048`.
- Determine whether `GUI +0x3f8/+0x400` are image buffer conversion, masked
  blit, or disabled-item rendering helpers.
- Map the configuration files/settings records written through `FS +0x00c`.
