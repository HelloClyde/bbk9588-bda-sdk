# 文件写入 API

本文只记录已经通过 BDA 运行和 worker NAND 导出验证的文件写入接口。

## API 定义

```c
int bda_fs_fopen_raw(const char *path, const char *mode);
int bda_fs_file_is_valid(int file);
int bda_fs_fwrite_raw(
    const void *buffer,
    bda_size_t size,
    bda_size_t count,
    int file
);
int bda_fs_write_raw(int file, const void *buffer, bda_size_t size);
int bda_fs_fread_raw(
    void *buffer,
    bda_size_t size,
    bda_size_t count,
    int file
);
int bda_fs_read_raw(int file, void *buffer, bda_size_t size);
int bda_fs_tell_raw(int file);
int bda_fs_error(int file);
int bda_fs_close_raw(int file);
```

对应固件表项：

```text
FS +0x000  fopen-like   C200 0x80170b68
FS +0x004  fclose-like  C200 0x8017a928
FS +0x008  fread-like   C200 0x8017aa24
FS +0x00c  fwrite-like  C200 0x8017ab2c
FS +0x014  ftell-like   C200 0x8017ac18
FS +0x01c  ferror-like  C200 0x8017acfc
```

`FS+0x00c` 的 MIPS 参数顺序已经由 C200 和雷霆战机调用点交叉确认：

```text
a0 = buffer
a1 = size
a2 = count
a3 = file
```

底层返回成功写入的元素数量。`bda_fs_write_raw(file, buffer, bytes)` 固定使用
`size=1,count=bytes`，因此其成功返回值等于写入 byte 数量。

## 最小用法

```c
static const char path[] =
    "A:\\\xd3\xa6\xd3\xc3\\\xca\xfd\xbe\xdd\\\xd3\xce\xcf\xb7\\SAVE.TXT";
static const char payload[] = "hello\r\n";

int write_save(void) {
    int file = bda_fs_fopen_raw(path, "wb");
    int wrote;

    if (!bda_fs_file_is_valid(file)) {
        return 0;
    }

    wrote = bda_fs_write_raw(file, payload, sizeof(payload) - 1);
    if (wrote != (int)(sizeof(payload) - 1)) {
        (void)bda_fs_close_raw(file);
        return 0;
    }

    return bda_fs_close_raw(file) == 0;
}
```

需要保持 `fwrite` 的 size/count 语义时直接使用：

```c
int wrote = bda_fs_fwrite_raw(records, sizeof(records[0]), record_count, file);
if (wrote != (int)record_count) {
    /* 部分写入或失败 */
}
```

## 句柄判断

成功返回值是高地址 file-object pointer，例如实测值按 signed `int` 显示为
`-2137637704`。因此以下判断是错误的：

```c
if (file <= 0) { /* 错误：会拒绝有效高地址 handle */ }
```

已确认失败哨兵是 `0` 或 `0xffffffff`。必须使用：

```c
if (!bda_fs_file_is_valid(file)) {
    /* open failed */
}
```

只对有效 handle 调用 write/tell/error/close。不要 close 失败哨兵。

## 路径和模式

- 固件路径使用反斜杠。
- ASCII 路径可直接写入 C string。
- 中文目录按 GBK byte string 编写；示例中的 `应用/数据/游戏` 已给出对应 byte。
- `A:` 绝对路径和根相对路径都已通过写入验证。
- 模拟器写入闭环覆盖新建或覆盖模式 `"wb"`，读回验证使用 `"rb"`。
- `TouchStageV11.bda` 又在真机使用 `"wb"` 建立 `TOUCHDBG.TXT`，随后以 `"ab"`
  逐行追加并在每行后立即 close；中间版本死机时已写出的日志仍可读取。因此当前固件的
  `"ab"` 追加模式也进入已验证范围。
- 目标父目录必须已经存在。写文件 API 不会自动递归创建目录。

## 错误处理

- `write` 返回 `0` 表示没有写入元素或失败，不要只检查 `-1`。
- `write` 返回值小于期望 count 时按部分写入处理。
- `tell` 返回 `0` 既可能是文件开头，也可能是错误路径，需要结合 write/error 判断。
- 每个成功 open 都必须 close，包括 write 失败分支。
- 不要在窗口过程或按键钩子里做长期文件 IO；优先记录状态，再在应用主循环中写入。

## 验证记录

测试 BDA：`example/filesystem/fs_write/fs_write_demo.c`

预编译产物：`example/filesystem/fs_write/FsWrite.bda`

测试流程：

1. 从模拟器原版 NAND 启动，由模拟器创建 worker copy。
2. 通过文件接口把测试 BDA 放入 `/应用/程序/雷霆战机.bda`。
3. BDA 分别写入 `A:` 路径和根相对路径。
4. BDA 内部执行 write、tell、close、reopen、read 和逐字节比较。
5. 停止 QEMU 提交 worker，再通过 NAND 文件接口导出两个结果文件。

BDA 显示结果：

```text
A: write=19 tell=19 error=0 read=19 match=1
R: write=19 tell=19 error=0 read=19 match=1
```

NAND 导出结果：

```text
SDKWRA.TXT  size=19  match=true
SDKWRR.TXT  size=19  match=true
payload: BDA-FS-WRITE-9588\r\n
SHA-256: 44f98eda68a182a6222469f93bc9f008747fd942d966549328dfe25792180f76
```

这证明 `FS+0x00c` 的参数顺序、返回值、close 后可见性和 worker NAND 持久化路径均已闭环。

V11 的真机日志还确认了“open append、write、立即 close”的实时诊断模式。它适合低频
生命周期和输入事件，不适合在每次空闲 event pump 中写一行；早期版本因此出现明显卡顿。
