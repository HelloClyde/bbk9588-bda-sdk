# BDA Packer

`bda_packer` 是公开 SDK 的编译和打包工具，不包含固件探针或应用逆向逻辑。

```text
build.py     编译 freestanding C、链接 flat MIPS image 并组装 BDA
header.py    构造固件 header、XOR 字段和 checksum
validate.py  静态检查 header、entry 和 VX icon
vx_icon.py   解码 PNG、缩放并生成 RGB565 VX 图标
```

安装仓库后使用命令行入口：

```powershell
python -m pip install -e .
bda-pack example\basic\hello_world\hello_world_msgbox.c `
  --title HelloWorld --category 9 -o build\HelloWorld.bda
bda-validate build\HelloWorld.bda
```

传入 RGBA 菜单图标时，`bda-pack` 默认把 alpha 小于等于 `8` 的透明像素写成固件使用的
洋红 RGB565 色键 `0xf81f`；其余半透明像素先与菜单黑色背景合成，以保留抗锯齿边缘：

```powershell
bda-pack app.c --title App --category 9 --icon-png icon.png -o build\App.bda
```

可用 `--icon-alpha-threshold N` 调整阈值。只有需要把透明区域预合成为固定背景色时，才应
传 `--icon-transparent-key none --icon-background RRGGBB`。`bda-icon` 替换已有 BDA
图标时采用相同默认规则，对应关闭参数为 `--transparent-key none`。

## 菜单分类

`--category` 使用 BDA header category 的低 16 位。固件菜单映射为：

| 值 | 菜单 | 总菜单项上限 | 典型内容 |
|---:|---|---:|---|
| `1` | 听说 | `7` | 听力、会话、音标 |
| `2` | 语法 | `5` | 语法学习 |
| `3` | 阅读 | `9` | 阅读、资料内容 |
| `4` | 娱乐天地 | `10` | 游戏 |
| `5` | 考试 | `10` | 考试、课程辅导 |
| `6` | 背诵 | `8` | 单词记忆、背诵 |
| `7` | 词典 | `15` | 翻译、百科词典 |
| `8` | 娱乐 | `10` | 音乐、影音、相册、电子媒体 |
| `9` | 工具 | `20` | 计算器、记事本、时间、系统工具 |

`0` 虽能通过固件的范围检查，但没有发现对应的原机应用目录，不建议使用。开发者
通常应直接传 `1..9`，不要复制原机 BDA 中尚未解释的高 16 位标志。

上限是分类的总菜单项容量，固件预置或硬编码项也会占用槽位，不等于还可添加的 BDA
数量。“娱乐天地”（category `4`）第 11 个 BDA 不展示已经动态验证；其他上限来自
C200 固件静态分析，尚未逐类填满测试。

也可使用 `python -m bda_packer`、`python -m bda_packer.validate` 和
`python -m bda_packer.vx_icon`。输入源码必须定义置于 `.text.bda_main` 的
`bda_main()`，且不能依赖宿主 C runtime。

默认搜索随 wheel 安装的公开 header 和仓库中的 `sdk/include/`。自定义环境可设置：

```powershell
$env:BDA_TOOLCHAIN_PREFIX = "C:\mips\bin\mipsel-none-elf-"
$env:BDA_SDK_INCLUDE = "C:\bbk-sdk\include"
```

`-I/--include-dir` 可重复，并优先于公开 SDK。它只应用于受控逆向 probe；使用
`reverse/bda_research_sdk.h` 构建成功不表示候选 API 已稳定。
