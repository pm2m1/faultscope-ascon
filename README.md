# FaultScope-Ascon

**Pre-silicon fault-injection, temporal-recomputation evaluation, and interactive visualization for NIST Ascon-AEAD128.**

FaultScope-Ascon is an educational and experimental cryptographic-hardware security workbench. It combines an independently checked Ascon reference implementation, synthesizable SystemVerilog, deterministic Verilator fault campaigns, a temporal-recomputation countermeasure, generic Yosys synthesis measurements, and a local React/FastAPI dashboard.

**Project status (verified on macOS, October 2026):** 48 pytest cases passed and the Vite production build succeeded. The results below are measurements of specified **digital simulation models**, not physical attack success probabilities.

## Motivation and contributions

Re-executing a cryptographic permutation and comparing the two results can detect faults—provided the original execution can be compared with an uncompromised replay, checkpoint, and comparator. This project studies both the benefits and the limits of that assumption.

- Implements Ascon p[8]/p[12], a software Ascon-AEAD128 reference, and bounded **encryption/tag-generation RTL** (0–16 bytes each of plaintext and associated data).
- Validates the software reference against the official Ascon-C known-answer tests (KATs) and validates RTL behavior against the software model.
- Injects controlled single-bit pre-round state faults and tests a temporal-recomputation detector.
- Extends the study to first-pass, replay, identical dual-execution, checkpoint, and comparator-suppression fault hooks.
- Measures simulation cycles and generic synthesis-cell counts; presents evidence through a read-only dashboard and a separately computed educational Ascon lab.

This is a **systematic evaluation workbench**, not a newly invented cipher or a claim of the first fault attack on Ascon.

## Algorithm in brief

Ascon-AEAD128 is a NIST-standardized authenticated-encryption-with-associated-data (AEAD) algorithm (NIST SP 800-232). It processes a 320-bit permutation state as five 64-bit words, `x0`–`x4`. Each permutation round applies a round constant, a nonlinear substitution layer, and linear diffusion. The project models both `p[12]` and `p[8]` and the encryption workflow: initialization, associated-data absorption, domain separation, message processing, and finalization/tag generation.

AEAD encrypts the message and produces a tag tied to the key, nonce, ciphertext, and associated data. **Nonce reuse with the same key must be avoided.** The Python reference includes authenticated decryption for testing; the project's **hardware datapath is encrypt-and-tag only**, not an RTL authenticated-decryption engine.

## Architecture

```text
Official Ascon-C KATs ──► Python Ascon oracle ──► reference/ tests
                              │                         │
                              ▼                         ▼
                    Bounded Ascon AEAD RTL ◄──── Verilator testbenches
                              │                         │
                   Faultable permutation       Temporal replay / fault hooks
                              │                         │
                              └──────────┬──────────────┘
                                         ▼
                       Recorded CSV campaigns + Yosys analysis
                                         │
                              Hash-verified FastAPI
                                         │
                       React research dashboard + Ascon lab
```

The educational browser lab computes permutation traces locally using TypeScript `BigInt`. Its outputs and fault animations do **not** modify the recorded experimental CSV files.

## Verified results and interpretation

| Campaign | Configured scenarios | Recorded observations | What the result does **not** establish |
|---|---:|---|---|
| Phase 4B: single first-pass transient state-bit flip, clean replay | 424 | 93 applied faults; **93 detected**; zero alarms among 331 no-injection cases | Detection under physical, correlated, or repeated faults |
| Phase 7A: adversarial permutation-level hooks | 240 | **120** raw mismatches, **80** alarms, **60** silent incorrect permutation-state releases | An AEAD authentication bypass or real-world exploit probability |
| Phase 7B: adversarial bounded AEAD hooks | 600 | **204** raw mismatches, **136** alarms, **102** incorrect ciphertext/tag releases | Accepted forgeries or recipient-side tag-verification bypass |

The scenario categories **overlap** and the three campaign populations have different fault models. Do not sum their alarm/mismatch/incorrect-release counts or calculate a combined detection rate. The 60 and 102 incorrect-release counts are observed under deliberately selected adversarial fault hooks, including shared faults and simulated comparator suppression; they are not random physical-fault samples.

### Phase 5 implementation cost

The same `sv2v` → Yosys (`synth -flatten -noabc`) flow was used for three architectural variants:

| RTL variant | Generic cells | FF output bits |
|---|---:|---:|
| Baseline, no fault ports | 8,277 | 1,625 |
| Fault-instrumented | 9,865 | 1,659 |
| Temporal-recomputation protected | 12,863 | 2,645 |

