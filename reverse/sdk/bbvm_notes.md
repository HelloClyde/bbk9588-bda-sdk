# BB virtual machine API notes

These notes come from `应用/程序/BB虚拟机.bda`. The BB VM is still a native BDA
program, so its wrappers are useful hints for the native SDK even though the
final target is not BB bytecode.

## Runtime table registration

At startup the VM saves the native tables into globals:

```text
0x81c43c60  RES / Dict table
0x81c43c64  GUI table
0x81c43c68  SYS / Media table
0x81c43c6c  FS table
0x81c43c70  MEM / CRTL table
```

It then calls `RES+0x094` with debug strings such as:

```text
GeneralDLTable Address :%x
GeneralDLTable GUI_Address :%x
GeneralDLTable FS_Address :%x
GeneralDLTable Media_Address :%x
GeneralDLTable CRTL_Address :%x
GeneralDLTable Dict_Address :%x
```

This confirms that `0x81c0000c` is treated by at least one bundled runtime as a
media/system table, not only a miscellaneous table.

## Timing clues

Readable strings include:

```text
msdly_S:%d,%d\n
msdly_E:%d,%d\n
0100831:修改“gettick读出来不是ms”
```

So BB-level programs have `gettick`/millisecond-delay semantics, but the author
notes that `gettick` was not returning milliseconds before a fix. Native code
still needs a probe to map the exact unit. This reinforces the current native
leads:

```text
SYS+0x080  delay/sleep-like
SYS+0x09c  timer/tick/rate-like
```

## GUI/event/display clues

The VM does not call `SYS` directly in the scanned call sites. It uses many GUI
calls, including these GBA-relevant offsets:

```text
GUI+0x030  event/status poll-like; repeatedly called in VM loops
GUI+0x050  event/update helper-like
GUI+0x054  event/update helper-like, often called after GUI+0x050
GUI+0x074  frequent drawing/window flush/update-like
GUI+0x1ac  lock/begin update-like; seen with a small integer mode
GUI+0x1b0  unlock/end update-like
GUI+0x334  set background/fill color-like
GUI+0x374  RGB/color query or pixel/color conversion-like
GUI+0x3f8  framebuffer/region blit-like
GUI+0x400  alternate framebuffer/region blit-like
GUI+0x4d0  text width/height metric-like
GUI+0x4d4  text width/height metric-like
```

The `GUI+0x1ac/+0x1b0` pair is especially interesting for emulator work: it may
be the missing begin/end frame or lock/unlock sequence around fast drawing.

## File-system clues

BBVM uses the known stdio-like FS group plus extra offsets:

```text
FS+0x018  used as a small wrapper, exact role unknown
FS+0x01c  used as a small wrapper, exact role unknown
FS+0x020  used as a small wrapper, exact role unknown
FS+0x028  extra file/path operation, exact role unknown
FS+0x068  block/file helper-like; observed with pointer + offset/size args
```

The known `open/read/write/seek/tell/close/find` group is still enough for GBA
ROM and save files, but these extra offsets should be probed later.

## GBA impact

BBVM adds confidence that a usable native emulator needs these probes next:

```text
BlitLockProbe  GUI+0x1ac/+0x1b0 with GUI+0x3f8/+0x400
InputPollProbe GUI+0x030/+0x050/+0x054 event/status behavior
TickProbe      SYS+0x080/+0x09c units, compared with visible delay
```

It does not add new direct audio evidence; audio should still be mapped from
`GAMEBOY.BDA`, `飞天影音.bda`, or `飞天音乐.bda`.
