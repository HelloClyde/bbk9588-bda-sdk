# C200 首页菜单索引线索

- source: `系统\数据\C200.bin`
- base: `0x80004000`

本报告由 `reverse/c200_menu_scan.py` 生成，记录 C200 中和首页/menu/deploy
相关的 GBK 字符串。`xref_count` 是保守的 `lui + addiu/ori` 静态匹配数量，
用于定位候选函数，不等于完整反汇编控制流。`candidate_function_va` 来自向前
搜索最近的 `addiu sp, sp, -imm` stack prologue，只是切片入口提示。
每个字符串最多展开前 2 个去重 use-site，完整数据见 JSON。

## 结论

- C200 同时包含 `a:\系统\数据\Config.inf` 和 `A:\应用\程序\*.bda`，但它们属于独立代码路径；字符串共存不能建立两者的索引关系。
- 首页 carousel 还硬编码了一批 `A:\应用\程序\*.bda` 路径，例如 `时间.bda`、`系统设置.bda`、`模拟考场.bda`、`作文.bda`、`九门课程.bda`、`电子图书.bda` 和 `我的相册.bda`。
- `Config.inf` 与内置 BDA 的目录扫描、category 分类、排序、展示和菜单索引无关；替换其 slot 不会改变 BDA 菜单。
- BDA 扫描器按分类执行 `current_count < capacity`；各分类容量不同，固件预置或硬编码菜单项也会占用容量。
- category 4 的第 11 个 BDA 不展示已有动态证据；其他分类容量目前是 C200 静态证据，尚未逐类做满容量动态测试。

## 分类容量表

容量来自 `0x80366834 + category * 10` 的首个 halfword；`initial_count` 是
`0x8002c378..0x8002c3cc` 初始化后的预置菜单项数，不等于 BDA 文件数。
扫描器还会跳过已硬编码的“模拟考场”“作文”“九门课程”，因此不能简单用
`capacity - BDA 文件数` 计算剩余槽位。

| category | 固件标签 | capacity | initial_count | state VA |
|---:|---|---:|---:|---:|
| `1` | 听说 | `7` | `0` | `0x8036683e` |
| `2` | 语法 | `5` | `0` | `0x80366848` |
| `3` | 阅读 | `9` | `0` | `0x80366852` |
| `4` | 娱乐天地 | `10` | `0` | `0x8036685c` |
| `5` | 考试 | `10` | `6` | `0x80366866` |
| `6` | 背诵 | `8` | `0` | `0x80366870` |
| `7` | 词典 | `15` | `7` | `0x8036687a` |
| `8` | 娱乐 | `10` | `1` | `0x80366884` |
| `9` | 工具 | `20` | `4` | `0x8036688e` |

## 字符串表

