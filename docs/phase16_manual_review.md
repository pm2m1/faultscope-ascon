# Phase 16 — Manual signoff-gap review of Phase 15 routed checkpoint

## Scope and acceptance

**Review decision:** ACCEPT the Phase 16 read-only *diagnostic/research milestone* for source-control review, **not** hardware/bitstream/CDC signoff. The target is provisionally **Digilent Nexys 4 DDR Rev. C**, FPGA `xc7a100tcsg324-1`; physical board revision has not been confirmed and no board was programmed. All review findings below refer to the existing Phase 15 routed checkpoint and its Phase 16 inspection reports. This audit does not modify XDC/RTL/implementation artifacts.

- Phase 15 checkpoint: `build/reproduction/phase15/nexys4_ddr_rev_c_20261014T045950Z/post_route.dcp`.
- Phase 16 evidence: `build/reproduction/phase16/gap_audit_20261014T123705Z/` (local and intentionally Git-ignored).
- Phase 15 checkpoint SHA-256: `869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199`.
- Accepted LF XDC SHA-256: `69bddc36a6142b41c47e4335bd3cb56e1051fe0cf52a33491fdcfd2338ffa4d8`.
- Windows checkout XDC SHA-256: `516cc4c205f85e1160ca1b26bb41165f4566adf0c186ac57c72a836e06f951aa`.
- Provenance result: `CRLF_CHECKOUT_EQUIVALENT_TO_ACCEPTED_LF`; only the uniform CRLF representation of the *exact original XDC bytes* was accepted. Phase 16 regression tests: **30 passed** on Windows.
- Phase 16 verification verdict: `EVIDENCE_COLLECTED_REVIEW_REQUIRED`, no validator issues. Seven exported report SHA-256 values were recomputed from the review archive and match `verification.json`.

## Exact post-route diagnostic findings (Vivado 2026.1)

| Report | Finding | Review status |
|---|---|---|
| `drc.rpt` | Default ruledeck: **one** warning `CFGBVS-1`; 0 other findings. `CFGBVS` and `CONFIG_VOLTAGE` are both **UNSET** in the restored checkpoint. | **OPEN**; do not suppress rule or write a bitstream. |
| `methodology.rpt` | **Five** `TIMING-18` warnings: missing input delay for `rst_n`, `uart_rx_i`; missing output delay for `uart_tx_o`, `led_busy_o`, `led_alarm_o`. No other methodology rules were reported. | **OPEN**; constraints require defensible interface models, not guessed values. |
| `check_timing.rpt` | `no_clock=0`, `unconstrained_internal_endpoints=0`, `multiple_clock=0`, `loops=0`; `no_input_delay=2`, `no_output_delay=3`. No false-path constraints hide these five ports. | Internal coverage positive; **external paths unresolved**. |
| `clock_interaction.rpt` | Single `board_clk_100mhz` to itself: clean/timed, **11,252 total endpoints**, 0 failing endpoints, WNS displayed as +1.47 ns. No second clock domain in this report. | Internal timing evidence only; not external-input CDC analysis. |
| `clock_networks.rpt` | Single constrained 100 MHz clock on port `clk` with **3,772 clock endpoints** and 0 nonclock endpoints. `context.tsv` reports 1 BUFG-family clock buffer and 3 IBUF-family input buffers. | Clock topology structurally reported; hardware clock jitter, tolerance and power-up not verified. |
| `timing_summary.rpt` | 10.000 ns clock; setup **WNS +1.471 ns**, TNS 0, 0 failing endpoints; hold **WHS +0.022 ns**, THS 0, 0 failing endpoints; pulse-width **WPWS +4.500 ns**, TPWS 0, 0 failing endpoints. Worst setup data path 8.413 ns (7.479 ns routing). External `uart_rx_i` and outputs have paths with **infinite/undefined slack** because required external delays are missing; these are **not passing timing constraints**. | Modeled internal timing passes; external signoff remains **OPEN**. The +0.022 ns hold margin is small. |
| `cdc.rpt` | Says *All paths are Safely Timed*. Vivado console explicitly states `report_cdc` skips ports without input-delay constraints. | **NOT a UART input/reset CDC or analog MTBF signoff.** |

The timing report shows additional `**async_default**` paths timed in the existing netlist. Those modeled checks do **not** establish recovery/removal or pulse-width behavior for an uncharacterized physical reset input, including contact bounce, clock startup and asynchronous deassertion stimulus.

## Open engineering decisions (do not silently close)

1. **Electrical configuration bank:** Board documentation suggests `CFGBVS=VCCO` and `CONFIG_VOLTAGE=3.3` for *confirmed* Nexys 4 DDR Rev. C with the corresponding VCCO_0 connection. The current checkpoint has neither property. Check actual board/schematic revision and configuration supply before a **separate** configuration-hardened XDC and **fresh full implementation**. Do not modify accepted Phase 15 evidence or merely patch a routed checkpoint to claim closure.
2. **Asynchronous UART RX:** Preserve the physical two-flop `ASYNC_REG` chain (Phase 15 verification), document why its first-stage input is asynchronous, assess synchronizer timing/MTBF using justified board data where possible, and avoid fake synchronous `set_input_delay` or blanket false paths.
3. **UART TX and LEDs:** Obtain actual peripheral timing/load expectations or explain precisely why synchronous setup/hold constraints do not apply to a protocol-level asynchronous interface; do not mistake missing constraints for closure.
4. **Reset:** Identify physical active-low source, pulse width, bounce, supply startup and clock availability. Confirm the asynchronously asserted / synchronously released three-flop reset architecture under realistic board conditions. Do not infer external recovery/removal closure from generic internal timing.
5. **Clock and board:** Physical oscillator tolerance/jitter, I/O voltage, PCB routing, actual board revision, programming, COM-port behavior, LED outputs and fault behavior remain **HARDWARE_DEPENDENT**; no bitstream or hardware test is authorized by this report.
6. **Security boundary:** The lab UART interface provides no authentication/encryption. Do not use production secrets or claim certified fault resilience; future physical demonstrations use synthetic keys only.

## PR merge gate

Phase 16 may be merged **as report tooling + documentation** after checking that the PR changes only its intended audit/test/docs files and existing Linux CI passes. Preserve the full Phase 16 reports and Phase 15 checkpoint separately from Git. Do **not** introduce modified Phase 15 XDC, RTL, bitstream, timing exceptions, configuration-voltage 'fixes', or fabricated board measurements in this PR.
