# Phase 22 — Independent review: individual timing-path reports and board I/O inventory

**Decision:** ACCEPTABLE FOR A **READ-ONLY RESEARCH-DIAGNOSTIC DRAFT PR**, with the listed qualification gaps. **NOT** external-interface timing, asynchronous-reset electrical, physical-board, or bitstream signoff.

## Artifact identity and provenance

- Review input: `faultscope_phase22_review.zip` from `build/reproduction/phase22/path_binding_20261014T195315Z`.
- ZIP SHA-256: `5eb1c3dbb4ad299ad689c3778c51a5f62f5386267901ec101fe2dc02dded7509`.
- The archive has **17 of 17 expected root-level files** and no extra entries. Every one of the **16 evidence SHA-256 values** in `verification.json` independently matches its file bytes.
- `verification.json`: `issues=[]`; `paths_with_rendered_reports=10`; verdict `PATH_OBJECT_REPORTS_REVIEW_REQUIRED` (successful collection for **manual review**, not timing signoff).
- Preflight records the accepted Phase 17 routed DCP SHA-256 `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340` and Phase 15 hash `869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199`. The underlying DCP is **not** part of this ZIP and was not independently rehashed from the user's workstation.
- Vivado **2026.1**; part `xc7a100tcsg324-1`; design `checkpoint_post_route`; period `board_clk_100mhz = 10.000 ns`; `CFGBVS=VCCO`; `CONFIG_VOLTAGE=3.3`; board revision **PROVISIONAL**.
- User's console reports **49/49 Phase 22 regression tests passed**, preflight passed, and the read-only report runner accepted the evidence. Tests themselves do not imply physical-device qualification.

## Exact timing-report binding review

The Phase 22 Tcl calls `get_timing_paths` for each explicitly requested source/sink and delay type, then calls `report_timing -of_objects` on the **selected path object**. This bypasses the Phase 21 grouped-report `-from`/`-to` command-header anomaly. The Phase 21 grouped artifacts have not themselves been repaired.

**Independent report checks:** 10/10 requested sinks match the rendered report `Destination`; all 10 have the correct max/recovery or min/removal path type; all 10 rendered report files are authenticated by SHA-256.

| Requested path | Max / recovery | Min / removal | Qualification |
| --- | --- | --- | --- |
| External `rst_n` -> reset stage 0 `FDCE/CLR` | Path present, **slack unavailable** (`inf` in rendered report) | Path present, **slack unavailable** (`inf`) | Not externally constrained |
| External `rst_n` -> reset stage 1 `FDCE/CLR` | Same | Same | Not externally constrained |
| External `rst_n` -> reset stage 2 `FDCE/CLR` | Same | Same | Not externally constrained |
| Reset-release stage 2 to UART RX stage 0 `FDPE/PRE` | **+4.283 ns** | **+2.075 ns** | Positive **modeled internal** check only |
| Reset-release stage 2 to UART RX stage 1 `FDPE/PRE` | **+4.283 ns** | **+2.075 ns** | Positive **modeled internal** check only |

**Timing startpoint `C` versus requested `Q`:** In all four UART receiver reports, the displayed timing `Source` is `u_reset_sync/release_pipe_q_reg[2]/C`, although `get_timing_paths` was queried from its `/Q`. The detailed reported path traverses the launching `FDCE/C -> FDCE/Q` **clock-to-Q propagation arc**, then the inverter LUT and receiver `PRE` input. A clock pin can therefore appear as the **STA timing source**, while the **physical signal driver** is still the FF's `/Q` pin (established by Phase 20's direct mapped-pin trace). This is consistent with clock-launched recovery/removal reporting, not evidence that the reset net is electrically driven by `/C`. Nonetheless keep `source_query_mismatch=true` for these four report objects; the string labels are **not identical**, and the validator correctly does not hide this.

For the six external reset reports, Vivado prints `Slack: inf` with Path Group `(none)` and no externally qualified input delay. **Do not interpret `inf` as unlimited successful timing margin**, or replace it with 0 or a guessed external assumption.

## Implemented I/O inventory and board-reference cross-check

All mapped top-level ports report `LVCMOS33`:

| Implemented port | Package pin | Digilent Nexys4 DDR master-XDC function |
| --- | --- | --- |
| `clk` | E3 | `CLK100MHZ` |
| `rst_n` | C12 | `CPU_RESETN` |
| `uart_rx_i` | C4 | FPGA-side UART RX / board `UART_TXD_IN` |
| `uart_tx_o` | D4 | FPGA-side UART TX / board `UART_RXD_OUT` |
| `led_busy_o` | H17 | `LED[0]` |
| `led_alarm_o` | K15 | `LED[1]` |

The reported package pins agree with the **Digilent Nexys4DDR `Nexys4DDR_Master.xdc` source**, `https://github.com/Digilent/Nexys4DDR/blob/master/Resources/XDC/Nexys4DDR_Master.xdc` (reviewed against its clock, button, LED and USB-RS232 sections). This documents the **reference pin mapping**, not the revision or condition of any physical board; no board has been confirmed or programmed.

## Unresolved timing and qualification gaps

- `check_timing.rpt` reports **2 missing input delays** (`rst_n`, `uart_rx_i`) and **3 missing output delays** (`led_alarm_o`, `led_busy_o`, `uart_tx_o`). `methodology.rpt` independently reports the same **five `TIMING-18` warnings**. A master pin XDC alone cannot provide real external delay budgets.
- External asynchronous reset recovery/removal timing, minimum physical reset pulse width, reset-button bounce, oscillator startup, voltage behavior, and physical board revision remain **NOT VERIFIED**.
- The UART input is asynchronous to the board clock. Do **not** invent a synchronous `set_input_delay` to clear `TIMING-18`, or treat two FF stages as measured metastability MTBF.
- Output delays and loads require a defensible interface specification / connected receiver model. The two LED outputs are human-observable indicators, not automatically synchronous output-delay paths. Any timing-exception decision requires explicit justified scope and independent review.
- **No constraint changes** (`set_input_delay`, `set_output_delay`, `set_false_path`, `set_max_delay`, etc.), no new synthesis, place-and-route, bitstream, DCP overwrite or board test are authorized by this evidence.

## Acceptance boundary and next work

Approve Phase 22 only as an independently checked **timing-query integrity plus implemented-pin-inventory milestone**. Preserve the four documented `C`/`Q` timing-source-label differences and five `TIMING-18` warnings rather than declaring full signoff.

For a draft PR, stage only the **five Phase 22 pilot source/doc/test files** and this addendum. Run the 49 Phase 22 tests, `git diff --cached --check`, and review the six-file diff before submitting a **draft** PR. Do not include generated evidence files in Git, and wait for CI/scope review before merging.

Recommended next step: decide which additional *documented and reproducible* interface and reset qualification checks can be closed without a physical board; record a justified non-signoff limitation for all gaps requiring board access or external device timing models. Preserve the accepted Phase 17 routed checkpoint and current XDC unchanged.
