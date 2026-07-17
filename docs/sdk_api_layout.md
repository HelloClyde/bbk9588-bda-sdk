# SDK API 目录

`sdk/` 只保存 API header，且只允许已经验证的公开接口，不再混放候选接口、示例、
图片或开发文档：

```text
sdk/include/bda_sdk.h  动态验证后公开的稳定 API
sdk/include/bda_controls.h  已验证控件与自定义控件 API
```

未验证的候选 API 单独保存在 `reverse/bda_research_sdk.h`。

仓库打包器默认加入 `sdk/include`，因此普通程序可以直接：

```c
#include "bda_sdk.h"
```

需要内建或自定义控件时直接包含扩展头；它会自动包含基础头：

```c
#include "bda_controls.h"
```

只有 `reverse/examples/` 中的受控研究 probe 才显式传入 `-I reverse`；普通应用不应
依赖候选 header。

- 已验证示例：[example/README.md](../example/README.md)
- 开发者文档：[docs/README.md](README.md)
- 公开 API 准入规则：[docs/verified/public_api_policy.md](verified/public_api_policy.md)
- 触摸与窗口生命周期：[touch_window_lifecycle_api.md](verified/touch_window_lifecycle_api.md)
- 游戏绘图与计时：[game_rendering_api.md](verified/game_rendering_api.md)
- 堆、seek 与目录服务：[runtime_services_api.md](verified/runtime_services_api.md)
- 原始 RGB565 picture 提交：[picture_rendering_api.md](verified/picture_rendering_api.md)
- 系统文件选择器：[file_selector_api.md](verified/file_selector_api.md)
- Message Box 与确认框：[msgbox_api.md](verified/msgbox_api.md)
- 内建控件：[controls_api.md](verified/controls_api.md)
- 自定义控件教程：[custom_controls.md](tutorials/custom_controls.md)
