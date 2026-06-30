# 元素周期表.bda 完整逻辑分析

分析对象：

```text
应用\程序\元素周期表.bda
应用\数据\shell\Element.dlx
应用\数据\shell\HElement.dlx
应用\学习数据\元素周期表.hx
```

`元素周期表.bda` 是当前样本中最小的原厂 native BDA，大小 55,900 字节。它很适合作为
“标准窗口程序 + DLX 图片资源 + 外部数据文件 + 触摸/按键事件”的参考样本。

## 1. 总体布局

```text
BDA size          0xda5c / 55900
entry file off    0x95f8
entry runtime VA  0x81c00020
file base         0x81bf6a28
BSS               0x81c04480..0x81c06731
full disasm       reverse\analysis_element_full.disasm.txt
call scan         reverse\analysis_element_calls.txt
strings           reverse\analysis_element_strings.txt
tables            reverse\analysis_element_tables.txt
```

入口流程：

```text
0x81c00020:
  call 0x81c00050   初始化 BSS 和全局 API 表
  call 0x81c0218c   主程序
  return
```

`0x81c00050` 清零 BSS 后缓存系统表：

```text
RES  0x81c04480
GUI  0x81c04484
SYS  0x81c04488
FS   0x81c0448c
MEM  0x81c04490
```

注意：本程序里 `RES+0x094` 用于输出 `GeneralDLTable Address :%x` 这类格式字符串。
它更像 trace/printf helper，不是 DLX loader。之前 SDK 把它命名为 load_dlx 是误导性的。

## 2. 主要函数表

```text
0x81c00050  runtime/bootstrap 初始化
0x81c001a0  加载并解析 DLX，返回 app-local resource table
0x81c002f8  读取 DLX 资源表/某个资源段的辅助函数
0x81c004bc  从 app-local resource table 按 index 取资源指针
0x81c00654  释放资源表中的附属分配
0x81c0069c  释放 app-local resource table
0x81c006d0  主周期表窗口过程
0x81c00f7c  绘制当前元素的小图/局部图
0x81c01204  绘制当前元素在周期表中的高亮/定位图
0x81c014dc  元素详情/浏览窗口过程
0x81c0218c  主程序
0x81c0240c  加载 .hx 详情文本偏移表
0x81c02598  按元素 index 从 .hx 读取一段文本到缓冲
0x81c026c0  创建一个标准窗口并跑事件循环
0x81c027d0  memchr-like
0x81c02854  strlen-like
0x81c02884  strtol-like
0x81c02b60  memset-like
0x81c02bd0  printf/sprintf core
0x81c03480  isdigit-like
0x81c034a0  isspace-like
0x81c034d0  toupper/tolower-like
0x81c034f0  small malloc
0x81c03668  malloc arena init
0x81c036e0  heap descriptor shift helper
```

## 3. 外部资源

### 3.1 图片 DLX

主程序优先加载：

```text
A:\应用\数据\shell\Element.dlx
```

失败后尝试：

```text
A:\应用\数据\shell\HElement.dlx
```

两个 DLX 结构一致：

```text
count=7 variant=3 header=0x78 name='Vrix.Ipona'
#00 VX 240x320  周期表背景/整屏图
#01 VX 240x320  周期表背景/整屏图的另一态
#02 VX 757x383  大图/详情图集
#03 VX 16x16    小图标/标记
#04 VX 240x265  内容区图
#05 VX 240x25   顶部/底部条
#06 VX 240x30   顶部/底部条
```

DLX 不是系统自动加载的。`0x81c001a0` 自己用 `FS+0x000/+0x008/+0x010/+0x004`
打开、读取、seek、关闭，然后用 `MEM+0x008` 分配内存，构建 app-local resource table。

`0x81c004bc(index, table)` 从这个 table 取资源指针。返回值指向完整 `VX` 资源块，
包括 `VX` 头，不是裸 RGB565 像素。

### 3.2 学习数据 .hx

详情文本来自：

```text
A:\应用\学习数据\元素周期表.hx
```

文件大小 172,815 字节，开头包含：

```text
magic-ish/header
"hx"
"化学元素"
"BBK LTD."
元素符号表: H, He, Li, ...
基础条目: "1   H\r  氢\r1.008", ...
```

`0x81c0240c` 加载 `.hx` 的文本偏移表：

1. 清零 `0x81c044d4` 开始的 0x74 字节。
2. 打开 `元素周期表.hx`。
3. seek 到固定位置读取 3 字节偏移。
4. 循环 114 次读取 3 字节相对偏移。
5. 写入 `0x81c044d8...`，形成元素详情文本 offset 表。
6. 末尾 sentinel 写 `0x0002a071` 到 `0x81c046a0`。

`0x81c02598(index)` 使用这张 offset 表：

```text
offset_start = table[index]
offset_end   = table[index + 1]
read bytes [offset_start, offset_end) into 0x81c046a4 scratch buffer
```

所以自定义 `.hx` 的关键不是纯文本，而是要生成 3 字节 offset 表和文本段。

