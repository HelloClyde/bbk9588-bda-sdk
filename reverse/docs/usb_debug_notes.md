# USB 调试桥笔记

`UsbDebugBridge.bda` 是第一版调试桥。它把设备的 USB 大容量存储文件系统当作
命令/日志通道使用。

它不是原生 USB CDC 串口设备，也不是 GDB stub。它的目标是缩短硬件测试循环：

```text
在设备上运行一个常驻 BDA
PC 侧 tail 日志文件
通过写入命令文件发送小命令
```

## 文件

```text
reverse/examples/usb_debug_bridge.c
scripts/usb_debug_host.py
build/UsbDebugBridge.bda
```

设备侧路径：

```text
A:\应用\数据\debug\usbdebug.log
A:\应用\数据\debug\cmd.txt
```

如果设备在 PC 上挂载为 `F:`，主机侧路径为：

```text
F:\应用\数据\debug\usbdebug.log
F:\应用\数据\debug\cmd.txt
```

## 常用命令

```powershell
python scripts\usb_debug_host.py --drive F: --tail
python scripts\usb_debug_host.py --drive F: -c ping
python scripts\usb_debug_host.py --drive F: -c status
python scripts\usb_debug_host.py --drive F: -c "msg hello"
python scripts\usb_debug_host.py --drive F: --batch build\usbdebug_batch.txt
python scripts\usb_debug_host.py --drive F: --scan-table fs --start 0 --end 0x90 --argc 0
python scripts\usb_debug_host.py --drive F: -c quit
```

BDA 读取后会删除 `cmd.txt`，因此每条命令都应作为新文件发送。

## 当前协议

`UsbDebugBridge.bda` 会写日志：

```text
[BDA] boot UsbDebugBridge start
[BDA] gui <ptr>
[BDA] fs <ptr>
[BDA] sys <ptr>
[BDA] mem <ptr>
[BDA] res <ptr>
[BDA] ready <value>
[BDA] tick <counter>
```

支持命令：

```text
ping       -> log pong
status     -> 记录 runtime table pointer 和 storage-ready 值
msg TEXT   -> 在设备上显示 message box
peek ADDR COUNT
           -> 从内存读取最多 16 个 word
call TABLE OFFSET ARGC [A0 [A1 [A2 [A3]]]]
           -> 以 0..4 个原始 u32 参数调用 SDK table entry
quit       -> 退出常驻 bridge
```

`call` 支持的表名：

```text
gui fs sys mem res
```

示例：

```powershell
python scripts\usb_debug_host.py --drive F: -c "call fs 7c 0"
python scripts\usb_debug_host.py --drive F: -c "call gui 2b8 4 0 0 0 0"
python scripts\usb_debug_host.py --drive F: -c "peek 81c00000 8"
```

这里没有原生 try/catch。如果调用跳到坏 table entry、传入坏 pointer，或违反 GUI 生命周期，
设备可能卡死或重启。bridge 会在执行危险调用前删除 `cmd.txt`，并先记录
`begin`，调用返回后再记录 `done`。如果日志里只有 `begin` 没有 `done`，该命令
很可能让设备崩溃。

## Batch 和扫描模式

主机 helper 可以循环执行命令：

```powershell
python scripts\usb_debug_host.py --drive F: --batch build\usbdebug_batch.txt --timeout 5
```

batch 文件格式：

```text
# 注释和空行会被忽略
ping
status
peek 81c00000 8
call fs 7c 0
call gui 738 0
manual call gui 2b8 4 0 0 0 0
wait check the device screen, then press Enter here
sleep 2
```

主机默认会等待 `done`、`ret`、`pong` 或 `error` 后再发送下一条命令。超时后默认
停止，因为 `begin` 后超时通常表示设备崩溃或 bridge 停止轮询。只有确认目标命令
不会阻塞时，才使用：

```powershell
python scripts\usb_debug_host.py --drive F: --batch build\usbdebug_batch.txt --continue-on-timeout
```

部分 GUI 命令需要人工观察，或会弹出模态 UI。给这些行加 `manual` 前缀：

```text
manual call gui 2b8 4 0 0 0 0
```

主机会发送命令，等待通常结果或超时，然后暂停询问是否继续。纯人工检查点使用
`wait`：

```text
wait verify whether the screen changed
```

固定延迟使用 `sleep`：

```text
sleep 3
```

这样能让自动扫描保持较快速度，同时仍允许对显示、模态对话框、文件选择器、音频、
输入等测试做人工确认。

offset 扫描模式会生成原始 `call` 命令：

```powershell
python scripts\usb_debug_host.py --drive F: --scan-table gui --start 0 --end 0x900 --argc 0
python scripts\usb_debug_host.py --drive F: --scan-table fs  --start 0 --end 0x90  --argc 0
python scripts\usb_debug_host.py --drive F: --scan-table sys --start 0 --end 0xc0  --argc 0
```

也可以提供参数模板：

```powershell
python scripts\usb_debug_host.py --drive F: --scan-table gui --start 0 --end 0x900 --argc 1 --arg 0
python scripts\usb_debug_host.py --drive F: --scan-table gui --start 0x2b8 --end 0x2b8 --argc 4 --arg 0 --arg 0 --arg 0 --arg 0
```

扫描不会一次性证明语义。很多 GUI function 需要有效 handle、string pointer、draw context
或活动 frame 状态。batch 模式的价值在于快速把 offset 粗分为：

```text
立即返回
返回有趣的值
调用前就记录 error
begin 后卡死/重启
```

对 GUI API，优先扫描已知候选 offset 和保守参数模板，然后再写有状态脚本创建
frame/draw handle，并复用这些 pointer。

## 后续方向

如果这个文件通道 bridge 在 BDA runtime 可用，可以扩展成小型 monitor：

```text
poke ADDR VALUE     写一个 word/byte
load PATH           读取小脚本或二进制 payload
```

如果 BDA runtime PC 看不到 filesystem，真正的 USB 调试目标就要转向逆向 firmware USB stack，
或寻找串口/UART 路径。当前公开 SDK 笔记只确认 bootloader 层有 USB 磁盘支持，
还没有确认应用层 USB/CDC API。
