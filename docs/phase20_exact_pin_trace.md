# Phase 20 — exact pin/segment reset-path investigation (research pilot)

**Target:** same PROVISIONAL Nexys 4 DDR Rev. C `xc7a100tcsg324-1` Phase 17 routed checkpoint, SHA-256 `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`. The physical PCB remains unverified. Phase 19 established source reachability, but reported `u_reset_sync/release_pipe_q_reg[2]/C` as the PRE fan-in startpoint; a raw fan-in name is not a pin-level connectivity proof.

## Specific questions

1. Does `rst_n` connect to physical `IBUF/I`, and does `IBUF/O` connect to `u_reset_sync/release_pipe_q[2]_i_1/I0`?
2. Does that `LUT1/O` directly drive all three `FDCE/CLR` inputs, and does `INIT=2'h1` implement the required inversion?
3. Does **`u_reset_sync/release_pipe_q_reg[2]/Q`** directly connect to `u_reset_sync/FSM_sequential_state_q[1]_i_2/I0`, and does that inverter's `O` directly drive both RX `FDPE/PRE` controls?
4. Are all eight expected links connected by matching routed net *segments*, and is the expected leaf primitive output the unique driver? A hierarchical `fs_reset_sync` boundary pin is not a second leaf electrical driver. `core/round_count_q_reg[3]` can be a net alias, but it must not be used to infer source identity.

## Run

From `C:\Projects\faultscope-ascon` on a new `phase20-exact-reset-pins` branch, expand the pilot ZIP into the repository. Run `python -m pytest tests/test_phase20_exact_pin.py -v` then `python scripts/phase20_exact_pin_report.py --preflight-only` and `./scripts/phase20_exact_pin_trace.ps1` (PowerShell notation: `.\scripts\phase20_exact_pin_trace.ps1`). The runner validates the Phase 15/17 provenance first. It opens the already-routed Phase 17 DCP read-only, writes a *new* timestamped folder in `build/reproduction/phase20`, and never runs synthesis, place/route, timing-exception edits, bitstream creation or board programming.

## Evidence and interpretation

- `context.tsv` — scope, tool, FPGA part and configured clock.
- `pin_edges.tsv` — eight exact source/destination pin pairs; unique matching net segments; leaf driver identities/counts and statuses. An unresolved link is preserved as `UNRESOLVED`, not converted into a pass.
- `lut_truth.tsv` — exact LUT1 cells, `I0`, `O`, and `INIT`. `2'h1` implements inversion of the single Boolean input.
- `preset_startpoints.tsv` — separate raw Vivado fan-in startpoints to preserve `/C` vs `/Q` discrepancies as observations, not proof.
- `check_timing.rpt` and `methodology.rpt` — still-visible external timing gaps. No artificial I/O delays or false paths.
- `verification.json` — Python validator result with actual unresolved edges and SHA-256 digests.

`PIN_LEVEL_EVIDENCE_REVIEW_REQUIRED` means **only that a well-formed audit was collected**. `physical_netlist_chain=CANDIDATE_ALL_EIGHT_LINKS_OBSERVED` (if it occurs) means the expected *reported pin-net connections and two inverter truth tables* were observed, subject to **manual verification against exported Vivado reports**. It is **not** a hardware reset or power-up signoff.

Stop and inspect the console if Vivado cannot locate an expected cell/pin; do not silently replace RTL, XDC, or the accepted DCP. If Vivado reports ambiguous net-segment aliases or multiple primitive drivers, preserve them and review before committing.

**Still NOT VERIFIED:** external I/O timing (five `TIMING-18` warnings), physical minimum pulse width, recovery/removal, contact bounce, oscillator startup, configuration bank electrical measurements, UART MTBF and board revision. No bitstream generated. Keep all `build/` evidence local and Git-ignored; do **not** commit before manual report review and green CI.
