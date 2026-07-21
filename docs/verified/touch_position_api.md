# 高速触摸坐标 API

`GUI+0x6c0` 已由 `FastTouchV3.bda` 在 BBK 9588 真机上动态验证。它读取固件维护的
最新校准逻辑坐标，不经过窗口事件队列，也不会产生一次 25 ms 的空队列等待。

## API 定义

```c
void bda_gui_touch_position(u16 *x, u16 *y);
```

两个参数都必须是有效的 `u16 *`。调用后坐标范围为屏幕逻辑空间，当前目标为
`x=0..239`、`y=0..319`。该入口没有已验证的返回值，因此公开 wrapper 使用 `void`。

这个 API **不返回触摸是否按下**。抬起后它可以继续返回最后缓存的坐标。普通 Frame
应用使用窗口消息维护触摸生命周期：

```text
BDA_MSG_TOUCH_COORDINATE = 1  按下或坐标事件
BDA_MSG_TOUCH_RELEASE    = 2  抬起事件
```

不建立标准 Frame 消息泵的自管游戏循环也可以使用
[`bda_gui_raw_event_fetch()`](raw_input_event_api.md) 的 `8/12/11` 事件维护生命周期。
两种事件路径只能选一种，不能同时消费。

## 游戏用法

推荐组合是“消息决定状态，坐标 getter 提供按住期间的最新位置”：

```c
static int touch_down;
static u16 touch_x;
static u16 touch_y;

static int game_proc(bda_handle_t frame, u32 message, u32 wparam, u32 lparam) {
    (void)wparam;

    if (message == BDA_MSG_TOUCH_COORDINATE) {
        touch_down = 1;
        bda_gui_touch_position(&touch_x, &touch_y);
        return 1;
    }
    if (message == BDA_MSG_TOUCH_RELEASE) {
        touch_down = 0;
        return 1;
    }
    if (message == BDA_MSG_WINDOW_TIMER && touch_down) {
        bda_gui_touch_position(&touch_x, &touch_y);
        /* 在这里更新虚拟摇杆、触摸按钮或指针。 */
        return 1;
    }
    return bda_gui_default_proc(frame, message, wparam, lparam);
}
```

窗口定时器可设为 10 ms。事件循环每轮只调用一次
`bda_gui_event_pump_frame_once()`；不要在消费 wake/timer 消息后立刻进行第二次空队列
poll，否则仍会重新进入阻塞等待。

仅做按钮命中时，消息 `lparam` 中的坐标已经足够。高速 getter 主要用于按住拖动、虚拟
摇杆、绘图和模拟器触摸映射。

## 真机验证

测试源码：`reverse/examples/gameboy_fast_touch_hardware_probe.c`

测试产物：`build/FastTouchV3.bda`

SHA-256：

```text
265cc332c4dbdc3ba5470a7301c06102fef82f17bfbee5ba7eaf7ff42eef0651
```

关键结果：

- 首次调用返回 `X=28 Y=236`，随后触摸过程中持续出现有效坐标变化。
- 运行到 `FINAL TICK=0x313`，约 19.675 秒，共完成 `9,831,102` 次坐标 getter 调用，
  记录到 `131` 次坐标变化，并正常通过 ESC 退出。
- 这约等于每秒 50 万次函数调用，证明 getter 本身不受 25 ms tick 限制。
- 调用次数不是触摸控制器的硬件采样率。坐标由固件后台更新，V3 没有测量 ADC 的真实
  采样频率或端到端延迟。

V3 同时证明固定地址 `0x80059f68` 在这台真机上不是研究镜像中的 pen GPIO helper；
公开 API 只通过运行时 GUI 函数表调用，不依赖固定代码地址。

## 边界

- 已验证单点逻辑坐标，不包含压力、多点触控和原始 ADC 值。
- 已验证高频重复读取和正常 ESC 退出，没有验证从多个线程并发调用。
- API 本身不提供触摸生命周期；应用必须选择窗口消息或原始输入事件作为生命周期源。
- 使用普通 Frame/控件时仍需继续泵窗口消息；原始输入流不能替代窗口退出和控件事件。
- 直接读取 GPIOC 的实验位在真机上始终不变，不能作为公开 pressed-state API。
