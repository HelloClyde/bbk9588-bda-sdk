# 堆、文件定位与目录 API

验证环境：

- `bbk9588-emulator-v0.1.5`，8013 端口，完整 NAND 冷启动，固件
  `kj409588/C200`。
- BBK 9588 C200 真机，`MaxHeapProbeV1` 单块分配上限与失败恢复测试。

验证等级：`bda_alloc()`/`bda_free()` 已完成 C200 真机闭环；seek、目录和枚举仍为
模拟器稳定公开。本文不把其中一组的证据扩张到其他 API、机型或固件。

独立准入探针：

- `reverse/examples/gam4980_runtime_api_probe.c`
- `reverse/examples/max_heap_hardware_probe.c`

公开示例：`example/system/runtime_services/runtime_services_demo.c`。

## 公开 API

| 公开函数或常量 | 固件入口 | 已验证语义 |
|---|---:|---|
| `bda_alloc()` | MEM `+0x008` | 按 byte 数分配，成功返回可读写指针；本次真机耗尽返回 `NULL` |
| `bda_free()` | MEM `+0x00c` | 释放一次成功分配的指针；真机重复复用同一大块地址 |
| `bda_fs_seek_raw()` | FS `+0x010` | 成功返回更新后的绝对位置，失败返回 `-1` |
| `BDA_SEEK_SET` | `0` | 从文件开头定位 |
| `BDA_SEEK_CUR` | `1` | 从当前位置定位，支持负偏移 |
| `BDA_SEEK_END` | `2` | 从文件末尾定位 |
| `bda_fs_chdir()` | FS `+0x02c` | 切换当前目录；本次成功返回 `0` |
| `bda_fs_mkdir()` | FS `+0x030` | 创建目录；干净 NAND 上成功返回 `0` |
| `bda_fs_findfirst()` | FS `+0x03c` | 打开枚举并写回第一项 |
| `bda_fs_findnext()` | FS `+0x040` | 写回下一项；结束返回 `-1` |
| `bda_fs_findclose()` | FS `+0x044` | 释放枚举 cursor；本次成功返回 `0` |
| `bda_fs_find_data_init()` | 纯 SDK helper | 把 0x220-byte 枚举结构清零 |
| `bda_memcpy()` | 纯 SDK helper | freestanding byte copy，不调用固件 |

公开名称不带 `_like`。`calloc`、`realloc`、删除目录、重命名等入口没有随本次验证
一并公开。

## 堆所有权

`bda_alloc()` 的参数是 byte 数。每个成功返回的指针必须与一次 `bda_free()` 配对；
不要释放静态区、栈指针、固件 object handle 或 compatible draw context。

模拟器准入探针同时保留了 gam4980 实际需要的六块内存：

```text
0x8000
0x200000
0x200000
0x200000
161 * 96 * 2
24 + 240 * 320 * 2
```

探针对每个 4 KiB 边界、中点和末 byte 写入不同标记，并检查所有地址区间不重叠。
按逆序释放后，又成功分配和读写了一个 4096-byte block。

六块的精确合计为 `6508760` byte，即约 `6.21 MiB` 或 `6.51 MB`。旧文档曾把
十进制 MB 数值误标为二进制 MiB，现已修正。

### C200 真机单块结果

`MaxHeapProbeV1` 在每次测试期间先保留并验证 `262144` byte（256 KiB）恢复区，再对
一个候选连续块每隔 4096 byte 写入并读回标记。候选块每轮都在验证后释放，粗测步长
为 1 MiB，失败区间内的精测步长为 64 KiB。

真机结果：

| 项目 | 结果 |
|---|---:|
| 保留恢复区时最大成功单块 | `11337728` byte = `11072 KiB` = `10.8125 MiB` |
| 第一个失败候选 | `11403264` byte = `10.875 MiB` |
| 测量粒度 | `65536` byte = `64 KiB` |
| 成功峰值时同时持有 | `11337728 + 262144 = 11599872` byte = `11.0625 MiB` |
| 耗尽返回值 | `NULL` |
| 释放恢复区后的 4 KiB 复测 | `PASS` |

因此当前可以承诺的是：在该 C200 真机启动状态下，应用即使保留 256 KiB 恢复空间，
仍可取得并完整触碰一个 10.8125 MiB 连续块。真实阈值位于
`11337728..11403263` byte 之间，但没有按 byte 继续逼近。

所有成功候选均返回 `0x8112B3E8`，说明每轮 `bda_free()` 后该大块能够重新合并和复用。
这次同时验证了一个分配失败后的清理和恢复路径，但不把该地址、容量或失败阈值定义为
固件 ABI 常量。其他 BDA、后台服务、固件版本和堆碎片状态都会改变可用容量。

```c
u8 *buffer = (u8 *)bda_alloc(4096u);
if (!buffer || (u32)buffer == 0xffffffffu) {
    /* allocation failed */
}

buffer[0] = 0x5a;
bda_free(buffer);
buffer = 0;
```

