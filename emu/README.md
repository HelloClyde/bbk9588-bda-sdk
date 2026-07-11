# BBK 9588 硬件模拟器

`emu/` 是 BBK 9588 的 QEMU system emulation 实现。目标是让真实系统镜像在自定义
`bbk9588` machine 上运行，并通过本地 Web 前端显示 LCD、发送触摸和按键事件。

公开仓库和 release 包不包含固件、NAND 镜像或应用资源。所有 `系统/`、`应用/`、
`build/` 下的数据都应保持本地化。

## 用户路径：下载 release 包

Release 包中已经包含：

- `bin/bbk9588-qemu-system-mipsel.exe` 和 QEMU runtime DLL。
- `start-web.cmd` / `start-web.ps1`。
- Web 前端 `emu/web/`。
- NAND/FAT 镜像构建工具 `emu/tools/`。
- GitHub Actions 构建时附带的 `python/` runtime。

把本地 dump 放在 release 包根目录：

```text
系统/
  数据/
    loader_9588_4740.bin
    C200.bin
    kj409588.bin
    u_boot_9588_4740.bin
应用/
```

`loader_9588_4740.bin`、`u_boot_9588_4740.bin`、`kj409588.bin` 和 `应用/` 用于首次构建
runtime NAND。默认启动链路是 QEMU BootROM 从 NAND address `0` 按 JZ4740 spare valid flag
读取最多 8 KiB loader，并跳到 internal SRAM `0x80000004`，
再由 loader/U-Boot 通过 FAT/FTL 读取 `系统/数据/kj409588.bin` 并进入系统固件；
不会再把外部 U-Boot、C200 或 `kj409588.bin` 作为 RAM payload 预加载。然后双击 `start-web.cmd`，
或运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-web.ps1
```

浏览器入口：

```text
http://127.0.0.1:8000/
```

## 开发路径：源码仓库运行

安装 Python 依赖：

```powershell
python -m pip install -r requirements.txt
```

准备本地 dump：

```text
系统/
  数据/
    loader_9588_4740.bin
    C200.bin
    kj409588.bin
    u_boot_9588_4740.bin
应用/
```

构建 runtime NAND：

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\tools\build_runtime_images.ps1
```

构建或指定自定义 QEMU 后启动 Web 前端：

```powershell
python -m emu.web.frontend `
  --host 127.0.0.1 `
  --port 8000 `
  --boot-mode nand `
  --nand-image .\runtime\bbk9588_nand.bin `
  --qemu E:\qemu-src\build-bbk9588-win\qemu-system-mipsel.exe
```

## 目录结构

```text
emu/
  app.py                         Web 前端快捷入口
  qemu_app.py                    QEMU 命令行 probe / dry-run 入口
  core/                          framebuffer、PNG 等共享工具
  web/                           本地 HTTP/WebSocket 前端
  tools/                         FAT/NAND 镜像、runtime 收集、release 校验工具
  packaging/                     release 包根目录脚本和 README 模板
  docs/                          架构、镜像、开发流程文档
  test/                          单元测试和 Web smoke 脚本
  qemu/
    system.py                    QEMU 进程后端、命令构建、监控和设备交互
    source-overlay/              覆盖到 QEMU 11.0.0 的修改源码
    scripts/                     QEMU overlay/build 脚本
```

更多说明：

- [docs/architecture.md](docs/architecture.md)：模拟器组件边界。
- [docs/images.md](docs/images.md)：本地 dump 与 NAND/FAT 镜像。
- [docs/development.md](docs/development.md)：代码规范、测试和发布检查。
- [qemu/README.md](qemu/README.md)：QEMU overlay 和 Windows 构建。

## 构建 QEMU

源码仓库不 vendoring 完整 QEMU 树，只保存 overlay。当前目标版本：

```text
QEMU 11.0.0
```

本地构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\qemu\scripts\build_qemu_windows.ps1 `
  -QemuSource E:\qemu-src `
  -BuildDir E:\qemu-src\build-bbk9588-win `
  -UseOverlay
```

GitHub Actions release workflow 会自动下载 QEMU 11.0.0、应用 overlay、构建
`qemu-system-mipsel.exe`，并在 release 包中改名为：

```text
bin/bbk9588-qemu-system-mipsel.exe
```

## 打包与发布

本地打包源码 profile：

```powershell
powershell -ExecutionPolicy Bypass -File .\emu\tools\package_emulator.ps1 -Version emu-local
```

GitHub release 包由 `.github/workflows/release-emulator.yml` 生成。触发方式：

- push tag：`emu-v*` 或 `v*`
- workflow 进入默认分支后，也可以手动运行 `Release emulator`

打包完成后会生成：

```text
build/dist/bbk9588-emulator-版本.zip
build/dist/bbk9588-emulator-版本.zip.sha256
```

release runtime 包会用校验脚本检查结构：

```powershell
python .\emu\tools\validate_release_package.py .\build\dist\bbk9588-emulator-版本.zip --runtime
```

## 当前状态

QEMU/C200 运行路径已经能进入系统 UI，支持 framebuffer 输出、Web 前端触摸/按键输入，
并能打开多个内置应用。默认路径已经改为 BootROM -> loader (`0x80000004`) -> U-Boot -> FAT/FTL ->
`kj409588.bin`；旧的 BootROM 直接读取 FAT `C200.bin` 路径只作为显式 legacy 诊断选项保留。
Web 前端固定使用 `runtime/bbk9588_nand.bin`，不再暴露本机镜像切换控件。右侧
“文件”标签可离线管理 checkpoint 中的 FAT 文件，支持新建目录、导入、导出、改名
和删除。写操作会先停止并提交当前 NAND，完成后自动重启 QEMU。仍在推进的部分：

- NAND/FTL/FAT/cache 路径仍需继续靠硬件模型完善。
- U-Boot 冷启动路径需要继续优化 QEMU C NAND data port 性能和真机 OOB 元数据匹配。
- 部分主菜单资源渲染路径仍有兼容性问题。
- 诊断 machine property 和 TCG helper 仍保留在 QEMU overlay 中，但默认运行路径不应依赖
  Python/GDB 固件 hook。
