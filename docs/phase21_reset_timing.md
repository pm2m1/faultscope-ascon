# Phase 21 — Read-only asynchronous-reset timing and modeling audit

## Engineering purpose

Scope: a fresh, **read-only** diagnostic of the **accepted Phase 17 fully routed checkpoint** on a **PROVISIONAL Nexys 4 DDR Rev. C** target (part `xc7a100tcsg324-1`). This phase introduces **no RTL or XDC changes**, no timing exceptions or guessed I/O delays, no new synthesis/placement/routing, and **no bitstream**. Physical board configuration and minimum reset timing remain **NOT VERIFIED**.

Phase 20 verified eight expected mapped reset connections and both one-input inverter LUT truth tables. Phase 18 used XSim for selected digital behavior, including asynchronous assertion and three-edge release. Neither milestone establishes physical reset recovery/removal, minimum pulse width, clock startup, analog metastability, or bounce behavior. Phase 21 **does not repeat XSim** because the unresolved question is what the existing Vivado timing model actually covers.

## What Phase 21 does

1. Verify Phase 17 DCP provenance and existing clock, part, config properties before Vivado launches.
2. Reopen the routed DCP. For each of three `FDCE/CLR` reset controls and two `FDPE/PRE` UART controls, independently query available Vivado maximum and minimum timing paths. Export **ten explicit observations**. An absent path is recorded as `NO_PATH_REPORTED`, **not** as timing met. If a path exists but Vivado does **not** report a finite `SLACK` (observed on unconstrained external `rst_n` paths), the Tcl exporter records `PATH_REPORTED_SLACK_UNAVAILABLE` with `slack_ns=-`: this means **no qualified slack assessment**, not zero slack or timing closure. The Python validator also accepts the *original* Vivado 2026.1 export's blank eighth column strictly for `rst_n` path observations, and normalizes it to the same classification without altering the raw report. An error fails validation.
3. Export `check_timing.rpt`, `timing_summary.rpt` with unconstrained paths, `methodology.rpt`, and reset-control directed `report_timing` outputs. Do not silently suppress the five known `TIMING-18` input/output delay warnings.
4. Export `clock_pulse_width.rpt` with `report_pulse_width`. According to AMD UG835/UG906, this applies to **clock-network pulse/period checking, not external reset pulse width**. It cannot validate a mechanical button's minimum reset pulse duration, asynchronous reset assertion propagation under all electrical conditions, or oscillator startup behavior.
5. Require manual review of all exported reports. A query returning numeric slack alone is not a reset recovery/removal signoff. Constrained reset timing requires justified source models and validated operating conditions; never synthesize an input-delay number to make the report green.

## Expected interpretation

The validator emits `RESET_TIMING_EVIDENCE_REVIEW_REQUIRED` if inputs and reports are well formed. It never emits a hardware-signoff verdict. Its `timing_path_observations` field is descriptive, not a pass/fail timing-closure guarantee; `timing_paths_found` is the count of queries returning one timing path (including those without slack). The new `timing_paths_with_numeric_slack`, `timing_paths_without_numeric_slack` and `timing_paths_not_reported` fields separate the three outcomes. None is a count of paths proven physically safe. No-path results are left open. `clock_pulse_report_scope` must remain `CLOCK_NETWORK_ONLY_NOT_EXTERNAL_RESET`.

Physical minimum reset pulse width, asynchronous recovery/removal, device power-up and oscillator startup, clock jitter and reset-button bounce, external UART and LED timing budgets, and analog synchronizer MTBF remain **NOT VERIFIED**. The FPGA board has not been physically confirmed. The original five `TIMING-18` warnings are expected until actual external interface timing constraints can be defensibly derived. The `report_cdc` skip of unconstrained external ports remains relevant.

## Evidence and merge gate

New output directory is generated under `build/reproduction/phase21/reset_timing_<UTC>/`, which must remain Git-ignored. Expected files: `context.tsv`, `path_observations.tsv`, `check_timing.rpt`, `timing_summary.rpt`, `methodology.rpt`, `clock_pulse_width.rpt`, four scoped timing reports, and `verification.json`. Independently review the ZIP and all SHA-256 values before writing a manual addendum or opening a PR. Only after a manual review and full repository regressions may the new Phase 21 scripts/tests/docs be considered for a draft PR. No bitstream or board signoff is authorized.

Sources: AMD Vivado 2026.1 Tcl UG835 (`report_timing`, `report_timing_summary`, `report_pulse_width`) and AMD Vivado 2026.1 UG906 (`Report Pulse Width`).

The clock pulse width diagnostic is a clock-network check and is not external reset timing qualification.
