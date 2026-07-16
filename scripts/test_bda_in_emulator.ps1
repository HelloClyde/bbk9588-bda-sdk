<#
.SYNOPSIS
将一个 BDA 部署到模拟器固定的“背单词”入口并自动启动。

.EXAMPLE
.\scripts\test_bda_in_emulator.ps1 .\build\TouchStageV23.bda

.EXAMPLE
.\scripts\test_bda_in_emulator.ps1 .\build\Minesweeper.bda -ResetImage

.NOTES
默认使用 E:\bbk9588-emulator-v0.1.5、端口 8013 和独立的 runtime\bda_test NAND。
C200.bin 不会被修改；目标文件固定为 A:\应用\程序\宠物单词.bda。
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Bda,
    [string]$EmulatorRoot = $(
        if ($env:BBK9588_EMULATOR_ROOT) {
            $env:BBK9588_EMULATOR_ROOT
        } else {
            "E:\bbk9588-emulator-v0.1.5"
        }
    ),
    [int]$Port = 8013,
    [int]$BootDelaySeconds = 12,
    [switch]$ResetImage,
    [switch]$NoAutoLaunch,
    [switch]$NoOpenBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$BdaPath = (Resolve-Path -LiteralPath $Bda).Path
$EmulatorRoot = (Resolve-Path -LiteralPath $EmulatorRoot).Path
$Python = Join-Path $EmulatorRoot "python\python.exe"
$Qemu = Join-Path $EmulatorRoot "bin\bbk9588-qemu-system-mipsel.exe"
$Archive = Join-Path $EmulatorRoot "bbk9588_nand-v1.2.0.zip"
$RuntimeRoot = Join-Path $EmulatorRoot "runtime"
$TestImageDir = Join-Path $RuntimeRoot "bda_test"
$TestNand = Join-Path $TestImageDir "bbk9588_nand.bin"
$Helper = Join-Path $PSScriptRoot "replace_emulator_bda.py"
$BaseUrl = "http://127.0.0.1:$Port"

foreach ($required in @($Python, $Qemu, $Helper)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "缺少文件：$required"
    }
}
if ([IO.Path]::GetExtension($BdaPath) -ine ".bda") {
    throw "测试文件必须是 .bda：$BdaPath"
}

function Get-FrontendStatus {
    try {
        return Invoke-RestMethod -Uri "$BaseUrl/api/status" -TimeoutSec 5
    } catch {
        return $null
    }
}

function Resolve-StatusNand([object]$Status) {
    $value = [string]$Status.nand_image
    if (-not $value) { return "" }
    if ([IO.Path]::IsPathRooted($value)) {
        return [IO.Path]::GetFullPath($value)
    }
    return [IO.Path]::GetFullPath((Join-Path $EmulatorRoot $value))
}

function Stop-Guest([object]$Status) {
    if (-not $Status -or -not $Status.running) { return }
    $safeStopFailed = $false
    try {
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/stop" -TimeoutSec 45 | Out-Null
    } catch {
        $safeStopFailed = $true
        Write-Warning "模拟器安全停止返回错误，继续检查实际进程状态：$($_.Exception.Message)"
    }

    $deadline = (Get-Date).AddSeconds(5)
    do {
        Start-Sleep -Milliseconds 500
        $current = Get-FrontendStatus
        if (-not $current -or -not $current.running) { return }
    } while ((Get-Date) -lt $deadline)

    if ($safeStopFailed -or ($current -and $current.running)) {
        Write-Warning "固件没有完成安全关机，调用模拟器 force-stop 后再修改专用 NAND"
        $body = @{ op = "force-stop" } | ConvertTo-Json
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/command" `
            -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 30 | Out-Null
    }

    $deadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 500
        $current = Get-FrontendStatus
        if (-not $current -or -not $current.running) { return }
    } while ((Get-Date) -lt $deadline)
    throw "端口 $Port 的 QEMU 仍在运行，拒绝修改 NAND"
}

