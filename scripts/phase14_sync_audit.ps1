[CmdletBinding()]
param(
    [string]$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat',
    [string]$Python = 'C:\Users\mishr\anaconda3\python.exe',
    [string]$Checkpoint = 'build\reproduction\phase12\phase13_uart_ooc_10ns\uart_protected_10ns\post_route.dcp',
    [string]$OutputRoot = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = 'build\reproduction\phase14\audit_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') }
if (-not [IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot = Join-Path $root $OutputRoot }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$allowed = [IO.Path]::GetFullPath((Join-Path $root 'build\reproduction\phase14'))
if ($OutputRoot -ne $allowed -and -not $OutputRoot.StartsWith($allowed + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputRoot must be within build/reproduction/phase14'
}
if (Test-Path -LiteralPath $OutputRoot) { throw "Refusing to overwrite prior audit: $OutputRoot" }
if (-not [IO.Path]::IsPathRooted($Checkpoint)) { $Checkpoint = Join-Path $root $Checkpoint }
$Checkpoint = [IO.Path]::GetFullPath($Checkpoint)
if (-not (Test-Path -LiteralPath $Checkpoint -PathType Leaf)) { throw "Missing routed Phase 13 checkpoint: $Checkpoint" }
if (-not (Test-Path -LiteralPath $Vivado -PathType Leaf)) { throw "Missing Vivado batch executable: $Vivado" }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Missing Python executable: $Python" }

Push-Location $root
try {
    $dirty = @(& git status --porcelain -- rtl)
    if ($LASTEXITCODE -ne 0) { throw 'Git status check failed' }
    if ($dirty.Count -ne 0) { throw "RTL working tree has modifications; audit requires clean committed RTL: $($dirty -join ', ')" }
    $revision = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot establish revision' }
    # Metadata only: Vivado loads the checkpoint and never changes it.
    New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
    $sha = (Get-FileHash -LiteralPath $Checkpoint -Algorithm SHA256).Hash.ToLowerInvariant()
    $rtlHashes = @{}
    foreach ($p in @('rtl/fs_reset_sync.sv','rtl/fs_uart_rx.sv','rtl/faultscope_uart_top.sv')) {
        $rtlHashes[$p] = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    @{
        audit_scope = 'Phase14 mapped post-route synchronizer audit only; no board or CDC signoff'
        checkpoint = $Checkpoint
        checkpoint_sha256 = $sha
        git_revision = $revision
        rtl_source_sha256 = $rtlHashes
        created_utc = [DateTime]::UtcNow.ToString('o')
    } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutputRoot 'manifest.json') -Encoding utf8

    $tcl = Join-Path $PSScriptRoot 'phase14_sync_audit.tcl'
    & $Vivado -mode batch -source $tcl -log (Join-Path $OutputRoot 'vivado.log') `
        -journal (Join-Path $OutputRoot 'vivado.jou') -tclargs $Checkpoint $OutputRoot 2>&1 |
        Tee-Object -FilePath (Join-Path $OutputRoot 'vivado_console.log')
    if ($LASTEXITCODE -ne 0) { throw 'Vivado read-only audit failed; inspect vivado.log' }
    & $Python (Join-Path $PSScriptRoot 'phase14_sync_report.py') $OutputRoot --require-pass |
        Tee-Object -FilePath (Join-Path $OutputRoot 'verification.json')
    if ($LASTEXITCODE -ne 0) { throw 'Phase 14 synchronizer audit NOT VERIFIED; inspect TSV and logs, do not claim CDC signoff' }
    Write-Host "PASS: Mapped synchronizer preservation audit. Evidence at $OutputRoot"
    Write-Host 'IMPORTANT: External I/O timing, analog MTBF, reset recovery/removal and board behavior remain NOT VERIFIED.'
} finally {
    Pop-Location
}
