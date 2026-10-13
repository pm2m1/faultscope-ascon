# Phase 10E — XC7A100T feasibility and optional Vivado timing pilot

This phase is deliberately split into **(A) out-of-context mapped-resource capacity screen** and **(B) optional Xilinx Vivado placement/routing/timing**. Nothing here changes source RTL, campaign evidence, or the earlier synthesis report.

## Device and source references

Nexys 4 DDR (Nexys A7-100T) uses the **XC7A100T-1CSG324C**. Relevant device maxima are **63,400 LUTs**, **126,800 FFs**, **135 RAMB36 equivalent blocks / 270 RAMB18**, and **240 DSP48**. Package-level maximum user I/O is **210 pins**, and substantially fewer user I/O signals may be exposed through accessible board headers. AMD UG474 and 7-series overview plus Digilent Nexys A7 reference manual are authoritative. Note that **1,188 Kb** sometimes shown in Digilent's summary refers to maximum *distributed RAM*, not total block RAM (4,860 Kb, per DS180); do not conflate them.

- [Digilent Nexys A7 reference manual](https://digilent.com/reference/_media/reference/programmable-logic/nexys-a7/nexys-a7_rm.pdf)
- [AMD UG474 7-series CLB resource table](https://docs.amd.com/r/en-US/ug474_7Series_CLB/7-Series-FPGA-CLB-Resources)
- [AMD 7-series DS180 overview](https://www.xilinx.com/support/documentation/data_sheets/ds180_7Series_Overview.pdf)
- [AMD UG475 packaging](https://docs.amd.com/api/khub/documents/kHyYQ6XzXnQwR2O~gaV~MQ/content)
- [Digilent Nexys A7 master XDC](https://github.com/Digilent/digilent-xdc/blob/master/Nexys-A7-100T-Master.xdc)

## A. Offline resource fit screen

Reproduce the actual XC7 map first (on Mac, Yosys and sv2v installed):

```bash
uv run python -m experiments.phase10d_fpga --out-dir build/reproduction/phase10d
uv run python -m experiments.phase10e_feasibility \
  --fpga-json build/reproduction/phase10d/fpga_resources.json \
  --out-dir build/reproduction/phase10e
cat build/reproduction/phase10e/REPORT.md
uv run python -m pytest tests/test_phase10e_feasibility.py -v
```

The script rejects unmapped/empty designs, unverified provenance, missing architectures, and writes only to `build/`. Counts are **technology-mapped LUT primitives, not occupied slices or route utilization**. It only screens LUT, FF, BRAM18-equivalent and DSP; no proof of routability, MUXF placement or implementation DRC closure is claimed.

### Top-level pin/board caveat

The original AEAD top has a wide parallel API: **542 input + 261 output bits = 803 parallel bits**. This cannot be mapped directly to **210 package user I/O pins**. An FPGA demonstration needs a separately verified interface wrapper (UART/SPI, host memory bus or buffered/serialized commands), data staging registers and pin-safe XDC constraints. This phase does not create a board bitstream or claim a working physical board design.

## B. Optional Vivado out-of-context timing pilot

Run only on a supported Linux/Windows computer with **Vivado** and XC7A100T device support installed. Do *not* attempt `brew install vivado`; this project does not assume native macOS Vivado support. From the repository root:

```bash
vivado -mode batch -source scripts/phase10e_vivado_ooc.tcl -tclargs protected 10.0
```

The `10.0` is a **requested** 100 MHz internal clock period, not an achieved Fmax. Repeat for `baseline` and `instrumented` to make a comparison; use the **same version, target part, constraints and strategies** for each. The Tcl runs native SV `read_verilog`, `synth_design -mode out_of_context`, `opt_design`, `place_design`, `route_design`, writes post-synth/place/route checkpoints and reports (`post_route_timing.rpt`, `check_timing.rpt`, `post_route_status.rpt`, etc.) under `build/reproduction/phase10e/vivado/<design>/`.

**Acceptance requires**: tool and part recorded; successful place/route; no critical DRC/route failures; constrained reg-to-reg setup path exists; no negative setup slack at the selected period; and `check_timing` reviewed for any unconstrained paths. Since the top's external I/O has no input/output-delay constraints, this result is **only internal reg-to-reg OOC timing**, not a board throughput/Fmax claim. It does not validate CDC, PLL generation, board XDC pin assignments, external timing, power, physical fault resilience, or protocol transfer rates. A clock-period sweep requires separate routed runs and interpretation, not `1000 / (period-WNS)` alone.

The Tcl script was prepared from AMD UG903/UG904 workflow guidance, **not executed in the patch-authoring environment**. If Vivado raises command/version errors, preserve the exact Tcl log and we will fix them before accepting numbers.

## C. GitHub pilot

The optional `fpga-feasibility.yml` GitHub workflow re-runs Yosys XC7 mapping then the resource-fit screen. GitHub-hosted runners **do not run Vivado here**. The job uploads reproducible resource and feasibility artifacts. Enable it manually after Mac testing and cross-version review.

## Integrity and limitations

Phase 10D report and AEAD RTL byte hashes are embedded in the new `feasibility.json`. The originating Phase 10D report must assert `historical_rtl_verified` and include all three intended architectures. Differences between Yosys versions must be reported and must not be construed automatically as security regressions. Resource fit is **necessary but not sufficient** for working hardware. Neither successful mapping nor OOC timing proves physical fault resistance or full Ascon-AEAD implementation security.
