# Time and alarm API notes

These calls are inferred from the bundled Time, Alarm, Settings, and GAMEBOY
BDAs. Names are provisional until hardware probes confirm the exact struct
layout.

See also:

- `reverse/reports/time_bda_report.md`
- `reverse/reports/alarm_bda_report.md`

The alarm report is the strongest current source for the RTC/alarm call sites.
The Time app mostly proves the display/update loop and delay behavior.

## Secondary/SYS table calls

```text
SYS +0x080  delay/sleep-like
  observed in Time and Alarm
  common argument: a0 = 0xc350 (50000 decimal)
  used repeatedly between display refreshes, so it is very likely a delay
  helper rather than a wall-clock reader

  The Time app uses this offset 42 times, while no scanner-classified direct
  SYS+0x0b8 call appears in that app. The actual clock-read path may use a call
  shape not caught by the current scanner, or may be more obvious in Alarm.

SYS +0x0b8  time/RTC get-like
  observed in Alarm
  a0 = caller-provided buffer, examples use stack buffers at sp+0x20/sp+0x38
  caller later reads bytes at buffer+0x11 and buffer+0x12 and word at buffer+0
  strongest current evidence: reverse/reports/alarm_bda_report.md

SYS +0x0b0  alarm get-like
  observed in Alarm
  a0 = caller-provided buffer
  a1 = alarm slot/index, observed 0, 1, and 2

SYS +0x0ac  alarm set-like
  observed in Alarm
  a0 = caller-provided buffer
  a1 = alarm slot/index, observed 0, 1, and 2
  do not use from probes until the struct layout is known

SYS +0x0a8  alarm/time commit or refresh-like
  observed after SYS+0x0b8 in Alarm
  a0 = 0 in observed call sites

SYS +0x09c  timer/tick/rate-like
  observed in Settings and GAMEBOY
  this appears to be a timing helper, not the current date/time API
```

## Current probe

`reverse/examples/time_probe.c` reads `SYS+0x0b8` and the three alarm slots with
`SYS+0x0b0`, then displays the return values and raw bytes. It intentionally
does not call `SYS+0x0ac` or `SYS+0x0a8`, so it should not change clock or alarm
settings.
