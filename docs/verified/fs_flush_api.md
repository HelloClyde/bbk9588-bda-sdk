# 全局文件 flush API

`bda_fs_flush_all()` 已在 BBK 9588 C200 固件的 8013 模拟器中通过有 flush/无 flush
强制断电 A/B 测试。它把所有当前打开文件对象的脏数据和文件 metadata 写回，但不关闭
任何句柄。

## API

```c
void bda_fs_flush_all(void);
```

对应固件表项：

```text
FS +0x074  C200 0x8017b0d0
```

这个入口不读取参数。C200 会取得全局文件系统锁，遍历最多 100 个 open-file slot，
并对带 dirty flag 的对象执行 writeback。因此它是全局操作，不等价于
`fflush(file)`，也不能接受 file handle。

底层入口在本次成功路径返回 `0`，但其原始返回值还混合内部状态聚合结果。公开
wrapper 因而使用 `void`，不把尚未完整定义的固件错误码固化成 SDK 契约。需要判断某个
文件的写入状态时，应先检查 write 返回长度，并在 flush 后调用 `bda_fs_error(file)`。

## 用法

```c
int file = bda_fs_fopen_raw(path, "wb");
int wrote;

if (!bda_fs_file_is_valid(file)) {
    return 0;
}

wrote = bda_fs_write_raw(file, data, size);
if (wrote != (int)size) {
    (void)bda_fs_close_raw(file);
    return 0;
}

bda_fs_flush_all();
if (bda_fs_error(file) != 0) {
    (void)bda_fs_close_raw(file);
    return 0;
}

/* flush 不关闭 file；仍需正常收尾。 */
return bda_fs_close_raw(file) == 0;
```

普通程序仍应为每个成功打开的句柄调用 `bda_fs_close_raw()`。`flush_all()` 适合需要在
保持句柄打开的同时建立显式持久化点的存档、配置和日志流程，不应代替正常 close。

## 强制断电 A/B 验证

测试源码和预编译 BDA：

- `example/filesystem/fs_flush/fs_flush_power_demo.c`
- `example/filesystem/fs_flush/FsFlush.bda`

第一阶段在全新的专用 `bda_test` NAND 中执行：

1. 创建并关闭阶段标记，保证重启后进入第二阶段。
2. 打开 `F74YES.DAT`，写入确定性的 4096-byte payload。
3. 调用 `bda_fs_flush_all()`，保持该句柄打开。
4. 再打开 `F74NO.DAT` 并写入相同 payload，作为无 flush 对照，也保持句柄打开。
5. BDA 停在消息框时调用模拟器 `force-stop`，不执行应用 close 或固件安全关机。
6. 使用同一 NAND 重启，再次运行 BDA 并分别读回两份文件。

第一阶段屏幕结果：

```text
PHASE1 READY
yes write=4096 flush=done err=0
no write=4096 err=0
FORCE STOP NOW
```

第二阶段结果：

| 文件 | flush 时机 | 断电后长度 | 逐字节匹配 |
|---|---|---:|---:|
| `F74YES.DAT` | 写入后调用 `FS+0x074` | 4096 | 1 |
| `F74NO.DAT` | 在该次 flush 后才写入 | 0 | 0 |

停止模拟器后直接读取 NAND 得到相同结果：有 flush 文件 SHA-256 为
`4bdb590eaadb6efc9fc001b29f09b2af9edf289898cd204289fcf5557d97cb87`；无 flush
对照是 0-byte 文件，SHA-256 为
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
完整文本记录见 [`assets/fs_flush_power_probe_result.txt`](assets/fs_flush_power_probe_result.txt)。

这组对照证明：在当前模拟器和固件组合中，`FS+0x074` 会把已经打开的脏文件数据及
长度写入 NAND；仅调用 write 而不 flush/close，强制断电后只留下 0-byte 目录项。

## 验证边界

- 当前动态结论覆盖 `bbk9588-emulator-v0.1.5`、kj409588/C200 固件和 `A:` FAT 文件系统。
- 原机 `模拟考场.bda` 也存在一次明确分类的无参数 `FS+0x074` 调用，但原机调用点本身
  不替代独立动态验证。
- 尚未在 9588 真机上执行物理断电 A/B 测试，不能把模拟器结果扩张为真机掉电保证。
- 这是全局同步点，会处理其他打开的脏文件；不要在高频输入、绘图或音频回调中调用。
- truncate、rename 原子替换和目录项断电一致性仍是独立问题，不由本 API 保证。

