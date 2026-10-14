# Phase 22 — Exact timing report binding + provisional board I/O constraint inventory

**Scope: investigation only.** Branch from merged Phase 21 commit `0821d54`. Use the *accepted Phase 17* `post_route.dcp` (SHA-256 `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`). Phase 22 must never change RTL, XDC, DCP, timing exceptions, bitstream or placement/routing. No physical board is attached or signed off.

## Why Phase 22 exists

Phase 21 proved ten get_timing_paths queries can return paths, but its four *grouped* `report_timing -from ... -to ...` reports have misleading command headers: TCL collection/list passing caused the header to show only the last destination and a suspect source. A grouped textual report **must not** be used to assert exact query identity. The unexpected `release_pipe_q_reg[2]/C` timing *startpoint* still appears despite Phase 20's direct physical `.../Q → LUT1/I0` net proof; timing startpoint and net driver are distinct concepts, not interchangeable.

This pilot explicitly queries the **three FDCE/CLR** and **two FDPE/PRE** destination pins separately for each `max` / `min` delay type (ten queries total). Each result is rendered using AMD Vivado UG835 `report_timing -of_objects $path`; no grouped startpoint/endpoints collections and no simultaneous `-from`/`-to`/`-delay_type` with `-of_objects`. Reports include actual source, destination and path type. The validator rejects destination mismatches, unexpected timing sources, malformed/unbound commands, or unsourced numeric timing slack. A report whose true timing source is `/C` while query starts from `/Q` is **explicitly flagged**, never treated as a pin-level connectivity defect or proof.

The script also exports actual routed PACKAGE_PIN/IOSTANDARD/DIRECTION on six board ports and keeps the five missing delay warnings visible. Pin documentation is **not** a source for external input/output delay numbers. Exported `external_delay_model=NOT_QUALIFIED` is a deliberate unresolved condition.

## Grounded board documentation — never fabricate timing budgets

- Digilent **Nexys 4 DDR Rev. C** master XDC (not the similarly named original Nexys 4): <https://github.com/Digilent/digilent-xdc/blob/master/Nexys-4-DDR-Master.xdc>. The existing pin mapping is `clk E3`, `rst_n C12`, `uart_rx_i C4`, `uart_tx_o D4`, `led_busy_o H17`, `led_alarm_o K15`, all `LVCMOS33`. The XDC is a *package pin/IO-standard reference*, not a source of external timing constraints.
- Digilent Nexys4 DDR reference manual: <https://digilent.com/reference/_media/nexys4-ddr/nexys4ddr_rm.pdf>. Documents 100 MHz oscillator and FT2232HQ USB–UART path connected to C4/D4. UART baud rate/serial protocol is **not** a replacement for a synchronous `set_input_delay` or `set_output_delay` budget.
- Digilent Nexys4 DDR Rev C schematic: <https://digilent.com/reference/_media/nexys4-ddr/nexys_4_ddr_sch.pdf>. CPU reset-button net is active-low/pulled up; neither reset bounce nor minimum reset pulse width has been measured on the user's particular device.
- AMD Vivado Tcl UG835 commands: <https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/get_timing_paths> and <https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/report_timing>. `-of_objects` is designed to render paths returned by `get_timing_paths`, and must not be combined with `-from`, `-to`, or `-delay_type`.

| Port | Physical assignment from provisional DDR XDC | What is actually supported | What remains unverified |
|---|---|---|---|
| `clk` | E3, 100 MHz clock | Existing 10 ns constraint; 100 MHz oscillator in documentation | Startup, actual jitter/board revision |
| `rst_n` | C12, active-low reset input | Pin and reset-button topology | External async arrival/recovery/removal, pulse width, bounce |
| `uart_rx_i` | C4, USB-UART bridge drives FPGA | Pin mapping, async receive input | Analog MTBF, host/bridge waveform timing; **no synchronous input delay justified** |
| `uart_tx_o` | D4, FPGA drives USB-UART bridge | Pin mapping | Bridge input timing/load and an appropriate timing model |
| `led_busy_o`, `led_alarm_o` | H17, K15 | LED pin mapping | External load/timing model, hardware LED functionality |

**Do not eliminate TIMING-18 warnings by inventing timing numbers or applying blanket false paths.** An asynchronous input may require a deliberate CDC/reset methodology rather than fictitious phase alignment to `board_clk_100mhz`. Physical board/revision, oscillator and reset transitions remain unverified. No board programming is authorized.

## Windows pilot sequence

```powershell
cd C:\Projects\faultscope-ascon
git status --short
git switch -c phase22-timing-query-integrity
Expand-Archive -LiteralPath "$env:USERPROFILE\Downloads\faultscope_phase22_timing_query_pilot.zip" -DestinationPath . -Force
& 'C:\Users\mishr\anaconda3\python.exe' -m pytest tests/test_phase22_timing_query.py -v
git diff --check
& 'C:\Users\mishr\anaconda3\python.exe' scripts\phase22_timing_query_report.py --preflight-only
.\scripts\phase22_timing_query_integrity.ps1
```

Successful **collection** verdict: `PATH_OBJECT_REPORTS_REVIEW_REQUIRED` — **not** timing/board signoff. The validator will reject mismatched report endpoints, syntax errors, missing reports, nonfinite alleged slack and missing provenance. If the Vivado command or report format differs, record `NOT_VERIFIED` and review rather than editing accepted RTL/XDC/DCP or suppressing errors.

Review evidence in `build\reproduction\phase22\path_binding_<UTC>`: `verification.json`, `context.tsv`, `ports.tsv`, `path_bindings.tsv`, the ten individual `path_reset{0,1,2}_{max,min}.rpt` / `path_rx{0,1}_{max,min}.rpt`, `check_timing.rpt`, `methodology.rpt`, and `timing_summary.rpt`. Compare each path report's actual `Source`, `Destination`, `Path Type`, and printed `report_timing -of_objects` command. Explicitly document any `/C` vs `/Q` query startpoint discrepancy. Do not commit the pilot until the live evidence and validator behavior are independently reviewed.
