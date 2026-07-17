# C200 API Function-Level 说明

本文记录从 `C200.bin` 里的 API table function 地址继续 disasm 得到的 function-level 线索。
地址来源见 `system_api_tables.md`，这里重点写开发者会直接用到、或过去容易误判的 API。

复现 disasm slice 可以使用：

```powershell
python reverse\c200_api_disasm.py --name BDA_GUI_MSGBOX --size 0x80
python reverse\c200_api_disasm.py --table FS --offset 0x000 --size 0x120
```

## 文件系统表

### FS +0x000: `BDA_FS_OPEN`

system function VA：`0x80170b68`

当前证据：

- entry 保存 `a0` 到 `s0`、`a1` 到 `s2`，所以参数仍是 `path, mode`。
- 函数先调用 `MEM_ALLOC`，申请 `0x20a` byte 的 file handle/state object。
- 随后调用路径规范化/解析 helper；失败时释放刚分配的对象并返回 `0`。
- 成功后调用内部 open helper，并把 return value 作为 file handle 返回。
- 失败路径会写全局错误码，能看到 `1`、`9`、`0x10` 等错误值。

开发建议：

```c
int fd = bda_fs_fopen_raw(path, "rb");
if (!bda_fs_file_is_valid(fd)) {
    /* 打开失败；不要继续传给 read/seek/close */
}
```

成功 handle 是高地址 file-object pointer，按 signed `int` 显示时通常为负数。
失败哨兵是 `0` 或 `0xffffffff`，统一使用 `bda_fs_file_is_valid(fd)`。

### FS +0x004: `BDA_FS_CLOSE`

system function VA：`0x8017a928`

当前证据：

- entry 保存 `a0=file`，只使用一个调用者参数。
- 函数进入文件系统锁后调用内部 close helper `0x80170c74(file)`。
- return value 直接来自内部 close helper。

开发建议：

- SDK 暴露 `bda_fs_close_raw(file)`。
- 只关闭 `bda_fs_fopen_raw()` 成功返回的 fd；open 失败时不要再 close。

### FS +0x008 / +0x00c: `BDA_FS_READ` / `BDA_FS_WRITE`

system function VA：

```text
FS+0x008 -> 0x8017a978
FS+0x00c -> 0x8017ab2c
```

当前证据：

- 两个入口都保存 `a0=buffer`、`a1=size`、`a2=count`、`a3=file`。
- entry 先读取 `file+0x48` 的 signed 16-bit handle index，并检查是否在当前 volume
  数量范围内；非法时设置内部错误码 `9`。
- 文件系统后端未就绪时设置内部错误码 `0x10`。
- 上述失败路径都返回 `0`。这与 open/remove/chdir 等返回 `-1` 的路径不同。
- `FS+0x008` 主路径调用内部 read helper `0x80170d94(buffer,size,count,file)`。
- `FS+0x00c` 主路径调用内部 write helper `0x80171154(buffer,size,count,file)`。

开发建议：

- SDK 按 stdio 风格暴露 `bda_fs_fread_raw(buffer, size, count, file)` 和
  `bda_fs_fwrite_raw(buffer, size, count, file)`。
- 先用 `bda_fs_file_is_valid(fd)` 判断 open 结果；进入 read/write 后，返回 `0` 应按 EOF、
  写入 0 个元素或失败处理，不能再继续用 `-1` 作为唯一失败值。
- `bda_fs_read_raw(file, buffer, size)` 和 `bda_fs_write_raw(file, buffer, size)`
  只是固定 `size=1,count=size` 的便捷 wrapper。
- `fs_write_demo.c` 的 worker NAND 实测为 `write=19,tell=19,error=0,read=19,match=1`；
  停止模拟器后导出的 payload 与预期 19 byte 完全一致。

### FS +0x010: `BDA_FS_SEEK`

system function VA：`0x801712a0`

当前证据：

- entry 读取 `file+0x48` 的 signed 16-bit handle index 并检查 volume 范围；非法时
  返回 `-1` 并设置内部错误码 `9`。
- 保存的参数是 `a0=file`、`a1=offset`、`a2=whence`。
- 文件系统后端未就绪时返回 `-1` 并设置内部错误码 `0x10`。
- `whence == 0` 时把 `file+0x44` 设置为 `offset`。
- `whence == 1` 时把 `file+0x44` 设置为当前 `file+0x44 + offset`。
- `whence == 2` 时把 `file+0x44` 设置为 `file+0x20 + offset`，其中 `file+0x20`
  是当前 C200 handle object 中的 size/end-like word。
- 其他 `whence` 值会直接返回 `-1`。
- 成功路径返回更新后的 `file+0x44`。

开发建议：

- SDK 暴露 `bda_fs_seek_raw(file, offset, whence)`，并提供
  `BDA_SEEK_SET/BDA_SEEK_CUR/BDA_SEEK_END` 常量。
- 只传这三个 whence 常量；不要把 libc 以外的 custom 值传入该入口。
- 需要文件大小时，原机常用 `seek(file, 0, BDA_SEEK_END)` 后接
  `bda_fs_tell_raw(file)`。

### FS +0x014: `BDA_FS_TELL`

system function VA：`0x8017ac18`

当前证据：

- 函数先读取 handle object `+0x48` 的 signed 16-bit index，并与全局 volume/backend
  数量比较。
- index 为负或越界时返回 `0`，并把内部错误码写为 `9`。
- index 为 `0` 时要求全局 backend pointer `0x804bf434` 非空；非 0 index 路径要求
  `0x804bf438` 非空，否则返回 `0` 并把内部错误码写为 `0x10`。
- 有效路径返回 handle object `+0x44` 的 word。
- 这与原机应用中 `fseek(..., SEEK_END)` 后取大小的模式吻合。

因此 `bda_fs_tell_raw(file)` 可按当前 offset/文件大小类 return value 使用。调用前仍应通过
`bda_fs_file_is_valid(file)` 确认 handle；返回 `0` 既可能是文件开头，也可能是错误路径，必要时用 read/seek
结果交叉判断。

### FS +0x018/+0x01c/+0x020: file 状态 helper

system function VA：

```text
FS+0x018 -> 0x8017ac84
FS+0x01c -> 0x8017acfc
FS+0x020 -> 0x8017ad70
```

共同边界：

- 三个 entry 都读取 `a0=file`，先检查 handle object `+0x48` 的 signed 16-bit
  index，并与全局 volume/backend 数量比较。
- index 为负或越界时设置内部错误码 `9`。
- backend pointer 为空时设置内部错误码 `0x10`。
- 调用前仍应通过 `bda_fs_file_is_valid(file)` 确认 handle，不要传入失败哨兵。

具体行为：

- `FS+0x018` 是 feof-like：有效路径读取 `file+0x20` size-like word 和
  `file+0x44` 当前 offset；当前位置小于 size 时返回 `0`，否则返回 `1`。
- `FS+0x01c` 是 ferror-like：有效路径读取 `file+0x4a` 的 `0x1000` flag，
  flag 非 0 时返回非 0。
- `FS+0x020` 是 clearerr-like：有效路径清掉 `file+0x4a` 的 `0x1000` flag。

证据：

- BB 虚拟机、Eros 方块、三国霸业、九宫格、决战坦克、连连看、雷霆战机、
  黑白子等都有这些 offset 的直接 FS table 调用点，调用形状与 stdio file
  状态 wrapper 匹配。

SDK 暴露：

- `bda_fs_eof_like(file)`、`bda_fs_error_like(file)`、`bda_fs_clear_error_like(file)`。
  保留 `_LIKE` 后缀，提醒它们只确认了当前 C200 handle layout 和 error flag。

### FS +0x024: `BDA_FS_REMOVE`

system function VA：`0x801717f4`

当前证据：

- entry 保存 `a0=path`，只使用一个调用者参数。
- 函数申请 `0x20a` byte 临时 path buffer，并调用路径解析 helper `0x8016f904`。
- 路径解析结果为负数，或解析出的 volume/index 超出当前 volume 数量时，会释放
  临时 buffer，返回 `-1`，并设置内部错误码 `9`。
- 主路径调用内部删除 helper `0x801714ec(path_buffer)`；随后释放临时 buffer。
- 删除后还会调用内部同步/刷新 helper。该路径失败时可设置内部错误码 `0xd0`，
  并返回 `-1`；文件系统后端未就绪时可设置 `0x10`。

开发建议：

- SDK 暴露为 `bda_fs_remove_raw(path)`，只固定单参数 path ABI。
- 它是破坏性调用，只传明确的文件路径；不要传目录、空 pointer 或未终止字符串。
- 删除后若要重建文件，应重新 `bda_fs_fopen_raw(path, "wb")` 并检查 return value。

### FS +0x028: `BDA_FS_RENAME_LIKE`

system function VA：`0x80171d24`

当前证据：

- 参数为 `a0=old_path`、`a1=new_path`。
- 函数先调用 `0x80174340(path, out)` 判断两个 path 的 volume/backend 类别。
- 路径类别和 backend pointer 检查通过后，申请两个 `0x20a` byte 临时 path buffer。
- 分别调用 `0x8016f904(old_path, old_resolved)` 和
  `0x8016f904(new_path, new_resolved)`。
- 主路径调用内部 rename helper `0x80171930(old_resolved, new_resolved)`。
- 最后调用 `0x801813a0(volume)` 做同步/刷新；失败时可能设置内部错误码 `0xd0`。

原机证据：

- BB 虚拟机、Eros 方块、三国霸业、九宫格、决战坦克、连连看、雷霆战机、
  黑白子等游戏框架都有直接 FS+0x028 调用点。

SDK 暴露：

- `bda_fs_rename_like(old_path, new_path)`。这是破坏性 filesystem API，保留
  `_LIKE` 后缀；不要把它当成跨 volume move 的稳定 high-level API。

### FS +0x02c: `BDA_FS_CHDIR_LIKE`

system function VA：`0x8016fe18`

当前证据：

- entry 先保存 `a0=path`。`path == NULL` 时直接返回 `-1`；`path[0] == 0`
  时直接返回 `0`。
- 非空路径会申请 `0x20a` byte 临时 buffer，并调用路径解析 helper `0x8016f904`。
- 解析成功后会临时更新当前 volume/index global state，再调用内部 helper
  `0x8017a0d8(path_buffer, stack_info)` 读取对象属性。
- 成功路径检查 `stack_info+0x12` 的目录属性位 `0x4000`；如果不是目录，返回
  `-1` 并设置内部错误码 `0x15`。
- 最终成功路径会把path buffer 写入当前目录相关 global state，并返回 `0`。

开发建议：

- SDK 保守暴露为 `bda_fs_chdir_like(path)`。它不只是无副作用的存在性检查；
  成功后会改变当前目录状态，可能影响后续相对路径。
- 用它做“目录存在则进入，否则创建”的原机模式时，失败后再调用
  `bda_fs_mkdir_like(path)`；新代码若只想检查文件存在，优先使用
  `bda_fs_stat_like(path, flags)`。

### FS +0x030: `BDA_FS_MKDIR_LIKE`

system function VA：`0x80171f8c`

当前证据：

- entry 保存 `a0=path`，申请 `0x20a` byte 临时 buffer 后调用路径解析 helper
  `0x8016f904`。
- 解析结果为负数或超出当前 volume 数量时返回 `-1`，并设置内部错误码 `9`。
- 主路径会调用内部创建目录 helper `0x80171ec0(path_buffer)`。
- 创建后还会调用内部同步/刷新 helper；失败路径可设置 `0x10`、`0xd0` 等内部错误码。

开发建议：

- SDK 暴露为 `bda_fs_mkdir_like(path)`，只固定单参数 path ABI。
- 路径编码仍按 FS 其他入口处理，通常是 ASCII/GBK；不要传 `NULL` 或未终止字符串。
- 创建目录后仍应检查 return value，不要假设目录已经可枚举。

### FS +0x034: `BDA_FS_RMDIR_LIKE`

system function VA：`0x80172520`

当前证据：

- entry 只保存 `a0=path`，先调用路径解析 helper `0x8016f904(path, temp_path)`。
- 主路径调用内部 directory removal helper `0x801720c8(temp_path)`，并释放临时
  `0x20a` byte path buffer。
- `0x801720c8` 会读取目标对象属性，要求 directory bit 存在；普通 file path 会走
  错误路径并设置内部错误码。
- helper 内部会更新 directory entry、cluster chain 和 filesystem 同步状态；成功路径
  返回 `0`，失败通常返回 `-1`。
- inventory 中可见 `英语百科.bda`、`飞天影音.bda`、`飞天音乐.bda` 调用过
  `+0x034`。

开发建议：

- SDK 暴露为 `bda_fs_rmdir_like(path)`，只固定单参数 path ABI。
- 这是破坏性目录删除 API，不是 directory existence check。只传空目录 path；不要传
  file path、`NULL`、未终止字符串或仍包含文件的目录。
- 删除前如果只是想检查对象类型，优先用 `bda_fs_path_info_like(path, info)` 和
  `bda_fs_path_info_is_dir_like(info)`。

### FS +0x03c / +0x040 / +0x044: Directory Enumeration 结构

system function VA：

```text
FS+0x03c -> 0x80172630
FS+0x040 -> 0x8017add4
FS+0x044 -> 0x8017ae90
```

当前证据：

- `FS+0x03c(pattern, attr, find_data)` 保存 `a0=pattern`、`a1=attr`、
  `a2=find_data`。
- entry 先申请 `0x20a` byte 临时 path buffer，再调用路径解析 helper
  `0x8016f904(pattern, temp_path)`。
- 路径解析出的 volume index 为负或越界时释放临时 buffer，返回 `-1`，并设置
  内部错误码 `9`。
- backend pointer 未就绪时释放临时 buffer，返回 `-1`，并设置内部错误码
  `0x10`。
- 有效路径会对当前 backend 加锁，调用内部
  `0x8017e1a0(temp_path, find_data, attr)`，随后释放临时 buffer 并解锁。
- `0x8017e1a0` 成功后把 directory enumeration 状态写回调用者的 `find_data`。
- 临时 buffer 申请失败时会写全局 `0x80474280 = 1` 并返回 `0`；这个路径没有
  完整命名，调用者不应只依赖 return value 判断 `find_data` 是否可继续用。
- 内部成功路径会分配一个 `0x10c` byte cursor，并写到 `find_data+0x000`。
- 同一路径会写 `find_data+0x004`、`+0x008`、`+0x00c`、`+0x00e`、
  `+0x010`、`+0x012` 起的名称/路径区，以及 `find_data+0x21c`。
- `FS+0x040` 和 `FS+0x044` 开头都会读取 `find_data+0x010` 的 signed
  halfword 并检查范围；`FS+0x044` 还会释放 `find_data+0x000`。
- `FS+0x040` 的 index 为负或越界时返回 `-1` 并设置内部错误码 `9`。
- backend pointer 未就绪时返回 `-1` 并设置内部错误码 `0x10`。
- `FS+0x040` 有效路径会对当前 backend 加锁，调用内部
  `0x8017f6b0(find_data)` 更新下一项，然后解锁并返回内部 helper 的结果。
- `FS+0x044` 的 index 为负或越界时返回 `-1` 并设置内部错误码 `9`。
- `FS+0x044` 的 backend pointer 未就绪时返回 `-1` 并设置内部错误码 `0x10`。
- 有效路径会对当前 backend 加锁，调用内部 `0x8017f73c(find_data)` 释放/关闭
  cursor 状态，然后解锁并返回内部 helper 的结果。

开发建议：

- 不要再使用早期探针里的 `unsigned char find_data[512]`；成功路径会写到
  `+0x21c`，512 bytebuffer 偏小。
- SDK 提供 `bda_fs_find_data_like_t`，当前大小为 `0x220` byte。字段名仍保持
  `_like`，因为文件名区编码、时间字段和属性字段还需要真机样本继续命名。
- 调用 `bda_fs_findfirst_like()` 前先清零 `find_data`；调用后除了检查 return value，
  还应确认 `cursor` 或已命名字段处于预期状态，再进入 `findnext`。
- `bda_fs_findnext_like(&data)` 会原地更新 `data`，调用者应在每次成功后读取
  `name_or_path12` 等字段；不要复用尺寸不足或未初始化的 buffer。
- `findfirst` 成功后即使只读第一项，也应调用 `bda_fs_findclose_like(&data)`；
  不要把 close 当成可省略的状态清理。

### FS +0x048: `BDA_FS_DISKINFO_LIKE`

system function VA：`0x80172754`

当前证据：

- `a0` 只取低 8 位作为 drive/volume 选择，已见 `0` 和 `1` 两类路径。
- `a1` 是调用者 output struct pointer。
- drive 不是 `0` 或 `1` 时返回 `-1`，并写入内部错误码 `9`；backend 未就绪时
  返回 `-1` 并写入内部错误码 `0x10`。
- 成功路径写四个 word：`info+0x00 = total_clusters_like`、
  `info+0x04 = free_clusters_like`、`info+0x08 = sectors_per_cluster_like`、
  `info+0x0c = 0x200`。
- 系统设置和九门课程都会计算 `info[1] * info[2] * info[3]`，用于剩余空间阈值
  判断。

开发建议：

- SDK 暴露 `bda_fs_disk_info_like_t` 和
  `bda_fs_disk_free_bytes_like()` / `bda_fs_disk_free_bytes64_like()`。前者保留
  32-bit 兼容计算，后者做 64-bit 乘法；新代码优先用 64-bit helper。

### FS +0x050: `BDA_FS_GETCWD_LIKE`

system function VA：`0x801700d0`

当前证据：

- 表 entry 保存 `a0=buffer`、`a1=size`，不读取 `a2/a3`。
- 函数读取当前 volume index，并从内部 current path table 取字符串长度。
- return value 是需要的 byte 数：当前 path 字符串长度加 `3`，即 drive 字母、冒号和
  NUL 也计入。
- `buffer == NULL` 时不写入，只返回 required size。
- `size` 小于 required size 时也直接返回 required size。
- buffer 足够时写入形如 `A:`/`B:` 前缀的路径，并复制当前目录字符串，最后补 NUL。

开发建议：

- SDK 暴露 `bda_fs_getcwd_like(buffer, size)`。
- 如果 return value 大于传入 `size`，调用者应扩大 buffer 后重试。
- 这是只读 getter，不会改变 current directory；切换目录仍用
  `bda_fs_chdir_like(path)`。

### FS +0x054: `BDA_FS_PATH_INFO_LIKE`

system function VA：`0x8017a0d8`

当前证据：

- 表 entry 保存 `a0=path`、`a1=info`，不读取 `a2/a3`。
- `path == NULL` 或 `info == NULL` 时返回 `-1`。
- entry 申请 `0x20a` byte 临时 path buffer，调用 `0x8016f904(path,temp_path)`
  解析路径；解析失败返回 `-1` 并写内部错误码 `9`。
- 成功路径会先写 `info+0x00` 和 `info+0x04` 的 volume/index halfword，
  再调用内部 helper `0x80179cb8(temp_path, info)`。
- `0x80179cb8` 会写 `info+0x02` attr-like flags、`info+0x08` size-like word，
  以及 `info+0x0c/+0x10/+0x14` 三个 time-like word。目录路径会设置 attr bit
  `0x4000`，并把 size-like 清 0。

开发建议：

- SDK 暴露 `bda_fs_path_info_like(path, info)` 和 0x18 byte 的
  `bda_fs_path_info_like_t`。
- 目前只把 `attr_like`、`size_like` 和 directory bit `0x4000` 作为可用字段；
  `time_like*` 不命名为标准 FAT 时间。
