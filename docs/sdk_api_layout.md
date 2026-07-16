# SDK API 目录

`sdk/` 只保存 API header，且只允许已经验证的公开接口，不再混放候选接口、示例、
图片或开发文档：

```text
sdk/include/bda_sdk.h  动态验证后公开的稳定 API
```

未验证的候选 API 单独保存在 `reverse/bda_research_sdk.h`。

仓库打包器默认加入 `sdk/include`，因此普通程序可以直接：

```c
#include "bda_sdk.h"
```

只有 `reverse/examples/` 中的受控研究 probe 才显式传入 `-I reverse`；普通应用不应
依赖候选 header。

- 已验证示例：[example/README.md](../example/README.md)
- 开发者文档：[docs/README.md](README.md)
- 公开 API 准入规则：[docs/verified/public_api_policy.md](verified/public_api_policy.md)
- 触摸与窗口生命周期：[touch_window_lifecycle_api.md](verified/touch_window_lifecycle_api.md)
- 游戏绘图与计时：[game_rendering_api.md](verified/game_rendering_api.md)
