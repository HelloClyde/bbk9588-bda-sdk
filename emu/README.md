# BBK 9588 硬件级仿真器

`emu/` 是 BBK 9588 项目的硬件级仿真器目录。它的目标不是模拟某个
BDA API，也不是运行 BB 虚拟机程序，而是加载真实系统镜像，模拟 CPU、
内存、NAND、LCD、GPIO、触摸、按键、中断等硬件行为，让固件按真实设备
的路径启动和运行。

当前主要用户是中文用户，所以本目录文档以中文为准。

## 当前状态

目前仿真器已经可以通过本地 Web 后端启动真实 `C200.bin`，配合合成 NAND
镜像完成触摸校准、关闭时间变更对话框，并到达 240x320 竖屏主菜单。

当前回归测试只走 Web 后端：

```powershell
python .\emu\test\run_hwemu_regressions.py
```

这条路径会启动 `emu/app.py`，通过 HTTP 和 WebSocket 发送命令、接收状态
和帧数据，尽量贴近用户在浏览器里使用仿真器的方式。

## 目录结构

```text
emu/
  app.py                      应用入口；启动本地 Web 前后端
  core/                       仿真器核心
    core.py                   Bbk9588HwEmu 主类、内存映射、运行循环集成
    defs.py                   常量、数据类、地址表
    framebuffer.py            RGB565 扫描、方向转换、PNG/PPM 编码
  hooks/                      Unicorn hook、设备模型、快速路径和状态处理
    engine.py                 执行 hook、内存 hook、异常恢复、run loop
    devices.py                NAND/SADC/LCD/UART/GPIO/INTC 等 MMIO 设备模型
    fastpaths.py              等价快速路径，避免热点循环逐指令执行
    hook_policy.py            fast hook 选择策略
    input.py                  触摸、按键、BDA 事件等输入建模
    interrupts.py             TCU/周期中断、IRQ 挂起和 WAIT 服务
    state.py                  checkpoint 保存/加载和诊断快照
    surface.py                固件 surface/LCD 镜像和绘制加速
    tasks.py                  任务表、调度器状态和任务切换诊断
    trace.py                  trace 事件、PC 命中和调用记录
  web/                        HTTP/WebSocket 前端层
    frontend.py               前端服务启动、HTML 页面和参数解析
    frontend_server.py        HTTP API、WebSocket 连接和请求分发
    frontend_state.py         长生命周期仿真实例、后台 worker、输入队列、帧缓存
    frontend_ws.py            WebSocket 帧编码/解码工具
  tools/                      工具脚本和通用工具
    utils.py                  解析、地址转换、文件查找等通用 helper
    make_fat16_image.py       从本地文件树生成 FAT16 镜像
    make_combined_nand.py     将 C200/NAND 基础镜像与 FAT 区组合
    stamp_ftl_oob.py          写入最小 FTL OOB 标记
    inspect_combined_nand_fat.py  检查合成 NAND 中的 FAT 区
  test/                       Web 后端回归和 smoke 测试
    run_hwemu_regressions.py  统一回归入口，只通过 HTTP/WS 测试
    run_frontend_web_smoke.py 浏览器式 HTTP/WS smoke
    run_album_web_smoke.py    Album 应用 smoke
    run_thunder_web_smoke.py  Thunder 应用 smoke
```

## 快速启动

安装依赖：

```powershell
python -m pip install -r requirements.txt
python -m pip install unicorn capstone
```

启动本地 Web 仿真器：

```powershell
python .\emu\app.py --host 127.0.0.1 --port 9588
```

然后打开：

```text
http://127.0.0.1:9588/
```

如果已经有合成 NAND 镜像，可以显式指定：

```powershell
python .\emu\app.py `
  --host 127.0.0.1 `
  --port 9588 `
  --nand-image .\build\bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin
```

## 测试方式

行为测试必须经过 Web 后端，不直接调用 `Bbk9588HwEmu`，也不通过旧式 CLI
入口绕过用户路径。

基础回归：

```powershell
python .\emu\test\run_hwemu_regressions.py
```

更完整但更慢的应用级 smoke：

```powershell
python .\emu\test\run_hwemu_regressions.py --album-smoke
python .\emu\test\run_hwemu_regressions.py --thunder-smoke
```

单独运行前端 smoke：

```powershell
python .\emu\test\run_frontend_web_smoke.py --prefix frontend_web_smoke
```

性能路径探针：

```powershell
python .\emu\test\run_perf_paths.py `
  --case menu-tabs `
  --state-in .\build\nav_menu_checkpoint.pkl `
  --prefix perf_menu_tabs

python .\emu\test\run_perf_paths.py `
  --case tap-sequence `
  --state-in .\build\nav_menu_checkpoint.pkl `
  --action tap:tools-tab:210:287:1 `
  --action key:ok:10:1 `
  --action drag:scroll:120:250:120:100:8:1 `
  --prefix perf_notepad_path_probe

python .\emu\test\run_thunder_battle_benchmark.py `
  --state-in .\build\thunder_battle_checkpoint.pkl `
  --probe-seconds 5 `
  --prefix perf_thunder_battle