- 这是只读查询，但仍要检查 return value；失败时不要读取旧 `info` 内容。

### FS +0x064: 未公开的 block read support helper

system function VA：`0x8017afb4`

当前证据：

- 该 offset 在 C200 FS 表中有有效 function pointer，不是空洞 table entry。
- entry 把 `a0` 截成 signed 16-bit 后做卷/索引范围检查；越界时返回 `-1`，
  并写入全局错误码 `9`。
- 主路径要求全局 FS 状态已初始化，会围绕内部调用拿 `0x804c` 附近的锁：
  `0x8000ba84(lock, 0, stack)` / `0x8000bb98(lock)`。
- 函数保存 `a1/a2/a3`，先用 `0x80175dfc(index, a1)` 把调用者的 block/cluster
  参数转换为内部位置，再调用：
  `0x8017fbc0(a0, converted_a1, a2_or_default, a3)`。
- `a2 == 0` 时会从全局 `0x80474254` 读取默认 byte 值作为第三参数。
- 九门课程已有两个调用点：调用者建立 `0x218` byte stack buffer，传
  `a2=1, a3=stack+0x10`，调用后分别读取 `stack+0x34` 或 `stack+0x14`
  的 byte 与应用全局值比较。

开发建议：

- 暂不在 `bda_sdk.h` 暴露 wrapper。当前能确认它是低层 block read support
  helper，但不是 path API、不是普通 file handle API，也不是存档 API。
- 后续探针应从九门课程调用上下文复制参数形状，而不是在裸 `bda_main()` 中
  猜测调用。

### FS +0x068: 不公开的 file-object block read helper

system function VA：`0x8017a200`

当前证据：

- entry 保存 `a0=buffer`、`a1=offset`、`a2=size`，并把 `a3` 保存为内部
  file object/descriptor pointer。
- C200 立即读取 `a3+0x48` 作为 signed 16-bit volume/index，越界时返回 0，
  并写全局错误码 `9`。
- 主路径读取 descriptor 的 `+0x20` file size、`+0x4a` flags 和 `+0x3c`
  block/cluster table；根据 offset 和 size 截断读取范围。
- 函数以 0x200 byte 为 block 单位调用内部 `0x8017fbc0(index, block, 1, stack_buf)`
  读到栈上临时 buffer，再调用 `0x8017b454(dst, src, len)` 复制到调用者 buffer。
- 如果 descriptor `+0x4a` 没有 `0x100` flag，会从 `descriptor+0x18` 起沿
  `0x8017d37c(index, cluster)` 计算后续 block/cluster。
- 雷霆战机和决战坦克各有一个同形调用点：
  `a0=buffer+index*stride, a1=index*stride, a2=stride, a3=file_object`，调用前
  `stack+0x14=0`。

开发建议：

- SDK 不公开 wrapper。这个入口不是 path API，也不是普通 `FILE*` 风格 read；
  `a3` 必须是 firmware 已初始化的内部 file object/descriptor。
- 需要读取文件时继续使用 `bda_fs_open_raw()`、`bda_fs_read_raw()` /
  `bda_fs_read_bytes_raw()` 和 `bda_fs_close_raw()`。
- 后续如果要复刻游戏资源 streaming，应先复原创建该内部 file object 的上游路径，
  不要在裸 BDA 里构造猜测 descriptor。

### FS +0x06c: `BDA_FS_STAT_LIKE`

system function VA：`0x8017a5ec`

当前证据：

- 表 entry 保存 `a0` 到 `s0`，保存 `a1` 到 `s2`，没有保存或读取 `a2/a3`。
- entry 先申请 `0x20a` byte 临时 path buffer，调用路径解析 helper `0x8016f904`。
- 路径解析成功后调用内部 helper `0x8017a500(temp_path, flags)`。
- 内部 helper 只使用 `path, flags`。flags 为 `2` 或 `6` 时会在普通打开成功后
  继续调用 `0x80178178` 检查对象属性；其他 flags 主要按打开结果返回。
- 失败路径返回 `-1`，并写入全局错误码，如 `1`、`9`、`0x10`、`0x12`。

开发建议：

- SDK wrapper 只暴露 `bda_fs_stat_like(path, flags)`。旧的第三个 output pointer 参数
  是早期误留，C200 不会填充输出结构。
- 当前把它当作 `access()` 或带 flags 的存在性/属性检查使用；flags 枚举仍需
  结合更多原机调用点继续命名。

### FS +0x080: 不公开的 path/open-object 内部检查

system function VA：`0x8017a708`

当前证据：

- entry 保存 `a0=path`，先调用 `0x80174340(path, stack_state)` 解析当前
  volume/path 状态。
- 主路径分配 0x58 byte 临时对象，清零后调用
  `0x80173504(temp_obj, path, stack_out, 0)` 填充对象字段。
- 如果对象属性 byte `temp_obj+0x0f` 含 `0x10`，也就是 directory-like，对应路径直接
  走失败分支。
- 之后调用 `0x80178178(temp_obj)`；该 helper 扫描 `0x8086cce0` 一带的打开
  file object table，比对 `+0x48` index 和 `+0x18` 对象字段。
- 匹配时返回 `1`，未匹配返回 `0`；解析失败、内存分配失败或 directory-like 路径
  返回 `-1`，并写内部错误码 `9`、`1` 或 `0x12`。

开发建议：

- SDK 不公开 wrapper。这个入口更像内部“path 是否对应已打开/占用对象”的检查，
  不是普通 exists/stat/is-file 查询。
- 需要查询路径属性时使用 `bda_fs_path_info_like(path, info)`；需要存在性/flags
  检查时使用 `bda_fs_stat_like(path, flags)`。
- 不要把 `FS+0x080` 命名为 `bda_fs_exists_like()` 或 `bda_fs_is_file_like()`。

### FS +0x07c: `BDA_FS_STORAGE_READY_LIKE`

system function VA：`0x801705ec`

当前证据：

- 表 entry 没有保存或读取 `a0..a3`，因此它是无参数查询。
- 函数只调用内部检测 helper `0x8000f8a0`。
- 返回前执行 `andi v0, v0, 0xff`，即只把内部检测结果的低 8 位返回给调用者。
- hardware probe `FSList_cat09.bda` 中该入口返回 `1`，随后 `findfirst` 路径仍可能因
  路径/过滤组合失败而返回 `-1`；这说明“存储已就绪”不等于具体 directory enumeration 一定成功。

开发建议：

- SDK 暴露 `bda_fs_storage_ready_like(void)`，不要给它增加 path、drive 或输出
  结构参数。
- 可在文件读写、directory enumeration 或部署包 smoke 前做轻量检查；具体 `fopen/findfirst`
  仍必须独立检查 return value。

### FS +0x078: `BDA_FS_MEDIA_PRESENT_RAW_LIKE`

system function VA：`0x8017952c`

当前证据：

- 表 entry 没有保存或读取 `a0..a3`，因此它是无参数查询。
- 函数只调用内部 helper `0x8017060c`，随后执行 `sltu v0,zero,v0`，把结果转成 `0/1`。
- `0x8017060c` 会调用 `0x800103c0()`；该函数先调用 `0x8001079c()` 检查
  `0xb0010300` 的 `0x00800000` 相关状态，再读取 `0xb0010300` 的
  `0x01000000` bit 并返回 bool。
- 这比 `FS+0x07c` 更接近 raw media-present bit，不代表 higher-level filesystem 已可用。

开发建议：

- SDK 暴露 `bda_fs_media_present_raw_like(void)`，只固定无参数 ABI 和 `0/1` return。
- 用它区分底层 media-present 状态；实际文件读写仍应先用
  `bda_fs_storage_ready_like()`，再检查每个 `fopen/findfirst/stat` return value。

### FS +0x074: 不公开的全局 flush/sync 候选

system function VA：`0x8017b0d0`

当前证据：

- 表 entry 不读取调用者参数。
- 函数检查全局 FS 初始化状态，拿 `0x804c` 附近的全局锁，调用内部状态聚合 helper
  `0x80181778()`。
- 随后遍历 `0x8086cce0` 附近最多 100 个 open file object slot；对
  `object+0x4a` 带 `0x4000` flag 的对象调用 `0x801781dc()`。
- `0x801781dc()` 会分配临时 buffer，按 file object 的 offset/size/path 状态调用
  内部 read/writeback helper，并释放临时 buffer。

开发建议：

- 当前不公开 SDK wrapper。它影响全局打开文件状态，且 return value 混合内部状态
  聚合结果和 flush error，普通开发不要直接调用。

## SYS 表

### SYS +0x000 / +0x008 / +0x00c / +0x010: 不公开的 system resource/session manager

system function VA：

```text
SYS+0x000 -> 0x80184d30
SYS+0x008 -> 0x80185628
SYS+0x00c -> 0x80185814
SYS+0x010 -> 0x801859f0
```

当前证据：

- `SYS+0x000(a0)` 是大型 dispatcher。它读取 `a0` 指向的 descriptor：
  `descriptor+0x00` 是 operation/type-like word，`+0x04` 是 flags，
  `+0x08` 可传给内部路径/参数 helper。函数会在 `0x8087d364` 附近最多 10 个
  system resource/session slot 中找空位，并通过 callback table 分派不同类型。
- `SYS+0x008()` 不读取调用者参数。它先处理 `0x804742a4` 当前 active slot，
  再遍历 10 个 slot；对每个已打开 slot 检查 flags、timeout/countdown，并调用
  slot callback 或 `0x8018fb20()` 之类的内部 scheduler helper。
- `SYS+0x00c(resource_id, value, mode)` 要求 `resource_id` 在 1..10，读取对应
  slot 的 type/callback/status；会调用 callback，把 `value` 写入 slot 状态，
  还会 busy-wait `0xea60` 并触发 scheduler helper。`mode` 至少影响返回/状态更新
  路径。
- `SYS+0x010(resource_id, state_ptr)` 同样要求 `resource_id` 在 1..10；当
  `state_ptr != 0` 时会读取其中 3 个 word 写入对应 slot，随后更新 countdown/
  status 并可能触发 scheduler helper。
- 这组 entry 和 `SYS+0x004` 共享 10-slot resource/session table，但语义覆盖
  open/dispatch/tick/update，不是普通文件、音频或 GUI API。

开发建议：

- SDK 不公开这组 wrapper。不要把 `SYS+0x000/+0x008/+0x00c/+0x010` 命名为
  app init、event loop、timer、sleep 或通用 resource open API。
- 目前仅保留 `BDA_SYS_CLOSE_LIKE` 常量用于逆向 `SYS+0x004` close entry；普通
  BDA 开发应使用已确认的 FS、raw audio、timer/delay wrapper。

### SYS +0x004: `BDA_SYS_CLOSE_LIKE`

system function VA：`0x80185414`

当前证据：

- entry 读取 `a0=resource_id`，先计算 `resource_id - 1`，只接受 1..10 范围。
- 有效路径按 `resource_id` 查询 `0x8087d364` 附近的内部 resource table。
- 如果 slot 未打开，或 table entry 为 `-1`，函数直接返回 0。
- 普通 close 路径会调用该 slot 的 close callback，并把 slot 状态写回 `-1`。
- 若 slot 类型为 `2` 且带特殊 flag，会先进入一段 0x200 byte stack buffer 的
  handshake/flush 路径，再回到 close callback。
- 函数会递减 `0x804bf580` 一带的全局 open resource count；计数清零时调用
  `0x8018918c(0)`。

开发建议：

- 这不是 app exit API，也不是 raw audio 专用 stop；不要在普通 BDA 里直接调用。
- SDK 只保留 table offset 常量供逆向和特殊资源生命周期复刻，不提供 wrapper。
- 已确认的 raw audio 生命周期应继续使用 `audio_open/ready/write/reset/flush` wrapper。

### SYS +0x024 / +0x048 / +0x04c: 不公开 stub

system function VA：

```text
SYS+0x024 -> 0x80187df8
SYS+0x048 -> 0x801895d4
SYS+0x04c -> 0x801895dc
```

当前证据：

- `SYS+0x024` 函数体只有 `jr ra; move v0, zero`，不读取调用者参数，稳定返回 `0`。
- `SYS+0x048` 函数体只有 `jr ra; nop`，不读取调用者参数，也不设置稳定 return value。
- `SYS+0x04c` 同样只有 `jr ra; nop`。
- 相邻地址后面有其他音频/路径相关函数，但 table entry 指向的只是这些 stub
  起始地址，不能把后续函数体算作该 offset 的 ABI。

开发建议：

- SDK 不公开 wrapper。不要把这些 offset 命名为 resource close、loader、flush 或
  package sound API。
- 需要 raw audio 生命周期时使用 `SYS+0x06c/+0x074/+0x078/+0x08c/+0x090/+0x0a0`
  这组已命名 wrapper。

### SYS +0x050: 不公开的打包音效 stub

system function VA：`0x8018ef04`

当前证据：

- C200 table entry `SYS+0x050` 指向的函数只有两条有效指令：`jr ra; v0 = 1`。
- `SYS+0x054` 同样是立即返回 `1` 的相邻 stub。
- 因此旧的 `BDA_SYS_PACKAGE_SOUND_LOAD_LIKE` 名称不准确，SDK 已不再公开该宏和
  wrapper。

开发建议：

- 不要把 `SYS+0x050` 当作已确认加载器。
- 原机游戏报告中保留 `SYS+0x050` 调用点记录，但它只能说明应用触达了音效调用簇，
  不能证明该 offset 自身完成加载。

### SYS +0x040 / +0x044: raw PCM attenuation set/get

system function VA：

```text
SYS+0x040 -> 0x8018921c
SYS+0x044 -> 0x80189248
```

当前证据：

- `SYS+0x040(attenuation)` 把负数 clamp 到 `0`，把大于等于 `99` 的值 clamp
  到 `98`，随后写 `0x806c4790 = 1` 和 `0x80474308 = pending attenuation`。
- 下一次 `SYS+0x078` write 在 `0x80194638` 发现 pending flag 后调用
  `0x80195f58`。该函数按 `floor(value / 3)` 保存档位，再由 `0x80195fc8`
  选择 33-entry 16-bit PCM scaling callback 原地处理调用者 buffer。
- `SYS+0x044()` 调用 `0x80195fb4`，返回当前档位乘 3，因此 effective range 是
  `0..96`、步进 3。它读取的是已应用值，不是尚未消费的 pending value。
- `GameVolV1` 动态测试 `-1/0/1/2/3/48/97/98/120` 全部通过。输入峰值 12000
  在 effective attenuation `0/3/48/96` 时变为 `12000/11625/6000/46`。
  这证明数值表示 attenuation：`0` 是 full scale，`96` 是 near-silent。

开发建议：

- 公开 SDK 使用 `bda_audio_set_attenuation()` / `bda_audio_get_attenuation()`；
  不再保留错误的 package sound op40/op44 名称。
- setter 在下一次 PCM write 才生效。退出前恢复原值时，必须提交一个 silent block
  消费 pending value，然后再 stop。
- `96` 仍有极小非零输出，不能命名为绝对 mute。

### SYS +0x058 / +0x05c / +0x060 / +0x064 / +0x068: 打包音效操作簇

system function VA：

```text
SYS+0x058 -> 0x8018ecb4
SYS+0x05c -> 0x8018e958
SYS+0x060 -> 0x8018ee98
SYS+0x064 -> 0x8018eed0
SYS+0x068 -> 0x8018ee18
```

当前证据：

- 这些 entry 会读写 `0x804c4ba4`、`0x804c4ba8` 等全局音效状态，不是空 stub。
- `SYS+0x058` 只读取 `a0=descriptor`。它读取 descriptor 的 `+0x00/+0x08`，
  调用内部音频/任务 helper；成功时写 `0x804c4ba4 = 1` 并返回 `1`，
  已经初始化时返回 `0`。
- `SYS+0x05c` 使用 `a0=slot`、`a1=descriptor`、`a2`、`a3=flags` 四个参数；
  `slot >= 8` 或 package sound 未初始化时返回 `0`。它按 slot 访问
  `0x804c4d38` 附近的 descriptor 表，并把 descriptor 的 `+0x00/+0x04`
  组合成结束地址写入内部节点。
- `SYS+0x060` 不读取调用者参数，在状态存在且 `0x804c4ba8 == 0` 时设置
  `0x804c4ba8 = 1` 并返回 `1`，否则返回 `0`。
- `SYS+0x064` 不读取调用者参数，在状态存在且 `0x804c4ba8 != 0` 时清除
  `0x804c4ba8` 并返回 `1`，否则返回 `0`。
- `SYS+0x068` 不读取调用者参数；在状态存在时调用内部释放/停止 helper
  `0x80185414`，然后清除 `0x804c4ba4` 并返回 `1`，未初始化时返回 `0`。

开发建议：

- 这些入口暂保留 `_LIKE` 名称，因为 descriptor 布局和播放/停止时序仍需硬件
  probe 确认。
- 当前 SDK 签名只固定 C200 已确认的 ABI：
  `op58(descriptor)`、`op5c(slot, descriptor, a2, flags)`、`op60(void)`、
  `op64(void)`、`op68(void)`。
- custom 游戏若只需要简单声音，优先使用 GAMEBOY raw audio 路径；复刻原机游戏
  音效包时，再研究这组 SYS 调用。

### SYS +0x06c / +0x074 / +0x078: raw audio open/ready/write

system function VA：

```text
SYS+0x06c -> 0x80194654
SYS+0x074 -> 0x80194da4
SYS+0x078 -> 0x80194320
```

当前证据：

- `SYS+0x06c` 保存 `a0`，并把 `a1/a2` 截成 signed 8-bit 保存到 `s2/s3`。
  函数会初始化 DMA/音频 MMIO 寄存器，设置 `0x8058+0x6e8`、`0x8058+0x730`
  等 raw audio queue 状态；disasm slice 内未看到读取 `a3` 的证据，尾部固定
  `v0=0`，没有可用 return value。
- `SYS+0x074` 无调用者参数。它加锁后读取 `0x8058+0x6e8`，返回
  `0x8058+0x6e8 > 0` 的布尔值。
- `SYS+0x078` 保存 `a0=buffer`、`a1=bytes`。`bytes <= 0` 时返回 `-1`；
  正常路径会限制单次 chunk 到 `0x8000`，调用内部采样处理 helper，并按
  `0x8058+0x6e8/0x6ec/0x700/0x704` 一带的队列状态提交数据。函数最终返回
  `s4`，也就是已消费/提交的 byte 数。

开发建议：

- SDK 当前只固定 `bda_sys_audio_open_like(device, format, channels)`、
  `bda_sys_audio_ready_like()`、`bda_sys_audio_write_like(buffer, bytes)` 的 ABI。
- `bda_sys_audio_ready_like()` 可按 `0/1` ready bool 使用；`bda_sys_audio_write_like()`
  的非负 return value 可按已消费 byte 数处理。
- `bda_sys_audio_open_like()` 不暴露 return value，也不保留旧的第四参数。
- 这组三个入口应和 reset/flush 组成 GAMEBOY raw sample streaming 路径；
  不要和飞天音乐/数码录音的 high-level 媒体后端混用。

### SYS +0x084: 不公开的 raw input/internal helper

system function VA：`0x8001b6a8`

当前证据：

- entry 不读取调用者参数。
- 函数只顺序调用内部 helper `0x8001b324()` 和 `0x8001b0e4()`，随后返回。
- 相邻函数会读取固件内置路径、读入 `0x27c` byte 配置并解析输入相关表，但
  table entry `SYS+0x084` 只指向前面的短 helper，不能把后续函数体算进该 ABI。
