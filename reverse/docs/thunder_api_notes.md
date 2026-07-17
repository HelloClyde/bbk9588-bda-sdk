# 雷霆战机系统 API 与 SDK 用法

本文把 `fly-src-api/Fly原码` 中的 Rockchip GUI 源码名称、`雷霆战机.bda` 的实际
runtime table 调用和 `kj409588.bin` 对应 C200 固件实现对齐。完整 75-entry 清单见
`thunder_api_inventory.md`；本文重点说明哪些接口能作为 SDK API 使用，以及正确的
参数和 lifecycle。

## 样本和证据边界

样本哈希：

```text
雷霆战机.bda  SHA-256 75e389c5409360ae47fe4e04c20b6856c2d6d72016e3100c0da54373fcb14534
kj409588.bin   SHA-256 e86ceb0ab4cdf3075fc2086f59641ee12dd8de4d7fcbf2f2c0e24f20dee44321
```

`fly-src-api` 的两份二进制和仓库原机样本逐字节一致。源码不是这份 BDA 的精确
构建快照：BDA 时间是 2008-01-15，`fly.c` 顶部最新 revision 是 2008-06，
`game.c` 文件时间是 2010-02。还有两项可直接验证的分支差异：

- BDA 使用 `a:\应用\数据\游戏\Flydata.dat`、`FlySound.lib` 和
  `GamFlyInfo.Sav`；后续源码使用 `C:\APPDATA\fly\FlySave.bin`。
- BDA 有 23 次 SYS table 调用和完整打包音效簇；后续源码里的 `MixerSetChannel`
  已被注释掉。

因此，源码用于恢复 high-level 函数名、业务意图和参数含义；最终 table offset、
MIPS o32 ABI 和返回值均以 BDA 调用点与 C200 反汇编为准。

## 两层 API 模型

雷霆源码看到的是 `WindowCreate`、`DrawBmpIdEx`、`WinStartTimer` 等 GUI framework
函数。这些函数随应用静态链接，内部会组合多个 runtime table entry；它们不是
`GUI+offset` 的一一别名。

真正可供新 BDA 复用的是五张表：

```text
RES  0x81c16ba0  resource/state/trace
GUI  0x81c16ba4  window/event/draw
SYS  0x81c16ba8  packaged sound/device
FS   0x81c16bac  stdio-like filesystem
MEM  0x81c16bb0  firmware heap
```

扫描得到 291 次间接调用、75 个唯一入口：GUI 139/45，FS 72/16，MEM 43/2，
SYS 23/10，RES 14/2。72 个入口已有 SDK 名称；`FS+0x068` 是内部 file-object
block read，`SYS+0x050/+0x054` 是立即返回 1 的 stub，三者都刻意不公开 wrapper。

## 源码名称映射

| 原源码名称 | SDK 对应 | 结论 |
| --- | --- | --- |
| `MallocClass(T)` / `malloc` | `bda_alloc(size)` | 最终使用 `MEM+0x008`；检查 NULL。 |
| `FreeClass(p)` | `bda_free(p)` | 最终使用 `MEM+0x00c`；只释放 firmware heap pointer。 |
| `FSFileOpen(path, mode)` | `bda_fs_fopen_raw(path, mode)` | `FS+0x000`；用 `bda_fs_file_is_valid()` 判断高地址 handle。 |
| `FSFileRead(buf, len, file)` | `bda_fs_read_raw(file, buf, len)` | 底层 `FS+0x008` 实际是 `fread(buf,size,count,file)` ABI。 |
| `FSFileWrite(buf, len, file)` | `bda_fs_write_raw(file, buf, len)` | 底层 `FS+0x00c` 实际是 `fwrite` ABI。 |
| `FSFileClose(file)` | `bda_fs_close_raw(file)` | `FS+0x004`；每个成功 open 都必须 close。 |
| `FSFileDelete(path)` | `bda_fs_remove_raw(path)` | `FS+0x024`；破坏性操作。 |
| `WindowInvalidateWindow(win)` | `bda_gui_invalidate_window_like(win)` | `GUI+0x0e0` 发送内部 `0xb1` redraw message，不是立即 present。 |
| `WinSendCommand(win,event)` | `bda_gui_send(...)` | 最终同步调用 wndproc；原 framework 会先组装 command message，不能只替换函数名。 |
| `WindowCreate` / `WindowDestroy` | frame/window lifecycle wrapper 组合 | 不是单个 table API；需要 descriptor、callback、event loop 和正确释放顺序。 |
| `WinStartTimer` / `WinStopTimer` / `RockStopTimer` | 暂无直接兼容 wrapper | 属于静态链接 framework/OS timer 适配层，不能从单一 table offset 得出 ABI。 |
| `DrawPicture` / `DrawBmpIdEx` | draw context + resource + render helper 组合 | 依赖资源表和当前 window draw lifecycle，不等于 `bda_gui_blit_alt_like()`。 |
| `GuiDspGetWindowResProc` / `GetBmpHeadWidth` | 静态链接 resource helper | 提供资源定位和尺寸语义；未发现可安全替换的单一 runtime entry。 |
| `LCD_Update` / `RockOSSendMsg` | game shell display/message glue | BDA 实际表现为 draw-end、present guard、display pump 等序列。 |
| `Timer_GetCount` | 不作为本 BDA 证据 | 源码只在 `#ifdef __arm` 分支调用；9588 BDA 是 MIPS32 little-endian。 |
| `memcpy` / `memset` / `rand` / `abs` / `strncmp` | SDK/local libc helper | 这些是静态链接代码，不是五张 runtime table 的系统 API。 |