## 4. 关键全局变量

```text
0x81c04370  主界面帮助文本指针 -> 0x81c03850
0x81c04374  浏览界面帮助文本指针 -> 0x81c03a94
0x81c04378  当前选中元素 index，初始 1

0x81c04480  RES table
0x81c04484  GUI table
0x81c04488  SYS table
0x81c0448c  FS table
0x81c04490  MEM table

0x81c04494  主/子窗口 frame handle
0x81c04498  另一个窗口 frame handle
0x81c0449c  dictview/control handle
0x81c044a0  file handle
0x81c044d0  flag: 0 means Element.dlx, nonzero means HElement.dlx fallback path

0x81c044d4  .hx offset table base
0x81c046a4  scratch buffer, also used for .hx text
0x81c06644  app-local DLX resource table pointer
0x81c06648  current resource pointer
0x81c0664c  current draw handle
0x81c06650  temp 3-byte offset read buffer
```

## 5. 主程序逻辑

`0x81c0218c` 是主程序：

```c
int main_like(void) {
    if (GUI_0x7c0() != 0) {
        resource_table = load_dlx("A:\\应用\\数据\\shell\\HElement.dlx");
    } else {
        resource_table = load_dlx("A:\\应用\\数据\\shell\\Element.dlx");
        if (!resource_table)
            resource_table = load_dlx("A:\\应用\\数据\\shell\\HElement.dlx");
    }

    if (!resource_table) {
        show_msgbox("无图片数据请到步步高www.eebbk.com网站下载!");
        return;
    }

    load_hx_offsets();
    create_main_window_and_event_loop();
}
```

如果 `.hx` 不存在或失败，会显示：

```text
无元素周期表数据!请到
步步高www.eebbk.com
网站下载
```

如果图片 DLX 不存在，会显示：

```text
无图片数据!请到步步
高www.eebbk.com网站
下载！
```

## 6. 窗口创建和事件循环

本程序创建窗口的标准模式：

```text
surface = GUI+0x2fc(15)
desc.style   = 0x08000000
desc.title   = ""
desc.proc    = window_proc
desc.height  = 240
desc.width   = 320
desc.surface = surface
frame = GUI+0x084(&desc)
```

事件循环统一形态：

```c
while (GUI_0x030(msg, 0)) {
    GUI_0x050();
    GUI_0x054(msg);
}
GUI_0x17c(frame);
```

重点：`GUI+0x030` 第二个参数在原厂代码中是 `0`，不是 frame handle。
这解释了我们之前图片能显示但按键/触摸进不了窗口过程的问题。

## 7. 主窗口过程 `0x81c006d0`

主窗口是周期表页面。它处理这些消息：

```text
0x0001  触摸/坐标事件，lparam 高低 16 位是 y/x 或 x/y 坐标组合
0x0010  create/init 或 command 分支
0x0060  某种 draw/activate 分支
0x0066  close/返回
0x00b1  输入/重绘触发
0x07fd  app command，常用于刷新/返回
0x0844  key/input-like
```

未处理消息落到：

```text
GUI+0x08c(frame, msg, wparam, lparam)
```

### 7.1 触摸区域

`message == 1` 时，窗口过程从 `lparam` 拆出坐标：

```text
s0 = low16(lparam)
s5 = high16(lparam)
```

它先处理几个固定按钮区域：

```text
x 217..233, y 5..19      关闭/返回
x 199..212, y 5..19      另一返回按钮
x 6..24,   y 296..316    底部按钮
x 216..234,y 296..316    底部按钮
```

对应行为多为发送 `0x66` 或 `0x7fd` 到当前窗口，触发返回/关闭/刷新。

### 7.2 点选元素

主窗口根据触摸坐标计算元素 index，然后写入：

```text
0x81c04378 = selected_element_index
```

主要区域：

```text
常规周期表区域：
  x 大约 7..259
  y 大约 2..234
  每格宽高约 13

镧系/锕系区域：
  x 大约 260..284
  y 大约 42..235
```

代码中大量使用 `0x4ec4ec4f` 乘法常数，这是除以 13 的优化形式。
也就是说周期表格子的布局单位基本是 13 像素。

### 7.3 键盘导航

详情窗口过程里明确看到这些 command/键值：

```text
0x0067  使用导航表取 previous-like 元素
0x006a  current++，向后
0x0069  current--，向前；如果到 1 则跳到 118
0x006c  使用导航表取 next-like 元素
```

相关导航表位于：

```text
0x81c03fb8
```

它是 119 组 pair，每组两个 `u32`。程序通过：

```c
pair = table[current_index];
new_index = pair[0] or pair[1];
```

来处理上下左右移动时的“周期表邻居”关系。

## 8. 详情/浏览窗口过程 `0x81c014dc`

详情窗口进入方式：

1. 主界面点击某个元素。
2. 如果 `current_index < 115`，创建详情窗口。
3. 如果没有元素介绍，弹：

```text
暂无相关元素的介绍
```

详情窗口创建同样使用 `GUI+0x2fc(15)` + `GUI+0x084(&desc)` + 事件循环。

