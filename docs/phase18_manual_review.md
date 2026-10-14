# Phase 18 — Manual review of asynchronous UART and reset boundaries

## Scope and decision

**Decision:** Accept Phase 18 as a **pre-silicon research diagnostic milestone** for a draft pull request, provided its exact source/test/docs scope is checked and GitHub CI passes. **Do not approve** external I/O timing closure, reset-source/power-up qualification, analog metastability/MTBF, physical PCB signoff, a bitstream, or hardware programming. The target remains **PROVISIONAL Nexys 4 DDR Rev. C** (`xc7a100tcsg324-1`).

The two independently exercised activities were (1) XSim simulation of the **unchanged** `rtl/fs_reset_sync.sv` and `rtl/fs_uart_rx.sv`, and (2) a read-only Vivado 2026.1 inspection of the **existing** Phase 17 fully routed DCP. No RTL or XDC change, fresh implementation, timing exception, or bitstream was involved.

* Phase 18 Vivado inspection folder: `build/reproduction/phase18/async_audit_20261014T173429Z/` (local, Git-ignored).
* Phase 17 baseline DCP recorded SHA-256: `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`; Phase 15 baseline DCP recorded SHA-256: `869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199`. The Phase 18 validator checked its on-disk DCP against saved Phase 17 evidence; the DCP binary itself was **not** included in the Phase 18 review ZIP and was **not independently rehashed from that ZIP**.
* Phase 17 configuration overlay recorded SHA-256: `9f2b07df823b3fc1b4bf1c28a0cf4bc774e3a38f4a85e16b04acf4ab38149223`; checkout mode was verified as `CRLF_CHECKOUT_EQUIVALENT_TO_ACCEPTED_LF`.
* Phase 18 validator verdict: `ASYNC_BOUNDARY_EVIDENCE_REVIEW_REQUIRED`, with `issues=[]`. All **five** hashes under `report_sha256` were independently recomputed from the user's review archive and matched.
* The user's Windows log shows **36/36 Phase 18 Python tests passed**; the uploaded XSim log confirms `PHASE18_XSIM_PASS` without reported assertion failures. The simulation stopped normally at 5550 ns. These are test results, **not exhaustive verification**.

## Routed boundary findings

| Evidence | Actual Vivado reported value | Meaning / limitation |
|---|---|---|
| `context.tsv` | Clock `board_clk_100mhz`, 10.000 ns, part `xc7a100tcsg324-1`, configuration `CFGBVS=VCCO`, `CONFIG_VOLTAGE=3.3` | Existing Phase 17 routed candidate; physical board still unconfirmed |
| `stages.tsv` | Three reset stages `FDCE` / `ASYNC_REG=1` in `SLICE_X2Y144`; two RX stages `FDPE` / `ASYNC_REG=1` in `SLICE_X64Y114` | Physical structure and placement preserved; not MTBF or external reset-source proof |
| `async_input.tsv` | `uart_rx_i` -> `uart_rx_i_IBUF_inst` (`IBUF`) -> `receiver/sync_q_reg[0]/D`, direct reported net | External input reaches first RX synchronizer register; input remains asynchronous |
| Vivado structural assertion | First RX stage has only `receiver/sync_q_reg[1]` as sequential fanout | No detected sequential bypass in the audited netlist; raw fanout enumeration was not exported separately |
| Reset 0 -> 1 | Setup +9.241 ns, hold +0.160 ns | Registered direct Q->D path with positive modeled internal slack |
| Reset 1 -> 2 | Setup +8.903 ns, hold +0.267 ns | Registered direct Q->D path with positive modeled internal slack |
| RX 0 -> 1 | Setup +8.846 ns, hold +0.271 ns | Registered direct Q->D path with positive modeled internal slack |
| `rx_interstage_max.rpt` | RX interstage routed max data-path delay 1.072 ns (0.456 ns cell + 0.616 ns route), zero logic levels | The interval is modelled synchronous path delay, **not an analog MTBF calculation** |
| `rx_interstage_min.rpt` | RX interstage routed min data-path delay 0.346 ns (0.141 ns cell + 0.205 ns route) | Not a physical metastability experiment |

**Open lineage observation:** `stages.tsv` names the async-clear net for all three reset stages as `u_reset_sync/release_pipe_q[2]_i_1_n_0`. The RX stages' async-preset net is reported as `core/round_count_q_reg[3]`, an unintuitive identifier. These may be optimizer-selected aliases. Phase 18's Tcl verifies a **connected** `CLR`/`PRE` pin and the expected primitive, but it **does not trace those nets' actual source drivers** back to `rst_n` or `rst_n_core`. Do not infer from the name alone that the reset is connected incorrectly, but **do not claim source-to-sink reset lineage verified**. A dedicated read-only source/driver/polarity and control-fanout trace should be an explicit next-phase task before reset signoff.

## Digital RTL simulation findings

The XSim testbench (`tests/rtl/phase18_async_tb.sv`) compiles the original RTL at a 10 ns clock with test-only UART `CLOCKS_PER_BIT=16`. It self-checks: active-low reset asserted before the first rising clock, asynchronous re-assertion between edges, release only on the third rising edge, rejection of a two-cycle start-like glitch, receipt of byte `A6`, reset interruption during a partial frame, no stale completed frame, and subsequent correct receipt of byte `35`. Simulation ended with `PHASE18_XSIM_PASS` at 5550 ns; all of this is **event-based digital behavior only**. The result is not a post-route, analog-metastability, jitter, pulse-width or mechanical-bounce test and does not verify the complete board UART protocol or cryptographic fault resistance.

## Remaining Vivado and physical signoff gaps

* `methodology.rpt`: **five** `TIMING-18` warnings, and no additional methodology checks. Missing input delays: `rst_n`, `uart_rx_i`. Missing output delays: `led_alarm_o`, `led_busy_o`, `uart_tx_o`.
* `check_timing.rpt`: `no_clock=0`, `unconstrained_internal_endpoints=0`, `multiple_clock=0`, `loops=0`; `no_input_delay=2`, `no_output_delay=3`; no broad false paths suppress these entries.
* `cdc.rpt` says `All paths are Safely Timed`, but Vivado's console states that input ports without delay constraints are skipped by `report_cdc`. This is **not** asynchronous UART/reset CDC or analog MTBF signoff.
* Oscillator startup/tolerance/jitter, reset release at clock startup, reset recovery/removal/minimum async pulse width, button bounce, PCB I/O voltages, FTDI UART timing and signal quality, and actual board identity remain **NOT VERIFIED**.
* Phase 17's prior default DRC clean result is not new Phase 18 electrical evidence. Phase 18 did not rerun full routing or generate a bitstream. The research UART link is unauthenticated/unencrypted; never use production keys in demos.

## PR acceptance gate

Only the seven Phase 18 pilot files **plus this manual review addendum** are eligible for staging: `scripts/phase18_async_audit.tcl`, `scripts/phase18_async_audit.ps1`, `scripts/phase18_async_report.py`, `scripts/phase18_xsim.ps1`, `tests/rtl/phase18_async_tb.sv`, `tests/test_phase18_async.py`, `docs/phase18_async_boundary.md`, and `docs/phase18_manual_review.md`. Confirm exact git status and staged diff; run Phase 18 regression tests again; open a **draft** PR; inspect CI and changed-file scope before merging. Keep all locally generated DCP/logs/reports in Git-ignored `build/` evidence. No RTL/XDC modifications, bitstream or physical signoff is authorized.
