# 触摸按下/抬起 API

本文只收录已经由独立 BDA 动态验证的触摸按下状态查询。坐标读取尚未完成动态闭环，
不属于本文的已验证范围。

## API 定义

```c
int bda_touch_pressed_9588(void);
```

该 wrapper 无参数：

- 返回非 0：触摸屏当前处于按下状态。
- 返回 0：触摸屏当前处于抬起状态。

## 固件来源

该函数绑定 `kj409588/C200` 固件地址 `0x80059f68`，不是 runtime table entry。
原始 C200 实现读取 `0xb0010100` 的 `0x00040000` pen GPIO 位，并将 active-low
电平转换为 `0/1`。当前 BBK 9588 模拟器的运行时补丁把同一函数改为读取固件触摸
latch，保持相同返回语义。

因此名称中保留 `9588`：不要假定其他固件版本在同一地址提供相同 ABI。

## 基本用法

```c
while (!bda_touch_pressed_9588()) {
    bda_sys_delay(1);
}

while (bda_touch_pressed_9588()) {
    bda_sys_delay(1);
}
```

第一段等待按下，第二段等待抬起。循环中应保留短延时，避免无意义地占满 CPU。
如果业务只关心一次点击，应完成按下和抬起两个阶段后再触发动作，避免一次长按重复执行。

完整示例：`sdk/api/examples/touch_press_demo.c`。

## 动态验证

测试 BDA：`build/TouchPress.bda`

验证过程：

1. 把示例 C blob 追加到原版 `雷霆战机.bda` 的 BSS 之后，只 patch app-init 跳转。
2. 模拟器使用原版 `bbk9588_nand.bin` 创建 worker copy。
3. 只通过 `/api/files/delete` 和 `/api/files/import` 替换 worker 中的测试 BDA。
4. 进入测试应用，关闭初始提示后向屏幕中心注入按下，再注入抬起。
5. BDA 显示 `PRESS + RELEASE OK`。
6. 停止模拟器后，从 worker NAND 导出 `TOUCHPRESS.TXT`，内容为
   `PRESS=1 RELEASE=1`。

实际运行截图：

![TouchPress.bda 识别按下和抬起](assets/touch_press_bda_verified.png)

最终测试 BDA SHA-256：

```text
e9d1347306177c200531ebbbd773a688fa309ab57c08d9129abedc64b40edd46
```

## 注意点与边界

- 这是固件固定地址 API，不是 GUI/SYS 表项；升级或更换固件后必须重新核对地址和实现。
- 本次验证覆盖按下和抬起两个电平，不包含压力、移动轨迹、多点触控或中断回调。
- `GUI+0x6c0 -> 0x8001a3a0` 静态上是读取 raw/calibration globals、写两个
  `u16 *` 输出的坐标转换器。自建 BDA 只得到裁剪上限 `(239,319)`，但当时没有在
  同一次按压中同步采集 raw globals，因此动态验证无结论；它没有进入 verified。
- 原机 BDA 的 window procedure 会处理 `message=1/2` 并从 `lparam` 拆坐标。
  先前自建 frame 的 probe 保存了 `g_frame`，却通过旧 helper 固定轮询 `handle=0` 的
  global/default slot；“没有收到消息”的结果属于验证夹具错误，不能否定原机回调坐标 ABI。
