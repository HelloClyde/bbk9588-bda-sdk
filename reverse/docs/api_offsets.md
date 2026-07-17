# BBK 9588 原生 BDA API offset 速查

本文是手写速查索引，面向开发者理解 `bda_sdk.h` 里的 offset、调用约定和风险边界。

更完整、可再生成的表请优先看：

- `api_catalog.md`：由 `reverse/bda_api_catalog.py` 生成，合并原机 BDA call inventory 和 SDK 命名。
- `system_api_tables.md`：由 `reverse/c200_api_tables.py` 从本地 `C200.bin` 直接导出，给出 entry VA 和 C200 function VA。
- `c200_api_function_notes.md`：关键 function 的 disasm 结论和开发建议。

## Runtime Table Pointer

`C200.bin` 会把一组 table seeds 复制到 `0x81c00000`，原生 BDA 从这里取得 system API：

```text
0x81c00004  GUI/window/control/draw table
0x81c00008  FS/file/resource stream table
0x81c0000c  SYS/device/audio/time table
0x81c00010  MEM/CRT table
0x81c00014  RES/resource/trace table
```

SDK 中对应：

```c
void *bda_gui_table(void);
void *bda_fs_table(void);
void *bda_sys_table(void);
void *bda_mem_table(void);
void *bda_res_table(void);
```

low-level table call helper：

```c
int bda_call0(void *table, u32 offset);
int bda_call1(void *table, u32 offset, u32 a0);
int bda_call2(void *table, u32 offset, u32 a0, u32 a1);
int bda_call3(void *table, u32 offset, u32 a0, u32 a1, u32 a2);
int bda_call4(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3);
int bda_call5(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3, u32 a4);
int bda_call6(void *table, u32 offset, u32 a0, u32 a1, u32 a2, u32 a3, u32 a4, u32 a5);
```

这些 helper 不做 ABI validation。除非正在做 controlled probe，或需要复刻已知原机 call site，
否则优先使用 `bda_sdk.h` 里已经命名的 wrapper。
MIPS o32 只提供 `a0..a3` 四个参数寄存器；`bda_call5()` / `bda_call6()` 的额外参数
会按 C ABI 放到 caller stack，正好覆盖 C200 中读取 `stack+0x10`、`stack+0x14` 的入口。

## 当前最适合开发者使用的 Wrapper

### Message Box

```text
GUI +0x2b8  BDA_GUI_MSGBOX
system function VA: 0x800c6544
actual argument order: parent, message, title, flags
```

SDK wrapper：

```c
int bda_msgbox(const char *title, const char *message);
int bda_msgbox_ex(void *parent, const char *title, const char *message, u32 flags);
```

`bda_msgbox_ex()` 会把开发者更自然的 `title, message` 顺序转换成系统实际的
`message, title` 顺序。no-template `hello_msgbox.c` 已经用它做 SDK smoke。

### 基础 Memory

```text
MEM +0x000  BDA_MEM_TRACK_ALLOC_LIKE  system function VA 0x80058574
MEM +0x004  BDA_MEM_TRACK_FREE_LIKE   system function VA 0x80058618
MEM +0x008  BDA_MEM_ALLOC             system function VA 0x80007648
MEM +0x00c  BDA_MEM_FREE              system function VA 0x800067f4
MEM +0x010  BDA_MEM_CALLOC_LIKE  system function VA 0x800065bc
MEM +0x014  BDA_MEM_REALLOC_LIKE  system function VA 0x800077b0
MEM +0x01c  BDA_MEM_TRACK_BEGIN_LIKE   system function VA 0x80058554
MEM +0x020  BDA_MEM_TRACK_REPORT_LIKE  system function VA 0x8005868c
MEM +0x024  BDA_MEM_TRACK_FINISH_LIKE  system function VA 0x80058750
MEM +0x028  BDA_MEM_TRACK_RETAIN_LIKE  system function VA 0x80058820
MEM +0x02c  BDA_MEM_TRACK_RELEASE_LIKE system function VA 0x800588b8
```

SDK wrapper：

