# FaultScope-Ascon — Phase 7A: Adversarial Temporal-Replay Evaluation

## Goal and immutable baseline

Challenge the **single pre-round state-bit flip, clean-replay assumption** of Phase 4B without changing any verified RTL module or any Phase 4A/4B evidence. The new `ascon_permutation_adversarial.sv` is a standalone **test fixture**, not a production defense. It instantiates the existing `ascon_permutation_faultable.sv` round engine and allows two independently configured permutations. It does not instrument the existing bounded AEAD datapath; that would be a separate Phase 7B task.

## Interfaces and assumptions

Input state packing: `{x0,x1,x2,x3,x4}`; bit zero = low bit of `x4`. Supported permutations: `p[8]` and `p[12]`. Each round engine can receive one controlled pre-round bit flip (`round` zero-based, `bit` 0..319), independently for the first and replay executions.

Checkpoint modes:

- `0`: untouched checkpoint.
- `1`: one bit corrupted **as the shared checkpoint is captured**, so both passes use the same wrong input.
- `2`: one bit corrupted in the replay's starting checkpoint only.
- `3`: reserved, treated as no fault.

When `suppress_alarm_i=1`, a mismatched comparison is *deliberately* overridden by the fault-injection test fixture: `raw_mismatch_o=1` but `fault_detected_o=0`, and the replay result is allowed out. In a real design, the comparator output is a protection-critical signal. This diagnostic override exists to reveal a fail-closed dependency and must not be incorporated as a production feature.

Results:

- `first_fired_o`, `replay_fired_o`, `checkpoint_fired_o`: the respective modeled fault trigger actually fired.
- `raw_mismatch_o`: full 320-bit comparison before simulated comparator suppression.
- `fault_detected_o`: alarm **after** suppression hook.
- `result_valid_o`: whether the output is released.
- `state_o`: replay permutation result if valid; **zero otherwise**.
- `done_o`: one-cycle pulse; `busy_o` asserted during both executions.

No output is valid before `done_o`. Restart with new inputs only when idle; the design is single-transaction.

## Scenario matrix

The deterministic generator yields 240 cases: each of 12 scenarios tested against ten 320-bit inputs for each of `p[8]` and `p[12]`.

| Scenario | Fault mechanism | What is tested |
|---|---|---|
| `clean` | No fault | Golden output; no alarm |
| `first_only` | First-round-engine fault | First/replay mismatch and reject |
| `replay_only` | Replay-round-engine fault | First/replay mismatch and reject |
| `dual_identical` | Same bit in same round in both | Same *wrong* result; no mismatch |
| `dual_different` | Different pre-round faults in both | Mismatch and reject in the test set |
| `checkpoint_shared` | Common checkpoint corruption | Both executions agree on a wrong result |
| `checkpoint_replay` | Replay checkpoint corruption | Mismatch and reject |
| `suppress_replay_alarm` | Replay fault + comparison override | Mismatch masked; wrong replay output released |
| `suppress_first_alarm` | First fault + comparison override | Mismatch masked; **clean replay** output released |
| `first_invalid_bit` | 320 (outside 0..319) | No injection |
| `replay_invalid_round` | 15 (outside p[8]/p[12]) | No injection |
| `checkpoint_invalid_bit` | 320 (outside state) | No injection |

**Important:** an identical fault affecting both passes is **not** the same event as a single transient fault; it deliberately violates the single-fault model. Shared checkpoint corruption happens before either pass. Comparator suppression is an intentionally instrumented *logical* failure, not a demonstrated physical glitch.

## Integrity, inference and report interpretation

`silent_corruption` means only **a permutation result was released even though it differed from the fault-free Python permutation**. It does **not** mean an AEAD tag was accepted, ciphertext authentication bypassed, or secret key recovered. This phase contains no decryption or recipient-side tag-verification experiment.

We expect the Python model to produce 60 `silent_corruption` classifications in 240 deterministic cases (20 each for dual-identical, shared-checkpoint, and replay-fault-plus-suppressed-alarm). This number is a **software prediction**, not an observed RTL measurement until the Verilator test passes. The scenario design is not a statistically sampled physical fault distribution; do **not** compute an attack success probability from 60/240.

The suite checks expected hit flags, raw mismatch, alarm, output-valid policy, zeroization at invalid output, complete 320-bit results, and stable DONE pulses against the Python oracle, **before** accepting a CSV as experimental evidence.

## Reproduce on the existing Mac setup

Extract the Phase 7A zip at the repository root, preserving the directory layout:

```bash
unzip -n ~/Downloads/faultscope_ascon_phase7a.zip
uv run python -m pytest tests/test_phase7_adversarial.py -v
uv run python -m pytest tests/ -q
uv run python -m experiments.run_phase7 --out reports/phase7_adversarial.csv
```

Expected tests: 3 new tests; combined with the prior 35-test baseline this becomes **38 passing tests** if all checks pass. Do not replace any Phase 4B CSV or modify `reports/phase5/manifest.json`. Phase 7A CSV is separate evidence and does not automatically appear in the Phase 6A dashboard.

### Next possible research extension (not included)

A separate **Phase 7B** can instrument the AEAD controller to route an adversarial permutation result into the ciphertext/tag path and enforce a fail-closed policy. That is needed before stating conclusions about any **AEAD output**. Physical equipment-based fault resistance remains out of scope.
