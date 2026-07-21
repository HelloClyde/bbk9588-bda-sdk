# 原始输入事件 API

`bda_gui_raw_event_fetch()` 公开 C200 固件 GUI 表 `+0x750` 的非阻塞原始输入流。
它适合不建立标准 Frame 消息泵、由模拟器或游戏核心自行调度输入的 BDA。原机
`GAMEBOY.BDA` 就使用这一层，而不是 `GUI+0x030` 窗口事件泵或 Window Timer。

## 接口

```c
#include "bda_input.h"

typedef struct bda_gui_raw_event {
    s32 code;
    s32 value;
} bda_gui_raw_event_t;

int bda_gui_raw_event_fetch(bda_gui_raw_event_t *event);
```

已确认的事件码：

| 常量 | 值 | 含义 |
|---|---:|---|
| `BDA_INPUT_EVENT_TOUCH_DOWN` | 8 | 一次触摸开始 |
| `BDA_INPUT_EVENT_KEY_DOWN` | 9 | 实体键按下 |
| `BDA_INPUT_EVENT_KEY_UP` | 10 | 实体键抬起 |
| `BDA_INPUT_EVENT_TOUCH_UP` | 11 | 一次触摸结束 |
| `BDA_INPUT_EVENT_TOUCH_MOVE` | 12 | 按住期间坐标更新 |

真机还持续产生 `code=3,value=0`。它是周期性或系统维护事件，但业务语义尚未确认，
SDK 有意不为它提供公开名称。应用必须忽略不认识的 code。

`event.value` 不是触摸坐标。收到 `8/12/11` 后，使用
`bda_gui_touch_position(&x, &y)` 读取最新的 240x320 逻辑坐标。真机本轮按 ESC 时，
原始键事件 `9/10` 的 value 为 `9`；这个 raw value 命名空间不等于
`BDA_KEY_ESCAPE` 等 6-byte packet keycode，不能混用两组常量。

## 游戏循环

原始事件队列可能被 `code=3` 持续填充。每帧必须限制最大消费条数，不能一直读取到
空队列：

```c
static int touch_down;
static u16 touch_x;
static u16 touch_y;

static void poll_raw_input(void) {
    bda_gui_raw_event_t event;
    u32 i;

    for (i = 0u; i < 4u; ++i) {
        int code = bda_gui_raw_event_fetch(&event);
        if (code < 0) {
            break;
        }

        switch ((u32)event.code) {
            case BDA_INPUT_EVENT_TOUCH_DOWN:
                touch_down = 1;
                bda_gui_touch_position(&touch_x, &touch_y);
                break;
            case BDA_INPUT_EVENT_TOUCH_MOVE:
                if (touch_down) {
                    bda_gui_touch_position(&touch_x, &touch_y);
                }
                break;
            case BDA_INPUT_EVENT_TOUCH_UP:
                bda_gui_touch_position(&touch_x, &touch_y);
                touch_down = 0;
                break;
            default:
                break;
        }
    }
}
```

这是全局消费型输入流。不要在同一应用中同时使用
`bda_gui_raw_event_fetch()` 和 `bda_gui_event_pump_frame_once()`：两条路径会竞争
固件输入，窗口控件或 wndproc 可能收不到已经被游戏循环取走的事件。使用普通 Frame
和控件时，继续采用窗口消息；只有自管主循环的游戏/模拟器才应使用原始事件接口。

## 真机证据

测试 BDA：`build/GbTouchEventV1.bda`

源码：`reverse/examples/gameboy_event_touch_hardware_probe.c`

固件与设备：BBK 9588 / C200 真机

测试 BDA SHA-256：

```text
6eb26102e14cfb937e768ee71e294d81ce7753c2f0d56ddd8e8f72e1ab2165a8
```

探针执行多次短按、拖动和实体 ESC 后正常退出。最终计数：

```text
COUNTS C3=361 C8=15 C9=11 C10=7 C11=17 C12=109
RESULT=PASS
```

前 512 条详细事件中，函数返回值全部等于写入的 `event.code`。触摸序列反复表现为
`8 -> 多个 12 -> 11`；启动时残留的启动触摸产生了先于首个 `8` 的 `12/11`，因此
应用初始化时不能假设队列一定从完整的新触摸开始。完整真机日志见
[gameboy_raw_event_v1_hardware_log.txt](assets/gameboy_raw_event_v1_hardware_log.txt)，日志文件
SHA-256 为：

```text
5945bdd2646cc9e4462b5a45413f970e4697e6d613b7da3a810c9d2e628f34a8
```

## 验证边界

- `GUI+0x72c` 在本次测试中始终返回 `0`，并非使用原始事件接口的前置条件；它仍留在
  reverse 研究区，没有进入公开 SDK。
- 探针每 25 ms 最多取 4 条事件，并对每条事件实时开关日志文件。日志中的处理间隔
  不能用来衡量接口极限吞吐量。
- 真机运行期间持续存在 `code=3`，所以本轮没有动态观察到空队列负返回；负值退出判断
  来自固件静态实现，调用方仍应保留。
- 当前只验证单点触摸和六个实体键环境，没有验证多点、压力值或外接输入设备。