- 当前无法从 entry 本身确认它是 reset、poll、init 还是状态提交；也没有稳定
  return value 约定。

开发建议：

- SDK 不公开 wrapper。不要把 `SYS+0x084` 命名为 input reset、keyboard init 或
  key polling API。
- 需要 raw key probe 时使用已确认的 `bda_sys_keycode_raw_like()`；GUI 应用仍应
  优先使用 window procedure 和 `BDA_MSG_KEYDOWN_LIKE`。

### SYS +0x088: `BDA_SYS_KEYCODE_RAW_LIKE`

system function VA：`0x8001b464`

当前证据：

- entry 不读取调用者参数。
- 函数先调用 `0x8005c384` 做输入状态检查；之后直接读取硬件寄存器
  `0xb0010100`、`0xb0010200`、`0xb0010300`。
- 当前 disasm 可见的 raw return code 包括 `0`、`4`、`5`、`6`、`7`、`9`、`10`。
- 该 entry 只返回 raw code，不生成 GUI message，也不填充 packet。

开发建议：

- SDK 暴露为 `int bda_sys_keycode_raw_like(void)`。
- 这些 raw code 尚未和具体实体键完成硬件对照；不要在文档或示例中提前命名为
  ENTER/BACK/方向键。
- 普通 GUI 应用优先通过 window procedure 的 `BDA_MSG_KEYDOWN_LIKE` 处理按键；
  该 raw query 更适合硬件 probe 或简单轮询工具。

### SYS +0x08c / +0x090 / +0x094 / +0x0a0: raw audio reset/state/flush

system function VA：

```text
SYS+0x08c -> 0x8001dc04
SYS+0x090 -> 0x8001dad4
SYS+0x094 -> 0x8001dae0
SYS+0x0a0 -> 0x801891e8
```

当前证据：

- `SYS+0x08c` 入口不读取调用者参数。它读取全局 `0x80362830` 指向的音频对象，
  调用内部 helper `0x80185d34` 和 `0x80185414`，随后把该 global pointer 清零，并进入
  `0x8001da40` 初始化/复位路径。
- `SYS+0x090` 入口只有 `lui/addiu/jr` 形态，不读取调用者参数，直接返回
  raw audio 全局 state pointer `0x80362830`。这是状态观察入口，不是 open/init。
- `SYS+0x094(state)` 读取调用者传入的 audio state pointer；`state == 0` 时返回
  `0`。非空时会把 `state+0x00/+0x04` 写入 `0x80362830/+0x04`，把 `state+0x08`
  起的一段状态复制到 `0x80362838`，并复制 `state+0x210..+0x221` 到同一全局
  state 区域，最后清 `0x804781b4` 并返回 `1`。这是全局 raw audio state 写入
  helper，不是只读 probe。
- `SYS+0x0a0` 入口同样不读取调用者参数。它依次调用 `0x80195db0`、
  `0x80195db8`、`0x80195170`；V3 动态证明它不清除 AIC replay/global enable，
  不能独立命名为 stop。
- 两个 entry 都没有稳定 return value 约定；C200 disasm 也没有显示它们向调用者返回可用状态码。

开发建议：

- SDK 按无参数 `void bda_sys_audio_reset_like(void)` 和
  `void bda_sys_audio_flush_like(void)` 暴露。
- SDK 按无参数 `void *bda_sys_audio_state_like(void)` 暴露 `SYS+0x090`；只能读取
  pointer 做 probe，不要写入该结构，也不要把它当 high-level 播放器对象。
- SDK 不公开 `SYS+0x094` wrapper。不要把它命名为 audio state setter、resume
  或 high-level player restore；普通 BDA 不应写入 `0x80362830` 全局 state。
- `SYS+0x08c` 和 `SYS+0x0a0` 都不能独立完成 raw close。V3-V5 证明 raw open
  不写 `0x80362830` 的前四个 state word，且 `+0x0a0` 后 AIC timer 仍运行。
- 当前固件的完整停止顺序是 `SYS+0x0a0` 后调用内部 `0x80195b24(0)`；公开头
  `bda_audio.h` 将其封装为固件绑定的 `bda_audio_stop()`。SDK 本身只面向 9588，
  因此公开方法名不重复设备型号。
- 不要把它们套用到飞天音乐/数码录音的 high-level 播放器后端；那些应用还使用
  `SYS+0x020/+0x02c/+0x034/+0x038/+0x094` 等另一组未公开 offset。

### SYS +0x0a8: 不公开 no-op stub

system function VA：`0x8001415c`

当前证据：

- C200 table entry `SYS+0x0a8` 指向 `0x8001415c`。
- 函数体只有 `jr ra; nop`，不读取参数，也不设置 return value。
- 旧的 `BDA_SYS_ALARM_COMMIT_LIKE` / `bda_sys_alarm_commit_like()` 名称来自
  闹钟调用点附近的早期猜测；该 offset 自身不能证明提交或持久化行为。

开发建议：

- SDK 已删除 `BDA_SYS_ALARM_COMMIT_LIKE` 和 `bda_sys_alarm_commit_like()`。
- 闹钟写入/提交仍应继续从 `SYS+0x0ac/+0x0b0/+0x0b8` 调用点和原机结构体分析。

## GUI 表

### GUI +0x2b8: `BDA_GUI_MSGBOX`

system function VA：`0x800c6544`

当前证据：

- entry 把 `a0/a1/a2/a3` 保存到栈上，然后调用内部 message box 构造函数 `0x800e0be4`。
- SDK 当前封装 `bda_msgbox_ex(parent, title, message, flags)` 会转换为系统实际顺序：
  `parent, message, title, flags`。
- no-template `hello_msgbox.c` 和真机/emu 路径已经证明这是最安全的首个 GUI API。

推荐从 `bda_msgbox()` 开始测试新工具链产物。

### GUI +0x084: `BDA_GUI_REGISTER_FRAME_LIKE`

system function VA：`0x800cc1c8`

当前证据：

- 函数会分配约 `0x114` byte 的内部 frame/window 对象。
- 输入是 `a0 = descriptor`，C200 会读取描述符 `+0x00..+0x30`，因此当前
  SDK 的 `bda_frame_desc_like_t` 固定为 `0x34` byte。
- `+0x08` 会作为 title/name 字符串复制到内部对象。
- `+0x18` 会作为 window procfunction pointer 保存。
- `+0x1c/+0x20/+0x24/+0x28` 对应 SDK 字段 `x/y/height/width`，会作为
  矩形/状态数据传给内部消息/布局 helper；原机样本常见 `height=240,width=320`。
- `+0x2c` 对应 SDK 字段 `surface`。原机复杂应用常见 `GUI+0x2fc(15)` 返回的
  object/surface；no-template BDA 开发先用 `surface=0`，需要复刻原机窗口对象时
  再显式设置。
- `+0x30` 对应 `aux30`，会被读取并写入内部 object `+0x80`。

开发建议：

- 使用 `bda_frame_desc_init_like()` 生成 no-template 稳定描述符，不要手写更大的
  结构体。注册过程中会同步触发 create 类 message；wndproc 的 create 分支不要
  直接 `begin_draw`、`blit` 或做大块绘制。
- 只依赖 `style/title/wndproc/x/y/width/height/surface` 这些已在样本中验证过的字段。
- 新应用若要做完整 frame 生命周期，应同时参考 `window_notes.md` 的 event loop 和
  BBVM draw-handle 模型。

### GUI +0x08c: `BDA_GUI_DEFAULT_PROC_LIKE`

system function VA：`0x800ca8c0`

当前证据：

- entry 保存 `a0=handle`、`a1=message`、`a2=wparam`、`a3=lparam`，签名与
  `bda_wndproc_t` 一致。
- `message` 在 `1..7`、`8..15`、`0x10..0x1f`、`0x20..0x5f`、`0x60..0x9f`
  等区间有分组处理；未命中的路径通常返回 `0`。
- `message == 0xb0` 时调用内部 `0x800d0688(wparam, lparam)` 后返回 `0`。
- `message == 0xb1` 进入 redraw/input 类路径，会读取 handle 的 rect/style 字段，
  可能调用 `0x800de830` 或 `0x800de690` 准备 redraw 区域，并调用
  `0x800cfb08(handle, wparam)`、`0x800d02b4(handle, wparam, flag)` 等内部
  helper。
- `message == 0xb2` 要求 `wparam != 0`，并按 `lparam` 和 handle style 分支处理；
  它不是普通无副作用查询。
- `message == 0xb3` 会创建临时 draw object/context，调用
  `0x800d02b4(handle, temp, wparam)` 后释放临时对象。

开发建议：

- custom `bda_wndproc_t` 只处理自己认识的 message；未消费的 message 可返回
  `bda_gui_default_proc_like(hwnd, message, wparam, lparam)`。
- 不要把 `GUI+0x08c` 当成通用 send/dispatch API；主动发消息仍应使用
  `bda_gui_send()` 或 `bda_gui_notify_like()`。
- `BDA_MSG_REDRAW_INPUT_LIKE(0x00b1)`、`BDA_MSG_TOUCH_A_LIKE(0x00b0)` 等名字仍是
  实验性别名，但它们确实落在 default proc 的特殊处理分支里。

### GUI +0x04c: `BDA_GUI_FRAME_RELEASE_LIKE`

system function VA：`0x800dd31c`

当前证据：

- entry 只读取 `a0=handle`。
- `handle == 0` 时使用默认对象槽 `0x80825840`；`handle == -1` 时使用该槽的
  `+0xf0` pointer。
- 非空 handle 会检查对象开头 halfword 是否为 `1`。若对象 subtype halfword 为
  `0x11`，会改用默认槽 `+0xf0`；否则使用 `handle+0xcc` 指向的对象。
- 目标对象存在时，会把目标对象第一个 word OR 上 `0x80000000`，然后返回 `0`。
- 没有可用目标对象时返回 `-1`。

开发建议：

- 该入口更像 release/request/mark helper，不是释放内存的 close 操作。
- 顶层 frame 的最终资源释放仍应使用 `bda_gui_close_frame_like(frame)`。
- 不要把它当作普通 control destroy，也不要在不了解默认 frame slot 的情况下传
  `0` 或 `-1` 做探测。

### GUI +0x030 / +0x050 / +0x054: event loop helper

system function VA：

```text
GUI+0x030 -> 0x800dbfd0
GUI+0x050 -> 0x800de378
GUI+0x054 -> 0x800dd4b8
```

当前证据：

- `GUI+0x030` 读取 `a0=message_buffer`、`a1=frame_or_handle`。entry 会先把
  `message_buffer` 清零 `0x1c` byte；SDK 用 `BDA_GUI_MESSAGE_SIZE` 和
  `bda_gui_message_like_t` 固定该大小。
- `a1 == 0` 时使用默认事件/frame 状态槽；`a1 == -1` 或非法对象时会退到默认
  槽的 `+0xf0` pointer。
- `GUI+0x030` 会按内部 pending flag、frame 列表和输入状态填充消息包。已确认写入
  `message_buffer+0x00 = handle`、`+0x04 = message`、`+0x08 = wparam`、
  `+0x0c = lparam` 等字段。
- `GUI+0x030` 生成 redraw/input 路径时会写 `message == 0xb1`，并使用
  `0x804a6800/0x804a6801/0x804a6804` 一带的内部队列状态。
- `GUI+0x050` 不是无参数 pump。它读取 `a0=message_buffer`，只在
  `message_buffer+0x04` 为 `0x10` 或 `0x13` 且 `0x800de210()` 返回目标对象时，
  分别派生内部 `0x11` 或 `0x14` message，并调用 `0x800dd380`。
- `GUI+0x054` 读取 `a0=message_buffer`。若 `message_buffer+0x00 == -1`，
  直接返回 `-1`；若为 `0`，使用默认 callback `0x800d3d04`；否则调用
  `handle+0x88` 的 wndproc。
- `GUI+0x054` 调用目标 callback 时参数为
  `handle, message, wparam, lparam`，分别来自 message buffer 的 `+0x00/+0x04/+0x08/+0x0c`。

开发建议：

- SDK wrapper 固定为 `bda_gui_event_poll_like(bda_gui_message_like_t *message, frame)`、
  `bda_gui_event_step_like(bda_gui_message_like_t *message)`、
  `bda_gui_event_dispatch_like(bda_gui_message_like_t *message)`。
- 常见 event loop 是 `poll(&msg, frame) -> step(&msg) -> dispatch(&msg)`。不要再使用
  旧的无参数 `bda_gui_event_step_like()`。

### GUI +0x03c / +0x040: notify/post 与 send

system function VA：

```text
GUI+0x03c -> 0x800dced0
GUI+0x040 -> 0x800dd380
```

当前证据：

- `GUI+0x03c` 读取 `a0=handle`、`a1=message`、`a2=wparam`、`a3=lparam`。
- `handle == 0` 时使用默认 frame/event 状态；`handle == -1` 或非法对象时退到
  默认槽的 `+0xf0` pointer；普通对象路径可能改用 `handle+0xcc`。
- `message == 0xb1` 时不写 ring buffer，只把目标状态 word OR 上 `0x02000000`
  后返回。
- 其他 message 会检查目标队列 `+0x14/+0x18/+0x1c`，按 0x1c byte 一项写入
  `handle/message/wparam/lparam`，再把目标状态 word OR 上 `0x40000000`。
- 队列满或没有目标时返回负值；成功入队返回 `0`。
- `GUI+0x040` 读取同样四个参数，但它是同步 send：`handle == -1` 直接返回 `-1`；
  `handle == 0` 时调用默认 callback `0x800d3d04`；非 0 handle 时直接调用
  `handle+0x88` wndproc。
- `GUI+0x040` 的 callback 参数就是 `handle,message,wparam,lparam`，return value 直接来自
  callback。

开发建议：

- 需要同步得到 return value 时用 `bda_gui_send(handle, message, wparam, lparam)`。
- 需要投递到 frame/event queue 时用 `bda_gui_notify_like(handle, message, wparam, lparam)`。
- 不要把 `notify` 当成立刻执行；它通常要等 `GUI+0x030/+0x054` message loop 消费。
- `BDA_MSG_REDRAW_INPUT_LIKE(0xb1)` 在 `notify` 中是特殊 pending flag，不是普通队列消息。

### GUI +0x088 / +0x098 / +0x17c: frame 生命周期 helper

system function VA：

```text
GUI+0x088 -> 0x800ce090
GUI+0x098 -> 0x800cc4ec
GUI+0x17c -> 0x800cdffc
```

当前证据：

- `GUI+0x088` 只读取 `a0=handle`，先调用 `0x800d4900()`，再用
  `0x800dd180(handle)` 解析内部 frame object。
- `GUI+0x088` 找到 frame object 后，会遍历 `object+0xe8/+0xec` 链表，向子对象
  发送内部 `0x66` message；随后向 frame 发送 `0xf1` message，并释放
  `object+0x78` 等关联资源。成功路径返回 `1`，解析失败返回 `0`。
- `GUI+0x098` 读取 `a0=handle`、`a1=mode`。`mode == 0`、`0x10`、`0x100`
  都有特殊路径，会发送 `0xf6`、`0xf5`、`0xf2`、`0x10a/0x10b`、
  `0xb2` 等内部 message，并可能改写 frame style bit `0x08000000`。
- `GUI+0x17c` 只读取 `a0=handle`。它会先处理 `handle+0x8c`，再按需释放
  `handle+0x44`、`handle+0x4c`，随后清理 `handle+0x74` 和 `handle+0x54`
  起的资源，最后释放 frame 本体。
- `GUI+0x17c` 返回前会清空 `0x804a6540` 起的 active/current frame 全局槽：
  `+0x00/+0x04/+0x08/+0x0c`。
- 该函数没有稳定 return value：正常路径释放 frame 后，`v0` 只是前序内部调用或全局
  地址计算留下的值，不能解释为成功码。
- `TouchStageV11.bda` 已在真机确认完整组合：`GUI+0x088 stop`、
  `GUI+0x04c release`、继续事件泵直到 poll 返回 0、`GUI+0x17c close`，随后
  `bda_main` 返回并恢复系统主菜单。

开发建议：

- 公开 SDK 的真机已验证收尾使用 `void bda_gui_close_frame(frame)`；候选头中的
  `bda_gui_close_frame_like()` 只用于逆向兼容，不能读取其返回值。不要把顶层 frame
  close 和普通 control `bda_gui_destroy_like()` 混用，也不要把它和普通 control
  destroy 当成同一生命周期阶段。
- `bda_gui_frame_stop_like(frame)` 更像停止/收尾一个已解析 frame，并向内部对象
  广播 stop message；不要把它当成仅设置一个 boolean flag。
- `bda_gui_frame_activate_like(frame, mode)` 的 `mode` 是固件内部状态码，不是
  简单 show/hide。新代码只应复刻已观察到的原机 mode。
- 完整开发顺序见 `docs/verified/touch_window_lifecycle_api.md`。

### GUI +0x1a4: `BDA_GUI_CREATE`

system function VA：`0x800ccfac`

当前证据：

- 函数从寄存器读取 `class, caption, style, flags`。
- 还会读取栈上的 `id, x, y, width, height, parent, extra` 参数并传给内部 control
  构造路径。
- 记事本、电子书、设置等样本都按这个形状创建 edit/listbox/scroll 等 control。

开发建议：

- 使用 `bda_gui_create_window_like()`。旧 `bda_gui_create_ex()` 参数顺序来自早期
  探针误名，已从 SDK 删除，避免开发者继续按错误 ABI 创建 control。
- 不要在没有有效 parent/window 上下文时直接创建复杂 control，hardware probe 显示这类
  调用可能导致重启。

### GUI +0x1a8: `BDA_GUI_DESTROY_LIKE`

system function VA：`0x800cd41c`

当前证据：

- entry 只读取 `a0=handle`，并先调用 `0x800d4900()`。
- 只处理对象开头 halfword 为 `1` 且 subtype halfword 为 `0x12` 的 handle；
  不匹配时直接返回 `0`。
- 主路径先同步发送内部 `0x64` message：`0x800dd380(handle, 0x64, 0, 0)`；
  callback 返回非 0 时停止销毁并返回 `0`。
- C200 会读取 `handle+0xd0` 的 parent/manager，并清理其中 `+0xd8/+0xdc/+0xe0`
  指向当前 handle 的槽。
- 随后发送内部 `0x16a` message，并调用 `0x800cee94(..., 0x165, ...)` 之类的
  全局 cleanup helper。
- 释放路径会清理 style bit、draw/child 相关资源、`handle+0x50`、`+0x54`、
  `+0x74/+0x78`、`+0x8c` 等关联对象，最后调用 `MEM_FREE(handle)`。
- 成功释放返回 `1`，不匹配或被 callback 阻止返回 `0`。

开发建议：

- SDK 暴露 `bda_gui_destroy_like(handle)`，只用于 `GUI+0x1a4` 创建出的 child
  control/object。
- 顶层 frame/window 不应走这个入口；event loop 退出后使用
  `bda_gui_close_frame_like(frame)`。
- 这个 entry 会触发对象 callback 和父/manager 状态更新，不是无副作用 free。

### GUI +0x0e0: `BDA_GUI_OBJECT_OP_LIKE`

system function VA：`0x800ccf64`

当前证据：

- entry 只保存并使用 `a0=object`，没有读取 `a1/a2`。
- 函数先调用内部 helper `0x800ccc58(object)`，保存其 return value。
- 随后调用 `0x800dced0(object, 0xb1, 0, 0)`，向对象发送内部 `0xb1`
  消息/刷新通知。
