# Phase 23 — Cross-phase evidence-gap inventory and research qualification

**Scope:** offline, read-only evidence provenance and claim-qualification audit. Begin from merged Phase 22 `main` commit **`a63f22e`**. Do **not** edit RTL, XDC, timing exceptions, routed checkpoints or bitstreams. Do **not** infer board signoff from research milestone completion. The configured board is **provisional Nexys 4 DDR Rev. C**; a physical board/revision has not been confirmed.

## Why this phase exists

Phases 15–22 established a routed FPGA candidate and progressively narrower observations of its clock, asynchronous UART, reset, configuration voltage, pin connectivity, timing path queries and I/O assignment. The research evidence is substantial, but its conclusions have different scopes. Phase 23 consolidates those accepted reports without another Vivado run or alterations to FPGA implementation files. It distinguishes:

- **Model-bound verified observations**, such as the accepted Phase 17 routed checkpoint SHA-256, internal timing slacks, six pin assignments, eight routed reset pin edges, two LUT1 logical inverters, and ten individual path queries.
- **Unqualified physical requirements**, such as reset pulse width/bounce, oscillator startup, external timing budgets, UART analog MTBF, board revision, board programming and on-board operation.
- **Evidence limitations:** recorded report hashes cover all packaged reports for Phases 19–22, but some files in archived Phases 15–18 have no individual manifest SHA-256. The ZIPs have local SHA-256 and CRC; neither provides an external trusted signature of historical origin.

No amount of positive internal setup slack establishes physically qualified external asynchronous timing.

## Exact input evidence

Phase 23 takes the existing review archives **by exact filename** in a single directory (default `Downloads`):

| Phase | Required ZIP |
|---|---|
| 15 | `faultscope_phase15_review_reports.zip` |
| 16 | `faultscope_phase16_review.zip` |
| 17 | `faultscope_phase17_review.zip` |
| 18 | `faultscope_phase18_review.zip` |
| 19 | `faultscope_phase19_review.zip` |
| 20 | `faultscope_phase20_review.zip` |
| 21 | `faultscope_phase21_review.zip` |
| 22 | `faultscope_phase22_review.zip` |

Also required: the original accepted **Phase 17 routed DCP**, **not** a substitute or newly routed checkpoint:

`build\reproduction\phase17\nexys4_ddr_rev_c_cfg_20261014T131338Z\post_route.dcp`

Expected SHA-256:

`633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`

Previous Phase 15 DCP anchor: `869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199`.

The validator checks ZIP member inventories, safely parses archive paths, verifies all manifest-listed report hashes, validates signed-off/not-verified boundaries in each manifest, checks cross-phase source/sink/delay/recorded slack consistency for all ten timing queries, verifies pin inventory and direct reset pin-edge/inverter evidence, and checks the live Phase 17 DCP SHA-256. It does *not* accept new timing numbers or substitute a fabricated positive slate for physical unknowns.

## Windows PowerShell workflow

Run each code block separately, with a blank line between blocks, to avoid concatenating commands in PowerShell.

```powershell
cd C:\Projects\faultscope-ascon

git status --short

git switch -c phase23-evidence-gap-matrix

Expand-Archive `
  -LiteralPath "$env:USERPROFILE\Downloads\faultscope_phase23_evidence_gap_pilot.zip" `
  -DestinationPath . -Force
```

Review archive preflight (all eight ZIPs must already be in Downloads):

```powershell
$names = @(15,16,17,18,19,20,21,22) | ForEach-Object {
    if ($_ -eq 15) { 'faultscope_phase15_review_reports.zip' }
    else { "faultscope_phase${_}_review.zip" }
}
$names | ForEach-Object {
    $p = Join-Path "$env:USERPROFILE\Downloads" $_
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) {throw "Missing archive: $p"}
}

& 'C:\Users\mishr\anaconda3\python.exe' -m pytest tests/test_phase23_evidence_gap.py -v

git diff --check

& 'C:\Users\mishr\anaconda3\python.exe' `
  scripts\phase23_evidence_gap_matrix.py `
  --input-dir "$env:USERPROFILE\Downloads" `
  --checkpoint 'build\reproduction\phase17\nexys4_ddr_rev_c_cfg_20261014T131338Z\post_route.dcp' `
  --preflight-only
```

Expected preflight-only verdict: `PHASE23_INPUT_EVIDENCE_VERIFIED` (not a hardware signoff). Do not continue if it reports `NOT_VERIFIED`.

Generate a separate timestamped **derived** evidence matrix:

```powershell
.\scripts\phase23_evidence_gap_matrix.ps1
```

Expected verdict: `EVIDENCE_MATRIX_REVIEW_REQUIRED` (the correct outcome, **not** a closed hardware qualification). Result files in `build\reproduction\phase23\evidence_gap_<UTC>` are:

- `verification.json` — normalized input-source hashes, accepted anchors, counts and explicit limitations
- `evidence_sources.tsv` — per-phase archive hashes and historical hash-coverage classes
- `qualified_claims.tsv` — source-bounded engineering assertions, never board signoff
- `open_gaps.tsv` — eight **OPEN** dependencies plus one archive-integrity **LIMITATION**
- `dossier.md` — human-readable review summary

Package these **five** generated files for independent review, but do not commit them or the original report ZIPs into the source repository. Generated build outputs remain locally ignored as before.

## Deliberate acceptance limits

1. The five `TIMING-18` missing-delay warnings remain open for `rst_n`, `uart_rx_i`, `uart_tx_o`, `led_busy_o`, and `led_alarm_o`.
2. Six `rst_n` recovery/removal path queries have unavailable (not zero or passing) slack; four modeled UART preset paths report finite slack. The `/C` timing startpoint and `/Q` routed-net driver are different layers of description, as documented in Phase 22.
3. The 100 MHz clock report is **not** a measured reset-button pulse-width report.
4. Board revision, oscillator behavior, reset electrical transitions, analog metastability MTBF, physical functionality and programming remain unverified.
5. Historic ZIP-level hash checking proves internal consistency with recorded hashes/anchors, **not independent identity or authenticity of the original producer**. Phases 15–18 have legacy member-hash gaps.
6. Phase 24 can deliver a **qualified research release** with an explicit signoff-boundary statement. It cannot honestly certify hardware operation without a board and suitable external timing sources.

**Do not commit Phase 23 until the generated matrix and input digests have been reviewed.**
