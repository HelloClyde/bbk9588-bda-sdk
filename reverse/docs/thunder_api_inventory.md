# 雷霆战机.bda runtime API inventory

本表由 `reverse/bda_sdk_usage.py` 从 BDA 间接调用、SDK header 和 C200 固件函数表直接生成。
它只统计可识别的 runtime table 间接调用；随 BDA 静态链接的 GUI framework/libc 函数不在此表中。

- BDA：`fly-src-api\雷霆战机.bda`
- SHA-256：`75e389c5409360ae47fe4e04c20b6856c2d6d72016e3100c0da54373fcb14534`
- runtime file base：`0x81bf6a28`
- C200：`build\minesweeper_snapshot\系统\数据\C200.bin`
- 间接调用总数：295
- 唯一 table entry：78

生成命令：

```powershell
python reverse\bda_sdk_usage.py "fly-src-api\雷霆战机.bda" -o "reverse\docs\thunder_api_inventory.md"
```

## Table 汇总

| Table | 调用数 | 唯一 entry | BDA table global | C200 table VA |
| --- | ---: | ---: | ---: | ---: |
| RES | 14 | 2 | `0x81c16ba0` | `0x80280d30` |
| GUI | 143 | 48 | `0x81c16ba4` | `0x80280e60` |
| SYS | 23 | 10 | `0x81c16ba8` | `0x80280c60` |
| FS | 72 | 16 | `0x81c16bac` | `0x80280dd0` |
| MEM | 43 | 2 | `0x81c16bb0` | `0x8028169c` |

## 完整调用表

`未公开` 表示已识别固件行为但不适合作为通用 SDK API；它不等于未知。

