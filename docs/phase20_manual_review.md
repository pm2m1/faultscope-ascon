# Phase 20 — Manual review of exact routed reset-pin connectivity

## Decision and strict scope

**Decision: ACCEPT as a pre-silicon, read-only routed-netlist *diagnostic research milestone*, eligible for a draft PR after review of its exact changed-file scope and CI.** The evidence establishes all eight specifically audited Vivado-reported pin/net-segment connections and both single-input inverter configurations. It does **not** establish physical/electrical board reset signoff, recovery/removal, minimum pulse widths, clock startup, bounce, MTBF, complete reset-consumer coverage, or external I/O timing.

Target is the **PROVISIONAL Nexys 4 DDR Rev. C** `xc7a100tcsg324-1`. Phase 20 reopened the already-routed Phase 17 checkpoint read-only in Vivado 2026.1, with no RTL/XDC edits, resynthesis, placement, routing, timing exceptions, checkpoint writes, bitstream generation, or board programming. User Windows execution: `build/reproduction/phase20/pin_trace_20261014T182329Z/` (locally generated, Git-ignored).

The user console confirms **30/30 isolated Phase 20 pytest tests passed**, preflight verdict `PHASE17_PROVENANCE_VERIFIED`, and Vivado/validator verdict `PIN_LEVEL_EVIDENCE_REVIEW_REQUIRED`, `issues=[]`. The validator's separate `physical_netlist_chain` field reads `CANDIDATE_ALL_EIGHT_LINKS_OBSERVED` with `unresolved_edges=[]`; the verdict itself is only an evidence-collection outcome.

Phase 17 post-route DCP accepted SHA-256, reported by provenance verification: `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`. Phase 15 baseline DCP SHA-256: `869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199`. **The DCP binary was not in the Phase 20 review archive and was not independently rehashed from it**; on-disk baseline verification ran on the user's machine.

## Independently inspected pin-to-pin evidence

The uploaded ZIP contained seven files, and the six `report_sha256` values in `verification.json` were independently recomputed byte-for-byte and **all six matched**. The `context.tsv` records Phase 20 read-only scope, Vivado 2026.1, `checkpoint_post_route`, `xc7a100tcsg324-1`, `board_clk_100mhz` at 10.000 ns, `CFGBVS=VCCO`, and `CONFIG_VOLTAGE=3.3`.

| Edge | Exact link observed in `pin_edges.tsv` | Status |
|---|---|---|
| `reset_port_to_ibuf` | `rst_n` → `rst_n_IBUF_inst/I` | `PORT_TO_IBUF_DIRECT` (input port; zero leaf-output drivers) |
| `reset_ibuf_to_lut` | `rst_n_IBUF_inst/O` → `u_reset_sync/release_pipe_q[2]_i_1/I0` | Shared segments, one expected `IBUF/O` leaf driver |
| `reset_lut_to_clr0` | reset `LUT1/O` → `release_pipe_q_reg[0]/CLR` | Shared segment, one expected `LUT1/O` leaf driver |
| `reset_lut_to_clr1` | reset `LUT1/O` → `release_pipe_q_reg[1]/CLR` | Shared segment, one expected `LUT1/O` leaf driver |
| `reset_lut_to_clr2` | reset `LUT1/O` → `release_pipe_q_reg[2]/CLR` | Shared segment, one expected `LUT1/O` leaf driver |
| `release_q_to_lut` | `release_pipe_q_reg[2]/Q` → `u_reset_sync/FSM_sequential_state_q[1]_i_2/I0` | Shared segment, one expected `FDCE/Q` leaf driver |
| `release_lut_to_pre0` | release `LUT1/O` → `receiver/sync_q_reg[0]/PRE` | Shared segment, one expected `LUT1/O` leaf driver |
| `release_lut_to_pre1` | release `LUT1/O` → `receiver/sync_q_reg[1]/PRE` | Shared segment, one expected `LUT1/O` leaf driver |

Both LUTs have **`REF_NAME=LUT1`, `INIT=2'h1`**; the truth table is `I0=0 → O=1`, `I0=1 → O=0`. Thus the audited mapped Boolean paths invert the active-low external reset into active-high `FDCE/CLR`, and invert the stage-2 released-reset `Q` into active-high `FDPE/PRE`. This is a **netlist-level structural/Boolean observation**, not an electrical-polarity or temporal signoff.

