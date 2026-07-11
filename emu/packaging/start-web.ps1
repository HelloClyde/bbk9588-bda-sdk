param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [ValidateSet("nand", "c200", "uboot")]
    [string]$BootMode = "nand",
    [switch]$NoOpenBrowser,
    [switch]$RebuildImages,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Resolve-PythonExe {
    $bundled = Join-Path $Root "python\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }
    foreach ($name in @("python", "py")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }
    throw "Python was not found. Use the release package with bundled Python, or install Python 3.11+ and retry."
}

function Test-ExtraArgOption([string]$Name) {
    foreach ($arg in $ExtraArgs) {
        if ($arg -eq $Name -or $arg.StartsWith("$Name=")) {
            return $true
        }
    }
    return $false
}

function Join-Codepoints([int[]]$Codepoints) {
    return -join ($Codepoints | ForEach-Object { [char]$_ })
}

$SystemDirName = Join-Codepoints @(0x7cfb, 0x7edf)
$AppsDirName = Join-Codepoints @(0x5e94, 0x7528)
$DataDirName = Join-Codepoints @(0x6570, 0x636e)

$Python = Resolve-PythonExe
$Qemu = Join-Path $Root "bin\bbk9588-qemu-system-mipsel.exe"
if (-not (Test-Path -LiteralPath $Qemu)) {
    throw "Packaged QEMU executable not found: $Qemu"
}

$RuntimeDir = Join-Path $Root "runtime"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$NandImage = Join-Path $RuntimeDir "bbk9588_nand.bin"
$FallbackNandImages = @(
    (Join-Path $Root "build\bbk9588_nand_loader0_uboot40_fat_page1c40_root512_ftloob.bin"),
    (Join-Path $Root "build\bbk9588_nand_loader0_uboot40_fat_page1c40_root256_ftloob.bin"),
    (Join-Path $Root "build\bbk9588_nand_fat_page1c40_root512_ftloob.bin"),
    (Join-Path $Root "build\bbk9588_nand_fat_page1c40_root256_ftloob.bin"),
    (Join-Path $Root "build\bbk9588_nand_uboot40_fat_page1c40_root512_ftloob.bin"),
    (Join-Path $Root "build\bbk9588_nand_uboot40_fat_page1c40_root256_ftloob.bin")
)
if (-not $RebuildImages -and -not (Test-Path -LiteralPath $NandImage)) {
    foreach ($candidate in $FallbackNandImages) {
        if (Test-Path -LiteralPath $candidate) {
            Copy-Item -LiteralPath $candidate -Destination $NandImage
            break
        }
    }
}
$SystemDir = Join-Path $Root $SystemDirName
$AppsDir = Join-Path $Root $AppsDirName
$DataDir = Join-Path $SystemDir $DataDirName
$C200Image = Join-Path $DataDir "C200.bin"
$LoaderImage = Join-Path $DataDir "loader_9588_4740.bin"
$Kj409588Image = Join-Path $DataDir "kj409588.bin"
$UBootImage = Join-Path $DataDir "u_boot_9588_4740.bin"
if ($RebuildImages -or -not (Test-Path -LiteralPath $NandImage)) {
    if (
        (Test-Path -LiteralPath $LoaderImage) -and
        (Test-Path -LiteralPath $Kj409588Image) -and
        (Test-Path -LiteralPath $UBootImage) -and
        (Test-Path -LiteralPath $AppsDir)
    ) {
        $buildRuntimeArgs = @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            (Join-Path $Root "emu\tools\build_runtime_images.ps1"),
            "-Workspace",
            $Root,
            "-Python",
            $Python
        )
        $buildRuntimeArgs += @("-Loader", (Join-Path (Join-Path $SystemDirName $DataDirName) "loader_9588_4740.bin"))
        $buildRuntimeArgs += @("-UBoot", (Join-Path (Join-Path $SystemDirName $DataDirName) "u_boot_9588_4740.bin"))
        powershell @buildRuntimeArgs
    }
}

if (-not (Test-Path -LiteralPath $NandImage)) {
    throw @"
Runtime NAND image is missing:
  $NandImage

Place the firmware/resource dump next to this script and run again:
  系统\数据\loader_9588_4740.bin
  系统\数据\u_boot_9588_4740.bin
  系统\数据\kj409588.bin
  系统\...
  应用\...

Optional for C200 direct-boot compatibility mode:
  系统\数据\C200.bin

Or copy a prebuilt runtime NAND image to the path above.

The public release package does not include dumped firmware or applications.
"@
}

$ImageArgs = @()
if (-not (Test-ExtraArgOption "--image")) {
    if ($BootMode -eq "c200") {
        if (-not (Test-Path -LiteralPath $C200Image)) {
            throw "C200 boot mode requires a boot image: $C200Image"
        }
        $ImageArgs = @("--image", $C200Image)
    }
}

$url = "http://${HostName}:${Port}/"
Write-Host "Starting BBK 9588 emulator at $url"
if (-not $NoOpenBrowser) {
    Start-Process $url
}

& $Python -m emu.web.frontend `
    --boot-mode $BootMode `
    --qemu $Qemu `
    --nand-image $NandImage `
    --host $HostName `
    --port $Port `
    @ImageArgs `
    @ExtraArgs
