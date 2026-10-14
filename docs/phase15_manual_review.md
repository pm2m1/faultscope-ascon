# Phase 15 — Manual routed-candidate review (2026-10-14)

## Decision

**Accepted only as a provisional Nexys 4 DDR Rev. C full-device routed FPGA experiment.** This is **NOT** a board signoff, physical CDC/metastability proof, bitstream authorization, or tested hardware. The actual board and revision have not been verified because no board was connected. No bitstream was generated.

The manual review was based on the 14 report files archived from the Windows Vivado 2026.1 implementation directory:
`build/reproduction/phase15/nexys4_ddr_rev_c_20261014T045950Z/`.

- Reported post-route checkpoint SHA-256: `869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199` (reported in `verification.json`; full binary checkpoint not included in the small review archive).
- XDC SHA-256: `69bddc36a6142b41c47e4335bd3cb56e1051fe0cf52a33491fdcfd2338ffa4d8`, also verified against the Phase 15 pilot XDC supplied for this run.
- Target: `xc7a100tcsg324-1` / `faultscope_uart_top`; clock: `board_clk_100mhz` (10.000 ns).
- Candidate script verdict: `CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED`, `issues=[]`. This verdict does not accept external timing or the DRC warning.
- Preflight: exact six-port Rev. C mapping; Python regression tests: 24 passed after the pre-synthesis clock-query sequencing fix.

## Routing and timing, based on exported Vivado reports

- `post_route_status.rpt`: 5,739 of 5,739 routable nets fully routed; 0 routing-error nets.
- `post_route_timing.rpt`: WNS **+1.471 ns**, TNS 0, 0 setup failing endpoints; WHS **+0.022 ns**, THS 0, 0 hold failing endpoints; worst pulse-width slack +4.500 ns.
- All 3,772 clocked FFs see the single propagated 100 MHz board clock. The path detail shows the *routed* E3 `IBUF` -> `BUFGCTRL_X0Y16` global clock path, rather than the earlier OOC assumed clock source.
- Worst internal setup path: `core/FSM_sequential_fsm_q_reg[1]_rep__0` -> `core/ascon_state_q_reg[303]`, total data path 8.413 ns (routing 7.479 ns), suggesting routing/fanout sensitivity.
- Worst internal hold path: `core/u_permutation/state_o_reg[109]` -> `core/tag_q_reg[45]`, +0.022 ns, a small but positive measured margin in this implementation.
- `check_timing.rpt`: 0 unconstrained **internal** endpoints, 0 no-clock FFs, 0 combinational loops, 0 multi-clock FFs. These findings do not negate unconstrained external ports.

## Utilization and synchronizers

- 3,538 slice LUTs (5.58%); 3,772 slice FFs (2.97%); 6 bonded I/O pins; 1 global clock buffer; no block RAM or DSP; no black-box instances.
- UART RX stages `receiver/sync_q_reg[0:1]`: both `FDPE`, `ASYNC_REG=1`, in `SLICE_X64Y114` with a direct stage-to-stage net.
- Reset release stages `u_reset_sync/release_pipe_q_reg[0:2]`: `FDCE`, `ASYNC_REG=1`, in `SLICE_X2Y144`, two direct stage-to-stage nets.
- Pin mapping for provisional Rev. C from Digilent master XDC: `clk=E3`, `rst_n=C12`, `uart_rx_i=C4`, `uart_tx_o=D4`, `led_busy_o=H17`, `led_alarm_o=K15`, all `LVCMOS33`.

## Manual review exceptions — remain open

1. **DRC `CFGBVS-1`, severity Warning**: `CFGBVS` and `CONFIG_VOLTAGE` are absent. 0 errors and 0 critical warnings in the default post-route ruledeck. Resolve configuration-bank voltage from the confirmed board revision and official schematic before a bitstream; do **not** guess the values.
2. **External timing**: `check_timing.rpt` flags missing input delays for `rst_n` and `uart_rx_i`, and missing output delays for `uart_tx_o`, `led_busy_o`, and `led_alarm_o`. Their external arrival/load budgets are not established. No indiscriminate false paths should be added to silence these warnings.
3. **CDC/MTBF**: `cdc.rpt` says `All paths are Safely Timed`, but the externally asynchronous UART input is not modeled for complete CDC timing. No physical metastability MTBF or analog timing conclusion follows from this report. Preservation and co-location of `ASYNC_REG` FFs are only structural evidence.
4. **Reset**: physical button bounce, reset source/polarity on the actual revision, asynchronous pulse width, clock startup, recovery/removal under realistic input timing, and power-on behavior are **NOT VERIFIED**. Unconstrained external reset removal paths do not constitute signoff.
5. **Methodology and environment**: `post_route_timing.rpt` states that `report_methodology` was not previously run. The timing model does not establish measured oscillator jitter/tolerance under actual operating conditions.
6. **Board**: physical board identification, programming, UART COM-port behavior, LED responses, fail-closed behavior on physical faults, and real hardware are **NOT TESTED**. The UART link is unauthenticated/unencrypted; use synthetic keys for any future demonstration.

## Integration decision

This Phase 15 source/tooling change may be reviewed and merged **as a provisional research implementation**, provided documentation retains the above open limitations, the PR changes only Phase 15 files, and Linux CI passes. **Do not generate/program a bitstream or label this hardware-ready.** Preserve actual local checkpoint and complete routed reports outside Git because `build/` is ignored. A later board-specific signoff phase must verify board revision, configuration voltage, external timing/CDC/reset and rerun the necessary implementation.