- 最终返回 `0x800ccc58(object)` 的结果。

开发建议：

- SDK 暴露 `bda_gui_object_op_like(object)`。旧的 `object, op, arg` 三参数 wrapper
  与 C200 table entry 不符，`op/arg` 不会被读取。
- 它适合复刻 BBVM/窗口绘制路径中“绘制后通知对象刷新”的调用；不要把它当作通用
  object command API。
- TouchStageV20 在 BBK 9588 真机把 standalone 顶层 frame 传给该入口，日志在首个
  触摸事件后、wrapper 返回前停止并死机。`0x800ccc58(object)` 需要原机认可的可刷新
  child object；顶层 frame 应直接走已确认的 frame notify 路径，而不是套用 `+0x0e0`。

### GUI +0x304 / +0x308 / +0x30c: draw context 生命周期

system function VA：

```text
GUI+0x304 -> 0x800bceec
GUI+0x308 -> 0x800bce50
GUI+0x30c -> 0x800bd4b0
```

当前证据：

- `GUI+0x304` 和 `GUI+0x308` 都会从 `0x804a60c0` 开始按 `0xd4` 扫描 5 个普通
  draw context 槽；两个入口都会读取 `a0=handle`。`0x804a64e4` 是另一条初始化路径
  使用的保留 context，不是第 6 个普通槽。
- 扫描循环的 `slti index,6` 会额外检查保留 context 的 `+0x08`；5 个普通槽全满且
  保留 context 非空时，函数仍按 `index=6` 计算 `0x804a65b8`，没有返回 pool-full，
  随后的 `0x800bd678` 会从越界结构 `+0x0c` 开始覆盖相邻全局内存。
- `GUI+0x304` 调用内部 helper `0x800bd678(context_slot, handle, 0)`，即 mode=0。
- `GUI+0x308` 调用同一内部 helper `0x800bd678(context_slot, handle, 1)`，即 mode=1。
- `GUI+0x30c` 只读取 `a0=draw_context`；`a0 == 0` 时会落到默认 context
  `0x80825690`，因此不适合作为安全 smoke。
- `GUI+0x30c` 会清理 `context+0x94` 和 `context+0xb0` 两组区域/子区域状态，并
  根据 `context+0x0c/+0xcc/+0xd0` 的关系决定是否继续调用内部更新 helper。
- `GUI+0x30c` 没有稳定 return value；SDK 暴露为 `void bda_gui_end_draw_like(draw_context)`。
- `GUI+0x30c` 还会把 fixed slot 的 `+0x08` 清零。每个 `GUI+0x304/+0x308` 返回值
  必须恰好结束一次；`GUI+0x314` 只释放 compatible heap context，不能代替该配对。
- 原机记事本使用 `begin_draw -> GUI+0x074(1) -> 绘制 -> GUI+0x074(0) -> end_draw`
  的模式。
- BBVM 还使用 `GUI+0x304(frame_handle)` 获取 draw handle，再通过 `GUI+0x4f0` 绘制文字；
  该路径已由 hardware probe 证明可以显示文本。
- 雷霆战机/决战坦克在 wndproc message `0x60` 分支中把 callback 传入的 `a0=object`
  保存到 game global，随后调用 `GUI+0x304(object)`，把返回的 draw/context 保存为
  后续 `GUI+0x35c/+0x40c/+0x414/+0x418` 使用的 context。message `0x66` 分支再用
  `GUI+0x30c(context) -> GUI+0x088(object) -> GUI+0x04c(object)` 清理。

开发建议：

- 简单 control 绘制优先复刻原机应用的 draw 生命周期。
- SDK 暴露 `bda_gui_current_draw_like(handle)` 和 `bda_gui_begin_draw_like(handle)`；
  旧的无参数 `current_draw` wrapper 会丢失 C200 读取的 `a0=handle`。
- 两者不是“查询当前全局 draw handle”的无状态 getter；都会分配或复用一个 draw
  context slot，并要求调用者已经处在有效 frame/window 生命周期里。
- 需要文本输出时参考 BBVM 模型，但不要只复制单个绘图调用；frame event loop 和
  cleanup 所有权也要一起复刻。

### GUI +0x3f8 / +0x3fc / +0x400: `BDA_GUI_BLIT_LIKE` / `BDA_GUI_CAPTURE_REGION_ALLOC_LIKE` / `BDA_GUI_BLIT_ALT_LIKE`

system function VA：

```text
GUI+0x3f8 -> 0x800c0ba8
GUI+0x3fc -> 0x800c0bf0
GUI+0x400 -> 0x800c0c90
```

当前证据：

- 两个入口都是 5 参数 ABI：`x, y, height, width, buffer`。第五参数从调用者
  `stack+0x10` 读取。
- `GUI+0x3f8` 会读取全局 draw backend `0x80474030`，把 `a0=backend->surface`、
  `a1=x`、`a2=y`、`a3=height` 传给 backend `+0x84` callback，并在栈上传入
  `width` 和 `buffer`。
- `GUI+0x3fc` 是 4 参数 ABI：`x, y, width, height`。它读取 backend 的
  `bytes_per_pixel`，按 `width * height * bytes_per_pixel` 调 `MEM+0x008`
  分配 buffer，然后把 `x,y,width,height,buffer` 交给 backend `+0x84`，返回该
  buffer。分配失败返回 `0`。
- `GUI+0x400` 会先用 backend 的 `+0x44` callback 做一次全局 clip/prepare：
  大致范围是 `0,0,backend+0x0c-1,backend+0x10-1`。
- `GUI+0x400` 随后把同样的 `x, y, height, width, buffer` 转发给 backend
  `+0x80` callback。
- `名片.bda` 会用 `GUI+0x3fc(0,0,0xf0,0xc6)` 和
  `GUI+0x3fc(0,0x122,0xf0,0x140)` 暂存两块 screen region，稍后用
  `GUI+0x400` restore，并用 `MEM+0x00c` 释放返回 buffer。

开发建议：

- SDK 暴露 `bda_gui_blit_like(x, y, height, width, buffer)` 和
  `bda_gui_blit_alt_like(x, y, height, width, buffer)`，保留 height 在 width 前。
- SDK 暴露 `bda_gui_capture_region_alloc_like(x, y, width, height)`，按 C200 的
  capture 参数顺序固定为 width/height。返回 pointer 用完必须 `bda_free()`。
- 这些入口都是 low-level framebuffer/backend API，不会自己建立 frame、draw context、
  game surface 或 present 生命周期。普通 UI 优先使用 frame/control 绘制路径。
- tile 游戏不要在每个 tile 后调用 `GUI+0x074(0)` 或
  `bda_gui_draw_guard_end_like()`；旧扫雷真机反馈显示这会逐块 present/flip，最终可能
  白屏或死机。`TileBlit` 后续真机结果又确认：即使只在循环外统一 present，缺少原机
  game surface/context 时仍会逐块 flip 并死机。
- 原机雷霆战机/决战坦克会批量 blit dirty region 后统一 present/update，但 SDK
  目前还没复刻出创建有效 game surface/context 的前置 lifecycle；不要把
  `GUI+0x074/+0x400` 直接当作可玩 tile 游戏框架。
- 两款游戏的全屏 buffer 链路同构：`GUI+0x3f8` 后接 `GUI+0x6e0` game/display
  state pump，再按返回路径走 `GUI+0x400`，最后用 `MEM+0x00c` 释放临时 buffer。
  这说明 blit wrapper 只是小游戏 shell 状态机的一段。
- `buffer` 通常按 RGB565 像素数据处理，但 pitch、裁剪和目标 surface 仍由 backend
  当前状态决定，不要把它当作独立的跨设备图片绘制 API。

### GUI +0x40c: `BDA_GUI_REGION_DRAW_LIKE`

system function VA：`0x800b2e30`

当前证据：

- entry 保存 `a0=context`、`a1=x`、`a2=y`、`a3=width`，并从调用者
  `stack+0x10` 读取第五参数 `height`。
- `context == 0` 时使用默认 context `0x80825690`；如果传入对象的类型 word
  是 `0x82`，会先走内部 helper `0x800bc9e4(context, 0)`。
- 函数先构造 `x/y/x+width/y+height` 矩形；非默认 context 会叠加
  `context+0x40/+0x44` 的 origin，并按 `context+0x70` 相关缩放字段换算坐标。
- 随后调用 `0x800c04d8(rect)` 和 `0x800c056c(rect, rect, context+0xb0)` 做区域规范化
  与 clipping；clip 后宽高为 `rect[2]-rect[0]` 和 `rect[3]-rect[1]`。
- 命中子区域时会用 backend `+0x44` callback 准备源区域，再调用 backend `+0x7c`
  callback 提交 `surface, x, y, clipped_width, clipped_height` 类参数。
- 如果当前 backend 提供 `+0x58` callback，还会在子区域遍历前后调用它做状态切换。

开发建议：

- SDK 暴露 `bda_gui_region_draw_like(context, x, y, width, height)`；旧 4 参数形状少传
  `height`，与 C200 ABI 不符。
- 该入口仍依赖真实 draw context、surface 和 backend 状态。普通 demo 不应把它当作
  独立 fill-rect API；复刻电子画板或原机游戏绘制路径时才使用。

### GUI +0x410 / +0x414 / +0x418: render/copy helper 簇

system function VA：

```text
GUI+0x410 -> 0x800b3124
GUI+0x414 -> 0x800b34c0
GUI+0x418 -> 0x800b3d90
```

当前证据：

- `GUI+0x410` 是六参数 render/copy helper。它保存 `a0=context`、`a1=x`、
  `a2=y`、`a3=width`，读取调用者 `stack+0x10=height` 和
  `stack+0x14=descriptor`。
- `GUI+0x410` 会读取 descriptor 的 `+0x04/+0x08/+0x14/+0x18` 字段；
  `+0x04/+0x08` 像源宽高，`+0x14` 常作为 source buffer 或 bitmap pointer，
  `+0x18` 影响选择 backend `+0x88` 还是 `+0x80` callback。
- `GUI+0x410` 会按 context origin、缩放字段和 `context+0xb0` clipping 状态裁剪
  目标矩形；裁剪后宽度不等于 descriptor 宽度时，会通过 `MEM_ALLOC` 申请临时
  buffer，并在结束路径释放。
- 命中子区域时，`GUI+0x410` 先调用 backend `+0x44` 准备区域，然后根据
  descriptor 字段调用 backend `+0x88` 或 `+0x80` 提交。
- `GUI+0x414` 是多参数 render helper。它保存 `a0=context`、`a1=x`、`a2=y`、
  `a3=width_or_x2_like`，并读取调用者 `stack+0x10/+0x14/+0x18/+0x1c/+0x20/+0x24`
  一组参数。
- `GUI+0x414` 会读取 `stack+0x1c` 指向的 descriptor，并使用其中
  `+0x04/+0x08/+0x14/+0x18` 字段；`+0x14` 常作为 source buffer 或 bitmap
  pointer 使用。
- `GUI+0x414` 的 C200 切片显示，entry 会把 `descriptor+0x04/+0x08` 读到
  local `sp+0x34/+0x38`，并把调用者 `stack+0x14/+0x18` 作为裁剪后
  width/height gate；全局 draw backend `0x80474030+0x1c` 的返回值会参与临时
  buffer size 计算。
- `GUI+0x414` 的 `a0=0` 会回退到 default context `0x80825690`；context
  类型 word `+0x04 == 0x82` 时会进入特殊 object/context 路径。
- `GUI+0x414` 会按 context origin、缩放字段和 `context+0xb0` clipping 状态裁剪
  矩形；必要时通过 `MEM_ALLOC` 申请临时 buffer，按行 `memcpy` 裁剪后的区域。
- `GUI+0x414` 会调用全局 draw backend `0x80474030` 的 `+0x80/+0x88/+0x8c`
  callback，具体路径取决于 descriptor 字段和裁剪结果；结束路径会释放临时
  buffer。
- `GUI+0x418` 是多参数 context copy helper。V14/V15 真机 ABI 结果、V6/V8/V19-V21
  模拟器结果结合 C200
  控制流确认 `a0=source_context`、`a1/a2=source_x/y`、`a3=width`，调用者
  `stack+0x10=height`、`stack+0x14=destination_context`、
  `stack+0x18/+0x1c=destination_x/y`，`stack+0x20` 是 RGB565
  `color_key_or_zero`。
- 具体 stack slot 已能从 C200 固定：`stack+0x10` 参与第一矩形的
  `y+height_or_y2`，`stack+0x14` 作为第二个 context，即 `context_b`；`stack+0x18/+0x1c`
  作为第二矩形 origin，`stack+0x20` 会原样转发给 backend `+0x94`。
- `GUI+0x418` 的 C200 切片会把 `a0` 和 `stack+0x14` 分别归一化为两个
  context；二者为 0 时都退回 default context `0x80825690`，并且类型 word
  `+0x04 == 0x82` 会进入特殊 context 处理路径。
- `GUI+0x418` 会分别按两个 context 的 origin/缩放字段换算坐标，构造 clipping
  rect。可见 destination 会遍历 `context_b+0xc0` 子区域链；compatible destination
  还能走 backend 的直接 surface 路径。
- 命中子区域时，`GUI+0x418` 会先调用 backend `+0x44` 准备区域，再调用 backend
  `+0x94` 提交一次 source/destination 矩形复制，并把 color key 原样放在
  backend 调用的 `stack+0x20`。
- V19 同时创建 back 和 sprite 两块 `GUI+0x310` compatible context。每帧先用
  `GUI+0x540` 分别写背景和 32x32 精灵，再执行
  `GUI+0x418(sprite, ..., back, sprite_x, 16, 0)`；随后只把
  `GUI+0x418(back, ..., visible, 16, 90, 0)` 包在 `GUI+0x074(1/0)` 中。
- 两张采样画面中精灵位置和颜色均变化，旧位置的网格没有残影；连续 116616 帧后
  两块 compatible context 均经 `GUI+0x314` 释放，`FAILURES=0`、模拟器
  `invalid=0`。这动态确认 compatible context 可以作为 `+0x418` 的 destination。
- 雷霆战机 `0x81c10db8` 把 `s5=0xf81f`，并在 visible→temp 和 temp→visible 两个
  `GUI+0x418` 调用前写到 `stack+0x20`。决战坦克同时存在参数 0 和显式
  `0xf81f` 的复制分支，说明该参数不是固定保留 word。
- V19 使用末参数 0，32x32 深色背景被不透明复制。V20 把 sprite surface 未命中
  图案的像素填为 RGB565 洋红 `0xf81f`，并仅在 sprite→back 时传同一 color key；
  画面只保留图案，底层网格完整穿透洋红区域。两张采样帧中透明精灵移动并换色，
  无旧位置残影，连续 4448 帧后正常释放两块 context，模拟器 `invalid=0`。
- V21 同时保留 clean、back、sprite 三块 compatible context。首帧完整 present 后，
  每帧先用 `GUI+0x418(clean -> back)` 恢复旧 32x32 区域，再色键合成新精灵，
  最后只把新旧位置的最小外接 dirty rect 从 back 复制到 visible。第一次移动
  `old_x=0,new_x=1` 时日志为 `DIRTY WIDTH=0x21`，三次 copy 均返回 0；两张采样帧
  网格无残影，连续 20862 帧后 clean/back/sprite 均释放，模拟器 `invalid=0`。
- 当前可把 0 解释为禁用 color key，非零值解释为要跳过的 RGB565 source color。
  alpha blending 和多个透明键仍未验证；V19-V21 还需要真机复测。

开发建议：

- 公开 SDK 为 `GUI+0x418` 提供九参数 `bda_gui_context_copy()`，末参数命名为
  `color_key_rgb565`，并提供 `BDA_GUI_COLOR_KEY_NONE` 和
  `BDA_GUI_COLOR_KEY_MAGENTA_RGB565`。研究 header 继续保留 `_like` 名供 probe
  使用；`GUI+0x410/+0x414` 仍只暴露 low-level 候选。旧文档里的 “finish” 只是
  早期行为猜测，不应理解成无参数提交/flush。
- 这两个入口适合复刻相册、电子画板、小游戏的完整 render pipeline；不要在普通
  no-template demo 中直接调用。
- 若必须探测，应复用原机调用点的 descriptor、source buffer、draw context 和 stack
  参数布局，并先确认 `GUI+0x35c/+0x40c/+0x314` 的生命周期。

### GUI +0x368 / +0x36c: 单像素绘制

system function VA：

```text
GUI+0x368 -> 0x800b68c0
GUI+0x36c -> 0x800b6af8
```

当前证据：

- entry 保存 `a0=context`、`a1=x`、`a2=y`、`a3=color`。
- `context == 0` 时使用默认 context `0x80825690`；如果传入对象的类型 word
  是 `0x82`，会先走内部 helper `0x800bc9e4(context, 0)`。
- 非默认 context 会叠加 `context+0x40/+0x44` 的 origin；如果 `context+0x70`
  置位，还会按 `context+0x74..+0x90` 一组缩放字段换算坐标。
- 函数构造 `x-1/y-1/x+1/y+1` 的小矩形，并用 `0x800c056c(rect, rect, context+0xb0)`
  做 clipping；clip 失败时直接返回。
- 遍历 `context+0xc0` 子区域链时，会调用 `GUI+0x46c` 对应的 `0x800c0818`
  判断点是否落在子区域中。
- 命中子区域后，先用 backend `+0x44` callback 准备该子区域，再调用 backend
  `+0xb0(surface, x, y, color)` 提交像素。
- 如果当前 backend 提供 `+0x58` callback，会在子区域遍历前后用它切换绘制状态。

开发建议：

- SDK 暴露 `bda_gui_put_pixel_like(context, x, y, color)`。旧注释把第一个参数写成
  surface、把颜色写成固定 RGB565 都过窄；C200 走的是 draw context 和 backend
  当前颜色格式。
- 通常先用 `bda_gui_rgb_like(context, r, g, b)` 得到内部颜色值，再传给 put pixel。
- `GUI+0x36c` 是直接 RGB 版本，参数为 `context,x,y,r,g,b`。entry 从
  caller `stack+0x10/+0x14` 读取 `g/b`，把三个分量截断到低 8 位，通过 backend
  `+0x5c` 转成内部颜色，再走和 `+0x368` 相同的 `+0xb0` 单像素提交。
- SDK 暴露 `bda_gui_put_pixel_rgb_like(context, x, y, r, g, b)`；wrapper 使用
  `bda_call6` 保证第五、第六参数位于正确的 o32 stack slot。
- 独立 `GraphicsPrimitives.bda` 已动态验证两种路径：青色块使用
  `GUI+0x378 -> GUI+0x368`，橙色块使用 `GUI+0x36c`，均得到可见彩色输出。
- 该入口适合复刻电子画板一类逐点绘制路径；普通 UI 不应在没有 draw context
  生命周期时直接调用。

### GUI +0x384 / +0x3ec / +0x3f0 / +0x3f4: 折线与 clip 查询

system function VA：

```text
GUI+0x384 -> 0x800bc340
GUI+0x3ec -> 0x800b64f0
GUI+0x3f0 -> 0x800b6520
GUI+0x3f4 -> 0x800b65ac
```

静态证据：

- `GUI+0x384` 使用 `a0=context,a1=point_array,a2=count`。首个点的两个 word
  写入 `context+0x34/+0x38`，从第二个点开始按 8 byte 步长调用内部
  `0x800b715c`，即 `GUI+0x37c` 的 line-to 实现。
