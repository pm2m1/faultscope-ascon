# Phase 19 — Manual review of routed reset-source lineage diagnostics

## Disposition and scope

**ACCEPT as a pre-silicon, read-only diagnostic research milestone only**, contingent on exact source/test/documentation staging and green repository CI. **DO NOT claim reset-source-to-sink polarity verified, reset safety, recovery/removal closure, physical PCB signoff, or bitstream readiness.** Phase 19 collected useful evidence, but two UART receiver preset source observations are expressly **not resolved** by the current `all_fanin -startpoints_only` query. A separate pin-to-pin path and polarity probe is necessary before a polarity-verification claim.

- Design: `faultscope_uart_top`, provisional Digilent Nexys 4 DDR Rev. C, part `xc7a100tcsg324-1`.
- Actual Phase 19 read-only Vivado 2026.1 evidence: `build/reproduction/phase19/reset_lineage_20261014T175441Z/` (local; do not commit generated logs or DCP).
- Opened existing *routed* Phase 17 DCP. Prior Phase 17 checkpoint SHA-256 revalidated by the Windows preflight against the accepted evidence: `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`. Phase 15 archived checkpoint SHA-256: `869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199`. These binary files were **not included** in the user review ZIP; this manual review does not independently rehash either checkpoint.
- Configuration overlay provenance SHA-256: `9f2b07df823b3fc1b4bf1c28a0cf4bc774e3a38f4a85e16b04acf4ab38149223`, original LF with checkout CRLF equivalence verified by the runner.
- `verification.json` verdict `RESET_LINEAGE_EVIDENCE_REVIEW_REQUIRED`, `issues=[]`, `actual_signal_polarity=MANUAL_REVIEW_REQUIRED`, `unresolved_controls=[]` (meaning five control pins had reportable connections/startpoints, **not** that correctness was proven).
- Windows Python tests **34/34 passed**. No new synthesis, placement, routing, RTL/XDC changes, timing exceptions, checkpoint rewrite, bitstream or hardware programming.
- **All nine** report digests under `verification.json.report_sha256` were independently recomputed from the uploaded `faultscope_phase19_review.zip` contents and matched exactly: `check_timing.rpt`, `comb_cone.tsv`, `context.tsv`, `control_drivers.tsv`, `controls.tsv`, `methodology.rpt`, `release_fanout.tsv`, `reset_input.tsv`, `startpoints.tsv`.

## Exact reported connectivity and polarity-related evidence

| Audited area | Evidence from Vivado exports | Proven vs. unproven |
| --- | --- | --- |
| External reset source | `reset_input.tsv`: one `rst_n_IBUF_inst` (`IBUF`), input-net `rst_n`, output segments `rst_n_IBUF,u_reset_sync/rst_n_IBUF` | Unique physical input buffer identified in this routed netlist. |
| Reset release registers, stages 0–2 | All three `u_reset_sync/release_pipe_q_reg[0..2]` are `FDCE`, active-high `CLR`. `startpoints.tsv` returns top-level `rst_n` for each. All three controls report direct `u_reset_sync/release_pipe_q[2]_i_1/O`, a `LUT1` with `INIT=2'h1`; `comb_cone.tsv` includes `rst_n_IBUF_inst` and that LUT. | Source reachability and a compatible inversion primitive demonstrated. **Not** a full exported IBUF.O→LUT.I0→FDCE.CLR edge-by-edge proof. |
| RX synchronizer stages 0–1 | Both `receiver/sync_q_reg[0..1]` are `FDPE`, active-high `PRE`; their immediate leaf LUT output is `u_reset_sync/FSM_sequential_state_q[1]_i_2/O`, a `LUT1` with `INIT=2'h1`. | A candidate inverter is present at both receiver asynchronous presets. The LUT **input source** is not exported at pin level, so actual Q→I0→PRE polarity cannot be marked proven. |
| RX unexpected named net | `controls.tsv` lists `core/round_count_q_reg[3]`, other core/transmitter/receiver names, `u_reset_sync/release_pipe_q_reg[2]_0`, and `u_reset_sync_n_0` as *segments of one observed net*. | Names are aliases/segments, **not independent proof of source drivers**. No evidence the cryptography round counter actually drives PRE. |
| Ambiguous hierarchical output | `control_drivers.tsv` lists both the leaf `LUT1/O` and `u_reset_sync/release_pipe_q_reg[2]_0` under hierarchical `fs_reset_sync` for each PRE sink. | The export includes a **hierarchical boundary output pin** alongside a LUT leaf output. This must not be interpreted as a verified two-driver short, nor as proof of a single correct primitive driver, until boundary segments are isolated. |
| Discrepant fan-in root | For both RX PRE controls, `all_fanin -flat -startpoints_only` returns `u_reset_sync/release_pipe_q_reg[2]/C`, **not the expected `/Q`**. Correspondingly `source_observations.rx0.observed=false` and `.rx1.observed=false`. | **OPEN**, despite the successful schema/evidence verdict. A control clock pin appearing as a fan-in startpoint does not substantiate the expected reset-source polarity. |
| Reset release fanout | `release_fanout.tsv` reports 3,769 reachable endpoint *cells* from `u_reset_sync/release_pipe_q_reg[2]/Q`, including `receiver/sync_q_reg[0]` and `[1]`. | Broad cell-level reachability; cannot distinguish PRE from another pin or certify a direct functional reset relationship. It is **not** a count of 3,769 directly connected reset pins. |

