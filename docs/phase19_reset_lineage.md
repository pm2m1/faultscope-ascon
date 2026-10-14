# Phase 19 — Routed reset-source lineage and polarity *diagnostics*

## Scope

Read-only Vivado 2026.1 inspection of the **existing Phase 17** `post_route.dcp`, on the **PROVISIONAL Nexys 4 DDR Rev. C** (`xc7a100tcsg324-1`). The baseline evidence is rehashed through the existing Phase 18 preflight, including prior Phase 15 checkpoint provenance and Phase 17 configuration-overlay CRLF equivalence. No new implementation, modified RTL, XDC, timing exceptions, bitstream or board programming.

**Goal:** identify the *actual output-pin/port drivers* and combinational logic cone of all three reset-release `FDCE/CLR` and both UART receive `FDPE/PRE` pins, rather than trusting synthesized **net names**. Phase 18 reported all RX presets as `core/round_count_q_reg[3]`, which might be an optimized alias, **not evidence of a wrong source or proof of a right one**. The `FDCE CLR` and `FDPE PRE` physical primitive controls are both **active HIGH**; an external active-low `rst_n` or active-high `rst_n_core` must therefore have the appropriate inversion in its actual logic cone.

## Procedure

After `main` contains Phase 18 merge `d4e7794`, create `phase19-reset-lineage` on a clean working tree, extract this ZIP into the repository, then run:

```powershell
& 'C:\Users\mishr\anaconda3\python.exe' -m pytest tests/test_phase19_reset_lineage.py -v
& 'C:\Users\mishr\anaconda3\python.exe' scripts\phase19_reset_lineage_report.py --preflight-only
.\scripts\phase19_reset_lineage.ps1
```

The Vivado command opens the authenticated Phase 17 routed checkpoint and exports TSVs containing the physical `rst_n` IBUF, actual async CLR/PRE pin objects, **pin/port driver objects**, `all_fanin` startpoint objects, combinational LUT/BUF cell REF_NAME and `INIT` values when present, and endpoints reachable from final reset-release Q. `check_timing.rpt` and `methodology.rpt` remain diagnostics; do not create guessed delays to remove five `TIMING-18` warnings.

### Important interpretation constraints

- `startpoints.tsv` is an enumerated *candidate source set*, not automatically complete proof of signal polarity or absence of reconvergent logic. `control_drivers.tsv` identifies immediate physical drivers; `comb_cone.tsv` exposes LUT/BUF primitives and INIT codes to examine inversion. Actual logic truth tables must be assessed in the manual review, especially if a LUT has several inputs or nets have aliases.
- A `RESET_LINEAGE_EVIDENCE_REVIEW_REQUIRED` verdict means only that evidence collection and schema/provenance checks succeeded. **Actual source-to-sink polarity is always `MANUAL_REVIEW_REQUIRED`**, never accepted automatically.
- The physical external `rst_n` pin is active-low while the `FDCE` CLR and `FDPE` PRE pins assert high. For reset FFs the expected root is the physical `rst_n` port; for RX PRE the expected clocked root is `u_reset_sync/release_pipe_q_reg[2]/Q`. These root names appear in a clearly labeled observation field, *not* as a signoff verdict.
- If `all_fanin` shows an unexpected root, or a multi-input LUT/unknown primitive, preserve the raw rows for investigation. Do not assume the unintuitive `core/round_count_q_reg[3]` name identifies its source register.
- **NOT VERIFIED:** physical min reset pulse width, recovery/removal, UART analog metastability and MTBF, clock startup, button bounce, actual PCB/revision, electrical I/O timing and any hardware behavior. No bitstream is produced.

## Manual review gate

Collect the new Phase 19 `verification.json`, `context.tsv`, `reset_input.tsv`, `controls.tsv`, `startpoints.tsv`, `control_drivers.tsv`, `comb_cone.tsv`, `release_fanout.tsv`, `check_timing.rpt`, `methodology.rpt`. Assess whether each source's exact driver objects and polarity-inversion logic match the intended reset behavior. **Do not commit or merge Phase 19 until actual Vivado output has been reviewed**, including any tool errors, unexpected sources or unconstrained reset paths. Preserve all generated checkpoint evidence under `build/` and in backups outside Git.
