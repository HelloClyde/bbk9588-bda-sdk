# BBK 9588 原生 BDA SDK 与工具链

这是面向 BBK / 步步高 9588 学习机的实验性原生 `*.bda` SDK 和构建工具链。
仓库包含 BDA 文件格式、C200 系统 API、DLX 资源和硬件级 emu 的逆向记录。

当前已经覆盖：

- 原生 BDA 头部解码、构造和 checksum 修复
- 不依赖任何既有 BDA 的 standalone 打包
- 菜单标题、分类、图标生成
- DLX 资源检查、提取和重建
- freestanding MIPS little-endian C SDK 草案
- 文件系统、GUI、输入、文字、图片、音频等 API 探针
- C200 系统表到 SDK offset 的函数地址映射
- 能启动真实系统镜像的硬件级 emu 工作区
- 用于真机快速探测的 USB 大容量存储调试桥
- 原机内置 BDA 应用的逆向报告和清点表

## 目录结构

```text
reverse/                 Python 构建和逆向工具
reverse/examples/        freestanding C/ASM BDA 探针源码
reverse/docs/            未验证 API、候选 ABI 和探针研究记录
example/                 已动态验证的开发者 BDA 示例
bda_packer/              独立 BDA 编译、header、VX 图标和校验工具
emu/                     硬件级仿真器、Web 前端、hook、工具和测试
sdk/include/             已验证的稳定公开 API header
reverse/bda_research_sdk.h  未验证候选 API 研究头
docs/                    已验证 API 说明和开发教程
reverse/reports/         原机 BDA 清点表和应用报告
tools/                   工具链说明和本地安装/cache 位置
scripts/                 安装/辅助脚本
requirements.txt         Python 依赖
DATA_NOTICE.md           不应提交的数据说明
```

本地 dump 和生成物会被 `.gitignore` 排除：

```text
/系统/                    本地系统 dump，包含 C200.bin 等，禁止提交
/应用/                    本地应用/数据 dump，禁止提交
/build/                   生成的 BDA/DLX/探针/emu snapshot
tools/                    本地编译器、USB helper 等；解压产物禁止提交
```

## 当前状态

这是逆向研究代码。部分 API 已在真机确认；很多接口仍带 `_LIKE` 后缀，
表示 ABI、结构体布局或生命周期规则还没有完全证明。

真机或 C200 证据已经确认的要点：

- BDA 应用是 MIPS32 little-endian 原生代码，不是 ELF。
- 常见原生入口是文件偏移 `0x95f8`，运行时 VA `0x81c00020`。
- BDA 头部使用 XOR 编码字段和字节和 checksum。
- standalone C BDA 可以从零构建、出现在菜单并运行。
- `TouchStageV11.bda` 已在真机完成窗口创建、触摸坐标绘制、实时日志、退出并返回主菜单的完整闭环。
- 自定义菜单标题、分类和图标生成可用。
- DLX 是资源容器，图片资源常见 VX 块。
- `C200.bin` 会把 API 表种子复制到 `0x81c00000`，SDK 文档已导出表项函数 VA。

开发者示例见 [example/README.md](example/README.md)，SDK 入口见
[docs/README.md](docs/README.md)，工具链细节见
[reverse/native_toolchain_notes.md](reverse/native_toolchain_notes.md)。
当前 verify 覆盖和 `_LIKE` API 风险边界见
[reverse/docs/verification_notes.md](reverse/docs/verification_notes.md)。
硬件级 emu 在 [emu/](emu/)，其中文说明见 [emu/README.md](emu/README.md)。

## 安装

安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

如果要编译 C BDA，下载并解压 MIPS little-endian 工具链：

```powershell
.\scripts\setup_toolchain.ps1
```

它提供：

```text
mipsel-none-elf-gcc
mipsel-none-elf-objcopy
```

脚本会在本地没有缓存时下载 `g++-mipsel-none-elf-15.2.0.zip`。当前压缩包会
直接解到 `tools\bin\`；构建脚本也兼容旧的
`tools\g++-mipsel-none-elf-*\bin\` 布局。也可以传 `--prefix` 使用其他兼容
工具链。

## 构建最小原生 BDA

```powershell
python -m bda_packer example\basic\hello_world\hello_world_msgbox.c `
  --title HelloBDA `
  --category 9 `
  -o build\HelloBDA.bda
```

带自定义图标：

