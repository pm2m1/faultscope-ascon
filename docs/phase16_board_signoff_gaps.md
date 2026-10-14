# Phase 16 — Read-only routed design signoff-gap audit

**Target is PROVISIONAL Digilent Nexys 4 DDR Rev. C, xc7a100tcsg324-1; no physical board exists in this workflow.** Phase 15 (`a0d3088`) is accepted **only** as a full-device routed research candidate, not as board signoff. Phase 16 deliberately **does not modify the Phase 15 XDC, RTL, post-route checkpoint, or historical result**. It does not synthesize, route, program a device, or generate a bitstream. No bitstream signoff is authorized.

## Primary documented sources (check exact board revision before hardware)

1. [Digilent Nexys 4 DDR Rev. C.1 schematic, document 500-292](https://digilent.com/reference/_media/nexys4-ddr/nexys_4_ddr_sch.pdf), sheet **8/11** CONFIG/SPI FLASH: `CFG_BVS_0` (FPGA P8) connects to `VCC3V3`; `CPU_RESETN` is pulled up to `VCC3V3` through 4.7k and shorted to ground by the reset pushbutton. Power/GND sheet **11/11** identifies `VCCO_0` at package R9 alongside board power rails; verify the electrical net connection on the original schematic and physical board revision before applying configuration voltage constraints.
2. [Official Digilent Nexys 4 DDR Rev. C master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Nexys-4-DDR-Master.xdc) for the existing six physical port assignments.
3. [AMD UG912 CFGBVS](https://docs.amd.com/r/2024.1-English/ug912-vivado-properties/CFGBVS): VCCO option selects high-voltage configuration bank family (3.3/2.5 V); ground selects 1.8/1.5 V.
4. [AMD UG912 CONFIG_VOLTAGE](https://docs.amd.com/r/2022.1-English/ug912-vivado-properties/CONFIG_VOLTAGE): property of `current_design`, must equal actual configuration bank supply.
5. [AMD Vivado 2026.1 UG949 methodology](https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/Running-Report-Methodology): perform netlist and timing methodology checks on opened implemented design.

**Schematic-grounded candidate for future review, not applied by Phase 16:**

```tcl
# For electrically confirmed Nexys 4 DDR Rev. C only, after verifying VCCO_0 rail:
set_property CFGBVS VCCO [current_design]
set_property CONFIG_VOLTAGE 3.3 [current_design]
```

Do not silently add these commands to the locked Phase 15 seven-command XDC: Phase 15's immutable six-port validator intentionally rejects extras. A future new board-specific XDC and **fresh implementation** will be needed to close `CFGBVS-1` after confirming the exact revision and configuration-bank supply. Merely applying these properties to an already routed checkpoint does not establish a revalidated board implementation. Do not weaken DRC severities or add unjustified timing exceptions.

## Run on Windows (PowerShell, repo root)

```powershell
cd C:\Projects\faultscope-ascon
git switch -c phase16-signoff-gaps
# extract Phase 16 pilot archive into this repository on the new branch
& 'C:\Users\mishr\anaconda3\python.exe' -m pytest tests/test_phase16_gap_audit.py -v
.\scripts\phase16_gap_audit.ps1
```

Default input is `build\reproduction\phase15\nexys4_ddr_rev_c_20261014T045950Z\post_route.dcp`. The Python preflight revalidates the Phase 15 candidate through the existing Phase 15 strict validator, verifies the saved original `verification.json` hashes of the routed checkpoint and XDC, and refuses mismatches. **Git for Windows may convert the accepted Phase 15 XDC from LF to CRLF after checkout**. The preflight pins the original SHA-256 `69bddc36a6142b41c47e4335bd3cb56e1051fe0cf52a33491fdcfd2338ffa4d8` and accepts only either byte-identical contents or an entirely uniform CRLF checkout that normalizes to *exactly* the original LF bytes. It reports both the accepted SHA-256 and current worktree SHA-256 plus the provenance mode. A changed pin, clock, comment, altered/false saved hash, mixed line endings, or routed-checkpoint mismatch remains a hard failure. Do not normalize/rewrite or reset the Phase 15 XDC just to satisfy this audit. It never modifies the Phase 15 input. The PowerShell runner confines new diagnostic outputs to `build\reproduction\phase16\gap_audit_<UTC>`, and refuses overwrites. Vivado 2026.1 opens the checkpoint **read-only for inspection**; no `set_property`, `write_checkpoint`, `write_bitstream` or implementation commands occur.

`phase16_gap_audit.tcl` collects `context.tsv`, `ports.tsv`, `drc.rpt`, `methodology.rpt`, `clock_interaction.rpt`, `clock_networks.rpt`, `timing_summary.rpt`, `check_timing.rpt`, and `cdc.rpt`. The Python validator writes `verification.json` and `gap_matrix.tsv` with explicit *OPEN*, *MANUAL_REVIEW*, and *HARDWARE_DEPENDENT* states. The only successful collection verdict is `EVIDENCE_COLLECTED_REVIEW_REQUIRED`; that **never** means configuration, CDC, external I/O, reset or board signoff passed.

If Vivado fails, inspect the path of the console log printed by the wrapper; no existing evidence should be edited. If the validator returns `NOT_VERIFIED`, investigate which original hash/report/port/clock property differs before changing any source. A successful Phase 16 run must be inspected manually; do not commit or merge until review of the *actual* report content.

## Remaining engineering checks

| Area | Phase 16 disposition / required proof |
|---|---|
| Original physical board/revision | HARDWARE_DEPENDENT: identify board silkscreen and actual FPGA supply/revision |
| CFGBVS-1 | OPEN: original checkpoint missing properties; documented Rev. C proposal requires bank-voltage verification and new implementation |
| Default DRC | MANUAL_REVIEW: review severity of every violation in `drc.rpt`, not only CFGBVS-1 |
| Methodology | MANUAL_REVIEW: review all `report_methodology` rule IDs and severities |
| Clock | MANUAL_REVIEW: one 100 MHz clock and IBUF/BUFG connectivity, source tolerance and jitter not physically measured |
| UART RX async input | OPEN: direct 2-FF `ASYNC_REG` structure shown in Phase 15, analog MTBF NOT VERIFIED; no fabricated synchronous arrival budget |
| UART TX / LEDs | OPEN: output timing relationships/loads not validated against external components; no invented delays |
| Reset | OPEN: 3-FF deassertion synchronization structure, but bounce, async assertion minimum pulse, recovery/removal and power sequencing remain unverified |
| CDC report | OPEN: Vivado skips unconstrained external input ports; "All paths Safely Timed" is not physical metastability signoff |
| Physical testing | HARDWARE_DEPENDENT: no board, no UART tests, no physical fault injection, no bitstream |

**Security:** The existing UART demo protocol is not authenticated and not encrypted. Use only synthetic keys for a later board demonstration. No claims of side-channel/fault resistance certification follow from physical routing or a clean report.
