# Phase 13 — UART CDC and reset-release hardening (FPGA pre-silicon pilot)

Target: Xilinx Artix-7 `xc7a100tcsg324-1`; nominal 100 MHz / UART 115200 baud.
No physical FPGA or serial link was used to verify this patch. **Never use real keys**:
UART transports all key material and plaintext in the clear, and CRC-8 is not an authenticator.

## Changes, boundaries, and reset timing

* New `rtl/fs_reset_sync.sv`: three async-clear flops, `ASYNC_REG=TRUE`,
  `SHREG_EXTRACT=NO`; async `rst_n` assertion clears all three stages and
  `rst_n_sync` immediately, even if the clock stops. Deassertion propagates
  through three rising edges before `rst_n_sync` becomes high. Downstream
  stateful logic begins normal processing on a subsequent rising edge.
* `rtl/faultscope_uart_top.sv`: the raw physical `rst_n` only enters the
  reset-release synchronizer; the RX, TX, protected core, and wrapper's state
  registers all use `rst_n_core`. Port set remains six scalar bits.
* `rtl/fs_uart_rx.sv`: annotate the existing two-stage synchronizer with
  `ASYNC_REG=TRUE` and `SHREG_EXTRACT=NO`. `rx_i` feeds only its first stage;
  UART FSM uses the second stage. No new generated clock is introduced.
* **Unchanged cryptographic RTL**: Ascon round, permutation, and bounded
  protected AEAD remain byte-for-byte unchanged. No older campaign evidence,
  benchmark report or formal claim is modified.
* **Important**: Reset release requires a stable, running input clock. This
  design does not debounce a mechanical reset, verify minimum reset pulse
  width, prove metastability MTBF, or establish board voltages and pin mapping.
  A reset can terminate a UART frame mid-byte, so the host must discard any
  partial reply and re-synchronize by waiting for the idle line and sending
  a new PING. The saved host client has no automatic mid-frame recovery.

## Digital verification gates

1. Python static/integration checks for top-level reset fanout and the
   complete source lists (Mac or Windows):

   ```powershell
   python -m pytest tests/test_phase13_reset.py tests/test_phase11_uart.py tests/test_phase11_fpga.py -v
   ```

   The Verilator and Yosys tests are opt-in and skip without their flags.
2. Mandatory Linux/Verilator after local static checks (opt-in workflow):

   ```bash
   FAULTSCOPE_RUN_PHASE11_UART=1 python -m pytest tests/test_phase11_uart.py -v
   FAULTSCOPE_RUN_PHASE13_UART=1 python -m pytest tests/test_phase13_reset.py -v
   FAULTSCOPE_RUN_PHASE11_FPGA=1 python -m pytest tests/test_phase11_fpga.py -v
   ```

   The Phase 13 testbench checks three reset-release phases, partial command,
   mid-response reset, reset during actual AEAD busy operation, stale state
   clearing, real fault-alarm clearing, and post-reset PING/recovery.
3. Push this patch to a **feature branch** and create a pull request. The
   new `phase13-cdc-reset.yml` runs on that PR, making all three live checks
   mandatory. After merge, manual reruns are available with `workflow_dispatch`.
   A passed default Python suite alone is **not** sufficient. Do not claim
   success before the GitHub live jobs actually pass.

## Vivado reimplementation on Windows (after RTL simulation passes)

The existing Phase 12 Tcl flow now includes `fs_reset_sync.sv` in the
UART-protected source set. **Preserve** the old `clock_context_10ns` directory
as authoritative Phase 12 evidence; do not overwrite it. From repo root:

```powershell
.\scripts\phase12_vivado.ps1 `
  -Vivado 'C:\AMDDesignTools\2026.1\Vivado\bin\vivado.bat' `
  -Python 'C:\Users\mishr\anaconda3\python.exe' `
  -Designs uart_protected -Periods 10 `
  -OutputRoot 'build\reproduction\phase12\phase13_uart_ooc_10ns'
```

The validated report must indicate `acceptance_scope=explicit-subset`; it
must **never** masquerade as verification of all four architectures.
Use actual synthesized/post-route results to compare the UART row to Phase 12:
3,536 LUT, 3,769 FF, WNS +2.239 ns, WHS +0.028 ns. These are historical
Phase 12 numbers, **not a prediction** for Phase 13. A timing regression,
new routing error, DRC critical/error, or failed setup/hold is a blocker.

Use read-only validation (adjust path if the named output is different):

```powershell
python scripts\phase12_report.py `
  build\reproduction\phase12\phase13_uart_ooc_10ns `
  --require-verified --expected-designs uart_protected `
  --expected-periods 10 --validate-only
```

## Additional implementation-level inspections

In Vivado, inspect `ASYNC_REG`/`SHREG_EXTRACT` on all reset-release and UART
RX synchronization stages and their placement; verify the stages survived
synthesis and are not incorrectly merged, retimed, or repurposed. Inspect
reset recovery/removal, reset distribution/fanout, and `report_cdc` **with
external ports and missing input/output delay limitations visible**. A blank
CDC report is not proof of safe external UART input/reset behavior.
Do not add blanket false paths or timing exceptions merely to pass reports.
Any justified asynchronous-port or synchronizer exception needs a separate
analysis, documented endpoint set and review.

This is not a board-constrained clock/IBUF/BUFG implementation. The OOC
`BUFGCTRL_X0Y0` source-context assumption, external UART path timing, and
physical board deployment remain unverified. Physical fault resistance,
MTBF, key handling/erasure, reset debouncing, and secure serial transport
are **outside Phase 13**.
