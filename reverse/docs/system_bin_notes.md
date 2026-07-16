# 系统固件逆向笔记

本文记录 `系统/数据/C200.bin`、`系统/数据/C200knl.bin`、
`u_boot_9588_4740.bin` 以及原机原生 BDA 应用里能交叉验证的系统功能。
`C200.bin` 是当前最重要的原始 MIPS image，toolchain 按 load base `0x80004000`
disasm 并导出 API table。`C200knl.bin` 开头不像普通 MIPS 指令，可能经过压缩
或加密；它的字符串可作为功能线索，但代码需要另行解包后才能分析。

## Bootloader 硬件测试

`u_boot_9588_4740.bin` 内含工厂/诊断菜单：

```text
1. DISPLAYEFFECT TEST
2. BRIGHTNESS TEST
3. KEYBOARD TEST
4. TOUCHSCREEN TEST
5. SDRAM TEST
6. NANDFLASH TEST
7. SDCARD TEST
8. RECORDING TEST
9. BUZZER TEST
10.SPEAKER TEST
11.VOLTAGE TEST
12.USBCONNECT TEST
13.WAIT TEST
14.PRODUCTION TEST
15.AGING TEST
SDRAMTEST SUCCESS!
SDCARD TEST OK!
Ingenic JzSOC USB-DISK  0100p
9588 V2.60
```

这说明 bootloader 层已经具备 SDRAM、NAND、SD 卡、USB、键盘、触屏、录音、
蜂鸣器、扬声器、电压、产测和老化测试路径。对 SDK 来说，这些字符串证明
硬件能力存在，但并不等于已经有稳定的 BDA runtime ABI。

## LCD 和 Framebuffer 线索

系统字符串：

```text
lcdtest1
lcdtest2
lcdtest3
LCDC: PixClock:%d LcdClock:%d
LCD DOES NOT supported.
InitLingDaLCD_5408B start/end
InitXinLi9325LCD
testcolor
testcolor finished
Varam Buffer Test: %d
```

LCD 路径会配置底层 LCD 控制器时序和具体面板初始化。更接近 BDA 开发者的
high-level evidence 来自 `我的相册.bda`，它确认了 RGB565 image/region draw 路径：

```text
GUI +0x40c  region draw/copy helper；context,x,y,width,height
GUI +0x410  render/copy helper；context,x,y,width,height,descriptor
GUI +0x418  双 context/双矩形 render helper；使用 stack+0x14 的第二 context
RES +0x090  picture/resource state output
```

相册会把 image scaling 到 320x240 屏幕，并在转换路径里使用 RGB565 大小的 buffer。

## 触摸和按键输入

触摸相关字符串：

```text
InitTSC2100Touch
test begin!
calibration fail!
calibration ok!
logic position  x = %d, y = %d
\SysTp.cfg
```

触摸芯片很可能是 TSC2100。底层初始化路径会写 `0xb0010060` 等 MMIO 寄存器，
并检查 `0x02000000` 状态位。

`C200.bin` 在 `0x8000f718` 附近有系统全屏诊断/window proc，会分支处理这些
Message-like 常量：

```text
0x00b0
0x00b1
0x0842
0x0844
```

同一区域还会创建 240x320 的 window/control stack descriptor，并通过 GUI helper 投递或发送
`0x0842`、`0x0844`。这些常量已经在 `bda_sdk.h` 中以保守 `_LIKE` 名称暴露。

按键测试字符串：

```text
Key test window
Hello Press Key!
MSG_KEYDOWN
The key is ENTER
The key is BACK
The key is SHIFT
The key is HOME
The key is UP
The key is LEFT
The key is RIGHT
The key is END
The key is DOWN
The key is INS
The key is DEL
IntGPIO2_KeyHandler:%d
KEY_GPIO_POWER_KEY=%8.8X
```

这些字符串没有被简单的直接 load 交叉引用到，因此部分测试 UI 可能通过 GUI
resource table 或 debug register 路径进入。下一步最有价值的 hardware probe 仍是 custom window callback，
把 `message/wparam/lparam` 显示出来。

## 图片查看和 JPEG/BMP

系统有按扩展名分发图片的路径：

```text
.bmp
.jpg
```

原机相册包含：