```c
void *bda_alloc(bda_size_t size);
void bda_free(void *ptr);
void *bda_track_alloc_like(bda_size_t size);
void bda_track_free_like(void *ptr);
void bda_mem_track_begin_like(u32 free_on_finish);
int bda_mem_track_report_like(u32 summary_only);
void bda_mem_track_finish_like(void);
void *bda_mem_track_retain_like(void *ptr);
void bda_mem_track_release_like(void *ptr);
void *bda_calloc_like(bda_size_t count, bda_size_t size);
void *bda_realloc_like(void *ptr, bda_size_t new_size);
void *bda_memcpy(void *dst, const void *src, bda_size_t n);
void *bda_memset(void *dst, int value, bda_size_t n);
bda_size_t bda_strlen(const char *s);
```

`bda_memcpy()`、`bda_memset()`、`bda_strlen()` 是 SDK 本地实现，不依赖 libc。
`bda_track_alloc_like()`/`bda_track_free_like()` 对应 C200 tracked wrapper；
普通开发优先使用 `bda_alloc()`/`bda_free()`。
`bda_mem_track_begin_like()`/`bda_mem_track_report_like()`/`bda_mem_track_finish_like()`
是 firmware heap tracking debug helper；`finish` 在 `free_on_finish != 0` 时可能释放
仍记录的 pointer。`bda_mem_track_retain_like()`/`bda_mem_track_release_like()` 操作
tracked record table 的 refcount-like 字段，release 递减到 0 时也可能释放 pointer。
`bda_calloc_like()` 会按 `count * align4(size)` 分配并清零；不要依赖它处理 overflow。
`bda_realloc_like()` 只适用于 firmware heap pointer；`ptr=0` 可作为 alloc，
`new_size=0` 会释放旧 pointer 并返回 0。

### 基础 File IO

```text
FS +0x000  BDA_FS_OPEN   fopen 类
FS +0x004  BDA_FS_CLOSE  fclose 类
FS +0x008  BDA_FS_READ   fread 类
FS +0x00c  BDA_FS_WRITE  fwrite 类
FS +0x010  BDA_FS_SEEK   fseek 类
FS +0x014  BDA_FS_TELL   ftell 类；检查 file+0x48 index，返回 file+0x44
FS +0x018  BDA_FS_EOF_LIKE          feof-like；检查当前位置是否到文件末尾
FS +0x01c  BDA_FS_ERROR_LIKE        ferror-like；检查 file error flag
FS +0x020  BDA_FS_CLEAR_ERROR_LIKE  clearerr-like；清 file error flag
FS +0x024  BDA_FS_REMOVE            remove/unlink；删除文件
FS +0x028  BDA_FS_RENAME_LIKE       rename/move-like；old_path,new_path
```

SDK wrapper：

```c
int bda_fs_fopen_raw(const char *path, const char *mode);
int bda_fs_close_raw(int file);
int bda_fs_fread_raw(void *buffer, bda_size_t size, bda_size_t count, int file);
int bda_fs_fwrite_raw(const void *buffer, bda_size_t size, bda_size_t count, int file);
int bda_fs_seek_raw(int file, s32 offset, int whence);
int bda_fs_tell_raw(int file);
int bda_fs_eof_like(int file);
int bda_fs_error_like(int file);
int bda_fs_clear_error_like(int file);
int bda_fs_remove_raw(const char *path);
int bda_fs_rename_like(const char *old_path, const char *new_path);
```

成功 handle 是高地址 pointer，signed 值通常为负数。打开结果必须用
`bda_fs_file_is_valid(fd)` 判断；失败哨兵为 `0` 或 `0xffffffff`，继续传给
`read/seek/close` 可能导致真机重启。最小示例见 `reverse/examples/fs_read_demo.c`。

### 文件管理辅助

