# BBK 9588 Native BDA SDK 与硬件模拟器

这是一个面向步步高 / BBK 9588 学习机的逆向研究项目，包含两条主线：

- 原生 `*.bda` 应用格式、DLX 资源格式、系统 API 和实验性 MIPS SDK。
- 基于 QEMU system emulation 的硬件模拟器，用真实系统镜像启动 Web 前端。

项目仍处于研究阶段。公开仓库只保存源码、脚本、文档和可复现的补丁；固件、NAND
镜像、原始 BDA/DLX 资源和设备 dump 不应提交。

## 当前能力

- 解码 BDA 头部、修复校验和、生成无模板原生 BDA。
- 构建 MIPS little-endian C/ASM 示例程序。
- 检查、提取和重建 DLX/VX 资源。
- 维护硬件验证过的文件系统、GUI、输入、文本、图像和资源调用笔记。
- 用自定义 QEMU `bbk9588` machine 启动真实系统镜像，并通过本地 Web 前端交互。
- 通过 GitHub Actions 构建 Windows runtime release 包。

## 目录结构

```text
emu/                     QEMU 硬件模拟器、Web 前端、镜像工具、发布脚本
reverse/                 BDA/DLX 逆向、SDK 实验、硬件探针和分析工具
reverse/examples/        原生 C/ASM BDA 示例
reverse/sdk/             实验性 SDK 头文件与 API 笔记
reverse/reports/         人工整理后的逆向报告
scripts/                 仓库级辅助脚本
tools/                   工具链说明和本地工具缓存位置
.github/workflows/       CI / release workflow
DATA_NOTICE.md           数据和版权边界
CONTRIBUTING.md          贡献约定
```

本地研究数据会被 `.gitignore` 排除：

```text
系统/                    本地设备系统 dump
应用/                    本地设备应用/resource dump
build/                   生成的镜像、BDA、截图、release 包和临时文件
tools/g++-.../           本地解压的交叉编译器
```

## 快速开始

安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

构建原生 BDA 需要 MIPS little-endian 工具链：

```powershell
.\scripts\setup_toolchain.ps1
```

构建一个最小 BDA：

```powershell
python reverse\bda_compile_c.py reverse\examples\hello_msgbox.c `
  --no-template `
  --title HelloBDA `
  --category 9 `
  -o build\HelloBDA.bda
```

检查 BDA/DLX：

```powershell
python reverse\bda_probe.py path\to\calculator.bda
python reverse\bda_disasm_preview.py path\to\calculator.bda --count 80
python reverse\dlx_inspect.py path\to\text_A.dlx
```

## 模拟器

模拟器位于 [emu/](emu/)，入口说明见 [emu/README.md](emu/README.md)。

开发者常用命令：

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\tools\build_runtime_images.ps1
python -m emu.web.frontend --boot-mode uboot --qemu E:\qemu-src\build-bbk9588-win\qemu-system-mipsel.exe
```

Release 包由 `.github/workflows/release-emulator.yml` 构建。包内包含编译好的
`bin/bbk9588-qemu-system-mipsel.exe`、QEMU 运行 DLL、Web 前端、启动脚本和
Python runtime。公开 release 不包含固件和应用资源，用户需要自行提供本地 dump。

## 质量检查

提交前至少运行：

```powershell
python -m py_compile (Get-ChildItem emu -Filter *.py -Recurse).FullName
git diff --check
git status --short
```

发布包结构可以用脚本校验：

```powershell
python .\emu\tools\validate_release_package.py .\build\dist\bbk9588-emulator-版本.zip --runtime
```

## 发布边界

请不要提交：

- `系统/`、`应用/`、`build/`
- 原始固件、NAND 镜像、BDA、DBA、DLX、字典库、音频和图片资源
- 下载的工具链压缩包或解压目录
- 自动生成的长日志、反汇编全文、截图和临时 trace

更多说明见 [DATA_NOTICE.md](DATA_NOTICE.md)。

## License

本项目尚未选择统一开源许可证。QEMU overlay 中保留了上游文件原有的 GPL/LGPL/MIT
许可证头。正式接收外部贡献或重新分发大规模代码前，需要补充仓库级 `LICENSE`。
