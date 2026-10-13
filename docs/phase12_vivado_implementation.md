# Phase 12 - Windows Vivado implementation

Native Vivado synthesis, optimization, placement, and routing were executed for all four architectures. The authoritative evidence is `build/reproduction/phase12/clock_context_10ns/`; the first runs at the Phase 12 root are preliminary because they omitted the OOC clock-source context. No board was connected or programmed.

## Environment and provenance

- Windows 11 Home Single Language, version 10.0.26200, 25H2; PowerShell on the Windows laptop.
- Vivado 2026.1, SW build 6511674, `C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat`. Vivado recognized the target and acquired synthesis/implementation licenses; the probe log records the active BASIC license.
- Target: `xc7a100tcsg324-1`. All runs use 10.0 ns, OOC synthesis, `flatten_hierarchy=rebuilt`, default opt/place/route directives, and four tool threads.
- Git 2.55.0.windows.5; system Python 3.12.1; regression Python 3.12.4 from Anaconda; pytest 7.4.4; uv 0.11.3.
- Existing private repository: `C:\Projects\faultscope-ascon`, initially clean, origin `https://github.com/pm2m1/faultscope-ascon.git`.
- Source commit: `170136f0c486527ba511bfc797734eeecbe4685e`. RTL was not modified. Exact source snapshots, SHA-256 digests, run settings, timestamps, logs, and exit codes are retained.

During the initial run, the raw-byte evidence verifier reported FAIL for RTL because Git checked out CRLF on Windows. The final portable verifier now reports both raw and pinned hashes and explicitly records CRLF-to-LF comparison, without rewriting any source or pin. `source_line_ending_audit.json` proves that converting CRLF to LF matches both every historical Phase 5 source digest and the exact committed Git blobs for all seven pinned modules. All three campaign CSV hashes pass. Historical reports, CSVs, manifests, and RTL bytes were left unchanged. `final_evidence_validation.json` records verification at implementation completion. The final review preserves those snapshots; the report validator now has a separately recorded rejection fix, while all RTL inputs remain byte-for-byte unchanged.

## Implementation results

LUT counts below are Vivado occupied Slice LUTs, including LUT combining; FF counts are the report's Register as Flip Flop row. These are different measurements from Yosys technology-mapped primitive counts.

| Architecture | Synthesis LUT / FF | Placement LUT / FF | Route LUT / FF | Carry4 | BRAM18 / BRAM36 | DSP | Internal WNS / WHS ns | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| baseline | 1975 / 1633 | 1962 / 1633 | 1962 / 1633 | 0 | 0 / 0 | 0 | +3.060 / +0.117 | MET |
| instrumented | 2307 / 1669 | 2295 / 1669 | 2295 / 1669 | 0 | 0 / 0 | 0 | +1.688 / +0.048 | MET |
| protected | 3297 / 2666 | 3160 / 2666 | 3160 / 2666 | 54 | 0 / 0 | 0 | +1.210 / +0.058 | MET |
| uart_protected | 3552 / 3769 | 3536 / 3769 | 3536 / 3769 | 71 | 0 / 0 | 0 | +2.239 / +0.028 | MET |

Post-route protected-core overhead is calculated as `100 * (protected / reference - 1)`:

- Against baseline: LUT **61.06%**, FF **63.26%**.
- Against instrumented: LUT **37.69%**, FF **59.74%**.
- UART system relative to protected core: +376 LUTs (11.90%), +1103 FFs (41.37%).

Every final implementation has an actual routed checkpoint and reports. Acceptance checks require nonempty constrained setup and hold paths, matching full timing-summary slacks, zero failing setup/hold/pulse-width endpoints for MET, zero internal missing/multiple/constant clocks or unconstrained internal endpoints, no combinational loops, all routable nets fully routed, and zero routing-error nets. No critical/error DRC issues are accepted. Configuration-voltage warnings remain and are documented below.

## Timing context and critical paths

The XDC creates `core_clk` at 10.0 ns before synthesis and applies `HD.CLK_SRC=BUFGCTRL_X0Y0`. Vivado confirms that the site exists in this exact part. This is an explicit OOC assumption that a global clock buffer outside the module supplies the clock from that site; it is not a physically instantiated board oscillator/IBUF/BUFG network or a pin assignment. Clock distribution is estimated in this context. A later full top-level board implementation must verify its actual clock network and rerun timing.

