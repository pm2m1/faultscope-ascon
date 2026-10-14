# Phase 24 — Qualified research-release candidate

**Scope:** research-release reproducibility and provenance, not a bitstream, hardware programming, or board-level signoff. Begin from merged Phase 23 commit `1ce848e480dcfb65045ee04b89d2b67de57ade39` on `main` with an otherwise clean working tree. The user-side accepted Phase 17 routed checkpoint remains external to Git and MUST be present locally.

## What this pilot establishes

- Runs **the Phase 23 validator unchanged** on the original, explicitly named Phase 15–22 review ZIPs and the actual Phase 17 DCP. This is a fresh digest and semantic consistency check; it does **not** substitute a guessed certificate or create timing exceptions.
- Loads `faultscope_phase23_review.zip`, verifies its exact member inventory and compares all **five** files **byte-for-byte** to newly derived Phase 23 outputs from the eight historical ZIPs. This is stronger than trusting the copied JSON verdict alone.
- Requires the accepted Phase 23 merge commit to be an ancestor of Git HEAD; inventories SHA-256 over every tracked `HEAD` Git blob (not Windows CRLF checkout bytes), checks the pinned Ascon-C commit and blocks changes to historical tracked files. The pre-commit report covers **tracked HEAD only**, not untracked Phase 24 files. Re-run on `main` after Phase 24 is merged to freeze the final release source.
- Makes a research-release *candidate* manifest, per-file source inventory, nine-archive evidence inventory, explicit release gates, and human-readable release notes. It does not download CI artifacts or call GitHub; **fresh Phase 24 PR CI must be checked separately**.

The acceptance result is `RESEARCH_RELEASE_REVIEW_REQUIRED`, never `BOARD_VERIFIED`. External I/O timing is **NOT QUALIFIED**. Research claims remain scoped to cryptographic-reference checks, RTL simulation/formal work, and the routed timing *model* under the documented assumptions. The prior 8 claims, 8 open requirements, and 1 legacy evidence limitation remain unchanged.

## Inputs

Files in **one** Downloads folder:

- `faultscope_phase15_review_reports.zip`
- `faultscope_phase16_review.zip` through `faultscope_phase23_review.zip`, with one matching file for **each** integer phase 16–23.

And the accepted local checkpoint:

`build\reproduction\phase17\nexys4_ddr_rev_c_cfg_20261014T131338Z\post_route.dcp`

Expected DCP SHA-256: `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`.

## Windows pilot workflow

Run each block separately; do not concatenate PowerShell commands.

```powershell
cd C:\Projects\faultscope-ascon
git switch main
git pull --ff-only origin main
git status --short
git log -1 --oneline

git switch -c phase24-research-release
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\faultscope_phase24_release_pilot.zip" -DestinationPath . -Force
```

Run the offline regression and input preflight (Python 3.12, pytest, and Git installed):

```powershell
& 'C:\Users\mishr\anaconda3\python.exe' -m pytest tests/test_phase24_release_candidate.py -v
git diff --check
& 'C:\Users\mishr\anaconda3\python.exe' scripts/phase24_release_candidate.py --input-dir "$env:USERPROFILE\Downloads" --checkpoint 'build\reproduction\phase17\nexys4_ddr_rev_c_cfg_20261014T131338Z\post_route.dcp' --preflight-only
```

Expected preflight verdict: `PHASE24_RELEASE_INPUTS_VERIFIED` (not release approval). Stop if the result is `NOT_VERIFIED`.

Build five derived reports in a fresh, never-overwritten directory, without calling Vivado:

```powershell
.\scripts\phase24_release_candidate.ps1
```

Expected research verdict: `RESEARCH_RELEASE_REVIEW_REQUIRED`. Reports:

- `verification.json`
- `source_manifest.tsv`
- `evidence_manifest.tsv`
- `release_gates.tsv`
- `release_candidate.md`

Review and package:

```powershell
$audit = Get-ChildItem 'build\reproduction\phase24' -Directory |
  Where-Object Name -like 'release_candidate_*' |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $audit) { throw 'No Phase 24 release candidate found' }
$names = @('verification.json','source_manifest.tsv','evidence_manifest.tsv','release_gates.tsv','release_candidate.md')
$paths = $names | ForEach-Object {
    $file = Join-Path $audit.FullName $_
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Missing report: $file" }
    $file
}
Compress-Archive -LiteralPath $paths -DestinationPath "$env:USERPROFILE\Downloads\faultscope_phase24_review.zip" -Force
```

**Upload** `faultscope_phase24_review.zip` and the final preflight/runner output for independent review. **Do not commit, push, tag or merge yet.** An independently written manual-review addendum and a scoped draft PR are the next gates.

## Full project validation beyond the offline release pilot

The GitHub Actions workflows on the **Phase 24 PR head** (not only the Phase 23 merge) must pass:

1. `.github/workflows/verify.yml`: pinned external Ascon-C reference, locked `uv` dependencies, immutable campaign evidence, complete Python/Verilator/RTL tests, Yosys synthesis/output-mask SAT, and Node/Vite production build.
2. `.github/workflows/sequential-formal.yml`: 18-clock bounded controller SAT, completion witnesses, and intentionally failing negative controls.

The pre-existing Phase 23 merge head (`1ce848e`) passed both workflows. That historical CI success does **not** prove the future Phase 24 candidate has passed. On Ubuntu/macOS, use the workflows as documented, with Node 24 and Python 3.12. The Windows offline Phase 24 script does *not* silently claim it ran Verilator/Yosys locally. For Linux reproduction from the repository root:

```bash
mkdir -p references
git clone https://github.com/ascon/ascon-c.git references/ascon-c
git -C references/ascon-c checkout --detach "$(cat docs/ascon_reference_commit.txt)"
uv sync --locked --group dev
uv run faultscope-ascon verify-evidence
uv run python -m pytest tests/ -q
(cd frontend && npm ci && npm run build)
# See .github/workflows/verify.yml and sequential-formal.yml for Yosys/SAT tool setup.
```

## Deliberate unresolved qualifications

- No physically identified board: **provisional Nexys4 DDR Rev. C**; pin assignments and 100 MHz modeled clock do not confirm board revision or behavior.
- Five `TIMING-18` absent external input/output timing constraints remain open (`rst_n`, UART RX/TX, LED busy/alarm).
- Six external `rst_n` paths have unavailable slack (not zero or a pass). Four modeled UART release-to-preset paths show internal numeric slacks. Physical reset release, bounce, pulse width, oscillator startup, and jitter are **NOT VERIFIED**.
- UART metastability MTBF, actual USB-UART electrical timing, LED external delay assumptions, and actual programming/running on an FPGA are **NOT VERIFIED**.
- Phases 15–18 have incompletely member-hashed archival evidence. ZIP SHA-256 verifies the supplied bytes, not independent trusted origin; current local DCP rehash cannot certify remote board identity.
- No physical fault injection was demonstrated, no production cryptographic-library security claim is made, and neither countermeasure fault coverage nor implementation assurance extends outside the tested model.

**Post-merge:** re-run the Phase 24 pilot from merged `main` to capture the final Git commit snapshot, review the fresh hashes and CI, and only then consider an *explicitly qualified* research tag. This pilot does not create GitHub releases or tags and cannot perform physical FPGA signoff.