## 文件和内存

读取固定长度数据：

```c
int read_exact(const char *path, void *buffer, bda_size_t size) {
    int file = bda_fs_fopen_raw(path, "rb");
    int got;

    if (!bda_fs_file_is_valid(file)) {
        return 0;
    }
    got = bda_fs_read_raw(file, buffer, size);
    bda_fs_close_raw(file);
    return got == (int)size;
}
```

写存档时用 `"wb"`，检查写入数量，并保证所有失败分支都 close：

```c
int write_exact(const char *path, const void *buffer, bda_size_t size) {
    int file = bda_fs_fopen_raw(path, "wb");
    int wrote;

    if (!bda_fs_file_is_valid(file)) {
        return 0;
    }
    wrote = bda_fs_write_raw(file, buffer, size);
    bda_fs_close_raw(file);
    return wrote == (int)size;
}
```

雷霆同时使用 seek/tell/eof/error/clearerr、rename/chdir/mkdir/findfirst/findclose 等
FS 入口解析数据包和存档。完整参数、返回值和破坏性边界见 `fs_notes.md`，不要按
后续源码的三参数 `FSFileRead` 直接调用 table entry。

临时内存必须成对使用同一张 MEM 表：

```c
void *buffer = bda_alloc(size);
if (buffer != 0) {
    bda_memset(buffer, 0, size);
    /* use buffer */
    bda_free(buffer);
}
```

## Window 和消息

源码中的 `WindowCreate(..., proc_map, ...)` 会构造窗口、注册 callback map、启动
event/timer dispatch。SDK 的 `bda_gui_create_window_like()` 只是 control create
入口；顶层游戏 frame 还需要 `bda_gui_register_frame_desc_like()` 等完整 lifecycle。
不要把两者当成原 `WindowCreate` 的直接替换。

二进制中的根窗口过程位于 `0x81c0d23c`。它不是业务 `ProcMap` handler：
`message=1/2` 时会把事件写入 `0x81c17598..0x81c175a0`，`message=0x60` 时保存
frame/current-draw；`0x81c0fdb8` 再从桥接区提取事件。源码里的 `WM_KEY` 是这之后
由静态 child-window framework 生成的消息。只复制 frame descriptor 或把
`0x0844` 写进新的 wndproc 分支，不足以复制雷霆的实体键行为。

在已经有效的 window callback 中，请求 redraw 可以使用：

```c
bda_gui_invalidate_window_like(window);
```

它只发送内部 `0xb1`；真正绘制发生在后续 message dispatch。同步 command 需要
明确目标 wndproc 的 message contract 后再调用：

```c
bda_gui_send(window, BDA_MSG_COMMAND_LIKE, command_id, command_arg);
```

原源码 `WinSendCommand(win, EV_ItemSelect)` 会由 framework 组装参数，不能假设
`EV_ItemSelect` 总是直接放在 `wparam`。

## Draw context 和图元

本次从雷霆调用点和 C200 实现补齐了以下 SDK API：

```c
int bda_gui_display_metric_like(bda_handle_t context, u32 metric);
int bda_gui_display_pixel_bytes_like(void);
bda_handle_t bda_gui_compat_context_create_like(bda_handle_t source);
void *bda_gui_select_draw_object_like(bda_handle_t context, void *object);
void bda_gui_move_to_like(bda_handle_t context, s32 x, s32 y);
void bda_gui_line_to_like(bda_handle_t context, s32 x, s32 y);
void bda_gui_circle_like(bda_handle_t context, s32 cx, s32 cy, s32 radius);
void bda_gui_rectangle_like(bda_handle_t context, s32 left, s32 top, s32 right, s32 bottom);
void *bda_gui_current_font_like(bda_handle_t context);
int bda_gui_font_cell_width_like(bda_handle_t context);
int bda_gui_font_cell_height_like(bda_handle_t context);
```

