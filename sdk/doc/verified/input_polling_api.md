# 实体键轮询 API

已验证 helper 与常量：

```c
bda_gui_input_packet_key_pressed(packet, keycode);
bda_gui_key_pressed(keycode);
BDA_KEY_UP; BDA_KEY_DOWN; BDA_KEY_LEFT; BDA_KEY_RIGHT;
BDA_KEY_ENTER; BDA_KEY_ESCAPE;
BDA_INPUT_PACKET_UP_INDEX; BDA_INPUT_PACKET_DOWN_INDEX;
BDA_INPUT_PACKET_LEFT_INDEX; BDA_INPUT_PACKET_RIGHT_INDEX;
BDA_INPUT_PACKET_ENTER_INDEX; BDA_INPUT_PACKET_ESCAPE_INDEX;
```

本文只记录已经通过独立 BDA 动态验证的 `GUI+0x5d4` 实体键轮询接口。该接口不要求
创建窗口、注册 window procedure 或运行雷霆战机的私有事件桥。

## API 定义

```c
#define BDA_GUI_INPUT_PACKET_SIZE 6u

typedef struct bda_gui_input_packet {
    u8 bytes[BDA_GUI_INPUT_PACKET_SIZE];
} bda_gui_input_packet_t;

int bda_gui_input_packet(bda_gui_input_packet_t *packet);
int bda_gui_input_packet_key_pressed(
    const bda_gui_input_packet_t *packet,
    u32 keycode
);
int bda_gui_key_pressed(u32 keycode);
```

对应固件表项：

```text
GUI +0x5d4  C200 0x8001b518
```

固件会先清零 6 byte packet，再采样硬件输入状态。当前有任意支持键按下时返回非零；
对应 packet byte 写为 `1`，未按下写为 `0`。

## 已验证映射

```text
packet[0]  Right  BDA_KEY_RIGHT   0x6a
packet[1]  Left   BDA_KEY_LEFT    0x69
packet[2]  Down   BDA_KEY_DOWN    0x6c
packet[3]  Up     BDA_KEY_UP      0x67
packet[4]  Esc    BDA_KEY_ESCAPE  0x01
packet[5]  Enter  BDA_KEY_ENTER   0x1c
```

这些 `BDA_KEY_*` 值是 BDA 侧使用的 Linux input keycode。模拟器网页前端发送的
`4..10` 是前端注入协议，不是 BDA API 的 keycode，应用不能直接使用它们。

## 推荐用法

一次采样后可查询多个键：

```c
bda_gui_input_packet_t packet;

(void)bda_gui_input_packet(&packet);
if (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_LEFT)) {
    move_cursor_left();
}
if (bda_gui_input_packet_key_pressed(&packet, BDA_KEY_ENTER)) {
    open_current_item();
}
```

只查询一个键时可以使用便捷 wrapper：

```c
if (bda_gui_key_pressed(BDA_KEY_ESCAPE)) {
    return 0;
}
```

若同一帧需要检查多个键，不要连续调用多次 `bda_gui_key_pressed()`；每次调用都会
重新采样。应先调用一次 `bda_gui_input_packet()`，再查询同一个 packet。

## 状态和去抖

packet 表示当前电平状态，不是按下边沿或消息队列。按住实体键时对应 byte 会持续为 `1`。
菜单或游戏通常需要自己保存上一帧状态，或在处理后等待该键释放：

```c
do {
    (void)bda_gui_input_packet(&packet);
    bda_sys_delay(1);
} while (bda_gui_input_packet_key_pressed(&packet, keycode));
```

多键同时按下时，packet 可以分别查询；若应用只处理一个键，优先级和 first-match 顺序
由应用自行定义。

## 验证记录

静态证据：

- `Eros方块.bda` 的 `0x81c02284` 清理并查询 6-byte packet，再映射为 keycode；
  调用点位于 `0x81c06488` 一带。
- C200 `GUI+0x5d4` 的目标为 `0x8001b518`，会清零 packet 并采样输入 MMIO。

独立测试 BDA：`sdk/api/examples/key_msgbox_demo.c`

构建产物：`build/KeyInput.bda`

测试流程：

1. 模拟器以原版 NAND 为只读来源并创建运行 worker copy。
2. 通过模拟器文件接口把测试 BDA 放入 `/应用/程序/雷霆战机.bda`。
3. BDA 只调用 `GUI+0x5d4` 轮询，检测后等待释放，再用 MsgBox 显示键名。
4. 分别注入 Right、Down、Left、Up、Enter、Esc，画面依次显示对应键名。
5. 测试结束后删除运行 worker/checkpoint，不修改原版 NAND。

六个键均已形成可见闭环。初版 packet 索引曾把 Right 和 Down 对调，动态测试出现
“按 Right 显示 DOWN”，修正为本文布局后六键逐项通过。

## 未覆盖边界

- 本次验证不证明 `BDA_MSG_KEYDOWN_LIKE`、自建 window procedure 或 ProcMap ABI 可用。
- 本次不依赖、也不公开雷霆战机 `0x81c0fdb8` 私有事件桥。
- `SYS+0x088` 是另一套 raw keycode query，其 `4..10` 返回值尚未在本文验证。
- 本次验证对象是当前 C200 固件和模拟器输入路径；其他固件版本应重新跑同一测试 BDA。
