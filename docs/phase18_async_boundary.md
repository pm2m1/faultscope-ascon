# Phase 18 — Pre-silicon UART/reset asynchronous-boundary evidence pilot

## Scope

Read-only inspection of the **existing** Phase 17 routed full-device checkpoint for **provisional** Digilent Nexys 4 DDR Rev. C (XC7A100T CSG324-1), plus **separately run** RTL digital simulation of the original two modules `fs_reset_sync.sv` and `fs_uart_rx.sv`. No RTL, Phase 15/17 XDC, routing, timing exceptions, or checkpoint is modified. No bitstream is generated. Do not commit this pilot until actual Windows Vivado and XSim evidence has been reviewed.

Phase 17 accepted evidence: `build/reproduction/phase17/nexys4_ddr_rev_c_cfg_20261014T131338Z/post_route.dcp`, SHA-256 `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`. The Phase 18 Python preflight independently revalidates the Phase 17 candidate against the pinned Phase 15 baseline and the saved checkpoint/report digests. Phase 17 overlay accepts **only** byte-identical or uniform LF/CRLF-equivalent checkout (Windows Git). Any content edit fails closed.

## Observed RTL design to test

* `fs_reset_sync`: async active-low assertion of three `FDCE` release stages; three rising clock edges needed to deassert `rst_n_sync`, while async assertion immediately clears it. Clock required throughout release.
* `fs_uart_rx`: two `FDPE` receiver sync stages, asynchronously preset to idle. Only the second stage is used by receiver state machine (inspect routed first-stage fanout separately). 8N1 sampled at `CLOCKS_PER_BIT >= 8`.
* Phase 17 already showed five placed `ASYNC_REG=1` flops and three Q→D direct connections. Phase 18 additionally checks the physical `uart_rx_i` → input buffer → first-stage `D` queries exact Q→D path timing, and checks that stage 0 has no other sequential fanout.

Digital event-based simulation cannot show metastability, analog propagation, MTBF, minimum asynchronous reset pulse width, PCB button bounce, power-up timing, or clock jitter. It also cannot establish bus-level integration/fault-security semantics. The HDL testbench tests only reset propagation/release, short start-bit glitches, correct 8N1 reception, and recovery after reset during partial reception. Simulation of RTL does not replace a timed gate-level simulation.

## Windows execution (new branch, preserve old runs)

```powershell
cd C:\Projects\faultscope-ascon
git switch -c phase18-async-boundaries
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\faultscope_phase18_async_boundary_pilot.zip" -DestinationPath . -Force
& 'C:\Users\mishr\anaconda3\python.exe' -m pytest tests/test_phase18_async.py -v
& 'C:\Users\mishr\anaconda3\python.exe' scripts/phase18_async_report.py --preflight-only
.\scripts\phase18_xsim.ps1
.\scripts\phase18_async_audit.ps1
```

Simulated outputs are under `build/reproduction/phase18/xsim_<timestamp>/`; routed-audit outputs under `build/reproduction/phase18/async_audit_<timestamp>/` and are Git-ignored. The audit verdict `ASYNC_BOUNDARY_EVIDENCE_REVIEW_REQUIRED` is **not** signoff. Keep all Vivado/XSim output for manual review.

Expected audit files: `context.tsv`, `stages.tsv`, `interstage_timing.tsv`, `async_input.tsv`, `check_timing.rpt`, `rx_interstage_max.rpt`, `rx_interstage_min.rpt`, `methodology.rpt`, `cdc.rpt`, `verification.json`. HDL simulation requires the explicit `PHASE18_XSIM_PASS` line. The simulation and the routed audit must both pass and be reviewed before treating the pilot as a candidate research milestone.

## Explicitly open signoff gaps

1. UART input is **externally asynchronous**: do not add guessed `set_input_delay` or a false synchronization clock. The first sync stage may enter metastability in actual silicon; physical MTBF is **NOT VERIFIED**. The missing-delay `TIMING-18` warning remains a known exception, not closure.
2. The interstage Q→D timing confirms routed clocked behavior only. First-stage D arrival has no clock-relative valid data setup/hold requirement. Phase 18 does not derive an analog synchronizer MTBF from a digital path.
3. Reset physical pulse width, switch bounce, recovery/removal and startup with a stopped or unstable oscillator are **NOT VERIFIED**. RTL expects the clock to run during release. No broadband false-path/reset timing suppression is introduced.
4. Outputs `uart_tx_o`, `led_busy_o`, `led_alarm_o` remain unconstrained for justified external timing. The five `TIMING-18` warnings from Phase 17 should remain visible until appropriate board/peripheral model decisions.
5. Board part and physical Rev. C identity are not independently verified on a physical PCB. No configuration-bitstream, FTDI COM-port, LED, analog I/O bank voltage or fault-injection hardware verification is claimed. Continue to use synthetic demo keys only, because UART transport is not authenticated or encrypted.

## Review gate

Only approve a research-milestone **draft** PR after (a) all Phase 18 Python negative/positive tests pass, (b) the XSim run ends with its passing marker and no failed assertions, (c) the routed-checkpoint audit is successful and its original checkpoint digest unchanged, (d) the actual collected Vivado reports are manually reviewed, and (e) the diff includes only Phase 18 test/scripts/docs. Do not merge Phase 18 based on local Python tests alone.