- `GUI+0x3ec` 使用 `context,out_rect`，把 `context+0x94/+0x98/+0x9c/+0xa0`
  原样复制到四 word rect；函数没有稳定 return value。
- `GUI+0x3f0` 使用 `context,point`。context 有 clip-region 链时逐节点调用
  `0x800c0818(region,x,y)`，否则对 `context+0x40` 的 fallback bounds 调同一 helper。
- `GUI+0x3f4` 使用 `context,rect`，按相同分支调用 `0x800c05e0` 做矩形相交测试。

动态结果：

- `GamePolylineClipProbeV10` 在 8013 专用 NAND 上画出连续锯齿和闭合菱形交叉线。
- draw context 的 clip bounds 返回 `(0,0,240,320)`；屏内点/矩形返回 `1`，屏外
  点/矩形返回 `0`。
- ESC 完成既有窗口退出闭环，最终 `FAILURES=0`、`RESULT=PASS` 并回到主菜单。

开发建议：

- 研究层使用 `bda_point_like_t`（struct tag 为 `bda_point_like`，字段为两个 signed
  word `x/y`）描述点数组，并提供 `bda_gui_polyline_like()`、
  `bda_gui_clip_bounds_like()`、`bda_gui_clip_contains_point_like()` 和
  `bda_gui_clip_intersects_rect_like()`。
- polyline 不会自动闭合，也不填充；闭合时应在数组末尾重复首点。
- 这三个 clip 入口都不修改 region。clip region 的创建、合并和释放 ABI 尚未闭环，
  不要据此自行构造 `GUI+0x3e8` 的内部链表参数。
- 当前只有模拟器动态结果，真机验证前不进入公开 SDK 或 `docs/verified/`。

### GUI +0x390: 椭圆轮廓/填充

system function VA：`0x800b7fa0`

已确认的调用子集：

```text
a0 = draw context
a1 = center_x
a2 = center_y
a3 = radius_x
stack+0x10 = radius_y
stack+0x14 = 0
stack+0x18 = 0
stack+0x1c = filled (0/1)
```

静态证据：

- 函数用 `center_x +/- radius_x`、`center_y +/- radius_y` 构造 bounding rect 并走
  current context clipping/origin/scale 处理。
- `电子画板.bda` 在 file `+0x124c8` 取 `GUI+0x390`，调用时后三个 stack word
  全部为 0，对应 outline 模式。
- C200 的 `0x800bb23c` 调用同一 core 时把两个中间 stack word 置 0、末项置 1。
- 末项非 0 时调用 backend `+0xcc`，为 0 时调用 backend `+0xc8`；两条路径都把
  selected draw object 作为后续 stack 参数传入。

动态结果：

- `GameEllipseProbeV11` 对 object 7/8 分别执行 `filled=0` 和 `filled=1`，左列得到
  空心轮廓，右列得到实心椭圆。
- object 7/8 的填充中心像素约为 RGB `(131,129,131)` / `(197,194,197)`，说明
  selected draw object/backend 参与颜色选择；`GUI+0x334` 写入的 cyan 没有直接成为
  椭圆填充色。
- ESC 退出后最终 `FAILURES=0`、`RESULT=PASS`，并回到主菜单。

开发建议：

- 研究层提供 `bda_gui_ellipse_like(context,center_x,center_y,radius_x,radius_y,filled)`。
- wrapper 把两个仍未完整命名的参数固定为 0，与全部已知调用保持一致；不要自行暴露
  任意值版本。
- `filled` 只决定轮廓/实心路径，颜色由 selected draw object/backend 决定；不要把
  `bda_gui_set_fill_color_like()` 当作该图元的颜色 setter。
- 当前为模拟器动态验证，真机确认前不进入公开 SDK。

### GUI +0x394 / +0x398: 圆弧与圆角矩形

system function VA：

```text
GUI+0x394 -> 0x800ba660
GUI+0x398 -> 0x800ba8dc
```

`GUI+0x394` 参数：

```text
a0 = context
a1 = center_x
a2 = center_y
a3 = start_degrees
stack+0x10 = end_degrees
stack+0x14 = radius
```

函数按 `center +/- radius` 建立裁剪矩形，经过 context origin/scale/clip 后，把
start/end/radius 和 selected draw object 传给 backend `+0xd0`。V12 动态结果确认
`0→180` 画上半圆、`180→360` 画下半圆。

`GUI+0x398` 参数：

```text
a0 = context
a1 = center_x
a2 = center_y
a3 = width
stack+0x10 = height
stack+0x14 = corner_radius_x
stack+0x18 = corner_radius_y
stack+0x1c = filled
```

静态证据：

- width/height 分别按带符号除 2，围绕 center 形成 left/right/top/bottom。
- corner x/y 半径从外框半径中扣除，用于生成四角和中间直边。
- `filled != 0` 进入实心 scan/segment 路径；`filled == 0` 进入轮廓路径。
- 当尺寸退化为圆角覆盖整个外框时，`0x800bb23c` 会调用 `GUI+0x390` core，
  两个保留参数为 0、filled 为 1。这是其圆角矩形语义的直接内部证据。

动态结果：

- V12 的左下图元为圆角矩形轮廓，右下图元为同尺寸实心圆角矩形。
- 两个圆弧和两个圆角矩形绘制后，ESC 退出最终 `RESULT=PASS` 并回到主菜单。

开发建议：

- 研究层提供 `bda_gui_arc_like(context,cx,cy,start_degrees,end_degrees,radius)`。
- 研究层提供 `bda_gui_round_rect_like(context,cx,cy,width,height,corner_rx,corner_ry,filled)`；
  坐标是中心，不是左上角。
- 当前合同只覆盖非负 width/height/radius，且 corner 半径不超过对应半尺寸。不要依赖
  负值、过大圆角或跨多圈角度的行为。
- 实心颜色仍来自 selected draw object/backend，不要把 `GUI+0x334` 当作通用填充色 API。
- 当前为模拟器验证，真机确认前不进入公开 SDK。

### GUI +0x3a0..+0x3c4: 逻辑坐标映射状态

system function VA：

```text
GUI+0x3a0 -> 0x800bfa40  map mode getter
GUI+0x3a4 -> 0x800bfa54  viewport extent getter
GUI+0x3a8 -> 0x800bfa74  viewport origin getter
GUI+0x3ac -> 0x800bfa94  window extent getter
GUI+0x3b0 -> 0x800bfab4  window origin getter
GUI+0x3b4 -> 0x800bfad4  map mode setter
GUI+0x3b8 -> 0x800bfae8  viewport extent setter
GUI+0x3bc -> 0x800bfb08  viewport origin setter
GUI+0x3c0 -> 0x800bfb28  window extent setter
GUI+0x3c4 -> 0x800bfb48  window origin setter
```

字段映射：

```text
context+0x70       map mode enabled
context+0x74/+0x78 viewport origin x/y
context+0x7c/+0x80 viewport extent x/y
context+0x84/+0x88 window origin x/y
context+0x8c/+0x90 window extent x/y
```

map mode 非 0 时，`GUI+0x368` 等图元中可直接观察到以下转换：

```text
device = context_origin
       + (logical - window_origin) * viewport_extent / window_extent
       + viewport_origin
```

静态边界：

- 五个 getter 在 `context==0` 时读取默认 context `0x80825690`。
- 五个 setter 在 `context==0` 时不写任何状态；pair setter 从 `a1` 读取两个 word。
- window extent 是有符号除法的除数；映射开启时任何一个分量为 0 都会触发 MIPS
  divide-by-zero break，调用者必须先设置非零 extent。

动态结果：

- V13 初始状态为 mode 0、两组 extent `(1,1)`、两组 origin `(0,0)`。
- 设置 viewport extent `(2,2)` 和 origin `(30,80)` 后，逻辑 `70×30` 图元变为
  device `140×60`，左上位置为 `(30,80)`；四组 getter 回读与写入值完全一致。
- probe 按 `disable mode -> restore pairs -> restore old mode` 顺序恢复状态，ESC 退出后
  最终 `RESULT=PASS`，主菜单正常。

研究层 wrapper：

```c
int bda_gui_map_mode_get_like(bda_handle_t context);
void bda_gui_viewport_extent_get_like(bda_handle_t context, bda_point_like_t *extent);
void bda_gui_viewport_origin_get_like(bda_handle_t context, bda_point_like_t *origin);
void bda_gui_window_extent_get_like(bda_handle_t context, bda_point_like_t *extent);
void bda_gui_window_origin_get_like(bda_handle_t context, bda_point_like_t *origin);
void bda_gui_map_mode_set_like(bda_handle_t context, int enabled);
void bda_gui_viewport_extent_set_like(bda_handle_t context, const bda_point_like_t *extent);
void bda_gui_viewport_origin_set_like(bda_handle_t context, const bda_point_like_t *origin);
void bda_gui_window_extent_set_like(bda_handle_t context, const bda_point_like_t *extent);
void bda_gui_window_origin_set_like(bda_handle_t context, const bda_point_like_t *origin);
```

这些 API 当前仍属于研究层。游戏如需临时启用映射，应保存并完整恢复五组状态，不能只把
mode 清零后遗留修改过的 origin/extent。

### GUI +0x3c8..+0x3d4: point 坐标转换

system function VA：

```text
GUI+0x3c8 -> 0x800b6640  full device-to-logical point
GUI+0x3cc -> 0x800b66e8  full logical-to-device point
GUI+0x3d0 -> 0x800b6834  map-only device-to-logical point
GUI+0x3d4 -> 0x800b67b0  map-only logical-to-device point
```

四个入口都使用 `context,point*`，直接改写两个 signed word。区别不是 point/rect，
而是是否包含 draw context 自身的 `context+0x40/+0x44` origin：

```text
+0x3cc full L2D:
device = context_origin
       + (logical - window_origin) * viewport_extent / window_extent
       + viewport_origin

+0x3c8 full D2L:
logical = (device - context_origin - viewport_origin)
        * window_extent / viewport_extent
        + window_origin

+0x3d4 map-only L2D:
mapped = (logical - window_origin) * viewport_extent / window_extent
       + viewport_origin

+0x3d0 map-only D2L:
logical = (mapped - viewport_origin) * window_extent / viewport_extent
        + window_origin
```

map mode 为 0 时，map-only pair 不修改 point；full pair 仍会加减 context origin。
map mode 非 0 时两组公式都有有符号除法，因此对应 extent 分量必须非零。

V14 设置 viewport extent `(3,2)`、viewport origin `(20,40)`、window extent `(2,1)`、
window origin `(5,7)`。map-only L2D 把 `(25,27)` 转成 `(50,80)`，逆转换回
`(25,27)`；当前 frame 的 context origin 为零，因此 full pair 得到相同结果并完成
round-trip。逻辑坐标绘制的十字/圆和关闭映射后的物理参考框重合，ESC 退出后
`FAILURES=0`、`RESULT=PASS`，主菜单正常。

研究层 wrapper：

```c
void bda_gui_device_to_logical_point_like(bda_handle_t context, bda_point_like_t *point);
void bda_gui_logical_to_device_point_like(bda_handle_t context, bda_point_like_t *point);
void bda_gui_map_device_to_logical_point_like(bda_handle_t context, bda_point_like_t *point);
void bda_gui_map_logical_to_device_point_like(bda_handle_t context, bda_point_like_t *point);
```

### GUI +0x3d8: exclude clip rect

system function VA：`0x800b5e54`

ABI 为 `context,left,top,right,bottom`；第五参数从 `stack+0x10` 读取。入口先用
`0x800c0410/0x800c04d8/0x800c0464` 构造、规范化并检查矩形；空矩形直接返回。
有效矩形分别作用于 `context+0x94` 逻辑 region 和坐标变换后的 `context+0xb0`
backend region，无稳定 return value。

核心 helper `0x800d2fe4(region,rect)` 的行为已经恢复：

1. 遍历 region 的矩形节点并计算与排除矩形的交集。
2. 不相交节点保持不变。
3. 相交节点按需要生成 top、bottom、left、right 最多四个剩余矩形。
4. 原节点完全落入排除矩形时删除节点。
5. 最后重新计算 region aggregate bounds。

这证明该入口是矩形差集，而不是 intersect。V16 先用 `+0x3e4` 选择
`(30,70)-(210,230)`，再排除中央 `(85,110)-(155,190)`：四周点命中为 1，hole
中心和 hole 内矩形为 0，跨越 hole 左边界的矩形仍为 1。实际线网形成四周条带和
中央空洞。

排除内部 hole 后，`+0x3ec` 仍返回外层 `(30,70)-(210,230)` aggregate bounds；
因此 bounds 不能表达 region 内部空洞，必须使用 `+0x3f0/+0x3f4` 或实际绘图判断。
调用已验证的 `+0x3e4(context,NULL)` 后，hole 中心重新可命中和绘制。最终
`FAILURES=0`、`RESULT=PASS`，ESC 正常返回主菜单，模拟器 `invalid=0`。

研究层 wrapper：

```c
void bda_gui_clip_exclude_rect_like(
    bda_handle_t context,
    s32 left,
    s32 top,
    s32 right,
    s32 bottom
);
```

### GUI +0x3dc: union clip rect

system function VA：`0x800b6040`

ABI 同样为 `context,left,top,right,bottom`，第五参数来自 `stack+0x10`，无稳定
return value。逻辑 region 的核心顺序是：

```text
0x800d2fe4(region, new_rect)  从旧节点扣除与 new_rect 重叠的部分
0x800d3530(region, new_rect)  把 new_rect 作为新节点追加到链表
```

这样可以得到不重叠矩形节点组成的并集。V17 先选择左块 `(30,80)-(95,225)`，
再追加右块 `(145,80)-(210,225)`：左右点均命中，中间 gap 点和 gap 内矩形不命中，
跨越两块和 gap 的矩形命中。实际线网只显示在左右两块区域内。

`0x800d3530` 只链接新节点，不扩展 region header 中的 cached bounds。因此 V17 中
`+0x3ec` 仍返回旧左块 `(30,80)-(95,225)`，即使右块查询和绘图已经有效。对
`+0x3dc` 产生的多节点 region，不能把 `+0x3ec` 当作完整并集外接框；使用
`+0x3f0/+0x3f4` 判断 effective clip。

调用 `+0x3e4(context,NULL)` 后 gap 中心重新可命中和绘制。最终 `FAILURES=0`、
`RESULT=PASS`，ESC 正常返回主菜单，模拟器 `invalid=0`。

研究层 wrapper：

```c
void bda_gui_clip_union_rect_like(
    bda_handle_t context,
    s32 left,
    s32 top,
    s32 right,
    s32 bottom
);
```

### GUI +0x3e0: intersect clip rect

system function VA：`0x800b6260`

ABI 为 `context,const rect*`，无稳定 return value。入口先规范化输入矩形，再执行：

```text
0x800d35f0(context+0x94, intersect_rect)  逐节点求交并清理空节点
map logical rect to backend coordinates
0x800d35f0(context+0xb0, mapped_rect)     同步 backend region
```

`0x800d35f0` 会在节点处理完成后重新计算 region header 的 aggregate bounds；这与
`+0x3dc` 仅追加节点、不扩展 cached bounds 的行为不同。

V18 先建立左右两个分离节点 `(25,70)-(100,230)` 和 `(140,70)-(215,230)`，再与
`(50,110)-(190,190)` 求交。结果保留 `(50,110)-(100,190)` 和
`(140,110)-(190,190)` 两个裁剪岛，`+0x3ec` 返回重新计算后的整体边界
`(50,110)-(190,190)`。左右点命中，中间 gap、被上边界裁掉的点和 gap 内矩形均
不命中；跨越两个裁剪岛的矩形命中，实际绘图也只出现在左右两个岛内。

调用 `+0x3e4(context,NULL)` 后，`+0x3ec` 回到零矩形哨兵，gap 中心重新可命中和
绘制。最终 `FAILURES=0`、`RESULT=PASS`，ESC 正常返回主菜单，模拟器 `invalid=0`。

研究层 wrapper：

```c
void bda_gui_clip_intersect_rect_like(
    bda_handle_t context,
    const bda_rect_like_t *rect
);
```

### GUI +0x3e4: 矩形 clip select/reset

system function VA：`0x800b5c00`

ABI 为 `context,const rect*`，无稳定 return value：

- `rect != NULL` 时复制并规范化四个 signed word，重建 `context+0x94` 的逻辑
  clip region；完成坐标变换后同步重建 `context+0xb0` 的 backend region。
- `rect == NULL` 时清空自定义 region。后续 hit test 和绘图回退到 context 的完整
  drawable bounds。
- `context==0` 时使用 firmware default draw context；研究 probe 仍只在有效 object-draw
  scope 中调用，避免污染全局默认状态。

V15 选择 `(45,75)-(195,225)` 后，`+0x3ec` 回读完全一致；内部点/矩形返回 1，
外部点/矩形返回 0，跨边界矩形返回 1。横线和两条对角线只显示在该矩形内。

调用 `+0x3e4(context,NULL)` 后有一个必须单独记录的行为：

```text
+0x3ec clip bounds = (0,0,0,0)
+0x3f0 outside point = 1
+0x3f4 outside rect = 1
```

零矩形是“无自定义 region”的哨兵，不表示有效裁剪为空。左侧 `(20,150)` 十字能在
reset 后正常绘制，也证明 backend 已回退到完整 context bounds。probe 最终
`FAILURES=0`、`RESULT=PASS`，ESC 正常返回主菜单，模拟器 `invalid=0`。

研究层 wrapper：

```c
void bda_gui_clip_select_rect_like(
    bda_handle_t context,
    const bda_rect_like_t *rect_or_null
);
```

修改裁剪后必须在结束 draw scope 前传 `NULL` 恢复。`GUI+0x3d8/+0x3dc/+0x3e0`
现在都已用该恢复闭环完成独立模拟器验证；真机验证前仍保留在研究层 API。

### GUI +0x074: `BDA_GUI_PUMP_PRESENT_LIKE`

system function VA：`0x800d48a8`

当前证据：

- entry 会把 `a0` 写入全局 `0x80474040`。
- `a0 != 0` 时直接返回；原机常在绘图前传 `1`。
- `a0 == 0` 时，如果内部 present/update 对象存在，会以全零参数调用
  `0x8012c8f0`，随后返回；原机常在绘图后传 `0`。
- 记事本和电子图书都呈现 `GUI+0x308/0x304 -> GUI+0x074(1) -> 绘制 ->
  GUI+0x074(0) -> GUI+0x30c` 的生命周期。

开发建议：

- 不要使用无参数调用；C200 明确读取 `a0`。
- SDK 提供 `bda_gui_draw_guard_begin_like()` 和
  `bda_gui_draw_guard_end_like()`，分别对应原机常见的 `GUI+0x074(1/0)`。
- `draw_guard_end_like()` 是配对 guard 的 present/update 边界，不是 tile-level flip API，
  也不是独立 present。TouchStageV22 真机确认只调用 `GUI+0x074(0)` 即使返回 `0`
  也不会显示动态图元；TouchStageV23 则确认完整 `1 -> draw -> 0` 可以无闪烁更新。
  不要把 end 放在
  方块/像素循环内部。`TileBlit` 真机反馈显示，循环外只调用一次也不能弥补缺失的
  game surface/context 生命周期。
- 雷霆战机/决战坦克的 object render 链路显示，`GUI+0x074(0)` 通常接在
  `GUI+0x414 render helper -> GUI+0x0e8 object draw end` 之后；它依赖已建立的
  object/draw context，不是裸 BDA 的刷新按钮。
- 需要保留原始形态时使用 `bda_gui_pump_present_arg_like(draw_guard_enabled)`。