| file_off | VA | xrefs | text |
|---:|---:|---:|---|
| `0x274f14` | `0x80278f14` | 2 | `A:\应用\程序\时间.bda` |
| `0x277638` | `0x8027b638` | 13 | `a:\系统\数据\Config.inf` |
| `0x2778c4` | `0x8027b8c4` | 1 | `游戏` |
| `0x2778d6` | `0x8027b8d6` | 0 | `游戏` |
| `0x277af0` | `0x8027baf0` | 1 | `A:\应用\程序\*.bda` |
| `0x278018` | `0x8027c018` | 4 | `A:\应用\程序\时间.bda` |
| `0x278030` | `0x8027c030` | 4 | `没有找到下载程序` |
| `0x27806c` | `0x8027c06c` | 2 | `desktop` |
| `0x278074` | `0x8027c074` | 2 | `A:\应用\程序\系统设置.bda` |
| `0x2780ec` | `0x8027c0ec` | 1 | `A:\应用\程序\模拟考场.bda` |
| `0x278108` | `0x8027c108` | 1 | `A:\应用\程序\作文.bda` |
| `0x278120` | `0x8027c120` | 1 | `A:\应用\程序\九门课程.bda` |
| `0x27822c` | `0x8027c22c` | 1 | `A:\应用\程序\*.bda` |
| `0x278264` | `0x8027c264` | 1 | `没有找到下载程序，或者程序的版本不正确。` |
| `0x278264` | `0x8027c264` | 1 | `没有找到下载程序，或者程序的版本不正确。` |
| `0x2782b8` | `0x8027c2b8` | 1 | `没有找到下载程序` |
| `0x2793fa` | `0x8027d3fa` | 0 | `娱乐` |
| `0x27a820` | `0x8027e820` | 3 | `MENU` |
| `0x27bbc0` | `0x8027fbc0` | 2 | `MENU` |
| `0x27c918` | `0x80280918` | 1 | `A:\应用\程序\电子图书.bda` |
| `0x27c974` | `0x80280974` | 1 | `A:\应用\程序\情景会话.bda` |
| `0x27c994` | `0x80280994` | 1 | `A:\应用\程序\三步互动.bda` |
| `0x27c9b8` | `0x802809b8` | 1 | `A:\应用\程序\飞天音乐.bda` |
| `0x27c9e0` | `0x802809e0` | 1 | `A:\应用\程序\我的相册.bda` |
| `0x362480` | `0x80366480` | 0 | `娱乐` |
| `0x362540` | `0x80366540` | 0 | `娱乐` |
| `0x362558` | `0x80366558` | 0 | `工具` |
| `0x362668` | `0x80366668` | 0 | `游戏` |
| `0x362ac8` | `0x80366ac8` | 0 | `A:\应用\程序\三步互动.bda` |
| `0x362ce8` | `0x80366ce8` | 0 | `A:\应用\程序\飞天音乐.bda` |
| `0x363018` | `0x80367018` | 0 | `A:\应用\程序\我的相册.bda` |
| `0x364888` | `0x80368888` | 0 | `娱乐` |
| `0x364998` | `0x80368998` | 0 | `工具` |
| `0x364dd8` | `0x80368dd8` | 0 | `娱乐` |
| `0x364ee8` | `0x80368ee8` | 0 | `工具` |
| `0x3654fc` | `0x803694fc` | 0 | `娱乐` |
| `0x36c3a3` | `0x803703a3` | 0 | `娱乐` |
| `0x36c415` | `0x80370415` | 0 | `游戏` |

## Xref 候选调用点

### `A:\应用\程序\时间.bda`

- use `0x8001e328` (addiu), candidate_function_va `0x8001e304`

```asm
   8001e310: lui      $a0, 0x8028
   8001e314: addiu    $a0, $a0, -0x7104
   8001e318: sw       $ra, 0x70($sp)
   8001e31c: jal      0x800098c0
   8001e320: sw       $s1, 0x6c($sp)
   8001e324: lui      $a0, 0x8028
=> 8001e328: addiu    $a0, $a0, -0x70ec
   8001e32c: lui      $a1, 0x8028
   8001e330: jal      0x80170b68
   8001e334: addiu    $a1, $a1, -0x7160
   8001e338: move     $s1, $v0
   8001e33c: lui      $a0, 0x8028
   8001e340: addiu    $a0, $a0, -0x70d4
   8001e344: jal      0x800098c0
   8001e348: move     $a1, $v0
```

- use `0x8001f0c0` (addiu), candidate_function_va `0x8001effc`

```asm
   8001f0a8: jal      0x800dced0
   8001f0ac: move     $a3, $zero
   8001f0b0: j        0x8001f03c
   8001f0b4: move     $a0, $s1
   8001f0b8: lui      $a0, 0x8028
   8001f0bc: jal      0x8002c878
=> 8001f0c0: addiu    $a0, $a0, -0x70ec
   8001f0c4: j        0x8001f0a0
   8001f0c8: move     $a0, $s1
   8001f0cc: lui      $a1, 0x8028
   8001f0d0: addiu    $a1, $a1, -0x6ca4
   8001f0d4: lui      $a2, 0x8028
   8001f0d8: addiu    $a2, $a2, -0x6d80
   8001f0dc: jal      0x800c6544
   8001f0e0: addiu    $a3, $zero, 2
```

### `a:\系统\数据\Config.inf`

- use `0x8001f150` (addiu), candidate_function_va `0x8001f110`

