param(
    [string]$Archive = "tools/g++-mipsel-none-elf-15.2.0.zip",
    [string]$Url = "https://static.grumpycoder.net/pixel/mips/g++-mipsel-none-elf-15.2.0.zip",
    [string]$Destination = "tools",
    [string]$ExpectedSha256 = "8BA866E25C9826EE04AB4310365D264E3E73769E3738BB58AE38FD6740B7EE8D"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$archivePath = Join-Path $root $Archive
$destPath = Join-Path $root $Destination
$expectedDir = Join-Path $destPath "g++-mipsel-none-elf-15.2.0"
$gcc = Join-Path $destPath "bin/mipsel-none-elf-gcc.exe"
$legacyGcc = Join-Path $expectedDir "bin/mipsel-none-elf-gcc.exe"

if (Test-Path -LiteralPath $gcc) {
    Write-Host "Toolchain already installed: $destPath"
    exit 0
}

if (Test-Path -LiteralPath $legacyGcc) {
    Write-Host "Toolchain already installed: $expectedDir"
    exit 0
}

if (!(Test-Path -LiteralPath $archivePath)) {
    Write-Host "Downloading $Url"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $archivePath) | Out-Null
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $archivePath
}

$actualSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
if ($actualSha256 -ne $ExpectedSha256.ToUpperInvariant()) {
    throw "Toolchain archive SHA-256 mismatch. Expected $ExpectedSha256, got $actualSha256. Remove the archive and retry."
}
Write-Host "Toolchain archive SHA-256 verified: $actualSha256"

New-Item -ItemType Directory -Force -Path $destPath | Out-Null
Write-Host "Extracting $archivePath"
Expand-Archive -LiteralPath $archivePath -DestinationPath $destPath -Force

if (Test-Path -LiteralPath $gcc) {
    Write-Host "Toolchain ready: $destPath"
    exit 0
}

if (Test-Path -LiteralPath $legacyGcc) {
    Write-Host "Toolchain ready: $expectedDir"
    exit 0
}

throw "Extraction finished, but gcc was not found at: $gcc or $legacyGcc"
