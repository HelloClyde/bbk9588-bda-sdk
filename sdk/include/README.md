# `sdk/include` 准入规则

`sdk/include/bda_sdk.h` 是打包器唯一使用的公开 SDK 头文件。这里不是逆向 API
候选目录，只能放入已经动态验证、ABI 稳定且结论确定的系统 API。

## 必须满足的条件

一个 API 进入 `sdk/include` 前，必须同时满足：

1. 使用独立测试 BDA 调用了目标 API，而不是只观察原机应用调用点。
2. 在当前目标固件的真机或模拟器中实际运行，并得到可重复的可观察结果；文档必须
   明确环境，不能把其中一种环境的结果自动扩张到另一种。
3. 参数顺序、参数宽度、返回值语义及必要的数据结构布局已经确定。
4. 在 `sdk/doc/verified/` 有独立说明，记录用法、注意点、固件绑定、测试步骤、
   动态证据和未覆盖边界。
5. 有可编译的最小示例，并保留构建或回归验证。

可观察结果包括屏幕输出、导出的日志或数据文件、输入响应和绘图截图。仅有以下证据
不够进入本目录：

- 静态反汇编或固件表项定位。
- 其他 BDA 的调用点和参数推断。
- C 源码编译、链接或 BDA header 校验通过。
- 模拟器未崩溃、API 返回了一个数值，但结果语义未闭环。
- 尚未复现成功的 probe，或只在逆向笔记中标记为 `_LIKE` 的候选接口。

稳定公开 API、类型和常量的名称不得带 `_like` 或 `_LIKE` 后缀。该后缀只允许出现在
`sdk/api/bda_sdk.h` 和普通逆向笔记的候选名称中；候选接口动态闭环并进入公开头时，
必须同时确定稳定的公开名称。`sdk/include` 不提供带 `_like` 的兼容别名。

## 当前公开范围

- Message Box：`sdk/doc/verified/msgbox_api.md`
- 文件写入与读回：`sdk/doc/verified/fs_write_api.md`
- 六个实体键轮询：`sdk/doc/verified/input_polling_api.md`
- 9588 触摸按下和抬起状态：`sdk/doc/verified/touch_press_api.md`
- frame 绘制链和图形图元：`sdk/doc/verified/graphics_primitives_api.md`
- 真机触摸坐标与完整 frame 生命周期：`sdk/doc/verified/touch_window_lifecycle_api.md`

未达到上述条件的 API 必须留在 `sdk/api/bda_sdk.h` 或 `sdk/doc/` 逆向材料中，
不得被打包器隐式提供。受控 probe 可以显式传 `-I sdk/api` 使用候选头，但这不会改变
候选 API 的验证状态。若后续证据推翻现有 ABI，应立即从公开头移除或降回候选区，
不能为了源码兼容继续声明为稳定 API。
