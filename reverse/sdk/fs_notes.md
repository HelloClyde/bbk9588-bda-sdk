# File-system API notes

These notes summarize the native BDA file-system table as observed from the
bundled applications and the system binaries.

## Strongly mapped calls

`FS +0x000` through `FS +0x014` match a stdio-style API:

```c
file = fopen(path, "rb");
fseek(file, 0, SEEK_SET);
fread(buffer, 1, size, file);
fwrite(buffer, 1, size, file);
pos_or_size = ftell(file);
fclose(file);
```

Hardware-oriented correction: treat file handles `<= 0` as open failure. Some
native calls return `-1`, not just `0`, when a file cannot be opened. Passing
`-1` into subsequent read/seek calls can reboot the device; this was exposed by
the Showcase custom-DLX experiment.

The strongest examples are the bundled block/puzzle games, the photo app, the
ebook app, and the shared game framework. The photo app seeks to end with
whence `2`, calls `FS +0x014`, then closes the handle, which pins `+0x014` as
`ftell` or a file-size helper. See `reverse/reports/ebook_bda_report.md` for a
reader app that uses `fopen/fread/fseek/ftell` style calls, and
`reverse/reports/recorder_bda_report.md` for a WAV recorder/player using file
listing, delete, storage-ready, and generated filenames.

## Directory creation

Several apps do:

```text
FS +0x02c(path)
if return == -1:
    FS +0x030(path)
```

The paths are directories such as the system directory and the system data
directory, so `+0x02c` is currently named `chdir_like` and `+0x030` is named
`mkdir_like`. The exact distinction between "change directory" and "directory
exists" still needs a hardware probe.

## Directory listing

The listing API is a three-call group:

```text
FS +0x03c(path_or_pattern, attr_filter, find_data)
FS +0x040(find_data)
FS +0x044(find_data)
```

The notepad, settings, photo, and recorder apps all use this sequence. System
strings in `C200.bin` and `4720knl.bin` include `fs_findfirst`, which matches
this group.

Observed filter values include:

```text
0x01  used by photo/recorder scans
0x06  used by notepad scans
0x10  used by settings, likely directory attribute
0x27  used by settings for broader filtering
```

The find-data struct layout is not fully named yet. Apps pass a caller-owned
stack/global buffer and then read fields from it between `findnext` calls.

## System File Selector

GAMEBOY.BDA uses a higher-level system file selector through the GUI table:

```text
0x6a8  open-like
+0x6b8  get-result-like
+0x6bc  close-like
+0x6c8  update/run-like
```

The selector descriptor is not just path/title/filter strings. Hardware tests
show that a short/minimal descriptor can open the selector with unreadable
black-on-black folder text, while the fuller GAMEBOY-style descriptor fixes the
colors. So the reserved-looking fields in `bda_file_selector_like_t` include
display/theme/state parameters.

Important correction: this color fix is caused by the selector struct fields,
not by `RES+0x094` or the old `bda_load_dlx_*` wrappers. Later RES094 probes
showed those calls behave like trace/log output and do not visibly load skins.

Hardware probe result:

```text
FSList_cat09.bda:
  FS +0x07c() -> 0x00000001
  FS +0x03c("a:\\*.*", 0x27, find_data) -> 0xffffffff
  find_data remains all zero
```

This means storage-ready is confirmed, but the `findfirst` path/filter shape is
not yet correct. System strings favor root-relative patterns such as `\*.*` and
`\*.bda`, so `FSFindMatrix.bda` and `FSFindChdir.bda` test those next.

`FSFindMatrix.bda` did display, but the first line after `root00=` became
garbled on hardware. The follow-up probes avoid `findclose` and shorten the
message box payload:

```text
FSFindShort.bda  tests a small pattern matrix without findclose
FSFindOne.bda    tests only FS +0x03c("\\*.*", 0x00, find_data)
```

## Disk/storage status

`FS +0x048(0, info)` returns disk information. The settings app multiplies words
at `info+4`, `info+8`, and `info+0xc`, which looks like a FAT
cluster-size/count calculation.

`reverse/reports/settings_bda_report.md` is now the strongest source for this
call: `系统设置.bda` calls it 17 times and repeatedly computes
`word(info+4) * word(info+8) * word(info+0xc)`, comparing the result against
thresholds such as `0x200000` and `0x10000`.

`reverse/reports/ninecourse_bda_report.md` adds another content-app cross-check:
`九门课程.bda` calls `FS+0x048` three times and performs the same
capacity-style multiplication on the returned info fields.

`FS +0x07c()` is a no-argument storage/media-present check. It is used by
settings, media apps, recorder, and learning apps before enabling file-related
flows.

## Stat/access

`FS +0x06c(path, flags, optional_output)` checks path existence or attributes.
It returns `-1` on failure. Examples include dictionary data files and the game
data directory under the system data directory.

This is probably the closest native equivalent of `stat()` or `access()`.

## Unknown or non-file helpers

The FS table also exposes offsets such as `+0x018`, `+0x01c`, `+0x020`,
`+0x028`, `+0x064`, `+0x068`, `+0x078`, and `+0x094`. Some game framework
calls at `+0x068` pass buffer pointers and lengths rather than file handles, so
these may be support functions living in the same table, not ordinary file
operations.

`九门课程.bda` calls `FS+0x064` twice with stack buffers and then tests bytes from
the returned data against app globals. This gives a second non-game source for
the unresolved `+0x064` helper, but it is still not enough to name it.

`reverse/reports/eros_bda_report.md` and
`reverse/reports/linkgame_bda_report.md` show a compact game save-file pattern:
the apps prepare directories, open shared `\SysPet.yzj` data plus app-specific
`.dat` files, and copy/read/write fixed `0x44` byte records. Both games call
`FS+0x068` once in this helper area, but its signature is still unresolved.
