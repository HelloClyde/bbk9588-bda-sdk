# 图形图元 API

本文只记录已经通过独立 BDA 动态验证的 frame 绘制链和图元接口。图元集合最初在当前
C200 固件与模拟器显示后端验证；其中 V11 使用的画点、矩形和文字子集后来又在真机的
完整窗口生命周期内通过。真机证据和退出顺序见 `touch_window_lifecycle_api.md`。

## 已验证接口

```c
bda_handle_t bda_gui_register_frame_desc(bda_frame_desc_t *descriptor);
int bda_gui_frame_activate(bda_handle_t handle, u32 mode);
bda_handle_t bda_gui_current_draw(bda_handle_t handle);
void bda_gui_end_draw(bda_handle_t draw_context);
int bda_gui_default_proc(
    bda_handle_t handle,
    u32 message,
    u32 wparam,
    u32 lparam
);
int bda_gui_event_pump_frame_once(
    bda_gui_message_t *message,
    bda_handle_t frame
);
int bda_gui_frame_stop(bda_handle_t handle);
int bda_gui_frame_release(bda_handle_t handle);
void *bda_gui_draw_object_create(u32 kind);
void *bda_gui_select_draw_object(bda_handle_t context, void *object);

int bda_gui_draw_guard_begin(void);
int bda_gui_draw_guard_end(void);
int bda_gui_rgb(bda_handle_t context, u32 red, u32 green, u32 blue);
int bda_gui_put_pixel(bda_handle_t context, s32 x, s32 y, u32 color);
int bda_gui_put_pixel_rgb(
    bda_handle_t context,
    s32 x,
    s32 y,
    u32 red,
    u32 green,
    u32 blue
);
void bda_gui_move_to(bda_handle_t context, s32 x, s32 y);
void bda_gui_line_to(bda_handle_t context, s32 x, s32 y);
void bda_gui_circle(bda_handle_t context, s32 center_x, s32 center_y, s32 radius);
void bda_gui_rectangle(
    bda_handle_t context,
    s32 left,
    s32 top,
    s32 right,
    s32 bottom
);
int bda_gui_set_text_mode(bda_handle_t context, u32 mode);
int bda_gui_set_text_color(bda_handle_t context, u32 color);
int bda_gui_draw_text(
    bda_handle_t context,
    s32 x,
    s32 y,
    const char *text,
    s32 extra
);
```

## 固件表项

```text
GUI +0x074  draw/present guard        C200 0x800d48a8
GUI +0x084  register frame            C200 0x800cc1c8
GUI +0x098  activate frame            C200 0x800cc4ec
GUI +0x2fc  draw object table         C200 0x800bd36c
GUI +0x304  current draw context      C200 0x800bceec
GUI +0x338  text/background mode      C200 0x800b2c94
GUI +0x33c  text color                C200 0x800b2cac
GUI +0x358  select draw object        C200 0x800b2d40
GUI +0x368  put pixel, packed color   C200 0x800b68c0
GUI +0x36c  put pixel, direct RGB     C200 0x800b6af8
GUI +0x378  RGB conversion            C200 0x800bc2e0
GUI +0x37c  line to                   C200 0x800b715c
GUI +0x380  move to                   C200 0x800bc328
GUI +0x388  circle                    C200 0x800b7494
GUI +0x38c  rectangle outline         C200 0x800b76d8
GUI +0x4f0  draw text                 C200 0x800c0d40
```

同一个动态验证 BDA 还实际执行了 `GUI+0x030/+0x050/+0x054` 事件泵、
`GUI+0x08c` 默认窗口过程以及 `GUI+0x088/+0x04c` frame 收尾链。V11 真机进一步确认
收尾链之后必须等待 event poll 结束，再调用 `GUI+0x17c`。这些接口只按已验证组合和
参数使用；不要把其中任一表项推断成更广泛的窗口管理 API。

`GUI+0x36c` 的 ABI 是六参数 `context,x,y,r,g,b`。`r/g/b` 只使用低 8 位，
第五、第六参数按 MIPS o32 ABI 放在 caller `stack+0x10/+0x14`。固件将 RGB 转成当前
backend 颜色后，和 `GUI+0x368` 一样通过单像素 backend 提交。

## 最小绘制顺序

frame descriptor 必须在整个 frame 生命周期内保持有效。当前验证使用 240x320 竖屏，
descriptor 字段沿用原机游戏布局：

```c
static bda_handle_t frame;
static bda_handle_t draw;

descriptor.style = 0x08000000u;
descriptor.title = 0;
descriptor.wndproc = window_proc;
descriptor.height = 240;
descriptor.width = 320;
descriptor.surface = (u32)bda_gui_draw_object_create(15);

frame = bda_gui_register_frame_desc(&descriptor);
bda_gui_frame_activate(frame, 0x100);
draw = bda_gui_current_draw(frame);
```

在 window procedure 收到 `BDA_MSG_DRAW_CONTEXT_ATTACH` (`0x60`) 时，只在当前没有
同一 owner 的 draw context 时调用 `bda_gui_current_draw(handle)`。收到
`BDA_MSG_DRAW_CONTEXT_DETACH` (`0x66`) 时调用 `bda_gui_end_draw(draw)`；退出前若 detach
没有到达，还要执行一次兜底释放。绘制前选择固件 draw object，结束后恢复：

