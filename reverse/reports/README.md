# BDA 逆向报告

本目录存放原机内置原生 BDA 应用的逐应用逆向报告和清点索引。这里的材料用于支撑 `sdk/doc` 中的 SDK API 命名、结构体字段和风险说明。

## 生成索引

- `bda_inventory.json`：面向脚本处理的原机 `应用/程序/*.bda` 清点结果。
- `bda_inventory.md`：面向人工阅读的简表，包含 header、分类、布局、DLX 引用和原始间接 API offset 统计。
- `c200_menu_index_notes.md`：C200 首页/menu/deploy 相关字符串和硬编码 BDA 路径线索。

清点表只是索引。完整的逐 BDA 报告应继续补齐：

```text
1. Header 和菜单身份
2. 运行时布局、入口、BSS、关键全局变量
3. 外部资源和数据文件
4. 主启动流程
5. GUI、窗口和事件行为
6. FS、媒体、时间、输入等 API 使用
7. 与其他 BDA、C200 反汇编和硬件探针的交叉验证
8. 未确认点和后续探针建议
```

## 已开始的深度报告

- `reverse/reports/notepad_bda_report.md`
- `reverse/reports/album_bda_report.md`
- `reverse/reports/time_bda_report.md`
- `reverse/reports/music_bda_report.md`
- `reverse/reports/alarm_bda_report.md`
- `reverse/reports/video_bda_report.md`
- `reverse/reports/recorder_bda_report.md`
- `reverse/reports/ebook_bda_report.md`
- `reverse/reports/settings_bda_report.md`
- `reverse/reports/paint_bda_report.md`
- `reverse/reports/eros_bda_report.md`
- `reverse/reports/linkgame_bda_report.md`
- `reverse/reports/blackwhite_bda_report.md`
- `reverse/reports/jiugongge_bda_report.md`
- `reverse/reports/thunder_bda_report.md`
- `reverse/reports/tank_bda_report.md`
- `reverse/reports/sango_bda_report.md`
- `reverse/reports/schedule_bda_report.md`
- `reverse/reports/ninecourse_bda_report.md`
- `sdk/doc/element_bda_notes.md`
- `sdk/doc/gameboy_notes.md`
- `sdk/doc/bbvm_notes.md`
- `sdk/doc/game_framework_notes.md`
- `sdk/doc/picture_notes.md`
- `sdk/doc/paint_notes.md`
- `sdk/doc/showcase_notes.md`
- `sdk/doc/usb_debug_notes.md`

最后一组是面向 SDK 的专题笔记，不是最终逐应用报告。后续整理时应继续把每条 SDK 结论链接回支持它的原机 BDA 证据。
