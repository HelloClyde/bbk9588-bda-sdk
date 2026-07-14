# BBK 9588 BDA 逆向工具说明

本目录包含 BBK / 步步高 9588 原生 `*.bda` 应用格式、系统 API 表、资源文件
和构建工具链的逆向脚本。这里研究的是原生 BDA，不是 BB 虚拟机程序。

## 当前确认结论

- 原机应用位于 `应用\程序\*.bda`。
- 资源文件多为 `*.dlx`，文件头通常是 ASCII `DLX`。
- `*.bda` 不是 ELF，而是自定义 header + VX 图标资源 + MIPS32 little-endian
  代码/数据。
- 普通 standalone BDA 的入口文件偏移是 `0x95f8`，运行时 VA 是
  `0x81c00020`。
- `C200.bin` 加载基址按 `0x80004000` 处理。
- `C200.bin` 会把 API 表种子复制到 `0x81c00000`；原生 BDA 通过这些表调用
  GUI、FS、SYS、MEM、RES 等系统功能。
- BDA header 的 XOR 字段、文件大小、入口偏移、图标尺寸和 checksum 已集中到
  `reverse\bda_header.py`。
- 当前 C 工具链可以用 `mipsel-none-elf-gcc` 编译 freestanding `bda_main()`，
  再打包成 standalone BDA。

## 常用命令

安装/检查本地 MIPS 工具链：

```powershell
.\scripts\setup_toolchain.ps1
```

构建一个最小 C 消息框应用：

```powershell
python -m bda_packer reverse\examples\hello_msgbox.c `
  --title HelloC `
  --category 9 `
  -o build\HelloC.bda
```

验证 BDA header、入口和图标：

```powershell
python -m bda_packer.validate build\HelloC.bda
```

清点原机 BDA：

```powershell
python reverse\bda_inventory.py --root 应用\程序
```

生成中文 API 覆盖表：

```powershell
python reverse\bda_api_catalog.py
```

从 `C200.bin` 生成系统 API 表函数地址：

```powershell
python reverse\c200_api_tables.py --root . --json-out build\c200_api_tables.json
```

按 SDK 名称反汇编一个系统 API：

```powershell
python reverse\c200_api_disasm.py --name BDA_GUI_MSGBOX --size 0x80
python reverse\c200_api_disasm.py --table FS --offset 0x000 --size 0x120
```

输出会包含 API 表名、表内 offset、SDK 名称、函数 VA、`file_off` 和中文说明。
`file_off = 函数 VA - 0x80004000`，可直接和 `C200.bin` 静态切片对齐。

按原机 BDA 的缓存 table global 分类间接 API 调用，并输出调用点上下文：

```powershell
python reverse\bda_table_globals.py "应用\程序\雷霆战机.bda"
python reverse\bda_table_call_scan.py "应用\程序\雷霆战机.bda" `
  --table GUI `
  --offset 0x400 `
  --context
```

这组工具用于把原机调用点按 `GUI/FS/SYS/MEM/RES` 分类，避免只看裸 offset
误判 API 所属 table。`--context` 输出的 MIPS 反汇编可以直接补进 SDK 文档或
逐应用报告。

生成单个 BDA 的完整 SDK/C200 API 对照表：

```powershell
python reverse\bda_sdk_usage.py "fly-src-api\雷霆战机.bda" `
  --title "雷霆战机.bda" `
  -o sdk\doc\thunder_api_inventory.md
```

该工具保留 table 分类和调用次数，合并 `bda_sdk.h` 名称，并从 `C200.bin`
读取每个 entry 的 function VA。它适合生成逐应用的完整 API inventory；
high-level 源码函数和 lifecycle 解释仍应写在手工报告中。

扫描 C200 首页/menu/deploy 相关字符串：

```powershell
python reverse\c200_menu_scan.py --markdown reverse\reports\c200_menu_index_notes.md
```

该报告分别记录 `Config.inf` 字符串、`A:\应用\程序\*.bda` 字符串和首页硬编码
BDA 路径；字符串共存不表示 `Config.inf` 参与 BDA 菜单索引，也不要把报告当成完整
xref/call graph。

## 主要脚本

- `../bda_packer/`：独立的 BDA 编译、header、VX 图标和校验工具；这是唯一构建入口。
- `bda_compile_c.py` / `bda_header.py` / `bda_validate.py`：旧命令和逆向脚本的兼容转发。
- `bda_fix_header_checksum.py`：按固件公式修复 header checksum。
- `bda_deploy_bundle.py`：生成历史 deploy bundle；只研究文件复制和 Config.inf checksum，
  不作为 BDA app 注册或启动证据。
- `config_inf_add.py`：列出、追加或替换 `系统\数据\Config.inf` 文件自身的 slot；与 BDA 菜单无关。
- `config_inf_probe.py`：检查 `Config.inf` 文件自身的 slot、entry name 和 checksum。
- `bda_set_icon_png.py`：把 PNG 转成 BDA menu icon。
- `bda_copy_icons.py`：从已有 BDA 复制四个 VX icon block。
- `bda_extract_icons.py`：导出 BDA 内的 VX icon block。
- `bda_inventory.py`：清点原机应用标题、分类、入口和 API offset 热度。
- `bda_table_globals.py`：检测原机 BDA 缓存 runtime table pointer 的 global 地址。
- `bda_table_call_scan.py`：按 table global 分类间接 API 调用并输出 sample/context。
- `bda_game_framework_scan.py`：恢复原版游戏的根窗口过程、事件桥、frame 注册点和事件泵。
- `bda_sdk_usage.py`：生成单个 BDA 的 runtime table、SDK 名称和 C200 function 对照表。
- `bda_api_catalog.py`：合并 inventory 和 SDK header，生成中文 API 覆盖表。
- `c200_api_tables.py`：从 C200 API 表种子导出函数 VA。
- `c200_api_disasm.py`：快速反汇编 C200 中的 API 函数。
- `c200_menu_scan.py`：扫描 C200 首页/menu/deploy 字符串和保守 xref。
- `dlx_inspect.py`：检查 DLX resource container。
- `dlx_extract.py`：导出 DLX 内的 VX/resource payload。
- `dlx_build.py`：重建简单 DLX resource container。

## 文档入口

- `sdk\\doc\\README.md`：SDK 开发者入口。
- `sdk\\doc\\bda_header_notes.md`：BDA header 构造规则。
- `sdk\\doc\\api_catalog.md`：SDK 命名 API 与原机调用覆盖。
- `sdk\\doc\\system_api_tables.md`：C200 API 表函数地址。
- `sdk\\doc\\c200_api_function_notes.md`：关键 API 的函数级说明。
- `sdk\\doc\\window_notes.md`：窗口、控件和绘图生命周期。
- `sdk\\doc\\fs_notes.md`：文件系统 API。

## 使用边界

带 `_LIKE` 后缀的名称表示 ABI 或生命周期还没完全定名。它们可以用于探针和
实验性应用，但公开示例应优先使用已验证路径：

- `bda_msgbox()` / `BDA_GUI_MSGBOX`
- `bda_fs_*_raw()` 文件读写基础路径
- `bda_alloc()` / `bda_free()`
- standalone BDA header + VX 图标构造

新增脚本不要重复实现 header XOR/checksum，必须复用 `bda_header.py`。
