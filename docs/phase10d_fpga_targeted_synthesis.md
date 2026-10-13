# Phase 10D — Artix-7-family FPGA primitive evaluation

## Objective and scope

Estimate the *synthesis-mapped FPGA logic resources* for the same three committed
Ascon-AEAD128 bounded encryption/tag-generation RTL architectures used in Phase 5:

| Variant | RTL top | Distinction |
|---|---|---|
| Baseline | `ascon_aead_encrypt_bounded` | No fault-injection hardware or replay |
| Instrumented | `ascon_aead_encrypt_faultable` | Fault-injection controls, no replay |
| Protected | `ascon_aead_encrypt_temporal` | Fault instrumentation + temporal recomputation |

This uses `sv2v` 0.0.13 then Yosys `synth_xilinx -family xc7` (Xilinx 7-Series
mapping, suitable as an **architecture-level reference** for Digilent Nexys 4 DDR's
Artix-7 XC7A100T). **Yosys does not select a specific XC7A100T speed grade or
package here**, and the design is synthesized **out of context**, with no I/O pad
buffers or automatic clock buffers inserted. It must **not** be described as a
physically placed implementation on a Nexys board.

The number of top-level key/nonce/plaintext/AD and output signal bits is far
larger than available physical user pins on the target board. The project is a
hardware engine meant for integration behind an interface, **not a board-ready
top-level design**. This phase does not implement a pin mux, AXI interface,
BRAM packet buffers, clock constraints, placement, routing, post-route timing,
power estimation, or physical fault injection.

## Steps on macOS

Prerequisites: `brew install yosys sv2v`, Python 3.12/`uv`; `sv2v --numeric-version`
must return **0.0.13**. Verify source integrity first:

```bash
cd ~/Projects/faultscope-ascon
uv run faultscope-ascon verify-evidence
uv run python -m pytest tests/test_phase10d_fpga.py -v
```

The last test in the new file is an opt-in, time-consuming tool invocation and
will be skipped unless requested. Run the complete tool flow directly:

```bash
uv run python -m experiments.phase10d_fpga \
  --out-dir build/reproduction/phase10d

cat build/reproduction/phase10d/REPORT.md
cat build/reproduction/phase10d/fpga_resources.csv
```

Run full regression tests afterward; no original experiments are overwritten:

```bash
uv run python -m pytest tests/ -q
```

**Never** point the Phase 10D CLI at `reports/` or `rtl/`: it refuses any
output directory outside `build/` and requires the seven source hashes to
match the pinned Phase 5 manifest before doing tool work.

## Synthesis flow

For each architecture independently:

```text
sv2v <same Phase 5 source list> → converted Verilog
Yosys:
  read_verilog <converted.v>
  hierarchy -check -top <top>
  synth_xilinx -top <top> -family xc7 -flatten -noiopad -noclkbuf
  check -assert
  stat -tech xilinx
  write_json <mapped.json>
```

`-flatten` prevents double-counting hierarchically nested RTL.
`-noiopad` avoids unrealistic I/O pad utilization with the enormous
out-of-context streaming input buses. `-noclkbuf` avoids insertion of a board
clock-buffer assumption. ABC maps the combinational logic to LUTs.

The script validates the *top-level mapped cells* from the JSON netlists,
rejects unmapped `$...` gates, unexpected RTL submodules and inserted I/O pads,
and excludes `$scopeinfo` metadata. It reports LUT1–LUT6 primitives and
FDRE/FDSE/FDCE/FDPE flip-flops separately from CARRY4, MUXF7/8, RAMB18/36,
DSP48, SRL and distributed RAM. Zero-count resources appear as zero; a
percentage change against zero is reported as **N/A**, never infinity.

Read the detailed `cell_types` map in `fpga_resources.json` for any other
technology primitives not included in the headline counts. LUT totals are
primitive counts, **not placed slices**. No equivalent slice consumption can be
reliably inferred without place-and-route and architectural packing.

## Interpreting comparisons

Compute and report both:

1. `protected / baseline − 1`: full instrumentation-plus-defense cost.
2. `protected / instrumented − 1`: closer to marginal replay-defense overhead
   (but still affected by independent synthesis optimizations).

Do **not** compare LUT totals directly to Phase 5 generic gate counts.
They are fundamentally different measures. Two machines with different Yosys
versions may produce different primitive counts; record `yosys -V`, sv2v
version, source hashes, and full synthesis flags before numerical comparisons.

The protected architecture's latency overhead comes separately from the
pre-existing Verilator Phase 4B experiment and must not be inferred from
synthesis counts. No timing-closure or maximum-frequency claim is possible here.

## Output artifacts

The CLI generates:

- `fpga_resources.json`: complete cell-type distributions, summarized resources,
  tool versions, RTL source hashes and two overhead comparisons.
- `fpga_resources.csv`: compact summary suitable for a comparison table.
- `REPORT.md`: easy-to-read results and explicit limitations.
- `manifest.json`: UTC run time, commit SHA, target family and synthesis flags.
- `logs/*_sv2v.log` and `logs/*_yosys.log`: commands and complete diagnostics.
- `netlists/*_sv2v.v`, `netlists/*_xc7.json`: converted HDL and mapped cells.

All are generated under `build/` (already ignored by Git). Original Phase 5
reports, hashes and RTL files remain unchanged.

## GitHub verification workflow

A separate `Phase 10D Xilinx Series-7 FPGA synthesis` workflow is included in
`.github/workflows/fpga-synthesis.yml`. Initially, this is **manual only**
(`workflow_dispatch`), because differences between Yosys 0.69 on macOS and
Ubuntu's distribution package must be evaluated before making this a required
PR gate.

After Mac synthesis succeeds, commit and push the four Phase 10D files, visit
**GitHub → Actions → Phase 10D Xilinx Series-7 FPGA synthesis → Run workflow**, and
inspect the generated 14-day artifact containing all netlists, logs and reports.
Only when both environments succeed, and differences are documented, should
`push`/`pull_request` triggers be considered.

## Research boundaries

This is **not** a Vivado resource/timing report, a measured FPGA utilization
percentage, a board-fit guarantee, a physical fault test, or authenticated
decryption hardware. Phase 10C's controller formal proof and Phase 4B/7A/7B
fault outcomes remain separate evidence with their respective assumptions.
