# Offline Phase 24 research release candidate: no Vivado / hardware signoff.
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
        throw 'Checkpoint must be inside the accepted Phase 17 evidence directory'
    }
    & $Python 'scripts\phase24_release_candidate.py' --input-dir "$ReviewDir" --checkpoint "$checkpointPath" --preflight-only
    if ($LASTEXITCODE -ne 0) { throw 'Phase 24 provenance preflight rejected: no output written' }
    $base = Join-Path $root 'build\reproduction\phase24'
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $out = Join-Path $base "release_candidate_$stamp"
    if (Test-Path -LiteralPath $out) { throw "Refusing overwrite: $out" }
    & $Python 'scripts\phase24_release_candidate.py' --input-dir "$ReviewDir" --checkpoint "$checkpointPath" --out "$out"
    if ($LASTEXITCODE -ne 0) { throw 'Phase 24 release audit rejected: no approval' }
    Write-Host "PASS: Phase 24 research release candidate written for independent review: $out"
} finally { Pop-Location }