Protected vs. baseline: **+55.41% generic cells**. The Phase 4B campaigns measured mean **47.17 baseline cycles** versus **95.64 protected cycles** (**+102.77%**). Generic cells are neither FPGA LUT utilization nor physical area, and cycle counts alone do not determine clock period, throughput, energy, or power. See `reports/phase5/REPORT.md` for the exact methodology and limitations.

## Repository layout

```text
backend/                  Read-only FastAPI evidence endpoints
frontend/                 React / TypeScript / Vite research dashboard and Ascon lab
reference/                Python Ascon, fault, and adversarial oracles
references/ascon-c/        Upstream reference clone; intentionally ignored by Git
rtl/                      SystemVerilog permutation, bounded AEAD, and fault fixtures
tb/                       Verilator SystemVerilog testbenches and C permutation oracle
experiments/              Phase 4A, 4B, 5, 7A, 7B campaign runners
tests/                    Python, RTL, API, and TypeScript-oracle comparisons
reports/                  Committed CSV measurements, synthesis summaries, and manifest
docs/                     Phase-specific design, methodology, and limitation notes
src/faultscope_ascon/     uv package scaffold (not the active dashboard entry point)
```

The generated Phase 5 `logs/` and `netlists/` may be preserved separately for auditing; they are not required to *view* the committed dashboard summaries. The repository's own license must be declared separately before reuse rights are assumed. Upstream Ascon-C is a separate third-party project with its own license.

## Reproducible setup (macOS / Apple Silicon)

### 1. Prerequisites

- **Python 3.12**, `uv`, `git`, and Apple's command-line `clang` (`xcode-select --install` if needed).
- **Verilator**, **Yosys**, **sv2v**, and **CMake** for hardware verification and synthesis.
- **Node.js 22 or newer** and npm for the React build and the cross-language TypeScript tests.
- The committed `uv.lock` and `frontend/package-lock.json` are used to resolve the software environment.

On macOS with Homebrew, one way to install the non-Xcode tools is:

```bash
brew install uv node verilator yosys sv2v cmake
```

The recorded tool environment included Verilator 5.052, Yosys 0.69+post, sv2v 0.0.13, Python 3.12.14, and Node 24.20.0. Other versions may produce different synthesis structures or warnings. Run `verilator --version`, `yosys -V`, `sv2v --numeric-version`, `uv --version`, and `node --version` to record your environment.

### 2. Clone the project and restore the pinned upstream reference

The project's GitHub URL is not yet published here. Once a remote repository has been created, clone it using **its actual URL**. If already working in a local checkout, begin with `cd ~/Projects/faultscope-ascon` instead.

```bash
# Run from the parent directory of your checkout, after creating a remote:
# git clone <YOUR-REPOSITORY-URL> faultscope-ascon
cd faultscope-ascon

mkdir -p references
git clone https://github.com/ascon/ascon-c.git references/ascon-c
git -C references/ascon-c checkout --detach "$(cat docs/ascon_reference_commit.txt)"

# The restored upstream revision MUST equal the committed pin.
test "$(git -C references/ascon-c rev-parse HEAD)" = "$(cat docs/ascon_reference_commit.txt)"
```

The reference commit is **`446347f21b209f3921c65ece70027c366cbe1693`**. This step is essential: tests load `references/ascon-c/crypto_aead/asconaead128/LWC_AEAD_KAT_128_128.txt` and compile against `references/ascon-c/crypto_aead/asconaead128/ref/`. The clone itself stays ignored, and should **not** be copied into your own repository.

### 3. Install Python and frontend dependencies

From the repository root:

```bash
uv sync --locked --group dev
cd frontend
npm ci
cd ..
```

For the fresh-clone installation to work, `src/faultscope_ascon/__init__.py` and `.python-version` must be tracked in your own Git repository (they were untracked during the Phase 9A audit). The generated `faultscope-ascon` console-script entry currently prints a placeholder message; **do not use it** as the dashboard launcher.

### 4. Verify the full project

```bash
uv run python -m pytest tests/ -q
cd frontend && npm run build && cd ..
```

At the documented development revision, the result was **48 passed, 1 non-failing Starlette/httpx deprecation warning**, plus a successful TypeScript/Vite production build. The pytest suite includes official KAT checks, Python-to-C comparison, Verilator hardware simulations, adversarial-model checks, evidence-API integrity checks, and a Python-to-TypeScript permutation comparison. A pass on another machine must be confirmed by running the commands; it is not guaranteed by the stored historical result.

### 5. Launch the local research dashboard

Start **two terminals**, both from the project checkout:

```bash
# Terminal 1 — FastAPI
uv run uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2 — Vite
cd frontend
npm run dev
```

Open <http://127.0.0.1:5173>. The frontend proxies `/api` to `http://127.0.0.1:8000`.