```powershell
python -m bda_packer example\basic\hello_world\hello_world_msgbox.c `
  --title IconDemo `
  --category 9 `
  --icon-png path\to\icon.png `
  --icon-background 14245c `
  -o build\IconDemo.bda
```

构建后先静态校验 BDA 头部、入口和图标区：

```powershell
python -m bda_packer.validate build\HelloBDA.bda
```

## 一键验证

快速验证工具链、header 构造、C200/API 文档生成和 SDK C 示例编译：
如果本地存在 `系统\数据\C200.bin`，C200 API 表生成失败会让 verify 失败，
不会被当作可忽略 warning。

```powershell
.\scripts\verify_sdk.ps1
```

同时运行 emu 前端启动 smoke：

```powershell
.\scripts\verify_sdk.ps1 -Emu
```

已安装 toolchain 且只想复跑验证时，可以跳过安装检查：

```powershell
.\scripts\verify_sdk.ps1 -SkipToolchainSetup -Emu
```

## BDA 启动测试

不要把 `Config.inf` 当成 BDA app 的有效注册机制。当前真机反馈显示它对 BDA
启动没有指导意义，也与内置 BDA 的扫描、category 分类、展示和菜单索引无关；
相关 reverse 工具只保留为历史文件格式分析，不作为 SDK 安装指南。

emu smoke 必须从原版 NAND 创建 frontend worker copy，再通过 `/api/files/import`
写入 standalone BDA。不要手工制作 NAND，也不要直接修改原版 NAND 或运行中的
worker 文件。文件变更后由 frontend 停机、checkpoint 和重启。

`TileBlit` probe 已经完成真机 A/B，结果是否定的：即使批量 blit 后只统一
present 一次，真机仍会逐块 flip，并在全部 tile 渲染后死机。它只保留为
ABI/build probe，不再作为推荐真机测试路径：

```powershell
python -m bda_packer reverse\examples\tile_blit_probe.c `
  --title TileBlit `
  --category 9 `
  -I reverse `
  -o build\TileBlit.bda

python -m bda_packer.validate build\TileBlit.bda
```

`TileBlit` 会在一次 guard 内批量 blit 8x6 个 16x16 RGB565 tile，然后统一
present。真机已确认这仍会逐块 flip 并死机，说明 `GUI+0x074/+0x400`
依赖原机游戏已经建立好的 surface/context 生命周期，不能直接作为游戏 SDK 示例。
不要把它当作完整 frame/window lifecycle 或可玩的扫雷。

## 固件/API 文档生成

本地有 `系统/数据/C200.bin` 后，可以生成 C200 API 表函数地址文档：

```powershell
python reverse\c200_api_tables.py --root .
```

输出文档：

```text
reverse/docs/system_api_tables.md
```

从原机 BDA 清点和 SDK header 生成 API 覆盖表：

```powershell
python reverse\bda_api_catalog.py
```

输出文档：

```text
reverse/docs/api_catalog.md
```

## 检查 BDA 和 DLX

```powershell
python reverse\bda_probe.py path\to\calculator.bda
python reverse\bda_disasm_preview.py path\to\calculator.bda --count 80
python reverse\dlx_inspect.py path\to\text_A.dlx
python reverse\dlx_extract.py path\to\text_A.dlx -o build\text_A_extract
```

## USB 调试桥

构建常驻调试桥：

```powershell
python -m bda_packer reverse\examples\usb_debug_bridge.c `
  --title UsbDebug `
  --category 9 `
  -o build\UsbDebugBridge.bda
```

把它复制到设备应用目录，在设备上运行，然后用主机端 helper 通信：

```powershell
python tools\usb_debug_host.py --drive F: --tail
python tools\usb_debug_host.py --drive F: -c status
python tools\usb_debug_host.py --drive F: -c "msg hello"
python tools\usb_debug_host.py --drive F: -c quit
```

详见 [reverse/docs/usb_debug_notes.md](reverse/docs/usb_debug_notes.md)。

## 发布注意事项

推送前检查：

```powershell
git status --short
```

应该只看到源码、脚本和文档变更。原始固件/应用 dump、普通构建生成的 BDA/DLX、
下载的工具链压缩包和解压后的工具链目录都应保持 ignored。唯一例外是
`example/**/*.bda`：这些已验证预编译示例会随源码一同提交。详见
[DATA_NOTICE.md](DATA_NOTICE.md)。

## License

尚未选择许可证。接受外部贡献或重新分发大量代码前，应先添加 `LICENSE`。
