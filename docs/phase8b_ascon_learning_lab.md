# FaultScope-Ascon — Phase 8B: Interactive cryptographic learning lab

## Objective

Extend the existing Phase 8A dashboard with a **local, deterministic educational visualization**. This is a presentation aid for cryptographic understanding, not a new cipher, cryptographic library, experimental measurement, receiver-side AEAD verifier, or physical-fault exploit tool. The Phase 8A research results and API are unchanged.

## Interface

A new sidebar destination, **Ascon learning lab**, scrolls to a new section below **Adversarial research**. It includes three interactive modules:

1. **Permutation rounds:** Enter five hexadecimal 64-bit words (`x0`–`x4`), or choose a preset. Choose p[8] or p[12] and play/step through **every** round's constant addition, nonlinear S-box, and linear diffusion, with full 320-bit state after each layer. Playback pauses on a manual step, can restart, and shows the current round constant. The implementation uses JavaScript `BigInt` with 64-bit masks and correct 64-bit rotations, and does **not** generate fake trace values.
2. **AEAD workflow:** Walk through initialization, associated-data absorption, domain separation, plaintext processing, and finalization/tag generation. This conceptual flow explains bounded AEAD without pretending to execute a complete encryption based on the five editable words. Full-block vs partial-block differences and nonce-use requirements are stated.
3. **Fault & defense:** Select a deterministic permutation-level model (no fault, first only, replay only, identical dual faults, shared/replay checkpoint, and comparator suppression). Choose round and 320-bit index. Step through checkpoint, first execution, replay, comparison and release policy, seeing the calculated golden, first and replay states and actual alarm/valid/incorrect-release classifications. Comparator override is *deliberately modeled as a fault*, never described as a secure feature.

The panels are local React state only. No new API endpoint or network request is introduced. The educational lab neither alters nor re-executes the recorded Phase 4B, 7A or 7B campaigns.

## Mathematics and bit indexing

The permutation uses the existing `reference/ascon_permutation.py` conventions (NIST SP 800-232): five unsigned 64-bit words; `x2 XOR RC`, 5-word bitsliced substitution, then `x_i XOR ROTR(x_i,a) XOR ROTR(x_i,b)` for `(a,b) = (19,28), (61,39), (1,6), (10,17), (7,41)` respectively. p[12] uses constants `F0,E1,D2,C3,B4,A5,96,87,78,69,5A,4B` and p[8] uses their final eight members. In the concatenated `{x0,x1,x2,x3,x4}` RTL representation, bit 0 is the least-significant bit of `x4`, bit 319 is the most-significant bit of `x0`.

The replay model is **permutation-level** and intentionally mirrors the selected fault conditions investigated in Phase 7A. It is not a time-accurate rendering of Verilator clocks, an AEAD ciphertext/tag validity proof, or a simulator for physical fault resistance.

## Verification

New test `tests/test_phase8b_lab.py` has three checks:

- All 8 and 12-round traces agree **at the end of every round** with the verified Python Ascon reference on 40 inputs. The round-constant step is independently checked.
- Eight replay scenarios are compared against an independent Python evaluation (12 initial-state/round combinations × 8 models = 96 comparisons).
- Hexadecimal input validation, RTL-compatible bit indexing at positions 0/319 and the all-zero p[8] state are cross-checked.

The tests call the locally installed Node.js binary (Node 22+ for native TypeScript type stripping). On the user's Mac, Node v24 is already installed. No new npm dependencies were introduced.

**Mac commands:**

```bash
cd ~/Projects/faultscope-ascon
cp frontend/src/App.tsx /tmp/faultscope-App-before-phase8b.tsx
cp frontend/src/styles.css /tmp/faultscope-styles-before-phase8b.css
unzip -o ~/Downloads/faultscope_ascon_phase8b.zip
uv run python -m pytest tests/test_phase8b_lab.py -v
uv run python -m pytest tests/ -q
cd frontend
npm run build
```

Existing full-suite result before this phase: 45 passing. The expected new total is **48 tests**, subject to verification on the target Mac. The Vite production build and browser interaction must be checked on the Mac; TSX transpilation alone is not a production build.

Run backend and frontend as usual in separate terminals, open `http://127.0.0.1:5173`, click **Ascon learning lab**, switch among the three tabs, play animations, edit lane inputs, compare a first-only fault with a dual-identical fault, and verify the research ledger is unchanged.

Commit only after test+build+browser verification:

```bash
git add frontend/src/App.tsx frontend/src/styles.css \
  frontend/src/AsconLab.tsx frontend/src/asconTrace.ts \
  tests/test_phase8b_lab.py docs/phase8b_ascon_learning_lab.md
git diff --cached --stat
git commit -m "Add verified interactive Ascon learning and fault replay lab"
```

## Important limits

The lab computes p[8]/p[12] accurately for educational inputs, but it does not encrypt with or store real keys, certify hardware resistance, measure power/timing/area, or demonstrate that a decryption recipient accepted a forged tag. The five-stage AEAD illustration is a conceptual sequence, whereas the round and replay views use deterministic calculated state values. The Phase 8A experimental data and their hash checks remain authoritative.
