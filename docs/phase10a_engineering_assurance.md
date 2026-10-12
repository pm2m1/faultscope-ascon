# Phase 10A — CI, CLI, and temporal-RTL safety contract

## Scope

This is an additive engineering-hardening phase. No `rtl/`, `reference/`,
`experiments/`, original testbench, or `reports/` content is changed. The
pre-existing 48-test baseline remains meaningful and must continue to pass.

## Changes

- `.github/workflows/verify.yml` runs two jobs on pushes to `main`, pull
  requests targeting `main`, and manual dispatch. The Python/RTL job restores
  the exact upstream Ascon-C pin, installs Verilator, sets up Python 3.12 and
  Node 24, checks immutable CSVs, and runs the complete test suite. The
  frontend job runs `npm ci` and `npm run build`.
- `pyproject.toml` now supplies a concrete description and points its console
  script to a working CLI. `faultscope-ascon verify-evidence` compares the
  Phase 4B SHA-256 from `reports/phase5/manifest.json` plus the Phase 7A/7B
  digests pinned in `backend/research.py`, all seven Phase 5 RTL source
  hashes and the Ascon-C revision pin, and returns nonzero on mismatches.
  `faultscope-ascon serve` launches the FastAPI app locally (default
  `127.0.0.1:8000`). Run both commands from the repository root.
- A separate SystemVerilog safety monitor checks the **live protected RTL**:
  invalid outputs are masked, sticky alarms block release, no output is
  externally valid while busy, DONE only occurs at idle, and DONE is a
  single-cycle pulse.
- The positive directed test runs live protected RTL over normal, injected,
  and restart paths. A **negative-control test** drives a deliberate contract
  violation, requiring the monitor to fail with a named assertion. Both use
  Verilator `--assert` and are mandatory in GitHub Actions.

## Local commands

```bash
uv sync --locked --group dev
uv run faultscope-ascon --help
uv run faultscope-ascon verify-evidence
uv run python -m pytest tests/test_phase10a_cli.py tests/test_phase10a_rtl_contract.py -v
uv run python -m pytest tests/ -q
cd frontend && npm run build && cd ..
```

The original suite had **48** test cases. Phase 10A adds **6** cases, so the
expected regression count is **54** if all previous tests still collect.

To start the API via the new console entry point:

```bash
uv run faultscope-ascon serve --reload
# In another shell: cd frontend && npm run dev
```

## Honest assurance boundary

**These are simulation-checked properties, not exhaustive formal verification.**
The SVA monitor samples supported RTL interfaces during three directed
transactions; it cannot establish all possible states, control upsets, or
real-world physical fault coverage. Unlike claims of a full proof, it is
appropriate to state **five safety assertions passed on the sampled tests**
after testing on the target Mac/CI runners. The negative control checks that
assertion processing is active, but does not prove the design correct.

A future *formal* phase should use a formal model checker (e.g., SymbiYosys /
Yosys SAT or another compatible engine) with explicit reset assumptions,
fairness and environment constraints, reachable-state analysis, and a report
of proved properties / bounds / counterexamples. Keep that result separate
from this simulation contract and from the Phase 4B campaign's fault coverage.

## CI caveats

The GitHub hosted runner is Linux, whereas the initial 48-test record came
from a Mac. Verilator / native-tool versions can differ. This workflow is
prepared but **not considered verified** until the first GitHub Actions run
passes. The CI checks simulation and recorded data; it does not automatically
rerun expensive Yosys synthesis or prove physical-hardware properties.

The CLI description/entrypoint change doesn't alter dependency requirements.
Run `uv sync --locked --group dev` to confirm `uv.lock` remains current; if
`uv` reports a lockfile mismatch, regenerate with `uv lock`, inspect the diff,
and include the updated lockfile in the commit. Never alter pinned CSV evidence.