```text
FS +0x024  remove/unlink 类
FS +0x02c  chdir 或 directory existence check-like
FS +0x030  mkdir 类
FS +0x034  rmdir/remove-directory 类；单参数 path，删除空目录
FS +0x03c  findfirst/search-open 类；pattern,attr,find_data 三参数
FS +0x040  findnext 类；读取 find_data+0x10 index，更新下一项
FS +0x044  findclose 类；读取 find_data+0x10 index，释放 +0x00 cursor
FS +0x048  disk-info/free-space 类
FS +0x050  current directory getter；buffer,size，返回 required size
FS +0x054  path info getter；path,info，填充 attr/size/time-like 结构
FS +0x06c  path/flags 存在性或属性检查；C200 只使用 a0/a1，不填充 stat 结构
FS +0x078  BDA_FS_MEDIA_PRESENT_RAW_LIKE  raw media-present bit 查询；无参数，返回 0/1
FS +0x07c  storage-ready/media-present 类
```

`findfirst/findnext/findclose` 是当前 low-level directory enumeration 路线，但 `find_data` struct 还没有
完整命名。disk info output struct 也仍在逆向中。

## GUI/Window/Draw Wrapper

### 创建和销毁 Control

```text
GUI +0x1a4  BDA_GUI_CREATE
GUI +0x1a8  BDA_GUI_DESTROY_LIKE；destroy child control/object，不是 frame close
```

`GUI+0x1a4` 的当前调用形态：

```text
a0 = class name，例如 "edit"、"medit"、"EB_SCROLL"
a1 = caption/title string 或 0
a2 = style
a3 = flags/extended style，常见为 0
stack+0x10 = control id
stack+0x14 = x
stack+0x18 = y
stack+0x1c = width
stack+0x20 = height
stack+0x24 = parent/window handle
stack+0x28 = extra/user data
```

SDK 推荐使用：

```c
bda_handle_t bda_gui_create_window_like(
    const char *class_name,
    const char *caption,
    u32 style,
    u32 flags,
    u32 id,
    s32 x,
    s32 y,
    s32 width,
    s32 height,
    bda_handle_t parent,
    u32 extra
);
```

不要在没有有效 parent/frame lifecycle 时直接创建复杂 control；hardware probe 显示这类调用
可能重启。`parent=0` 的裸 `bda_main()` create probe 不是 GUI bootstrap，只能说明
ABI 已进入固件路径，不能证明 control lifecycle 已建立。

### frame 描述符

```text
GUI +0x084  BDA_GUI_REGISTER_FRAME_LIKE
```

`C200.bin` 会读取 `0x34` byte descriptor 并创建约 `0x114` byte 内部 object。SDK 暴露：

```c
typedef struct bda_frame_desc_like bda_frame_desc_like_t;
void bda_frame_desc_init_like(
    bda_frame_desc_like_t *descriptor,
    const char *title,
    bda_wndproc_t wndproc,
    s32 width,
    s32 height,
    void *surface
);
bda_handle_t bda_gui_register_frame_desc_like(bda_frame_desc_like_t *descriptor);
```

`bda_frame_desc_like_t` 只命名已确认或样本验证过的 field；`internal*` 和 `aux30`
不要当成应用级配置项使用，也不要自行扩展结构体大小。
`bda_frame_desc_init_like()` 的 no-template 默认是 `style=0,surface=0`。原机复杂窗口
里常见的 `style=0x08000000` 和 `GUI+0x2fc(15)` surface 不是通用最小组合；需要复刻
原机窗口管理时再显式设置。

### Message/Event

```text
GUI +0x030  event poll 类；message_buffer,frame_or_handle，写 0x1c byte message packet
GUI +0x03c  notify/post 类；写入 frame queue，0xb1 只置 pending flag
GUI +0x040  send 类；直接调用 handle+0x88 wndproc，返回 callback result
GUI +0x050  event step 类；读取 message_buffer，不是无参数 pump
GUI +0x054  event dispatch 类；调用 message_buffer 中 handle 的 wndproc
GUI +0x08c  default window procedure fallback；handle,message,wparam,lparam
```

window proc ABI：

```c
int wndproc(bda_handle_t hwnd, u32 message, u32 wparam, u32 lparam);
```

对应寄存器为 `a0/a1/a2/a3`。message 常量和 input 线索见 `input_notes.md`。

frame 生命周期：