```asm
   8001f138: jal      0x8016fe18
   8001f13c: addiu    $a0, $a0, -0x49d8
   8001f140: addiu    $v1, $zero, -1
   8001f144: beq      $v0, $v1, 0x8001f228
   8001f148: nop
   8001f14c: lui      $a0, 0x8028
=> 8001f150: addiu    $a0, $a0, -0x49c8
   8001f154: lui      $a1, 0x8028
   8001f158: jal      0x80170b68
   8001f15c: addiu    $a1, $a1, -0x49b0
   8001f160: beqz     $v0, 0x8001f200
   8001f164: move     $s0, $v0
   8001f168: beqz     $s1, 0x8001f220
   8001f16c: nop
   8001f170: addiu    $v0, $zero, 1
```

- use `0x8001f35c` (addiu), candidate_function_va `0x8001f344`

```asm
   8001f344: addiu    $sp, $sp, -0x1478
   8001f348: sw       $s4, 0x1470($sp)
   8001f34c: lui      $a1, 0x8028
   8001f350: addiu    $a1, $a1, -0x49a4
   8001f354: move     $s4, $a0
   8001f358: lui      $a0, 0x8028
=> 8001f35c: addiu    $a0, $a0, -0x49c8
   8001f360: sw       $s2, 0x1468($sp)
   8001f364: sw       $ra, 0x1474($sp)
   8001f368: sw       $s3, 0x146c($sp)
   8001f36c: sw       $s1, 0x1464($sp)
   8001f370: jal      0x80170b68
   8001f374: sw       $s0, 0x1460($sp)
   8001f378: beqz     $v0, 0x8001f7dc
   8001f37c: move     $s2, $v0
```

### `游戏`

- use `0x800211f8` (addiu), candidate_function_va `(unknown)`

```asm
   800211e0: move     $a0, $s4
   800211e4: addiu    $s0, $zero, -1
   800211e8: move     $a0, $s4
   800211ec: addiu    $a1, $zero, 0xa
   800211f0: addiu    $a2, $zero, 0x2a
   800211f4: lui      $a3, 0x8028
=> 800211f8: addiu    $a3, $a3, -0x473c
   800211fc: jal      0x800c0d40
   80021200: sw       $s0, 0x10($sp)
   80021204: move     $a0, $s4
   80021208: addiu    $a1, $zero, 0xa
   8002120c: lui      $a3, 0x8028
   80021210: addiu    $a3, $a3, -0x4730
   80021214: j        0x80021020
   80021218: addiu    $a2, $zero, 0x3e
```

### `A:\应用\程序\*.bda`

- use `0x80023b24` (addiu), candidate_function_va `0x800239f0`

```asm
   80023b0c: jal      0x80181870
   80023b10: nop
   80023b14: jal      0x8002c378
   80023b18: nop
   80023b1c: lui      $a0, 0x8028
   80023b20: jal      0x8002c0c0
=> 80023b24: addiu    $a0, $a0, -0x4510
   80023b28: jal      0x800ce090
   80023b2c: move     $a0, $s2
   80023b30: jal      0x800dd31c
   80023b34: move     $a0, $s2
   80023b38: j        0x80023a58
   80023b3c: move     $a0, $s2
   80023b40: jal      0x800e1c84
   80023b44: nop
```

### `A:\应用\程序\时间.bda`

- use `0x80026ae4` (addiu), candidate_function_va `(unknown)`

```asm
   80026acc: move     $a0, $s2
   80026ad0: sw       $a3, 0x14($a1)
   80026ad4: jal      0x800de190
   80026ad8: addiu    $a1, $zero, 1
   80026adc: lui      $a0, 0x8028
   80026ae0: jal      0x8002c878
=> 80026ae4: addiu    $a0, $a0, -0x3fe8
   80026ae8: bnez     $v0, 0x80026894
   80026aec: move     $a0, $s2
   80026af0: lui      $a1, 0x8028
   80026af4: addiu    $a1, $a1, -0x3fd0
   80026af8: lui      $a2, 0x8028
   80026afc: addiu    $a2, $a2, -0x3fbc
   80026b00: jal      0x800c6544
   80026b04: move     $a3, $zero
```

