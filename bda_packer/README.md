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
