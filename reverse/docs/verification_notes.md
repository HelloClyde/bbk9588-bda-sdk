# SDK 验证边界

## 自动验证

`scripts/verify_sdk.ps1` 执行：

- header XOR、checksum、category、entry 和 VX icon 单元测试。
- standalone C 编译、`.bss` 零填充和 MIPS o32 调用约定测试。
- `bda_validate.py` 固件规则校验。
- SDK 示例编译 smoke。
- 本地存在 `系统\数据\C200.bin` 时生成 runtime API table 报告。

```powershell
.\scripts\verify_sdk.ps1 -SkipToolchainSetup
```

`-Emu` 只运行 emulator frontend smoke，不制作 NAND 镜像。

## 动态验证

模拟器动态验证必须满足：

1. frontend 从原版 NAND 创建 persistent worker copy。
2. 只通过 `/api/files/import`、`/api/files/export`、`/api/files/delete` 操作 BDA 和日志。
3. 不直接修改原版 NAND，不直接操作运行中的 worker image。
4. 停机后从 worker checkpoint 导出日志或截图。
5. 只有形成可复核闭环的 API 才写入 `docs/verified/`。

真机动态验证不依赖 frontend worker，但必须记录测试 BDA 的源码、SHA-256、固件/机型、
可观察画面或实时日志，以及是否能够正常退出恢复系统。`TouchStageV11.bda` 是当前首个
完成触摸窗口全生命周期闭环的真机 standalone 样本，记录见
`docs/verified/touch_window_lifecycle_api.md`。

`docs/verified/` 之外的 API 名称、ABI 和语义都属于逆向候选。即使静态调用点
看起来合理，也不能作为新应用的可靠系统 API。

## Standalone builder

唯一构建入口是：

```powershell
python -m bda_packer example\basic\hello_world\hello_world_msgbox.c `
  --title HelloWorld `
  --category 9 `
  --icon-png path\to\icon.png `
  -o build\HelloWorld.bda
```

仓库不提供基于既有 BDA 的构建或 patch 模式。静态校验通过不等于系统 API 已验证；
入口运行和 API 行为都要分别做动态 smoke。
