# Phase 10B — Independent Yosys CI and output-gate SAT assurance

## Why this phase exists

Phase 10A's passing GitHub checks run Python, Verilator, the read-only evidence verifier, and the Vite build. **They do not run Yosys.** Phase 10B adds a separate Ubuntu synthesis/limited-formal job without editing the RTL modules, original campaigns, or historical Phase 5 measurements.

## What the new GitHub job actually does

1. Checks out the committed source on `ubuntu-24.04`.
2. Installs distribution Yosys and the `sv2v` v0.0.13 Ubuntu release binary.
3. Verifies the SHA-256-pinned historical campaigns, original seven RTL sources, and recorded Ascon-C reference revision string.
4. Extracts the **two output assignments** from the actual `rtl/ascon_aead_encrypt_temporal.sv` and invokes Yosys SAT on the extracted *combinational* output-gating circuit.
5. Requires an intentionally broken ciphertext-masking assignment to yield a SAT **counterexample**. The formal step fails if there is a parser/tool failure rather than a genuine proof verdict.
6. Repeats the Phase 5 `sv2v → hierarchy -check → synth -flatten -noabc → check -assert → write_json` flow against all three RTL architectures in `build/reproduction/phase10b/`.
7. Excludes Yosys `$scopeinfo` metadata cells from the comparative logic-cell counts and reports overhead against **both** baseline and instrumented designs.
8. Uploads the generated `manifest.json`, synthesis logs and netlists, comparisons, and SAT logs as a **14-day Actions artifact**, even when a downstream step fails (if any files exist).

### SAT scope and assumptions

The proof is about *actual source-extracted continuous output assignments*, where `result_valid_o`, `ciphertext_q`, and `tag_q` are modeled as arbitrary defined inputs. It proves, independent of inputs:

- `!result_valid_o -> ciphertext_o == 0 && tag_o == 0`;
- `result_valid_o -> ciphertext_o == ciphertext_q && tag_o == tag_q`.

It does **not** prove that the RTL raises alarms correctly, reaches `done_o`, avoids deadlock, or keeps `result_valid_o` deasserted throughout all unsafe sequences. The Phase 10A Verilator assertions still test these protocol behaviors under finite, directed scenarios; that is **simulation**, not exhaustive formal verification of the full controller. The source extraction fails if output drivers are missing/duplicated.

The negative-control proof replaces the output mask **in a generated temporary harness only**, never in the original RTL.

## Historical resource accounting

`reports/phase5/synthesis_summary.json` was generated with Yosys 0.69+post and includes metadata `$scopeinfo` cells. The corrected *historical* values are:

| Top | Historical total | `$scopeinfo` excluded | Corrected generic logic cells | FF output bits |
|---|---:|---:|---:|---:|
| Baseline | 8,277 | 2 | 8,275 | 1,625 |
| Fault instrumented | 9,865 | 2 | 9,863 | 1,659 |
| Protected temporal replay | 12,863 | 3 | 12,860 | 2,645 |

Historical corrected overhead: protected/baseline **+55.4079%**, protected/instrumented **+30.3863%**.

The Ubuntu 24.04 Yosys package may differ from Yosys 0.69 used to record Phase 5. **No exact cell-count equality is required across tool versions.** The new report explicitly includes both tool versions, confirms the original RTL source hashes and synthesis flow, and lists per-architecture differences. Different generic-cell counts under different tool versions are not, by themselves, evidence of a security regression. No target ASIC library, FPGA device, placement, routing, static timing, power, or physical fault experiment is involved.

## Run locally on your Mac

From repository root (assuming `brew install yosys sv2v` has already been done):

```bash
uv run python -m experiments.phase10b_formal --out-dir build/reproduction/phase10b/formal
uv run python -m pytest tests/test_phase10b_analysis.py tests/test_phase10b_formal.py -v
uv run python -m experiments.run_phase5 \
  --campaign reports/phase4b_temporal.csv \
  --out-dir build/reproduction/phase10b
uv run python -m experiments.phase10b_analysis --out-dir build/reproduction/phase10b
cat build/reproduction/phase10b/phase10b_comparison.json
```

`build/` is already Git-ignored. **Do not run these commands with `--out-dir reports/phase5`**, which would overwrite committed evidence.

## Verify on GitHub

After committing and pushing the Phase 10B patch, open **Actions → Verify cryptography and dashboard** and select the new **Yosys synthesis, comparison, output-gate SAT** job. The job must be green independently of the two prior Phase 10A jobs. Open **Artifacts** from the successful workflow run to download the synthesis evidence, generated netlists, and proof logs. GitHub Actions uploaded artifacts expire after 14 days, so archive important evidence separately if needed.

## Important limitations / follow-up

- The CI job installs a version-tagged external `sv2v` binary; pinning its distribution SHA-256 would strengthen the supply-chain guarantee.
- The output-gate SAT proof operates on extracted actual RTL assigns, **not the entire 320-bit permutation/controller cone**. Follow-up formal work should prove reset, state-transition, alarm/valid gating, and liveness under explicit assumptions and bounded or induction-based strategies.
- Neither generic synthesis metrics nor an output-gate SAT proof demonstrates resistance to physical fault injection.