```c
void *object = bda_gui_draw_object_create(7);
void *old_object;
u32 cyan;

bda_gui_draw_guard_begin();
old_object = bda_gui_select_draw_object(draw, object);

cyan = (u32)bda_gui_rgb(draw, 20, 145, 170);
bda_gui_put_pixel(draw, 20, 50, cyan);
bda_gui_put_pixel_rgb(draw, 21, 50, 235, 165, 35);

bda_gui_move_to(draw, 20, 130);
bda_gui_line_to(draw, 220, 130);
bda_gui_circle(draw, 60, 185, 34);
bda_gui_rectangle(draw, 126, 151, 218, 219);

bda_gui_set_text_mode(draw, 1);
bda_gui_set_text_color(draw, cyan);
bda_gui_draw_text(draw, 40, 10, "GRAPHICS API", -1);

bda_gui_select_draw_object(draw, old_object);
bda_gui_draw_guard_end();
```

`draw_text` 的 `extra < 0` 路径按 NUL 结尾字符串计算长度。传入的字符串必须在调用期间
保持有效；中文文本应使用固件可识别的 GBK byte string。

## 图元语义

- `move_to` 只更新 context 当前点；可见线段由后续 `line_to` 绘制。
- `line_to` 会把 endpoint 保存为新的当前点，因此可以连续绘制折线。
- `circle` 参数是圆心和半径。
- `rectangle` 参数是 `left,top,right,bottom`，不是 `x,y,width,height`。
- 当前 `kind=7` draw object 的动态结果是矩形轮廓，不是填充矩形。
- `set_fill_color_like` 只确认会写 context 字段；本次没有证明它能让 rectangle 填充，
  因此不把“填充矩形”列入已验证能力。
- `bda_gui_put_pixel()` 的 color 应来自同一 context 的 `bda_gui_rgb()`；不要硬编码为
  RGB565。
- `bda_gui_put_pixel_rgb()` 省略显式颜色转换，适合少量点或测试。大面积逐像素填充可用，
  但效率明显低于尚未完成生命周期验证的 bitmap/render 路径。

## 验证记录

测试源码：`example/graphics/primitives/graphics_primitives_demo.c`

预编译产物：`example/graphics/primitives/GraphicsPrimitives.bda`

测试过程：

1. 把 C blob 追加到原版 `雷霆战机.bda` 的 BSS 之后，只 patch app-init 跳转。
2. 模拟器从原版 NAND 创建 worker copy。
3. 通过 `/api/files/delete` 和 `/api/files/import` 在 worker 中替换测试 BDA。
4. 导出 worker 中的 BDA，SHA-256 与本地构建产物一致。
5. 从“玩游戏”进入应用，画面显示青色和橙色实心像素块、白色矩形轮廓、水平线、
   圆、下方像素棋盘和 `GRAPHICS API` 等文字。

实际运行截图：

![GraphicsPrimitives.bda 在 BBK 9588 模拟器中的验证画面](assets/graphics_primitives_bda_verified.png)

截图中的可见证据：

- 左上青色块：`bda_gui_rgb()` 转换颜色后，由 `bda_gui_put_pixel()` 逐点绘制。
- 右上橙色块：`bda_gui_put_pixel_rgb()` 直接使用 RGB 分量逐点绘制。
- 两个色块外框和右侧大框：`bda_gui_rectangle()` 的轮廓输出。
- 中部水平线：`bda_gui_move_to()` 与 `bda_gui_line_to()`。
- 左下圆形：`bda_gui_circle()`。
- `GRAPHICS API`、`RECT`、`FILL` 等文字：text mode、text color 和
  `bda_gui_draw_text()`。
- 下方黄白棋盘：两种单像素 API 在同一区域交叉绘制。

青色块使用 `RGB转换 + GUI+0x368`，橙色块使用 `GUI+0x36c` 直接 RGB。两条路径都
形成可见彩色输出。线、圆、rectangle 和 text 也在同一有效 draw context 中显示。

最终测试 BDA SHA-256：

```text
1abe3668bb922c8ba9919af85ad1114a675fd7ffee30605e2d19ef22bb810449
```

加入 fixed draw slot 归还逻辑后，当前公共预编译产物
`example/graphics/primitives/GraphicsPrimitives.bda` 的 SHA-256 为：

```text
080775136337a21b7b9b5f3aa12cde037b7c5eed3cc1676d87635e02acb5313a
```

## 未覆盖边界

- 首次完整场景绘制已验证；同一 context 上反复整屏逐像素重绘出现局部中间状态，
  本文不承诺可直接把该流程当双缓冲游戏循环。
- `GUI+0x334` 不等于已验证的 fill-rectangle API。
- `GUI+0x3f8/+0x400` 裸 framebuffer blit 仍属于失败 probe，不能由本文推导为稳定 API。
- bitmap、VX 和离屏 compatible context 仍需单独验证；V11 已真机确认 frame 能关闭，
  但其原始代码未归还 fixed draw slot，不能作为完整 draw 生命周期的依据。
- bare `bda_main()` 中传 `context=0` 不在验证范围；必须先建立有效 frame/draw context。
