# DLX Resource Container 笔记

DLX 是系统 shell skin、应用美术资源和部分应用模块使用的简单 resource container。当前
扫描到的文件主要包含嵌入式 `VX` RGB565 图片或标准 BMP 文件。

## 文件头

已观察到的 DLX 都以以下布局开头：

```text
00  3 bytes  "DLX"
03  u8       resource count
04  u8       major/version byte，已见 1
05  u8       variant，已见 0 或 3
06  u16      reserved，已见 0
08  u32      stamp/constant，已见 0x19811108
0c  u32      header size / first resource file offset
```

variant 0：

```text
10  char[20] name/stamp string，常见 "Vrix 06/07/17 19:25"
24  resource table
```

variant 3：

```text
10  u32      payload size，等于 file_size - header_size
14  char[16] name string，常见 "Vrix.Ipona"
24  resource table
```

`variant 3` 在 `0x20..0x23` 有 4 个 reserved byte，之后才是 resource table。

## Resource Table

每个 resource table entry 12 byte：

```text
u32 type          已见图片资源为 1
u32 rel_offset    相对 header_size
u32 size          resource byte 长度
```

resource 在文件中的 absolute offset：

```text
file_offset = header_size + rel_offset
```

`dlx_inspect.py` / `dlx_extract.py` 用 0 基 `#index` 展示 table entry。原 BDA 中常见的
app-local `get_dlx_resource(resource_number, table)` helper 使用 1 基资源号：调用参数
`1` 对应工具报告的 `#00`，参数 `12` 对应 `#11`。分析应用调用点时必须先确认 helper
的编号规则，不能直接把调用参数当成工具输出的 index。

当前 dump 中 168 个 DLX 文件可以解析出 3580 个资源：

```text
VX   3509
BMP    71
```

## 资源载荷

### VX

`VX` 是未压缩 RGB565 图片资源：

```text
00  char[2] "VX"
02  4 bytes 通常为 cc cc cc cc
06  u32 width
0a  u32 height
0e  10 bytes padding/color-key-like 字段
18  RGB565 little-endian pixels，width * height * 2 byte
```

### BMP

部分较旧的 `variant 0` DLX 会直接嵌入普通 BMP 文件。例如：

```text
系统/数据/shell/sanjiao.dlx
应用/翻译/alltran.dlx
```

## 工具

检查 DLX：

```powershell
python reverse\dlx_inspect.py path\to\file.dlx
```

提取资源：

```powershell
python reverse\dlx_extract.py path\to\file.dlx -o build\dlx_extract
```

用已有 BMP/VX 资源构建简单 DLX：

```powershell
python reverse\dlx_build.py --resource image.bmp -o build\custom.dlx
```

把 PNG 转成 VX 后构建 DLX：

```powershell
python reverse\dlx_build.py --resource image.png:66:72 -o build\custom_icon.dlx
```

当前 builder 只生成简单 type-1 资源。这已经足够做图片资源实验；可执行模块式
DLX 行为仍需要单独逆向，不要把当前工具当作通用 DLX linker。
