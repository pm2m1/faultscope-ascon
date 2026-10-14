# Phase 22 read-only path-object timing audit; accepted Phase 17 checkpoint only.
param(
    [string]$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat',
    [string]$Python = 'C:\Users\mishr\anaconda3\python.exe',
    [string]$Phase17 = 'build\reproduction\phase17\nexys4_ddr_rev_c_cfg_20261014T131338Z'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $Vivado -PathType Leaf)) {throw "Vivado executable missing: $Vivado"}
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {throw "Python executable missing: $Python"}
    $p17 = (Resolve-Path -LiteralPath $Phase17 -ErrorAction Stop).Path
    $allowed = [IO.Path]::GetFullPath((Join-Path $root 'build\reproduction\phase17'))
    if (-not $p17.StartsWith($allowed + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Phase 17 path must remain inside build\reproduction\phase17'
    }
    & $Python 'scripts\phase22_timing_query_report.py' --phase17 "$p17" --preflight-only
    if ($LASTEXITCODE -ne 0) {throw 'Phase 17 provenance failed; refusing Vivado diagnostic'}
    $base = Join-Path $root 'build\reproduction\phase22'
    New-Item -ItemType Directory -Force -Path $base | Out-Null
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $out = Join-Path $base "path_binding_$stamp"
    if (Test-Path -LiteralPath $out) {throw "Refusing overwrite: $out"}
    $dcp = Join-Path $p17 'post_route.dcp'
    $tcl = Join-Path $PSScriptRoot 'phase22_timing_query_integrity.tcl'
    & $Vivado -mode batch -log (Join-Path $base "vivado_$stamp.log") -journal (Join-Path $base "vivado_$stamp.jou") `
        -source "$tcl" -tclargs "$dcp" "$out" 2>&1 | Tee-Object -FilePath (Join-Path $base "console_$stamp.log")
    if ($LASTEXITCODE -ne 0) {throw "Phase 22 Vivado audit failed; see $base"}
    & $Python 'scripts\phase22_timing_query_report.py' --phase17 "$p17" --audit "$out"
    if ($LASTEXITCODE -ne 0) {throw "Phase 22 evidence rejected: $out"}
    Write-Host "PASS: Phase 22 reports collected for manual review: $out"
} finally {Pop-Location}
