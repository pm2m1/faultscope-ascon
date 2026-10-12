# Phase 3B: Bounded NIST Ascon-AEAD128 RTL, encryption only

## Scope / interface

- Synthesizable `ascon_aead_encrypt_bounded` module. Reuses the already verified
  `ascon_permutation` / `ascon_round` modules (no duplicate cipher core).
- 128-bit key and nonce; 0..16 bytes of associated data; 0..16 bytes of plaintext.
- `start_i` accepted only when idle and lengths <= 16. Output `ciphertext_o`
  contains up to 16 significant bytes, padded with zeroes, and `tag_o` is 16 bytes.
- All 128-bit input/output buses use **little-endian byte positions**:
  first byte at bits [7:0]. Internally permutation lanes are packed
  `{x0,x1,x2,x3,x4}` in descending bit significance.
- Encryption and tag generation only. **No RTL decryption or tag verification**;
  that extension must be implemented and tested separately.
- No fault injection, countermeasure, side-channel claim, FPGA timings or
  physical fault claim is part of this milestone.

## FSM phases

1. Capture key, nonce, message, associated data and lengths into registers.
2. Initialize 320-bit state (`IV`, K0, K1, N0, N1) and run p[12].
3. XOR the key into x3,x4.
4. If associated data is nonempty, absorb and pad it with p[8]. A full
   16-byte AD block gets an additional padded empty block and a second p[8].
5. Domain separation: toggle bit 63 of state word x4.
6. Encrypt message. Full 16-byte block uses p[8] followed by empty final
   padded block; a shorter final block uses padding without p[8].
7. Mix the key into x2,x3, run p[12], and produce tag x3||x4 after key XOR.
8. Pulse done_o once, hold ciphertext and tag until next accepted request.

## Test coverage

`tests/test_rtl_aead_bounded.py` creates all 17x17 possible length pairs
from 0 through 16, plus 48 deterministic extra vectors (337 total).
It uses the previously official-KAT-validated Python implementation as the
reference. The Verilator testbench verifies exact ciphertext and tag bits,
completion and a bounded timeout, and a one-clock done pulse.

## Run

```bash
uv run python -m pytest tests/test_rtl_aead_bounded.py -v
uv run python -m pytest tests/ -v
```

**Validation gate:** Do not declare RTL AEAD verified or commit this milestone
until the Verilator test passes. Both the Python reference and current RTL are
educational; test-vector agreement is not proof of general security.

## Next: Phase 3C / 4

Add hardware authenticated decryption/tag rejection with separate tests, or
freeze encrypt-only scope as the fault-study target if time is constrained.
Then add deterministic fault injection at chosen cycles to the RTL core, with
fault outcome classification and a fault-detection mechanism. For security
claims, define the adversary/fault model and recipient verification boundary.
