[CmdletBinding()]
param(
    [string]$Vivado = 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat',
    [string]$Python = 'python',
    [ValidateSet('baseline','instrumented','protected','uart_protected')]
    [string[]]$Designs = @('baseline','instrumented','protected','uart_protected'),
    [ValidateRange(2,1000)][double[]]$Periods = @(10.0),
    [string]$OutputRoot = ''
)
$ErrorActionPreference = 'Stop'
$Designs = @($Designs | ForEach-Object { $_.ToLowerInvariant() })
if (-not $Designs.Count -or @($Designs | Sort-Object -Unique).Count -ne $Designs.Count) { throw 'Designs must be a nonempty unique selection' }
if (-not $Periods.Count -or @($Periods | Sort-Object -Unique).Count -ne $Periods.Count -or @($Periods | Where-Object { [double]::IsNaN($_) -or [double]::IsInfinity($_) }).Count) { throw 'Periods must be a nonempty finite unique selection' }
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $OutputRoot) { $OutputRoot = Join-Path $repoRoot ('build\reproduction\phase12\run_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')) }
if (-not [IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot = Join-Path $repoRoot $OutputRoot }
$OutputRoot = [IO.Path]::GetFullPath($OutputRoot)
$allowedRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'build\reproduction\phase12'))
if ($OutputRoot -ne $allowedRoot -and -not $OutputRoot.StartsWith($allowedRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence output must be within build/reproduction/phase12' }
if (-not (Test-Path -LiteralPath $Vivado)) { $Vivado = (Get-Command $Vivado -ErrorAction Stop).Source }
foreach ($period in $Periods) {
    foreach ($design in $Designs) {
        $periodLabel = $period.ToString('R',[Globalization.CultureInfo]::InvariantCulture)
        $runDir = Join-Path $OutputRoot ($design + '_' + $periodLabel + 'ns')
        if (Test-Path -LiteralPath $runDir) { throw "Refusing to overwrite existing run: $runDir. Choose a new OutputRoot." }
    }
}
if (Test-Path -LiteralPath (Join-Path $OutputRoot 'provenance.json')) { throw 'Existing provenance found; choose a new OutputRoot to preserve evidence' }
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
Push-Location $repoRoot
try {
    $revision = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Cannot establish Git revision' }
    $status = @(& git status --porcelain)
    $sourceFiles = @(Get-ChildItem rtl -Filter *.sv) + @(Get-Item scripts\phase12_vivado_ooc.tcl,scripts\phase12_vivado.ps1,scripts\phase12_report.py)
    $hashes = @{}
    $snapshot = Join-Path $OutputRoot 'source_snapshot'
    foreach ($file in $sourceFiles) {
        $relative = $file.FullName.Substring($repoRoot.Length + 1).Replace('\','/')
        $hashes[$relative] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        $dest = Join-Path $snapshot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $dest
    }
    $manifest = @{
        utc_started = [DateTime]::UtcNow.ToString('o'); git_revision = $revision; git_status = $status;
        source_sha256 = $hashes; vivado_path = $Vivado; vivado_version = @(& $Vivado -version);
        windows_version = [Environment]::OSVersion.VersionString; git_version = (& git --version);
        python_version = @(& $Python --version 2>&1); target_part = 'xc7a100tcsg324-1'; periods_ns = $Periods;
        scope = 'OOC internal timing only; external interfaces and asynchronous reset unconstrained; no bitstream'
    }
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputRoot 'provenance.json') -Encoding utf8
    & git diff --binary | Set-Content -LiteralPath (Join-Path $OutputRoot 'working_tree.patch') -Encoding utf8
    $runs = @()
    foreach ($period in $Periods) {
        $periodLabel = $period.ToString('R',[Globalization.CultureInfo]::InvariantCulture)
        foreach ($design in $Designs) {
            $name = $design + '_' + $periodLabel + 'ns'
            $runDir = Join-Path $OutputRoot $name
            Write-Host "Phase 12: implementing $design at $periodLabel ns"
            $start = [DateTime]::UtcNow
            New-Item -ItemType Directory -Path $runDir | Out-Null
            Push-Location $runDir
            try {
            & $Vivado -mode batch -source (Join-Path $PSScriptRoot 'phase12_vivado_ooc.tcl') -log (Join-Path $OutputRoot ($name + '.log')) -journal (Join-Path $OutputRoot ($name + '.jou')) -tclargs $design $periodLabel $runDir 2>&1 | Tee-Object -FilePath (Join-Path $OutputRoot ($name + '_console.log'))
            $code = $LASTEXITCODE
            } finally { Pop-Location }
            $runs += @{design=$design; period_ns=$period; exit_code=$code; started_utc=$start.ToString('o'); ended_utc=[DateTime]::UtcNow.ToString('o')}
            $runs | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $OutputRoot 'run_exit_codes.json') -Encoding utf8
            if ($code -ne 0) { Write-Warning "Vivado failed for $name, exit $code; evidence retained" }
        }
    }
    $periodArguments = @($Periods | ForEach-Object { $_.ToString('R',[Globalization.CultureInfo]::InvariantCulture) })
    $reportArguments = @((Join-Path $PSScriptRoot 'phase12_report.py'), $OutputRoot, '--require-verified', '--expected-designs') + $Designs + @('--expected-periods') + $periodArguments
    & $Python @reportArguments
    if ($LASTEXITCODE -ne 0) { throw 'Phase 12 evidence validation failed or internal timing failed; inspect summary.json and reports' }
    if (@($runs | Where-Object { $_.exit_code -ne 0 }).Count) { throw 'One or more Vivado runs failed; inspect logs and summary' }
} finally { Pop-Location }
