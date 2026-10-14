# Phase 17: fresh full-device routed candidate, no physical board and no bitstream.
param(
    [string]$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat',
    [string]$Python = 'C:\Users\mishr\anaconda3\python.exe',
    [string]$Phase15Dir = 'build\reproduction\phase15\nexys4_ddr_rev_c_20261014T045950Z'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $Vivado -PathType Leaf)) {throw "Missing Vivado: $Vivado"}
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {throw "Missing Python: $Python"}
    $phase15 = (Resolve-Path -LiteralPath $Phase15Dir).Path
    $safeBaselineRoot = [IO.Path]::GetFullPath((Join-Path $root 'build\reproduction\phase15'))
    if (-not $phase15.StartsWith($safeBaselineRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing non-Phase15 baseline directory'
    }
    # Prevent accidental RTL edits from invalidating the controlled A/B comparison.
    & git diff --quiet HEAD -- rtl
    if ($LASTEXITCODE -ne 0) {throw 'RTL worktree differs from HEAD; use a clean RTL worktree'}
    $untrackedRTL = & git ls-files --others --exclude-standard -- rtl
    if ($untrackedRTL) {throw 'Untracked RTL present; check before rerunning Phase 17'}
    & $Python 'scripts\phase17_cfg_review.py' --phase15 "$phase15" --preflight-only
    if ($LASTEXITCODE -ne 0) {throw 'Phase 17 baseline/XDC overlay preflight failed'}
    $base = (Resolve-Path 'constraints\phase15_nexys4_ddr_rev_c.xdc').Path
    $overlay = (Resolve-Path 'constraints\phase17_cfg_rev_c_overlay.xdc').Path
    $outRoot = Join-Path $root 'build\reproduction\phase17'
    New-Item -ItemType Directory -Path $outRoot -Force | Out-Null
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $out = Join-Path $outRoot "nexys4_ddr_rev_c_cfg_$stamp"
    if (Test-Path -LiteralPath $out) {throw "Refusing overwrite: $out"}
    New-Item -ItemType Directory -Path $out | Out-Null
    $tcl = Join-Path $PSScriptRoot 'phase17_cfg_impl.tcl'
    Write-Host "Phase 17: fresh provisional Rev. C full-device implementation; NO bitstream. Output: $out"
    & $Vivado -mode batch -log (Join-Path $out 'vivado.log') -journal (Join-Path $out 'vivado.jou') -source "$tcl" -tclargs "$base" "$overlay" "$out" 2>&1 | Tee-Object -FilePath (Join-Path $out 'vivado_console.log')
    if ($LASTEXITCODE -ne 0) {throw "Vivado implementation failed; inspect $out\vivado_console.log"}
    & $Python 'scripts\phase17_cfg_review.py' --phase15 "$phase15" --overlay "$overlay" --candidate "$out"
    if ($LASTEXITCODE -ne 0) {throw "Candidate rejected; inspect $out\verification.json and Vivado reports"}
    Write-Host "PASS: Phase 17 routed config candidate; DRC/methodology/CDC/board signoff still need review: $out"
} finally {
    Pop-Location
}
