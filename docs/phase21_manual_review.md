# Phase 21 — Independent review of routed reset timing evidence

Status: **ACCEPTABLE AS A READ-ONLY TIMING-DIAGNOSTIC RESEARCH MILESTONE; NOT RESET, I/O, OR BOARD SIGNOFF.**

## Identity and provenance

- Evidence bundle: `faultscope_phase21_review.zip`, source audit `build/reproduction/phase21/reset_timing_20261014T192759Z`.
- Vivado v2026.1, `xc7a100tcsg324-1`, routed `checkpoint_post_route`, `board_clk_100mhz` 10.000 ns, `CFGBVS=VCCO`, `CONFIG_VOLTAGE=3.3`.
- Accepted Phase 17 DCP SHA-256: `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340` (recorded by the Phase 21 provenance preflight).
- Independent ZIP review: **11/11 expected entries present, no unexpected entries; 10/10 report SHA-256 values match the attached `verification.json`**. ZIP SHA-256: `4b58f9dc359232472238cebb2818e36d0404fc2354476c407390f6891cd26787`.
- The final Phase 21 validation result has `issues=[]` and `RESET_TIMING_EVIDENCE_REVIEW_REQUIRED`. That is **successful evidence collection**, not a timing signoff verdict.
- The earlier Phase 21 result was correctly rejected because Vivado returned blank `SLACK` for paths from the external asynchronous reset. The correction preserves that as `PATH_REPORTED_SLACK_UNAVAILABLE` instead of inventing a number.

## Per-endpoint timing queries: 10/10 returned a path

| Source and destination | Maximum (recovery) | Minimum (removal) | Evidence status |
| --- | ---: | ---: | --- |
| `rst_n` → `u_reset_sync/release_pipe_q_reg[0]/CLR` | Slack unavailable | Slack unavailable | Path reported; no external timing qualification |
| `rst_n` → `u_reset_sync/release_pipe_q_reg[1]/CLR` | Slack unavailable | Slack unavailable | Path reported; no external timing qualification |
| `rst_n` → `u_reset_sync/release_pipe_q_reg[2]/CLR` | Slack unavailable | Slack unavailable | Path reported; no external timing qualification |
| `u_reset_sync/release_pipe_q_reg[2]/Q` → `receiver/sync_q_reg[0]/PRE` | +4.283 ns | +2.075 ns | Modeled recovery/removal path reported |
| `u_reset_sync/release_pipe_q_reg[2]/Q` → `receiver/sync_q_reg[1]/PRE` | +4.283 ns | +2.075 ns | Modeled recovery/removal path reported |

The 10 individual `get_timing_paths` queries cover 5 endpoints × 2 delay types. There are 4 numeric-slack observations and 6 path observations without numeric slack. Never interpret an absent slack field or the `inf` displayed for unconstrained external reset paths in `report_timing` as a positive timing margin.

## Additional Vivado timing details

- `timing_summary.rpt` reports whole-design routed **WNS +1.471 ns**, **WHS +0.022 ns** and zero failing endpoints in the represented modeled setup/hold groups.
- The clocked `**async_default**` group reports worst modeled **recovery +2.097 ns** and **removal +1.208 ns**, with zero failing endpoints out of **3,769 reported endpoints** in each max/min summary. This is a **modeled internal reset-release** observation, not external reset qualification.
- `clock_pulse_width.rpt` reports `board_clk_100mhz` period 10.000 ns, 5.000 ns high and low pulses, required high/low minimum of 0.500 ns and **+4.500 ns** clock-pulse-width slack. `Min Period` for `BUFG/I` requires 2.155 ns against a modeled 10.000 ns period (+7.845 ns). These checks **do not** measure the physical `rst_n` pulse or button bounce.
- `check_timing.rpt`: **2 inputs without input delay** (`rst_n`, `uart_rx_i`), **3 outputs without output delay** (`led_alarm_o`, `led_busy_o`, `uart_tx_o`); no unclocked register pins and no unconstrained *internal maximum-delay endpoints* were identified by that check.
- `methodology.rpt` contains **five `TIMING-18` missing-input/output-delay warnings**, one for each of the five ports above.

## Grouped timing-report command header caveat

The four supplemental grouped `report_timing` files contain **inconsistent command headers**. For example, the `release_to_preset_*.rpt` header shows a `-from` and `-to` both referencing `receiver/sync_q_reg[1]/PRE`, while the report body lists the clocked release register as the source and both receiver preset pins as destinations. The `reset_from_port_*.rpt` header similarly displays a destination filter inconsistent with its three `FDCE/CLR` report-body destinations.

**Do not represent these four grouped report command headers as proven correct, specifically filtered queries.** Their report-body timing paths agree with the design and independently queried path categories, but the inconsistency needs a future bounded tooling review. The milestone's ten per-endpoint `get_timing_paths` observations, independent hash checks, `check_timing`, clock pulse-width report and top-level timing summary remain the primary evidence. Do not derive full source-to-destination completeness from the grouped files alone.

## Not verified / restrictions

- External `rst_n` release recovery/removal relative to the actual board clock, minimum reset pulse duration, reset-button bounce, oscillator startup and reset release during startup.
- External UART timing assumptions and LED / UART TX output loads and delays; analog MTBF, physical voltage or board revision, and board-electrical signoff.
- No bitstream generated, no board programmed, and no new synthesis, placement, routing, source change or timing exception is supported or implied by this diagnostic review.
- Do **not** invent `set_input_delay`, `set_output_delay`, `set_false_path`, board oscillator behavior, jitter or electrical tolerances just to silence the warnings. Document actual interface timing assumptions and board facts before any constraint changes.

## Recommended acceptance and follow-up

Accept Phase 21 **only as a reproducible research evidence-collection milestone**, with both the external-path incompleteness and the grouped command-header discrepancy explicitly open. Stage only the five original Phase 21 pilot files and this addendum, rerun Phase 21's corrected regression tests and provenance preflight, then submit a draft pull request for CI and scope review before merge.

Before any claim of comprehensive asynchronous reset signoff, use a separate bounded investigation to reproduce and correct the grouped `report_timing` selection/header behavior, establish defensible reset and external I/O constraints from physical sources, and evaluate startup and recovery/removal assumptions. Preserve the accepted Phase 17 DCP unmodified.