详情窗口的核心绘制流程：

```text
GUI+0x308(frame)            获取 draw handle
GUI+0x074(1)                进入绘制/present 保护
get_resource(1 or 2/6/7)    从 DLX 获取 VX 资源
GUI+0x540(...)              绘制完整 VX
GUI+0x5bc(...)              绘制裁剪/局部 VX
0x81c00f7c                  绘制当前元素小图/标记
0x81c01204                  绘制高亮/位置
GUI+0x30c(draw)             结束 draw
GUI+0x074(0)                退出绘制/present 保护
```

`0x81c0207c` 分支显示完整背景图：

```text
resource #1
GUI+0x540(draw, 0, 0, 240, 320, resource)
```

这也解释了屏幕逻辑坐标是 `240x320` 竖屏系，而 frame descriptor 中仍写
`height=240,width=320`。

## 9. 图片绘制 API 形状

这个 BDA 不使用游戏式裸 framebuffer：

```text
GUI+0x3f8
GUI+0x400
```

它使用资源绘制 API：

```c
GUI+0x540(draw, x, y, width, height, vx_resource);
```

参数来自真实调用：

```text
draw resource #1:
  a0 = draw handle
  a1 = 0
  a2 = 0
  a3 = 240
  stack+0x10 = 320
  stack+0x14 = vx_resource

draw resource #6:
  a0 = draw handle
  a1 = 0
  a2 = 290
  a3 = 240
  stack+0x10 = 30
  stack+0x14 = vx_resource
```

这就是我们 `DLXImageElementStyle.bda` 能显示图片的原因：传的是完整 `VX` 块，
不是裸 RGB565。

相关 API：

```text
GUI+0x540  draw VX resource full image
GUI+0x5bc  draw VX region/cropped image-like
GUI+0x65c  draw small tile/icon-like, 参数更多，常用于元素标记
GUI+0x690  message/status box-like helper，失败时显示提示
```

## 10. 文本和帮助

内置帮助文本有两份：

```text
0x81c03850  帮助--元素周期表，主界面帮助
0x81c03a94  帮助--元素周期表，浏览界面帮助
```

帮助文本明确说明原厂交互设计：

```text
主界面键盘：
  上下键：上、下选择元素
  左右键：左、右选择元素
  退出键：返回上级界面
  确认键：进入选中元素的浏览界面

主界面触摸：
  点击元素：选中元素并显示相应图片
  点击元素图片：进入浏览界面

浏览界面键盘：
  上下键：上、下翻行
  左右键：上、下翻屏
  退出键：退出浏览界面
```

## 11. app-local DLX resource table

`0x81c001a0` 返回的结构大致为：

```c
struct app_dlx_table {
    u8 count;
    u8 reserved[3];
    struct entry entries[count];
    u8 payload[];
};

struct entry {
    u32 type;
    u32 rel_or_abs_offset;
    u32 size;
};
```

`0x81c004bc(index, table)`：

```c
void *get_resource(int index, struct app_dlx_table *t) {
    if (!t || index out of range) return 0;
    return payload_base + entry[index].offset;
}
```

这里的返回值是 `VX` 开始地址。自定义程序如果使用 `GUI+0x540`，应保留完整资源块。

## 12. 可复用到 SDK/工具链的结论

稳定可复用：

```text
1. 标准窗口 descriptor 布局基本正确。
2. 事件循环必须使用 GUI+0x030(msg, 0)。
3. GUI+0x540 可以显示完整 VX 资源。
4. VX 参数是完整资源块，不是 pixels 指针。
5. DLX 可以由应用自己解析，不依赖系统 loader。
6. .hx 风格数据文件使用 3 字节 offset 表。
```

仍需继续确认：

```text
1. GUI+0x5bc 的完整参数语义。
2. GUI+0x65c 的小图/图标绘制参数语义。
3. `message == 1` 的 lparam 坐标高低位顺序在所有窗口中是否一致。
4. 真实实体键消息号，需要真机 EventDump 收到事件后确认。
5. RES+0x094 的真实名字；目前只能保守称 trace/printf-like。
```

## 13. 对自定义程序的意义

`元素周期表.bda` 给出的稳定应用框架是：

```c
init_tables();
resource_table = load_dlx_by_fs(path);
load_optional_data_file();

frame = create_frame(proc, surface=GUI+0x2fc(15));
while (GUI+0x030(msg, 0)) {
    GUI+0x050();
    GUI+0x054(msg);
}
GUI+0x17c(frame);
free_resources();
```

绘图时：

```c
draw = GUI+0x308(frame or current);
GUI+0x074(1);
GUI+0x540(draw, x, y, w, h, vx_resource);
GUI+0x30c(draw);
GUI+0x074(0);
```

这比裸 framebuffer 路线更适合普通应用、图片展示、菜单、资料浏览类 BDA。

游戏或模拟器仍可能需要 `GUI+0x3f8/+0x400`，但 UI/资源型程序优先走
`DLX/VX resource + GUI+0x540`。