```text
GUI +0x04c  frame release/request-like；标记对象状态，不是释放 frame 本体
GUI +0x088  frame stop-like；发送内部 stop message 并释放关联资源
GUI +0x098  frame activate/state-like；handle,mode，mode 不是 show flag
GUI +0x134  active frame set-like；切换内部 +0xd8，向旧/新 frame 发 0x31/0x30
GUI +0x13c  active child get-like；读取 context，解析所属 container 后返回 container+0xd8
GUI +0x17c  close frame-like；释放 frame 并清空 active frame 全局槽
GUI +0x1b4  BDA_GUI_OBJECT_PAIR_EXISTS_LIKE；只读扫描 GUI 全局记录表，比较 record+0/record+4，返回 0/1
```

`TouchStageV11.bda` 已在真机确认顶层窗口的完整顺序是：`+0x088 stop`、`+0x04c
release`、`+0x030 poll` 返回 0、`+0x17c close`、`bda_main return`。`+0x17c` 没有
稳定 return value，公开 SDK 使用 `void bda_gui_close_frame(handle)`。详见
`verified/touch_window_lifecycle_api.md`。

### 绘图生命周期

```text
GUI +0x308  BDA_GUI_BEGIN_DRAW_LIKE
GUI +0x30c  BDA_GUI_END_DRAW_LIKE
GUI +0x304  BDA_GUI_CURRENT_DRAW_LIKE
GUI +0x310  compatible draw context/surface 创建；V19 验证可同时创建两块
GUI +0x314  compatible context flush-and-free；释放后 handle 不可复用
GUI +0x074  BDA_GUI_PUMP_PRESENT_LIKE
```

`+0x310/+0x314` 的公开 wrapper 是
`bda_gui_compatible_context_create()` 和 `bda_gui_compatible_context_free()`。

原机应用常见模式是：

```text
begin_draw -> pump/present(1) -> 绘制 -> pump/present(0) -> end_draw
```

`GUI+0x304` 和 `GUI+0x308` 都接收 `handle` 参数；C200 分别以 mode=0 和
mode=1 调用同一个内部 draw context helper。不要再使用无参数
`current_draw` 形态。两者都会分配或复用 draw context slot，不是查询全局
draw handle 的无状态 getter。

`GUI+0x074/+0x400` 不能脱离原机 surface/context 直接当作 framebuffer 游戏接口。
旧扫雷把 present 放在 tile 循环里会逐块 flip；`TileBlit` 后续真机结果确认，即使
只在循环外统一 present，缺少原机 game surface/context 时仍会逐块 flip 并死机。
雷霆战机和决战坦克的全屏 buffer 链路都是
`GUI+0x3f8 -> GUI+0x6e0 -> GUI+0x400 -> MEM+0x00c`，说明 SDK 当前缺的是小游戏
shell 状态机，而不是单个 blit wrapper。

对象级绘图还有：

```text
GUI +0x0e4  object draw begin 类
GUI +0x0e8  object draw end 类
GUI +0x07c  BDA_GUI_OBJECT_FLAGS_CLEAR_LIKE；kind=1 object +0x24 flags &= ~mask，成功返回 1
GUI +0x080  BDA_GUI_OBJECT_FLAGS_OR_LIKE；kind=1 object +0x24 flags |= mask，成功返回 1
GUI +0x0b0  BDA_GUI_OBJECT_FLAGS_GET_LIKE；kind=1 object +0x24 flags getter，失败返回 0
GUI +0x0b8  BDA_GUI_OBJECT_USERDATA0_GET_LIKE；kind=1 object +0x80 getter
GUI +0x0bc  BDA_GUI_OBJECT_USERDATA0_SET_LIKE；kind=1 object +0x80 setter，返回旧值
GUI +0x0c0  BDA_GUI_OBJECT_USERDATA1_GET_LIKE；kind=1 object +0x84 getter
GUI +0x0c4  BDA_GUI_OBJECT_USERDATA1_SET_LIKE；kind=1 object +0x84 setter，返回旧值
GUI +0x0c8  BDA_GUI_OBJECT_PAYLOAD_WORD_GET_LIKE；subtype=0x12 object payload+0x1c getter
GUI +0x0cc  BDA_GUI_OBJECT_PAYLOAD_WORD_SET_LIKE；subtype=0x12 object payload+0x1c setter，返回旧值
GUI +0x0d0  BDA_GUI_OBJECT_RESOURCE_PTR_GET_LIKE；kind=1 object +0x8c pointer getter
GUI +0x0d8  BDA_GUI_OBJECT_CALLBACK_PTR_GET_LIKE；kind=1 object +0x88 pointer getter
GUI +0x0dc  BDA_GUI_OBJECT_CALLBACK_PTR_SET_LIKE；kind=1 object +0x88 pointer setter，value 非 0 才写
GUI +0x0f4  BDA_GUI_ACCUMULATE_ORIGIN_LIKE；沿 object 父链把 +0x14/+0x18 累加到 x/y pointer
GUI +0x0f8  BDA_GUI_SUBTRACT_ORIGIN_LIKE；沿 object 父链从 x/y pointer 减去 +0x14/+0x18
```

