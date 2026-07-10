# JZ4740 手册驱动的 QEMU 改造计划

本文基于当前 `bbk9588` QEMU 实现、`u_boot_9588_4740.bin` 反汇编结论，以及
[JZ4740 Programming Manual](https://opennoah.github.io/datasheet/JZ4740_pm.pdf)
整理后续硬件模型改造范围。

## 目标

当前模拟器已经能跑到主菜单和部分应用，但 `bbk9588.c` 仍然是“能跑优先”的混合模型：

- SoC 设备模型、板级连线、BootROM、NAND 后端、FTL/FAT 辅助、LCD 输出、触摸输入和诊断桥都集中在一个大文件里。
- `system.py` 仍保留大量早期 firmware patch、stall region 和资源/存储诊断语义。
- NAND 镜像工具已经能构造可启动镜像，但 BootROM 与 NAND 启动路径仍存在模拟器私有格式。

后续目标是把默认路径收敛为更接近真机的 system emulation：

1. QEMU 只模拟 JZ4740 SoC、板级外设和 raw NAND 行为。
2. U-Boot/C200 自己完成 FTL、FAT、资源缓存和 UI 逻辑。
3. Python 只负责启动、前端、打包和只读诊断，不长期承担硬件行为替代实现。

## 当前实现边界

主要代码位置：

- `emu/qemu/source-overlay/hw/mips/bbk9588.c`：当前 QEMU C machine 和设备模型主体。
- `emu/qemu/system.py`：QEMU 命令构造、进程管理、Web 后端状态和诊断。
- `emu/tools/make_combined_nand.py`：构建 raw boot 区 + FAT 数据区的 NAND 镜像。
- `emu/tools/stamp_ftl_oob.py`：给 NAND OOB 写入当前固件能识别的 FTL 映射标签。
- `emu/web/frontend_state.py`：Web 前端状态、输入转发、自动校准和诊断接口。

当前 `bbk9588.c` 里已经包含：

- MIPS CPU、RAM、reset PC、raw firmware 加载。
- NAND command/address/data port、READ ID、page read/program/erase、ready/busy、部分 OOB/FTL 映射。
- LCD framebuffer 镜像、frame chardev、vblank/frame done 近似调度。
- INTC、TCU、GPIO、SADC touch、RTC、UART、UDC、MSC、DMAC 的不同程度 stub。
- 诊断 RAM 区、storage/resource trace、progress trace、touch trace。

这些能力可以作为继续实现的基础，但需要重新划分职责。

## 手册能指导什么

JZ4740 手册对模拟器最有价值的是寄存器级硬件契约：

- BootROM/NAND boot：内部 SRAM、NAND page size boot select、normal/backup boot area、ECC 行为。
- EMC/NAND：NAND data/command/address 空间、NFCSR、ready/busy、ECC/BCH、DMA page 边界。
- INTC：中断 mask/set/clear/pending 寄存器和 source 编号。
- TCU：timer/counter channel、compare、flag、mask、start/stop 和中断产生。
- LCD/SLCD：LCD controller 寄存器、descriptor DMA、frame done、disable/reset、vblank 节拍。
- SADC：touch FIFO、pen event、battery/sample register、SADC interrupt。
- DMA/MSC/UART/RTC/PM/GPIO：固件等待、搬运、低功耗和输入输出路径。

手册不能直接解决 BBK 私有层：

- `kj409588.bin`、C200 固件格式和应用资源格式。
- BBK 的 FTL 逻辑块/OOB 标签含义。
- FAT 镜像内容、目录结构、BDA/DLX/图片资源。
- 板级 GPIO 具体接线、触摸屏校准参数、LCD panel 时序细节。

这些仍需要反汇编、真机 dump、运行 trace 和截图对比确认。

## 高优先级改造项

### 1. BootROM 与 NAND 启动路径

当前状态：

- `bbk9588.c` 定义了 `BBK9588_BOOTROM_MAGIC = "BBKUBOOT"`。
- 默认 raw boot page 是 `0x40`，默认复制大小是 `512 KiB`。
- 还存在 `bootrom-fat-kernel` 路径，会从 NAND FAT 里直接找 `系统/数据/kj409588.bin`。
- `make_combined_nand.py` 在无 loader 时会写模拟器私有 BootROM header。

需要改造：

- 按 JZ4740 BootROM 建模：从 NAND address `0` 读取 first-stage loader 到内部 SRAM/RAM 启动区。
- 支持 normal boot area 和 backup boot area；backup 起点按手册使用 NAND address `0x2000`。
- BootROM 不应懂 FAT，也不应直接找 `kj409588.bin`。
- `BBKUBOOT` header 只能作为旧镜像兼容诊断路径，默认发布路径应移除依赖。
- `U-Boot -> FAT -> kj409588.bin -> 0x80004000` 这条链路应由 U-Boot 自己执行。

验收标准：

- 不传 `-kernel C200.bin` 时，可以只靠 NAND raw boot 区启动 first-stage/U-Boot。
- 删除或禁用 `bootrom-fat-kernel` 后，仍能进入 C200 主菜单。
- 刻意破坏 normal boot area 后，backup boot area 能被尝试读取。

### 2. NAND/EMC 控制器与 raw NAND 后端

当前状态：

- `Bbk9588NandState` 同时负责 NAND 命令状态机、backing file、FTL map、FAT16 查找、逻辑扇区读写和部分资源缓存辅助。
- `bbk9588_find_fat16_layout()` 会扫描 NAND 数据区寻找 FAT16 boot sector。
- `bbk9588_read_logical_sector()`、`bbk9588_storage_first_dirent_for_pattern_from_nand()` 等函数已经越过硬件层，理解 FAT/目录项。
- `BBK9588_NAND_FAT_PROTECT_*` 是为了保护当前构造镜像的兼容逻辑，不属于真实 NAND 控制器。

需要改造：

- 把 NAND/EMC 分成两层：
  - JZ4740 EMC/NAND controller：只处理 NFCSR、data/command/address 空间、ready/busy、ECC/BCH/DMA 可见行为。
  - raw NAND backend：只保存 page data + OOB，支持 read/program/erase 和 bad block/OOB。
- 从 controller 默认路径移除 FAT16、目录项、资源文件、逻辑扇区等系统层知识。
- FTL 映射由 U-Boot/C200 通过 OOB 自己建表；QEMU 只保证 OOB 字节可被正确读写。
- 保留 trace 可以，但 trace 只能观察 raw page/OOB 访问，不能改变返回数据。

镜像工具同步要求：

- `stamp_ftl_oob.py` 继续负责离线写好 OOB 映射，让固件自然扫描通过。
- `make_combined_nand.py` 需要与真实 512 MiB NAND 几何对齐：2048B page、64B OOB、64 pages/block、4096 blocks。
- FAT 可见容量、16 KiB cluster 等真机参数应在镜像工具里固定或显式配置，而不是由 QEMU 运行时猜测。

验收标准：

- U-Boot 的 OOB scan 不需要 QEMU 认识 FAT。
- C200 主菜单资源、应用图标和应用数据都通过固件 FTL/FAT 路径读取。
- 图标随机污染问题不再依赖 resource/cache bridge 规避。

### 3. INTC/TCU/CPU wake 路径

当前状态：

- INTC 有 `pending_mask`、`intc_mask` 和 CPU IRQ 输出，但仍偏简化。
- TCU 有 6 个 channel 的近似计数、compare、pending 和 `tcu-period-ms` property。
- `system.py` 保留了早期 CP0 IRQ patch、wait patch 和很多 stall region。

需要改造：

- 按 JZ4740 INTC 寄存器实现 `ICSR/ICMR/ICMSR/ICMCR/ICPR` 等 mask/set/clear/pending 语义。
- 明确每个外设的 interrupt source 编号，统一由设备 raise/lower 到 INTC。
- TCU 按寄存器模型实现 enable/disable、compare、counter、flag set/clear、mask set/clear。
- MIPS `wait` 退出必须依赖真实 pending interrupt，而不是 firmware no-op patch。

验收标准：

- 默认启动不需要 `c200-cp0-irq-enable-noop`、`c200-cp0-status-restore-noop`、`c200-wait-noop`。
- GUI tick、触摸 IRQ、NAND ready、LCD frame done 都通过 INTC 唤醒固件。
- `tcu-period-ms` 这类调参属性不再影响正确性，只能作为诊断/性能选项。

### 4. LCD/SLCD 输出模型

当前状态：

- LCD 模型会观察 MMIO 写入，猜测 framebuffer/descriptor 地址。
- 使用定时器推 frame，并设置 `LCD_STATUS_READY`、`LCD_STATUS_FRAME_DONE` 等位。
- 主菜单曾出现局部未画完整和随机彩色噪点，说明输出节拍与内存更新/资源加载仍有边界问题。

需要改造：

- 按 LCD controller 寄存器建模：config、sync、virtual area、display area、control、state、descriptor、source address、frame id、DMA command。
- frame 只在硬件意义上的 frame done/vblank 节点推给前端。
- LCDSTATE/frame done/underflow/disable done 等状态位应由 LCD 状态机维护。
- 如果固件使用 Smart LCD，需要单独实现 SLCD command/data FIFO，而不是混入普通 framebuffer mirror。
- frame chardev 只是显示输出，不应参与判断资源是否加载成功。

验收标准：

- 同一菜单页重复截图稳定，不出现同一图标随机缺半截。
- 应用画面、主菜单、校准界面都通过同一 LCD 节拍输出。
- 前端 PNG/WebSocket 只包装最终帧，不掩盖 LCD 模型问题。

### 5. SADC/Touch/GPIO 输入路径

当前状态：

- Web 输入通过 chardev 传入 QEMU。
- C 模型把 host touch 转换成 raw X/Y、SADC status、GPIO latch 和 IRQ。
- 这比 firmware global hook 好，但 SADC/GPIO 仍是为当前固件路径定制的近似模型。

需要改造：

- 按 JZ4740 SADC 寄存器实现 ADENA、ADCFG、ADCTRL、ADSTATE、ADSAME、ADWAIT、ADTCH FIFO。
- touch sample 应以 FIFO 形式提供，包含 X/Y/Z 和 sample type bit。
- GPIO 只模拟板级接线和电平/边沿/flag，不直接理解“触摸校准流程”。
- Web 自动校准保留为测试 harness，但不能放进 SoC 模型。

验收标准：

- 校准十字可以靠 SADC FIFO + GPIO/INTC 完成。
- 关闭自动校准后，用户手动点击仍能完成校准。
- 不存在 `touch-firmware-globals` 或等价系统层变量写入。

### 6. DMA/MSC/UART/UDC/RTC/PM

当前状态：

- DMAC、MSC、UART、UDC、RTC/ready/power 目前以局部 stub 为主。
- `bbk9588_msc_complete_dma()`、audio DMA completion、UDC idle read 等行为够当前路径用，但仍不完整。
- RTC 和电池值目前有固定默认值/魔数。

需要改造：

- DMAC：实现 channel register、descriptor/transfer、terminal count、IRQ，至少覆盖 NAND/LCD/MSC/audio 相关路径。
- MSC：如果固件通过 MSC 访问内部 NAND/FAT，需要把 command/response/DMA 语义补齐。
- UART：实现 FIFO/status/IRQ，保留 chardev 输出。
- UDC：无 USB host 时也要提供合理 idle/interrupt 状态，避免固件服务循环异常。
- RTC/PM/SADC battery：日期时间、电池电压和低功耗唤醒应从对应寄存器模型给出。

验收标准：

- 主菜单日期时间由 RTC 路径自然显示。
- 不再需要 `c200-uart-ready`、`c200-graphics-done`、固定 ready magic 等 firmware patch。
- 低电压提示只由真实 battery ADC/PM 状态触发。

## 结构重构建议

当前 `bbk9588.c` 已经接近 6000 行，继续加设备会越来越难维护。建议按 QEMU 习惯拆分：

```text
hw/mips/bbk9588.c             板级 machine、RAM、CPU、设备 wiring
hw/misc/jz4740_intc.c         INTC
hw/timer/jz4740_tcu.c         TCU
hw/mem/jz4740_emc.c           EMC/NAND controller windows
hw/block/bbk9588_nand.c       raw NAND backend / board NAND 参数
hw/display/jz4740_lcd.c       LCD controller
hw/input/jz4740_sadc.c        SADC/touch ADC
hw/gpio/jz4740_gpio.c         GPIO ports
hw/dma/jz4740_dmac.c          DMAC
hw/rtc/jz4740_rtc.c           RTC
```

如果短期不拆文件，也至少应在 `bbk9588.c` 内保持同样边界：每个设备有独立 state、register ops、IRQ out、reset，并由 board 统一连线。

## Python/前端需要收敛的部分

`system.py` 的长期职责应是：

- 构造 QEMU 命令。
- 管理 QEMU 进程生命周期。
- 接收 frame/input chardev。
- 输出只读诊断状态。

需要逐步移除或降级：

- `KNOWN_FIRMWARE_PATCHES` 默认不应再影响 `bbk9588` machine。
- `KNOWN_STALL_REGIONS` 可以保留为逆向索引，但不应作为“修系统逻辑”的入口。
- FAT16 layout cache、resource trace、storage fastpath 命名应避免给人仍有 Python storage bridge 的误解。
- 自动校准只属于 Web smoke test，不属于硬件模型。

## 实施顺序

建议按风险从低到高推进：

1. 固化基线：保留当前能进主菜单/打开应用的 smoke test 和截图对比，作为回归门槛。
2. 拆职责：先把寄存器常量、state、trace 命名按设备边界整理，减少后续误改。
3. BootROM：移除默认 `BBKUBOOT`/FAT kernel 依赖，实现 raw NAND first-stage boot 和 backup boot。
4. NAND/EMC：让 controller 只返回 raw page/OOB，FTL/FAT 完全交给 U-Boot/C200；同步修镜像 OOB。
5. INTC/TCU：补完整中断和 timer/wait 唤醒，删除 CP0/wait 类 firmware patch。
6. LCD/SLCD：按 descriptor DMA 和 frame done/vblank 推帧，消除主菜单随机渲染污染。
7. SADC/GPIO：补 touch FIFO、pen IRQ、GPIO flag/edge，删除系统层触摸注入。
8. DMAC/MSC/RTC/PM：补齐剩余会影响应用、日期时间、电池状态、音频/存储的设备。
9. 清理发布路径：删除旧兼容开关、过时诊断文案和不再使用的镜像格式。

## 关键验收清单

- 冷启动：只提供 NAND 镜像即可从 BootROM -> loader/U-Boot -> `kj409588.bin` -> C200。
- 存储：没有 resource/dirent/cluster fastpath，主菜单图标和应用资源仍稳定显示。
- 性能：U-Boot OOB scan 不出现分钟级等待；大文件搬运不会逐 byte 形成异常 MMIO 瓶颈。
- 显示：LCD 按 frame done/vblank 推帧，截图没有随机半图标、噪点和局部补绘。
- 输入：触摸校准和菜单点击通过 SADC/GPIO/INTC 完成。
- 时间/电池：主菜单日期时间、电量图标和低电压提示来自 RTC/SADC/PM 状态。
- 发布：release zip 内只包含运行时必需文件、启动脚本、Web 端、QEMU 可执行文件和 README。

## 风险与注意点

- JZ4740 手册是 SoC 级参考，BBK 9588 的板级接线和固件约定仍要靠反汇编/trace 确认。
- 手册不同章节对 BootROM copy size 存在描述差异；实现时应优先按 BootROM 章节和真实固件行为验证。
- 过早删除 NAND/FAT 辅助会导致资源加载回归；应先把 OOB 映射和 raw read/write 验证补足。
- LCD 噪点不应只从显示层猜测，仍要结合资源加载、cache flush、DMA descriptor 和 framebuffer 写入路径定位。
- 诊断 trace 可以保留，但必须保证关闭 trace 后行为不变。

