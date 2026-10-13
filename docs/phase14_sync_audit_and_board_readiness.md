# Phase 14 — Routed synchronizer structural audit and board readiness

## Purpose and scope

This additive phase reads the **existing Phase 13** `faultscope_uart_top` post-route checkpoint for the **XC7A100T-1CSG324** part. It does **not** synthesize/place/route, edit RTL, create board pin constraints or generate a bitstream. The original six top-level ports, cryptographic Ascon RTL, historical reports and archived Vivado checkpoints remain untouched.

Phase 13 evidence: `build/reproduction/phase12/phase13_uart_ooc_10ns/uart_protected_10ns/post_route.dcp`, target 10 ns, published +1.881 ns WNS and +0.031 ns WHS. Those are internal-clock out-of-context results with assumed external clock context (`HD.CLK_SRC=BUFGCTRL_X0Y0`), *not* board timing signoff.

## Usage on Windows (PowerShell from repository root)

```
& 'C:\Users\mishr\anaconda3\python.exe' -m pytest tests/test_phase14_sync_report.py -v
.\scripts\phase14_sync_audit.ps1
```

`phase14_sync_audit.ps1` requires your installed Vivado 2026.1, an existing routed checkpoint, and a clean committed RTL worktree. It creates a new timestamped directory under `build/reproduction/phase14/` and refuses to overwrite an existing audit. Supply `-Checkpoint`, `-OutputRoot`, `-Vivado`, or `-Python` only when your local paths differ. The Tcl script calls `open_checkpoint` and reports only; it does not call any implementation or bitstream-writing commands.

Run the report parser again without Vivado:

```
& 'C:\Users\mishr\anaconda3\python.exe' scripts\phase14_sync_report.py build\reproduction\phase14\<your_audit_directory> --require-pass
```

Vivado can display a restored out-of-context checkpoint under its generated in-memory name `checkpoint_post_route`, not the original RTL top name `faultscope_uart_top`. The audit accepts those two known design labels, but continues to require the six exact ports, five named mapped registers, attributes and three direct connections; the generated name alone does not establish the source top identity.

The parser validates five mapped FF stages: reset release (0, 1, 2) and asynchronous UART receive (0, 1), all with `ASYNC_REG` true and physical LOC/BEL. It requires three **direct** Q-to-D stage connections, the exact six scalar ports/directions and 10 ns OOC clock source. Missing, duplicated, renamed, non-FF, disconnected, or unparsable evidence fails closed. The `SHREG_EXTRACT` directive may not survive as a primitive property; actual FD* primitive mapping is the no-SRL check. Any unrecognized synthesized naming should be **investigated against the checkpoint**: do not weaken checks by accepting arbitrary FFs.

Expected generated files: `manifest.json`, `cells.tsv`, `edges.tsv`, `ports.tsv`, `context.tsv`, `verification.json`, `timing_summary.rpt`, `check_timing.rpt`, `cdc.rpt`, `vivado.log` and `vivado_console.log`. The manifest records source and checkpoint raw SHA-256, Git HEAD, and timestamp. Preserve this local evidence outside Git in a backed-up folder.

**Important limit**: A pass proves mapped, attribute-marked FF structure and direct nets in this saved implementation only. It does **not** establish asynchronous setup/hold metastability MTBF, reset recovery/removal, reset pulse-width compliance, clock-startup correctness, physically constrained UART input timing, power integrity, full design-rule checks, or hardware behavior. `report_cdc` skips unconstrained external input ports; neither an empty CDC report nor Vivado's generic 'safe' text overrides these limitations. We do **not** invent a numeric MTBF, route frequency, or board pins.

### Resolving a NOT_VERIFIED audit

Read `cells.tsv`, `edges.tsv` and the Vivado log before changing code. If only cell names differ, establish the exact mapped names, inspect attributes and connections in the design checkpoint, then update a targeted detection expression plus regression tests; do not bypass the missing-stage or missing-edge controls. If the mapped synchronizer actually lacks a FF/ASYNC_REG or has logic inserted between stages, treat that as an implementation issue requiring separate RTL/synthesis changes and complete reimplementation/verification.

## Board integration readiness — no physical board yet

1. **Identify exact hardware**: Nexys 4 DDR vs Nexys A7 board revision, FPGA marking/package/speed grade, Digilent schematics, official board master XDC and board power/clock/reset documentation. Do not guess pin names or re-use a random Nexys XDC.
2. **Clock network**: establish oscillator input pin, nominal frequency and jitter, actual input buffer/BUFG clock path and constrained `create_clock`. The OOC `HD.CLK_SRC` assumption must be replaced by verified physical clock context.
3. **Reset source**: determine actual pushbutton/power-good/USB reset polarity, debounce needs, input voltage, minimum asserted pulse width, clock availability on release, and recovery/removal timing. Reset-release FF structure alone is insufficient.
4. **UART transport**: identify onboard USB-UART chip and FPGA-side RX/TX pin routing, 3.3 V/IOSTANDARD compatibility, USB serial port on host, baud rate and `CLOCKS_PER_BIT`, UART input path timing and TX output timing. Do not apply unjustified `set_false_path` to internal synchronized paths.
5. **Pin/IO constraints**: only then produce a complete reviewed XDC with exact `PACKAGE_PIN`, `IOSTANDARD`, board clock, physical reset/LED locations and voltage-bank compatibility. Do not generate a bitstream from the Phase 12 OOC checkpoint.
6. **Implementation signoff**: run full board-level synthesis/place/route after integrating proper clock/IBUF/BUFG and XDC; inspect setup/hold, route/DRC, unconstrained endpoints, CDC/recovery-removal, and synchronizer placement. Check precise FF-to-FF placement and any requested MTBF assumptions in that context.
7. **Hardware test**: after obtaining the FPGA, program a board-specific bitstream and run UART PING, framing/CRC negative cases, Ascon KAT, reset during active RX/TX/compute, zeroed invalid output on fault alarm, using **synthetic keys only**. UART has no key confidentiality or authenticated control.

## Review policy

Do not claim board-ready, physically tested, formal proof of analog CDC safety, or security certification. Keep this audit on a review branch until the actual local Vivado Tcl run produces interpretable evidence and the standard Linux CI remains green. Do not edit historical campaign outputs or pinned source hashes.
