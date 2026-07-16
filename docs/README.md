# BBK 9588 BDA 开发文档

本目录只放已经形成动态验证闭环的公开 API 说明和开发教程。静态推断、候选 ABI、
探针进度和未验证接口统一放在 [`reverse/docs/`](../reverse/docs/README.md)。

普通应用只使用 [`sdk/include/bda_sdk.h`](../sdk/include/bda_sdk.h)。未验证的
[`reverse/bda_research_sdk.h`](../reverse/bda_research_sdk.h) 仅供逆向实验使用。

## 快速开始

已验证源码和预编译 BDA 按类别放在 [`example/`](../example/README.md)。最小程序：

```powershell
python -m bda_packer example\basic\hello_world\hello_world_msgbox.c `
  --title HelloWorld --category 9 `
  -o example\basic\hello_world\HelloWorld.bda

python -m bda_packer.validate example\basic\hello_world\HelloWorld.bda
```

## 已验证 API

| 能力 | 文档 | 验证环境 |
|---|---|---|
| Message Box | [msgbox_api.md](verified/msgbox_api.md) | 模拟器 |
| 文件写入与读回 | [fs_write_api.md](verified/fs_write_api.md) | 模拟器 |
| 六键轮询 | [input_polling_api.md](verified/input_polling_api.md) | 模拟器 |
| 触摸按下与抬起 | [touch_press_api.md](verified/touch_press_api.md) | 真机 |
| 图形图元 | [graphics_primitives_api.md](verified/graphics_primitives_api.md) | 模拟器 |
| 触摸坐标与窗口生命周期 | [touch_window_lifecycle_api.md](verified/touch_window_lifecycle_api.md) | 真机 |
| 双缓冲、VX、色键、dirty rect、tick | [game_rendering_api.md](verified/game_rendering_api.md) | 模拟器 |

![图形图元验证](verified/assets/graphics_primitives_bda_verified.png)

![双缓冲扫雷](verified/assets/game_rendering_minesweeper.png)

## 教程

- [SDK API 目录与公开/研究边界](sdk_api_layout.md)
- [公开 API 准入规则](verified/public_api_policy.md)
- [窗口生命周期与触摸重绘](verified/touch_window_lifecycle_api.md)
- [游戏离屏绘制、精灵和计时](verified/game_rendering_api.md)
- [完整扫雷示例](minesweeper_v1.md)

模拟器通过不自动等于真机通过。每篇文档会单独标出适用固件、验证环境和仍未覆盖的
边界；没有这些信息的接口不得加入公开 SDK。
