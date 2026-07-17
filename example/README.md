# 已验证 BDA 示例

本目录只收录已经在 BBK 9588 真机或 8013 完整 NAND 模拟器中形成运行闭环的
开发者示例。逆向候选和危险探针保留在 `reverse/examples/`，不会混入这里。

所有源码只包含 `sdk/include/bda_sdk.h`、独立控件头 `sdk/include/bda_controls.h`
或音频头 `sdk/include/bda_audio.h`，不会访问 `reverse/bda_research_sdk.h`。

每个叶子目录中的 `.bda` 都由同目录 `.c` 构建，并已通过 header、entry、checksum 和
图标区静态校验：

```text
basic/hello_world/        hello_world_msgbox.c + HelloWorld.bda
filesystem/fs_write/     fs_write_demo.c + FsWrite.bda
input/key_polling/        key_msgbox_demo.c + KeyInput.bda
input/touch_press/        touch_press_demo.c + TouchPress.bda
input/touch_crosshair/    touch_crosshair_demo.c + TouchCrosshair.bda
graphics/primitives/      graphics_primitives_demo.c + GraphicsPrimitives.bda
graphics/picture_render/  picture_render_demo.c + PictureRender.bda
games/minesweeper/        minesweeper_bda.c + MinesweeperV1.bda + icon
system/runtime_services/  runtime_services_demo.c + RuntimeServices.bda
system/file_selector/     file_selector_demo.c + FileSelector.bda
system/confirm_dialog/    confirm_dialog_probe.c + ConfirmDialog.bda
system/audio_pcm/         audio_pcm_demo.c + AudioPcm.bda
gui/control_gallery/      control_gallery_demo.c + ControlGallery.bda
gui/custom_control/       custom_control_demo.c + CustomControl.bda
gui/gif_player/           gif_player_demo.c + GifPlayer.bda
```

| 示例 | 能力 | 验证环境 | 说明 |
|---|---|---|---|
| `basic/hello_world/` | Message Box | 模拟器 | [API 文档](../docs/verified/msgbox_api.md) |
| `filesystem/fs_write/` | 文件写入、关闭、重开、读回 | 模拟器 | [API 文档](../docs/verified/fs_write_api.md) |
| `input/key_polling/` | 六个实体键轮询 | 模拟器 | [API 文档](../docs/verified/input_polling_api.md) |
| `input/touch_press/` | 触摸按下、抬起状态 | 真机 | [API 文档](../docs/verified/touch_press_api.md) |
| `input/touch_crosshair/` | 触摸坐标、无闪烁重绘、窗口退出 | 真机 | [生命周期教程](../docs/verified/touch_window_lifecycle_api.md) |
| `graphics/primitives/` | 点、线、圆、矩形和文字 | 模拟器 | [API 文档](../docs/verified/graphics_primitives_api.md) |
| `graphics/picture_render/` | 原生尺寸 raw RGB565 动态提交 | 模拟器 | [API 文档](../docs/verified/picture_rendering_api.md) |
| `games/minesweeper/` | 双缓冲、VX、色键、dirty rect、tick | 模拟器 | [游戏绘图教程](../docs/verified/game_rendering_api.md) |
| `system/runtime_services/` | heap、seek、目录和枚举 | 模拟器 | [API 文档](../docs/verified/runtime_services_api.md) |
| `system/file_selector/` | 默认目录、后缀过滤和完整路径返回 | 模拟器 | [API 文档](../docs/verified/file_selector_api.md) |
| `system/confirm_dialog/` | 系统是/否确认框及返回值 | 模拟器 | [API 文档](../docs/verified/msgbox_api.md) |
| `system/audio_pcm/` | 22050 Hz raw PCM、衰减控制、立即 stop 和 AIC 清理 | 模拟器 | [API 文档](../docs/verified/audio_pcm_api.md) |
| `gui/control_gallery/` | 文本、按钮、列表、组合框、进度条和 toolbar | 模拟器 | [控件 API](../docs/verified/controls_api.md) |
| `gui/custom_control/` | 自定义类注册、局部绘制、触摸和注销 | 模拟器 | [教程](../docs/tutorials/custom_controls.md) |
| `gui/gif_player/` | 内存 GIF89a 加载、定时换帧和销毁 | 模拟器 | [控件 API](../docs/verified/controls_api.md) |

## 构建

普通示例可直接打包：

```powershell
python -m bda_packer example\basic\hello_world\hello_world_msgbox.c `
  --title HelloWorld --category 9 `
  -o example\basic\hello_world\HelloWorld.bda
```

扫雷带自定义图标，并放入“娱乐天地”分类：

```powershell
python -m bda_packer example\games\minesweeper\minesweeper_bda.c `
  --title MinesV1 --category 4 `
  --icon-png example\games\minesweeper\minesweeper_icon.png `
  -o example\games\minesweeper\MinesweeperV1.bda
```

控件示例：

```powershell
python -m bda_packer example\gui\control_gallery\control_gallery_demo.c `
  --title Controls --category 9 `
  -o example\gui\control_gallery\ControlGallery.bda

python -m bda_packer example\gui\custom_control\custom_control_demo.c `
  --title CustomCtrl --category 9 `
  -o example\gui\custom_control\CustomControl.bda

python -m bda_packer example\gui\gif_player\gif_player_demo.c `
  --title GifPlayer --category 9 `
  -o example\gui\gif_player\GifPlayer.bda
```

Raw PCM 示例：

```powershell
python -m bda_packer example\system\audio_pcm\audio_pcm_demo.c `
  --title AudioPCM --category 9 `
  -o example\system\audio_pcm\AudioPcm.bda
```

![扫雷运行画面](../docs/verified/assets/game_rendering_minesweeper.png)

## 验证边界

“已验证”只覆盖相应文档写明的固件和环境。模拟器通过不自动等于真机通过；示例也不
代表 `reverse/bda_research_sdk.h` 中的全部研究接口已经稳定。