- use `0x80026c08` (addiu), candidate_function_va `0x80026b20`

```asm
   80026bf0: sw       $zero, 0x14($s1)
   80026bf4: sw       $a3, 0x14($s1)
   80026bf8: jal      0x800de190
   80026bfc: addiu    $a1, $zero, 1
   80026c00: lui      $a0, 0x8028
   80026c04: jal      0x8002c878
=> 80026c08: addiu    $a0, $a0, -0x3fe8
   80026c0c: bnez     $v0, 0x80026bdc
   80026c10: move     $a0, $s2
   80026c14: lui      $a1, 0x8028
   80026c18: addiu    $a1, $a1, -0x3fd0
   80026c1c: lui      $a2, 0x8028
   80026c20: addiu    $a2, $a2, -0x3fbc
   80026c24: jal      0x800c6544
   80026c28: move     $a3, $zero
```

### `没有找到下载程序`

- use `0x80026af4` (addiu), candidate_function_va `(unknown)`

```asm
   80026adc: lui      $a0, 0x8028
   80026ae0: jal      0x8002c878
   80026ae4: addiu    $a0, $a0, -0x3fe8
   80026ae8: bnez     $v0, 0x80026894
   80026aec: move     $a0, $s2
   80026af0: lui      $a1, 0x8028
=> 80026af4: addiu    $a1, $a1, -0x3fd0
   80026af8: lui      $a2, 0x8028
   80026afc: addiu    $a2, $a2, -0x3fbc
   80026b00: jal      0x800c6544
   80026b04: move     $a3, $zero
   80026b08: move     $a0, $s2
   80026b0c: move     $a1, $zero
   80026b10: jal      0x800ccf64
   80026b14: addiu    $a2, $zero, 1
```

- use `0x80026c18` (addiu), candidate_function_va `0x80026b20`

```asm
   80026c00: lui      $a0, 0x8028
   80026c04: jal      0x8002c878
   80026c08: addiu    $a0, $a0, -0x3fe8
   80026c0c: bnez     $v0, 0x80026bdc
   80026c10: move     $a0, $s2
   80026c14: lui      $a1, 0x8028
=> 80026c18: addiu    $a1, $a1, -0x3fd0
   80026c1c: lui      $a2, 0x8028
   80026c20: addiu    $a2, $a2, -0x3fbc
   80026c24: jal      0x800c6544
   80026c28: move     $a3, $zero
   80026c2c: move     $a0, $s2
   80026c30: move     $a1, $zero
   80026c34: jal      0x800ccf64
   80026c38: addiu    $a2, $zero, 1
```

### `desktop`

- use `0x80028058` (addiu), candidate_function_va `0x80028048`

```asm
   80028040: j        0x80027f48
   80028044: addiu    $v1, $zero, 0x64
   80028048: addiu    $sp, $sp, -0x70
   8002804c: lui      $v0, 0x800
   80028050: sw       $v0, 0x30($sp)
   80028054: lui      $v1, 0x8028
=> 80028058: addiu    $v1, $v1, -0x3f94
   8002805c: lui      $v0, 0x804a
   80028060: lw       $v0, 0x6b88($v0)
   80028064: sw       $v1, 0x38($sp)
   80028068: lui      $v1, 0x804a
   8002806c: lw       $v1, 0x6b8c($v1)
   80028070: addiu    $a0, $zero, 0xf
   80028074: sw       $v0, 0x54($sp)
   80028078: lui      $v0, 0x8002
```

- use `0x8002bc90` (addiu), candidate_function_va `0x8002bc80`

```asm
   8002bc78: jr       $ra
   8002bc7c: sb       $zero, 0xe($a0)
   8002bc80: addiu    $sp, $sp, -0x70
   8002bc84: lui      $v0, 0x800
   8002bc88: sw       $v0, 0x30($sp)
   8002bc8c: lui      $v1, 0x8028
=> 8002bc90: addiu    $v1, $v1, -0x3f94
   8002bc94: lui      $v0, 0x804a
   8002bc98: lw       $v0, 0x6b88($v0)
   8002bc9c: sw       $v1, 0x38($sp)
   8002bca0: lui      $v1, 0x804a
   8002bca4: lw       $v1, 0x6b8c($v1)
   8002bca8: addiu    $a0, $zero, 0xf
   8002bcac: sw       $v0, 0x54($sp)
   8002bcb0: lui      $v0, 0x8003
```

