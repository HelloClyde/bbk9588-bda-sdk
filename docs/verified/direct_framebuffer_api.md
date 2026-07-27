# C200 直接 Framebuffer API

验证环境：

- `bbk9588-emulator-v0.1.5`，8013 端口，完整 NAND 冷启动。
- BBK 9588 / C200 真机，由 `ps-for9588` R32 及后续版本完成方向、颜色、持续刷新、
  模态菜单和退出生命周期验证。

公开示例：
`example/graphics/direct_framebuffer/direct_framebuffer_demo.c`。

## 公开接口

```c
#include "bda_graphics.h"

#define BDA_GUI_FRAMEBUFFER_WIDTH 240u
#define BDA_GUI_FRAMEBUFFER_HEIGHT 320u
#define BDA_GUI_FRAMEBUFFER_STRIDE_BYTES 480u
#define BDA_GUI_FRAMEBUFFER_SIZE_BYTES \
    (BDA_GUI_FRAMEBUFFER_STRIDE_BYTES * BDA_GUI_FRAMEBUFFER_HEIGHT)

typedef struct bda_gui_framebuffer {
    volatile u16 *pixels;
    u32 width;
    u32 height;
    u32 stride_bytes;
    u32 rotate_180;
} bda_gui_framebuffer_t;

int bda_gui_framebuffer_acquire(
    bda_gui_framebuffer_t *framebuffer
);

int bda_gui_framebuffer_present_rgb565(
    const bda_gui_framebuffer_t *framebuffer,
    const u16 *source
);
```

两个函数均以 `0` 表示成功，`-1` 表示参数错误或当前固件布局不在已验证范围内。
`source` 必须是 32-bit 对齐、逐行紧密排列的 240×320 RGB565 缓冲，共
`153600` byte。

`bda_gui_framebuffer_acquire()` 不分配显存。它取得固件当前扫描缓冲，并只在以下条件
全部成立时返回成功：

- GUI `+0x6b0` 返回 KSEG0 或 KSEG1 地址。
- 地址 32-bit 对齐、物理地址非零，且完整 framebuffer 不越过 KSEG 物理地址范围。
- GUI `+0x738` 返回 `0x130` 或 `0x131`。

SDK 不固定 framebuffer 物理地址；成功后的 `pixels` 指向系统返回地址所对应的
uncached KSEG1 alias。尺寸固定为 240×320，stride 固定为 480 byte。`0x130`
表示提交时需要旋转 180 度，`0x131` 表示正向复制。公开 wrapper 负责方向补偿、
两像素 32-bit 写入和结束时的 MIPS `sync`。

## 使用方式

在 frame 注册并激活后获取一次 framebuffer：

```c
bda_gui_framebuffer_t framebuffer;

bda_memset(&framebuffer, 0, sizeof(framebuffer));
if (bda_gui_framebuffer_acquire(&framebuffer) == 0) {
    if (bda_gui_framebuffer_present_rgb565(
            &framebuffer, screen_pixels
        ) != 0) {
        /* Disable the direct path and use the firmware renderer. */
    }
}
```

应用应先在自己的 CPU 缓冲中完成整帧合成，再调用一次提交函数。不要在扫描缓冲中
逐图元绘制，也不要写 LCD MMIO、DMA descriptor 或接口返回范围以外的地址。

不匹配上述布局时必须回退 `bda_gui_render_picture()` 或 compatible-context 路径。
不得绕过 GUI API 并自行填写任意 framebuffer 地址。

## 动态证据

独立 `DirectFramebuffer.bda` 在 8013 完整 NAND 中从系统菜单启动。测试图每 100 ms
更新一次全屏色带和棋盘，四角分别写入红、绿、蓝、黄方向标记。模拟器报告：

```text
framebuffer = 0xa1f82000
format = rgb565
width = 240
height = 320
stride_pixels = 240
orientation = rot180
nonzero_pixels = 76800
unique_pixel_values = 10
```

![直接 framebuffer 验证画面](assets/direct_framebuffer_demo.png)

截图中四角、色带和棋盘方向均符合 CPU source。移除固定物理地址校验并重建后，
在全新 NAND 中连续采集的 4 张画面哈希均不相同；实体 Escape 触发
`frame_stop -> frame_release`，随后只在关闭阶段运行事件泵，程序成功回到系统菜单。

验证 BDA SHA-256：

```text
5ebf5d14d0fbb7ee257001117a24ee57077672967bf22de17bc0ad263cc77462
```

截图 SHA-256：

```text
8e10fad83c470960eaaa621d2b03b2848f3efb97282b540a7cb1d18a5a60dbf7
```

真机交叉证据来自 `ps-for9588`。该项目从 GUI API 取得 `0xa1f82000`，查询值为
`0x130`，连续运行约 904 秒后正常退出；其记录的整帧提交平均值由固件 picture
路径的 22.189 ms 降至直接复制的 3.973 ms。原机 `GAMEBOY.BDA` 的逐帧路径也通过
GUI `+0x6b0` 获取屏幕指针，并根据 `+0x738` 在正向和 180 度复制之间选择。

## 生命周期与限制

- 这是 LCD DMA 持续扫描的单缓冲，不是垂直同步 page flip。CPU 写入期间仍可能出现
  撕裂；整帧连续 32-bit 复制只能明显缩短风险窗口，不能保证完全无撕裂。
- 固件帮助页、确认框和文件选择器运行期间，应用必须停止写 framebuffer。同步模态
  调用返回并恢复应用 frame 后才能继续提交。
- `bda_gui_raw_event_fetch()` 适合直接 framebuffer 游戏循环，但运行期不能同时调用
  `bda_gui_event_pump_frame_once()`。事件泵只应在停止 raw 轮询并请求关闭 frame 后
  用于接收 detach。
- 当前只公开完整 240×320 RGB565 提交，不公开局部 dirty rect、其他 stride、其他
  像素格式，也不接受调用者自行指定的 framebuffer 地址。
- 模拟器验证不能替代每个新固件版本的真机校验；指针、布局或方向查询不匹配时必须
  回退。
