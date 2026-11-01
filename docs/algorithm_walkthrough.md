# Algorithm Walkthrough

The dark-themed website has two top-level pages: the Research Dashboard and Algorithm Walkthrough. Hash navigation needs no routing service or additional runtime dependency. The dashboard remains mounted while the walkthrough is open, retaining its filters and Learning Lab state.

## Run locally

From the repository root, install locked dependencies:

```powershell
uv sync --locked --group dev
npm.cmd --prefix frontend ci
```

Use separate terminals, both starting at the repository root:

```powershell
uv run uvicorn backend.api:app --host 127.0.0.1 --port 8000
```

```powershell
npm.cmd --prefix frontend run dev
```

- Dashboard: http://127.0.0.1:5173/#/
- Walkthrough: http://127.0.0.1:5173/#/walkthrough
- Recorded results: http://127.0.0.1:5173/#/results

The API reads fixed, hash-checked historical evidence. Browser encryption/decryption and fault illustrations also work when the API is unavailable; unavailable research results are never replaced with fallback measurements.

## What runs in the browser

`frontend/src/asconAeadTrace.ts` implements pure byte-oriented NIST Ascon-AEAD128 encryption, authenticated decryption and real state-transition traces. It reuses the existing `asconTrace.ts` permutation. The UI limits plaintext and associated data independently to 0-16 UTF-8 bytes. The pure byte functions support the longer official known-answer vector lengths.

The form accepts plaintext, public associated data, a 16-byte key and a 16-byte nonce. Advanced inputs accept exactly 32 hexadecimal digits, with optional spaces. The fixed key and nonce are explicitly DEMO values. Do not reuse a nonce with a real key or use this educational implementation for production secrets.

Every encryption freezes its input snapshot. Changing any input stops playback and clears the prior trace/receiver result. No keys, plaintext or decrypted content are written to URLs, local/session storage, logs or telemetry, or sent to the evidence API. Copy buttons write only the selected output to the clipboard.

The eight-step trace shows preparation, initialization, p[12], AD absorption, domain separation, message encryption, finalization and final output. Round explorers reveal actual constant-addition, substitution and diffusion values. Byte-XOR rows come from the computation, not illustrative substitute data.

The receiver reconstructs its state from the received ciphertext and recomputes the tag. It returns plaintext only after authentication succeeds; it does not compare against a cached expected plaintext. A rejected result has no released plaintext. JavaScript execution is not claimed constant-time or side-channel hardened.

## Algorithm conventions

- Five 64-bit words; 320-bit state; 16-byte rate.
- Initial state `(IV,K0,K1,N0,N1)`, with `IV=0x00001000808c0001` and little-endian words.
- Initialization p[12], then key XOR into x3/x4.
- Nonempty AD: each full block gets p[8], then a required padded tail and p[8]. Exactly 16 bytes needs a separate padding-only block. Empty AD skips its absorption, padding and permutations.
- Domain separation: `x4 ^= 1 << 63`.
- Full plaintext blocks emit rate XOR plaintext, update the rate and run p[8]. The final tail always receives `01` padding, including an empty tail. No p[8] follows that final tail.
- Finalization: key XOR into x2/x3, p[12], key XOR into x3/x4; extract the tag little-endian.

These conventions match `reference/ascon_aead.py` and the pinned standardized Ascon-C vectors. They must not be confused with older Ascon v1.2 byte-order/IV conventions.

## Reproducible HELLO example

| Input/output | Value |
|---|---|
| Message | `HELLO` |
| Associated data | `Course: CNS` |
| Synthetic key | `000102030405060708090a0b0c0d0e0f` |
| Synthetic nonce | `101112131415161718191a1b1c1d1e1f` |
| Ciphertext | `a0b29b6679` |
| Tag | `38a5911ee12bb09077fdc926a45cae30` |

Click Encrypt My Message, jump to the XOR and final-output steps, then Verify & decrypt. Both Tamper With Message and Tamper With Tag reject modified data. Reset received data restores the original authenticated message.

## Fault illustration boundary

The six scenarios use `compareReplay` on one p[12] permutation: clean, first-pass fault, replay fault, identical faults, shared-checkpoint corruption and alarm suppression. The displayed golden/first/replay words and flags are actual browser calculations. This is not the complete protected AEAD datapath, a live Verilator experiment, physical fault injection, key recovery, RTL decryption or a successful forgery.

The final project bridge links to the dashboard for historical measured findings. Raw research hashes and full experimental tables stay on the dashboard.

## Tests and reproduction

Restore `references/ascon-c` at `docs/ascon_reference_commit.txt` as described in README. Then run:

```powershell
uv run python -m pytest tests/test_algorithm_walkthrough.py tests/test_aead.py tests/test_phase8b_lab.py tests/test_dashboard_api.py tests/test_phase8a_research_api.py tests/test_phase5_analysis.py -q
npm.cmd --prefix frontend run build
$env:FAULTSCOPE_TEST_PYTHON = (uv run python -c "import sys; print(sys.executable)").Trim()
npm.cmd --prefix frontend run test:ui
```

Windows defaults to installed Edge. Linux defaults to Playwright Chromium; install it from `frontend` with `npx playwright install --with-deps chromium`. Each browser run uses a new ignored directory under `build/reproduction/website_ui/`. Set `FAULTSCOPE_UI_OUTPUT` to choose a separate explicit directory. Existing screenshot collections are not test-output destinations.

Reference tests cover all 1,089 official vectors, decryption/tampering, all 16 boundary pairs from `{0,1,15,16}`, every permutation round layer, UTF-8 validation, wrong key/nonce/AD and truncated tags. Browser tests cover navigation, snapshot resets, playback, copy, receiver behavior, rounds, fault scenarios, offline evidence, keyboard access, responsive layouts and the dark theme.

Earlier local implementation validation recorded 54 reference/API tests and 16 Edge tests passing. Release validation adds an explicit dark-theme regression and exact HELLO browser assertions. Current CI logs are the authority for current execution counts; historical results are not rewritten.

No RTL, reference, campaign, formal, synthesis or FPGA evidence changes are required by this feature. The original pixel-identical dashboard fixture belonged to the initial navigation-only review; the subsequently requested showcase intentionally changes dashboard presentation while retaining its behavior and data. That obsolete fixture is not an active release test.
