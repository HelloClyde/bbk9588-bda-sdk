# BBK 9588 模拟器 Runtime 包

这是 Windows 版 BBK 9588 QEMU system emulator 的下载运行包。

## 包内包含

- `bin/bbk9588-qemu-system-mipsel.exe` 和运行所需 DLL。
- 根目录启动脚本：`start-web.cmd`、`start-web.ps1`。
- Web 前端：`emu/web/`。
- 镜像构建与运行工具：`emu/tools/`。
- GitHub Actions 构建时会附带 `python/` runtime。

## 启动

双击：

```text
start-web.cmd
```

或在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-web.ps1
```

浏览器入口：

```text
http://127.0.0.1:8000/
```

## 必需的本地数据

公开 release 不包含固件、NAND 镜像、BDA 应用或商业资源。请把你自己的本地 dump 放到
`start-web.ps1` 同级目录：

```text
系统/
  数据/
    C200.bin
    u_boot_9588_4740.bin
应用/
```

首次启动时脚本会自动生成：

```text
build/bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin
```

强制重建镜像：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-web.ps1 -RebuildImages
```

修改端口或追加前端参数：

```powershell
powershell -ExecutionPolicy Bypass -File .\start-web.ps1 -Port 8010 --no-auto-calibration
```

## 故障排查

- 提示缺少 NAND 镜像：确认 `系统/数据/C200.bin` 和 `应用/` 已放在包根目录。
- 端口被占用：使用 `-Port 8010` 换端口。
- 不想自动打开浏览器：加 `-NoOpenBrowser`。
