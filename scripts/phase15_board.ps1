# Phase 15 provisional full-board implementation. No board, no bitstream.
param(
    [string]$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat',
    [string]$Python = 'C:\Users\mishr\anaconda3\python.exe',
    [string]$OutputRoot = 'build\reproduction\phase15',
    [string]$Xdc = 'constraints\phase15_nexys4_ddr_rev_c.xdc'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    if (-not (Test-Path -LiteralPath $Vivado -PathType Leaf)) {throw "Vivado not found: $Vivado"}
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {throw "Python not found: $Python"}
    if (-not (Test-Path -LiteralPath $Xdc -PathType Leaf)) {throw "XDC not found: $Xdc"}
    $xdcPath = (Resolve-Path -LiteralPath $Xdc).Path
    & $Python 'scripts\phase15_board_report.py' --preflight-only --xdc "$xdcPath"
    if ($LASTEXITCODE -ne 0) { throw 'Official six-port XDC preflight failed' }
    if (-not [System.IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot = Join-Path $root $OutputRoot }
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $runPath = Join-Path $OutputRoot "nexys4_ddr_rev_c_$stamp"
    if (Test-Path -LiteralPath $runPath) {throw "Refusing overwrite: $runPath"}
    New-Item -ItemType Directory -Path $runPath -Force | Out-Null
    Write-Host "Phase 15: provisional Nexys 4 DDR Rev. C; full device implementation, NO bitstream"
    Write-Host "Evidence folder: $runPath"
    $tcl = Join-Path $PSScriptRoot 'phase15_board_impl.tcl'
    $console = Join-Path $runPath 'vivado_console.log'
    $vivadoLog = Join-Path $runPath 'vivado.log'
    $vivadoJournal = Join-Path $runPath 'vivado.jou'
    & $Vivado -mode batch -log "$vivadoLog" -journal "$vivadoJournal" -source "$tcl" -tclargs "$xdcPath" "$runPath" 2>&1 | Tee-Object -FilePath $console
    if ($LASTEXITCODE -ne 0) { throw "Vivado implementation failed; inspect $console" }
    & $Python 'scripts\phase15_board_report.py' "$runPath" --xdc "$xdcPath" --require-candidate
    if ($LASTEXITCODE -ne 0) {throw "Phase 15 acceptance review failed; inspect $runPath"}
    Write-Host "PASS: full-board routed candidate, pending manual DRC/CDC/external-I/O review: $runPath"
} finally {
    Pop-Location
}