### `A:\应用\程序\系统设置.bda`

- use `0x80029a84` (addiu), candidate_function_va `0x800299a8`

```asm
   80029a6c: jal      0x800de190
   80029a70: sw       $v0, ($s0)
   80029a74: jal      0x80022944
   80029a78: addiu    $a0, $zero, 1
   80029a7c: lui      $a0, 0x8028
   80029a80: jal      0x8002c878
=> 80029a84: addiu    $a0, $a0, -0x3f8c
   80029a88: jal      0x80022944
   80029a8c: move     $a0, $zero
   80029a90: j        0x80029a4c
   80029a94: move     $a0, $s1
   80029a98: addiu    $v0, $zero, 1
   80029a9c: move     $a0, $s1
   80029aa0: sw       $v0, ($s0)
   80029aa4: jal      0x800de190
```

- use `0x80029f34` (addiu), candidate_function_va `0x80029e48`

```asm
   80029f1c: jal      0x800de190
   80029f20: sw       $v0, ($s1)
   80029f24: jal      0x80022944
   80029f28: addiu    $a0, $zero, 1
   80029f2c: lui      $a0, 0x8028
   80029f30: jal      0x8002c878
=> 80029f34: addiu    $a0, $a0, -0x3f8c
   80029f38: jal      0x80022944
   80029f3c: move     $a0, $zero
   80029f40: j        0x80029efc
   80029f44: move     $a0, $s0
   80029f48: jal      0x800bce50
   80029f4c: move     $a0, $s0
   80029f50: move     $s2, $v0
   80029f54: lw       $v1, 4($s1)
```

### `A:\应用\程序\模拟考场.bda`

- use `0x8002b3a4` (addiu), candidate_function_va `0x8002b39c`

```asm
   8002b38c: nop
   8002b390: lw       $ra, 0x10($sp)
   8002b394: jr       $ra
   8002b398: addiu    $sp, $sp, 0x18
   8002b39c: addiu    $sp, $sp, -0x18
   8002b3a0: lui      $a0, 0x8028
=> 8002b3a4: addiu    $a0, $a0, -0x3f14
   8002b3a8: move     $a1, $zero
   8002b3ac: sw       $ra, 0x10($sp)
   8002b3b0: jal      0x8002c5b0
   8002b3b4: move     $a2, $zero
   8002b3b8: lw       $ra, 0x10($sp)
   8002b3bc: jr       $ra
   8002b3c0: addiu    $sp, $sp, 0x18
   8002b3c4: addiu    $sp, $sp, -0x18
```

### `A:\应用\程序\作文.bda`

- use `0x8002b3cc` (addiu), candidate_function_va `0x8002b3c4`

```asm
   8002b3b4: move     $a2, $zero
   8002b3b8: lw       $ra, 0x10($sp)
   8002b3bc: jr       $ra
   8002b3c0: addiu    $sp, $sp, 0x18
   8002b3c4: addiu    $sp, $sp, -0x18
   8002b3c8: lui      $a0, 0x8028
=> 8002b3cc: addiu    $a0, $a0, -0x3ef8
   8002b3d0: move     $a1, $zero
   8002b3d4: sw       $ra, 0x10($sp)
   8002b3d8: jal      0x8002c5b0
   8002b3dc: move     $a2, $zero
   8002b3e0: lw       $ra, 0x10($sp)
   8002b3e4: jr       $ra
   8002b3e8: addiu    $sp, $sp, 0x18
   8002b3ec: addiu    $sp, $sp, -0x18
```

### `A:\应用\程序\九门课程.bda`

- use `0x8002b3f4` (addiu), candidate_function_va `0x8002b3ec`

