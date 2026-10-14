# Phase 15 — PROVISIONAL Nexys 4 DDR Rev. C full-device Vivado pilot

## Decision boundary

**Provisional target only: Digilent Nexys 4 DDR Rev. C.** The user has not confirmed a physical board revision and does not presently have a physical FPGA board. The Nexys 4 (without DDR), Nexys 4 DDR, Nexys A7 50T, and Nexys A7 100T are NOT interchangeable targets. Never use these pin constraints for an unidentified board. This pilot does not generate or program a bitstream.

Source of pin assignments: Digilent's official [Nexys-4-DDR-Master.xdc](https://github.com/Digilent/digilent-xdc/blob/master/Nexys-4-DDR-Master.xdc), marked **Nexys4 DDR Rev. C**. Verify the actual board silkscreen, FPGA marking, schematic revision and Digilent document before any subsequent bitstream work. See Digilent's [reference manual](https://digilent.com/reference/_media/nexys4-ddr/nexys4ddr_rm.pdf) and [schematic](https://digilent.com/reference/_media/nexys4-ddr/nexys_4_ddr_sch.pdf).

| Existing RTL port | Direction | DDR Rev. C schematic name | FPGA package pin | I/O |
|:--|:--|:--|:--|:--|
| `clk` | input | `CLK100MHZ` | E3 | LVCMOS33 |
| `rst_n` | input | `CPU_RESETN` active-low pushbutton | C12 | LVCMOS33 |
| `uart_rx_i` | input | `UART_TXD_IN` bridge-to-FPGA | C4 | LVCMOS33 |
| `uart_tx_o` | output | `UART_RXD_OUT` FPGA-to-bridge | D4 | LVCMOS33 |
| `led_busy_o` | output | `LED[0]` | H17 | LVCMOS33 |
| `led_alarm_o` | output | `LED[1]` | K15 | LVCMOS33 |

**Important direction trap:** the Digilent USB-RS232 `UART_TXD_IN` and `UART_RXD_OUT` names denote the bridge-facing names, not an invitation to swap host TX/RX without checking the board drawing. This mapping follows the six-port RTL's direction. User LED mappings are a proposed assignment to LED0 and LED1, not an existing wiring claim about the RTL.

## Windows usage (create a review branch, do not commit before examining Vivado output)

From `C:\Projects\faultscope-ascon`, after extracting the pilot ZIP:

```powershell
& 'C:\Users\mishr\anaconda3\python.exe' -m pytest tests/test_phase15_board.py -v
& 'C:\Users\mishr\anaconda3\python.exe' scripts/phase15_board_report.py --preflight-only
.\scripts\phase15_board.ps1
```

You may supply `-Vivado`, `-Python`, `-OutputRoot`, `-Xdc` on the PowerShell runner if paths differ. The runner checks the exact six XDC commands, opens a fresh timestamped output directory under `build/reproduction/phase15`, and calls Vivado in batch. It **fully synthesizes, places and routes the device** using the real 100 MHz E3 input pin and its inferred input/global clock buffers. It does **not** use `-mode out_of_context`, `HD.CLK_SRC`, intentional timing exceptions, or `write_bitstream`. It writes a full set of clock, DRC, timing, port and synchronizer inspection reports and `post_route.dcp` into the ignored output directory. Previous Phase 12–14 results are not touched.

After the run, inspect `verification.json`, `pin_assignment.tsv`, `synchronizer_cells.tsv`, `synchronizer_edges.tsv`, `internal_metrics.tsv`, `post_route_drc.rpt`, `post_route_timing.rpt`, `check_timing.rpt`, `clock_networks.rpt`, and `cdc.rpt`. The Python validator requires the six exact pins, XDC, five mapped synchronizer cells, their `ASYNC_REG`/location, and three direct interstage nets, measured nonnegative internal setup/hold, a full implementation checkpoint and report files. A success verdict is only **`CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED`**, never a full signoff. If the mapped FFs have different names in the full-board checkpoint, investigate real cells first; do not disable the attribute/location checks or fabricate a pass.

## Deliberate remaining limits

- Physical board revision and electrical documentation: not confirmed against hardware.
- External input/output timing: **NOT VERIFIED** (no justified UART/LED I/O delay models); reset input is asynchronous. Do not invent `set_input_delay` / `set_output_delay` or broad `set_false_path` settings just to silence warnings.
- Clock arrival/source jitter or oscillator tolerance under actual operating conditions: not measured.
- Reset button bounce, power-up/startup, minimum pulse, recovery/removal, metastability MTBF, and precise CDC structural applicability: **NOT VERIFIED**.
- Board programming, serial COM port communication, LED behavior and physical fault injection: **NOT TESTED** because no board is connected.
- The UART lab transport is unauthenticated, unencrypted, and not suitable for production keys. Only synthetic test keys.
- The strict Python review deliberately leaves manual Vivado DRC, clock-network and external constraints review open; do not equate a positive register-to-register WNS/WHS with board signoff.

## Review policy

Keep this change separate from Phase 12–14 and all historical campaign evidence. Keep the output in `build/` (git-ignored) and archive it outside Git as needed. Do not commit/push/merge until actual Vivado execution and reports are reviewed. This pilot's first run on Windows is an implementation experiment; adapt tool-version-specific report formatting with a tested patch rather than relaxing correctness gates. No board purchase required for this implementation experiment; a physical board is required for hardware claims.