这两个 wrapper 内部会走与 `GUI+0x308/+0x30c` 相同的 C200 draw helper，但要求传入
真实对象/control handle。

### Text/Color

```text
GUI +0x338  set text/background mode 类
GUI +0x33c  set text/foreground color 类
GUI +0x334  set background/fill color 类
GUI +0x378  RGB/color helper 类
GUI +0x4f0  draw text 类
```

`GUI+0x4f0` 当前参数形态：

```text
a0 = drawing/window handle
a1 = x
a2 = y
a3 = GBK/ASCII string
stack+0x10 = extra/width/flags，常见 -1
```

### Pixel/Region/Framebuffer

```text
GUI +0x368  put pixel / draw point 类
GUI +0x384  polyline；context,point_array,count，point 为两个 signed word
GUI +0x390  ellipse outline/fill；context,cx,cy,rx,ry,0,0,filled
GUI +0x394  circular arc；context,cx,cy,start_degrees,end_degrees,radius
GUI +0x398  center-based rounded rectangle；context,cx,cy,width,height,corner_rx,corner_ry,filled
GUI +0x3a0..+0x3b0  map mode / viewport / window mapping getters
GUI +0x3b4..+0x3c4  map mode / viewport / window mapping setters
GUI +0x3c8/+0x3cc  full device-to-logical / logical-to-device point conversion；包含 context origin
GUI +0x3d0/+0x3d4  map-only device-to-logical / logical-to-device point conversion；不含 context origin
GUI +0x3d8  exclude clip rect；context,left,top,right,bottom
GUI +0x3dc  union clip rect；context,left,top,right,bottom，cached bounds 不随追加节点扩展
GUI +0x3e0  intersect clip rect；context,const rect*，逐节点求交并重新计算 aggregate bounds
GUI +0x3e4  select/reset clip rect；context,rect_or_null，NULL 清除自定义 region
GUI +0x3ec  custom clip-region bounds getter；reset 后返回零矩形哨兵
GUI +0x3f0  current clip point hit test；context,point
GUI +0x3f4  current clip rect intersection test；context,rect
GUI +0x40c  region draw/copy 类
GUI +0x410  render/copy helper；context,x,y,width,height,descriptor
GUI +0x414  low-level render helper，多 stack 参数和 descriptor
GUI +0x418  双 context 矩形复制；支持 compatible source/destination 子矩形和 dirty present；末参数 0 禁用色键，0xf81f 跳过洋红 source pixel
GUI +0x430  rect writer；rect,x0,y0,x1,y1 五参数，SDK wrapper 为 bda_gui_rect_prepare_like()
GUI +0x0a4  object/default client rect 查询；handle,rect，成功写 16 byte rect
GUI +0x3f8  framebuffer/region blit 类
GUI +0x3fc  capture region alloc；x,y,width,height，返回 buffer 需 bda_free()
GUI +0x400  alternate framebuffer/region blit 类
```

`GUI+0x368` 在 `电子画板.bda` 中证据最强，常用于线段/矩形循环：