```asm
   8002b3dc: move     $a2, $zero
   8002b3e0: lw       $ra, 0x10($sp)
   8002b3e4: jr       $ra
   8002b3e8: addiu    $sp, $sp, 0x18
   8002b3ec: addiu    $sp, $sp, -0x18
   8002b3f0: lui      $a0, 0x8028
=> 8002b3f4: addiu    $a0, $a0, -0x3ee0
   8002b3f8: move     $a1, $zero
   8002b3fc: sw       $ra, 0x10($sp)
   8002b400: jal      0x8002c5b0
   8002b404: move     $a2, $zero
   8002b408: lw       $ra, 0x10($sp)
   8002b40c: jr       $ra
   8002b410: addiu    $sp, $sp, 0x18
   8002b414: addiu    $sp, $sp, -0x18
```

### `A:\应用\程序\*.bda`

- use `0x8002c440` (addiu), candidate_function_va `0x8002c438`

```asm
   8002c428: lui      $v1, 0x8037
   8002c42c: addiu    $v1, $v1, -0x3134
   8002c430: lui      $v0, 0x8037
   8002c434: addiu    $v0, $v0, -0x1fdc
   8002c438: addiu    $sp, $sp, -0x18
   8002c43c: lui      $a0, 0x8028
=> 8002c440: addiu    $a0, $a0, -0x3dd4
   8002c444: sw       $a2, 0x14($a1)
   8002c448: sw       $v1, 0x1c($a1)
   8002c44c: sw       $v0, 0x20($a1)
   8002c450: sw       $a2, ($a1)
   8002c454: sw       $ra, 0x10($sp)
   8002c458: jal      0x8002c0c0
   8002c45c: nop
   8002c460: lw       $ra, 0x10($sp)
```

### `没有找到下载程序，或者程序的版本不正确。`

- use `0x8002c6a4` (addiu), candidate_function_va `0x8002c5b0`

```asm
   8002c68c: lui      $v0, 0x5d24
   8002c690: ori      $v0, $v0, 0x5562
   8002c694: beq      $v1, $v0, 0x8002c700
   8002c698: nop
   8002c69c: move     $a0, $zero
   8002c6a0: lui      $a1, 0x8028
=> 8002c6a4: addiu    $a1, $a1, -0x3d9c
   8002c6a8: lui      $a2, 0x8028
   8002c6ac: addiu    $a2, $a2, -0x3d70
   8002c6b0: jal      0x800c6544
   8002c6b4: move     $a3, $zero
   8002c6b8: jal      0x8017a928
   8002c6bc: move     $a0, $s1
   8002c6c0: lui      $a0, 0x8048
   8002c6c4: lw       $a0, -0x7c38($a0)
```

### `没有找到下载程序，或者程序的版本不正确。`

- use `0x8002c6a4` (addiu), candidate_function_va `0x8002c5b0`

```asm
   8002c68c: lui      $v0, 0x5d24
   8002c690: ori      $v0, $v0, 0x5562
   8002c694: beq      $v1, $v0, 0x8002c700
   8002c698: nop
   8002c69c: move     $a0, $zero
   8002c6a0: lui      $a1, 0x8028
=> 8002c6a4: addiu    $a1, $a1, -0x3d9c
   8002c6a8: lui      $a2, 0x8028
   8002c6ac: addiu    $a2, $a2, -0x3d70
   8002c6b0: jal      0x800c6544
   8002c6b4: move     $a3, $zero
   8002c6b8: jal      0x8017a928
   8002c6bc: move     $a0, $s1
   8002c6c0: lui      $a0, 0x8048
   8002c6c4: lw       $a0, -0x7c38($a0)
```

### `没有找到下载程序`

- use `0x8002c85c` (addiu), candidate_function_va `0x8002c5b0`

```asm
   8002c844: jal      0x800de190
   8002c848: addiu    $a1, $zero, 1
   8002c84c: j        0x8002c794
   8002c850: nop
   8002c854: move     $a0, $zero
   8002c858: lui      $a1, 0x8028
=> 8002c85c: addiu    $a1, $a1, -0x3d48
   8002c860: lui      $a2, 0x8028
   8002c864: addiu    $a2, $a2, -0x3d70
   8002c868: jal      0x800c6544
   8002c86c: move     $a3, $zero
   8002c870: j        0x8002c6c0
   8002c874: nop
   8002c878: addiu    $sp, $sp, -0xe0
   8002c87c: lui      $a1, 0x8028
```

