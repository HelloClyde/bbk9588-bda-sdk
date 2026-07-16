# 内存 API 笔记

本文记录原生 BDA MEM table 的当前结论。function-level C200 disasm 补充见
`c200_api_function_notes.md`。

## Firmware Heap Allocator

SDK 暴露三个基础 wrapper：

```c
void *bda_alloc(bda_size_t size);
void bda_free(void *ptr);
void *bda_track_alloc_like(bda_size_t size);
void bda_track_free_like(void *ptr);
void bda_mem_track_begin_like(u32 free_on_finish);
int bda_mem_track_report_like(u32 summary_only);
void bda_mem_track_finish_like(void);
void *bda_mem_track_retain_like(void *ptr);
void bda_mem_track_release_like(void *ptr);
void *bda_calloc_like(bda_size_t count, bda_size_t size);
void *bda_realloc_like(void *ptr, bda_size_t new_size);
```

`MEM+0x000` 是 tracked heap alloc wrapper。C200 table entry 目标为 `0x80058574`，
只读取 `a0=size`，先调用基础 allocator `0x80007648(size)`。如果 firmware
tracking flag `0x80474020` 未开启，它直接返回基础 allocator 的 pointer；开启时会把
`pointer/size/active flag` 写入 `0x80823e40` 起始的 12-byte 记录表，并递增
`0x80474018` 的记录计数。分配失败时仍返回 `0`。

`MEM+0x004` 是 tracked heap free wrapper。C200 table entry 目标为 `0x80058618`，
只读取 `a0=ptr`。tracking flag 开启时会在线性记录表里查找该 pointer，命中后清
`active flag` 和 pointer 记录；无论是否命中，最后都会调用基础 free helper
`0x800067f4(ptr)`。tracking flag 未开启时直接退化为基础 free。

`MEM+0x01c` 是 heap tracking begin helper。C200 table entry 目标为 `0x80058554`，
只读取 `a0=free_on_finish`，设置 tracking flag `0x80474020 = 1`，保存
`0x8047401c = free_on_finish`，并清记录计数 `0x80474018 = 0`。它没有可用
return value。

`MEM+0x020` 是 heap tracking report/count helper。C200 table entry 目标为
`0x8005868c`，读取 `a0=summary_only` 并返回当前记录计数 `0x80474018`。
`summary_only == 0` 时会扫描 `0x80823e40` 的记录表并通过 trace/log helper 输出
仍有 pointer 的记录；非 0 时只输出 summary-like log。它不会释放 pointer，也不会
清 tracking state。

`MEM+0x024` 是 heap tracking finish helper。C200 table entry 目标为 `0x80058750`，
不读取调用者参数，会扫描 `0x80823e40` 的记录表并输出仍有 pointer 的记录。随后清
`0x80474018` 和 `0x80474020`。如果 `MEM+0x01c` 保存的 `free_on_finish`
(`0x8047401c`) 非 0，它还会对仍有记录的 pointer 调用 `0x800067f4(ptr)`，因此
这个 helper 可能释放调用者还持有的 firmware heap pointer。

`MEM+0x028` 是 heap tracking retain-like helper。C200 table entry 目标为
`0x80058820`，读取 `a0=ptr`，在 `0x80823e40` 起始的 tracked record table
中查找 pointer；命中后递增记录 `+8` 的 refcount-like 字段并返回原 pointer。
未命中或传入空 pointer 时会调用 trace/log helper，仍返回原 pointer 或 `0`。

`MEM+0x02c` 是 heap tracking release-like helper。C200 table entry 目标为
`0x800588b8`，读取 `a0=ptr`，在同一 tracked record table 中查找 pointer；
命中后递减记录 `+8` 的 refcount-like 字段。递减结果为 0 时，它会调用基础
free wrapper `0x800067f4(ptr)`，并清记录 pointer/refcount。因此这个 helper
可能释放调用者传入的 pointer，不能当作无副作用的 release flag。

`MEM+0x008` 是 firmware heap alloc wrapper。C200 table entry 目标为 `0x80007648`，只读取
`a0=size`，进入全局锁后调用内部 allocator `0x80007440(size)`，释放锁后把
内部 allocator 返回的 pointer 交给调用者。