```text
a0 = surface/canvas handle
a1 = x
a2 = y
a3 = RGB565 color，例如 0xf800 红色
```

`GUI+0x384` 已由 C200 确认会把首点设为 current point，再对剩余点逐个调用
line-to；V10 模拟器验证连续折线可见。`GUI+0x3ec/+0x3f0/+0x3f4` 只读当前 clip，
不包含 clip region 的创建或修改生命周期。

`GUI+0x390` 已由 V11 验证末项 `0/1` 分别产生轮廓/实心椭圆；两个中间参数在
`电子画板` 和 C200 内部调用中都为 0，研究 wrapper 固定写 0。填充颜色来自 selected
draw object/backend，不是 `GUI+0x334` 的直接颜色值。

`GUI+0x394` 的角度为整数度，V12 已确认 `0→180` 是上半圆、`180→360` 是下半圆。
`GUI+0x398` 使用中心坐标而不是左上角，末项切换轮廓/实心；调用者应让两个圆角半径
不超过 width/height 的一半。

逻辑坐标映射字段位于 context `+0x70..+0x90`。V13 已验证单位默认值、2 倍 viewport
extent、viewport origin 偏移和完整恢复。启用 map mode 前必须保证 window extent 两个
分量都非 0；setter 要求非空 context。

`GUI+0x3f8/+0x400` 在游戏中常见全屏形态：

```text
a0 = x
a1 = y
a2 = 0xf0  (240)
a3 = 0x140 (320)
stack+0x10 = buffer pointer
```

`GUI+0x3fc` 不是同一个参数顺序：它是 `x,y,width,height`，会分配并返回一块
screen/backend region buffer，适合和 `GUI+0x400` restore 路径配对；返回值必须
用 `bda_free()` 释放。

`GUI+0x314` 已由 compatible context 闭环收窄为 destructive free；`GUI+0x334`
仍是研究候选：

```c
void bda_gui_compatible_context_free(bda_handle_t context);
int bda_gui_set_fill_color_like(bda_handle_t handle, u32 color);
```

它们需要真实 surface/draw handle。`GUI+0x430` 已在 C200 表中确认是
`rect,x0,y0,x1,y1` 五参数 writer，SDK wrapper 为
`bda_gui_rect_prepare_like(rect, x0, y0, x1, y1)`。

### 矩形命中测试

```text
GUI +0x46c  BDA_GUI_RECT_CONTAINS_LIKE
system function VA: 0x800c0818
```

逻辑等价于：

```c
return rect[0] <= x && x < rect[2] && rect[1] <= y && y < rect[3];
```

SDK 暴露：

```c
typedef struct {
    s32 x0;
    s32 y0;
    s32 x1;
    s32 y1;
} bda_rect_like_t;

int bda_gui_rect_contains_like(const bda_rect_like_t *rect, s32 x, s32 y);
```

这个 wrapper 不依赖 window handle，适合作为 SDK smoke 示例，见
`reverse/examples/gui_rect_contains_demo.c`。

### 图片解码和绘制

```text
GUI +0x540  draw VX 类
GUI +0x670  BMP decode 类
GUI +0x808  JPEG decode 类
RES +0x090  resource/picture state 类
```

`GUI+0x540` 的公开 wrapper 是
`bda_gui_draw_vx(context, x, y, vx_resource)`；尺寸来自 VX header，不执行缩放。
`GUI+0x418` 的公开 wrapper 是九参数 `bda_gui_context_copy()`，支持 compatible
source/destination、visible 提交、`0xf81f` 洋红色键和子矩形复制。

相册使用的临时图片描述符：

```text
+0x00  RGB565 pixel pointer
+0x04  width
+0x08  height
+0x0c  stride_bytes，VX 快路径写 width * 2
+0x10  mode byte
+0x11  bits_per_pixel11，VX 快路径写 0x10
+0x14  source_pixels，VX 快路径写 resource + 0x18
+0x18  selected/index field，初始化为 -1
```

SDK 对应 `bda_picture_like_t`。VX 快路径已确认写 `width/height/stride_bytes`
和 `source_pixels`；完整流程见 `picture_notes.md`。

