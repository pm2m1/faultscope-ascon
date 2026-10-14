# Independently compile + simulate original UART/reset RTL with Vivado XSim.
# Digital tests do not establish analog MTBF, debounce, timing signoff or hardware success.
param(
    [string]$VivadoBin = 'C:\AMDDesignTools\2026.1\Vivado\bin'
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$xvlog = Join-Path $VivadoBin 'xvlog.bat'
$xelab = Join-Path $VivadoBin 'xelab.bat'
$xsim = Join-Path $VivadoBin 'xsim.bat'
foreach ($exe in @($xvlog,$xelab,$xsim)) {
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {throw "Missing Vivado simulator: $exe"}
}
$outBase = Join-Path $root 'build\reproduction\phase18'
New-Item -ItemType Directory -Force -Path $outBase | Out-Null
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
$run = Join-Path $outBase "xsim_$stamp"
if (Test-Path -LiteralPath $run) {throw "Refusing overwrite: $run"}
New-Item -ItemType Directory -Path $run | Out-Null
Push-Location $run
try {
    $sources = @(
        (Join-Path $root 'rtl\fs_reset_sync.sv'),
        (Join-Path $root 'rtl\fs_uart_rx.sv'),
        (Join-Path $root 'tests\rtl\phase18_async_tb.sv')
    )
    & $xvlog -sv @sources 2>&1 | Tee-Object -FilePath 'xvlog_console.log'
    if ($LASTEXITCODE -ne 0) {throw 'Phase 18 RTL compilation failed'}
    & $xelab phase18_async_tb -s phase18_async_sim 2>&1 | Tee-Object -FilePath 'xelab_console.log'
    if ($LASTEXITCODE -ne 0) {throw 'Phase 18 simulation elaboration failed'}
    & $xsim phase18_async_sim -runall 2>&1 | Tee-Object -FilePath 'xsim_console.log'
    if ($LASTEXITCODE -ne 0) {throw 'Phase 18 RTL simulation failed'}
    if (-not (Select-String -LiteralPath 'xsim_console.log' -SimpleMatch 'PHASE18_XSIM_PASS:' -Quiet)) {
        throw 'Simulation completed without the explicit passing assertion marker'
    }
    'PHASE18_XSIM_PASS: original RTL digital behavior only; not hardware signoff' |
      Set-Content -LiteralPath 'simulation_result.txt' -Encoding UTF8
    Write-Host "PASS: Phase 18 RTL digital simulation; inspect $run"
} finally {Pop-Location}