`GUI+0x358` 的使用方式与 select-object 一致：保存旧对象，绘制，再恢复旧对象。
调用者必须已经持有来自有效 frame callback 的 context 和 firmware draw object：

```c
void *old_object = bda_gui_select_draw_object_like(context, draw_object);

bda_gui_move_to_like(context, x0, y0);
bda_gui_line_to_like(context, x1, y1);
bda_gui_circle_like(context, center_x, center_y, radius);
bda_gui_rectangle_like(context, left, top, right, bottom);

bda_gui_select_draw_object_like(context, old_object);
```

`bda_gui_compat_context_create_like(source)` 会分配一个 `0xd4` byte compatible
draw context，并复制 source 的 drawable bounds/backend。使用完成后调用
`bda_gui_surface_flush_like(context)`；后者会 flush 并释放 context，不能再次复用。

这些 API 的 ABI 已静态确认，但没有完整 shell 时仍不安全。`context=0` 只表示 C200
选择 default draw context，不表示 bare `bda_main()` 已拥有可显示的窗口。

## 全屏 buffer 路径

雷霆三次调用 `GUI+0x300(0,6)`。其中两次按以下公式分配全屏临时 buffer：

```text
size = 320 * 240 * display_metric(0, 6) + 10
```

这证明 metric 6 是该显示 backend 的像素字节因子。对应 SDK helper 是：

```c
/* BDA_GUI_DISPLAY_METRIC_PIXEL_BYTES_LIKE == 6 */
int pixel_bytes = bda_gui_display_pixel_bytes_like();
```

原机完整序列是：

```text
GUI+0x3f8(0, 0, 240, 320, buffer)
GUI+0x6e0()
GUI+0x400(0, 0, 240, 320, buffer)
MEM+0x00c(buffer)
```

这不是可直接复制到 no-template BDA 的 public framebuffer API。该路径依赖前置
message `0x60` 取得的 object/context、render helper、draw-end 和 present guard
状态。真机已经确认，脱离 shell 单独调用 `+0x074/+0x400` 会逐块 flip 后死机。

## 打包音效

BDA 从 `A:\应用\数据\游戏\FlySound.lib` 读取最多 `0x14` 个 chunk，每个 descriptor
间距 `0x20` byte。后续源码没有这段 active code，因此声音 ABI 只按 BDA+C200 命名：

| SDK API | 参数/行为 |
| --- | --- |
| `bda_sys_audio_attenuation_set_like(attenuation)` | 写 pending PCM attenuation；下一次 raw write 应用。 |
| `bda_sys_audio_attenuation_get_like()` | 返回 effective attenuation `0..96`，步进 3。 |
| `bda_sys_package_sound_op58_like(descriptor)` | 初始化/启动 descriptor，成功置全局 handle 并返回 1。 |
| `bda_sys_package_sound_op5c_like(slot, descriptor, a2, flags)` | 四参数 descriptor 操作；slot 和 flags 业务语义仍未完全命名。 |
| `bda_sys_package_sound_op60_like()` | 状态从 0 置 1 时返回 1。 |
| `bda_sys_package_sound_op64_like()` | 状态从 1 清 0 时返回 1。 |
| `bda_sys_package_sound_op68_like()` | 关闭全局 handle 并清理 package sound 状态。 |

`SYS+0x040/+0x044` 已由 `GameVolV1` 动态确认为共享 PCM attenuation API，不属于
package sound descriptor 生命周期。`SYS+0x050/+0x054` 都是 `return 1` stub，
不要作为 load/init/free API 调用。
在 descriptor 字段和 slot 语义完成真机 probe 前，这组接口只适合复刻原机包声音，
不适合作为新游戏的 high-level audio API。新应用优先使用已单独记录的 raw audio
路径，或暂时不启用声音。

## 复现分析

```powershell
python reverse\bda_table_globals.py "fly-src-api\雷霆战机.bda"
python reverse\bda_table_call_scan.py "fly-src-api\雷霆战机.bda"
python reverse\bda_sdk_usage.py "fly-src-api\雷霆战机.bda" `
  --title "雷霆战机.bda" `
  -o docs\thunder_api_inventory.md
python reverse\c200_api_disasm.py --table GUI --offset 0x300 --size 0x240
```

逆向证据、具体调用地址和音效包分析还保留在
`reverse/reports/thunder_bda_report.md`。
