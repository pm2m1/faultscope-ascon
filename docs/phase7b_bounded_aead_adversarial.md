# FaultScope-Ascon — Phase 7B: AEAD-level adversarial temporal replay

## Goal and scope

This **research-only** extension carries Phase 7A's independent first/replay
pre-round state-bit flips, shared/replay-only checkpoint corruption, and
comparator-alarm suppression into the **bounded Ascon-AEAD128 encryption-and-tag
controller**. It must not be interpreted as a physical fault attack, secure
hardware design, decryption functionality, or an AEAD authentication bypass.

Files are additive: none of Phase 3B (baseline), Phase 4B (clean replay), or
Phase 7A (permutation stress test) implementations are replaced.

## Architecture

`ascon_aead_encrypt_adversarial` uses the verified bounded AEAD state machine
from `ascon_aead_encrypt_temporal`, substituting `ascon_permutation_adversarial`
for the clean-replay temporal permutation. An adversarial configuration is
latched on transaction start, targets a single selected Ascon phase, and is
inert in all other permutation invocations.

Phase selector:

- `0`: initialization p[12]
- `1`: associated data p[8] when AD length > 0
- `2`: final padding p[8] when AD length == 16
- `3`: message full-block p[8] when plaintext length == 16
- `4`: finalization p[12]

Input bus bytes are packed little-endian. Key, nonce, message, associated data
are supplied in the same format as the Phase 3B and Phase 4B testbenches.
Maximum plaintext length and AD length are each **16 bytes**. One transaction
is processed at a time.

The instrumented permutation's result is *the replay output*. A raw mismatch
with an intact comparator raises `fault_detected_o`. The bounded AEAD
controller accumulates the event flags and alarm over all permutations. The
external 128-bit `ciphertext_o` and `tag_o` ports are always zero until the
final `result_valid_o` assertion; any raised alarm suppresses both outputs.

The `suppress_alarm_i` input deliberately models a *compromised comparator*
for one selected phase. A raw mismatch is still observable, but an alarm can
be suppressed. This is intentionally **not a secure countermeasure**.

## Experiment and oracle

`reference/ascon_aead_adversarial_model.py` independently implements the
bounded AEAD phase transitions, applying the already-verified Phase 7A
permutation-fault oracle at each permutation call. It compares final released
ciphertext/tag bytes against the official-KAT-verified `reference.ascon_aead`
implementation. Invalid output ports are modeled as zero by the RTL testbench.

`experiments/run_phase7b.py` builds **600 deterministic cases**:

- 10 `(ad_len, msg_len)` combinations, including empty, partial, and exactly
  16-byte boundaries
- 5 AEAD permutation phases each
- 12 scenarios each, including clean, single-pass, dual-identical,
  dual-different, both checkpoint modes, comparator override, and invalid
  targets

The testbench asserts that:

1. The RTL observes each expected injected fault event, comparator raw
   mismatch, and alarm state.
2. Ciphertext and tag match the independent Python adversarial oracle on
   every case, byte-for-byte, including output suppression.
3. No ciphertext, tag, or output-valid signal is exposed before `done_o`.
4. An actual alarm prevents externally valid ciphertext/tag release.
5. If output is externally valid but either ciphertext or tag differs from
   golden, the case is classified as an **incorrect release**, not an
   authentication bypass.
6. Unreachable/inert injection requests do not produce false alarms.
7. The `done_o` completion pulse is one cycle wide.

The primary CSV contains **RTL-observed** results. The runner stops with a
failure if Verilator is unavailable or any RTL measurement differs from its
oracle: it never fabricates software-only simulation rows.

## Commands

```bash
cd ~/Projects/faultscope-ascon
unzip -n ~/Downloads/faultscope_ascon_phase7b.zip
uv run python -m pytest tests/test_phase7b_aead_adversarial.py -v
uv run python -m pytest tests/ -q
uv run python -m experiments.run_phase7b --out reports/phase7b_aead.csv
```

Assuming Phase 7A is already installed, the total pytest count should increase
from **38 to 41**. Check Verilator compilation and RTL comparison on the Mac;
these have not been executed in the package-authoring environment.

After successful verification, commit the six source/docs files and then the
CSV separately. Existing `.gitattributes` includes `reports/*.csv -text`;
verify staged and working CSV SHA-256 hashes are identical before committing.

## Honest interpretation

An earlier Phase 4B experiment reported 93/93 detected *single first-pass
state-bit faults* with clean replay. Phase 7A stressed permutation-level
adversarial conditions. Phase 7B checks how those conditions influence a
bounded encryption datapath's **observable ciphertext, tag, and validity
signals**. Silent corruption here means externally valid ciphertext/tag
that disagree with the verified AEAD encryptor. It does **not** demonstrate
that a receiver accepted a forged message, that authenticated decryption was
compromised, or that an attacker can cause the simulated hooks physically.

The scenarios are deterministic and deliberately selected, not a statistical
sample from a real-world physical fault distribution. No physical clock,
voltage, thermal, or electromagnetic attack data was collected.
