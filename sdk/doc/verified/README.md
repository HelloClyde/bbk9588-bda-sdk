# 已动态验证的 API

本目录只收录已经通过独立 BDA 在模拟器中运行，并取得可复核结果的 API。静态反汇编、
原机调用点推断和未闭环 probe 仍放在 `sdk/doc/` 的普通逆向笔记中，不能混入这里。

每份文档必须写明：

- 固件表项、调用约定和公开 wrapper。
- 最小可用示例、返回值语义和错误处理。
- 测试 BDA、运行步骤和可观察结果。
- 本次实际覆盖的范围，以及没有验证的边界。
- 原版 NAND、模拟器 worker copy 和测试文件的处理方式。

当前已验证：

- [Message Box API](msgbox_api.md)：standalone BDA 使用 `GUI+0x2b8` 显示标题、正文和确认按钮。
- [文件写入 API](fs_write_api.md)：`fopen/fwrite/tell/error/close/reopen/read` 写入闭环。
- [实体键轮询 API](input_polling_api.md)：`GUI+0x5d4` 六键状态包和 Linux keycode 映射。
- [触摸按下/抬起 API](touch_press_api.md)：`kj409588/C200` 固件绑定的 pen GPIO 电平查询。
- [图形图元 API](graphics_primitives_api.md)：有效 frame 中的彩色画点、线、圆、矩形轮廓和文字。