For a `LUT1`, `INIT=2'h1` means output = NOT(input), since the output truth table is `1` for `I0=0` and `0` for `I0=1`. Therefore both exported LUTs are **consistent** with the intended polarity transformation: active-low `rst_n` becomes active-high `FDCE/CLR`, and low synchronized reset release drives active-high `FDPE/PRE`. But knowing the LUT truth table **without its actual source and sink pin edges** is not sufficient to prove the entire implemented signal equation. In particular, the observed `/C` vs `/Q` discrepancy remains unresolved.

## Diagnostic warnings and physical limitations

- `check_timing.rpt`: no-clock 0; unconstrained internal endpoints 0; multiple-clock 0; combinational loops 0; **no_input_delay 2** (`rst_n`, `uart_rx_i`) and **no_output_delay 3** (`led_alarm_o`, `led_busy_o`, `uart_tx_o`).
- `methodology.rpt`: **exactly five** `TIMING-18` missing-delay warnings on the same two inputs and three outputs. No arbitrary `set_input_delay`, `set_output_delay` or false-path exceptions were applied.
- Phase 19 is diagnostic; it does **not** retest the Phase 17 internal setup/hold closure or electrically qualify configuration-voltage pins.
- Physical board revision and wiring, minimum asynchronous reset pulse width, button bounce, clock-up/reset interplay, reset recovery/removal, UART analog metastability MTBF, external UART/LED timing, and hardware operation remain **NOT VERIFIED**. No physical board/bitstream was used.

## Required follow-up to close digital polarity lineage

A separate read-only Vivado pin-edge probe against the same authenticated DCP should export, for **each of the five sinks**:

1. The exact connected leaf primitive pin object at the sink (`FDCE/CLR` or `FDPE/PRE`), and the shared net segment(s) with its actual leaf `LUT1/O` driver, excluding hierarchy-only apparent driver pins.
2. The actual `LUT1/I0` pin, its net segments, and the unique leaf-source output pin. For reset CLR: establish `rst_n` → `IBUF/I` → `IBUF/O` → `LUT1/I0` → `LUT1/O` → `FDCE/CLR`; for receiver PRE: establish `u_reset_sync/release_pipe_q_reg[2]/Q` → `LUT1/I0` → `LUT1/O` → `FDPE/PRE`.
3. Derive the two logic equations from verified primitive `REF_NAME`, `INIT` and pin connections. If any edge is missing, multiple leaf drivers remain, or a different primitive/route is observed, retain an **OPEN** status and investigate. Do not change RTL/XDC to force the expected outcome without evidence.
4. Explain why `all_fanin -startpoints_only` reported `/C` while `all_fanout` from `/Q` reached both RX endpoint cells, separating query semantics, hierarchy boundaries and actual primitive connectivity.

Only after those checks may we assess **digital netlist source-to-control polarity**. It still will not establish analog reset release safety, hardware MTBF or board signoff.

## Phase 19 PR gate

**Appropriate for a draft PR as a _read-only reset-lineage evidence collector_, not as completed reset verification.** Stage only the five pilot source/test/doc files plus this addendum (six total): `scripts/phase19_reset_lineage.tcl`, `scripts/phase19_reset_lineage.ps1`, `scripts/phase19_reset_lineage_report.py`, `tests/test_phase19_reset_lineage.py`, `docs/phase19_reset_lineage.md`, and `docs/phase19_manual_review.md`. Recheck the 34 regression tests, the staged diff and GitHub CI before merging. Store reports in ignored `build/`, never in Git. Explicitly state RX `/C` vs `/Q` mismatch and unresolved polarity in the PR description.