### `MENU`

- use `0x8003ec84` (addiu), candidate_function_va `(unknown)`

```asm
   8003ec6c: sw       $v1, -0x750c($at)
   8003ec70: lui      $v0, 0x800
   8003ec74: addiu    $v1, $zero, 8
   8003ec78: sw       $v0, 0x38($sp)
   8003ec7c: sw       $v1, 0x3c($sp)
   8003ec80: lui      $v0, 0x8028
=> 8003ec84: addiu    $v0, $v0, -0x17e0
   8003ec88: sw       $s2, 4($a0)
   8003ec8c: lui      $v1, 0x8005
   8003ec90: addiu    $v1, $v1, -0x7634
   8003ec94: sw       $s0, 8($a0)
   8003ec98: sw       $v0, 0x40($sp)
   8003ec9c: sw       $v1, 0x50($sp)
   8003eca0: sw       $zero, 0x18($sp)
   8003eca4: sw       $zero, 0x1c($sp)
```

- use `0x8003fb68` (addiu), candidate_function_va `(unknown)`

```asm
   8003fb50: sw       $v1, -0x750c($at)
   8003fb54: lui      $v0, 0x800
   8003fb58: addiu    $v1, $zero, 8
   8003fb5c: sw       $v0, 0x38($sp)
   8003fb60: sw       $v1, 0x3c($sp)
   8003fb64: lui      $v0, 0x8028
=> 8003fb68: addiu    $v0, $v0, -0x17e0
   8003fb6c: sw       $s6, 4($a0)
   8003fb70: lui      $v1, 0x8005
   8003fb74: addiu    $v1, $v1, -0x7634
   8003fb78: sw       $s3, 8($a0)
   8003fb7c: sw       $v0, 0x40($sp)
   8003fb80: sw       $v1, 0x50($sp)
   8003fb84: sw       $zero, 0x18($sp)
   8003fb88: sw       $zero, 0x1c($sp)
```

### `MENU`

- use `0x8004bd30` (addiu), candidate_function_va `0x8004bc90`

```asm
   8004bd18: jal      0x800ccf64
   8004bd1c: addiu    $a2, $zero, 1
   8004bd20: lui      $v0, 0x800
   8004bd24: sw       $v0, 0x30($sp)
   8004bd28: addiu    $v1, $zero, 8
   8004bd2c: lui      $v0, 0x8028
=> 8004bd30: addiu    $v0, $v0, -0x440
   8004bd34: sw       $v1, 0x34($sp)
   8004bd38: sw       $v0, 0x38($sp)
   8004bd3c: lui      $v1, 0x8005
   8004bd40: addiu    $v1, $v1, -0x648
   8004bd44: addiu    $v0, $zero, 0x87
   8004bd48: addiu    $a0, $zero, 0xf
   8004bd4c: sw       $v1, 0x48($sp)
   8004bd50: sw       $v0, 0x50($sp)
```

- use `0x8004be30` (addiu), candidate_function_va `0x8004bdec`

```asm
   8004be18: sw       $v1, 0x48($sp)
   8004be1c: lui      $v0, 0x800
   8004be20: lui      $v1, 0x8048
   8004be24: lw       $v1, 0x3078($v1)
   8004be28: sw       $v0, 0x30($sp)
   8004be2c: lui      $v0, 0x8028
=> 8004be30: addiu    $v0, $v0, -0x440
   8004be34: sw       $v0, 0x38($sp)
   8004be38: addiu    $v0, $zero, 1
   8004be3c: sw       $s1, 0x6c($sp)
   8004be40: sw       $s0, 0x68($sp)
   8004be44: sw       $ra, 0x70($sp)
   8004be48: sw       $zero, 0x10($sp)
   8004be4c: sw       $zero, 0x14($sp)
   8004be50: sw       $zero, 0x18($sp)
```

### `A:\应用\程序\电子图书.bda`

- use `0x80056210` (addiu), candidate_function_va `0x800560ec`

