# Phase 18 read-only Phase 17 routed UART/reset boundary investigation.
param(
    [string]$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat',
    [string]$Python = 'C:\Users\mishr\anaconda3\python.exe',
    [string]$Phase17 = 'build\reproduction\phase17\nexys4_ddr_rev_c_cfg_20261014T131338Z'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $Vivado -PathType Leaf)) {throw "Vivado missing: $Vivado"}
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {throw "Python missing: $Python"}
    $p17 = (Resolve-Path -LiteralPath $Phase17 -ErrorAction Stop).Path
    $expectedRoot = [IO.Path]::GetFullPath((Join-Path $root 'build\reproduction\phase17'))
    if (-not $p17.StartsWith($expectedRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Phase 17 evidence must reside under build\reproduction\phase17'
    }
    & $Python 'scripts\phase18_async_report.py' --phase17 "$p17" --preflight-only
    if ($LASTEXITCODE -ne 0) {throw 'Phase 17 evidence provenance failed; Vivado not launched'}
    $base = Join-Path $root 'build\reproduction\phase18'
    New-Item -ItemType Directory -Path $base -Force | Out-Null
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $output = Join-Path $base "async_audit_$stamp"
    if (Test-Path -LiteralPath $output) {throw "Refusing overwrite: $output"}
    $script = Join-Path $PSScriptRoot 'phase18_async_audit.tcl'
    $checkpoint = Join-Path $p17 'post_route.dcp'
    & $Vivado -mode batch -log (Join-Path $base "vivado_$stamp.log") -journal (Join-Path $base "vivado_$stamp.jou") `
        -source "$script" -tclargs "$checkpoint" "$output" 2>&1 | Tee-Object -FilePath (Join-Path $base "console_$stamp.log")
    if ($LASTEXITCODE -ne 0) {throw "Vivado audit failed; inspect $base"}
    & $Python 'scripts\phase18_async_report.py' --phase17 "$p17" --audit "$output"
    if ($LASTEXITCODE -ne 0) {throw "Phase 18 evidence validation failed; inspect $output"}
    Write-Host "PASS: Phase 18 routed async-boundary evidence collected; manual review required: $output"
} finally {Pop-Location}