### GUI +0x6a8: `BDA_GUI_FILE_SELECTOR_OPEN_LIKE`

system function VA：`0x80021334`

当前证据：

- entry 只读取 `a0=mode/session`，先调用 `0x8001f344(sp+0x10)` 准备内部
  selector 状态。
- `mode` 会写入全局 `0x80473fe4`；当前看到 `mode 0/1/2/3` 分别从内部
  状态区的不同 byte 读取启用/选择状态。
- 状态 byte 为 0 时不会打开 modal frame，直接按路径返回。
- 打开路径在 stack 上构造内部 frame descriptor：style 为 `0x08000000`，
  wndproc 为 `0x80020918`，并通过 `0x800bd36c(15)` 创建内部 object。
- 随后通过 `0x800cc1c8` 注册 frame，进入
  `0x800dbfd0` / `0x800de378` / `0x800dd4b8` 组成的 modal event loop，
  结束后调用 `0x800cdffc` 关闭 frame。
- return value 依赖 `mode` 路径和全局 selector 状态，不是简单 success boolean。

开发建议：

- SDK 暴露 `bda_gui_file_selector_open_like(mode)`，不要把 selector descriptor
  pointer 传给 open。
- `bda_file_selector_init_like()` 只负责复刻 GAMEBOY 风格的 selector 描述符初始化；
  随后的 `GUI+0x6c8` 必须显式传入该 descriptor。
- selector descriptor 中 `selected_index/sentinel20/sentinel24/sentinel34/sentinel38/sentinel48`
  按 GAMEBOY 风格初始化为 `-1`，`list_limit40` 初始化为 `0x1000`，
  `result64` 初始化为 `0`；不要把这些字段当作无用 padding 删除。
- `mode` 的语义还未完整命名，开发代码应优先沿用原机 GAMEBOY 路径。

### GUI +0x6b8 / +0x6bc / +0x6c8: 文件选择器相邻 helper

system function VA：

```text
GUI+0x6b8 -> 0x80042ed8
GUI+0x6bc -> 0x80042ebc
GUI+0x6c8 -> 0x80042fec
```

当前证据：

- `GUI+0x6b8` 开头检查 `a1 <= 0` 和 `a0 == NULL`，随后沿 `*(a0+4)` 链表 pointer
  迭代，返回第 `a1` 项或 `NULL`。它不是无参数“获取文件选择结果”函数。
- `GUI+0x6bc` 表 entry 没有设置参数，直接调用 `0x8003e868`。该 helper 读取
  `a0=head`，沿每个节点的 `+0x04` next pointer 遍历，先释放 `node+0x00`
  data pointer，再释放 node 本身。`head == NULL` 是 no-op。
- `GUI+0x6c8` 表 entry 没有改写 `a0`，而是把调用者传入的 descriptor pointer
  原样交给 `0x80040848`。该内部函数在 `0x80040864` 保存 `a0`，随后读取
  descriptor 的 path/filter/title/status/flags 字段。
- `GAMEBOY.BDA` 的 `0x81c0fc7c` 调用点在 `jalr` delay slot 显式执行
  `move a0,s2`，其中 `s2=sp+0x610` 是 descriptor。
- 早期 SDK 对 `GUI+0x6b8/+0x6bc` 的无参数 `get()/close()` 命名错误；二者实际
  分别接收 `head,index` 和 `head`。

开发建议：

- 研究 SDK 暴露 `bda_gui_file_selector_update_like(&descriptor)`；公开 SDK 使用
  `bda_gui_select_file()` 封装整个模态生命周期。
- `GUI+0x6b8` 改名为 low-level `bda_gui_list_nth_like(head, index)`。
- `GUI+0x6bc` 改名为 low-level `bda_gui_list_free_like(head)`；不要再调用旧的
  no-arg file selector close wrapper。
- modal 返回后 descriptor `+0x10` 是 list head，`+0x1c` 是 selected index；
  `GUI+0x6b8` 返回节点的首 word 指向文件名。当前目录仍在 descriptor `+0x00`
  path buffer 中，公开 wrapper 在释放 list 前拼成完整路径。

### GUI +0x35c: `BDA_GUI_OBJECT_BIND_LIKE`

system function VA：`0x800b2d58`

当前证据：

- entry 只读取 `a0=context` 和 `a1=value`。
- `context == 0` 时使用默认 draw context `0x80825690`；否则使用调用者传入的
  context。
- 函数先读取并返回旧的 `context+0x20`，然后把 `value` 写入 `context+0x20`。
- 它不创建 object，也不接管 resource/image 生命周期；更像当前
  bitmap/resource slot setter。
- C200 附近还有同形态 getter/setter：`0x800b2d18/+0x2c`、
  `0x800b2d2c/+0x1c`、`0x800b2d40/+0x30`、`0x800b2d70/+0x2c`、
  `0x800b2d88/+0x1c`、`0x800b2db4/+0x64` 等，说明这一段是 draw context
  状态字段访问器簇。

开发建议：

- SDK 仍保留历史名称 `bda_gui_object_bind_like(context, value)`，但注释中按
  setter 语义解释。
- 画板、相册和小游戏常在 `GUI+0x40c/+0x418/+0x314` 前调用它，`value` 可能是
  color、bitmap 或 resource-like handle，具体取决于当前 draw pipeline。
- 它不是 object 生命周期绑定 API；不要把它当作通用 object/resource 生命周期绑定
  入口。传入值必须来自已确认的
  draw context 或原机同路径资源。

### GUI +0x0a4: `BDA_GUI_OBJECT_RECT_LIKE`

system function VA：`0x800ce3c8`

当前证据：

- 参数为 `a0=handle`、`a1=rect`，只使用两个参数。
- `rect` 至少需要 16 byte 可写内存，布局同 `bda_rect_like_t`：
  `x0,y0,x1,y1`。
- `handle == 0` 时，函数从 firmware global `0x80825830..0x8082583c`
  复制四个 word 到 `rect`，返回 `1`。
- `handle != 0` 且 `*(s16 *)handle == 1` 时，函数写：
  `rect->x0 = 0`、`rect->y0 = 0`、
  `rect->x1 = handle+0x1c - handle+0x14`、
  `rect->y1 = handle+0x20 - handle+0x18`，返回 `1`。
- `handle` 非空但不是 kind `1` 时不写有效 rect，返回 `0`。
- `黄冈教辅.bda`、`听力测试.bda`、`英语百科.bda` 等原机应用会调用
  `GUI+0x0a4(handle, &rect)` 后立刻把 rect 传给 `GUI+0x46c` 做 hit test，
  这说明该 entry 是 object/default client rect 查询，不是 draw 操作。

开发建议：

- SDK 暂命名为 `int bda_gui_object_rect_like(handle, rect)`。
- 传入真实 object/window/control handle 时，返回的是以 object 自身为原点的 client
  size rect，不是屏幕绝对坐标；需要绝对坐标时再结合
  `bda_gui_accumulate_origin_like()`。
- `handle=0` 使用 firmware default/global rect，只适合复刻原机默认上下文或 probe；
  不要把它当成当前 BDA window 已经创建成功的证据。

### GUI +0x430: `BDA_GUI_RECT_PREPARE_LIKE`

system function VA：`0x800c0410`

当前证据：

- entry 没有栈帧，只读取 `a0=rect`、`a1=x0`、`a2=y0`、`a3=x1`，并从调用者
  `stack+0x10` 读取第五参数 `y1`。
- 写入顺序是 `rect+0x00=x0`、`rect+0x04=y0`、`rect+0x08=x1`、
  `rect+0x0c=y1`。
- 函数不做排序、clipping 或有效性检查，也没有稳定 return value。
- C200 中它后面紧邻一组 0x10 byte rect helper：清零、复制、空矩形判断、
  相等判断、排序规范化、包含和交集。这解释了课程表/九门课程里
  `GUI+0x430 -> GUI+0x46c` 的组合。

开发建议：

- SDK wrapper `bda_gui_rect_prepare_like(rect, x0, y0, x1, y1)` 已按
  `bda_call5(bda_gui_table(), BDA_GUI_RECT_PREPARE_LIKE, (u32)rect, x0, y0, x1, y1)`
  封装这个 5 参数 ABI。
- 传入的 `rect` 必须指向至少 16 byte 可写内存。该入口不会检查空 pointer。
- 如果只是判断点是否在矩形中，优先使用已经包装好的
  `bda_gui_rect_contains_like(&rect, x, y)`。

### GUI +0x314 / +0x334 / +0x338 / +0x33c / +0x378: 绘图刷新和颜色

system function VA：

```text
GUI+0x314 -> 0x800bd584
GUI+0x334 -> 0x800b2c7c
GUI+0x338 -> 0x800b2c94
GUI+0x33c -> 0x800b2cac
GUI+0x378 -> 0x800bc2e0
```

当前证据：

- `GUI+0x314` 只读取 `a0=context`；`a0 == 0` 时使用默认 context `0x80825690`。
  函数调用 draw backend `+0x34(context+0x10)`，随后清理 `context+0x94` 与
  `context+0xb0`，最后调用 `MEM_FREE(context)`。它没有稳定 return value。
- 电子画板的 `GUI+0x418` 调用后经常紧跟 `GUI+0x314(context)`，因此 `+0x314`
  是较强的 surface/canvas flush-and-free 候选。
- V19 对两次 `GUI+0x310(visible_context)` 的结果分别调用 `GUI+0x314`，日志完整
  到 `BACK FREED`、`SPRITE FREED` 并正常返回主菜单，确认该入口是 compatible
  context 的配对销毁操作，不是只提交但保留对象的 flush。
- 公开 SDK 因此使用唯一名称 `bda_gui_compatible_context_create()` 和
  `bda_gui_compatible_context_free()`；free 后 handle 不可复用。
- `GUI+0x334` 会选择 `a0` 指向的 draw/context；`a0 == 0` 时使用默认 context
  `0x80825690`。它把 `a1=color` 写入 `context+0x14`，返回旧值。
- `GUI+0x338` 形状相同，但写入 `context+0x18`，返回旧 text/background mode
  值。mode 枚举仍未完全命名。
- `GUI+0x33c` 形状相同，但写入 `context+0x50`，返回旧文本颜色值。
- `GUI+0x378` 会把 `a1/a2/a3` 截成 3 个 byte，放到栈上，然后通过 context
  callback `global+0x5c(context+0x10, rgb_bytes)` 生成内部颜色值。它不是裸
  RGB565 常量构造函数。
开发建议：

- SDK 暴露 `bda_gui_rgb_like(handle, r, g, b)`、
  `bda_gui_set_fill_color_like(handle, color)`、
  `bda_gui_set_text_mode_like(handle, mode)` 和
  `bda_gui_set_text_color_like(handle, color)`。通常先用 rgb helper 生成内部
  颜色值，再传给 set_fill/text_color。
- 雷霆战机/决战坦克里也会把 `GUI+0x2fc(0x10)` 的返回值传给
  `GUI+0x334/+0x33c`，所以不要把这种返回值当 surface/context handle。
- SDK 暴露 `void bda_gui_surface_flush_like(context)`；调用后不要继续复用同一个
  context handle。
- 不要把 `bda_gui_rgb_like()` 当作固定 RGB565 编码器；颜色值依赖 draw/context
  的转换 callback。

### GUI +0x4f0: `BDA_GUI_DRAW_TEXT_LIKE`

system function VA：`0x800c0d40`

当前证据：

- entry 保存 `a0=handle/context`、`a1=x`、`a2=y`、`a3=text`，并从调用者
  `stack+0x10` 读取第五参数 `extra`。
- `handle == 0` 时使用默认 context `0x80825690`；否则使用调用者传入的
  draw/context。
- `extra == 0` 时直接返回 `0`，不会进入正常绘制路径。
- `extra < 0` 时调用 strlen-like helper `0x800068c4(text)`，再把得到的长度
  当作 `extra` 继续处理。
- 正常路径调用 `0x80119f68(context, context+0x54, text, extra)` 计算文本
  尺寸，并把 `x + width` 写到 `context+0x5c`，把 `y` 写到 `context+0x60`。
- 随后构造 `x/y/x+width+1/y+height+1` 矩形并走裁剪/重叠检查；无可绘制区域时
  可返回 `-1` 或已计算的 width-like 值。
- 裁剪通过后会调用底层 text draw helper `0x80119b50(context,x,y,text,extra)`。

开发建议：

- SDK 暴露 `bda_gui_draw_text_like(handle, x, y, text, extra)`。
- 当前推荐 `extra=-1` 表示按 NUL 结尾 GBK/ASCII 字符串绘制；不要把
  `extra=0` 当作默认值。
- 该入口仍需要真实 draw/context 生命周期。裸 `bda_main()` 中直接
  `handle=0` 调用可能重启，hardware probe 已有失败记录；优先放在原机 frame/control
  绘制 callback 或模板 patch 路径中使用。

### GUI +0x0e4 / +0x0e8: 对象绘图 begin/end 类调用

system function VA：

```text
GUI+0x0e4 -> 0x800ce928
GUI+0x0e8 -> 0x800ce9f0
```

当前证据：

- 两个函数都会先检查对象开头的 halfword 是否为 `1`，否则直接返回。
- `GUI+0x0e4` 只读取 `a0=object`。它是 object-level wrapper，不是新的
  framebuffer/draw backend；内部会调用 `GUI+0x308` 对应的 C200 函数
  `0x800bce50(object)` 取得 draw context；对象类型不匹配时返回 `0`。
- `GUI+0x0e4` 会把 `object+0x54+0x1c` 的 draw 计数加 1，然后根据对象
  `+0x7c` 的附加描述符走两条准备路径：普通路径调用 `0x800b643c(draw_context,
  object+0x54)`，附加描述符 `+0x28/+0x2c` 命中时会调用 `0x800b3950()` 并使用
  描述符 `+0x00/+0x04/+0x20/+0x24` 等字段。
- `GUI+0x0e8` 读取 `a0=object` 和 `a1=draw_context`。它先对
  `object+0x54` 调用 `0x800d33c4`，再把 `object+0x54+0x1c` 的 draw 计数减 1。
- `GUI+0x0e8` 在收尾路径调用 `GUI+0x30c` 对应的 C200 函数
  `0x800bd4b0(draw_context)`；没有稳定 return value。

开发建议：

- SDK 暂命名为 `bda_gui_object_draw_begin_like()` 和
  `bda_gui_object_draw_end_like()`；后者是 `void` cleanup wrapper。
- `begin` 返回的 draw context 必须传回同一个 object 的 `end`；不要把
  `bda_gui_object_draw_end_like()` 当作无状态 present/flush。
- 这两个入口适合复刻原机对象绘制生命周期；不要把它们当作比
  `GUI+0x308/+0x30c` 更通用的 draw API。

### GUI +0x0f4 / +0x0f8: object 父链 origin 累加/反向换算

system function VA：

- `GUI+0x0f4 -> 0x800ce26c`
- `GUI+0x0f8 -> 0x800cc664`

当前证据：

- 输入形态是 `a0 = handle/object`，`a1 = s32 *x`，`a2 = s32 *y`。
- 两个函数都会先检查 `handle != NULL` 且对象开头 halfword 为 `1`。
- `GUI+0x0f4` 把对象 `+0x14` 累加到 `*x`，把对象 `+0x18` 累加到 `*y`。
- `GUI+0x0f8` 从 `*x` 减去对象 `+0x14`，从 `*y` 减去对象 `+0x18`。
- 如果对象 `+0xd0` 指向父对象，会沿父链继续处理同样的 `+0x14/+0x18`。
- 两个函数都不设置有意义 return value。
- `GUI+0x0fc/+0x100` 是相邻坐标 helper，但使用 `+0x04/+0x08` 字段；字段含义
  尚未钉牢，SDK 暂不公开。

等价伪代码：

```c
void accumulate_origin(obj, int *x, int *y) {
    while (obj && obj->kind == 1) {
        *x += obj->origin_x_or_left14;
        *y += obj->origin_y_or_top18;
        obj = obj->parent_d0;
    }
}

void subtract_origin(obj, int *x, int *y) {
    while (obj && obj->kind == 1) {
        *x -= obj->origin_x_or_left14;
        *y -= obj->origin_y_or_top18;
        obj = obj->parent_d0;
    }
}
```

开发建议：

- SDK 暂命名为 `bda_gui_accumulate_origin_like(handle, &x, &y)` 和
  `bda_gui_subtract_origin_like(handle, &x, &y)`。
- 前者适合把 control/对象局部坐标转换为父链累计坐标；后者适合把累计坐标反向换算
  回 object 局部坐标。不要传空的 `x/y` pointer。

### GUI +0x134: `BDA_GUI_ACTIVE_FRAME_SET_LIKE`

system function VA：`0x800cad3c`

当前证据：

- entry 只读取 `a0=handle`。
- 函数先调用 `0x800caf64(handle)` 判断对象形态；某些形态会转入
  `0x800cae80(handle)` 并发送内部 `0xf3` message。
- 普通路径通过 `0x800dd1ac()` 取得当前 frame manager，对其中 `+0xd8` 的
  active frame pointer 进行比较和更新。
- 当前 active frame 与传入 handle 相同则直接返回 `0`。
- 若存在旧 active frame，会向旧 frame 发送内部 `0x31` message；随后把
  `manager+0xd8` 更新为新 handle。
- 新 handle 非空时会向新 frame 发送内部 `0x30` message，`a3` 为 `1`。
- 切换路径 return value 主要是内部 message return value 或 `0`，不是新 handle 本身的稳定别名。

开发建议：

- 当前只包装为 `int bda_gui_active_frame_set_like(handle)`。
- 只有在复刻原机 frame 生命周期时使用；普通 message box/文件读写应用不需要调用。
- 不要把 return value 当作 active frame handle；需要查询 container 的 active child 时
  使用相邻的 `bda_gui_active_child_get_like(context)`，但仍要按原机 event loop 模型处理
  lifecycle。

### GUI +0x13c: `BDA_GUI_ACTIVE_FRAME_GET_LIKE`

system function VA：`0x800cae04`

当前证据：

- 该 table entry 读取 `a0=context`，并把它原样传给 `0x800dd1ac(context)`。
- context 是 subtype `0x11` 的顶层 frame 时，helper 返回 context 本身；普通 kind=1
  object 则沿 `context+0xcc` 取得所属 container。
- 解析结果非空时读取并返回 `container+0xd8`；这是 `GUI+0x134` 普通 object 路径
  读写的 active-child slot。
- `名片.bda` 中该 offset 在 GUI table 下出现 67 次，调用点通常在 `jalr` delay slot
  把 frame/context 放入 `a0`，再把返回值和一组已知 child handle 比较。
- 传入 0 会让 helper 返回 `-1`，随后本函数仍读取 `-1+0xd8`；因此 0 和无参调用都
  不是安全查询方式。

开发建议：

- SDK 包装为 `bda_gui_active_child_get_like(context)`，context 必须是有效 handle。
- 它只查询 container 内的 active child，不创建 frame、不激活 frame，也不保证返回
  handle 在当前 BDA 入口上下文可安全绘制。
- 适合调试和复刻原机多 frame 切换流程；不要用它绕过 `register_frame`、
  `event_poll/dispatch` 和 `close_frame` 的完整 lifecycle，也不要改回无参 wrapper。

### GUI +0x07c/+0x080/+0x0b0 / +0x0b8..+0x0dc: kind=1 object flags/userdata/payload/resource/callback word

system function VA：