function Stop-ForeignFrontend([object]$Status) {
    Stop-Guest $Status
    try {
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/shutdown" -TimeoutSec 5 | Out-Null
    } catch {
    }
    Start-Sleep -Seconds 2

    $portPattern = "--port\s+$Port(?:\s|$)"
    $oldNand = Resolve-StatusNand $Status
    $oldNandPattern = if ($oldNand) {
        [regex]::Escape(($oldNand -replace "\\", "/"))
    } else {
        "a^"
    }
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ProcessId -ne $PID -and $_.CommandLine -and (
                ($_.Name -eq "python.exe" -and $_.CommandLine -match $portPattern) -or
                ($_.Name -eq "bbk9588-qemu-system-mipsel.exe" -and
                    ($_.CommandLine -replace "\\", "/") -match $oldNandPattern)
            )
        } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
}

function Initialize-TestImage {
    if ((Test-Path -LiteralPath $TestNand -PathType Leaf) -and -not $ResetImage) {
        return
    }
    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw "缺少官方 NAND 压缩包：$Archive"
    }

    $runtimeFull = [IO.Path]::GetFullPath($RuntimeRoot).TrimEnd('\') + '\'
    $testDirFull = [IO.Path]::GetFullPath($TestImageDir)
    if (-not $testDirFull.StartsWith($runtimeFull, [StringComparison]::OrdinalIgnoreCase) -or
        [IO.Path]::GetFileName($testDirFull) -ne "bda_test") {
        throw "测试镜像目录越界：$testDirFull"
    }
    if (Test-Path -LiteralPath $TestImageDir) {
        Remove-Item -LiteralPath $TestImageDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $TestImageDir | Out-Null
    Expand-Archive -LiteralPath $Archive -DestinationPath $TestImageDir -Force
    if (-not (Test-Path -LiteralPath $TestNand -PathType Leaf)) {
        throw "官方 NAND 解压后未生成：$TestNand"
    }
}

function Start-Frontend {
    $arguments = @(
        "-m", "emu.web.frontend",
        "--boot-mode", "nand",
        "--qemu", $Qemu,
        "--nand-image", $TestNand,
        "--host", "127.0.0.1",
        "--port", [string]$Port
    )
    Start-Process -FilePath $Python -ArgumentList $arguments `
        -WorkingDirectory $EmulatorRoot -WindowStyle Hidden | Out-Null
}

function Wait-Frontend {
    $deadline = (Get-Date).AddSeconds(60)
    do {
        Start-Sleep -Seconds 1
        $status = Get-FrontendStatus
        if ($status -and $status.running) { return $status }
    } while ((Get-Date) -lt $deadline)
    throw "端口 $Port 的模拟器未在 60 秒内启动"
}

function Send-Touch([int]$X, [int]$Y) {
    Invoke-RestMethod -Method Post `
        -Uri "$BaseUrl/api/touch?x=$X&y=$Y&down=1" -TimeoutSec 15 | Out-Null
    Start-Sleep -Milliseconds 150
    Invoke-RestMethod -Method Post `
        -Uri "$BaseUrl/api/touch?x=$X&y=$Y&down=0" -TimeoutSec 15 | Out-Null
}

$status = Get-FrontendStatus
if ($status) {
    $currentNand = Resolve-StatusNand $status
    if ($currentNand -ine [IO.Path]::GetFullPath($TestNand)) {
        Stop-ForeignFrontend $status
        $status = $null
    } else {
        Stop-Guest $status
    }
}

Initialize-TestImage

$env:PYTHONNOUSERSITE = "1"
& $Python $Helper `
    --emulator-root $EmulatorRoot `
    --nand $TestNand `
    --bda $BdaPath
if ($LASTEXITCODE -ne 0) {
    throw "替换宠物单词.bda 失败"
}

if ($status) {
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/reset" -TimeoutSec 45 | Out-Null
} else {
    Start-Frontend
}
$status = Wait-Frontend

if (-not $NoAutoLaunch) {
    Start-Sleep -Seconds $BootDelaySeconds
    Send-Touch 198 84
    Start-Sleep -Seconds 2
    Send-Touch 120 100
}

if (-not $NoOpenBrowser) {
    Start-Process "$BaseUrl/"
}

Write-Host "BDA 已部署到固定入口：A:\应用\程序\宠物单词.bda"
Write-Host "测试 NAND：$TestNand"
Write-Host "模拟器：$BaseUrl/"