本次仍没有验证 `bda_free(NULL)`、重复释放、连续多次耗尽后的恢复，以及不保留恢复区
时的绝对单块上限。应用应只把成功分配且尚未释放的指针传给 `bda_free()`；申请失败
必须同时识别 `NULL` 和 SDK 保守示例中的 `0xffffffff` 哨兵。

## Seek

成功 seek 的返回值就是新位置，不是固定的 `0`：

```c
int size = bda_fs_seek_raw(file, 0, BDA_SEEK_END);
if (size < 0 || bda_fs_tell_raw(file) != size) {
    /* seek failed */
}

if (bda_fs_seek_raw(file, 4, BDA_SEEK_SET) != 4) {
    /* position mismatch */
}
```

动态结果为：`END -> 16`、`SET 4 -> 4`、从位置 8 执行 `CUR -2 -> 6`。随后分别读回
`4567` 和 `67`。非法 `whence=99` 返回 `-1`。

## 目录与枚举

路径使用与 `bda_fs_fopen_raw()` 相同的 ASCII/GBK byte string。相对路径依赖当前目录，
因此应用退出或启动其他模块前应切回明确目录。

```c
bda_fs_find_data_t find_data;
int result;
int opened;

if (bda_fs_chdir(data_directory) == -1) {
    /* directory unavailable */
}

bda_fs_find_data_init(&find_data);
result = bda_fs_findfirst("*.gam", 0x27u, &find_data);
opened = result != -1;
while (result != -1) {
    find_data.name_or_path[sizeof(find_data.name_or_path) - 1u] = 0;
    /* consume find_data.name_or_path */
    result = bda_fs_findnext(&find_data);
}
if (opened)
    (void)bda_fs_findclose(&find_data);
```

只对成功打开的枚举调用一次 `bda_fs_findclose()`。`bda_fs_find_data_t` 必须保持完整的
0x220 byte，不能用较短的
自定义 buffer 替代。

## 模拟器动态证据

测试使用基础 NAND 新建并补 ECC 的 worker copy：

```text
E:\bbk9588-emulator-v0.1.5\runtime\bda_test\bbk9588_nand_gam4980_api_verify_ecc.bin
```

原始 `bbk9588_nand.bin` 未修改，legacy Python storage/resource hooks 均关闭。探针在
`A:\应用\数据\游戏\G498API` 创建两个相对路径文件，结果导出到 `G498API.TXT`。

探针 BDA SHA-256：

```text
7efd51d825633858456455ec8c1a058fcd34d2a90327a92633208e0071eff0ef
```

模拟器原始导出日志（CRLF 字节）SHA-256：

```text
6ac2fc57342a89fe0ae4682dc7fd58a4021502053829a7e29c60e46d7184e796
```

完整日志保存在 [runtime_services_probe_log.txt](assets/runtime_services_probe_log.txt)；
Git 按仓库规则将该文本规范化为 LF，因此检出文件的字节哈希不同。屏幕同时显示 PASS：

![运行时服务探针 PASS](assets/runtime_services_probe_pass.png)

安全关机后 NAND 校验仍通过，目录中恰有 `ONE.TST` 16 byte 和 `TWO.TST` 11 byte。

## 真机动态证据

真机探针 BDA：

```text
build/MaxHeapProbeV1.bda
SHA-256 8c2e2e3f160ba6c0a5c37db4a1dcadf5e3dde977c1e8df3da6dc416422a8deb0
```

探针把每一步立即追加并关闭到：

```text
A:\应用\数据\游戏\MAXHEAP.TXT
```

完整真机日志保存在
[max_heap_v1_hardware_log.txt](assets/max_heap_v1_hardware_log.txt)。日志结尾为
`RECOVERY PAGE=PASS`、`CAP REACHED=0` 和 `RESULT=PASS`，应用随后正常结束。
仓库中 LF 规范化日志的 SHA-256 为：

```text
84863eb890bfda7601ed578864a971d9b97c985afc52dd43688126d83c80be1f
```

## 已知边界

- 堆分配/释放已在一台 C200 真机闭环；seek、目录和枚举仍只验证
  `kj409588/C200` 模拟器完整固件路径。
- 10.8125 MiB 是保留 256 KiB 时、64 KiB 粒度下的安全单块，不是所有运行状态的固定
  堆上限，也不是未保留恢复区时的绝对最大值。
- `findfirst` 的 `attr=0x27` 只验证普通测试文件枚举，没有完整命名每个属性 bit。
- 没有验证跨 volume、长 GBK 文件名截断、并发枚举或目录被同时修改。
- 没有验证 seek 到负位置、超过文件末尾后的写入或大于 2 GiB 的位置。
- 模拟器累计测试精确覆盖 `6508760` byte；真机峰值同时持有 `11599872` byte。两者的
  分配形状不同，不能互相替代，也不代表任意内存压力都可恢复。