`MEM+0x00c` 是 firmware heap free wrapper。C200 table entry 目标为 `0x800067f4`，只读取
`a0=ptr`，进入同一个全局锁后调用内部 free helper `0x80006620(ptr)`，随后
释放锁。该 wrapper 没有可用 return value。

`MEM+0x010` 是 firmware heap calloc-like wrapper。C200 table entry 目标为
`0x800065bc`，读取 `a0=count`、`a1=size`，进入同一个全局锁后调用内部 helper
`0x80006540(count, size)`。内部 helper 会先把 `size` 向上对齐到 4 byte，再分配
`count * aligned_size` byte，成功后调用 zero-fill helper `0x800078ec(ptr, bytes)`。
`count == 0` 或 `size == 0` 返回 `0`。当前未见 overflow guard，不能把它当作
compiler libc calloc 的完整替代。

`MEM+0x014` 是 firmware heap realloc-like wrapper。C200 table entry 目标为
`0x800077b0`，读取 `a0=ptr`、`a1=new_size`：

- `ptr == 0 && new_size != 0`：退化为 `bda_alloc(new_size)`。
- `ptr != 0 && new_size == 0`：调用 `bda_free(ptr)`，返回 `0`。
- `ptr != 0 && new_size != 0`：先分配新块，再查询旧块大小，copy
  `min(old_size, align4(new_size))` byte，最后释放旧块并返回新 pointer。
- 新块分配失败或旧块大小查询失败时返回 `0`，不会释放旧块。

原机 `黄冈教辅.bda`、`飞天影音.bda` / `飞天影音_.bda` 有直接 MEM+0x010 调用点；
`飞天影音.bda` / `飞天影音_.bda` 也有直接 MEM+0x014 调用点。SDK 仍保留 `_LIKE`
后缀，因为这些 helper 依赖 C200 firmware heap 语义，不能对非 firmware heap pointer 使用。

## 使用边界

- `bda_alloc()` 返回的是 firmware heap memory，不是 compiler libc heap。
- 用 `bda_alloc()` 得到的 pointer 必须用 `bda_free()` 释放；不要和 libc
  `malloc/free` 混用。
- `bda_track_alloc_like()`/`bda_track_free_like()` 对应 firmware tracked wrapper；
  普通开发优先使用 `bda_alloc()`/`bda_free()`，只有需要匹配原机 tracked entry
  行为时才直接调用。
- `bda_mem_track_begin_like()` 会开启 firmware heap tracking；`free_on_finish`
  会被 `bda_mem_track_finish_like()` 读取。若该 flag 非 0，finish 可能释放仍被
  记录的 pointer。
- `bda_mem_track_retain_like()` / `bda_mem_track_release_like()` 只操作 tracking
  record table 中已有的 pointer；release 可能在 refcount-like 字段归零时释放
  pointer。普通业务代码不要用它们管理对象生命周期。
- `bda_calloc_like()` 返回的 pointer 同样必须用 `bda_free()` 释放；不要依赖它处理
  `count * size` overflow。
- `bda_realloc_like()` 也只能接收 firmware heap pointer；传 `0` 可作为 alloc，
  传非 `0` pointer 且 `new_size == 0` 会释放该 pointer。
- 不要把 stack pointer、static buffer、C200 内部 table pointer 或 file handle 传给 `bda_free()`。
- `bda_free(NULL)` 的行为尚未单独确认，新代码应避免依赖它。

SDK 示例 `reverse/examples/mem_alloc_demo.c` 演示保守用法：检查 `bda_alloc(64)`
返回 pointer，写入 64 byte app-local buffer，使用后只释放成功返回的 pointer。
失败路径直接提示 `alloc failed`，不会调用 `bda_free(NULL)`。

原机 `FS_OPEN` 自己也通过 `MEM+0x008` 申请 file handle object。Element/DLX resource parser
路径会用 `MEM+0x008` 分配 app-local resource table；GAMEBOY 路径会用它分配较大的 audio
或 framebuffer 相关 buffer。
