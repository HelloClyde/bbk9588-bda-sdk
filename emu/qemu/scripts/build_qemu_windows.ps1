param(
  [string]$QemuSource = "E:\qemu-src",
  [string]$BuildDir = "E:\qemu-src\build-bbk9588-win",
  [string]$MsysBash = "C:\msys64\usr\bin\bash.exe",
  [int]$Jobs = 0,
  [switch]$SkipPatch,
  [switch]$UseOverlay,
  [switch]$Reconfigure,
  [switch]$ConfigureOnly
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
$msysUsrDir = Split-Path -Parent (Split-Path -Parent $MsysBash)
$msysRoot = Split-Path -Parent $msysUsrDir
$ucrtBin = (Join-Path $msysRoot "ucrt64\bin").Replace("\", "/")
$gcc = "$ucrtBin/gcc.exe"
$gxx = "$ucrtBin/g++.exe"
$python = "$ucrtBin/python.exe"
$pkgConfig = "$ucrtBin/pkg-config.exe"
$ninja = "$ucrtBin/ninja.exe"

$ninjaJobs = ""
if ($Jobs -gt 0) {
  $ninjaJobs = "-j $Jobs"
}

$configure = @"
set -eo pipefail
export MSYSTEM=UCRT64
export PATH=/ucrt64/bin:/usr/bin:`$PATH
unset CFLAGS CXXFLAGS LDFLAGS PKG_CONFIG_PATH PKG_CONFIG_LIBDIR
unset Python_ROOT_DIR Python2_ROOT_DIR Python3_ROOT_DIR pythonLocation
export CC="$gcc"
export CXX="$gxx"
export PKG_CONFIG="$pkgConfig"
export PYTHON="$python"
echo "MSYS2 toolchain:"
echo "PATH=`$PATH"
command -v gcc || true
ls -l /ucrt64/bin/gcc.exe "$gcc" || true
"$gcc" --version | head -n 1
"$python" --version
"$pkgConfig" --version
"$ninja" --version
mkdir -p "$buildPosix"
cd "$buildPosix"
printf 'int main(void) { return 0; }\n' > .qemu-build-cc-probe.c
"$gcc" -m64 -c -o .qemu-build-cc-probe.o .qemu-build-cc-probe.c
rm -f .qemu-build-cc-probe.c .qemu-build-cc-probe.o
if [ ! -f build.ninja ] || [ "$($Reconfigure.IsPresent)" = "True" ]; then
  configure_status=0
  "$sourcePosix/configure" \
    --target-list=mipsel-softmmu \
    --disable-werror \
    --cc="$gcc" \
    --host-cc="$gcc" \
    --cxx="$gxx" \
    --python="$python" \
    --ninja="$ninja" || configure_status=`$?
  if [ "`$configure_status" -ne 0 ]; then
    echo "::group::QEMU config.log"
    if [ -f config.log ]; then
      tail -n 260 config.log
    else
      echo "config.log was not created"
    fi
    echo "::endgroup::"
    if [ -f meson-logs/meson-log.txt ]; then
      echo "::group::Meson log"
      tail -n 260 meson-logs/meson-log.txt
      echo "::endgroup::"
    fi
    exit "`$configure_status"
  fi
fi
if [ "$($ConfigureOnly.IsPresent)" = "True" ]; then
  echo "configured $buildPosix"
  exit 0
fi
ninja $ninjaJobs qemu-system-mipsel.exe
"@

& $MsysBash -lc $configure
if ($LASTEXITCODE -ne 0) {
  throw "QEMU build failed"
}

if ($ConfigureOnly) {
  Write-Host "configured $BuildDir"
  return
}

$exe = Join-Path $BuildDir "qemu-system-mipsel.exe"
if (-not (Test-Path -LiteralPath $exe)) {
  throw "build finished but executable not found: $exe"
}

Write-Host "built $exe"
