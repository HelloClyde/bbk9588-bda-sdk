param(
  [string]$Workspace = ".",
  [string]$Python = "python",
  [string]$BuildDir = "build",
  [string]$SystemDir = "系统",
  [string]$AppsDir = "应用",
  [string]$C200 = "系统\数据\C200.bin",
  [string]$FatImage = "bbk9588_fat_page1c40.img",
  [string]$CombinedNand = "bbk9588_nand_c200_fat_page1c40.bin",
  [string]$StampedNand = "bbk9588_nand_c200_fat_page1c40_root256_ftloob.bin",
  [string]$FatPageBase = "0x1c40"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path $Workspace
$build = Join-Path $root $BuildDir
New-Item -ItemType Directory -Force -Path $build | Out-Null

$systemPath = Join-Path $root $SystemDir
$appsPath = Join-Path $root $AppsDir
$c200Path = Join-Path $root $C200
$fatPath = Join-Path $build $FatImage
$combinedPath = Join-Path $build $CombinedNand
$stampedPath = Join-Path $build $StampedNand

foreach ($path in @($systemPath, $appsPath, $c200Path)) {
  if (-not (Test-Path -LiteralPath $path)) {
    throw "required source path missing: $path"
  }
}

& $Python (Join-Path $root "emu\tools\make_fat16_image.py") `
  --output $fatPath `
  $systemPath $appsPath
if ($LASTEXITCODE -ne 0) { throw "make_fat16_image.py failed" }

& $Python (Join-Path $root "emu\tools\make_combined_nand.py") `
  --base-nand $c200Path `
  --fat-image $fatPath `
  --output $combinedPath `
  --fat-page-base $FatPageBase
if ($LASTEXITCODE -ne 0) { throw "make_combined_nand.py failed" }

& $Python (Join-Path $root "emu\tools\stamp_ftl_oob.py") `
  $combinedPath `
  $stampedPath `
  --fat-page-base $FatPageBase
if ($LASTEXITCODE -ne 0) { throw "stamp_ftl_oob.py failed" }

Write-Host "wrote $fatPath"
Write-Host "wrote $combinedPath"
Write-Host "wrote $stampedPath"
