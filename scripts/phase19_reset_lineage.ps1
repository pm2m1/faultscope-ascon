# Phase 19: read-only reset-source and polarity investigation of Phase 17 DCP.
param(
    [string]$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat',
    [string]$Python = 'C:\Users\mishr\anaconda3\python.exe',
    [string]$Phase17 = 'build\reproduction\phase17\nexys4_ddr_rev_c_cfg_20261014T131338Z'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $Vivado -PathType Leaf)) { throw "Vivado missing: $Vivado" }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python missing: $Python" }
    $p17 = (Resolve-Path -LiteralPath $Phase17 -ErrorAction Stop).Path
    $allowed = [IO.Path]::GetFullPath((Join-Path $root 'build\reproduction\phase17'))
    if (-not $p17.StartsWith($allowed + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Phase 17 candidate must be under build\reproduction\phase17'
    }
    & $Python 'scripts\phase19_reset_lineage_report.py' --phase17 "$p17" --preflight-only
    if ($LASTEXITCODE -ne 0) { throw 'Phase 17 provenance check failed; refusing Vivado run' }
    $outputRoot = Join-Path $root 'build\reproduction\phase19'
    New-Item -ItemType Directory -Path $outputRoot -Force | Out-Null
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $output = Join-Path $outputRoot "reset_lineage_$stamp"
    if (Test-Path -LiteralPath $output) { throw "Refusing overwrite: $output" }
    $script = Join-Path $PSScriptRoot 'phase19_reset_lineage.tcl'
    $dcp = Join-Path $p17 'post_route.dcp'
    & $Vivado -mode batch -log (Join-Path $outputRoot "vivado_$stamp.log") -journal (Join-Path $outputRoot "vivado_$stamp.jou") `
        -source "$script" -tclargs "$dcp" "$output" 2>&1 | Tee-Object -FilePath (Join-Path $outputRoot "console_$stamp.log")
    if ($LASTEXITCODE -ne 0) { throw "Vivado reset-lineage collection failed; inspect console logs in $outputRoot" }
    & $Python 'scripts\phase19_reset_lineage_report.py' --phase17 "$p17" --audit "$output"
    if ($LASTEXITCODE -ne 0) { throw "Phase 19 evidence invalid; inspect $output" }
    Write-Host "PASS: Phase 19 reset-lineage diagnostics collected for manual review: $output"
} finally { Pop-Location }