```asm
   800561f8: lui      $a0, 0x8048
   800561fc: addiu    $a0, $a0, 0x2e64
   80056200: lui      $a1, 0x8048
   80056204: jal      0x80241e80
   80056208: addiu    $a1, $a1, 0x2d80
   8005620c: lui      $a0, 0x8028
=> 80056210: addiu    $a0, $a0, 0x918
   80056214: jal      0x8002c878
   80056218: nop
   8005621c: lui      $a0, 0x8048
   80056220: addiu    $a0, $a0, 0x2e64
   80056224: lui      $a1, 0x8028
   80056228: jal      0x80006bac
   8005622c: addiu    $a1, $a1, -0xa10
   80056230: jal      0x80022938
```

### `A:\应用\程序\情景会话.bda`

- use `0x80056334` (addiu), candidate_function_va `0x800560ec`

```asm
   8005631c: addiu    $a0, $a0, 0x2e64
   80056320: lui      $a1, 0x8048
   80056324: jal      0x80241e80
   80056328: addiu    $a1, $a1, 0x2d80
   8005632c: lui      $a0, 0x8028
   80056330: j        0x80056214
=> 80056334: addiu    $a0, $a0, 0x974
   80056338: lui      $a1, 0x8028
   8005633c: addiu    $a1, $a1, 0x990
   80056340: jal      0x80241fd0
   80056344: addiu    $a0, $sp, 0x10
   80056348: bnez     $v0, 0x8005639c
   8005634c: nop
   80056350: jal      0x8005b844
   80056354: nop
```

### `A:\应用\程序\三步互动.bda`

- use `0x80056398` (addiu), candidate_function_va `0x800560ec`

```asm
   80056380: addiu    $a0, $a0, 0x2e64
   80056384: lui      $a1, 0x8048
   80056388: jal      0x80241e80
   8005638c: addiu    $a1, $a1, 0x2d80
   80056390: lui      $a0, 0x8028
   80056394: j        0x80056214
=> 80056398: addiu    $a0, $a0, 0x994
   8005639c: lui      $a1, 0x8028
   800563a0: addiu    $a1, $a1, 0x9b0
   800563a4: jal      0x80241fd0
   800563a8: addiu    $a0, $sp, 0x10
   800563ac: beqz     $v0, 0x800563cc
   800563b0: nop
   800563b4: lui      $a1, 0x8028
   800563b8: addiu    $a1, $a1, 0x9b4
```

### `A:\应用\程序\飞天音乐.bda`

- use `0x80056414` (addiu), candidate_function_va `(unknown)`

```asm
   800563fc: addiu    $a0, $a0, 0x2e64
   80056400: lui      $a1, 0x8048
   80056404: jal      0x80241e80
   80056408: addiu    $a1, $a1, 0x2d80
   8005640c: lui      $a0, 0x8028
   80056410: j        0x80056214
=> 80056414: addiu    $a0, $a0, 0x9b8
   80056418: lui      $a1, 0x8028
   8005641c: addiu    $a1, $a1, 0x9d4
   80056420: jal      0x80241fd0
   80056424: addiu    $a0, $sp, 0x10
   80056428: beqz     $v0, 0x800563cc
   8005642c: nop
   80056430: lui      $a1, 0x8028
   80056434: addiu    $a1, $a1, 0x9d8
```

### `A:\应用\程序\我的相册.bda`

- use `0x80056498` (addiu), candidate_function_va `(unknown)`

```asm
   80056480: addiu    $a0, $a0, 0x2e64
   80056484: lui      $a1, 0x8048
   80056488: jal      0x80241e80
   8005648c: addiu    $a1, $a1, 0x2d80
   80056490: lui      $a0, 0x8028
   80056494: j        0x80056214
=> 80056498: addiu    $a0, $a0, 0x9e0
   8005649c: beqz     $v0, 0x800564b0
   800564a0: addiu    $v1, $a0, 0x20
   800564a4: addiu    $a2, $a2, 1
   800564a8: j        0x800561a8
   800564ac: sb       $v1, ($a1)
   800564b0: j        0x800561a4
   800564b4: sb       $a0, ($a1)
   800564b8: addiu    $sp, $sp, -0x3d0
```