```text
LoaderPicture
LoaderPicture FileName = %s
---Width = %d, Height = %d---
*.bmp
*.jpg
bmp;jpg
```

`LoaderPicture` 会通过 `FS+0x000` 以 `rb` 模式打开选中的文件，拒绝空文件和
大于 `0x400000` 的文件，然后调用 GUI table 里的 image decode wrapper：

```text
GUI +0x670  BMP decode-like
GUI +0x808  JPEG decode-like
```

`C200.bin` 内嵌 libjpeg 6b 字符串：

```text
Copyright (C) 1998, Thomas G. Lane
6b  27-Mar-1998
Not a JPEG file: starts with 0x%02x 0x%02x
Bogus JPEG colorspace
JPEG datastream contains no image
```

应用层图片描述符和渲染流程见 `picture_notes.md`。

## 音频、WMA、MP3、录音和 TTS

系统字符串显示多条音频路径：

```text
10CMp3Decomp
Mp3DecodeFinish
mp3 user break
WMA - Open!
WMA - Start decode!
jz_i2s_replay_dma_irq
jz_i2s_record_dma_irq
\alarm.mp3
\Record.yzj
```

bootloader 也有录音、蜂鸣器和扬声器测试。当前最接近 SDK 可复用的直接 PCM
输出样本仍是 `GAMEBOY.BDA` 的流式音频路径。

## Video Player Runtime

原机视频应用更像是在使用外部 player runtime，而不是一个小型系统 API：

```text
\player.bin
\player.cfg
MPlayer  (C) 2000-2005 MPlayer Team
Starting playback...
Open stream, file name:%s
```

`reverse/reports/video_bda_report.md` 对比了两个原机视频 BDA。它们内部的大块
私有间接调用表应先当作播放器/编解码器表处理，不能在和其他应用或 `C200.bin`
交叉验证前升格为 public SDK API。

TTS 也存在：

```text
\TTScfg.cfg
\shell\TTSSET.dlx
TTSState
TTSTextMark
TTSUsePrompt
TTSRecPinyin
TTSReadPunc
TTSReadName
TTSReadDigit
TTSOutputVoice
TTSPhoneme
TTS Voice Change
```

目前还没有映射出可公开使用的原生 BDA TTS 调用 ABI。

## 输入法和文本输入

系统字符串显示输入法子系统和默认输入数据：

```text
\shell\ImeLib_A.dlx
\shell\ImeLib_B.dlx
\default_ime.bin
IME_SX_SHUZI
Ime_GetSysType = %d
ListInputBuffer0000000000000=%s
ListInputBuffer99999999999=%s
```

当前面向 custom app 的路线是先复刻真实 frame/control 生命周期，再在已有 parent/window
上下文中通过 `GUI+0x1a4` 创建 `edit`/`medit` control。`GUI+0x1a4` 的 ABI 已确认，
但裸 `bda_main()` 中用 `parent=0` 直接创建 edit/listbox 的 probe 已有重启记录；
它不是通用 GUI bootstrap。更底层的 IME hook 需要单独逆向。

## 文件管理器隐藏能力

系统文件管理器不只支持简单 open/read/write，还有较完整的操作：

```text
fs_rename
RenameApp
explorer_PasteSelFile
explorer_Paste
explorer_SetCopyData
explorer_FileCopy
explorer_searchdirfile_Quick
fs_findfirst
DeleteError_Message
\*.bda
.bda
```

它支持 SD 插拔、复制、移动、删除、重命名、搜索，以及按扩展名分发到 BDA
应用。当前 SDK 已暴露 `findfirst/findnext/findclose` 和基础文件读写，复制/
重命名等管理器级 ABI 还没有稳定命名。

## SWF/BBK Runtime

firmware 里还有内置的 Flash-like/SWF runtime：

```text
?bbk_swf_file
not bbk file
failed to recognize bbk file
File uncompress failed
attachBitmap
beginBitmapFill
createEmptyMoiveClip
createTextField
getSWFVersion
getTime
getTimezoneOffset
addListener
removeListener
hitTest
isDown
onKeyDown
onKeyUp
attachAudio
getBytesTotal
```

这和原生 BDA 不是同一套 runtime，但能证明 firmware 内部具备 graphics/audio/input 等 primitive。
