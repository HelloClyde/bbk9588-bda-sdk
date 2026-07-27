# gam4980 移植反馈：SDK 优化建议

本文整理 `gam4980-player-for9588` 移植过程中暴露出的 SDK 问题，并给出建议的
优先级、API 形态、验证要求和实施顺序。

本文是设计反馈，不代表其中提议的接口已经通过动态验证。任何需要新增固件 ABI 的
项目，仍须遵守[公开 API 准入规则](verified/public_api_policy.md)，完成独立 BDA、
模拟器和必要的真机验证后才能进入 `sdk/include/`。

## 总体判断

当前 SDK 已经具备文件、窗口、绘图、输入、对话框和 raw PCM 等底层能力，可以完成
较复杂的模拟器移植。主要问题不再是缺少更多固件表偏移，而是：

1. 多个底层 API 必须按隐含顺序组合，调用者很容易造成死机、资源泄漏或显示错误。
2. 部分公开常量和实际固件语义不一致。
3. 模拟器、真机和不同固件之间的行为差异缺少统一的能力查询与回归测试。
4. 文件、音频、编码和打包仍停留在低层接口，应用需要重复实现大量样板代码。

因此，下一阶段应优先把已经验证过的调用链封装成安全的高层操作，而不是继续扩大
公开的裸 ABI 面积。

## 移植中发现的问题

| 领域 | 实际现象 | 当前应用侧处理 |
|---|---|---|
| 帧提交 | 黑色笔画变透明，动画出现类似撕裂的半帧 | compatible back context、draw guard、矩形复制，并避开黑色色键 |
| 模态页面 | 活跃游戏窗口中直接打开帮助页会在真机卡死 | 释放 draw context，使用 `parent=0` 打开，返回后重新激活并获取 context |
| 触摸输入 | 触摸同时使轮询按键包出现 Escape | 应用维护触摸状态并屏蔽合成 Escape |
| 文件系统 | handle、短读短写、seek 返回值和保存完整性都要手动处理 | 每个调用点自行循环读写和检查 handle |
| 音频 | raw PCM 接口需要应用自行预填充、泵送、补零、排空和恢复衰减 | 项目最终移除音频支持；这不证明 raw API 错误，但说明持续流封装不足 |
| 中文文本 | 固件使用 GBK，帮助正文只能手工写 `\xNN` | 应用维护大段转义字节字符串 |
| 构建发布 | BDA 构建、数据目录和安装 ZIP 需要项目自定义脚本 | 项目维护独立 `build.py`、打包脚本和 workflow |

## P0：帧提交 API

### 问题

[`bda_graphics.h`](../sdk/include/bda_graphics.h) 当前定义：

```c
#define BDA_GUI_COLOR_KEY_NONE 0u
```

但 `gam4980` 在 C200 的 compatible-to-visible 路径中观察到，参数 `0` 会把 RGB565
黑色当作透明色键。结果是黑色文字和图形只剩轮廓。应用只能选择当前画面中不会使用的
色键，或在提交前把精确 `0x0000` 映射为视觉近黑的 `0x0001`。

同时，提交一帧需要调用者正确完成：

1. 初始化 raw RGB565 picture descriptor。
2. 将完整画面渲染到 compatible context。
3. 开启 dynamic draw guard。
4. 选择正确的 draw object。
5. 将 compatible context 复制到 visible context。
6. 恢复 draw object 并关闭 guard。

这个调用链过长，而且任何一步使用了正在被 CPU 写入的缓冲区，都可能让显示扫描读到
半帧。

### SDK 处理结果

2026-07-25 的 C200knl 真机正反测试再次复现该行为：参数 `0` 确实跳过 RGB565
`0x0000`。公开 SDK 已删除误导性的 `BDA_GUI_COLOR_KEY_NONE`，改为明确的
`BDA_GUI_COLOR_KEY_BLACK_RGB565`；同时增加 `BDA_GUI_OPAQUE_BLACK_RGB565=0x0001`
和 `bda_gui_rgb565_avoid_black_key()`，供 CPU/VX 帧在使用黑色色键提交前消除透明
黑洞。由于仍未验证固件通用的“禁用色键”值，SDK 不再承诺真正的 opaque-copy 参数。

回归证据是同一渲染链的三组真机正反测试：V24 使用非零背景时，source 中的
`0x0000` 区域露出旧 destination；V25 将整个九宫格背景设为 `0x0000` 后，旧菜单、
Loading 和新 UI 大面积重叠；V26 仅将待提交 source 的 `0x0000` 改为 `0x0001`，
显示恢复正常。这里的黑色色键属于 `GUI+0x418` context copy，与 BDA 图标资源自身
使用的 `0xf81f` 透明键是两个独立阶段。

### 后续建议

