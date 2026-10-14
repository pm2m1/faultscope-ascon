# Phase 17 — PROVISIONAL Rev. C configuration-bank routed candidate

## Purpose and hard boundary

Separate Vivado **full-device** reproduction for the **PROVISIONAL Digilent Nexys 4 DDR Rev. C**, FPGA `xc7a100tcsg324-1`, with supported configuration bank properties. This is a research **candidate**, not an electrically qualified physical board. Neither the board revision nor actual supply has been physically checked. No board is connected and **no bitstream is generated**.

**Original, unmodified controls:** Phase 15 base pin XDC, Phase 15 routed DCP/verification and Phase 16 gap audit remain untouched. The only new electrical XDC is `constraints/phase17_cfg_rev_c_overlay.xdc` containing exactly two commands:

```tcl
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
```

**Evidence and rationale**: Digilent [Nexys 4 DDR schematic](https://digilent.com/reference/_media/nexys4-ddr/nexys_4_ddr_sch.pdf), CONFIG FPGA bank drawing, connects `CFG_BVS_0` to `VCC3V3` (P8 on IC8F); [Digilent Rev. C pin master](https://github.com/Digilent/digilent-xdc/blob/master/Nexys-4-DDR-Master.xdc). AMD UG912 [CFGBVS](https://docs.amd.com/r/en-US/ug912-vivado-properties/CFGBVS) and [CONFIG_VOLTAGE](https://docs.amd.com/r/en-US/ug912-vivado-properties/CONFIG_VOLTAGE) define the corresponding VCCO / 3.3 values for that board's intended configuration-bank supply. Actual VCCO_0 must be verified for the specific physical PCB before **hardware/bitstream signoff**. Do not apply this profile to an unconfirmed Nexys A7 or plain Nexys 4.

## Procedure — Windows PowerShell, separate review branch

From `C:\Projects\faultscope-ascon`, with Phase 16 merged at `dfd6d1a` and its original Phase 15 local evidence preserved:

```powershell
git status --short
git switch -c phase17-cfg-voltage
# Extract the pilot ZIP to the repository root.
& 'C:\Users\mishr\anaconda3\python.exe' -m pytest tests/test_phase17_cfg_candidate.py -v
& 'C:\Users\mishr\anaconda3\python.exe' scripts/phase17_cfg_review.py --preflight-only
.\scripts\phase17_cfg_candidate.ps1
```

`phase17_cfg_candidate.ps1` validates the original Phase 15 DCP hash, signed-off-as-candidate Phase 15 verification file and the accepted LF or strict uniform CRLF XDC hash using **Phase 16's existing provenance logic**. It refuses an edited RTL worktree, outside-baseline directory and output overwrite. Output is a **new** UTC timestamped directory under `build/reproduction/phase17`. No file in Phase 12–16 is edited.

The Vivado script reads the original Phase 15 XDC **before synthesis**; after `synth_design` opens a mapped design, it `read_xdc`s the strictly checked two-property Phase 17 overlay. The properties are checked before and after fresh optimization/placement/routing, then a **new** routed checkpoint is written. Reports include routed DRC, methodology, clock network/interactions, external timing coverage, synchronizer FFs and direct nets. No arbitrary `set_input_delay`, `set_output_delay`, false paths or clock exceptions are inserted.

Accepted *automated* verdict (not yet proven on Windows): `ROUTED_CFG_CANDIDATE_REVIEW_REQUIRED`, requiring a new routed checkpoint, exact config property values, exact pins and FF chains, nonnegative modeled internal setup/hold slack, and no `CFGBVS-1` finding in the DRC text. **All other DRC/methodology findings require manual review**, because source-code checks and presence of a report do not prove electrical signoff. If a Vivado command fails, retain the output and report the exact console error without relaxing guards.

## What to compare after running

Review `verification.json`, `source_context.tsv`, `internal_metrics.tsv`, `pin_assignment.tsv`, `synchronizer_cells.tsv`, `synchronizer_edges.tsv`, `post_route_drc.rpt`, `methodology.rpt`, `post_route_timing.rpt`, `clock_networks.rpt`, `clock_interaction.rpt`, `check_timing.rpt`, and `cdc.rpt`. The machine-readable `setup_delta_vs_phase15_ns` and `hold_delta_vs_phase15_ns` are *observed implementation differences*; there is no promise of increased slack. The Phase 15 reference has +1.471 ns internal setup and +0.022 ns hold, 3,772 FFs and 3,538 slice LUTs.

Open signoff items even after `CFGBVS-1` disappears:

- The physical **Rev. C** board, VCCO_0 electrical measurements and configuration compatibility remain **NOT VERIFIED**.
- UART RX is asynchronous: `report_cdc` omits missing input delay ports and no analog MTBF can be inferred from two co-located `ASYNC_REG` FFs.
- UART TX and LEDs have no characterized external timing budgets; the active-low reset button's bounce/pulse/clock start/recovery/removal behavior is **NOT VERIFIED**. Do not invent synchronous delays or false paths to remove Vivado `TIMING-18` methodology warnings.
- No board programming, USB-UART traffic, fault insertion or voltage measurements occurred; use synthetic keys only in any later hardware tests.
- Any generated report is a **candidate under manual review**; never call Phase 17 hardware-qualified or security-certified.

**Only after local review + CI:** stage and commit these Phase 17 source/test/doc files; do not commit `build/`, FPGA DCPs, `.Xil/`, `clockInfo.txt` or logs. Keep all past evidence locally backed up.
