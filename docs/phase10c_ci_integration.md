# Phase 10C-B — Dedicated GitHub Actions verification

This workflow is intentionally separate from the existing `Verify cryptography and dashboard` workflow. Both run on pushes and pull requests to `main`; a failure in the bounded sequential pilot should not prevent the independent cryptography, Verilator, frontend, or Yosys synthesis results from being seen.

Workflow: `.github/workflows/sequential-formal.yml`.

## Acceptance conditions

1. On Ubuntu 24.04, install Yosys from Ubuntu's package repository, and sv2v 0.0.13 from its pinned upstream release. Record tool versions in the generated report. This does **not** pin the entire Yosys binary or the SHA-256 of the downloaded sv2v release asset.
2. Verify the original RTL/source and campaign hashes using the existing read-only CLI.
3. Run the five structural/verdict Python tests. The sixth test intentionally skips in this step because the standalone SAT runner will execute the live proof once and preserve its output.
4. Run 18-cycle bounded SAT against the real `ascon_aead_encrypt_temporal` controller with its `ascon_permutation_temporal` child replaced by symbolic, unconstrained outputs. Require a passing safety policy, witnesses for clean and alarmed completions, and genuine SAT counterexamples for two temporary, deliberately corrupted controller copies.
5. Require a machine-readable `phase10c_result.json` reporting all five expected outcomes; upload formal logs and the JSON summary even if a later step fails.

## What the green check means

No counterexample was found **within 18 modeled clock steps**, under the runner's explicit reset initialization, for the safety policy of the outer bounded AEAD controller with an unconstrained permutation interface. Both selected completions are reachable; source-level fault mutations produce counterexamples. The result is a **bounded, abstraction-based safety check**, not unbounded proof, cryptographic correctness, physical resistance, or a proof that all transactions terminate.

A failure under Ubuntu does not invalidate the previously passing macOS experiment. Preserve the failing workflow's artifacts, diagnose the Yosys version/tool behavior, and avoid weakening the property to obtain a green check.

## Local commands

```bash
uv run python -m pytest tests/test_phase10c_sequential.py -q
uv run python -m experiments.phase10c_sequential --steps 18 --out-dir build/reproduction/phase10c
```

The output directory is Git-ignored. No original RTL or historical evidence files are modified.
