# GAMEBOY.BDA Reverse Notes

These notes are about `应用\程序\GAMEBOY.BDA`, the bundled Game Boy emulator
front end. It is the best current sample for emulator-style native BDA code.

## Layout

```text
file size          0x29a4c
entry offset       0x95f8
runtime base       0x81bf6a28
runtime entry VA   0x81c00020
```

Startup stores the runtime tables in globals:

```text
0x81c20470  RES table
0x81c20474  GUI table
0x81c20478  SYS/device table
0x81c2047c  FS table
0x81c20480  MEM table
```

Use `reverse\bda_table_call_scan.py` with these globals to classify indirect
API calls in this app.

## Core Module

`GAMEBOY.BDA` references:

```text
a:\gameboy\gameboy.dlx
A:\gameboy\
a:\gameboy\gb.cfg
```

The dumped files currently do not include `gameboy.dlx`. Earlier passes treated
that as a possible external core, but the later disassembly shows the main Game
Boy core is embedded in `GAMEBOY.BDA` itself. `gameboy.dlx` is probably the UI
or skin/resource pack used by the front end.

The ROM path is opened through the FS table. Around `0x81c10808`, the code
calls:

```text
FS +0x000  open(path, "rb")
MEM +0x008 allocate 0x25800 bytes
FS +0x010 / +0x014 / +0x008 / +0x004 style calls
```

This is the ROM/config loader path, not an external emulator-code loader.

The string table also shows a fairly complete Game Boy emulator feature set:

```text
gb;gbc
GameStartBox
Action replay code faulty
Gameboy COLOR rom detected.
ROM ONLY
ROM+MBC1
ROM+MBC2
ROM+MBC1+RAM+BATTERY
ROM+MBC5
MBC5+ROM+SRAM+BATTERY
Nintendo logo not found.
Checksum failure
```

So this BDA supports GB/GBC detection, Action Replay-style cheat codes, MBC1,
MBC2, MBC5, SRAM/battery saves, and cartridge checksum validation.

## CPU and Memory Core

The CPU interpreter entry is at `0x81c12270`. It is a classic dispatch-loop
interpreter, not a dynarec:

```text
0x81c25272  current PC
0x81c12270  read opcode at PC through 0x81c0ee74
0x81c122b4  increment PC
0x81c122c4  opcode * 4
0x81c122d0  jump through dispatch table near 0x81c1ef40
0x81c2068c  per-op cycle/flag accumulator-like byte
```

The important memory helpers are:

```text
0x81c0ee74  read byte from GB address space
0x81c0f008  read little-endian 16-bit word by two byte reads
0x81c0f054  write little-endian 16-bit word by two byte writes
0x81c017c8  write byte to GB address space
```

The byte reader maps the normal Game Boy regions:

```text
0000-3fff  fixed ROM bank at pointer 0x81c20850
4000-7fff  switchable ROM bank selected by 0x81c204e8
8000-9fff  VRAM bank based on LCD state
a000-bfff  external RAM bank
c000-cfff  WRAM bank 0
d000-dfff  switchable WRAM bank
ff00-ffff  IO/HRAM/special registers
```

The renderer at `0x81c08bf4` consumes the emulator's LCD/VRAM state and expands
tile pixels into a 16-bit destination buffer. It manipulates palette tables and
screen windows directly; it is not just calling a generic GUI image draw API.

## Save and Config Data

Around `0x81c0f3f0`, the emulator reads/writes small `0x44` byte records. The
integrity rule is simple:

```text
sum bytes 0x00..0x3f
compare with u32 at +0x40
```

If the checksum fails, the file is removed/recreated. This appears to cover
`gb.cfg` or related per-ROM state/config data, separate from the BDA header
checksum.

## Video Leads

The front end allocates a large GUI/screen buffer through the extended GUI table
saved at `0x81c20474`. It stores it at `0x81c2051c` and derives another pointer
at `+0x11200`. It copies or expands data over a `0x140` by `0xf0` style region,
which matches a 320x240 host buffer with scaled or staged Game Boy output.

Extended GUI calls worth probing:

```text
GUI +0x6b0  large screen/frame buffer allocation-like call
GUI +0x738  screen mode/size query-like call; returns 0x131 on one branch
GUI +0x72c  state/query-like call
GUI +0x750  event or key fetch-like call
GUI +0x5d4  draw/update-like call that takes a small stack buffer
```

Names are provisional. They are inferred from call context only. Note that this
app does not use the common `GUI+0x3f8/+0x400` blit group that other games use;
it uses a higher-offset extended GUI/event table instead.

## Audio Leads

Relevant strings:

```text
/dev/dsp
/dev/audio
AudioOpen
Allocating sound pattern memory 4x%d bytes.
Initializing sound pattern memory.
Sound pattern memory OK.
```

Around `0x81c11640`, the BDA initializes audio through the SYS/device table:

```text
SYS +0x090  open/lookup-like call with stack arguments including 0x5622
SYS +0x06c  called as (0x5622, 0x10, 1, 0x64)
SYS +0x09c  called with computed timing/rate value
MEM +0x008  allocates four sound pattern buffers of sample_count * 4 bytes
```

The streaming path uses a 0x400-byte sample buffer at `0x81c24db0`:

```text
SYS +0x074  wait/ready-like call
SYS +0x078  write-like call: (buffer at 0x81c24db0, 0x400)
SYS +0x004  close/release-like call
SYS +0x08c  reset/init-like call
SYS +0x0a0  flush/drain-like call
```

Samples are queued as 16-bit halfwords. The simple output helper at
`0x81c121b8` stores `(sample << 5)` until it reaches `0x200` samples, waits on
`SYS+0x074`, writes `0x400` bytes through `SYS+0x078`, then resets the count.
Another path pads silence with `0x1000` or `0x0000` before flushing. The SDK
exposes these as raw `*_like` helpers until hardware probes confirm their exact
contracts.

## Input Leads

This BDA has a dense input/status routine beginning near `0x81c10d30`. It uses
GUI calls around `+0x72c`, `+0x750`, and `+0x5d4`, then updates globals such as
`0x81c205f4`, `0x81c205f8`, and `0x81c205fc`.

The audio synthesis path also reads button-state-like fields from a structure
at global `0x81c204d0`, with offsets including `0x12`, `0x1a`, `0x24`, `0x25`,
and `0x26`.

This is useful but not yet a clean SDK input API. Keep using `input_notes.md`
and hardware probe BDAs to pin the real touch/key messages.

## GBA Implication

A native GBA emulator BDA is plausible only as an emulator project, not as a
tiny SDK demo. The viable shape is likely:

```text
BDA front end:
  header/icon/menu identity
  file picker / ROM loading
  framebuffer allocation and blit
  key/touch input mapping
  audio device buffering

core module:
  ARM7TDMI interpreter or dynarec
  PPU/APU/timer/DMA/cartridge logic
  save RAM/state handling
```

`GAMEBOY.BDA` suggests the platform already supports the needed classes of
host services: framebuffer, input polling/events, raw PCM output, heap, and
file IO. The missing piece is still exact framebuffer/input signatures and a
portable emulator core small and fast enough for the Ingenic CPU.
