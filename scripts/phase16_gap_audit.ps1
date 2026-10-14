# Read-only Phase 16 audit of the ALREADY ROUTED Phase 15 checkpoint.
param(
    [string]$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat',
    [string]$Python = 'C:\Users\mishr\anaconda3\python.exe',
    [string]$RunDir = 'build\reproduction\phase15\nexys4_ddr_rev_c_20261014T045950Z',
    [string]$OutputRoot = 'build\reproduction\phase16'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $Vivado -PathType Leaf)) { throw "Vivado missing: $Vivado" }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python missing: $Python" }
    if (-not (Test-Path -LiteralPath $RunDir -PathType Container)) { throw "Phase 15 run missing: $RunDir" }
    $phase15 = (Resolve-Path -LiteralPath $RunDir).Path
    # Restrict input to the historical Phase 15 evidence tree.
    $phase15Root = [IO.Path]::GetFullPath((Join-Path $root 'build\reproduction\phase15'))
    if (-not $phase15.StartsWith($phase15Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Phase 15 run must reside under build\reproduction\phase15'
    }
    & $Python 'scripts\phase16_gap_report.py' --preflight-only --phase15 "$phase15"
    if ($LASTEXITCODE -ne 0) {throw 'Phase 15 provenance verification failed'}
    $outBase = [IO.Path]::GetFullPath((Join-Path $root $OutputRoot))
    $safeRoot = [IO.Path]::GetFullPath((Join-Path $root 'build\reproduction\phase16'))
    if ($outBase -ne $safeRoot) {throw 'For this pilot, OutputRoot must equal build\reproduction\phase16'}
    New-Item -ItemType Directory -Path $outBase -Force | Out-Null
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $output = Join-Path $outBase "gap_audit_$stamp"
    if (Test-Path -LiteralPath $output) {throw "Refusing overwrite: $output"}
    $checkpoint = Join-Path $phase15 'post_route.dcp'
    $tcl = Join-Path $PSScriptRoot 'phase16_gap_audit.tcl'
    $console = Join-Path $outBase "vivado_console_$stamp.log"
    $vivadoLog = Join-Path $outBase "vivado_$stamp.log"
    $vivadoJournal = Join-Path $outBase "vivado_$stamp.jou"
    Write-Host 'Phase 16: read-only checkpoint audit; no synthesis/route/bitstream'
    Write-Host "Phase 15 checkpoint: $checkpoint"
    & $Vivado -mode batch -log "$vivadoLog" -journal "$vivadoJournal" -source "$tcl" -tclargs "$checkpoint" "$output" 2>&1 | Tee-Object -FilePath $console
    if ($LASTEXITCODE -ne 0) {throw "Vivado diagnostic failed; inspect $console"}
    & $Python 'scripts\phase16_gap_report.py' --phase15 "$phase15" --audit "$output" --require-evidence
    if ($LASTEXITCODE -ne 0) {throw "Phase 16 review incomplete; inspect $output"}
    Write-Host "PASS: Phase 16 diagnostic evidence collected, review required: $output"
} finally { Pop-Location }