| Table | Offset | 调用数 | SDK 名称 | C200 function VA | First instruction | 行为 |
| --- | ---: | ---: | --- | ---: | --- | --- |
| RES | +0x090 | 3 | `BDA_RES_GET_STATE_LIKE` | `0x80017580` | `addiu $sp, $sp, -0x50` | 资源/图片状态 snapshot；C200 从 0xb0003004 取状态源，向 out_state 写 7 个 word，无稳定 return value。 |
| RES | +0x094 | 11 | `BDA_RES_ENTRY_094_LIKE` | `0x800098c0` | `sw $a1, 4($sp)` | trace/log；历史 DLX loader 名称已废弃。 |
| GUI | +0x030 | 5 | `BDA_GUI_EVENT_POLL_LIKE` | `0x800dbfd0` | `addiu $sp, $sp, -0x28` | event poll；C200 参数为 message_buffer,frame_or_handle，会填 0x1c byte message packet。 |
| GUI | +0x03c | 4 | `BDA_GUI_NOTIFY_LIKE` | `0x800dced0` | `lui $t1, 0x8082` | 异步 notify/post；C200 将 handle,message,a,b 写入 frame queue，0xb1 只置 pending flag。 |
| GUI | +0x040 | 2 | `BDA_GUI_SEND` | `0x800dd380` | `addiu $sp, $sp, -0x18` | 同步 send；C200 直接调用 handle+0x88 wndproc，参数为 handle,message,wparam,lparam。 |
| GUI | +0x04c | 2 | `BDA_GUI_FRAME_RELEASE_LIKE` | `0x800dd31c` | `lui $a1, 0x8082` | frame release/request；C200 解析 handle/default slot 后设置 object 高位状态 flag。 |
| GUI | +0x050 | 5 | `BDA_GUI_EVENT_STEP_LIKE` | `0x800de378` | `addiu $sp, $sp, -0x20` | event step；C200 读取 a0=message_buffer，只处理 message 0x10/0x13 派生通知。 |
| GUI | +0x054 | 5 | `BDA_GUI_EVENT_DISPATCH_LIKE` | `0x800dd4b8` | `addiu $sp, $sp, -0x18` | event dispatch；C200 读取 message_buffer 并调用目标 handle 的 +0x88 wndproc。 |
| GUI | +0x074 | 10 | `BDA_GUI_PUMP_PRESENT_LIKE` | `0x800d48a8` | `addiu $sp, $sp, -0x18` | 绘图/present guard；C200 保存 a0，a0=0 时触发 present/update；缺少原机 surface/context 时 TileBlit 会逐块 flip 后死机。 |
| GUI | +0x084 | 2 | `BDA_GUI_REGISTER_FRAME_LIKE` | `0x800cc1c8` | `addiu $sp, $sp, -0x50` | 注册 frame/window descriptor；C200 读取 0x34 byte descriptor 后创建内部 window object。 |
| GUI | +0x088 | 2 | `BDA_GUI_FRAME_STOP_LIKE` | `0x800ce090` | `addiu $sp, $sp, -0x20` | 停止 frame/window；C200 只读取 handle，解析 frame 后发送内部 0x66/0xf1 message。 |
| GUI | +0x08c | 2 | `BDA_GUI_DEFAULT_PROC_LIKE` | `0x800ca8c0` | `addiu $v0, $a1, -1` | default window procedure fallback；C200 参数为 handle,message,wparam,lparam。 |
| GUI | +0x0e0 | 13 | `BDA_GUI_OBJECT_OP_LIKE` | `0x800ccf64` | `addiu $sp, $sp, -0x20` | object refresh/notify；C200 只读取 object 并发送内部 0xb1 message。 |
| GUI | +0x0e4 | 4 | `BDA_GUI_OBJECT_DRAW_BEGIN_LIKE` | `0x800ce928` | `addiu $sp, $sp, -0x28` | object draw begin wrapper；C200 检查 object kind，调用 GUI+0x308 取得 draw context 并递增 draw 计数。 |
| GUI | +0x0e8 | 2 | `BDA_GUI_OBJECT_DRAW_END_LIKE` | `0x800ce9f0` | `addiu $sp, $sp, -0x28` | object draw end wrapper；C200 递减 draw 计数并调用 GUI+0x30c(draw_context)，无稳定 return value。 |
| GUI | +0x134 | 1 | `BDA_GUI_ACTIVE_FRAME_SET_LIKE` | `0x800cad3c` | `addiu $sp, $sp, -0x20` | 设置/切换当前 active frame；C200 写内部 +0xd8，并向旧/新 frame 发 0x31/0x30。 |
| GUI | +0x17c | 2 | `BDA_GUI_CLOSE_FRAME_LIKE` | `0x800cdffc` | `addiu $sp, $sp, -0x18` | 关闭并释放 frame/window；V11 真机确认应在 stop/release 和 event poll 结束后调用，且无稳定返回值。 |
| GUI | +0x1a8 | 1 | `BDA_GUI_DESTROY_LIKE` | `0x800cd41c` | `addiu $sp, $sp, -0x30` | destroy control/object；C200 要求 kind=1 subtype=0x12，先发内部 0x64 再摘链释放。 |
| GUI | +0x1ac | 1 | `BDA_GUI_WINDOW_TIMER_START_LIKE` | `0x800de150` | `addiu $sp, $sp, -0x28` | window timer start；注册 (frame,timer_id,period_ms)，内部消息 0x162，最多 16 个活动记录。 |
| GUI | +0x1b0 | 1 | `BDA_GUI_WINDOW_TIMER_STOP_LIKE` | `0x800de190` | `addiu $sp, $sp, -0x28` | window timer stop；按 (frame,timer_id) 注销，内部消息 0x163。 |
| GUI | +0x2b8 | 1 | `BDA_GUI_MSGBOX` | `0x800c6544` | `addiu $sp, $sp, -0x28` | message box，hardware probe 已确认可用于简单 BDA demo。 |
| GUI | +0x2fc | 7 | `BDA_GUI_DRAW_OBJECT_CREATE_LIKE` | `0x800bd36c` | `sll $v1, $a0, 2` | draw/resource object table 查询；C200 只读取 kind/index，范围为 0..16。 |
| GUI | +0x300 | 3 | `BDA_GUI_DISPLAY_METRIC_LIKE` | `0x800bc8fc` | `addiu $sp, $sp, -0x18` | display backend metric 查询；C200 使用 context,metric，metric 范围 0..6；Thunder 用 metric=6 作为 framebuffer 像素字节因子。 |
| GUI | +0x304 | 1 | `BDA_GUI_CURRENT_DRAW_LIKE` | `0x800bceec` | `addiu $sp, $sp, -0x18` | current draw context；C200 读取 handle，从 5 个普通 slot 取/初始化 context，并以 mode=0 调内部 helper；满池扫描存在越界缺陷。 |
| GUI | +0x30c | 1 | `BDA_GUI_END_DRAW_LIKE` | `0x800bd4b0` | `addiu $sp, $sp, -0x20` | 结束 draw 并归还 fixed context slot；无稳定 return value，必须与 +0x304/+0x308 配对。 |
| GUI | +0x310 | 2 | `BDA_GUI_COMPAT_CONTEXT_CREATE_LIKE` | `0x800bd100` | `addiu $sp, $sp, -0x30` | compatible draw context create；C200 分配 0xd4 byte context 并复制 source context 的 drawable bounds/backend；V19 验证可同时创建两块。 |
| GUI | +0x314 | 2 | `BDA_GUI_SURFACE_FLUSH_LIKE` | `0x800bd584` | `addiu $sp, $sp, -0x18` | surface/canvas flush 并释放 context；C200 调 backend +0x34 后释放 object；V19 验证两块 compatible surface 可分别释放。 |
| GUI | +0x334 | 2 | `BDA_GUI_SET_FILL_COLOR_LIKE` | `0x800b2c7c` | `lui $v1, 0x8082` | 设置 fill color；C200 写 context+0x14 并返回旧值。 |
| GUI | +0x338 | 6 | `BDA_GUI_SET_TEXT_MODE_LIKE` | `0x800b2c94` | `lui $v1, 0x8082` | 设置文本模式/背景模式；C200 写 context+0x18 并返回旧值。 |
| GUI | +0x33c | 2 | `BDA_GUI_SET_TEXT_COLOR_LIKE` | `0x800b2cac` | `lui $v1, 0x8082` | 设置文本颜色；C200 写 context+0x50 并返回旧值。 |
| GUI | +0x358 | 6 | `BDA_GUI_SELECT_DRAW_OBJECT_LIKE` | `0x800b2d40` | `lui $v1, 0x8082` | select draw object；C200 把 object 写入 context+0x30 并返回旧值，Thunder 会在绘制后恢复旧 object。 |
| GUI | +0x35c | 3 | `BDA_GUI_OBJECT_BIND_LIKE` | `0x800b2d58` | `lui $v1, 0x8082` | draw context resource/image slot setter；C200 写 context+0x20 并返回旧值。 |
| GUI | +0x368 | 2 | `BDA_GUI_PUT_PIXEL_LIKE` | `0x800b68c0` | `addiu $sp, $sp, -0x48` | 画点/put pixel；C200 使用 context,x,y,color 并经 backend +0xb0 提交。 |
| GUI | +0x378 | 5 | `BDA_GUI_RGB_LIKE` | `0x800bc2e0` | `lui $v1, 0x8047` | RGB 颜色构造或转换；C200 使用 a1/a2/a3 低 8 位和 draw/context callback。 |
| GUI | +0x37c | 1 | `BDA_GUI_LINE_TO_LIKE` | `0x800b715c` | `addiu $sp, $sp, -0x50` | line-to primitive；C200 使用 context,x,y，从 context+0x34/+0x38 取旧点，裁剪后调用 line backend。 |
| GUI | +0x380 | 1 | `BDA_GUI_MOVE_TO_LIKE` | `0x800bc328` | `lui $v0, 0x8082` | move-to primitive；C200 使用 context,x,y，写 context+0x34/+0x38。 |
| GUI | +0x388 | 1 | `BDA_GUI_CIRCLE_LIKE` | `0x800b7494` | `addiu $sp, $sp, -0x48` | circle primitive；C200 使用 context,center_x,center_y,radius，并按圆的 bounding rect clipping。 |
| GUI | +0x38c | 1 | `BDA_GUI_RECTANGLE_LIKE` | `0x800b76d8` | `addiu $sp, $sp, -0x50` | rectangle primitive；C200 使用 context,left,top,right,bottom，第五参数从 stack+0x10 读取。 |
| GUI | +0x3f8 | 2 | `BDA_GUI_BLIT_LIKE` | `0x800c0ba8` | `addiu $sp, $sp, -0x20` | framebuffer/region blit；C200 使用 x,y,height,width,buffer 五参数，依赖原机 surface/context，SDK 仅作 unsafe probe。 |
| GUI | +0x400 | 2 | `BDA_GUI_BLIT_ALT_LIKE` | `0x800c0c90` | `lui $v1, 0x8047` | 带全局 clip/prepare 的 blit；C200 使用 x,y,height,width,buffer 五参数，TileBlit 真机会逐块 flip 后死机。 |
| GUI | +0x40c | 3 | `BDA_GUI_REGION_DRAW_LIKE` | `0x800b2e30` | `addiu $sp, $sp, -0x50` | region draw/copy；C200 使用 context,x,y,width,height 五参数。 |
| GUI | +0x414 | 8 | `BDA_GUI_RENDER_HELPER_LIKE` | `0x800b34c0` | `lui $v1, 0x8047` | low-level render helper；C200 读取 descriptor、多个 stack 参数并可分配临时 buffer。 |
| GUI | +0x418 | 6 | `BDA_GUI_RENDER_FINISH_LIKE` | `0x800b3d90` | `addiu $sp, $sp, -0x60` | 双 context 矩形复制；stack+0x14 为 destination，stack+0x20 为 RGB565 color_key_or_zero；V19-V21 验证 compatible 合成、0xf81f 洋红透明键和 dirty rect 局部提交。 |
| GUI | +0x4a4 | 1 | `BDA_GUI_CURRENT_FONT_LIKE` | `0x800bf744` | `lui $v1, 0x8082` | current font pointer getter；C200 返回 context+0x54，context=0 时使用 default draw context。 |
| GUI | +0x4d0 | 1 | `BDA_GUI_FONT_CELL_WIDTH_LIKE` | `0x800c1c68` | `lui $v0, 0x8082` | font cell width-like metric；C200 返回 current font descriptor +0x38。 |
| GUI | +0x4d4 | 1 | `BDA_GUI_FONT_CELL_HEIGHT_LIKE` | `0x800c1c80` | `addiu $sp, $sp, -0x20` | font cell height-like metric；C200 查询 primary/fallback font callback 并返回较大值。 |
| GUI | +0x4f0 | 4 | `BDA_GUI_DRAW_TEXT_LIKE` | `0x800c0d40` | `addiu $sp, $sp, -0x50` | draw GBK/ASCII text；C200 使用 handle,x,y,text,extra，extra<0 时按 strlen。 |
| GUI | +0x5d4 | 1 | `BDA_GUI_INPUT_PACKET_LIKE` | `0x8001b518` | `addiu $sp, $sp, -0x18` | GAMEBOY/input 按键包 helper；C200 清 6 byte packet 后写入按键状态。 |
| GUI | +0x6a8 | 1 | `BDA_GUI_FILE_SELECTOR_OPEN_LIKE` | `0x80021334` | `addiu $sp, $sp, -0x5e0` | file selector open/session；C200 只读取 a0=mode，内部构造 modal frame。 |
| GUI | +0x6e0 | 2 | `BDA_GUI_GAME_DISPLAY_PUMP_LIKE` | `0x8005b844` | `addiu $sp, $sp, -0x20` | 触摸长按驱动的 game state pump；C200 无参数，先查 pen GPIO，阈值 0x1068 后写全局状态；有副作用。 |
| SYS | +0x040 | 3 | `BDA_SYS_AUDIO_ATTENUATION_SET_LIKE` | `0x8018921c` | `slti $v0, $a0, 0` | raw PCM attenuation setter；C200 clamp 到 0..98，写 pending value，下一次 audio write 量化并应用。 |
| SYS | +0x044 | 1 | `BDA_SYS_AUDIO_ATTENUATION_GET_LIKE` | `0x80189248` | `addiu $sp, $sp, -0x18` | raw PCM attenuation getter；C200 无参数，返回当前 effective attenuation（0..96，步进 3）。 |
| SYS | +0x050 | 1 | 未公开 | `0x8018ef04` | `jr $ra` | C200 中是立即返回 1 的 stub，不公开 SDK wrapper。 |
| SYS | +0x054 | 1 | 未公开 | `0x8018ef0c` | `jr $ra` | C200 中是立即返回 1 的 stub，不公开 SDK wrapper。 |
| SYS | +0x058 | 2 | `BDA_SYS_PACKAGE_SOUND_OP58_LIKE` | `0x8018ecb4` | `lui $v0, 0x804c` | 打包音效 init/start；C200 使用 a0=descriptor，成功置 0x804c4ba4 并返回 1。 |
| SYS | +0x05c | 4 | `BDA_SYS_PACKAGE_SOUND_OP5C_LIKE` | `0x8018e958` | `addiu $sp, $sp, -0x28` | 打包音效 descriptor 操作；C200 使用 slot,descriptor,a2,flags 四参数。 |
| SYS | +0x060 | 2 | `BDA_SYS_PACKAGE_SOUND_OP60_LIKE` | `0x8018ee98` | `lui $v0, 0x804c` | 打包音效状态置位；C200 无参数，0x804c4ba8 从 0 置 1 时返回 1。 |
| SYS | +0x064 | 4 | `BDA_SYS_PACKAGE_SOUND_OP64_LIKE` | `0x8018eed0` | `lui $v0, 0x804c` | 打包音效状态清除；C200 无参数，0x804c4ba8 从 1 清 0 时返回 1。 |
| SYS | +0x068 | 4 | `BDA_SYS_PACKAGE_SOUND_OP68_LIKE` | `0x8018ee18` | `lui $v0, 0x804c` | 打包音效 release/stop；C200 无参数，关闭全局 handle 并清 0x804c4ba4。 |
| SYS | +0x08c | 1 | `BDA_SYS_AUDIO_RESET_LIKE` | `0x8001dc04` | `addiu $sp, $sp, -0x18` | raw audio reset/init；C200 无参数，关闭全局 audio object 后进入初始化路径，无稳定 return value。 |
| FS | +0x000 | 9 | `BDA_FS_OPEN` | `0x80170b68` | `addiu $sp, $sp, -0x28` | fopen-style；原机代码常传 rb/wb 等 mode string。 |
| FS | +0x004 | 15 | `BDA_FS_CLOSE` | `0x8017a928` | `addiu $sp, $sp, -0x20` | fclose-style；C200 单参数 file，return value 来自内部 close helper。 |
| FS | +0x008 | 11 | `BDA_FS_READ` | `0x8017a978` | `addiu $sp, $sp, -0x30` | fread-style；C200 参数顺序为 buffer,size,count,file，失败返回 0。 |
| FS | +0x00c | 5 | `BDA_FS_WRITE` | `0x8017ab2c` | `addiu $sp, $sp, -0x30` | fwrite-style；C200 参数顺序为 buffer,size,count,file，失败返回 0。 |
| FS | +0x010 | 15 | `BDA_FS_SEEK` | `0x801712a0` | `addiu $sp, $sp, -0x30` | fseek-style；C200 参数为 file,offset,whence，无效 whence 返回 -1。 |
| FS | +0x014 | 4 | `BDA_FS_TELL` | `0x8017ac18` | `lh $v1, 0x48($a0)` | ftell-style；C200 检查 file+0x48 index，有效路径返回 file+0x44。 |
| FS | +0x018 | 1 | `BDA_FS_EOF_LIKE` | `0x8017ac84` | `lh $v1, 0x48($a0)` | feof-like；C200 检查 file+0x44 当前位置和 file+0x20 size-like word。 |
| FS | +0x01c | 1 | `BDA_FS_ERROR_LIKE` | `0x8017acfc` | `lh $v1, 0x48($a0)` | ferror-like；C200 检查 file+0x4a 的 0x1000 error flag。 |
| FS | +0x020 | 1 | `BDA_FS_CLEAR_ERROR_LIKE` | `0x8017ad70` | `lh $v1, 0x48($a0)` | clearerr-like；C200 清除 file+0x4a 的 0x1000 error flag。 |
| FS | +0x024 | 1 | `BDA_FS_REMOVE` | `0x801717f4` | `addiu $sp, $sp, -0x28` | remove/unlink；C200 解析单参数 path 后删除文件。 |
| FS | +0x028 | 1 | `BDA_FS_RENAME_LIKE` | `0x80171d24` | `addiu $sp, $sp, -0x30` | rename/move-like；C200 使用 old_path,new_path，分别解析后调用内部 rename helper。 |
| FS | +0x02c | 2 | `BDA_FS_CHDIR_LIKE` | `0x8016fe18` | `addiu $sp, $sp, -0x40` | chdir/current directory 切换；C200 检查目录属性位 0x4000。 |
| FS | +0x030 | 2 | `BDA_FS_MKDIR_LIKE` | `0x80171f8c` | `addiu $sp, $sp, -0x28` | mkdir-style；C200 解析 path 后调用内部创建目录 helper。 |
| FS | +0x03c | 1 | `BDA_FS_FINDFIRST_LIKE` | `0x80172630` | `addiu $sp, $sp, -0x30` | findfirst/search-open；C200 参数为 pattern,attr,find_data，内部申请 0x20a 临时 path buffer。 |
| FS | +0x044 | 2 | `BDA_FS_FINDCLOSE_LIKE` | `0x8017ae90` | `addiu $sp, $sp, -0x28` | findclose-style；C200 读取 find_data+0x10 index，并释放 find_data+0x00 cursor。 |
| FS | +0x068 | 1 | 未公开 | `0x8017a200` | `addiu $sp, $sp, -0x250` | file-object block read helper；a3 是内部 file descriptor，不公开 SDK wrapper。 |
| MEM | +0x008 | 19 | `BDA_MEM_ALLOC` | `0x80007648` | `addiu $sp, $sp, -0x20` | 固件堆内存分配/heap alloc；C200 单参数 size，锁保护后返回 pointer。 |
| MEM | +0x00c | 24 | `BDA_MEM_FREE` | `0x800067f4` | `addiu $sp, $sp, -0x20` | 固件堆内存释放；C200 单参数 ptr，锁保护后调用内部 free。 |
