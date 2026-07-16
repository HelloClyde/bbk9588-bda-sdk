# 原生 GBA.BDA 工作记录

## 当前构建

```text
build\GBA.BDA       当前测试构建，目前等同 v3 文件选择器版本
build\GBA_v1.BDA    原生 GBA 宿主/核心骨架
build\GBA_v2.BDA    ROM 选择 + 更大的 ARM/THUMB 探测核心
build\GBA_v3_select.BDA  GAMEBOY.BDA 文件选择器 + 追加的 GBA 核心
build\gba_native_v0.bda  ROM 头和 framebuffer 探测
build\gba.cfg.example    ROM 选择配置样例
```

## v1 范围

`reverse\examples\gba_native_v1.c` 还不是可玩的 GBA 模拟器。它是一个
原生 BDA 骨架，用来在移植更大的核心之前验证 BBK 宿主侧能力。

已经实现：

```text
ROM 路径         A:\gba\gba.gba，回退到 a:\gba\gba.gba
ROM 读取上限     早期探测版限制为 2 MiB
EWRAM            堆上分配 256 KiB
IWRAM            堆上分配 32 KiB
VRAM             堆上分配 96 KiB
显示输出         暂未恢复；不能直接用 GUI+0x3f8/+0x400 当 framebuffer/present API
头解析           title、game code、checksum
CPU 状态         r0-r15 + CPSR
ARM 探测循环      从 0x08000000 开始，最多执行 2048 条 ARM 指令
```

`GUI+0x3f8/+0x400` 在雷霆战机/决战坦克里是 game shell surface/context
生命周期中的 region blit 链路，不负责分配 framebuffer。`TileBlit` 真机结果已经
确认：裸 no-template BDA 直接调用这组 wrapper 会逐块 flip 并死机。因此 GBA/GBC
这类模拟器移植在恢复显示前，应先复原 game shell lifecycle，或使用已验证的
frame/control 路径做较低频的调试输出。

ARM 解释器目前只支持很小的子集：

```text
B / BL
BX
MOV immediate
ADD immediate
SUB immediate
CMP immediate
LDR / STR word immediate offset
condition codes
```

message box 会报告：

```text
ROM title
file size / loaded size
header checksum result
PC after probe
executed step count
first unsupported opcode and PC
```

## 预期真机结果

没有 ROM 时：

```text
ROM not found:
A:\gba\gba.gba
```

有 ROM 时：

```text
ROM: <title>
Size/load: <file>/<loaded>
Chk OK/BAD <header byte>/<calculated>
PC=<after probe> steps=<count>
```

多数商业 ROM 会很快停在尚未支持的 ARM opcode 上。这符合 v1 预期；该版本的
目标是验证 ROM 读取、内存分配、初始 ARM 分发，以及不会误触 framebuffer/音频
宿主路径。

## v2 范围

`reverse\examples\gba_native_v2.c` 增加 ROM 选择和更大的 CPU 探测核心。它仍然
不是可玩的模拟器。

ROM 选择使用：

```text
A:\gba\gba.cfg
```

第一行可以是 `A:\gba\` 下的文件名，也可以是完整路径：

```text
demo.gba
A:\gba\demo.gba
```

如果 `gba.cfg` 缺失或为空，会回退到 `A:\gba\gba.gba`，再回退到
`a:\gba\gba.gba`。当前选中的路径会显示在 message box 里。

v2 额外覆盖的 CPU 子集：

```text
ARM/THUMB mode bit and BX switching
THUMB MOV/CMP/ADD/SUB immediate
THUMB add/sub register/immediate
THUMB ALU AND/EOR/LSL/CMP/NEG/ORR/MUL subset
THUMB literal LDR
THUMB LDR/STR byte/halfword/word immediate
THUMB conditional/unconditional branch
ARM data processing immediate and register operand forms
ARM byte/word LDR/STR immediate
ARM LDM/STM increment-after subset
```

## v3 文件选择器版本

`build\GBA_v3_select.BDA` 保留原始 `GAMEBOY.BDA` 前端和文件选择流程，然后把
选中的 ROM 路径重定向到追加的 GBA 核心。

补丁策略：

```text
template          应用\程序\GAMEBOY.BDA
original selector GAMEBOY main at 0x81c0f90c
hooked function   gbmain(path) at 0x81c10158
new core VA       0x81c25338, after original BSS clear range
filter patch      gb;gbc -> gba
title patch       GameBoy -> GBA
config patch      a:\gameboy\gb.cfg -> a:\gba\gba.cfg
```

这是目前最接近内置 Game Boy 行为的版本：文件选择器不是由我们的代码重新实现，
而是复用原始扩展 GUI 选择器。选中的路径会以 `a0` 传给追加的 GBA 核心。

原前端仍然引用：

```text
a:\gameboy\gameboy.dlx
```

如果原始 Game Boy 应用在真机上需要该资源，请保留它。它很可能包含选择器/前端
资源。

## 后续核心任务

```text
1. 增加 THUMB long BL pair、PUSH/POP 和 high-register operations。
2. 增加 ARM multiply、halfword/signed transfer、swap 和更完整的 shifts。
3. 补完 ARM block transfer addressing modes。
4. Stub key IO、DISPCNT、VCOUNT、timers、IRQ flags 和 DMA。
5. 先增加 PPU mode 3，再增加 mode 4/5。
6. 增加 palette/OAM/tile rendering。
7. 增加 sound core 和 save type handling。
8. 真机确认堆行为后再提高 ROM 读取上限。
```
