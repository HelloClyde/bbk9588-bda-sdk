param(
    [switch]$Emu,
    [switch]$SkipToolchainSetup
)

$ErrorActionPreference = "Stop"
$utf8 = New-Object System.Text.UTF8Encoding $false
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$OutputEncoding = $utf8
$env:PYTHONIOENCODING = "utf-8"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "== $Name =="
    & $Command
}

if (-not $SkipToolchainSetup) {
    Invoke-Step "检查 MIPS 工具链" {
        & .\scripts\setup_toolchain.ps1
    }
}

Invoke-Step "生成 API 覆盖表" {
    & python -B reverse\bda_api_catalog.py
}

Invoke-Step "生成 C200 API 表" {
    $systemBin = "系统\数据\C200.bin"
    if (Test-Path $systemBin) {
        & python -B reverse\c200_api_tables.py --root . --json-out build\c200_api_tables.json
    } else {
        Write-Warning "跳过 C200 API 表生成：未找到本地 $systemBin。"
    }
}

Invoke-Step "运行单元测试和 SDK C 示例编译 smoke" {
    $testOutput = & python -m unittest `
        reverse.test_bda_header `
        reverse.test_bda_api_catalog `
        reverse.test_bda_deploy_bundle `
        reverse.test_bda_validate `
        reverse.test_config_inf_add `
        reverse.test_c200_api_tables `
        reverse.test_sdk_docs `
        reverse.test_sdk_examples 2>&1
    $testExit = $LASTEXITCODE
    $testOutput | ForEach-Object { Write-Host $_ }
    if ($testExit -ne 0) {
        exit $testExit
    }
}

Invoke-Step "构建并验证 RectDemo 示例" {
    & python -m bda_packer reverse\examples\gui_rect_contains_demo.c `
        --title RectDemo `
        --category 9 `
        -I reverse `
        -o build\RectDemo.bda
    & python -m bda_packer.validate build\RectDemo.bda
}

if ($Emu) {
    Invoke-Step "运行 emu 前端 smoke" {
        & python emu\test\run_frontend_web_smoke.py `
            --prefix codex_frontend_smoke `
            --boot-timeout 180 `
            --chunk-steps 250000
    }

} else {
    Write-Host ""
    Write-Host "未运行 emu smoke。需要时执行：.\scripts\verify_sdk.ps1 -Emu"
}

Write-Host ""
Write-Host "验证完成。"
