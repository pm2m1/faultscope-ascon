# FaultScope-Ascon Phase 8A — Unified Evidence Dashboard

## Deliverable and baseline preservation

This patch only modifies the existing React `App.tsx` and stylesheet, extends `backend/api.py` by registering a new router, and adds `backend/research.py`, `tests/test_phase8a_research_api.py`, and this document. It does **not** modify any existing RTL module, experiment runner, Phase 4B/7A/7B CSV, or Phase 5 provenance manifest.

### Local startup

Run from `~/Projects/faultscope-ascon` after extracting `faultscope_ascon_phase8a.zip`:

```bash
uv run python -m pytest tests/test_dashboard_api.py tests/test_phase8a_research_api.py -v
uv run python -m pytest tests/ -q
# 41 existing tests + 4 new tests = target 45 passing
uv run uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000
```

In a separate terminal:

```bash
cd ~/Projects/faultscope-ascon/frontend
npm run build
npm run dev
```

Open `http://127.0.0.1:5173`, then click **Adversarial research** in the sidebar. Check Phase 7A/7B toggle, scenario comparison, per-phase 7B breakdown, scenario and outcome filters, pagination, and the provenance accordion. Leave both servers running while testing.

**Note:** The frontend package's TSX syntax was checked during preparation; a complete `npm run build` was unavailable in the author's isolated environment because the package installation did not finish. Your local build is mandatory before committing.

## Read-only endpoints

Unchanged existing endpoints:

- `GET /api/health`
- `GET /api/summary` — Phase 4B/5 metrics and resources, linked to the Phase 5 manifest hash
- `GET /api/cases` — original Phase 4B experiment ledger

New:

- `GET /api/research/summary` — both advanced campaigns; aggregated 12-scenario breakdowns and 5 AEAD-phase breakdowns, scoped disclaimers and SHA-256 identifiers.
- `GET /api/research/cases` — paginated recorded rows (`kind=permutation|aead`, `scenario=all|<known-name>`, `outcome=all|alarm|incorrect_release|raw_mismatch|valid_correct|no_alarm`, `phase=0..4` for AEAD, `rounds=8|12` for permutation, `offset>=0`, `1<=limit<=100`).

All endpoints are GET-only. There is no raw file-path parameter, arbitrary command execution, hardware invocation, file upload, user-supplied cryptographic key, or mutation of recorded data.

## Evidence integrity policy

The original Phase 4B `/api/summary` still checks the Phase 5 manifest against the on-disk `phase4b_temporal.csv` SHA-256. Phase 7A and Phase 7B **do not** have individual provenance manifests, so the Phase 8A reader pins the previously verified, committed **exact file bytes**:

| Campaign | Recorded rows | SHA-256 |
|---|---:|---|
| Phase 7A (permutation) | 240 | `c249e85323d901c115463b6ebce8d0693368e3b960756919762256012629eabc` |
| Phase 7B (bounded AEAD) | 600 | `4d1757ef06d079f6ed810112876699404d1709b8fb0da47f5e8baac85aeb5b04` |

Altered evidence returns HTTP **409**. Missing or structurally malformed evidence returns **503**. Filters with invalid arguments return **422**. Phase 8A does not silently manufacture substitute data. The original Phase 4B/5 overview continues to load independently if one of the new evidence files is missing or altered; the research panel displays the corresponding error.

If a Phase 7 CSV is deliberately regenerated, carefully verify and document the new campaign and update its pinned hash before showing it in the research dashboard. Do not simply weaken the hash check to make a new report load.

## Terminology and limitations

- **Phase 4B**: 424 deterministic scenarios, 93 applied single-first-execution faults, 93 alarms, no observed alarm-and-valid violations; *clean* temporal replay assumption.
- **Phase 7A**: 240 permutation-level scenarios, 120 raw mismatches, 80 alarms, 60 **silent incorrect permutation releases**. This concerns 320-bit permutation state only, *not* AEAD output validity.
- **Phase 7B**: 600 bounded encryption-and-tag scenarios, 204 raw mismatches, 136 alarms, 102 **incorrect ciphertext/tag releases** compared against a verified golden encryptor. It does not demonstrate a receiving-party tag-acceptance forgery.

`raw_mismatch`, `alarm`, and `incorrect_release` are overlapping/non-partitioning flags. Do not add their counts together or combine them into a single detection percentage. The case sets are deliberately specified fault hooks, not samples of real physical fault-event probability. Neither silicon area, FPGA LUT utilization, nor physical fault resistance has been established by these plots.

## Pre-commit checklist

1. Run `uv run python -m pytest tests/ -q` and confirm **45 passed** (if no further unrelated tests added).
2. Run `npm run build` and open `http://127.0.0.1:5173` while FastAPI is running.
3. Verify the original three dashboard sections still work and still show 424 cases / 93 detections / existing cost metrics.
4. Verify Phase 7A=240 / 80 alarms / 60 incorrect releases and Phase 7B=600 / 136 alarms / 102 incorrect releases.
5. Filter Phase 7B `dual_identical` + `incorrect release` + `initialization` and confirm 10 rows match.
6. Confirm no change to tracked `reports/*.csv`, RTL, or experiment runners.
7. Stage **only** six Phase 8A source/doc/test files, then commit.
