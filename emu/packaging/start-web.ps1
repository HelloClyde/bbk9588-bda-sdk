param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [ValidateSet("c200", "uboot")]
    [string]$BootMode = "uboot",
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

$Python = Resolve-PythonExe
$Qemu = Join-Path $Root "bin\bbk9588-qemu-system-mipsel.exe"
if (-not (Test-Path -LiteralPath $Qemu)) {
    throw "Packaged QEMU executable not found: $Qemu"
}

$NandImage = Join-Path $Root "build\bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin"
if ($RebuildImages -or -not (Test-Path -LiteralPath $NandImage)) {
    $c200 = Join-Path $Root "系统\数据\C200.bin"
    $apps = Join-Path $Root "应用"
    if ((Test-Path -LiteralPath $c200) -and (Test-Path -LiteralPath $apps)) {
        powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "emu\tools\build_runtime_images.ps1") `
            -Workspace $Root `
            -Python $Python
    }
}

if (-not (Test-Path -LiteralPath $NandImage)) {
    throw @"
Runtime NAND image is missing:
  $NandImage

Place the firmware/resource dump next to this script and run again:
  系统\数据\C200.bin
  系统\...
  应用\...

The public release package does not include dumped firmware or applications.
"@
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
    @ExtraArgs
