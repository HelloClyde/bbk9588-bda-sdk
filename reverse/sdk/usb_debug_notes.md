# USB Debug Bridge Notes

`UsbDebugBridge.bda` is a first-pass debug bridge that uses the device's USB
mass-storage filesystem as a command/log channel.

This is not a native USB CDC serial device and not a GDB stub yet. It is meant
to shorten the hardware test loop:

```text
run one resident BDA on the device
tail a log file from the PC
send small commands by writing a command file
```

## Files

```text
reverse/examples/usb_debug_bridge.c
tools/usb_debug_host.py
build/UsbDebugBridge.bda
```

Device-side paths:

```text
A:\应用\数据\debug\usbdebug.log
A:\应用\数据\debug\cmd.txt
```

Host-side mounted paths, if the device appears as `F:`:

```text
F:\应用\数据\debug\usbdebug.log
F:\应用\数据\debug\cmd.txt
```

## Commands

```powershell
python tools\usb_debug_host.py --drive F: --tail
python tools\usb_debug_host.py --drive F: -c ping
python tools\usb_debug_host.py --drive F: -c status
python tools\usb_debug_host.py --drive F: -c "msg hello"
python tools\usb_debug_host.py --drive F: --batch build\usbdebug_batch.txt
python tools\usb_debug_host.py --drive F: --scan-table fs --start 0 --end 0x90 --argc 0
python tools\usb_debug_host.py --drive F: -c quit
```

The BDA removes `cmd.txt` after reading it, so each command should be sent as a
fresh file.

## Current Protocol

`UsbDebugBridge.bda` logs:

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

Supported commands:

```text
ping       -> log pong
status     -> log runtime table pointers and storage-ready value
msg TEXT   -> show a message box on the device
peek ADDR COUNT
           -> read up to 16 words from memory
call TABLE OFFSET ARGC [A0 [A1 [A2 [A3]]]]
           -> call an SDK table entry with 0..4 raw u32 arguments
quit       -> exit the resident bridge
```

Tables for `call`:

```text
gui fs sys mem res
```

Examples:

```powershell
python tools\usb_debug_host.py --drive F: -c "call fs 7c 0"
python tools\usb_debug_host.py --drive F: -c "call gui 2b8 4 0 0 0 0"
python tools\usb_debug_host.py --drive F: -c "peek 81c00000 8"
```

There is no native try/catch. If a call jumps to a bad table entry, passes a bad
pointer, or violates GUI lifetime rules, the device can hang or reboot. The
bridge deletes `cmd.txt` before executing a command and logs `begin` before the
dangerous call and `done` afterwards. If the log contains `begin` without
`done`, that command likely crashed the device.

## Batch And Scan Mode

The host helper can loop commands:

```powershell
python tools\usb_debug_host.py --drive F: --batch build\usbdebug_batch.txt --timeout 5
```

Batch file format:

```text
# comments and blank lines are ignored
ping
status
peek 81c00000 8
call fs 7c 0
call gui 738 0
```

It waits for `done`, `ret`, `pong`, or `error` before sending the next command.
On timeout it stops by default, because a timeout after `begin` usually means
the device crashed or the bridge stopped polling. Use this only when you know
the target command is nonblocking:

```powershell
python tools\usb_debug_host.py --drive F: --batch build\usbdebug_batch.txt --continue-on-timeout
```

Offset scan mode generates raw `call` commands:

```powershell
python tools\usb_debug_host.py --drive F: --scan-table gui --start 0 --end 0x900 --argc 0
python tools\usb_debug_host.py --drive F: --scan-table fs  --start 0 --end 0x90  --argc 0
python tools\usb_debug_host.py --drive F: --scan-table sys --start 0 --end 0xc0  --argc 0
```

Argument templates can be supplied:

```powershell
python tools\usb_debug_host.py --drive F: --scan-table gui --start 0 --end 0x900 --argc 1 --arg 0
python tools\usb_debug_host.py --drive F: --scan-table gui --start 0x2b8 --end 0x2b8 --argc 4 --arg 0 --arg 0 --arg 0 --arg 0
```

This will not magically prove semantics in one pass. Many GUI functions require
valid handles, string pointers, draw contexts, or active frame state. Batch mode
is still useful because it quickly classifies offsets into:

```text
returns immediately
returns an interesting value
logs error before call
hangs/crashes after begin
```

For GUI APIs, prefer scanning known candidate offsets with conservative argument
templates, then move to stateful scripts that create a frame/draw handle and
reuse those pointers.

## Next Steps

If this file-channel bridge works while the app is running, extend it into a
small monitor:

```text
poke ADDR VALUE     write one word/byte
load PATH           read a small script or binary payload
```

If the filesystem is not visible to the PC while a BDA is running, the next real
USB-debug target is to reverse the firmware USB stack or locate a serial/UART
path. Current public SDK notes only confirm bootloader-level USB disk support,
not an app-level USB/CDC API.
