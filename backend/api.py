"""Read-only local API for *measured* FaultScope-Ascon experiment results.

Start from the repository root:
    uv run uvicorn backend.api:app --reload --host 127.0.0.1 --port 8000

No hardware builds, shell commands, uploads or user-chosen file paths are exposed.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
REPORTS = Path("reports")

app = FastAPI(title="FaultScope-Ascon Evidence API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

PHASE_NAMES = {
    0: "Initialization p[12]",
    1: "Associated data p[8]",
    2: "AD full-block padding p[8]",
    3: "Message full-block p[8]",
    4: "Finalization p[12]",
}
REQUIRED_COLUMNS = {
    "case", "ad_len", "msg_len", "armed", "phase", "round", "bit",
    "injected", "detected", "valid", "baseline_cycles", "protected_cycles",
    "faulted_cycles",
}


def _paths():
    return {
        "campaign": ROOT / REPORTS / "phase4b_temporal.csv",
        "summary": ROOT / REPORTS / "phase5" / "campaign_summary.json",
        "synthesis": ROOT / REPORTS / "phase5" / "synthesis_summary.json",
        "manifest": ROOT / REPORTS / "phase5" / "manifest.json",
    }


def _require(p: Path) -> Path:
    if not p.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"Missing project evidence: {p.relative_to(ROOT)}. Run Phase 4B and Phase 5 first.",
        )
    return p


def _read_json(p: Path) -> dict:
    try:
        value = json.loads(_require(p).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Expected an object")
        return value
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=503, detail=f"Invalid evidence file {p.name}: {e}") from e


def _read_campaign(p: Path) -> list[dict]:
    _require(p)
    try:
        with p.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if not REQUIRED_COLUMNS.issubset(reader.fieldnames or []):
                raise ValueError("Missing required campaign columns")
            rows = []
            for item in reader:
                row = {field: int(item[field]) for field in REQUIRED_COLUMNS}
                if any(row[key] not in (0, 1) for key in ("armed", "injected", "detected", "valid")):
                    raise ValueError("Invalid binary field")
                rows.append(row)
        if not rows or [r["case"] for r in rows] != list(range(len(rows))):
            raise ValueError("Empty, nonsequential or duplicate campaign IDs")
        return rows
    except (OSError, ValueError, TypeError) as e:
        raise HTTPException(status_code=503, detail=f"Invalid campaign CSV: {e}") from e


def _evidence() -> tuple[list[dict], dict, dict, dict]:
    files = _paths()
    rows = _read_campaign(files["campaign"])
    summary = _read_json(files["summary"])
    synthesis = _read_json(files["synthesis"])
    manifest = _read_json(files["manifest"])
    actual_hash = hashlib.sha256(files["campaign"].read_bytes()).hexdigest()
    if manifest.get("campaign_sha256") != actual_hash:
        raise HTTPException(
            status_code=409,
            detail="Campaign CSV does not match the Phase 5 manifest. Rerun Phase 5 analysis.",
        )
    if summary.get("cases") != len(rows):
        raise HTTPException(status_code=409, detail="Summary count does not match campaign CSV")
    if summary.get("applied_faults") != sum(r["injected"] for r in rows):
        raise HTTPException(status_code=409, detail="Summary fault count disagrees with campaign CSV")
    if summary.get("detected_faults") != sum(r["injected"] and r["detected"] for r in rows):
        raise HTTPException(status_code=409, detail="Summary detection count disagrees with campaign CSV")
    for design in ("baseline", "instrumented", "protected"):
        if design not in synthesis:
            raise HTTPException(status_code=409, detail=f"Synthesis missing {design}")
    return rows, summary, synthesis, manifest


def _classify(row: dict) -> str:
    if row["injected"]:
        return "detected_fault" if row["detected"] else "undetected_fault"
    return "false_alarm" if row["detected"] else "no_injection"


@app.get("/api/health")
def health() -> dict:
    files = _paths()
    return {"service": "faultscope-api", "evidence_files_present": all(p.is_file() for p in files.values())}


@app.get("/api/summary")
def summary() -> dict:
    rows, metrics, synthesis, manifest = _evidence()
    phase_counts: dict[int, Counter] = {}
    for row in rows:
        counter = phase_counts.setdefault(row["phase"], Counter())
        counter["cases"] += 1
        counter["applied"] += row["injected"]
        counter["detected"] += row["injected"] and row["detected"]
        counter["false_alarms"] += (not row["injected"]) and row["detected"]
    by_phase = [
        {"phase": phase, "name": PHASE_NAMES.get(phase, f"Phase {phase}"),
         "cases": counts["cases"], "applied": counts["applied"],
         "detected": counts["detected"], "false_alarms": counts["false_alarms"]}
        for phase, counts in sorted(phase_counts.items())
    ]
    resources = []
    for design in ("baseline", "instrumented", "protected"):
        value = synthesis[design]
        resources.append({
            "design": design,
            "generic_cells": value["total_cells"],
            "ff_bits": value["sequential_q_bits"],
            "combinational_cells": value["combinational_cells"],
        })
    return {
        "metrics": metrics,
        "resources": resources,
        "phases": by_phase,
        "provenance": {
            "git_commit": manifest.get("git_commit", "unknown"),
            "reference_commit": manifest.get("ascon_reference_commit", "unknown"),
            "yosys": manifest.get("yosys", "unknown"),
            "sv2v": manifest.get("sv2v", "unknown"),
            "campaign_sha256": manifest["campaign_sha256"],
        },
        "scope": {
            "cipher": "NIST Ascon-AEAD128",
            "plaintext_ad_max_bytes": 16,
            "hardware": "bounded encryption + tag generation (not RTL decryption)",
            "fault_model": "single pre-round state-bit flip, first execution only; clean replay",
            "disclaimer": "Digital fault simulation only. Generic Yosys cells are not FPGA LUTs or silicon area. No authenticated-decryption bypass claim.",
        },
    }


@app.get("/api/cases")
def cases(
    phase: int | None = Query(None, ge=0, le=7),
    status: Literal["all", "detected_fault", "undetected_fault", "no_injection", "false_alarm"] = "all",
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> dict:
    rows, _, _, _ = _evidence()
    filtered = [r for r in rows if (phase is None or r["phase"] == phase) and
                (status == "all" or _classify(r) == status)]
    return {"total": len(filtered), "offset": offset, "limit": limit,
            "rows": [{**r, "outcome": _classify(r)} for r in filtered[offset:offset + limit]]}
