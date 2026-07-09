# 固件与运行时镜像

公开仓库不发布固件、NAND 镜像或商业应用资源。用户和开发者需要自行准备本地 dump。

## 本地目录约定

从仓库根目录或 release 包根目录看，应放置：

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

Python 启动器会在工作区中查找 `C200.bin` 和 `u_boot_9588_4740.bin`。如果路径包含中文，
启动器会把 payload 复制到 `build/qemu_payloads/`，避免 Windows 下 QEMU 命令行路径处理
不稳定。

## 构建 FAT 与 NAND

推荐使用 wrapper：

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\tools\build_runtime_images.ps1
```

等价的手动步骤：

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

前端默认使用最终的 `_ftloob` 镜像：

```text
build/bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin
```

## 运行时写入策略

QEMU 前端会把源 NAND 镜像复制到：

```text
build/qemu_nand_runs/
```

普通前端会话不会直接修改 `build/` 下的源镜像。

## 发布规则

不要提交：

- `系统/`
- `应用/`
- `build/`
- `*.bin`
- `*.bda`
- `*.dba`
- `*.dlx`
- 批量截图、trace、完整反汇编和临时分析输出

`.gitignore` 已排除这些路径和扩展名。
