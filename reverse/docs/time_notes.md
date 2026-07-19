# 时间和闹钟 API 笔记

这些调用来自原机 `时间.bda`、`闹钟.bda`、`系统设置.bda` 和 `GAMEBOY.BDA`。
当前 SDK 只给已确认 ABI 的 wrapper 命名；alarm record 字段仍只标注已确认 offset。

相关报告：

- `reverse/reports/time_bda_report.md`
- `reverse/reports/alarm_bda_report.md`

当前 `闹钟.bda` 报告是 RTC/闹钟调用点最强证据；`时间.bda` 主要证明显示刷新
循环和 delay 行为。

## GUI 游戏 tick

```text
GUI +0x6d8  25 ms raw tick counter
```

该入口无参数返回 32-bit 原始计数。C200 定时 IRQ 每 25 ms 递增一次；官方 BBVM
的 GetTick 会先减去启动时保存的基准值，再乘 25 返回毫秒。公开 SDK 提供：

```c
u32 bda_gui_tick_count_25ms(void);
u32 bda_gui_tick_elapsed_25ms(u32 start, u32 end);
u32 bda_gui_tick_elapsed_ms(u32 start, u32 end);
```

差值 helper 使用无符号减法，可跨一次 32-bit 回绕。`GameTickProbeV9` 已在 8013
模拟器验证 raw counter 前进、40 tick 等于 1000 ms 的换算和回绕算术；它已按模拟器
稳定等级进入 `sdk/include`，真机待测。
这与 `SYS+0x080` busy-wait delay 和 `SYS+0x09c` preset selector 是三条不同路径。

## 高分辨率计时研究

官方 BDA 没有直接执行 `mfc0 ..., $9`；U-Boot `0x8091ce34` 虽提供 CP0 Count
getter，但 U-Boot 地址在 C200/BDA 运行期不可作为 SDK 入口调用。继续扫描 GUI 表的
未命名入口后，已定位到一组独立的 1 ms timer start/read/stop API。

### V2 否定的路径

C200 `0x8012bcd4` 把 JZ4740 TCU channel 1 配置为：

```text
TDFR1  0xb0002050 = 18750
TDHR1  0xb0002054 = 18750
TCNT1  0xb0002058 = 0..18749
TCSR1  0xb000205c = 0x14  // external 12 MHz, /16
```

8013 模拟器把 `TCNT1` 实现为 750 kHz、约 1.333 us 粒度的 fine counter；V2 四段
200 ms 窗口分别得到 `150004/149997/150000/150000`，CP0 Count 与 TCU1 比例为
224。但真机 V2 返回：

```text
TDFR1=0x0000FFFF
TDHR1=0x0000FFFF
TCSR1=0x0000FFFF
TFR=0xFFFFFFFF
WINDOW=0..3 CP0=0 TCU=524280 HIRES=150000
FAILURES=0x00000004
RESULT=FAIL
```

真机中的直接 TCU MMIO 是全一开路值，CP0 Count 恒为零。`HIRES=150000` 仅来自
`8 * 18750` 的 coarse tick 换算；前后 `TCNT1` 都为 `0xffff`，相减后没有提供任何
fine 时间。因此 750 kHz 组合 helper 已撤销，TCU/CP0 路径明确判定为不可公开。

### V3 否定的路径：未启用固件全局

C200 还包含独立 timer-0 路径：

```text
0x800043f8  TCSR0 = external clock / 4，TDFR0 = TDHR0 = 3000
0x800043e0  timer-0 IRQ：将 *(u32 *)0x80473ed0 加一
```

12 MHz external clock 经 `/4` 后为 3 MHz，3000 count 周期正好是 1 ms。但 V3 在
8013 上四个窗口的 `0x80473ed0` 差值全部为零，subtick 也失败，说明这段旧 timer-0
初始化没有进入当前 C200 启动流程。直接读取该 RAM word 的 helper 已撤销。

### V4 已验证：GUI 标称 1 ms timer API

GUI 表靠后的三个未命名入口构成完整生命周期：

