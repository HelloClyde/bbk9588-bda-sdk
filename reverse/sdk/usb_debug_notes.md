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
quit       -> exit the resident bridge
```

## Next Steps

If this file-channel bridge works while the app is running, extend it into a
small monitor:

```text
peek ADDR LEN       dump memory as hex into log
poke ADDR VALUE     write one word/byte
call TABLE OFF ...  call SDK table offsets for probes
load PATH           read a small script or binary payload
```

If the filesystem is not visible to the PC while a BDA is running, the next real
USB-debug target is to reverse the firmware USB stack or locate a serial/UART
path. Current public SDK notes only confirm bootloader-level USB disk support,
not an app-level USB/CDC API.