AMD documents the purpose and ordering of this context property in [UG905 Context Constraints](https://docs.amd.com/r/2022.1-English/ug905-vivado-hierarchical-design/Context-Constraints). The initial pilot lacked the property and emitted Timing 38-242; all four final runs were repeated with the property, and that warning is absent. Preliminary slacks must not be substituted for final results.

| Architecture | Actual worst setup startpoint | Endpoint | Data delay / logic levels | Fully routed / routable nets |
|---|---|---|---|---:|
| baseline | `FSM_sequential_fsm_q_reg[2]_rep/C` | `ascon_state_q_reg[213]/CE` | 6.653ns  (logic 1.255ns (18.865%)  route 5.398ns (81.135%)) / 3  (LUT3=1 LUT5=1 LUT6=1) | 2527 / 2527 |
| instrumented | `FSM_sequential_fsm_q_reg[2]/C` | `u_permutation/state_q_reg[135]/CE` | 8.030ns  (logic 0.718ns (8.942%)  route 7.312ns (91.058%)) / 1  (LUT5=1) | 2967 / 2967 |
| protected | `u_permutation/fault_detected_o_reg/C` | `tag_q_reg[21]/D` | 8.651ns  (logic 0.642ns (7.421%)  route 8.009ns (92.579%)) / 1  (LUT5=1) | 4215 / 4215 |
| uart_protected | `core/u_permutation/u_round_engine/state_o_reg[175]/C` | `core/u_permutation/state_o_reg[242]/D` | 7.665ns  (logic 2.399ns (31.299%)  route 5.266ns (68.701%)) / 13  (CARRY4=10 LUT3=1 LUT5=1 LUT6=1) | 5727 / 5727 |

The full paths, cell locations, logic-versus-route delays, fanout, clock skew, uncertainty, and endpoints are in each `internal_setup_paths.rpt` and `internal_hold_paths.rpt`. The protected-core and system paths must be interpreted using the final reported netlist; control/fault-status fanout can dominate delay even when the Ascon round itself is not the worst path. All four designs meet the requested internal setup/hold/pulse-width checks, so no clock-period sweep, RTL retiming, false-path exclusion, or constraint relaxation was used. No achieved Fmax is claimed.

## UART, reset, CDC, and external timing

The synthesized UART top has exactly six scalar ports: `clk`, `rst_n`, `uart_rx_i`, `uart_tx_o`, `led_busy_o`, `led_alarm_o`. It includes the existing RX/TX modules, command/CRC controller, staging/configuration registers, temporal Ascon core, valid/fault logic, and result response state machine.

`faultscope_uart_top`, `fs_uart_rx`, and `fs_uart_tx` default to `CLOCKS_PER_BIT=868`; the wrapper passes this parameter to both UART blocks. At 100 MHz this produces approximately 115207.37 baud, +0.00640% relative to 115200. Final synthesis uses the original default parameter, with no simulation-speed override.

- RX uses `sync_q[0]` followed by `sync_q[1]`; the state machine observes only the second stage. The two-flop synchronizer has no `ASYNC_REG` attribute. Its metastability MTBF and placement suitability have not been established.
- All logic operates on the single `clk`. UART baud counting creates clock enables, not another clock domain.
- `rst_n` is directly used as an asynchronous active-low reset throughout the hierarchy. Deassertion is not synchronized. Reset recovery/removal and metastability-safe release are NOT VERIFIED.
- `report_cdc` explicitly skips external ports without input delays. A report with no crossings does not prove the asynchronous UART input or reset safe.
- UART check_timing records two ports without input delays (`rst_n`, `uart_rx_i`) and three without output delays. The wide cores likewise have intentionally unconstrained external data/control interfaces. None of these interfaces is included in the internal timing pass.
- OOC routing emits Route 35-198 because external ports lack HD.PARTPIN_LOCS. Their partial routes/timing are not accurate or exported. Internal routable net counts and errors are checked independently. No artificial port location was added to suppress this warning.
- DRC CFGBVS-1 warns that CFGBVS/CONFIG_VOLTAGE are unspecified. These require verified board voltage information in a board implementation; no voltage or pin map was invented.

No functional RTL change is needed for this OOC feasibility experiment. Before deployment, reset release synchronization and RX synchronizer attributes/constraints should be addressed with focused regression tests before changing RTL. CRC-8 provides framing-error detection only; UART is unauthenticated and unencrypted. Use synthetic test keys exclusively.

## Tcl audit and changes

The original Phase 10E pilot already loaded the correct baseline, instrumented, and protected dependencies and invoked synth/opt/place/route for the exact target part. Its real gaps were applying the clock only after synthesis, missing OOC clock-source context, and reporting MET from setup slack alone.

- `scripts/phase10e_vivado_ooc.tcl`: creates an in-memory project, reads a clock/context XDC before synthesis, checks the synthesized clock, reports min/max and unconstrained timing, adds DRC, and gates its verdict on hold slack, internal clock/endpoint coverage, loops, routing completeness, critical DRC, and OOC clock-source context. Historical output locations are unchanged and were not used for this experiment.
- `scripts/phase12_vivado_ooc.tcl`: independent four-architecture flow with exact source sets, scalar UART port assertion, clock-context checks, three checkpoints/utilization/timing stages, post-route DRC/route/check_timing/CDC/clock reports, and setup/hold path metrics. A completion marker means reporting finished, not timing passed.
- `scripts/phase12_vivado.ps1`: Windows entry point; discovers/accepts the Vivado executable, guards output paths and existing runs/provenance, snapshots sources and settings, records exit codes and console logs, keeps tool temporary files in run directories, and invokes strict validation. Failed or incomplete evidence and failed internal timing return nonzero.
- `scripts/phase12_report.py`: standard-library parser; creates JSON, comparison CSV, Markdown, and SHA-256 inventory; rejects missing/ambiguous resource, route, clock, setup/hold/pulse-width, or DRC evidence. Missing values are NOT VERIFIED.
- `tests/test_phase12_vivado.py`: parser acceptance/failure tests, including negative setup/hold/pulse-width, missing clock source, report disagreement, missing evidence, cross-version overhead rejection, and actual dotted route formatting.
- `tests/test_phase10e_feasibility.py`: writes its synthetic hash fixture as explicit UTF-8 bytes to prevent Windows newline translation. Production digest checks and historical evidence are unchanged.

## Reproduce

From the repository root in PowerShell:

```powershell
.\scripts\phase12_vivado.ps1 -Vivado 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat' -Python 'C:\Users\mishr\anaconda3\python.exe'
```

By default this creates a fresh UTC-stamped directory below `build/reproduction/phase12/` and runs all four designs at 10 ns. Supply `-OutputRoot build/reproduction/phase12/my_new_run` for a named new run. Existing runs/provenance are never overwritten. `-Periods 20,15,10` enables independent period runs if a future timing investigation needs them; no frequency extrapolation is performed.

Regenerate and validate the authoritative comparison:

```powershell
python scripts\phase12_report.py build\reproduction\phase12\clock_context_10ns --require-verified --expected-periods 10 --validate-only
& C:\Users\mishr\anaconda3\python.exe -m pytest tests\test_phase12_vivado.py tests\test_phase10e_feasibility.py -q
```

## Verification and limitations

- Initial supported regression subset (before the final portability review): 57 passed, 4 skipped. It includes all 1,089 official KAT vectors, UART framing/CRC checks, static FPGA/formal contracts, Phase 10E checks, and 13 Phase 12 parser tests. The official reference was restored at pinned commit `446347f21b209f3921c65ece70027c366cbe1693` in ignored `references/ascon-c/`.
- Initial broader regression run (resolved in the final review below): 62 passed, 5 skipped, 3 failures from original checkout CRLF/raw-digest mismatches. One initial collection attempt failed at the Unix-only `resource` import in `test_phase10a_rtl_contract.py`. Failure logs remain in Phase 12 evidence.
- Verilator, Yosys, and sv2v were not installed automatically. New RTL simulation, live SAT, bounded formal, and Yosys mapping are NOT VERIFIED on this laptop. Existing GitHub workflows cover those checks; connector queries returned no proof of a successful current CI run, and no CI pass is claimed for these uncommitted changes.
- No physical FPGA functionality, programming, bitstream, board XDC, external I/O closure, power measurement, physical fault experiment, production security, or certification is claimed.

## Before a Nexys hardware demonstration

1. Review this diff and run the full existing Linux CI/RTL/formal suite. Preserve the byte-pinned audits; the explicit checkout line-ending policy now supports CRLF while retaining raw digests and all historical pins.
2. Obtain and verify the exact board revision, schematic, oscillator frequency, reset circuit/polarity, UART voltage/routing, and official pin constraints.
3. Add/test asynchronous-assert, synchronized-deassert reset handling and RX synchronizer implementation attributes/constraints. Review CDC with explicitly justified external-interface assumptions.
4. Create a real board top-level clock/I/O implementation with verified pins, IOSTANDARD, configuration-bank voltage, appropriate external constraints, and no indiscriminate timing exceptions. Rerun synthesis, implementation, timing, CDC, and bitstream DRC against the actual clock buffer network.
5. Generate/program a bitstream only after those checks; then test reset, PING/CRC errors, clean known-answer encryption, invalid-result masking, and synthetic fault detection using synthetic keys. Physical fault injection requires a separate justified setup and evidence.

## Deliverables and review

The root `summary.json` and `comparison.csv` point to the authoritative clock-context run. `REPORT.md` is this detailed report. Logs and checkpoints remain below each architecture directory; `artifact_sha256.json` inventories evidence. `final_diff.patch` includes all tracked and new reviewable source/doc/test changes; nothing was staged, committed, or pushed.

## Final Windows portability and evidence review

No Vivado implementation was repeated in this final review. RTL, original campaign CSVs, Phase 5 evidence and pins, GitHub workflows, and every file in the authoritative `clock_context_10ns/` evidence set remain byte-for-byte unchanged. The prior report, summary, inventory, and diff were archived under `final_verification/before_*` before updating derived review documents. The original artifact inventory remains preserved; `final_verification/review_artifact_sha256.json` inventories the current review state.

### Exact failure causes and minimal fixes

- `test_compare_to_historical_is_version_aware_and_non_destructive` failed because Phase 10B hashed CRLF checkout bytes and compared them directly with LF historical pins.
- `test_invalid_cell_counts_and_different_rtl_rejected` encountered the same source-hash exception before its intended synthesis-flow mismatch check, so the expected error-message assertion also failed.
- `test_real_report_provenance_from_committed_rtl` passed raw CRLF hashes from `run_phase5.source_hashes()` into the strict Phase 10D dictionary comparison against LF pins.
- `test_phase10a_rtl_contract.py` imported POSIX-only `resource` during collection. After that import is addressed, its unconditional `preexec_fn` is also unsupported by Windows subprocesses, and native executable names require the `.exe` suffix.

`experiments/source_provenance.py` now checks raw bytes first and permits only an explicitly recorded CRLF-to-LF comparison with an unchanged historical pin. It returns raw, LF, and pinned SHA-256 values plus `match_mode`. It does not trim whitespace, change encoding, discard BOMs/comments, alter lone CRs, or rewrite source files. Mutation-negative tests cover those exclusions. `run_phase5.source_hashes()` remains a raw-byte hash function; raw source fields in future experiment reports remain raw. Phase 10B distinguishes raw manifest equality from the permitted source comparison instead of equating the two. Phase 10D requires actual source bytes and an exact raw-file/hash match before permitting checkout conversion; hash-dictionary-only calls remain strict. Phase 10E and the evidence CLI expose the same explicit source policy. Campaign and artifact digest checks remain raw and strict.

The Phase 12 report validator also had a false-pass edge case: a late UART scalar-port mismatch was logged after MET was assigned, leaving the timing verdict unchanged. A focused negative test reproduced it before the one-line exception-path fix; every validation error now clears the timing verdict to NOT VERIFIED. The actual six-port design passes before and after this analysis-only fix, and all measured slacks/counts are unchanged. The original run-time parser snapshot remains preserved.

Core-dump suppression in the contract test now uses `resource` and `preexec_fn` only on POSIX. Windows uses the native executable suffix. Only the two contract simulations skip on Windows when Verilator is absent. Linux/POSIX still asserts that Verilator is installed, and a focused regression checks that gate. No GitHub workflow or mandatory Linux RTL check was weakened.

### Independent saved-report audit

`final_verification/post_route_audit.json` cross-checks each timing/utilization report's Routed/Fully Routed header, setup and hold path slacks, the full timing summary, the published report, routing counts, internal coverage checks, scalar ports, and the saved clock XDC. It performs no report regeneration or Vivado execution.

| Architecture | Post-route WNS ns | Post-route WHS ns | Fully routed / routable nets | Unconstrained internal endpoints | External inputs / outputs without delay |
|---|---:|---:|---:|---:|---:|
| baseline | +3.060 | +0.117 | 2527 / 2527 | 0 | 524 / 258 |
| instrumented | +1.688 | +0.048 | 2967 / 2967 | 0 | 541 / 259 |
| protected | +1.210 | +0.058 | 4215 / 4215 | 0 | 541 / 261 |
| uart_protected | +2.239 | +0.028 | 5727 / 5727 | 0 | 2 / 3 |

All four have zero routing-error nets. UART's unconstrained external inputs are `rst_n`, `uart_rx_i`; its unconstrained outputs are `uart_tx_o`, `led_busy_o`, `led_alarm_o`. The audit records all wide-core external port names as well. The clock remains 10 ns with the OOC assumption of an external BUFG at `BUFGCTRL_X0Y0`. That is a clock-context estimate, not a physically implemented board clock network. Post-placement UART hold violations were repaired by routing; the final +0.028 ns WHS is taken from post-route reports, not the placement report. Its modest margin requires revalidation in the eventual board context.

### UART review and separate proposed follow-up

Source inspection verifies the RX pipeline assignment `sync_q <= {sync_q[0], rx_i}` and that the receiver state machine consumes `sync_q[1]`. This establishes the digital two-stage structure; it does not establish metastability MTBF or safe physical placement. There is no `ASYNC_REG` attribute. Reset is asserted and released directly through `rst_n` in RX, TX, wrapper, and core, with no release synchronizer. The CDC log explicitly skips ports without input delays, despite the CDC report's “All paths are Safely Timed” sentence. External RX CDC and asynchronous reset recovery/removal remain NOT VERIFIED. No wrapper or cryptographic RTL was changed.

A separate board-wrapper change should add an asynchronously asserted, synchronously deasserted reset and apply appropriate synchronizer attributes to RX/reset stages. Before that change, add tests for reset assertion/release at varied phases, reset during busy RX/TX/Ascon operations, the documented release-cycle bound, and absence of stale valid/alarm/partial frames. Rerun the existing UART clean/fault/CRC and fail-closed RTL benches. Inspect the synthesized synchronizer stages/attributes and post-route placement, then rerun the affected UART implementation and board-context timing/CDC/recovery-removal checks. Digital simulation cannot prove analog metastability safety; any external timing exceptions must be individually justified. This is a proposal requiring a separate reviewed implementation, not a completed safety fix.

### Final tests and review status

The preceding portability review completed with **105 passed, 8 skipped, 6 explicitly deselected, zero failures or collection errors**; the latest acceptance-review results are recorded below. The skips include the absent clang C oracle, two Windows contract simulations without Verilator, and the existing opt-in/live-tool checks. The six deselections are mandatory Verilator RTL/campaign tests unavailable on this laptop; their test definitions and Linux CI execution remain unchanged. Python reference/KAT, model, dashboard/API, Node-based trace, UART host/static, provenance, and report-validation tests ran where available. POSIX subprocess-option behavior is unit-tested with a resource stub; a native Linux run of these uncommitted changes has not been performed or claimed. The exact JUnit skips, deselections, command and logs are in `final_verification/review_summary.json` and `final_windows_tests.*`.

The portable evidence CLI now reports PASS for campaign bytes, all seven historical RTL pins under explicit CRLF-to-LF comparison, and the Ascon-C revision pin. Original raw hashes and pinned hashes are both printed. Prior failure logs remain retained; they describe the earlier state, not unresolved failures. The UTF-8 report-generator punctuation caught during diff review was restored, and affected report/provenance tests subsequently passed (30 passed, 1 skipped).

No known failure remains among tests that can run here. Native RTL simulation, Yosys/SAT/bounded-formal checks, actual Linux CI, external I/O/CDC/reset safety, board timing and physical hardware validation remain unavailable or unverified. Nothing has been staged, committed, pushed, or programmed. The complete diff against HEAD includes both the original Phase 12 work and these final portable fixes; review it before approving integration.

### Complete changed-file list against HEAD

- `experiments/phase10b_analysis.py`
- `experiments/phase10d_fpga.py`
- `experiments/phase10e_feasibility.py`
- `scripts/phase10e_vivado_ooc.tcl`
- `src/faultscope_ascon/cli.py`
- `tests/test_phase10a_rtl_contract.py`
- `tests/test_phase10d_fpga.py`
- `tests/test_phase10e_feasibility.py`
- `docs/phase12_vivado_implementation.md`
- `experiments/source_provenance.py`
- `scripts/phase12_report.py`
- `scripts/phase12_vivado.ps1`
- `scripts/phase12_vivado_ooc.tcl`
- `tests/test_phase12_vivado.py`
- `tests/test_source_provenance.py`

## DRC severity and complete-suite acceptance review

This final acceptance review reproduced the two reported fail-open cases before changing code: four capitalization variants of critical/error DRC violations passed, and a single protected-core run passed `--require-verified` with three architectures missing. All five negative tests failed before the fix; the before-fix log is preserved in `acceptance_review/before_fix_tests.log`.

The DRC severity match now ignores capitalization and permits whitespace between Critical and Warning. Regression tests cover upper/lower/mixed case and the Vivado 2026.1 summary-table and rule-detail layouts. Genuine reports with no critical/error violations remain accepted, including the actual saved reports containing only CFGBVS-1 Warning. Relevant critical/error matches make both implementation and internal timing NOT VERIFIED.

`--require-verified` defaults to the complete four-architecture set at every observed period. `--expected-periods` pins the required period set, so an entirely absent period cannot be silently accepted. Missing architecture/period combinations and collection errors return exit 2; verified coverage with failing timing returns exit 3. An intentionally selected subset must use `--expected-designs`; its summary explicitly records `acceptance_scope=explicit-subset` and `full_suite_complete=false`, even when that selected subset passes. It is not full-suite acceptance.

Directory labels and metadata must agree. Duplicate combinations (including 10ns/10.0ns aliases), unexpected architectures or periods, extra architectures outside a selected subset, malformed run labels with metadata, duplicate/empty selections, and nonfinite/out-of-range periods are rejected. Legitimate complete multi-period suites pass. The PowerShell runner now passes its Designs and Periods explicitly to validation, rejects duplicate/empty selections before any Vivado invocation, and uses round-trip period formatting to avoid silently rounding requested periods.

Read-only validation of the original saved suite succeeds:

```powershell
python scripts\phase12_report.py build\reproduction\phase12\clock_context_10ns --require-verified --expected-periods 10 --validate-only
```

No Vivado was invoked. All 152 protected files remain byte-for-byte unchanged, including RTL, campaign and Phase 5 evidence/pins, CI workflows, and every authoritative saved implementation file. The four original LUT/FF/WNS/WHS tuples remain exactly unchanged; see `acceptance_review/saved_suite_validation.json`. The OOC clock-buffer assumption and unresolved external timing/CDC/reset limitations documented above still apply.

Focused parser tests: **47 passed**. All locally available Windows regressions: **138 passed, 8 skipped, 6 explicitly deselected, zero failures/errors**. Unavailable native RTL/formal checks and Linux CI have not been claimed as passing. PowerShell syntax and duplicate/empty selection preflight checks also pass without launching Vivado.

Exactly four repository files changed during this review:

- `scripts/phase12_report.py` - DRC capitalization, complete architecture/period coverage, explicit subset/period selection and read-only validation.
- `scripts/phase12_vivado.ps1` - selected-scope forwarding, duplicate/empty preflight guards and exact period formatting.
- `tests/test_phase12_vivado.py` - negative reproductions, Vivado-layout DRC checks, positive acceptance and architecture/period ambiguity tests.
- `docs/phase12_vivado_implementation.md` - corrected acceptance semantics, final verification and read-only command.

`acceptance_review/this_review_diff.patch` is the incremental four-file diff against the starting local workspace. `acceptance_review/final_diff.patch` and the root `final_diff.patch` contain the complete 15-file diff against HEAD, including prior Phase 12 work. Previous report, summary and diff versions are preserved under `acceptance_review/before_*`. Nothing is staged, committed or pushed.
