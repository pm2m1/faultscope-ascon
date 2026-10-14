# Phase 23 offline evidence inventory. No Vivado, synthesis, routing or bitstream.
param(
    [string]$Python = 'C:\Users\mishr\anaconda3\python.exe',
    [string]$ReviewDir = "$env:USERPROFILE\Downloads",
    [string]$Checkpoint = 'build\reproduction\phase17\nexys4_ddr_rev_c_cfg_20261014T131338Z\post_route.dcp'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python executable missing: $Python" }
    if (-not (Test-Path -LiteralPath $ReviewDir -PathType Container)) { throw "Review directory missing: $ReviewDir" }
    $checkpointPath = (Resolve-Path -LiteralPath $Checkpoint -ErrorAction Stop).Path
    $allowed = [IO.Path]::GetFullPath((Join-Path $root 'build\reproduction\phase17'))
    if (-not $checkpointPath.StartsWith($allowed + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Checkpoint must be within build\reproduction\phase17'
    }
    & $Python 'scripts\phase23_evidence_gap_matrix.py' --input-dir "$ReviewDir" --checkpoint "$checkpointPath" --preflight-only
    if ($LASTEXITCODE -ne 0) { throw 'Phase 23 input archives or accepted checkpoint rejected' }
    $base = Join-Path $root 'build\reproduction\phase23'
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $out = Join-Path $base "evidence_gap_$stamp"
    if (Test-Path -LiteralPath $out) {throw "Refusing overwrite: $out"}
    & $Python 'scripts\phase23_evidence_gap_matrix.py' --input-dir "$ReviewDir" --checkpoint "$checkpointPath" --out "$out"
    if ($LASTEXITCODE -ne 0) {throw "Phase 23 matrix generation rejected: $out"}
    Write-Host "PASS: Phase 23 evidence matrix created for manual review: $out"
} finally {Pop-Location}
