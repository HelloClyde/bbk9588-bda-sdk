# BDA Packer

本目录是独立的 BBK 9588 BDA 编译和打包工具，不包含固件探针或应用逆向脚本。

```text
build.py     编译 freestanding C、链接 flat MIPS image 并组装 BDA
header.py    固件 header 字段、XOR 和 checksum
validate.py  静态复现固件校验并检查 entry/VX block
vx_icon.py   PNG 解码、缩放和 VX RGB565 生成
```

构建：

```powershell
python -m bda_packer reverse\examples\hello_world_msgbox.c `
  --title HelloWorld `
  --category 4 `
  --icon-png path\to\icon.png `
  -o build\HelloWorld.bda
```

校验：

```powershell
python -m bda_packer.validate build\HelloWorld.bda
```

输入必须是定义 `bda_main()` 的 freestanding C 源码。打包器不读取已有 BDA，
不提供 template、main patch、passthrough 或汇编打包模式。
编译始终使用 `sdk/include/bda_sdk.h`，不依赖 `sdk/api`、`reverse/sdk` 或工作区外部 header。
`sdk/include` 只公开已经由独立 BDA 动态验证的稳定 API；准入规则见
`sdk/include/README.md`。逆向候选接口不会自动暴露给打包器。
