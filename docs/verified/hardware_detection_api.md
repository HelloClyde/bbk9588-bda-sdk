# 机型与芯片识别 API

`bda_hardware.h` 提供只读硬件识别，用同一个 BDA 区分 BBK 9588、BBK 9688，以及
JZ4720、JZ4730、JZ4740。API 不写 NAND 或 MMIO；未知系统返回 `UNKNOWN`，不会因为
Boot ROM 中缺少标记而盲猜成 JZ4730。

## 公开接口

包含 [`bda_hardware.h`](../../sdk/include/bda_hardware.h)：

```c
u32 bda_detect_device_model(u32 *signature_address);
u32 bda_detect_chip_model(
    u32 device_model,
    u32 *boot_rom_signature_address,
    s32 *gui_screen_width_value
);
void bda_detect_hardware(bda_hardware_info_t *info);
const char *bda_device_model_name(u32 model);
const char *bda_chip_model_name(u32 model);
```

机型返回值：

```c
BDA_DEVICE_MODEL_UNKNOWN
BDA_DEVICE_MODEL_9588
BDA_DEVICE_MODEL_9688
```

芯片返回值：

```c
BDA_CHIP_MODEL_UNKNOWN
BDA_CHIP_MODEL_JZ4720
BDA_CHIP_MODEL_JZ4730
BDA_CHIP_MODEL_JZ4740
```

普通应用优先一次性取得完整结果：

```c
#include "bda_hardware.h"

bda_hardware_info_t info;

bda_detect_hardware(&info);
if (info.device_model == BDA_DEVICE_MODEL_9588 &&
    info.chip_model == BDA_CHIP_MODEL_JZ4730) {
    /* 使用 9588/JZ4730 对应实现。 */
}
```

`os_signature_address` 和 `boot_rom_signature_address` 用于诊断；没有命中时为 `0`。
`gui_screen_width_value` 只有 9588 命中 `JZ4740` Boot ROM 标记后才会查询，其他路径为
`BDA_HARDWARE_VALUE_NOT_QUERIED`。

## 判断流程

1. 在 `0x80004000` 开始的 5 MiB 已加载系统映像中查找 `9588 OS` 或 `9688 OS`。
2. 未识别机型时立即返回未知芯片，不读取 Boot ROM。
3. 已识别机型后，在 `0xbfc00000` 前 `0x1000` 字节查找隔字节排列的 `JZ4740`。
4. 未找到标记时，按两版原厂恢复程序的逻辑返回 JZ4730。
5. 9688 找到标记时返回 JZ4740。
6. 9588 找到标记后调用 GUI `+0x738`；返回 `0x131` 时为 JZ4720，否则为 JZ4740。

这些范围、签名和分支分别来自 9588 V3.30 与 9688 V2.32 原厂系统恢复 BDA。公开实现
重新实现搜索算法，不调用恢复 BDA 的固定代码地址。

## 真机验证

公开示例：
`example/system/hardware_detection/hardware_detection_demo.c`

预编译产物：
`example/system/hardware_detection/HardwareDetect.bda`

SHA-256：

```text
CA84EE31D752151F34A1B091AECE217C042274F9C19B3D7623D577C712AA7415
```

BBK 9588 真机消息框：

```text
DEVICE=BBK 9588
CHIP=JZ4730
OS_SIG=0x80253710
ROM_SIG=0x00000000
GUI_738=NOT_QUERIED
RESULT=DETECTED
```

该结果闭环验证了：

- 9588 产品签名能够从系统映像中识别并返回实际命中地址。
- Boot ROM 中没有 JZ4740 标记时返回 JZ4730。
- JZ4730 分支不会误调用仅用于区分 JZ4720/JZ4740 的 GUI `+0x738`。
- 测试 BDA 能正常显示完整结构化结果。

## 验证边界

- 当前保存的完整原始结果覆盖 BBK 9588/JZ4730。
- 9688、JZ4720 和 JZ4740 分支与对应原厂恢复程序一致，但仍应继续保存各组合的实机
  消息框结果以扩大动态证据。
- 8013 模拟器没有映射真机 `0xbfc00000` Boot ROM；测试 BDA 会在该只读访问处触发
  TLB-load，因此模拟器不作为芯片检测验证环境。
- API 只识别列出的两种机型和三种芯片，不承诺适用于其他 BBK 产品或修改过的系统
  映像。