```text
GUI+0x07c -> 0x800ce4c8
GUI+0x080 -> 0x800ce4fc
GUI+0x0b0 -> 0x800ce4a0
GUI+0x0b8 -> 0x800ce558
GUI+0x0bc -> 0x800ce580
GUI+0x0c0 -> 0x800ce5b0
GUI+0x0c4 -> 0x800ce5d8
GUI+0x0c8 -> 0x800ce608
GUI+0x0cc -> 0x800ce644
GUI+0x0d0 -> 0x800ce7dc
GUI+0x0d4 -> 0x800ce804  // 不公开 wrapper
GUI+0x0d8 -> 0x800ce780
GUI+0x0dc -> 0x800ce7a8
```

当前证据：

- 这些 entry 都先检查 `a0 != 0`，再读取 `lh 0(a0)`；只有 object kind 为 `1`
  时继续，否则返回 `0`。`GUI+0x0c8/+0x0cc` 还会继续检查 subtype halfword
  `lh 2(a0) == 0x12`。
- `GUI+0x0b0(handle)` 读取 `handle+0x24` flags；失败返回 `0`。
- `GUI+0x080(handle, mask)` 读取旧 `handle+0x24` flags，把 `mask` OR 进去并写回；
  成功返回 `1`，失败返回 `0`。它不清除任何 bit。
- `GUI+0x07c(handle, mask)` 先计算 `~mask`，再把 `handle+0x24` 与 `~mask`
  相与写回；成功返回 `1`，失败返回 `0`。它只清 mask 对应 bit。
- `GUI+0x0b8(handle)` 读取 `handle+0x80` word；失败返回 `0`。
- `GUI+0x0bc(handle, value)` 读取旧 `handle+0x80`，写入 `value`，成功返回旧值；
  失败返回 `0`。
- `GUI+0x0c0(handle)` 读取 `handle+0x84` word；失败返回 `0`。
- `GUI+0x0c4(handle, value)` 读取旧 `handle+0x84`，写入 `value`，成功返回旧值；
  失败返回 `0`。
- `GUI+0x0c8(handle)` 读取 `handle+0xec` 指向 payload 结构的 `+0x1c` word；
  失败返回 `0`。
- `GUI+0x0cc(handle, value)` 读取旧 `payload+0x1c`，写入 `value`，成功返回旧值；
  失败返回 `0`。
- `GUI+0x0d0(handle)` 读取 `handle+0x8c` pointer；失败返回 `0`。
- `GUI+0x0d4(handle, value)` 不是简单 setter：subtype `0x12` 路径会释放旧
  `handle+0x8c`、复制新字符串/资源指针并写回；subtype `0x11` 路径会通过
  `0x800dd380` 同步发送内部 `0x134` message。因此 SDK 不公开这个 setter。
- `GUI+0x0d8(handle)` 读取 `handle+0x88` pointer；失败返回 `0`。
- `GUI+0x0dc(handle, value)` 读取旧 `handle+0x88`，只有 `value != 0` 时才写入，
  成功返回旧值；失败或 `value == 0` 返回 `0`。

开发建议：

- SDK 暂命名为 `bda_gui_object_flags_get_like()`、
  `bda_gui_object_flags_or_like()`、`bda_gui_object_flags_clear_like()`。这组
  wrapper 只固定 `+0x24` flags 访问形态；不是 show/hide、enable/disable 或通用
  state setter；不要用它猜测未确认 bit。
- SDK 暂命名为 `bda_gui_object_userdata0_get_like()` /
  `bda_gui_object_userdata0_set_like()` 和
  `bda_gui_object_userdata1_get_like()` /
  `bda_gui_object_userdata1_set_like()`。
- 这里的 userdata 是 caller data / internal object slot 的保守命名；不同
  control 可能复用这两个 word 做不同用途。不要把 `0` return 单独当成失败证明，
  因为字段本身也可能合法保存 `0`。
- `bda_gui_object_payload_word_get_like()` /
  `bda_gui_object_payload_word_set_like()` 更窄：它们只适用于 subtype `0x12` 且
  `handle+0xec` payload 存在的 object/control。
- `bda_gui_object_resource_ptr_get_like()` 只读 `handle+0x8c` pointer。不要直接写
  这个字段；需要改值时应先从原机同类 control 中确认 `GUI+0x0d4` 的 subtype
  分支和资源所有权。
- `bda_gui_object_callback_ptr_get_like()` /
  `bda_gui_object_callback_ptr_set_like()` 访问 `handle+0x88`。该字段接近
  wndproc/callback pointer；setter 只适合复刻原机 control 初始化/替换路径。
- setter 会改写 object 内部字段，只应在真实 object/control lifecycle 内复刻原机
  调用形态，不要对 frame handle 或 bare 指针调用。

### GUI +0x1ac / +0x1b0: 对象更新通知对

system function VA：

```text
GUI+0x1ac -> 0x800de150
GUI+0x1b0 -> 0x800de190
```

当前证据：

- 两个入口都把调用参数写入 `sp+0x10` 起的小消息包，然后通过 GUI+0x040 对应的
  同步 send 入口 `0x800dd380` 派发。
- `GUI+0x1ac` 使用内部消息号 `0x162`，参数形态是 `handle, a1, a2`；C200 会把
  `handle/a1/a2` 分别写到 `sp+0x10/+0x14/+0x18`。
- `GUI+0x1b0` 使用内部消息号 `0x163`，参数形态是 `handle, a1`；C200 会把
  `handle/a1` 写到 `sp+0x10/+0x14`。
- 这两个 helper 自身不排队，也不直接修改对象字段；具体效果来自目标对象处理
  `0x162/0x163` message 的 wndproc。
- 九门课程等应用常见形态是 `GUI+0x1ac(handle, 0x64, 0x190)` 后跟
  `GUI+0x1b0(handle, 0x64)`，像对象布局/刷新通知对。

开发建议：

- SDK 暂命名为 `bda_gui_object_update3_like()` 和
  `bda_gui_object_update2_like()`。
- 参数语义仍未最终命名，优先在克隆原机 control 刷新路径时使用。

### GUI +0x1b4: `BDA_GUI_OBJECT_PAIR_EXISTS_LIKE`

system function VA：`0x800de0a8`

当前证据：

- C200 entry 只读取 `a0/a1`，没有写入调用者 buffer，也没有发送 message。
- 函数从 `0x804a6b40` 起扫描 GUI 全局记录 pointer 表，每项先判空，再读取记录
  `record+0` 和 `record+4`。
- 当 `record+0 == a0` 且 `record+4 == a1` 时返回 `1`；扫描到上限仍未命中时返回
  `0`。
- 循环使用 `slti ..., 0x10`，实际只访问这组全局表的有限槽位，不遍历普通
  window/control 子树。

开发建议：

- SDK 暂命名为 `bda_gui_object_pair_exists_like(a0, a1)`，强调它只是 pair 查询。
- 不要把它当成通用 handle validity check：它比较的是 GUI 内部记录的前两个 word，
  不证明该 object 可绘制、可 destroy，或属于当前 BDA 的完整 lifecycle。

### GUI +0x2fc: `BDA_GUI_DRAW_OBJECT_CREATE_LIKE`

system function VA：`0x800bd36c`

当前证据：

- 该函数非常短，只读取 `a0=kind/index`。
- entry 先计算 `kind * 4`，再检查 `kind < 0x11`。
- `kind >= 0x11` 时返回 `-1`。
- 合法时从 `0x80825640 + kind*4` 读取一个 word 并返回。
- C200 没有读取 `a1/a2/a3`，因此旧 4 参数 wrapper 与 table entry ABI 不符。

开发建议：

- SDK 只暴露 `bda_gui_draw_object_create_like(kind)`，不再为早期
  `frame_surface` 误名保留同义 wrapper。
- 原机 frame/window descriptor 中常见 `kind=15`，可作为 `descriptor+0x2c` 的
  surface/object 候选值；但它只有在原机 frame/control lifecycle 已经建立时才有意义。
- 雷霆战机/决战坦克还会查询 `kind=7`、`kind=8`、`kind=15` 和 `kind=0x10`。
  其中 `kind=0x10` 的返回值会传给 `GUI+0x334/+0x33c` color setter，并保存到
  game global；这说明该入口返回的是 firmware object/value table 项，不一定是
  surface 或 context handle。
- 该入口更像 draw object/surface 表查询，不是通用对象构造器；返回 `-1` 时不要
  当作有效 pointer 传给 frame 注册或 draw API。
- 它不是 framebuffer allocator 或最小绘图入口。no-template BDA 开发先用
  `surface=0`，不要把 `bda_gui_draw_object_create_like(15)+register_frame` 当成
  standalone UI template。

### GUI +0x46c: `BDA_GUI_RECT_CONTAINS_LIKE`

system function VA：`0x800c0818`

当前证据：

该函数非常短，逻辑等价于：

```c
int contains(const s32 *rect, s32 x, s32 y) {
    return rect[0] <= x && x < rect[2] && rect[1] <= y && y < rect[3];
}
```

即 `a0` 指向四个 word 的矩形，`a1` 是 x，`a2` 是 y；返回 `1` 表示点在范围内。

开发建议：

- SDK 暴露 `bda_rect_like_t` 和 `bda_gui_rect_contains_like()`。
- 原机电子书、课程表、九门课程等应用在资源/矩形热点判断附近频繁调用它。

### GUI +0x540: `BDA_GUI_DRAW_VX_LIKE`

system function VA：`0x800bb864`

当前证据：

- C200 entry 保存 `a0=handle/context`、`a1=x`、`a2=y`，但会从调用者
  `stack+0x14` 读取 `vx_resource`，也就是第 6 个参数位置。
- entry 只接受完整 VX resource block；先检查 `resource[0..1] == "VX"`。
- width/height 不是来自调用者参数。函数分别从 `vx_resource+0x06` 和
  `vx_resource+0x0a` 读取 VX header 里的 width/height，并用它们构造绘制矩形。
- `handle == 0` 或 handle 不是当前期望的 draw/context 类型时，会走默认 context
  或内部对象解析路径；普通应用仍应传有效 draw handle。
- 绘制路径会做 clipping/intersection 检查，随后通过 draw backend callback
  绘制 VX payload。
- 无效 VX magic、无可绘制区域或 context 不可用时提前返回；不要把 return value
  当作稳定的绘制成功计数。

开发建议：

- 公开 SDK 暴露 `bda_gui_draw_vx(handle, x, y, vx_resource)`。wrapper 内部用
  `bda_call6` 补齐两个 unused 参数，把 `vx_resource` 放在 C200 读取的第 6 个参数位。
- 不再公开旧的 `width,height` 参数；缩放/裁剪应通过其他 draw/context API 实现，
  不能靠 `GUI+0x540` 的调用参数。
- `vx_resource` 必须指向完整 VX block，不是裸 pixel buffer。

### GUI +0x670 / +0x808: BMP/JPEG 解码入口

system function VA：

```text
GUI+0x670 -> 0x800e1f74
GUI+0x808 -> 0x800e2d2c
```

当前证据：

- 两个入口都会保存 `a0=owner`、`a1=out`，把 `a2=path` 传给内部文件读取 helper
  `0x800e1cb0`。
- `GUI+0x670` 的 BMP 路径会检查文件数据前两个 byte 是否为 `VX`。若匹配，会从
  数据 offset `+0x06/+0x0a/+0x12/+0x18` 等位置填充 `bda_picture_like_t`，并把
  `a3` 当作 `void **out_source_buffer`，成功时把源 file buffer 写回 `*a3`。
  非 VX decoder 路径会释放临时 file buffer，并把 `*out_source_buffer` 写成 0。
- VX 快路径会写 `out+0x00 = 0`、`out+0x04 = width`、`out+0x08 = height`、
  `out+0x0c = width * 2`、`out+0x10 = resource[0x12]`、`out+0x11 = 0x10`、
  `out+0x14 = resource+0x18`、`out+0x18 = -1`。
- `GUI+0x808` 会把 `a3` 截成 signed 8-bit mode。`mode == 1` 时先走
  `0x800e2bc0` 检查路径；其他 mode 直接进入 JPEG 解码 helper `0x800bebf8`。
- 两者都会在返回前释放临时文件 buffer；return value 通过内部 decoder 或错误路径传播。

开发建议：

- SDK 暴露 `bda_gui_decode_bmp_like(owner, out, path, out_source_buffer)` 和
  `bda_gui_decode_jpeg_like(owner, out, path, mode)`，只固定当前 C200 ABI。
- 调用 BMP wrapper 时 `out_source_buffer` 不能是 `NULL`。若它非 0，后续释放时机
  应复刻原机相册路径，不要把 returned pointer 当作长期静态资源。
- 这不是完整图片 control API。调用者还需要有效 owner/window/image handle，以及后续
  把 RGB565 buffer 渲染到屏幕的 draw/surface 生命周期。
- 结构体字段说明见 `picture_notes.md`；普通应用优先使用已打包 VX 资源和
  `bda_gui_draw_vx_like()`。

### GUI +0x5d4 / +0x6b0 / +0x6e0 / +0x72c / +0x750: game/display 扩展 screen/input helper

system function VA：

```text
GUI+0x5d4 -> 0x8001b518
GUI+0x6b0 -> 0x80010d94
GUI+0x6e0 -> 0x8005b844
GUI+0x72c -> 0x8005a2d4
GUI+0x750 -> 0x8001de5c
```

当前证据：

- `GUI+0x5d4` 接收 `a0=packet`。entry 先调用 memset-like helper 清 6 byte，
  然后读取 `0xb0010100/0xb0010200/0xb0010300` 等按键/MMIO 状态；按键有效时
  写入 `packet[0..5]` 中的若干 byte，并返回 1，否则返回 0。
- `GUI+0x6b0` 表 entry 只有 `lui v0, 0x8034; jr ra; lw v0, -0x3f18(v0)`，
  不读取任何调用者参数。它返回内部 screen/framebuffer pointer，不是 4 参数分配函数。
  这个 pointer 属于 firmware display state，不是 SDK 分配的稳定 framebuffer；
  普通 BDA 不要直接写入，也不要把它和 `GUI+0x3f8/+0x400` 拼成自定义 present 路径。
- `GUI+0x6e0` table entry 无参数。它先调用 `0x80059f68` 查询 active-low pen GPIO，
  再用 `0x8001e6c4` 或 `0x8005a7e0` 取得阈值，与 `0x1068` 比较。
- `GUI+0x6e0` 在阈值未到时返回 `1`。阈值达到后会写 global state：
  `0x8048da68 = 1`、`0x8047402c = 2`、`0x8048dab0 = 2`，调用
  `0x80185628`、`0x800de144` 和 `0x8005b030`，最后返回 `0`。
- `雷霆战机.bda` 和 `决战坦克.bda` 的全屏 blit 链路都在 `GUI+0x3f8` 之后调用
  `GUI+0x6e0`，再根据返回路径进入 `GUI+0x400` 和 `MEM+0x00c`。因此它不是
  GAMEBOY 专用 getter，而是触摸长按驱动、带全局副作用的 game state pump。
- `GUI+0x72c` 当前 table entry 也不读取 `a0`。它检查全局 `0x804a6c70`，否则调用
  `0x8012d508`、`0x80058cb4`、`0x8005b604`，并把结果写到 `0x8048d920`
  附近的状态 word。
- `GUI+0x750` 保存 `a0`、`a1` 为两个 output pointer，通过 `0x8000aeb0` 获取事件记录。
  成功时写 `record+4` 到 `*a0`、写 `record+0` 到 `*a1`；失败时两个输出都写 `-1`。

开发建议：

- SDK 当前暴露为 `bda_gui_screen_buffer_like(void)`。
- SDK 当前暴露为 `bda_gui_input_packet_like(bda_gui_input_packet_like_t *packet)`；
  packet 大小由 `BDA_GUI_INPUT_PACKET_SIZE` 固定为 6 byte。
- SDK 当前暴露为 `bda_gui_game_display_pump_like(void)`，对应
  `BDA_GUI_GAME_DISPLAY_PUMP_LIKE`。名称为兼容保留；实际实现是触摸长按状态 pump，
  不是 blit status getter；不要把 return value 当作 framebuffer 地址，也不要在普通
  触摸轮询中调用这个有全局副作用的入口。
- SDK 已将 `GUI+0x72c` 收窄为 `bda_gui_state_query_like(void)`。
- SDK 已将 `GUI+0x750` 修正为 `bda_gui_event_fetch_like(bda_gui_event_fetch_like_t *out_event)`；
  typed result 中 `code` 对应 `record+4`，`value` 对应 `record+0`。这仍是 low-level helper，
  不应替代稳定窗口消息/按键 API。

### GUI +0x6d8: `BDA_GUI_TICK_COUNT_25MS_LIKE`

system function VA：`0x8012bdb0`

当前证据：

- table entry 无参数，直接返回全局 `0x80474094`。
- 定时 IRQ `0x8012bb90` 先把该全局加一，再向 TCU `0xb0002028` 写入确认值。
- 初始化函数 `0x8012bcd4` 把 `0x000b71c4 / 0x28 = 18750` 写入 TCU compare。
  配合 12 MHz 外部时钟和 `/16` prescale，周期是 `18750 / 750000 = 25 ms`。
- 官方 `BB虚拟机.bda` 在初始化路径调用 `GUI+0x6d8` 并保存返回值；其 GetTick
  wrapper 在 `0x81c051b4` 再读当前值，执行无符号 `current - base`，最后用移位加法
  乘 25。固件字符串 `0100831:修改“gettick读出来不是ms”` 与该换算一致。
- `GameTickProbeV9` 在 8013 上从 `0x000001ff` 走到 `0x00000227`，raw delta 为
  `40`，毫秒换算为 `1000`，回绕算术通过并正常返回菜单。
- 独立 HMP 读取同一固件全局，两轮宿主采样得到 `24.853 ms/tick` 和
  `24.696 ms/tick`；误差来自 HMP 读取暂停和模拟器自适应 instruction clock。

开发建议：

- 读取原始值用公开 `bda_gui_tick_count_25ms()`。
- 时间间隔必须用无符号差值；公开 helper 提供 `bda_gui_tick_elapsed_25ms()` 和
  `bda_gui_tick_elapsed_ms()`。
- 不要把 raw tick 直接当毫秒，不要用 `SYS+0x09c` 代替；后者是 preset selector。
- 当前公开等级是模拟器稳定；研究头保留 `_like` 供 probe 使用，普通应用使用上面的
  无后缀公开名称。真机状态仍为待复测。

### GUI +0x738: `BDA_GUI_SCREEN_WIDTH_LIKE`

system function VA：`0x80024708`

当前证据：

- table entry 目标的第一条指令是 `jr ra`，delay slot 是 `addiu v0, zero, 0x130`。
- 因此函数无参数，稳定返回 `0x130`，即十进制 `304`。
- `GAMEBOY.BDA` 在扩展 GUI/screen buffer 路径附近引用该 offset；结合
  320x240 设备和内部边距，`0x130` 更像可绘制区域宽度，而不是完整屏幕模式结构。

开发建议：

- SDK 将旧 `BDA_GUI_SCREEN_MODE_QUERY_LIKE` / `bda_gui_screen_mode_query_like()`
  直接改名为 `BDA_GUI_SCREEN_WIDTH_LIKE` / `bda_gui_screen_width_like()`。
- 该 return value 适合当作系统可绘制宽度常量使用；高度、颜色深度和 framebuffer 布局
  仍应从 `GUI+0x6b0/+0x72c/+0x750` 等扩展 GUI 调用继续确认。

## 内存表

### MEM +0x000: `BDA_MEM_TRACK_ALLOC_LIKE`