## 游戏计时

```text
GUI +0x6d8  25 ms raw tick counter；无参数返回 u32
```

C200 table entry 指向 `0x8012bdb0`，只返回全局 `0x80474094`。定时 IRQ
`0x8012bb90` 每次把该全局加一；初始化函数把定时器配置为 25 ms 周期。
官方 `BB虚拟机.bda` 会在启动时保存一次原始值，随后按
`(current - base) * 25` 返回毫秒数。

公开 wrapper：

```c
u32 bda_gui_tick_count_25ms(void);
u32 bda_gui_tick_elapsed_25ms(u32 start, u32 end);
u32 bda_gui_tick_elapsed_ms(u32 start, u32 end);
```

elapsed helper 使用无符号 `end - start`，可跨一次 `u32` 回绕。不要把 raw counter
直接当毫秒，也不要用 `end >= start` 判断是否前进。V9 已在 8013 模拟器通过并按
模拟器稳定等级进入公开 `sdk/include`；真机仍待复测。

## 文件选择器

GAMEBOY.BDA 使用 high-level file selector，不是直接用 FS 枚举：

```text
GUI +0x6a8  open/session 类；a0=mode，不是 selector descriptor pointer
GUI +0x6c8  modal selector；a0=descriptor pointer
GUI +0x6b8  list nth helper 类；参数是 head/index，不是无参数 selector get
GUI +0x6bc  linked list free helper；a0=head，不是无参数 selector close
```

选择器描述符开头：

```text
+0x00  output path/name buffer
+0x04  extension filter string，例如 "gb;gbc"
+0x08  directory/current-state buffer
+0x0c  title string，例如 GBK "请选择游戏文件"
+0x10 list head output；+0x14 internal，默认 0
+0x18 status output，默认 0
+0x1c selected index output；+0x20/+0x24 sentinel，初始化为 -1
+0x34/+0x38 sentinel 字段，初始化为 -1
+0x40 list_limit40，原机 selector/list 描述符中见到 0x1000
+0x48 sentinel48，原机 selector/list 描述符中见到 -1
+0x64 result64，原机 selector/list 描述符中见到 0
```

SDK 暴露 `bda_file_selector_like_t` 和 `bda_file_selector_init_like()`。硬件测试显示，
selector text color 修正来自更完整的 struct 初始化，不是 RES+0x094 加载 skin。
字段名里的 `internal*` 仍表示只确认 offset 和初始化值，不是应用级配置项。
当前不公开无参数 selector get wrapper；`GUI+0x6b8` 在 C200 中读取的是
`a0=head, a1=index`，更像链表第 N 项 helper。
`GUI+0x6a8` 只接收 `mode`；descriptor 必须传给随后的 `GUI+0x6c8`。选择完成后，
`+0x10` 是结果链表头，`+0x1c` 是选中索引，节点 `+0x00` 是文件名。调用者必须在
`GUI+0x6bc(head)` 前复制或拼接结果。

## RES 表

```text
RES +0x000  不公开；resource manager reset，全局状态清零
RES +0x004  不公开；路径/文件驱动的 resource manager open/init，读写全局 cache
RES +0x008  不公开；resource manager cleanup，关闭全局 handle 并释放 buffer
RES +0x00c  不公开；descriptor 驱动的 resource state 配置，会打开路径并 seek
RES +0x010  不公开；resource manager cleanup/close，无稳定 return value
RES +0x040  不公开；固件内置资源路径读取，失败时可能弹 message box
RES +0x090  get resource/picture state 类
RES +0x094  trace/log 类
```

`RES+0x000/+0x004/+0x008/+0x00c/+0x010/+0x040` 都是 resource manager 全局
lifecycle/cache 路径，会打开/关闭 file handle、释放 buffer、写全局状态，甚至在
失败时弹 message box。SDK 不公开这些 wrapper，也不把它们命名为 high-level
DLX loader。

