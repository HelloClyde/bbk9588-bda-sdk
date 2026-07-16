# Message Box API

## 已验证接口

```c
int bda_msgbox(const char *title, const char *message);
int bda_msgbox_ex(void *parent, const char *title, const char *message, u32 flags);
```

固件绑定信息：

```text
SDK macro       BDA_GUI_MSGBOX
runtime table   GUI +0x2b8
table slot VA   0x80281118
system function 0x800c6544
```

C200 的实际参数顺序是 `parent,message,title,flags`。SDK wrapper 对开发者公开
`title,message` 顺序，并在内部完成转换。最小用法：

```c
#include "bda_sdk.h"

__attribute__((section(".text.bda_main")))
int bda_main(void) {
    bda_msgbox("HelloWorld", "HelloWorld");
    return 0;
}
```

## 注意点

- `title` 和 `message` 必须在调用期间保持有效，并以 NUL 结尾。
- 最简单的调用使用 `parent=0, flags=0`，即 `bda_msgbox()`。
- 本次验证只确认系统能显示标题、正文和确认按钮；return value、非零 `flags`、
  非空 `parent` 和多按钮行为没有动态验证，不能依赖。
- Message box 自己建立模态 GUI，不要求应用预先创建 window/frame，适合作为新
  standalone BDA 的第一个系统 API smoke。

## 动态验证

测试源码是 `example/basic/hello_world/hello_world_msgbox.c`。构建命令：

```powershell
python -m bda_packer example\basic\hello_world\hello_world_msgbox.c `
  --title HelloWorld `
  --category 9 `
  -o example\basic\hello_world\HelloWorld.bda

python -m bda_packer.validate example\basic\hello_world\HelloWorld.bda
```

当前预编译样例大小为 `38488` byte，entry file offset 为 `0x95f8`，运行 VA 为
`0x81c00020`，SHA-256 为
`54ECDB37508C7CF3B183476CE314FDC1BD1B353BC0381DF5C0BC9A545FC57DCB`。

动态验证时使用的是相同源码生成的 category 4 测试包，并额外带测试图标；该历史包
SHA-256 为 `A91EF6F90A2CE32E7F4F1CEB31E4CDCAC3499F4A8B630DD03BA9DFA45E9E0B60`。
验证使用原版 NAND 的 frontend persistent worker copy。BDA 只通过
`/api/files/import` 写入，通过 `/api/files/export` 导出后哈希与本地生成物一致。
category 4 原有菜单已经达到 10 项；新增第 11 个文件不会展示。将同一生成物临时放入
已知 category 4 菜单路径后，菜单显示自定义图标和 `HelloWorld` 标题，点选后弹出：

![HelloWorld message box](assets/msgbox_hello_world_verified.png)

QEMU 在弹窗显示后保持 `running=true`、`stop_reason=null`。测试完成后已通过文件 API
恢复被临时替换的 worker 文件；原版 NAND SHA-256 保持
`0D01C5A1B547419E0E76CB8BAF9AA1951FEC27B4629033D33EFEB99C3C97F103`。

## 验证边界

本页证明 standalone header、VX icon、flat code loader 和 `GUI+0x2b8` 的最小显示路径
可以共同工作。它不证明其他 GUI wrapper、window lifecycle 或 message box 的高级选项
已经可用。
