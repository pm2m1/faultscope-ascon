# Phase 17 — Manual review of the separate Rev. C configuration-voltage routed candidate

## Scope, original evidence, and disposition

**Disposition: ACCEPT for a *provisional research implementation* pull request, contingent on the expected six-file plus this addendum scope and green CI. Do NOT approve bitstream generation, configuration-bank electrical qualification, CDC/MTBF, external I/O timing, physical reset, or hardware signoff.** The target is **provisional Digilent Nexys 4 DDR Rev. C**, part `xc7a100tcsg324-1`. The physical PCB revision and its supply rails have not been observed. The Phase 17 run is a fresh full-device route, **not a modified/resaved Phase 15 DCP**.

- Phase 17 evidence: `build/reproduction/phase17/nexys4_ddr_rev_c_cfg_20261014T131338Z/` (local; preserve in `build/`, not Git).
- Original Phase 15 checkpoint SHA-256 (from accepted baseline and Phase 17 verification): `869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199`.
- Original Phase 15 base XDC SHA-256 (LF): `69bddc36a6142b41c47e4335bd3cb56e1051fe0cf52a33491fdcfd2338ffa4d8`; verified checkout mode `CRLF_CHECKOUT_EQUIVALENT_TO_ACCEPTED_LF`.
- Two-property overlay SHA-256, recorded by the Phase 17 validator: `9f2b07df823b3fc1b4bf1c28a0cf4bc774e3a38f4a85e16b04acf4ab38149223`.
- **New** Phase 17 routed DCP SHA-256, recorded by the validator (the binary DCP was not included in the review ZIP): `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`.
- Validator verdict: `ROUTED_CFG_CANDIDATE_REVIEW_REQUIRED`, with empty `issues`, no bitstream, no hardware programming. Local Python regressions: **32 passed** in Windows Python 3.12.4.
- The uploaded Phase 17 review ZIP contains 16 reports/TSVs/JSON. **All nine `report_sha256` values were independently recomputed from the ZIP bytes and matched the validator's `verification.json`.** This establishes integrity of *those included reports*, not an independent hash measurement of the omitted binary DCP.

## Exact implemented-property change

The Phase 17 overlay contains only the two board-configuration properties below; there were **no new pin, clock, delay, or false-path constraints**:

```tcl
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
```

`source_context.tsv` from the new route confirms `cfgbvs=VCCO`, `config_voltage=3.3`, `design_mode=full_board_not_ooc`, 10.000 ns clock, and the same eight RTL source names. The choice is based on the *intended* configuration supply of the documented Rev. C schematic, not on any measured user's PCB. See [Digilent schematic](https://digilent.com/reference/_media/nexys4-ddr/nexys_4_ddr_sch.pdf), [Digilent Rev. C master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Nexys-4-DDR-Master.xdc), and AMD Vivado UG912 (`CFGBVS`, `CONFIG_VOLTAGE`).

## Independent review of the exported Vivado 2026.1 evidence

| Diagnostic | Phase 17 reported finding | Interpretation |
|---|---|---|
| `post_route_drc.rpt` | **0 checks found** under default ruledeck; no `CFGBVS-1` | The Phase 15 default-ruledeck configuration warning is cleared **in this design**. Other electrical/bitstream checks and actual PCB measurements are not established. |
| `methodology.rpt` | Exactly **5 `TIMING-18` Warnings**: missing input delay on `rst_n`, `uart_rx_i`; missing output delay on `led_alarm_o`, `led_busy_o`, `uart_tx_o` | No improvement in external timing closure; do not invent clock-relative UART/reset requirements just to remove warnings. |
| `check_timing.rpt` | `no_clock=0`, `unconstrained_internal_endpoints=0`, `multiple_clock=0`, `loops=0`; `no_input_delay=2`, `no_output_delay=3` | Internal clocks have timing coverage; **five external ports remain unmodeled**; no false paths hide them. |
| `post_route_status.rpt` | **5,739 / 5,739** routable nets fully routed; 0 nets with routing errors | Complete route under implemented constraints. |
| `post_route_timing.rpt` | 100 MHz / 10.000 ns; WNS **+1.471 ns**, TNS 0, 0 setup failures; WHS **+0.022 ns**, THS 0, 0 hold failures; WPWS **+4.500 ns**, TPWS 0, 0 pulse-width failures | **Modeled internal timing meets requirements**, but the small +0.022 ns hold margin should be noted; these numbers are **not I/O or analog timing signoff**. |
| `clock_interaction.rpt` | One `board_clk_100mhz` self-clock relationship, **Clean**, **11,252** reported total endpoints, 0 failing endpoints | Only defined clock interaction; asynchronous UART/reset board inputs are not fully covered. |
| `clock_networks.rpt` | One 100 MHz constrained clock via port `clk`; 3,772 clock endpoints; 0 nonclock endpoints | Clock-net structural report; physical oscillator tolerance/start-up/jitter not characterized. |
| `cdc.rpt` | States `All paths are Safely Timed` | Not a proof for asynchronous input `uart_rx_i` or external `rst_n`; Vivado CDC analysis does not establish their analog MTBF or board timing. |
| `post_route_utilization.rpt` | 3,538 slice LUTs (5.58%), 3,772 slice FFs (2.97%), 6 bonded IOBs, 1 BUFGCTRL, 0 RAMB/DSP | Same implementation resource counts as Phase 15. |