2026-07-27 已新增面向 C200 游戏/模拟器的受保护快速路径：
`bda_gui_framebuffer_acquire()` 使用固件 GUI API 返回的动态地址，不固定物理地址，
并校验 KSEG、范围、对齐和方向值，
`bda_gui_framebuffer_present_rgb565()` 负责 240×320 RGB565 整帧连续写入与方向
补偿。该接口及动态证据见
[direct_framebuffer_api.md](verified/direct_framebuffer_api.md)。它解决的是已知 C200
上的低延迟整帧提交，不取代下述面向普通应用、兼容更多固件的高层 surface 设计。

首先重新验证 `GUI+0x418` 是否存在真正的“禁用色键”值。在结果明确前，不应继续把
`0` 命名为 `BDA_GUI_COLOR_KEY_NONE`。如果固件没有无色键模式，应明确命名为黑色色键，
并由高层 opaque-copy wrapper 选择安全路径。

建议增加由 SDK 管理 compatible context 和提交顺序的 surface API：

```c
typedef struct bda_gui_surface bda_gui_surface_t;

int bda_gui_surface_open(
    bda_gui_surface_t *surface,
    bda_handle_t frame,
    u32 width,
    u32 height
);

int bda_gui_surface_present_rgb565(
    bda_gui_surface_t *surface,
    const void *pixels,
    u32 stride_bytes,
    const bda_rect_t *dirty_rect
);

void bda_gui_surface_close(bda_gui_surface_t *surface);
```

该接口应保证：

- visible context 永远不读取正在修改的 CPU framebuffer。
- draw guard、draw object 和 context 所有权由 SDK 配对管理。
- 全帧和 dirty rect 使用同一套明确语义。
- opaque copy 不依赖业务画面中“碰巧不存在”的颜色。
- 创建失败、frame detach 和重复关闭都有确定错误码。

### 验收测试

- 黑底白字、白底黑字和全 16-bit 颜色扫描不能丢失像素。
- 交替提交带不同 frame id 的横线图，截图中不能出现两个 frame id 混合。
- 连续运行并重复打开、关闭窗口后，fixed draw slot 数量保持稳定。
- 8013 模拟器和 C200 真机分别留存截图、日志和产物哈希。

## P0：模态页面生命周期

### 问题

系统帮助页、确认框和文件选择器是同步模态调用。独立 Demo 中调用成功，不代表它能在
持有 visible draw context、compatible context 和活跃事件泵的游戏窗口中直接调用。

`gam4980` 真机稳定链路是：

```text
释放触摸按键状态
-> 清理待处理输入
-> 释放 compatible context
-> 归还 visible draw slot
-> bda_help_page(parent=0, ...)
-> 重新激活原 frame
-> 重新获取 visible/compatible context
-> 完整重绘
```

### 建议

短期可增加显式 modal guard：

```c
int bda_gui_modal_begin(
    bda_gui_surface_t *surface,
    bda_gui_modal_state_t *state
);

int bda_gui_modal_end(
    bda_gui_surface_t *surface,
    bda_gui_modal_state_t *state
);
```

进一步可提供：

```c
int bda_help_page_for_surface(
    bda_gui_surface_t *surface,
    const char *title,
    const char *body
);
```

SDK 负责释放和恢复自身持有的绘图资源；应用仍负责清理自己的触摸队列和业务状态。

帮助页文档还应区分以下两种已验证范围：

- 没有活跃绘图资源的独立 `bda_main()`。
- 持续渲染窗口中释放资源后进入模态页面并恢复。

### 验收测试

- 在 40 Hz 持续绘图窗口中连续打开、关闭帮助页 100 次。
- 分别测试退出键、触摸返回栏和系统关闭路径。
- 每次返回后能够继续提交画面和响应按键。
- 日志中不存在 draw slot 耗尽、重复释放或 stale context。

## P0：输入归一化

### 问题

9588 的触摸接触会同时影响轮询输入包中的 Escape 状态。对只看按键包的应用来说，
一次触摸可能被错误解释成退出键。触摸坐标消息、触摸电平和六键轮询目前也是彼此独立
的低层接口，调用者必须自己推断来源。

### 建议

增加统一输入快照：

```c
typedef struct bda_input_state {
    u32 keys;
    s16 touch_x;
    s16 touch_y;
    u8 touch_down;
    u8 touch_event;
    u8 synthetic_escape;
    u8 reserved;
} bda_input_state_t;

int bda_input_poll_normalized(bda_input_state_t *state);
```

同时提供可选 helper：

- 触摸引发的 Escape 过滤。
- 坐标解包、裁剪和屏幕方向转换。
- 按键边沿检测。
- 长按、连发和防抖状态机。

原始按键包和触摸消息仍可保留，供需要精确固件行为的应用使用。

### 验收测试

