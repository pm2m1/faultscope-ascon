# Phase 4B — Temporal recomputation, detection, and fail-closed outputs

## What is being evaluated

This research demonstration uses the existing Phase 4A fault model: a single
controlled pre-round 320-bit state flip applied **only on the first execution**
of a selected Ascon p[8] or p[12] invocation. For comparison, the same
input state is checkpointed and replayed through the **same hardware engine**
without the injected fault. The first and second 320-bit permutation results
are compared after the final round. A mismatch raises `fault_detected_o`.

The protected AEAD controller propagates a sticky alarm to the transaction
boundary. It exposes ciphertext and tag only if `result_valid_o` is asserted
at successful completion. If any permutation mismatch occurs, it suppresses
both output ports (zeros), keeps `result_valid_o=0` and raises the alarm.
This is **detection**, not correction or authenticated-decryption testing.

### Interfaces and semantics

- `ascon_permutation_temporal.sv`: sequential, shared round engine; clean replay
  after the potentially faulted first run. `fault_fired_o` refers only to the
  first pass, not to the clean replay. `fault_detected_o` is a mismatch alarm.
- `ascon_aead_encrypt_temporal.sv`: bounded 0..16-byte AD/message, encryption
  and tag generation only, one transaction at a time. `fault_applied_o`
  confirms injection. `fault_detected_o` is sticky during the transaction;
  `result_valid_o` becomes 1 only after a completed transaction without alarm.
  Outputs are zero until a valid completed transaction. All three status signals
  are reset when a new valid transaction begins.
- `ascon_aead_encrypt_bounded.sv` remains unchanged as the golden RTL baseline.

### Methodology

1. Compile protected and unprotected RTL with Verilator.
2. For each case, run the original baseline, the protected design with fault
   injection disabled, and the protected design with the specified target armed.
3. Compare baseline and fault-free protected ciphertext and tag to the
   verified independent Python reference.
4. Check whether an injection occurred, whether the protected circuit raised
   an alarm, whether it suppressed all outputs, and whether latency increased.
5. Preserve CSV records, simulator/tool versions, and the Git commit hash.

The campaign includes the 135 existing Phase 4A scenarios, plus all 289
combinations of 0..16-byte AD and message sizes without faults: 424 cases.
Each case executes three hardware transactions in the same testbench.

### Important limitations

**This is a deliberately narrow, optimistic fault model.** It does not test
faults during the replay, shared round logic, input checkpointing, alarm wire,
comparison logic, FSM, clock distribution, or output-valid gating. Correlated,
permanent, and repeated faults might evade a temporal recomputation defense.

For a bijective permutation, a single input bit change produces a distinct
permutation output if no later interference occurs. Therefore 100% coverage
for *this particular modeled injection site* would be expected; it is not
proof of a physically secure fault detector. Expand the fault model before
making any general detection-coverage claim.

Latency is cycle-accurate **for these RTL implementations and this testbench**.
Area comparison is reserved for Phase 5 and must use comparable Yosys flows.
No claims about FPGA timing/power or post-route silicon measurements.

### Commands

```bash
uv run python -m pytest tests/test_rtl_temporal_countermeasure.py -v
uv run python -m pytest tests/ -v
uv run python -m experiments.run_phase4b --out reports/phase4b_temporal.csv
```

Only commit the seven new files after the full regression suite passes.
