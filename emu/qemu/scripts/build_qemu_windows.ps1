param(
  [string]$QemuSource = "E:\qemu-src",
  [string]$BuildDir = "E:\qemu-src\build-bbk9588-win",
  [string]$MsysBash = "C:\msys64\usr\bin\bash.exe",
  [int]$Jobs = 0,
  [switch]$SkipPatch,
  [switch]$UseOverlay,
  [switch]$Reconfigure
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$patchScript = Join-Path $repoRoot "emu\qemu\scripts\apply_qemu_patch.py"
$overlayScript = Join-Path $repoRoot "emu\qemu\scripts\install_qemu_overlay.py"

if (-not (Test-Path -LiteralPath $QemuSource)) {
  throw "QEMU source tree not found: $QemuSource"
}
if (-not (Test-Path -LiteralPath $MsysBash)) {
  throw "MSYS2 bash not found: $MsysBash"
}

if (-not $SkipPatch) {
  if ($UseOverlay) {
    python $overlayScript --qemu-source $QemuSource
    if ($LASTEXITCODE -ne 0) {
      throw "failed to install QEMU source overlay"
    }
  } else {
    python $patchScript --qemu-source $QemuSource --check
    if ($LASTEXITCODE -eq 0) {
      python $patchScript --qemu-source $QemuSource
      if ($LASTEXITCODE -ne 0) {
        throw "failed to apply QEMU patch"
      }
    } else {
      python $patchScript --qemu-source $QemuSource --reverse --check
      if ($LASTEXITCODE -eq 0) {
        Write-Host "QEMU patch is already applied"
      } else {
        throw "QEMU source tree is neither clean nor already patched"
      }
    }
  }
}

function Convert-ToMsysPath([string]$Path) {
  $full = [System.IO.Path]::GetFullPath($Path).Replace("\", "/")
  if ($full -match "^([A-Za-z]):/(.*)$") {
    return "/" + $Matches[1].ToLowerInvariant() + "/" + $Matches[2]
  }
  return $full
}

$sourcePosix = Convert-ToMsysPath $QemuSource
$buildPosix = Convert-ToMsysPath $BuildDir

$ninjaJobs = ""
if ($Jobs -gt 0) {
  $ninjaJobs = "-j $Jobs"
}

$configure = @"
set -euo pipefail
export MSYSTEM=UCRT64
export PATH=/ucrt64/bin:/usr/bin:`$PATH
export CC=gcc
export CXX=g++
mkdir -p "$buildPosix"
cd "$buildPosix"
if [ ! -f build.ninja ] || [ "$($Reconfigure.IsPresent)" = "True" ]; then
  "$sourcePosix/configure" --target-list=mipsel-softmmu --disable-werror
fi
ninja $ninjaJobs qemu-system-mipsel.exe
"@

& $MsysBash -lc $configure
if ($LASTEXITCODE -ne 0) {
  throw "QEMU build failed"
}

$exe = Join-Path $BuildDir "qemu-system-mipsel.exe"
if (-not (Test-Path -LiteralPath $exe)) {
  throw "build finished but executable not found: $exe"
}

Write-Host "built $exe"
