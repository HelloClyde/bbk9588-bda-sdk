# 窗口消息定时器 API

`sdk/include/bda_time.h` 公开 C200 GUI 的 Frame 周期定时器。它适合让动画、
游戏逻辑或界面刷新跟随窗口事件泵执行，不会像 busy-wait 一样独占 CPU。

## 接口

```c
#include "bda_time.h"

#define BDA_MSG_WINDOW_TIMER 0x0144u
#define BDA_WINDOW_TIMER_MAX_ACTIVE 16u
#define BDA_WINDOW_TIMER_RESOLUTION_MS 10u

int bda_gui_window_timer_start(
    bda_handle_t frame, u32 timer_id, u32 period_ms
);
int bda_gui_window_timer_stop(bda_handle_t frame, u32 timer_id);
int bda_gui_window_timer_exists(bda_handle_t frame, u32 timer_id);
int bda_gui_window_timer_set_period(
    bda_handle_t frame, u32 timer_id, u32 period_ms
);
u32 bda_gui_window_timer_clock_ms(void);
```

`start`、`stop` 和 `set_period` 成功返回 `1`，失败返回 `0`。`start` 的返回值不是
timer handle；系统用 `(frame, timer_id)` 二元组识别定时器。`exists` 在二元组仍处于
活动状态时返回 `1`。`period_ms` 必须大于零，公开 wrapper 会拒绝零周期。

## 消息处理

到期消息传给 Frame 的 wndproc：

```c
static int window_proc(
    bda_handle_t frame, u32 message, u32 wparam, u32 lparam
) {
    if (message == BDA_MSG_WINDOW_TIMER) {
        u32 timer_id = wparam;

        /* 更新游戏状态，再请求或执行该帧的绘制。 */
        (void)timer_id;
        return 1;
    }
    return bda_gui_default_proc(frame, message, wparam, lparam);
}
```

`wparam` 是注册时传入的 `timer_id`，`lparam` 为 `0`。消息必须由正常的 Frame 事件泵
消费。事件泵落后时，固件可能合并同一 timer 的待处理状态，因此游戏应根据单调时钟
计算实际经过时间，不要把收到的消息数量当作绝对时间。

## 生命周期

1. 注册并激活 Frame。
2. 用该 Frame 和应用自选的 `timer_id` 调用 `bda_gui_window_timer_start()`。
3. 在 wndproc 中处理 `BDA_MSG_WINDOW_TIMER`。
4. 改周期时调用 `bda_gui_window_timer_set_period()`。
5. Frame 执行 stop、release、close 前，逐一停止它拥有的所有 timer。

系统全局 timer 表最多有 `16` 个活动记录。不要依赖 Frame 关闭时自动回收 timer；遗漏
`stop` 会留下指向旧 Frame 的记录，之后可能把消息投给失效对象。

公开 `set_period` 有意使用已经验证的 `stop + start`。原生 GUI `+0x1b8` 在 timer 表
存在空槽时会无判空解引用，因此没有进入公开 SDK。若重新注册失败，旧 timer 已经停止，
调用方应按返回 `0` 处理。

## 时间语义

- `period_ms` 的单位是毫秒，调度器以 `10 ms` 步进；非整步周期会在下一个调度边界
  到期，即 `ceil(period_ms / 10) * 10 ms`。V6 已在 8013 模拟器动态验证该量化规则。
- 这是消息调度器，不是硬实时中断。事件泵、绘制和文件日志都会推迟 wndproc 实际运行。
- `bda_gui_window_timer_clock_ms()` 返回调度器使用的 32-bit 单调毫秒计数。计算间隔时用
  无符号减法，以自然处理回绕。
- 它与 `bda_gui_tick_count_25ms()` 是两个不同的系统计数器。

## 固件入口