- 按住屏幕任意位置时，不产生实体 Escape 事件。
- 实体 Escape 在触摸前后都不会被吞掉。
- 触摸按下、移动、抬起和移出按钮区域的事件顺序固定。
- 连发使用 tick 计算，不受事件泵一次处理多个消息影响。

## P0：文件系统高层 helper

### 问题

当前文件 API 忠实暴露固件语义，但不适合直接用于存档和配置：

- 有效 file object 可能是高地址，按 signed `int` 显示为负数。
- `read`/`write` 返回元素数，调用者必须处理短读和短写。
- `seek` 成功返回新位置，不是固定返回 `0`。
- 缺少统一的文件大小、存在性、完整写入和路径拼接 helper。
- truncate、flush、rename 和断电一致性仍需进一步验证。

### 可直接实现的 helper

这些功能可以只组合现有已验证 API，不需要新增固件 ABI：

```c
int bda_fs_read_exact(bda_file_t file, void *buffer, bda_size_t bytes);
int bda_fs_write_all(bda_file_t file, const void *buffer, bda_size_t bytes);
int bda_fs_get_size(bda_file_t file, u32 *size_out);
int bda_fs_exists(const char *path);
int bda_fs_join_path(char *out, bda_size_t capacity,
                     const char *directory, const char *name);
```

建议把公开 file 类型改为不透明或无符号 handle，避免调用者使用 `file <= 0` 判断。

### 必须先验证的能力

以下能力不能只凭常见 FAT/C stdio 行为推断：

- `wb` 是否在所有目标上可靠截断旧文件。
- flush 或 sync 的真实固件入口与返回语义。
- rename 是否能用于同目录原子替换。
- seek 到文件末尾之外再写入的行为。
- 写入后模拟器重启、NAND 重新挂载和真机断电后的持久性。

完成验证后再考虑 `bda_fs_atomic_replace()`，供 `.sav` 和配置文件使用。

## P1：连续音频流

### 问题

当前 [`bda_audio.h`](../sdk/include/bda_audio.h) 是已验证的 raw PCM 接口，只覆盖
22050 Hz、signed 16-bit、mono。它适合探针和简单播放，但持续模拟器音频还需要：

- 预填充固件队列。
- 按队列可写状态持续泵送。
- 欠载时补零。
- 管理应用环形缓冲区。
- 将用户音量换算成 attenuation。
- 区分 drain、abort 和 finish。
- 在模态页面和应用退出时恢复系统衰减状态。

`gam4980` 最终移除音频支持，并不能证明 raw PCM API 有错误，但说明 SDK 还缺少可复用
的实时流层。

### 建议

在 raw PCM API 之上增加纯 SDK helper，不增加新的固件声明：

```c
typedef struct bda_audio_stream bda_audio_stream_t;

int bda_audio_stream_open(bda_audio_stream_t *stream,
                          void *ring_buffer, u32 ring_bytes);
u32 bda_audio_stream_push(bda_audio_stream_t *stream,
                          const s16 *samples, u32 sample_count);
int bda_audio_stream_pump(bda_audio_stream_t *stream);
int bda_audio_stream_drain(bda_audio_stream_t *stream, u32 timeout_ticks);
void bda_audio_stream_abort(bda_audio_stream_t *stream);
void bda_audio_stream_set_volume(bda_audio_stream_t *stream, u32 percent);
```

还应公开 queued bytes、underrun、dropped samples 和 write errors 等统计信息，方便应用
判断声音问题来自核心、调度还是固件队列。

## P1：UTF-8 到 GBK 文本工具

### 问题

固件界面使用 GBK。应用目前需要手写：

```c
"\xce\xde\xd4\xc6"
```

这降低可读性，也容易在标题字节限制、断行和字符串拼接时产生错误。

### 建议

优先提供构建期生成器，而不是依赖旧 GCC 是否完整支持 `-fexec-charset=GBK`：

```powershell
bda-text encode help.zh-CN.txt --encoding gbk -o build/help_text.h
```

生成器应支持：

- 从 UTF-8 输入生成 C byte array。
- 报告无法编码的字符。
- 按固件字节数检查帮助页标题等字段。
- 保留换行并输出可读的源位置诊断。
- 可选生成多语言资源表。

## P1：类型、初始化器和错误码

### 问题

公开结构仍包含 `internal28`、`internal44` 等固件布局字段，应用还会直接使用
`0x100` 之类的模式魔数。大量 wrapper 返回原始 `int` 或 `void`，调用失败时难以定位。

### 建议

