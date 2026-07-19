param(
    [string]$Archive = ".toolchain/g++-mipsel-none-elf-15.2.0.zip",
    [string]$Url = "https://static.grumpycoder.net/pixel/mips/g++-mipsel-none-elf-15.2.0.zip",
    [string]$Destination = ".toolchain",
    [string]$ExpectedSha256 = "8BA866E25C9826EE04AB4310365D264E3E73769E3738BB58AE38FD6740B7EE8D"
)

$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$archivePath = Join-Path $root $Archive
$destPath = Join-Path $root $Destination
$expectedDir = Join-Path $destPath "g++-mipsel-none-elf-15.2.0"
$gcc = Join-Path $destPath "bin/mipsel-none-elf-gcc.exe"
$cc1 = Join-Path $destPath "libexec/gcc/mipsel-none-elf/15.2.0/cc1.exe"
$versionedGcc = Join-Path $expectedDir "bin/mipsel-none-elf-gcc.exe"
$versionedCc1 = Join-Path $expectedDir "libexec/gcc/mipsel-none-elf/15.2.0/cc1.exe"
$defaultDestPath = [IO.Path]::GetFullPath((Join-Path $root ".toolchain"))
$legacyDestPath = Join-Path $root "tools"
$legacyGcc = Join-Path $legacyDestPath "bin/mipsel-none-elf-gcc.exe"
$legacyCc1 = Join-Path $legacyDestPath "libexec/gcc/mipsel-none-elf/15.2.0/cc1.exe"
$legacyVersionedGcc = Join-Path $legacyDestPath "g++-mipsel-none-elf-15.2.0/bin/mipsel-none-elf-gcc.exe"
$legacyVersionedCc1 = Join-Path $legacyDestPath "g++-mipsel-none-elf-15.2.0/libexec/gcc/mipsel-none-elf/15.2.0/cc1.exe"

function Test-ToolchainComplete([string]$GccPath, [string]$Cc1Path) {
    return (Test-Path -LiteralPath $GccPath -PathType Leaf) -and
        (Test-Path -LiteralPath $Cc1Path -PathType Leaf)
}

if (Test-ToolchainComplete $gcc $cc1) {
    Write-Host "Toolchain already installed: $destPath"
    exit 0
}

if (Test-ToolchainComplete $versionedGcc $versionedCc1) {
    Write-Host "Toolchain already installed: $expectedDir"
    exit 0
}

if ((Test-Path -LiteralPath $gcc) -or (Test-Path -LiteralPath $versionedGcc)) {
    Write-Warning "Incomplete toolchain detected; reinstalling because cc1.exe is missing."
}

if ([IO.Path]::GetFullPath($destPath) -eq $defaultDestPath) {
    if ((Test-ToolchainComplete $legacyGcc $legacyCc1) -or
        (Test-ToolchainComplete $legacyVersionedGcc $legacyVersionedCc1)) {
        Write-Warning "Using legacy toolchain location: $legacyDestPath. New installations use .toolchain/."
        exit 0
    }
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

if (Test-ToolchainComplete $gcc $cc1) {
    Write-Host "Toolchain ready: $destPath"
    exit 0
}

if (Test-ToolchainComplete $versionedGcc $versionedCc1) {
    Write-Host "Toolchain ready: $expectedDir"
    exit 0
}

throw "Extraction finished, but a complete gcc/cc1 toolchain was not found at: $destPath or $expectedDir"
