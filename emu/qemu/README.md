# QEMU `bbk9588` Machine

模拟器使用自定义 QEMU `bbk9588` MIPS system machine。仓库不包含完整 QEMU 源码，只保存：

```text
emu/qemu/source-overlay/              完整修改后的覆盖文件
emu/qemu/patches/qemu-v11.0.0-bbk9588.patch
```

目标 QEMU 版本：

```text
QEMU 11.0.0
```

## 安装 Overlay

把 overlay 复制进一个干净 QEMU checkout：

```powershell
python .\emu\qemu\scripts\install_qemu_overlay.py --qemu-source E:\qemu-src
```

检查 checkout 是否已经匹配 overlay：

```powershell
python .\emu\qemu\scripts\install_qemu_overlay.py --qemu-source E:\qemu-src --check
```

也可以使用 patch：

```powershell
python .\emu\qemu\scripts\apply_qemu_patch.py --qemu-source E:\qemu-src --check
python .\emu\qemu\scripts\apply_qemu_patch.py --qemu-source E:\qemu-src
```

## Windows 构建

安装 MSYS2 UCRT64 依赖后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\qemu\scripts\build_qemu_windows.ps1 `
  -QemuSource E:\qemu-src `
  -BuildDir E:\qemu-src\build-bbk9588-win `
  -UseOverlay
```

脚本会在缺少 `build.ninja` 时运行 QEMU configure，然后构建：

```text
E:\qemu-src\build-bbk9588-win\qemu-system-mipsel.exe
```

Release workflow 会把它复制并改名为：

```text
bin/bbk9588-qemu-system-mipsel.exe
```

## 前端集成

开发环境启动：

```powershell
python -m emu.web.frontend `
  --boot-mode uboot `
  --qemu E:\qemu-src\build-bbk9588-win\qemu-system-mipsel.exe
```

release 包启动脚本会显式传入：

```text
bin/bbk9588-qemu-system-mipsel.exe
```

## 模型范围

`hw/mips/bbk9588.c` 当前负责：

- RAM 与 firmware 加载。
- LCD/frame chardev。
- input chardev。
- NAND/MSC/FTL 相关存储行为。
- timer、interrupt、GPIO/SADC touch 状态。
- 兼容性诊断寄存器和 machine property。

patch 还包含少量 `target/mips` 侧 instrumentation/helper，用于当前 machine model 和诊断。