| 公开能力 | GUI 表项 | C200 入口 |
|---|---:|---:|
| start | `+0x1ac` | `0x800de150` |
| stop | `+0x1b0` | `0x800de190` |
| exists | `+0x1b4` | `0x800de0a8` |
| scheduler clock | `+0x1bc` | `0x800de144` |

start/stop 先同步发送内部 `0x162/0x163`，随后由固件维护 16-byte timer 记录。到期后，
事件获取路径生成公开可见的 `0x144` Frame 消息。

## V4 动态验证

源码：`reverse/examples/window_timer_probe.c`

构建产物：`build/WindowTimerProbeV4.bda`

```powershell
python -m bda_packer reverse\examples\window_timer_probe.c `
  --title WindowTimerV4 --category 9 `
  -I sdk\include -o build\WindowTimerProbeV4.bda
./scripts/test_bda_in_emulator.ps1 `
  ./build/WindowTimerProbeV4.bda -Port 8013 -NoOpenBrowser
```

8013 模拟器完整 NAND 和 BBK 9588 真机均验证了：40 ms 连续触发、改为 20 ms 后连续
触发、消息参数、exists 的 start/stop 状态，以及先释放较早槽位后再修改另一个 timer
的稀疏表场景。两边结果均为 `FAILURES=0x00000000`、`RESULT=PASS`。日志见
[`assets/window_timer_v4_emulator_log.txt`](assets/window_timer_v4_emulator_log.txt)。
真机日志见
[`assets/window_timer_v4_hardware_log.txt`](assets/window_timer_v4_hardware_log.txt)。

真机 scheduler clock 的连续增量严格为 `40 ms` 和 `20 ms`。同一批日志中的 25 ms
tick 增量会受逐行文件写入和事件泵运行时间影响，因此不能用它推导 wndproc 的硬实时
延迟保证。

验证 BDA SHA-256：
`10636d3fea1b341907501429750d7146e24afeff5c1d09c67600c4afc0934ee4`。

测试使用的 C200 SHA-256：
`02a16107b11a3281067871c6fe3d4c289c910d8dfa9924573dd87f00351d6525`。

## V6 精度边界验证

`WindowTimerPrecisionV6.bda` 对每个周期丢弃一个 warm-up 事件，然后在回调中只采样
内存，停止该 phase 后才写日志。每组包含 12 个有效样本：

| 请求周期 | 预期量化 | scheduler min/max/avg | 结果 |
|---:|---:|---:|---|
| 5 ms | 10 ms | 10/10/10 ms | PASS |
| 10 ms | 10 ms | 10/10/10 ms | PASS |
| 15 ms | 20 ms | 20/20/20 ms | PASS |
| 25 ms | 30 ms | 30/30/30 ms | PASS |

模拟器共 48 个 scheduler delta，失败数为零，确认最小调度步长和非整 10 ms 周期的
向上取整。完整日志见
[`assets/window_timer_precision_v6_emulator_log.txt`](assets/window_timer_precision_v6_emulator_log.txt)。

V6 同时读取标称 1 ms counter 观察消息实际投递间隔。8013 模拟器中该 counter 与 GUI
timer scheduler 不同步，消息会成批投递，因此日志中的
`DELIVERY RESULT=OUTSIDE TOLERANCE` 只表示模拟器无法完成跨时钟精度验证，不推翻
`SCHED RESULT=PASS`。实际 10 ms 消息投递抖动仍需用同一 V6 BDA 在真机判断。

V6 构建产物：`build/WindowTimerPrecisionV6.bda`

V6 SHA-256：
`49367dfd1116d10d221fcec92bd8d336e6d038ba472c2a899c645efab2f770ab`。

当前结论覆盖 8013 模拟器和本次 BBK 9588 真机的 kj409588/C200 固件。真机已验证
20/40 ms 周期；5/10/15/25 ms 量化和独立 1 ms counter 投递抖动等待 V6 真机日志。
尚未覆盖 16 个 timer 同时运行、事件泵长期阻塞、32-bit clock 回绕以及其他固件版本。
