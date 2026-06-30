# System Binary Reverse Notes

These notes track interesting functions and hidden facilities found in
`System/Data/C200.bin`, `System/Data/C200knl.bin`, `u_boot_9588_4740.bin`, and
the bundled native applications that exercise those system paths. `C200.bin`
is the main raw MIPS image we can directly disassemble at base `0x80000000`.
`C200knl.bin` starts with non-MIPS-looking bytes and is likely packed or
encrypted, so its strings are useful as evidence but its code needs a separate
unpack step.

## Bootloader Hardware Tests

`u_boot_9588_4740.bin` contains a factory/diagnostic menu:

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

This confirms bootloader-level SDRAM, NAND, SD card, USB, keyboard,
touchscreen, recording, buzzer, speaker, voltage, production, and aging tests.

## LCD And Framebuffer Leads

System strings:

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

The LCD path configures low-level LCD controller timing and panel-specific
initialization. The bundled photo album confirms the higher-level RGB565
drawing path:

```text
GUI +0x40c  region draw/copy-like
GUI +0x410  helper used by album render path
GUI +0x418  draw/scale/render helper-like
RES +0x090  picture/resource state output
```

The album scales pictures to the 320x240 screen and uses RGB565-sized buffers
in conversion paths.

## Touch And Key Input

Touch-related strings:

```text
InitTSC2100Touch
test begin!
calibration fail!
calibration ok!
logic position  x = %d, y = %d
\SysTp.cfg
```

The touch chip is likely TSC2100. The lower-level init path writes
memory-mapped registers such as `0xb0010060` and checks status bit
`0x02000000`.

`C200.bin` has a system full-screen diagnostic/window procedure around
`0x8000f718`. It branches on these message-like values:

```text
0x00b0
0x00b1
0x0842
0x0844
```

The same area creates a 240x320 window/control stack descriptor and posts or
sends `0x0842`/`0x0844` back through a GUI helper. These constants are now
exposed in `bda_sdk.h` with conservative `_LIKE` names.

Key test strings:

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

The strings are not referenced by simple direct loads, so some of this test UI
is likely reached through a GUI resource/table or debug registration path. The
next useful hardware probe is still a custom window callback that displays
`message/wparam/lparam`.

## Picture Viewer And JPEG/BMP

The system has extension-based image dispatch:

```text
.bmp
.jpg
```

The bundled photo album contains:

```text
LoaderPicture
LoaderPicture FileName = %s
---Width = %d, Height = %d---
*.bmp
*.jpg
bmp;jpg
```

`LoaderPicture` opens the selected file with `FS +0x000` mode `rb`, rejects
empty files and files larger than `0x400000`, then calls GUI-table image
decoders:

```text
GUI +0x670  BMP decode-like
GUI +0x808  JPEG decode-like
```

`C200.bin` embeds libjpeg 6b strings:

```text
Copyright (C) 1998, Thomas G. Lane
6b  27-Mar-1998
Not a JPEG file: starts with 0x%02x 0x%02x
Bogus JPEG colorspace
JPEG datastream contains no image
```

See `picture_notes.md` for the app-level picture descriptor and render path.

## Audio, WMA, MP3, Record, And TTS

System strings show multiple audio paths:

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

The bootloader also has recording, buzzer, and speaker tests. The Game Boy
emulator's raw streaming path remains the best current SDK sample for direct
PCM output.

## Video Player Runtime

The bundled video apps reference an external player runtime rather than a
single obvious system SDK function:

```text
\player.bin
\player.cfg
MPlayer  (C) 2000-2005 MPlayer Team
Starting playback...
Open stream, file name:%s
```

`reverse/reports/video_bda_report.md` compares both bundled video BDA variants.
Their large private-looking indirect-call clusters should be treated as
player/codec tables until cross-checked against other apps or `C200.bin`.

TTS is present too:

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

No native BDA TTS call ABI has been mapped yet.

## IME And Text Input

System strings show an IME subsystem and default input data:

```text
\shell\ImeLib_A.dlx
\shell\ImeLib_B.dlx
\default_ime.bin
IME_SX_SHUZI
Ime_GetSysType = %d
ListInputBuffer0000000000000=%s
ListInputBuffer99999999999=%s
```

The public custom-app route is still the GUI edit/medit controls through
`GUI+0x1a4`; lower-level IME hooks need a focused reverse pass.

## File Manager Hidden Capabilities

The system file manager has rich operations beyond simple open/read/write:

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

It supports SD insert/pull-out handling, copy/move/delete/rename, search, and
extension-based dispatch to BDA applications.

## SWF/BBK Runtime

There is a built-in Flash-like/SWF runtime:

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

This is separate from native BDA, but it is useful evidence for available
graphics/audio/input primitives inside the firmware.