`RES+0x094` 曾被误命名为 DLX loader。真机 probe 结果显示，传入 trace 字符串或
`\\shell\\commonframe_A.dlx`、`\\shell\\MessageBoxBlue.dlx` 等路径都返回 0，
应用继续运行，且没有可见加载效果。因此新代码应使用 `bda_res_trace_like()`
或 `bda_res_entry_094_like()` 这类保守名称，不要把它当 DLX 加载器。

`元素周期表.bda` 的外部 DLX 文件是应用自己通过 FS open/read/seek/close 解析的。
详见 `element_bda_notes.md`。

## SYS 表

### 音频和设备

GAMEBOY.BDA 使用 SYS 表做直接音频流：

```text
SYS +0x000  不公开；system resource/session dispatcher，descriptor 驱动并分配 10-slot table
SYS +0x008  不公开；system resource/session scheduler tick，遍历 10 个 slot
SYS +0x00c  不公开；system resource/session slot update，参数 resource_id,value,mode
SYS +0x010  不公开；system resource/session state update，参数 resource_id,state_ptr
SYS +0x06c  audio/device open 类
SYS +0x074  audio ready/wait 类
SYS +0x078  audio write 类
SYS +0x084  不公开；raw input/internal helper，只调用内部函数，无稳定 return value
SYS +0x088  raw keycode query；无参数，返回 raw code
SYS +0x08c  audio reset/init 类
SYS +0x090  raw audio state pointer getter；返回 0x80362830，不是 open API
SYS +0x094  不公开；raw audio state 写入 helper，会复制调用者结构到 0x80362830
SYS +0x0a0  audio flush/drain 类
```

打包声音/游戏音效还有：

```text
SYS +0x040  BDA_SYS_PACKAGE_SOUND_OP40_LIKE；打包音效 low-level op40，clamp sound_id 到 0..0x62 并置 pending flag
SYS +0x044  BDA_SYS_PACKAGE_SOUND_OP44_LIKE；打包音效 low-level op44，无参数内部 helper
SYS +0x058
SYS +0x05c
SYS +0x060
SYS +0x064
SYS +0x068
```

这些名称仍偏保守，主要依据原机游戏路径和 C200 table entry。`SYS+0x050` 曾被
误认为 loader wrapper，但 C200 中它只是立即返回 `1` 的 stub，因此不再作为 SDK
公共 offset 暴露。

### delay/time/alarm

```text
SYS +0x080  busy-wait delay 类；参数是固件 delay 单位，不是调度式 sleep
SYS +0x09c  timer/rate preset 类；参数是 0..14 preset index，不是任意 tick 数
SYS +0x0ac  alarm set 类
SYS +0x0b0  alarm get 类
SYS +0x0b8  alarm due record get 类；扫描 alarm.db，输出 0x2b8 byte record
```

`SYS+0x0a8` 曾被误认为 alarm/time commit 或 refresh wrapper，但 C200 table entry 实际是
`jr ra; nop`，SDK 不再公开该 offset。alarm record 字段仍只命名已确认部分。只读 probe 见
`reverse/examples/time_probe.c` 和 `time_notes.md`。

## main/entry 约定

no-template C 程序 entry 是：

```c
__attribute__((section(".text.bda_main")))
int bda_main(void) {
    return 0;
}
```

no-template 构建会把 entry 放在 file offset `0x95f8`，runtime VA `0x81c00020`。
模板 patch 路径则替换原机启动代码中的跳转目标；手写汇编应保存自己使用的
callee-saved 寄存器，并用 `jr $ra` 返回。

## 命名规则

- 没有 `_LIKE` 的少数 wrapper 表示当前风险较低或已经有 hardware smoke，但不表示
  任意入口上下文、任意 GUI lifecycle 都安全；例如 `bda_msgbox()` 在普通
  no-template app 中适合作为首个 smoke，在硬编码时间入口替换上下文仍可能崩溃。
- 带 `_LIKE` 的名称表示 offset 和大致调用形态有证据，但 ABI、结构体字段或生命周期
  仍可能继续收窄；它们不是自动稳定的 high-level API。
- 旧误名 `bda_load_dlx*` 已从 SDK 删除；新代码不要把 `RES+0x094` 当资源加载器。