```text
GUI +0x714 -> 0x8001dce0  start：TCU0 external 12 MHz /16，period 750
GUI +0x718 -> 0x8001ddb0  stop：mask timer-0 并注销 IRQ 0x17
GUI +0x71c -> 0x8001dde0  read：返回 *(u32 *)0x80473fd0
IRQ callback 0x8001dec0   每次将 0x80473fd0 加一
```

`750000 / 750 = 1000 Hz`，因此该 API 的理论粒度为 1 ms。8013 V4 的四个 200 ms
窗口均得到 `MS=200`；同一 25 ms GUI tick 内 counter 从 934 增到 935；stop 后等待
50 ms，counter 保持 943。真机 V4 的四个窗口为 `200/194/194/194`，同一 25 ms tick
内 counter 从 959 增到 960，stop 后保持 `1017`，最终 `RESULT=PASS`。该组 API 已进入
`sdk/include/bda_time.h`；公开文档明确将它描述为标称 1 ms 的单调计数，不承诺墙钟
误差为 1 ms。

研究头当前提供以下符号：

```c
#define BDA_TCU_TIMER1_FLAG_LIKE              0x00000002u
#define BDA_TCU_TIMER1_COUNTS_PER_TICK_LIKE   18750u
#define BDA_TCU_TIMER1_COUNTS_PER_SECOND_LIKE 750000u
#define BDA_GUI_MILLISECOND_TIMER_START_LIKE  0x714u
#define BDA_GUI_MILLISECOND_TIMER_STOP_LIKE   0x718u
#define BDA_GUI_MILLISECOND_COUNT_LIKE        0x71cu

u32 bda_cp0_count_raw_like(void);
u32 bda_tcu_flags_raw_like(void);
u32 bda_tcu_timer1_period_raw_like(void);
u32 bda_tcu_timer1_half_period_raw_like(void);
u32 bda_tcu_timer1_count_raw_like(void);
u32 bda_tcu_timer1_control_raw_like(void);
int bda_tcu_timer1_available_like(void);
void bda_gui_millisecond_timer_start_like(void);
void bda_gui_millisecond_timer_stop_like(void);
u32 bda_gui_millisecond_count_like(void);
u32 bda_gui_millisecond_elapsed_like(u32 start, u32 end);
```

TCU raw getter 只用于复现 V2 的模拟器/真机差异；
`bda_tcu_timer1_available_like()` 在真机返回 false。V4 的 1 ms API 必须严格配对调用
start/stop，elapsed helper 使用无符号差值。带 `_like` 的符号保留给历史 probe；普通
应用使用公开的 `bda_gui_millisecond_*` 名称。

## SYS 表调用

```text
SYS +0x080  busy-wait delay-like
  在时间和闹钟应用中出现
  常见参数: a0 = 0xc350 (十进制 50000)
  C200 会读取系统校准值，把 a0 换算成循环次数后原地忙等。
  它不是调度式 sleep，不能在 GUI main event loop 里长时间调用。

  时间应用调用该 offset 42 次，但当前 scanner 没有分类出直接 SYS+0x0b8 调用。
  实际读取时钟的路径可能是当前 scanner 没抓到的调用形态，也可能在闹钟应用中
  更明显。

SYS +0x0b8  alarm due record get-like
  在闹钟应用中出现
  a0 = 调用者提供的 bda_sys_alarm_record_like_t out buffer
  C200 打开 a:\应用\数据\alarm.db，读取 0xda0 byte，扫描 0x2b8 byte alarm record
  命中时把整条 record 复制到 out buffer；失败/无可用记录时写 out+0x00 = -1
  比较逻辑会读取 record+0x11、record+0x12 等 byte，以及 record+0x30 的 word
  SDK 可用 bda_sys_alarm_due_miss_like(record) 判断 out+0x00 是否为 -1
  最强证据: reverse/reports/alarm_bda_report.md

SYS +0x0b0  alarm get-like
  在闹钟应用中出现
  a0 = 调用者提供的 buffer
  a1 = slot，已见 0、1、2
  C200 从 file offset 0x578 + slot * 0x2b8 复制 0x2b8 byte record
  return value: 成功 1，失败 0；未见 slot bounds check
  SDK helper bda_sys_alarm_record_file_offset_like(slot) 只复现该 offset 计算

SYS +0x0ac  alarm set-like
  在闹钟应用中出现
  a0 = 调用者提供的 buffer
  a1 = slot，已见 0、1、2
  C200 会把 record+0x00 写成 slot+2，把 record+0x10 写成 1
  然后把 0x2b8 byte record 写回同一配置文件
  return value: 成功 1，失败 0；未见 slot bounds check
  在结构体布局确认前，不要从 probe 里调用它

SYS +0x0a8  不公开 no-op stub
  C200 table entry 指向 0x8001415c，函数体是 jr ra; nop
  旧的 alarm/time commit 命名只是早期调用点猜测，SDK 不再公开该 wrapper

SYS +0x09c  timer/rate preset-like
  在系统设置和 GAMEBOY.BDA 中出现
  C200 会把 a0 限制到 0..14，再按 index 读取内部 preset table entry 并调用下游函数。
  因此 SDK 参数命名为 preset_index，不应把它当作任意 tick 数。
```

