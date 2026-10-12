# Phase 6A — Local read-only experiment dashboard

Purpose: display **measured** Verilator/Phase 4B and Yosys/Phase 5 results.
This milestone adds no new crypto implementation or experimental claims.

## Prerequisites

Phase 4B (`reports/phase4b_temporal.csv`) and Phase 5 reports
(`reports/phase5/{manifest,campaign_summary,synthesis_summary}.json`) must exist.

1. From the repository root, install the backend packages:
   `uv add fastapi uvicorn` and `uv add --dev httpx`.
2. Run backend tests: `uv run python -m pytest tests/test_dashboard_api.py -v`.
3. Start backend: `uv run uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000`.
4. In a **new Terminal**, `cd ~/Projects/faultscope-ascon/frontend && npm install && npm run dev`.
5. Open `http://127.0.0.1:5173`.

Backend read-only endpoints:
- `GET /api/health`
- `GET /api/summary`
- `GET /api/cases?phase=0&status=detected_fault&offset=0&limit=50`

The server refuses to invent sample data when reports are missing and verifies
that the campaign CSV SHA-256 hash equals the Phase 5 manifest hash.

## Scope and limitations

- **No browser-triggered Verilator/Yosys execution**; filters and refresh only.
- The UI shows model-specific 93/93 detection, not universal resistance.
- Generic cell counts are Yosys generic structural proxies, not ASIC area,
  actual FPGA LUTs, physical frequency or power.
- Baseline, injected and protected are different architectures; generic-cell
  comparison is not a gate-isolated accounting of detector costs.
- No RTL decryption, tag-checking, replay-compromise or physical attack claims.
- For use on localhost only. Do not expose the development server publicly.
