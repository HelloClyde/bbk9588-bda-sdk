# 发布检查清单

1. 确认发行包保留根目录 `LICENSE`、`NOTICE` 和 `DATA_NOTICE.md`。
2. 同步 `pyproject.toml`、`bda_packer.__version__`、`bda_sdk.h` 和 changelog 版本。
3. 运行 `.\scripts\verify_sdk.ps1`，确保全量测试和公开示例编译通过。
4. 运行 `python -m build`，在干净虚拟环境安装 wheel 并构建 HelloWorld。
5. 检查 wheel 包含 `bda_packer/include/*.h`，不包含固件、NAND、BDA dump 或工具链。
6. 更新 [兼容性矩阵](compatibility.md) 和每个新增 API 的验证环境。
7. 确认 `git status --short` 中没有 `系统/`、`应用/`、`build/` 或实验日志。
8. 给提交和 tag 使用同一 SemVer 版本；alpha 阶段允许不兼容的研究区变化。

`example/**/*.bda` 是唯一允许提交的常规 BDA 生成物，且必须与同目录源码对应、通过
静态校验，并在文档中记录动态验证环境。