The worst setup path is `core/FSM_sequential_fsm_q_reg[1]_rep__0` to `core/ascon_state_q_reg[303]`, with data path **8.413 ns**, routing **7.479 ns**. The worst hold path is `core/u_permutation/state_o_reg[109]` to `core/tag_q_reg[45]`, with **+0.022 ns** slack. The unconstrained I/O timing section shows **infinite/undefined slack** for external paths, including `uart_rx_i` and `uart_tx_o`: those must **not** be called timing-passing interfaces. The reset input's physical recovery/removal, bounce, and power-up are not verified by internally timed reset paths.

## Phase 15 comparison and physical synchronizers

Compared with Phase 15's archived reports, `pin_assignment.tsv`, `synchronizer_cells.tsv`, `synchronizer_edges.tsv`, `internal_metrics.tsv`, and `post_route_status.rpt` are **text-identical after newline normalization**. Setup/hold delta reported by the Phase 17 validator: **0.000 ns / 0.000 ns**; this is observed reproduction, **not evidence of voltage-induced timing improvement**.

- Six unchanged pin mappings, all `LVCMOS33`: `clk=E3`, `rst_n=C12`, `uart_rx_i=C4`, `uart_tx_o=D4`, `led_busy_o=H17`, `led_alarm_o=K15`.
- Three reset release stages: FDCE, `ASYNC_REG=1`, all `SLICE_X2Y144`, with both interstage Q→D connections `DIRECT`.
- Two UART RX synchronizer stages: FDPE, `ASYNC_REG=1`, both `SLICE_X64Y114`, interstage Q→D connection `DIRECT`.
- Structural preservation **does not** quantify UART metastability MTBF, asynchronous reset release under physical conditions, or real-world signal integrity.

## Open gates; no automatic closure

1. **Physical board and configuration:** Verify actual board revision, part, configuration bank `VCCO_0` wiring/supply, startup behavior, and electrical correctness. A clean *default* DRC is not board qualification or bitstream authorization.
2. **External constraints:** Determine appropriate UART transport/input modeling and actual peripheral/LED timing requirements. Keep the five `TIMING-18` findings visible until defensible requirements are available; do not silence with arbitrary delay values or broad false paths.
3. **Reset and CDC:** Test contact bounce, assertion pulse width, clock availability, asynchronous release conditions, reset recovery/removal, and receiver synchronizer behavior with justified analog assumptions / eventual hardware. `report_cdc` does not establish MTBF here.
4. **Hardware security and function:** No board execution, COM-port/LED checks, real transient fault generation, voltage measurement, or certified side-channel/fault-resilience claims; lab UART is unauthenticated. If later demonstrated, use **synthetic** cryptographic keys.
5. **Evidence/PR scope:** Keep `build/` and DCP/logs local and backed up. Commit only the six Phase 17 source/test/docs files plus **this review addendum** if the staged scope is exact; require repository CI green before merging. Do not modify past XDCs, RTL, Phase 15/16 evidence or claim physical signoff.

## Review decision

**Approve a Phase 17 draft PR *only as a reproducible, provisionally board-specific, fully routed configuration-property candidate*.** Do not approve a bitstream, programming or hardware readiness based on this review. The subsequent engineering work should prioritize an explicit external-interface/reset CDC timing argument and, when hardware is available, board electrical validation rather than merely eliminating warnings.
