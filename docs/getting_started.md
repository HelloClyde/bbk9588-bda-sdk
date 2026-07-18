# 入门教程

本教程在 Windows PowerShell 下构建一个独立 BDA。当前 CI 使用 Python 3.12；工具本身
支持 Python 3.10 或更高版本。

## 1. 安装

```powershell
git clone --recurse-submodules https://github.com/HelloClyde/bbk9588-bda-sdk.git
cd bbk9588-bda-sdk
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
.\scripts\setup_toolchain.ps1
```

安装脚本下载 MIPS little-endian GCC 15.2.0，并在解压前校验仓库中固定的 SHA-256。
如果已有兼容工具链，可跳过脚本并设置：

```powershell
$env:BDA_TOOLCHAIN_PREFIX = "C:\toolchains\mips\bin\mipsel-none-elf-"
```

## 2. 编写程序

创建一个定义 `bda_main()` 的 freestanding C 文件：

```c
#include "bda_dialogs.h"

__attribute__((section(".text.bda_main")))
int bda_main(void)
{
    bda_msgbox("HelloWorld", "Hello from BDA");
    return 0;
}
```

BDA 不链接宿主 `stdio.h` 或常规 C runtime。系统能力由固件启动时放入固定位置的动态
函数表提供，公开 wrapper 已封装在 `sdk/include/` 中。

## 3. 构建和校验

仓库自带同等的最小源码，可以直接构建：

```powershell
bda-pack example\basic\hello_world\hello_world_msgbox.c `
  --title HelloWorld --category 9 `
  -o build\HelloWorld.bda

bda-validate build\HelloWorld.bda
```

标题经 GBK 编码后最多 16 字节。`--category 4` 是娱乐天地，`--category 9` 适合一般
测试程序。使用 `--icon-png` 可以生成四个固件要求的 VX 图标尺寸。

未安装命令行入口时，对应命令为：

```powershell
python -m bda_packer --help
python -m bda_packer.validate --help
```

## 4. 模拟器测试

先安装独立的 `bbk9588-emulator-v0.1.5`，然后指定其目录：

```powershell
$env:BBK9588_EMULATOR_ROOT = "E:\bbk9588-emulator-v0.1.5"
.\scripts\test_bda_in_emulator.ps1 .\build\HelloWorld.bda -ResetImage
```

脚本使用端口 8013，把 BDA 写入专用 `runtime\bda_test` NAND 副本中的“宠物单词”
入口。它不会修改原始 NAND。`-ResetImage` 用原始压缩包重新创建测试副本，适合排除
前一个程序留下的运行状态。

## 5. 选择 API

从 [开发文档索引](README.md) 选择公开头和示例，并先阅读对应 API 的生命周期。
模拟器通过不代表真机已经验证；兼容情况见 [兼容性矩阵](compatibility.md)。固定函数
地址、带 `_LIKE` 的候选接口和 `reverse/` 头文件不得用于要发布的程序。
