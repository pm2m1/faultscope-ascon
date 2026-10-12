# Phase 5 — Technology-independent synthesis and latency comparison

## Objective

Measure the **relative RTL resource complexity** of three architectures, and join that information with the verified Phase 4B fault and cycle data:

1. `ascon_aead_encrypt_bounded` — no fault-injection instrumentation, no protection.
2. `ascon_aead_encrypt_faultable` — instrumentation but no protection.
3. `ascon_aead_encrypt_temporal` — the same basic fault controls plus temporal recomputation and fail-closed gating.

These are distinct RTL top modules. Comparisons between protected and instrumented isolate the approximate *increment associated with defense* more fairly than only comparing protected with the wholly uninstrumented baseline. However, they are still design-level resource comparisons, not exact isolated gate attribution.

## Requirements

```bash
brew install yosys sv2v
```

Use the same Yosys and sv2v tool versions for all three variants. Save the emitted manifest and synthesis logs.

## Steps

First verify existing project regressions:

```bash
uv run python -m pytest tests/ -v
```

Generate or regenerate Phase 4B results (do not manually edit):

```bash
uv run python -m experiments.run_phase4b --out reports/phase4b_temporal.csv
```

Test the Phase 5 analysis code (these tests do not need Yosys):

```bash
uv run python -m pytest tests/test_phase5_analysis.py -v
```

Run all three Yosys synthesis jobs:

```bash
uv run python -m experiments.run_phase5 \
  --campaign reports/phase4b_temporal.csv \
  --out-dir reports/phase5
```

Inspect the report:

```bash
cat reports/phase5/REPORT.md
cat reports/phase5/synthesis_summary.csv
```

Optionally compare Yosys statistics from the full logs:

```bash
tail -n 50 reports/phase5/logs/baseline_yosys.log
tail -n 50 reports/phase5/logs/instrumented_yosys.log
tail -n 50 reports/phase5/logs/protected_yosys.log
```

## Files produced

- `REPORT.md` — combined findings and limitations.
- `synthesis_summary.csv` — generic mapped-cell counts, FF output bits.
- `synthesis_summary.json` — same counts plus gate-type distributions.
- `campaign_summary.json` — fault detection and latency metrics from the CSV.
- `manifest.json` — tool versions, source SHA256 hashes, campaign hash, Git commit.
- `logs/*` — separate sv2v conversion and Yosys synthesis logs for each top.
- `netlists/*` — converted Verilog and flattened Yosys JSON netlists.

All syntheses use: `sv2v` conversion; `hierarchy -check`; `synth -flatten -noabc`; `check -assert`; `write_json`. No specific FPGA family, device, ASIC library, standard-cell area, placement, routing, timing closure, or power model is used. A generic-cell count is NOT a physical area estimate, and the cycle ratio is NOT a frequency or throughput measurement.

## Scientific interpretation and limitations

- Phase 4B faults target only a single pre-round state bit in the *first* permutation execution, while the replay is clean. This intentionally optimistic model does **not** include shared engine faults, corrupted checkpoints, comparator/control FSM faults, repeated/permanent faults, clock glitches, or faults during replay.
- 93 alarms for 93 applied faults means **100% detected for this injected fault subset only**. Permutations are bijective, so a single flip in a checkpointed input state must lead to a different result if the replay is clean. Avoid presenting this as a novel universally effective countermeasure.
- 'No false alarms' is only observed under the 331 no-injection scenarios in this campaign; it does not establish a zero false-alarm probability.
- Fail-closed output behavior is an *RTL interface guarantee under the tested paths*, not proof of physical secure operation or of authentication-bypass prevention. The design is an **encrypt-only** bounded AEAD engine. Authenticated decryption/tag verification at RTL is not implemented in Phase 4B.
- Do not call the resource counts FPGA LUTs or silicon area. For more meaningful resource measurements on an actual FPGA, add `synth_xilinx` and target part information in a separate explicitly scoped experiment.

## Acceptance criteria

1. Existing `29` project tests remain passing.
2. `tests/test_phase5_analysis.py` passes.
3. All three synthesis runs exit successfully, with `hierarchy -check` and `check -assert` passing.
4. Output artifacts contain all three design entries and tool/source provenance.
5. Report provides quantified cycle overhead and **clearly distinguishes** generic resource counts from physical area.

Do NOT commit any generated `reports/phase5` data before checking its size; optionally commit a small reproducible metrics summary rather than huge netlists and logs. Track the Phase 5 Python analysis and documentation independently from generated data.