system function VA：`0x80058574`

当前证据：

- entry 只保存 `a0=size`，先调用基础 allocator `0x80007648(size)`。
- firmware tracking flag `0x80474020` 为 0 时，直接返回 allocator pointer。
- tracking flag 开启且分配成功时，会读取记录计数 `0x80474018`，在
  `0x80823e40 + count * 12` 写入 pointer、size 和 active flag `1`，再递增计数。
- 分配失败时会调用 trace/log helper `0x800098c0`，最终返回 `0`。

开发建议：

- SDK 暴露 `bda_track_alloc_like(size)`，只固定单参数 ABI。
- 普通开发优先使用 `bda_alloc()`；tracked wrapper 主要用于匹配原机使用
  MEM+0x000 的场景，返回 pointer 仍属于 firmware heap。

### MEM +0x004: `BDA_MEM_TRACK_FREE_LIKE`

system function VA：`0x80058618`

当前证据：

- entry 只保存 `a0=ptr`。
- firmware tracking flag `0x80474020` 开启时，会在 `0x80823e40` 起始的记录表中
  线性查找 pointer；命中后清 active flag 和 pointer word。
- 无论 tracking 是否开启，最终都会调用基础 free wrapper `0x800067f4(ptr)`。
- 该 entry 没有可用 return value。

开发建议：

- SDK 暴露 `bda_track_free_like(ptr)`，返回类型为 `void`。
- 只释放 `bda_track_alloc_like()` 或同一 firmware heap 分配得到的 pointer；不要和
  compiler libc `free` 混用。

### MEM +0x01c: `BDA_MEM_TRACK_BEGIN_LIKE`

system function VA：`0x80058554`

当前证据：

- entry 只读取 `a0=free_on_finish`。
- 函数设置 tracking flag `0x80474020 = 1`，保存 `0x8047401c = free_on_finish`，
  并清记录计数 `0x80474018 = 0`。
- 该 entry 没有可用 return value。

开发建议：

- SDK 暴露 `bda_mem_track_begin_like(free_on_finish)`，只固定单参数 ABI。
- 这是 firmware heap debug helper；普通开发不需要调用它。
- `free_on_finish` 会被 `MEM+0x024` 结束 helper 读取，而该结束 helper 可能释放仍
  在记录表里的 pointer，SDK 当前不公开 `MEM+0x024`。

### MEM +0x020: `BDA_MEM_TRACK_REPORT_LIKE`

system function VA：`0x8005868c`

当前证据：

- entry 读取 `a0=summary_only`。
- `summary_only == 0` 时会扫描 `0x80823e40` 起始的 tracked record table，
  对 pointer 非 0 的记录调用 trace/log helper `0x800098c0`。
- `summary_only != 0` 时走 summary-like log 路径，把记录计数作为参数传给
  `0x800098c0`。
- 函数返回当前记录计数 `0x80474018`，不会释放 pointer，也不会清 tracking state。

开发建议：

- SDK 暴露 `bda_mem_track_report_like(summary_only)`。
- 该 helper 主要用于 debug/probe；不要把 return value 当作当前 live allocation
  个数，它更接近 tracked record count。

### MEM +0x024: `BDA_MEM_TRACK_FINISH_LIKE`

system function VA：`0x80058750`

当前证据：

- entry 不读取调用者参数。
- 函数读取记录计数 `0x80474018`，扫描 `0x80823e40` 起始的 tracked record table。
- 对 pointer 非 0 的记录调用 trace/log helper `0x800098c0`。
- 如果 `0x8047401c` 非 0，会对仍记录的 pointer 调用基础 free wrapper
  `0x800067f4(ptr)`，并清 active flag 和 pointer 记录。
- 最后清 `0x80474018` 和 tracking flag `0x80474020`。

开发建议：

- SDK 暴露 `void bda_mem_track_finish_like(void)`，只固定无参数 ABI。
- 这是 firmware heap debug/probe helper。若 begin 时 `free_on_finish != 0`，
  finish 可能释放调用者仍持有的 pointer；普通业务代码不要调用它。

### MEM +0x028: `BDA_MEM_TRACK_RETAIN_LIKE`

system function VA：`0x80058820`

当前证据：

- entry 读取 `a0=ptr`，空 pointer 会调用 trace/log helper `0x800098c0` 并返回 `0`。
- 函数读取记录计数 `0x80474018`，扫描 `0x80823e40` 起始的 12-byte tracked record table。
- 命中 pointer 后，读取记录 `+8` 的 refcount-like 字段，加一后写回。
- 无论命中与否，返回值都是原 pointer；未命中时只额外调用 trace/log helper。

开发建议：

- SDK 暴露 `void *bda_mem_track_retain_like(void *ptr)`，只固定单参数 ABI 和 pointer return。
- 这个 helper 只适合 firmware tracking/debug 场景；不要把它当作通用对象 retain。

### MEM +0x02c: `BDA_MEM_TRACK_RELEASE_LIKE`

system function VA：`0x800588b8`

当前证据：

- entry 读取 `a0=ptr`，空 pointer 或未命中记录时会调用 trace/log helper。
- 函数读取记录计数 `0x80474018`，扫描同一个 `0x80823e40` tracked record table。
- 命中 pointer 后，读取记录 `+8` 的 refcount-like 字段，减一后写回。
- 递减结果为 0 时，函数调用基础 free wrapper `0x800067f4(ptr)`，随后清记录
  `+8` 和 pointer word。
- 该 entry 没有稳定 return value。

开发建议：

- SDK 暴露 `void bda_mem_track_release_like(void *ptr)`，返回类型为 `void`。
- 它可能释放传入 pointer；只对 tracking record table 中已有、且生命周期已按
  firmware tracking 规则管理的 pointer 使用。普通业务代码不要调用它。

### MEM +0x008: `BDA_MEM_ALLOC`

system function VA：`0x80007648`

当前证据：

- entry 保存 `a0=size`，只使用一个调用者参数。
- 函数读取全局锁/互斥对象 `0x80473f00`，先调用 lock helper `0x8000ba84`。
- 主路径调用内部 allocator `0x80007440(size)`。
- 分配完成后调用 unlock helper `0x8000bb98`，并返回内部 allocator 的 pointer。
- `FS_OPEN` 自己也调用这个入口申请 file handle 对象。

开发建议：

- SDK 暴露 `bda_alloc(size)`。
- 返回的是固件堆内存；释放必须用 `bda_free()`，不要和 libc `malloc/free` 混用。
- 分配失败 return value 仍按空 pointer 处理。

### MEM +0x00c: `BDA_MEM_FREE`

system function VA：`0x800067f4`

当前证据：

- entry 保存 `a0=ptr`，只使用一个调用者参数。
- 与 alloc 一样先锁住全局堆锁 `0x80473f00`。
- 主路径调用内部 free helper `0x80006620(ptr)`。
- 随后释放锁并返回；该 entry 没有可用 return value。
- 传入 `NULL` 的行为尚未单独确认；SDK 侧仍应避免释放无效 pointer。

开发建议：

- SDK 暴露 `bda_free(ptr)`，返回类型为 `void`。
- 只释放 `bda_alloc()` 或固件明确交给调用者释放的 MEM 堆 pointer。

### MEM +0x010: `BDA_MEM_CALLOC_LIKE`

系统表项：

```text
MEM+0x010 -> 0x800065bc
```

C200 行为：

- 参数为 `a0=count`、`a1=size`。
- 表项 wrapper 先进入 firmware heap 全局锁，再调用内部 helper
  `0x80006540(count, size)`，最后释放锁并返回 pointer。
- 内部 helper 在 `count == 0` 或 `size == 0` 时返回 `0`。
- `size >= 3` 时先向上对齐到 4 byte，然后计算 `bytes = count * aligned_size`，
  调用内部 allocator `0x80007440(bytes)`。
- 分配成功后调用 zero-fill helper `0x800078ec(ptr, bytes)`，逐 byte 清零。
- 当前切片未见乘法 overflow guard，因此 SDK 不把它命名为标准 `calloc`。

证据：

- `黄冈教辅.bda` 直接调用 MEM+0x010，形状为 `count=0x90,size=1`，随后按
  `0x90` byte 结构继续初始化。
- `飞天影音.bda` 和 `飞天影音_.bda` 也有直接 MEM+0x010 调用点，并与 MEM+0x014
  realloc-like helper 成组使用。

SDK 暴露：

- `bda_calloc_like(count, size)`。返回 pointer 属于 firmware heap，释放必须用
  `bda_free()`；不要和 compiler libc `calloc/free` 混用，也不要依赖 overflow 处理。

### MEM +0x014: `BDA_MEM_REALLOC_LIKE`

系统表项：

```text
MEM+0x014 -> 0x800077b0
```

C200 行为：

- 参数为 `a0=ptr`、`a1=new_size`。
- `ptr == 0 && new_size != 0` 时直接调用 `MEM_ALLOC(new_size)` 并返回新 pointer。
- `ptr != 0 && new_size == 0` 时调用 `MEM_FREE(ptr)`，返回 `0`。
- 普通 realloc 路径先调用 `MEM_ALLOC(new_size)`；成功后通过内部 helper
  `0x80007874(ptr)` 查询旧块 size。旧块 size 为 0 时返回 `0`，不会释放旧块。
- copy 长度为 `min(old_size, align4(new_size))`，内部 copy helper 为 `0x80006bf8`。
  copy 完成后调用 `MEM_FREE(ptr)`，返回新 pointer。

证据：

- `飞天影音.bda` 和 `飞天影音_.bda` 有直接 MEM+0x014 调用点。
- 该 helper 依赖 firmware heap 元数据查询旧块大小，因此只适用于 `bda_alloc()` 或
  固件明确交给调用者释放的 pointer。

SDK 暴露：

- `bda_realloc_like(ptr, new_size)`。保留 `_LIKE` 后缀，提醒它不是 compiler libc
  realloc，也不能接收 stack/static buffer 或 file handle。
- 不要释放栈 pointer、静态 buffer、运行时 API 表 pointer 或 file handle。

## RES 表

### RES +0x000/+0x004/+0x008/+0x00c/+0x010/+0x040: 不公开的 resource manager lifecycle

system function VA：

```text
RES+0x000 -> 0x8013dfe4
RES+0x004 -> 0x8013aaf0
RES+0x008 -> 0x8013bb40
RES+0x00c -> 0x8013bc10
RES+0x010 -> 0x8013e018
RES+0x040 -> 0x80142f50
```

当前证据：

- `RES+0x000` 不读取调用者参数，只清 `0x80474148/0x8047415c/0x80474130/0x80474178`
  和 `0x804aaa0/0x804aa9c` 等全局状态；它更像 resource manager reset。
- `RES+0x004(a0, a1, a2)` 会把 `a0` 当作路径，调用 `FS+0x000` 打开文件，
  读取多个 `0x80/0x400` byte 全局 buffer，并写 `0x804b` 附近的 resource 全局
  file handle/cache pointer。它不是普通 DLX loader，也不是只读查询。
- `RES+0x008()` 会释放 `0x804b` 附近的两个全局 buffer、关闭全局 file handle，
  并清 `0x804b-0x790/-0x78c/-0x580` 等状态；它是全局 cleanup，不应由普通
  BDA 直接调用。
- `RES+0x00c(descriptor)` 会从 descriptor 读取多个 word 写入 `0x8047` 附近
  的全局 resource state，随后按 `descriptor+0x1c` 的路径打开文件并 seek 到末尾。
  descriptor layout 仍未命名，且会改全局状态。
- `RES+0x010()` 会关闭 `RES+0x00c` 打开的全局 file handle，并释放/清零相关
  buffer；它没有稳定 return value。
- `RES+0x040()` 会打开固件内置路径，成功后读取 0x40 byte 到 `0x8086b740`
  一带；失败时若全局静音/抑制 flag 未置位，会调用 `GUI+0x2b8` message box。
  因此它不是无副作用的 resource query。

开发建议：

- SDK 不公开这些 wrapper。它们是系统 resource manager lifecycle/全局缓存路径，
  不能当成稳定的 DLX load/open/close API。
- 当前公共 RES wrapper 只保留 `bda_res_get_state_like()` 和
  `bda_res_entry_094_like()`；真正资源加载仍应从原机调用点和 C200 descriptor
  layout 继续拆解。
- 旧误名 `bda_load_dlx*` 已删除；不要用 `RES+0x004/+0x00c/+0x040` 重新发明
  一个 high-level loader 名称。

### RES +0x090: `BDA_RES_GET_STATE_LIKE`

system function VA：`0x80017580`

当前证据：

- 函数只接收 `a0=out_state` 一个调用者参数，并保存到 `s0`。
- 入口加锁后读取 MMIO/状态寄存器 `0xb0003004`，调用内部 helper
  `0x800165b0`，把多个栈上临时输出复制到 `out_state`。
- C200 会写入 `out_state+0x00/+0x04/+0x08/+0x0c/+0x10/+0x14/+0x18`
  共 7 个 word；写出后还会把 `out_state+0x10` 减 1。
- 函数尾部调用 `0x8000528c(saved_cp0_status)` 释放/恢复锁状态；该 helper 只是
  写回 CP0 状态，不构造稳定 `v0`。因此 `RES+0x090` 应视为只写 `out_state`
  的 snapshot API，不要读取 return value。
- 相邻函数 `0x8001763c` 形状几乎相同，但读取 `0xb0003008`，说明这是一组
  资源/图片状态快照 helper。

开发建议：

- SDK 暴露 `bda_res_state_like_t` 和
  `void bda_res_get_state_like(bda_res_state_like_t *out_state)`。
- 字段名仍保持 `aux*`，因为状态 word 的具体含义要结合相册、课程表、九门课程
  的资源渲染路径继续命名。

### RES +0x094: `BDA_RES_ENTRY_094_LIKE`

system function VA：`0x800098c0`

当前证据：

- 函数 entry 只把 `a1/a2/a3` 写到调用者栈上，随后调整 `sp` 并直接 `jr ra`。
- return value 为 `0`。
- 这解释了 hardware probe 里传入格式字符串或 DLX 路径都“返回 0 且无可见加载效果”的现象。

结论：

- 这个入口更像被编译成空实现的 trace/log/debug stub。
- 不应再把它作为 DLX 加载器使用。
- SDK 已删除旧 `bda_load_dlx_*` 别名；新代码应使用文件系统读取 DLX，或等待
  真正资源加载 API 被确认。

## SYS 表

### SYS +0x080: `BDA_SYS_DELAY_LIKE`

system function VA：`0x800043a0`

当前证据：

- 函数读取系统频率/校准全局值，计算循环次数后执行忙等。
- 它不是睡眠调度 API，而是阻塞式 delay。
- entry 只接收 `a0` 一个参数；SDK 将该参数命名为 `delay_units`，避免误认为是
  标准毫秒或微秒单位。
- 函数结束路径没有构造状态码；SDK 暴露为 `void bda_sys_delay_like(u32 delay_units)`，
  不要读取 return value。

开发建议：

- 小探针里可短暂使用。
- GUI 应用不要在主 event loop 里长时间调用，否则会阻塞消息处理。

### SYS +0x09c: `BDA_SYS_TIMER_LIKE`

system function VA：`0x80022dd0`

当前证据：

- 函数先判断 `a0 < 0x0f`，超出时使用 `0x0e`，负数时使用 `0`。
- 随后把该值左移两位，从 `0x8027b5ec` 附近的 14/15 项内部表中取一个 word，
  再调用 `0x8018921c`。
- 下游 `0x8018921c` 会把表值再次 clamp 到 `0..0x62`，设置
  `0x806c4790 = 1`，并把结果写到 `0x80474308`；它同样不构造稳定 return value。
- `系统设置.bda` 的调用点会传入递增的索引；`GAMEBOY.BDA` 的调用点会把运行时
  timing/rate 值除以 10 后传入。

结论：

- 该入口更像选择 timer/rate preset，而不是设置任意 tick 数。
- SDK wrapper 的参数命名为 `preset_index`；开发者应把可用范围按 `0..14`
  处理，超出范围会被 C200 clamp。SDK 暴露为
  `void bda_sys_timer_like(u32 preset_index)`，不要读取 return value。

### SYS +0x0ac / +0x0b0: `BDA_SYS_ALARM_SET_LIKE` / `BDA_SYS_ALARM_GET_LIKE`

system function VA：

- `SYS+0x0ac` -> `0x80016294`
- `SYS+0x0b0` -> `0x800163d8`

当前证据：

- 两个入口都使用 `alarm_data, slot` 两个参数，原机闹钟应用已见 slot 0/1/2。
- C200 以 `0x2b8` byte 作为一个 alarm record，持久化文件中的 record offset 为
  `0x578 + slot * 0x2b8`。
- `alarm_get` 从配置文件复制 0x2b8 byte 到调用者 buffer，return value: 成功 1，失败 0。
- `alarm_set` 会把 `record+0x00` 写成 `slot+2`，把 `record+0x10` 写成 1，
  然后把整个 0xda0 byte 配置文件写回；return value: 成功 1，失败 0。
- 当前function-level slice未见 slot bounds check。
- SDK 中 `BDA_SYS_ALARM_DB_FIRST_RECORD_OFFSET`、`BDA_SYS_ALARM_SLOT_TAG_OFFSET`
  和 `BDA_SYS_ALARM_ENABLE_FLAG_OFFSET` 只对应这些已确认 offset；未命名 byte
  仍保留为 raw data。

开发建议：

- SDK 暴露 `bda_sys_alarm_record_like_t`、raw wrapper 和少量 offset/helper，不提供完整
  alarm record struct。
- 普通 BDA 程序不要对未验证 slot 调用 `alarm_set`；probe 阶段优先使用
  `alarm_get` 读取 slot 0/1/2。

### SYS +0x0b8: `BDA_SYS_ALARM_DUE_GET_LIKE`

system function VA：`0x80015014`

当前证据：

- 函数打开 `a:\应用\数据\alarm.db`（GBK 路径），mode 是 `rb+`，并调用
  FS open/read/seek/write/close。
- 它不是单纯读取硬件 RTC 寄存器的小函数；旧 `time_get` 命名会误导调用者。
- C200 读取 0xda0 byte alarm database，按 0x2b8 byte record 排序/扫描。
- 命中 due record 时，会向调用者 out buffer 复制 `BDA_SYS_ALARM_RECORD_SIZE`
  byte；失败或没有可用记录时写 `out+0x00 = -1`。
- 比较逻辑读取 record `+0x11`、`+0x12` 两个 byte，也读取 record `+0x30`
  附近的 word 作为状态/模式类字段；这些字段还不足以正式命名。

开发建议：

- SDK 命名为 `bda_sys_alarm_due_get_like(out_alarm_data)`，调用方使用
  `bda_sys_alarm_record_like_t` 作为 buffer 类型。
- 调用后可用 `bda_sys_alarm_due_miss_like(record)` 检查 `out+0x00 == 0xffffffff`。
- 该 entry 会读写 alarm database，适合 probe 和闹钟类程序复刻原机流程；普通程序不要把它当成通用 clock API。

## 后续优先级

1. 对 `GUI+0x1a4` 创建 control、`GUI+0x084` frame 注册、`GUI+0x308/0x30c` draw lifecycle 做function-level slice。
2. 对 `FS+0x03c/0x040/0x044` 的 find-data 结构体命名。
3. 对 `SYS+0x06c/0x074/0x078` 音频流 API 结合 GAMEBOY.BDA 调用点继续确认。
4. 将确认后的结构体字段同步到 `bda_sdk.h`，并尽量减少 `_LIKE` 名称。