The web UI offers original evidence overview, phase comparison, experimental ledger, adversarial research, and the interactive Ascon learning lab. Research API entry points include `/api/summary`, `/api/cases`, `/api/research/summary`, and `/api/research/cases`.

## Evidence integrity and safe reruns

**Never overwrite committed experimental CSVs simply to check reproducibility.** The backend explicitly rejects changed Phase 4B/7A/7B evidence hashes, rather than displaying mismatched metrics. The Phase 5 manifest pins the Phase 4B CSV, upstream reference, source hashes, analysis-time tool versions, and analysis Git commit; the stored `git_commit` is historical provenance, **not** a requirement to equal today's `HEAD`.

Check the pinned data without altering it:

```bash
uv run python - <<'PY'
import hashlib, json
from pathlib import Path
from backend.research import CAMPAIGNS

manifest = json.loads(Path('reports/phase5/manifest.json').read_text())
expectations = {
    'reports/phase4b_temporal.csv': manifest['campaign_sha256'],
    **{cfg['path']: cfg['sha256'] for cfg in CAMPAIGNS.values()},
}
for path, expected in expectations.items():
    actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    print(('PASS' if actual == expected else 'FAIL'), path, actual)
    if actual != expected:
        raise SystemExit(1)
PY
```

For **new experimental runs**, generate their outputs in Git-ignored `build/` rather than replacing the committed evidence:

```bash
mkdir -p build/reproduction
uv run python -m experiments.run_phase4b --out build/reproduction/phase4b_temporal.csv
uv run python -m experiments.run_phase7 --out build/reproduction/phase7_adversarial.csv
uv run python -m experiments.run_phase7b --out build/reproduction/phase7b_aead.csv

# Optional: time/resource-intensive generic synthesis comparison
uv run python -m experiments.run_phase5 \
    --campaign reports/phase4b_temporal.csv \
    --out-dir build/reproduction/phase5
```

The CPU time, compiler version, synthesis output, absolute paths, and report timestamps may differ across environments; if reporting numerical comparisons, document those differences. To compare deterministically generated campaign CSV bytes with committed evidence, use `shasum -a 256` on the corresponding old/new files and inspect any mismatch instead of updating pinned hashes automatically.

Phase 5 outputs include `logs/` and `netlists/` and may occupy tens of megabytes. Preserve them as an optional audit archive, not as prerequisites for viewing the recorded dashboard results.

## Threat model, limitations and security claims

1. The experiments are **pre-silicon digital simulations** using explicit fault-injection hooks, not laser, EM, voltage, or clock-glitch experiments.
2. Phase 4B assumes a **single first-execution state-bit fault** with a clean replay, checkpoint, and comparator. Its 93/93 result applies only to that subset.
3. Phase 7A examines adversarial **permutation** output; Phase 7B examines bounded **encryption and tag generation** output. Neither tests physical reliability or successful recipient-side forgery acceptance.
4. `incorrect_release` is a specific model classification: valid output differs from the fault-free reference, **not** authenticated-decryption bypass.
5. Correlated dual faults and simulated alarm suppression deliberately violate Phase 4B's protection assumptions; these hooks are **testing instrumentation**, not functionality to ship in secure hardware.
6. Hardware evaluation uses generic Yosys cells. No place-and-route, fixed target FPGA LUT utilization, silicon area, timing closure, physical power, or attack equipment evaluation has been demonstrated.
7. This code is a teaching and research prototype. It has not received an independent production security audit and should not protect real confidential data or manage production keys.

## Reference materials and provenance

- [NIST SP 800-232 — Ascon-based Lightweight Cryptography Standards](https://csrc.nist.gov/pubs/sp/800/232/final)
- [Official Ascon-C implementation repository](https://github.com/ascon/ascon-c), pinned in [`docs/ascon_reference_commit.txt`](docs/ascon_reference_commit.txt)
- [`docs/phase4b_temporal_recomputation.md`](docs/phase4b_temporal_recomputation.md)
- [`docs/phase5_hardware_cost_evaluation.md`](docs/phase5_hardware_cost_evaluation.md)
- [`docs/phase7a_adversarial_temporal.md`](docs/phase7a_adversarial_temporal.md)
- [`docs/phase7b_bounded_aead_adversarial.md`](docs/phase7b_bounded_aead_adversarial.md)
- [`docs/phase8a_unified_dashboard.md`](docs/phase8a_unified_dashboard.md)
- [`docs/phase8b_ascon_learning_lab.md`](docs/phase8b_ascon_learning_lab.md)

**Attribution:** The project uses the official Ascon-C upstream implementation as a separately pinned verification reference. This project does not claim ownership of upstream reference code or of the NIST Ascon standard. The project's own licensing and release decision should be made explicitly before publishing the repository.
