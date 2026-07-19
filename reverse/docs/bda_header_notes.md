# BDA Header 与固件加载规则

本文只记录从 `fly-src-api/kj409588.bin` 静态还原并由 standalone BDA 动态测试的
格式。`kj409588.bin` 前 `0x40` byte 是封装头，后续 C200 image 按
`0x80004000` 加载。

## 固件校验路径

菜单扫描函数 `0x8002c4c0` 和启动函数 `0x8002c5b0` / `0x8002c878` 都先读取
`0x88` byte header。关键指令如下：

- `0x8002c4dc..0x8002c4f8`：前 11 个 u32 与 `0x44525744` XOR 解码。
- `0x8002c4fc..0x8002c514`：`0x84` checksum 与 `0x322d464b` XOR 解码。
- `0x8002c518..0x8002c52c`：对解码后的 `0x00..0x83` 共 `0x84` byte 求和。
- `0x8002c574..0x8002c584`：header 开头必须是 C string `"BBK"`。
- `0x8002c548..0x8002c554`：word `0x04` 必须是 `0x5d245562`。
- `0x8002c58c..0x8002c590`：checksum 必须等于 byte sum。
- `0x8002c598..0x8002c5a4`：category 低 16 位必须小于 `10`。
- `0x8002c530..0x8002c540`：标题 `"资源管理"` 被菜单明确过滤。
- `0x8002c718..0x8002c724`：启动时 version 低 16 位必须至少为 `0x0102`。

## Header 布局

```text
Offset  解码后含义
0x00    0x004b4242，little-endian bytes 为 "BBK\0"
0x04    0x5d245562，固件精确比较
0x08    0x01000102，builder 固定值；loader 检查 low16 >= 0x0102
0x0c    category；菜单/loader 检查 low16 < 10
0x10    文件大小 - 4
0x14    文件内 native entry offset
0x18    第一个 VX icon offset
0x1c    icon 0 size
0x20    icon 1 size
0x24    icon 2 size
0x28    icon 3 size
0x2c    GBK title，16 byte，NUL padding
0x3c    保留区；固件校验不读取，standalone builder 置零
0x84    encoded header checksum
0x88    icon/resource 起点
```

`0x00..0x2b` 的 11 个字段以 `decoded ^ 0x44525744` 存储。checksum 算法是：

1. 解码前 11 个 u32。
2. 对解码后的 `0x00..0x83` 每个 byte 求和，取低 32 位。
3. 写入 `sum ^ 0x322d464b` 到 `0x84`。

category 菜单映射由 C200 `0x80366444..0x803664e4` 的连续 GBK 标签和 54 个
原机 BDA header 交叉确认：

| low16 | 固件标签 | 总菜单项上限 | 启动预置 count | 原机应用类型 |
|---:|---|---:|---:|---|
| `1` | 听说 | `7` | `0` | 听力、会话、音标 |
| `2` | 语法 | `5` | `0` | 语法学习 |
| `3` | 阅读 | `9` | `0` | 阅读和资料内容 |
| `4` | 娱乐天地 | `10` | `0` | 游戏 |
| `5` | 考试 | `10` | `6` | 考试和课程辅导 |
| `6` | 背诵 | `8` | `0` | 单词记忆和背诵 |
| `7` | 词典 | `15` | `7` | 翻译和百科词典 |
| `8` | 娱乐 | `10` | `1` | 音乐、影音、相册和电子媒体 |
| `9` | 工具 | `20` | `4` | 计算器、记事本、时间和系统工具 |

容量来自 `0x80366834 + category * 10` 结构的第一个 halfword；扫描器在
`0x8002c1c8..0x8002c1d4` 比较 `current_count < capacity`。启动函数
`0x8002c378..0x8002c3cc` 设置预置 count。预置项包含固件硬编码入口，且扫描器会
跳过已硬编码的“模拟考场”“作文”“九门课程”，所以不能用“容量减 BDA 文件数”直接
计算剩余槽位。

固件只检查 low16 `< 10`，但 inventory 中没有发现对应 category `0` 的应用目录，
因此不能把 `0` 解释为已确认的菜单目录。原机还存在 `0x00010001`、`0x80000004` 和
`0x80000008`，说明高 16 位可能携带附加标志；当前公开 builder 只推荐简单值 `1..9`。

原机常见四个 VX icon size 为 `0x3218, 0x3218, 0x16e0, 0x1a60`，总布局使
entry offset 为 `0x95f8`。

## 加载与执行

固件不会执行 BDA 文件开头。启动函数执行以下步骤：

1. 从 header `0x14` 取得 entry file offset。
2. `0x8002c74c..0x8002c758` seek 到该 offset。
3. `0x8002c764..0x8002c77c` 把 entry 到 EOF 的全部内容读到 `0x81c00020`。
4. `0x8002c794` 刷新 cache。
5. `0x8002c79c` 直接 `jalr 0x81c00020`。

入口运行地址始终是 `0x81c00020`，不会随 file offset 平移。系统启动早期的
`0x8002b330` 已把 `0x80281680` 的 8 个 runtime seed word 复制到
`0x81c00000..0x81c0001f`，SDK 从固定地址取得 GUI/FS/SYS/MEM/RES table。

BDA 不是 ELF，loader 不做 relocation，也没有可靠的 `.bss` 清零阶段。因此 builder
把代码链接到 `0x81c00020`，并把 `.bss` 合并成文件里的零填充 `.data`。

## 唯一构建入口

```powershell
python -m bda_packer reverse\examples\hello_world_msgbox.c `
  --title HelloWorld `
  --category 9 `
  --icon-png path\to\icon.png `
  -o build\HelloWorld.bda

python -m bda_packer.validate build\HelloWorld.bda
```

打包器不接受任何已有 BDA，没有 template、patch、passthrough 或汇编打包模式。
`--icon-png` 可省略，此时生成内置诊断图标。

## 验证边界

`bda_validate.py` 复现上述固件条件，并额外检查文件大小字段、entry 范围、首条 MIPS
指令和四个 VX block。静态通过只证明文件会通过已还原的 loader 条件；系统 API
是否可用仍必须由独立 BDA 动态验证。

固件的“娱乐天地”（category 4）总容量为 10。动态测试中新增第 11 个合法 BDA 文件
不会展示，但把同一文件临时放到已有 category 4 菜单路径后，标题、图标和 native
entry 都能正常加载。这个现象属于菜单索引容量边界，不是 header 校验失败。其他分类
容量已经由 C200 静态确认，但尚未逐一填满做动态边界测试。