- 对 frame descriptor、picture descriptor 和 selector 提供 `*_init()`。
- 用公开枚举替代已验证的模式魔数。
- 将内部布局移动到 `bda/detail/`，公开层使用 opaque state 或 builder。
- 统一 `bda_result_t`，至少区分参数错误、资源不足、固件拒绝和不支持。
- debug 构建记录 draw context、compatible context 和 frame 的所有权。
- 在重复释放、跨 frame 使用 context 和 fixed slot 耗尽前主动报错。

## P1：SDK 版本与能力查询

### 建议接口

```c
u32 bda_sdk_version(void);
int bda_sdk_has_feature(u32 feature);
u32 bda_sdk_target_firmware(void);
```

建议能力项至少包括：

- 系统帮助页。
- 系统文件选择器。
- compatible context 与矩形复制。
- normalized touch input。
- raw PCM。
- 已验证的文件写入和 seek。

当目标系统表为空或版本不匹配时，wrapper 应返回“不支持”，而不是盲目跳转到固定
表项。兼容性矩阵应由同一份机器可读清单生成，避免头文件、文档和模拟器实现漂移。

## P2：统一构建与安装包

复杂项目目前需要自己维护 BDA metadata、图标、数据目录和安装 ZIP。建议引入项目清单：

```toml
[bda]
title = "GAM4980"
category = 9
entry = "src/gam4980_payload.c"
icon = "assets/gam4980-icon.png"

[[package.files]]
source = "应用/数据/游戏/gam4980/8.BIN"
target = "应用/数据/游戏/gam4980/8.BIN"
```

对应命令：

```text
bda build
bda validate
bda package
```

工具应输出可复现的 BDA、安装目录树、ZIP、SHA-256 和构建信息。toolchain setup 还应
检查所有必需二进制及版本，而不是只检查缓存目录是否存在。

## P2：应用级回归套件

现有单 API probe 很重要，但无法覆盖 API 组合后的生命周期问题。建议把
`gam4980-player-for9588` 作为综合回归项目，并增加可重复场景：

1. 启动并连续运行片头动画，检查帧率和混合帧。
2. 打开设置、切换全部页签并恢复游戏。
3. 连续打开和关闭帮助页。
4. 触摸全部虚拟按键，确认不会附带 Escape。
5. 创建、覆盖、重载 `.sav`，然后重启模拟器并再次校验。
6. 重选游戏、取消选择、重新启动和游戏主动退出。
7. 长时间运行后检查 draw slot、heap 和文件 handle 是否泄漏。

模拟器测试应输出：

- 可机器读取的事件和 API 调用日志。
- 固定帧截图和像素哈希。
- NAND 修改前后文件清单与哈希。
- GUI resource ownership 统计。
- 与真机证据分开的验证标签。

## API 分层建议

建议最终形成三层：

| 层级 | 目录 | 内容 |
|---|---|---|
| 应用层 | `sdk/include/bda/` | surface、modal、input、file、audio stream 等安全组合 API |
| 已验证 ABI 层 | `sdk/include/bda/detail/` | 固件系统表 wrapper、结构布局和固定语义 |
| 研究层 | `reverse/` | 候选偏移、失败探针和未经真机闭环的接口 |

普通应用只使用第一层。第二层供 SDK 自身和确实需要低层控制的应用使用，必须明确资源
所有权。第三层不得被发布应用直接包含。

## 建议实施顺序

### 第一阶段：修正高风险契约

1. 重新验证 context copy 的色键语义。
2. 修正或移除错误的 `BDA_GUI_COLOR_KEY_NONE` 命名。
3. 实现 surface present helper。
4. 实现 modal guard。
5. 实现 normalized input，并加入触摸 Escape 回归。

### 第二阶段：减少重复代码

1. 增加 `read_exact`、`write_all`、`get_size` 和路径 helper。
2. 增加 descriptor 初始化器与统一错误码。
3. 增加 UTF-8 到 GBK 生成器。
4. 建立 API 能力清单和运行时查询。

### 第三阶段：完善大型应用支持

1. 增加 audio stream helper。
2. 标准化项目清单、构建和安装 ZIP。
3. 将 `gam4980-player-for9588` 纳入综合回归。
4. 对模拟器和真机结果建立可追踪的证据矩阵。

## 完成标准

本轮优化不应只以“新增了多少函数”为完成标准。建议使用以下结果衡量：

- 应用不再直接操作 `internalXX` 字段和已封装的固件模式魔数。
- 普通 RGB565 应用无需理解 compatible context 和 draw guard 即可无撕裂提交。
- 打开任何同步模态页面都不会泄漏或复用 stale draw context。
- 触摸不会被误判为实体退出键。
- 存档写入不需要每个项目重复实现短写循环。
- 中文帮助内容可以直接以 UTF-8 维护。
- 模拟器回归可以自动发现黑色色键、FAT 持久化和 GUI 生命周期退化。
- 每个正式 API 都能追溯到独立 BDA、验证环境、日志和已知边界。
