# 已动态验证的 API

本目录只收录已经通过独立 BDA 在模拟器或真机中运行，并取得可复核结果的 API。静态
反汇编、原机调用点推断和未闭环 probe 仍放在 `reverse/docs/` 的逆向笔记中，不能混入
这里。每项记录必须明确验证环境，不能把模拟器结果自动扩张为真机结论。

每份文档必须写明：

- 固件表项、调用约定和公开 wrapper。
- 最小可用示例、返回值语义和错误处理。
- 测试 BDA、运行步骤和可观察结果。
- 本次实际覆盖的范围，以及没有验证的边界。
- 原版 NAND、模拟器 worker copy 和测试文件的处理方式。

当前已验证：

- [Message Box 与确认框 API](msgbox_api.md)：`GUI+0x2b8` 的单按钮消息框、是/否布局及返回值。
- [文件写入 API](fs_write_api.md)：`fopen/fwrite/tell/error/close/reopen/read` 写入闭环。
- [实体键轮询 API](input_polling_api.md)：`GUI+0x5d4` 六键状态包和 Linux keycode 映射。
- [触摸按下/抬起 API](touch_press_api.md)：`kj409588/C200` 固件绑定的 pen GPIO 电平查询。
- [图形图元 API](graphics_primitives_api.md)：有效 frame 中的彩色画点、线、圆、矩形轮廓和文字。
- [触摸窗口与完整生命周期](touch_window_lifecycle_api.md)：真机 V23 两阶段绘制、无闪烁坐标十字和可返回主菜单的 frame 退出链。
- [游戏离屏绘制、精灵与计时 API](game_rendering_api.md)：8013 验证的 compatible context、VX、矩形复制、洋红色键、dirty rect 和 25 ms tick。
- [堆、文件定位与目录 API](runtime_services_api.md)：8013 验证的 alloc/free、seek、mkdir/chdir 和完整目录枚举生命周期。
- [原始 RGB565 Picture 提交 API](picture_rendering_api.md)：8013 验证的 GUI `+0x410` 原生尺寸动态提交和 28-byte descriptor。
- [系统文件选择器 API](file_selector_api.md)：8013 验证的默认目录、后缀过滤、选择/取消和结果链表释放。
- [控件 API](controls_api.md)：8013 验证的内建控件、内存 GIF 自动播放、消息 helper、
  自定义类注册和失败边界。
