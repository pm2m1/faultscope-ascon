# Phase 4A — Deterministic RTL transient single-bit fault injection

## Scope

- Fault instrumentation is in **separate RTL modules** so the verified Phase 3B baseline is left unchanged:
  - `ascon_permutation_faultable.sv` — injects one XOR bit mask into the **input of exactly one permutation round**.
  - `ascon_aead_encrypt_faultable.sv` — uses the instrumented permutation controller, selects the desired AEAD phase, and reports whether injection actually fired.
- Inputs/key/nonce/associated data/message remain bounded as in Phase 3B: 0..16-byte message and 0..16-byte AD, encryption/tag generation only.
- No FPGA device, physical power/EM/voltage injection, timing fault, stuck-at model, cryptographic auth bypass, or protection scheme is claimed.
- Injection is deterministic at one selected **permutation phase**, **zero-based round number**, and **bit in the 320-bit permutation state**.
- A fault mask XOR is applied immediately **before** the selected round's combinational Ascon transformation. This fault changes the round input for one cycle. It is not a transient bit flip applied after that round; it does not randomly decay. The altered state can propagate into subsequent rounds.

### Configuration and bit ordering

- `fault_enable_i`: 0 = disabled; 1 = armed.
- `fault_phase_i`:
  - `0` initialization p[12]
  - `1` first AD p[8] (present only when AD length > 0)
  - `2` final padding p[8] after **exactly 16-byte AD**
  - `3` p[8] after **exactly 16-byte plaintext**
  - `4` finalization p[12]
- `fault_round_i`: 0..11 for p[12], 0..7 for p[8], zero-based within the selected permutation invocation.
- `fault_bit_i`: 0..319, referring to RTL concatenated state `{x0,x1,x2,x3,x4}`; bit 0 is the LSB of x4, bit 319 the MSB of x0.
- Invalid, disabled, or unreachable targets must **not** trigger `fault_applied_o`.
- `fault_applied_o`: sticky result for the current AEAD request; cleared when the next valid transaction is accepted. It records injection occurrence, **not fault detection or a security alarm**.

## Test methodology

- The verified Python Ascon-AEAD128 reference provides fault-free ciphertext and tags.
- New `reference/ascon_fault_model.py` independently computes the **expected faulted result** at each injected state, phase and round. This checks *where and when* the RTL injection happens, not merely that its output differs.
- Every test vector first runs **unarmed** and is checked against the original verified reference; it then runs **armed** and is checked against the software fault model.
- Both `fault_applied_o` and ciphertext/tag are checked, alongside completion, bounded timeouts, and identical cycles between unarmed and armed cases.
- Tests exercise all 5 phases, first/intermediate/last rounds, varied bit positions, absent phases, invalid round/bit selectors, and disabled injection.
- Full campaigns are run twice by pytest to verify deterministic replay.
- CSV results distinguish ciphertext changes from authentication-tag changes. A change in the produced authentication tag is **not** equivalent to a successful forgery or authentication bypass at a receiver. A later receiving-side verification model must be added before classifying such an outcome.

## Commands

First unzip the package **from the repository root**. It adds files only and should not replace existing ones.

```bash
uv run python -m pytest tests/test_rtl_fault_injection.py -v
uv run python -m pytest tests/ -v
uv run python -m experiments.run_phase4a --out reports/phase4a_faults.csv
```

The default test runs a bounded campaign with a fixed seed. The standalone runner writes a deterministic CSV to `reports/phase4a_faults.csv`, which should be preserved as a reproducible experiment artifact. It includes each tested phase, round, bit index, whether the injection fired, ciphertext change, tag change and latency.

## Verification gate

This package's Python fault model was locally checked for fault-enabled/disabled behavior over 289 message/AD length pairs. The RTL **must still pass Verilator on the user's machine**; do not declare the fault-injection milestone verified or commit it before the test passes.

If a test fails, preserve the complete simulator/build output and fix the first failing case rather than weakening the assertions.

## Next milestone

Phase 4B will freeze a precise threat model and add a receiving-side tag-verification experiment, potentially including a separately protected RTL variant for one countermeasure. Distinguish fault **injection**, fault **detection**, fault **propagation**, output corruption, and successful authenticated acceptance as separate outcome categories.