`pin_edges.tsv` reports the RX `PRE` net with several hierarchical segment labels, including `core/round_count_q_reg[3]`, `receiver/valid_o_reg_0`, `u_reset_sync_n_0`. The identical shared segment set and expected `u_reset_sync/FSM_sequential_state_q[1]_i_2/O|LUT1` leaf driver identify those names as *aliases on the audited net*, not independent additional primitive output drivers. Importantly, the Tcl intentionally counts only selected **recognized leaf primitive output classes**, excluding hierarchical module boundary pins; the evidence is not a universal electrical multi-driver proof.

**Preserved discrepancy:** `preset_startpoints.tsv` still reports `u_reset_sync/release_pipe_q_reg[2]/C` (not `/Q`) for both RX `PRE` controls under `all_fanin -flat -startpoints_only`. The direct `/Q → LUT1/I0` and `LUT1/O → PRE` connections were independently exported and verified, so the specific intended chain is no longer missing in the pin-edge trace. The precise cause of the `/C` response in this distinct fan-in query is **not established**. Do not silently re-label it as `/Q` or claim to have resolved the tool's query semantics.

## Unchanged timing/methodology gaps

`check_timing.rpt` reports `no_clock=0`, `unconstrained_internal_endpoints=0`, `multiple_clock=0`, `loops=0`; **two missing input delays** (`rst_n`, `uart_rx_i`) and **three missing output delays** (`led_alarm_o`, `led_busy_o`, `uart_tx_o`). It finds zero false-path-exempt input/output ports in these categories. `methodology.rpt` reports **exactly five `TIMING-18` warnings** for the same ports, with no additional methodology finding.

The Phase 17 prior routed internal setup and hold measurements were +1.471 ns / +0.022 ns; Phase 20 **did not rerun implementation or collect a new whole-design timing summary**, and must not claim new timing closure. External UART/reset timing, reset recovery/removal/minimum async pulse width, mechanical button bounce, clock startup, physical PCB revision/voltage measurement, and analog MTBF remain **NOT VERIFIED**. No bitstream or board execution.

## Exact provenance of uploaded review ZIP

SHA-256 values independently matched against the archived `verification.json`:

| Evidence file | SHA-256 |
|---|---|
| `context.tsv` | `1f54e66778efa9e22ef51cb31079460138ec10b24e14c1046dca3db73bcaa799` |
| `pin_edges.tsv` | `881aecf5fe53ecc70ed7b39ac2ad491e33e10e160c12418e05d1f657f65054cd` |
| `lut_truth.tsv` | `cce9233141eacb655721ded968ccb3ac74099015fa3ffbc0fdcd542705138ab3` |
| `preset_startpoints.tsv` | `e44c5059db83910f5033df918c2eeef36715a9ce8ec523cb92ef8403aa9e26b5` |
| `check_timing.rpt` | `9b5ddbd2a4a776f64ef8221659017ea7d94e295cbfa56266d03bdfcfe5f958c4` |
| `methodology.rpt` | `dc0cbcaa0014136d06738f5537b162ed03c1f31c6d4f005920e9906aa4deb41b` |

## PR and follow-up gate

The only eligible Phase 20 files are the **five pilot files plus this manual-review document**: `scripts/phase20_exact_pin_trace.tcl`, `scripts/phase20_exact_pin_trace.ps1`, `scripts/phase20_exact_pin_report.py`, `tests/test_phase20_exact_pin.py`, `docs/phase20_exact_pin_trace.md`, and `docs/phase20_manual_review.md`. Review the exact staged diff, rerun the 30 Phase 20 tests, and create a **draft** PR; check CI, changed files, and mergeability before merging. Never stage locally generated report files, logs, DCPs, or any bitstream. No RTL or XDC modification is part of Phase 20.

Further FPGA verification should separately address a defensible external timing model (with actual interface specifications, not fabricated delay numbers), reset release/recovery corner cases, any unmapped downstream reset consumers, and eventual physical-board testing when the board and revision are confirmed. The existing five `TIMING-18` warnings must not be suppressed by invented delays or broad false paths merely for a clean report.