```

性能探针默认不传 `--nand-image` 给 `app.py`，因此会使用前端入口自己的默认镜像选择；
只有显式传入 `--nand-image` 时才覆盖这个起点。
`tap-sequence` 支持有序 `--action`：`tap:name:x:y[:settle]`、`key:name:code[:settle]`、
`drag:name:x1:y1:x2:y2[:steps][:settle]`，以及用于保存中间状态的
`save:name:path[:settle]`。

测试脚本会启动本地 HTTP 服务，使用 `/api/status`、`/api/command`、`/screen.png`
和 `/ws` 来驱动仿真器并检查状态、输入队列和帧输出。

## HTTP / WebSocket 接口

常用 HTTP 接口：

- `GET /`：浏览器 UI。
- `GET /api/status`：紧凑状态。
- `GET /api/status?detail=full`：包含更多诊断字段的状态。
- `GET /api/logs?limit=120`：最近日志。
- `GET /screen.png`：当前屏幕 PNG 快照，主要用于诊断和报告。
- `POST /api/command`：统一命令入口，JSON body。
- `POST /api/run-start?name=boot&steps=0&chunk=250000`：启动后台运行任务。
- `POST /api/stop`：停止后台 worker。
- `POST /api/shutdown`：关闭 HTTP 服务。

`/api/command` 常用 JSON：

```json
{"op": "reset"}
{"op": "step", "steps": 250000}
{"op": "run-start", "name": "continuous", "steps": 0, "chunk": 250000}
{"op": "stop"}
{"op": "key", "code": 7, "down": true, "run": true}
{"op": "key", "code": 7, "down": false, "run": true}
{"op": "touch", "x": 120, "y": 160, "down": true, "run": true}
{"op": "touch", "x": 120, "y": 160, "down": false, "run": true}
```

WebSocket 地址是 `/ws`。浏览器和测试脚本通过它发送同样的命令 JSON，并接收：

- JSON 状态/命令响应；
- 二进制 `BBKRAW1` RGB565 帧。

## 输入模型

触摸坐标以 240x320 竖屏坐标为准。浏览器输入会先按当前 canvas 显示尺寸转换到
原始触摸坐标，再进入后端输入队列。

当前已验证的六键扫描码：

```text
4  = 上
5  = 下
6  = 左
7  = 右
9  = 取消/返回
10 = 确认
```

按键输入走硬件级模拟：后端修改建模的 GPIO 电平、设置 GPIO pending 标志、
触发 JZ GPIO 主 IRQ，然后让 C200 固件自己的按键 ISR 消费事件。

## 镜像和文件系统工具

从本地 `系统/` 和 `应用/` 目录生成 FAT16 镜像：

```powershell
python .\emu\tools\make_fat16_image.py `
  --output .\build\bbk9588_fs_fat16_root256.img `
  --free-clusters 256 `
  .\系统 .\应用
```

组合 NAND 镜像：

```powershell
python .\emu\tools\make_combined_nand.py `
  --base-nand .\系统\数据\C200.bin `
  --fat-image .\build\bbk9588_fs_fat16_root256.img `
  --output .\build\bbk9588_nand_c200_fat_page1c40_root256.bin
```

给合成 NAND 写入最小 FTL OOB 标记：

```powershell
python .\emu\tools\stamp_ftl_oob.py `
  .\build\bbk9588_nand_c200_fat_page1c40_root256.bin `
  .\build\bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin
```

检查合成 NAND 中的 FAT 区：

```powershell
python .\emu\tools\inspect_combined_nand_fat.py `
  .\build\bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin
```

## 已知硬件假设

- 主 SoC 是 Ingenic/JzSOC，当前按 JZ4740 一类硬件建模。
- CPU 是 MIPS32 little-endian，XBurst 世代。
- `系统/数据/u_boot_9588_4740.bin` 是 raw MIPS，链接地址 `0x80900000`。
- `系统/数据/C200.bin` 是 raw MIPS，当前作为二阶段系统载荷，基址
  `0x80004000`。
- 离线反汇编 `C200.bin` 时应使用 `0x80004000` 作为加载基址；使用
  `0x80000000` 会让函数地址整体偏移 `0x4000`。
- 已知启动路径涉及 LCD、NAND、键盘、触摸、I2S、USB disk、SDRAM 和产测诊断。

## 当前限制

这仍然是研究型仿真器，不是完整设备模拟器。

主要缺口：

- FTL/NAND 写入模型还不完整。
- 调度器、timer、中断时序仍需要继续校准。
- 部分快速路径仍是等价加速，需要逐步用更精确的设备行为替换。
- 字体和 surface/LCD 提交流程仍有视觉细节差异。

## 开发约束

- 新功能优先走 `emu/app.py` 暴露的 Web 后端。
- 行为回归测试必须用 HTTP/WS，不直接实例化 `Bbk9588HwEmu`。
- `core/` 只放仿真核心、常量和 framebuffer 等核心数据处理。
- `hooks/` 只放 Unicorn hook、设备模型、输入/中断/状态/快速路径。
- `web/` 只放 HTTP/WS 服务、前端页面和长生命周期状态管理。
- `tools/` 放可复用工具脚本和通用 helper。
- `test/` 放用户路径测试，优先复用 HTTP/WS helper。

## 常用排错

如果 Web 页面没有画面：

1. 先看 `/api/status` 是否返回 JSON。
2. 再看 `/screen.png` 是否能返回 PNG。
3. 检查 WebSocket 是否收到二进制 `BBKRAW1` 帧。
4. 查看 `/api/logs?limit=120`。
5. 确认 `--nand-image` 指向存在的合成 NAND 镜像。

如果输入无效：

1. 检查 `/api/status` 里的 `pending_touches` / `pending_keys` 是否能归零。
2. 确认命令里带了 `run:true`，否则事件可能只入队不推进。
3. 确认坐标是 240x320 竖屏坐标，或通过浏览器 canvas 发送显示坐标。

如果测试不稳定：

1. 不要并行运行多个会启动 HTTP 服务的 smoke。
2. 使用不同 `--port` 或传 `--port 0` 让脚本自动选端口。
3. 删除过期 checkpoint 后重新从冷启动 smoke 生成状态。
