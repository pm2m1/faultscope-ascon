# Phase 10C-A — Bounded sequential controller verification (pilot)

## Goal and proof boundary

Phase 10B proved only the two **combinational** output mask assignments extracted from `rtl/ascon_aead_encrypt_temporal.sv`. Phase 10C-A checks a **bounded sequential execution** of the actual, unchanged AEAD controller FSM.

The script `experiments/phase10c_sequential.py` converts the *actual* `rtl/ascon_aead_encrypt_temporal.sv` via `sv2v` and constructs a formal top module. **Only** the child instance of `ascon_permutation_temporal` is replaced with a symbolic stub, so the outer controller's state machine, output latches and guard conditions are still taken from the original source. The stub's `done`, `fault_detected`, `fault_fired`, `state` and `busy` are independently unconstrained at every step.

This is an **over-approximation** of the permutation interface. For a safety property, an over-approximation can be useful: no counterexample even with arbitrary child outputs is evidence for the controller boundary. However, it is NOT a proof of the permutation engine, correct Ascon computation, temporal fault detection, realistic handshakes, physical attack resistance or properties after the selected depth. The stub can produce impossible sequences and still be permitted by the verification model.

## Properties (checked at every modeled clock in a bounded SAT run)

| Property | Condition | Important interpretation |
|---|---|---|
| Invalid output masking | `!result_valid_o -> ciphertext_o == 0 && tag_o == 0` | Includes interim data stored internally; external ports remain zero |
| Latched alarm inhibits validity | `fault_detected_o -> !result_valid_o` | Does not show a fault will raise an alarm |
| Busy inhibits validity | `busy_o -> !result_valid_o` | Existing valid results persist after a clean completion until a new accepted start; they are not required to disappear immediately when idle |
| Done implies idle | `done_o -> !busy_o` | Applies at the externally sampled clock boundary |
| Done is a pulse | `prev_done -> !done_o` | Two-cycle safety monitor |
| Reset safety | After a modeled reset edge, externally visible outputs, alarm, done, busy and validity are zero | The first modeled cycle has asserted reset; no arbitrary power-up security claim |

The reset generator begins asserted and deasserts after the first clock. The run uses Yosys `sat -seq N -set-init-zero` and therefore assumes initialized state in the bounded model in addition to the explicit reset. Inputs to the AEAD top, including keys, lengths, start and fault configuration, are unconstrained at each time step. Invalid lengths are handled by the original RTL. No fairness/liveness constraints require the permutation stub to finish; the tool makes **no termination guarantee**.

## Non-vacuity and negative controls

A passing proof of `policy_ok` alone is not enough to know that interesting paths were exercised. The runner requires explicit SAT **witnesses** for both:

- `cover_clean`: completion with `done_o=1`, `result_valid_o=1`, and no latched alarm.
- `cover_alarm`: completion with `done_o=1`, `fault_detected_o=1`, and `result_valid_o=0`.

It also converts two **mutated copies of the actual RTL**, never changing the real source:

1. `mutant_leak` removes the external ciphertext validity gate.
2. `mutant_alarm_bypass` disables the `FINAL_WAIT` fail-closed branch.

Both must produce explicit `SAT proof finished - model found: FAIL!` counterexamples. A Yosys error, timeout, missing verdict, or unexpected zero/nonzero return code is a **failure**, not a successful negative control. Unlike the positive run, counterexample-seeking SAT commands **do not use `-verify`** for Ubuntu Yosys 0.33 compatibility.

## Installation and local execution

Unzip the 10C-A patch at the project root; the three files are additive. Keep your committed RTL and all Phase 4B/7A/7B evidence unchanged.

```bash
cd ~/Projects/faultscope-ascon
uv run python -m pytest tests/test_phase10c_sequential.py -v
uv run python -m experiments.phase10c_sequential \
  --steps 18 \
  --out-dir build/reproduction/phase10c
```

**Stop if any step fails.** The first Python test run deliberately skips the expensive Yosys test unless `FAULTSCOPE_RUN_PHASE10C_FORMAL=1` is set. After the standalone solver command succeeds, optionally run the gated test:

```bash
FAULTSCOPE_RUN_PHASE10C_FORMAL=1 \
  uv run python -m pytest tests/test_phase10c_sequential.py -v
uv run python -m pytest tests/ -q
```

This reruns the solver inside pytest and can take extra time. Output files are written only to Git-ignored `build/reproduction/phase10c/`: generated converted Verilog, symbolic permutation stub, proof logs, mutated RTL variants and `phase10c_result.json` containing bound, tool versions and source SHA-256.

Run *before* any commit or CI modification. Version-specific syntax/solver behavior is possible; the initial runner has not yet been verified against macOS Yosys 0.69 or Ubuntu Yosys 0.33.

## Scientific interpretation

If this run succeeds, report: **"18-clock bounded SAT safety analysis of the actual AEAD controller with an unconstrained temporal-permutation child and explicit initial reset; clean and alarmed completion witnesses, two source-level negative-control counterexamples."**

Never shorten this to "Ascon hardware formally proven secure." In particular, this work does not prove fault detection coverage, full state-space correctness, authentication acceptance, all possible transaction lengths/completions, or unbounded behavior. A clean run also does not prove that a physical device is fault resistant.

## Next steps after acceptance

After confirming the logs on the Mac, add this pilot as a dedicated CI job (or an opt-in `workflow_dispatch` job), test on Ubuntu's older Yosys, and examine any counterexamples. Extend the model toward fair permutation completion and actual temporal-permutation constraints, then consider inductive/unbounded proofs. Keep these experiments separate from Phase 10B's already-green CI until cross-version behavior is validated.
