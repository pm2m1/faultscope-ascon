# Phase 21: read-only reset timing/missing-constraint evidence (no bitstream).
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
    $allowed = [IO.Path]::GetFullPath((Join-Path $root 'build\reproduction\phase17'))
    if (-not $p17.StartsWith($allowed + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Phase 17 evidence must be inside build\reproduction\phase17'
    }
    & $Python 'scripts\phase21_reset_timing_report.py' --phase17 "$p17" --preflight-only
    if ($LASTEXITCODE -ne 0) {throw 'Phase 17 checkpoint provenance failed: abort before Vivado'}
    $base = Join-Path $root 'build\reproduction\phase21'
    New-Item -ItemType Directory -Force -Path $base | Out-Null
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $out = Join-Path $base "reset_timing_$stamp"
    if (Test-Path -LiteralPath $out) {throw "Refusing overwrite: $out"}
    $dcp = Join-Path $p17 'post_route.dcp'
    $script = Join-Path $PSScriptRoot 'phase21_reset_timing.tcl'
    & $Vivado -mode batch -log (Join-Path $base "vivado_$stamp.log") -journal (Join-Path $base "vivado_$stamp.jou") `
        -source "$script" -tclargs "$dcp" "$out" 2>&1 | Tee-Object -FilePath (Join-Path $base "console_$stamp.log")
    if ($LASTEXITCODE -ne 0) {throw "Phase 21 Vivado diagnostic failed. Inspect $base"}
    & $Python 'scripts\phase21_reset_timing_report.py' --phase17 "$p17" --audit "$out"
    if ($LASTEXITCODE -ne 0) {throw "Phase 21 evidence rejected: $out"}
    Write-Host "PASS: Phase 21 diagnostic reports collected for review: $out"
} finally {Pop-Location}
