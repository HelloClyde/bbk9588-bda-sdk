# 原生 BDA SDK

本目录只放面向 BDA 开发者使用的 SDK 代码和中文文档，逆向工具、probe 和原机报告仍放在 `reverse/`。

```text
include/ 稳定公开 C header
api/     逆向候选 header 和开发者示例
doc/     中文 API 文档、C200 表项说明和开发笔记
```

开发 entry：

- `include/bda_sdk.h`：打包器默认使用的稳定公开 BDA SDK header。
- `api/bda_sdk.h`：受控 probe 使用的逆向候选 header，不会被默认构建隐式包含。
- `api/examples/hello_msgbox.c`：最小 message box 示例。
- `api/examples/hello_world_msgbox.c`：standalone 打包器动态验证用的 HelloWorld message box 示例。
- `api/examples/gui_rect_contains_demo.c`：rect helper 示例。
- `api/examples/gui_screen_width_demo.c`：屏幕宽度常量查询示例。
- `api/examples/input_state_demo.c`：input packet/event/state 查询示例。
- `api/examples/mem_alloc_demo.c`：firmware heap alloc/free 示例。
- `api/examples/fs_read_demo.c`：file open/read/seek/tell/close 示例。
- `api/examples/fs_read_raw_demo.c`：便捷 `read_raw(file, buffer, size)` 参数顺序示例。
- `api/examples/fs_write_demo.c`：写入、tell、关闭、重开、读回并比较的文件 API 闭环示例。
- `api/examples/fs_find_demo.c`：directory enumeration 结构和 findclose 收尾示例。
- `api/examples/fs_diskinfo_demo.c`：disk/storage 容量查询示例。
- `api/examples/fs_status_demo.c`：storage ready 和 path stat/access 示例。
- `api/examples/res_state_demo.c`：RES state snapshot 示例。
- `api/examples/key_msgbox_demo.c`：轮询六字节实体键 packet 并用 MsgBox 显示键名。
- `api/examples/touch_press_demo.c`：已验证的触摸按下、抬起轮询和 NAND 日志示例。
- `api/examples/touch_crosshair_demo.c`：真机 V23 两阶段绘制的触摸坐标与无闪烁十字定位程序。
- `api/examples/graphics_primitives_demo.c`：已验证的 frame 图元绘制和彩色像素示例。
- `api/examples/tile_blit_probe.c`：tile framebuffer blit ABI/build probe；真机已确认逐块 flip 后死机，不能作为游戏绘图示例。
- `api/examples/minesweeper_bda.c`：使用公开 API 的 9x9 可玩扫雷，8013 已完成胜负、触摸和退出闭环。
- `doc/README.md`：如何编写、编译和验证原生 BDA 程序。
- `doc/api_catalog.md`：SDK 已命名 API 与原机调用覆盖。
- `doc/system_api_tables.md`：从 `C200.bin` 导出的系统 API 表函数地址。
- `doc/verified/README.md`：动态验证文档专区及准入标准。
- `doc/verified/msgbox_api.md`：已验证的 Message Box ABI、最小用法和模拟器截图。
- `doc/verified/fs_write_api.md`：已验证的文件写入 API、注意点和 NAND 导出证据。
- `doc/verified/input_polling_api.md`：已验证的六键轮询 API、映射和去抖方式。
- `doc/verified/touch_press_api.md`：已验证的触摸按下/抬起 API、固件绑定和动态证据。
- `doc/verified/graphics_primitives_api.md`：已验证的图元绘制 API、生命周期和动态证据。
- `doc/verified/touch_window_lifecycle_api.md`：真机已验证的触摸坐标、实时日志和完整窗口退出顺序。
- `doc/verified/game_rendering_api.md`：图文说明 compatible context、VX、双缓冲、色键、dirty rect 和 25 ms tick。
- `doc/game_api_verification_progress.md`：游戏候选系统 API 的静态、模拟器和真机分级验证进度。
- `doc/verification_notes.md`：verify 覆盖、已验证能力和 `_LIKE` API 风险边界。

仓库自带打包器默认加入 `sdk/include`，稳定示例源码可以直接：

```c
#include "bda_sdk.h"
```

只有研究 probe 才显式传入 `-I sdk/api`；普通应用不应依赖候选 header。