## 当前 Probe

`reverse/examples/time_probe.c` 会读取 `SYS+0x0b8` 的 due alarm record 和三个
alarm slot 的 `SYS+0x0b0`，然后显示 return value 和原始 byte。

`reverse/examples/game_tick_probe.c` 只读 `GUI+0x6d8`，等待至少 40 个 raw tick，
将每条结果立即写入 `A:\应用\数据\游戏\GAMETICK.TXT` 后返回菜单。

`reverse/examples/high_resolution_timer_probe.c` V4 调用 GUI `+0x714/+0x718/+0x71c`
并用 `GUI+0x6d8` 交叉验证，将实时结果写入 `A:\HRTIMER.TXT`。真机测试构建产物为
`build/HighResolutionTimerProbeV4.bda`。

该 probe 刻意不调用 `SYS+0x0ac`。`SYS+0x0a8` 在 C200 中是 no-op stub，已经从
SDK 公开 wrapper 中移除。

## SDK 暴露的 wrapper

```c
void bda_sys_delay_like(u32 delay_units);
void bda_sys_timer_like(u32 preset_index);
int bda_sys_alarm_due_get_like(bda_sys_alarm_record_like_t *out_alarm_data);
int bda_sys_alarm_get_like(bda_sys_alarm_record_like_t *alarm_data, u32 slot);
int bda_sys_alarm_set_like(bda_sys_alarm_record_like_t *alarm_data, u32 slot);
void bda_sys_alarm_record_init_like(bda_sys_alarm_record_like_t *record);
int bda_sys_alarm_slot_confirmed_like(u32 slot);
u32 bda_sys_alarm_record_file_offset_like(u32 slot);
u32 bda_sys_alarm_record_slot_tag_like(const bda_sys_alarm_record_like_t *record);
int bda_sys_alarm_due_miss_like(const bda_sys_alarm_record_like_t *record);
u8 bda_sys_alarm_record_enable_flag_like(const bda_sys_alarm_record_like_t *record);
```

当前只有 `alarm_due_get/alarm_get` 适合做只读或低风险 probe。`delay` 和
`timer` 都是 side-effect API，没有稳定 return value。`alarm_set`
需要等 struct 字段、checksum/persistence 规则和副作用都确认后再给普通开发者使用。
`bda_sys_alarm_record_like_t` 固定为 `0x2b8` byte；`alarm_due_get/alarm_get/alarm_set`
的 buffer 都按这个类型准备，不要传未验证 slot。

已确认 helper 只覆盖下面几个 C200 直接证据：

- `BDA_SYS_ALARM_CONFIRMED_SLOTS == 3`：当前只见 slot `0/1/2`。
- `BDA_SYS_ALARM_DB_FIRST_RECORD_OFFSET == 0x578`：持久化 record 起点。
- `BDA_SYS_ALARM_SLOT_TAG_OFFSET == 0x00`：`alarm_set` 写入 `slot + 2`，`alarm_due_get`
  失败时写 `BDA_SYS_ALARM_DUE_MISS_TAG` (`0xffffffff`)。
- `BDA_SYS_ALARM_ENABLE_FLAG_OFFSET == 0x10`：`alarm_set` 写入 `1`。

这些 helper 不是完整 alarm record struct。未命名 byte 仍按 raw data 处理。
