"""Dashboard endpoint tests use fixture evidence, not fabricated live results."""
import csv
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend import api


def make_evidence(tmp_path: Path, mismatch: bool = False):
    folder = tmp_path / "reports" / "phase5"
    folder.mkdir(parents=True)
    rows = [
        dict(case=0, ad_len=0, msg_len=0, armed=1, phase=0, round=0,
             bit=3, injected=1, detected=1, valid=0,
             baseline_cycles=40, protected_cycles=80, faulted_cycles=80),
        dict(case=1, ad_len=16, msg_len=16, armed=0, phase=4, round=0,
             bit=5, injected=0, detected=0, valid=1,
             baseline_cycles=60, protected_cycles=120, faulted_cycles=120),
    ]
    p = tmp_path / "reports" / "phase4b_temporal.csv"
    with p.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    (folder / "campaign_summary.json").write_text(json.dumps({
        "cases": 2, "applied_faults": 1, "detected_faults": 1,
        "coverage_percent": 100.0, "mean_baseline_cycles": 50.0,
        "mean_protected_cycles": 100.0,
    }))
    (folder / "synthesis_summary.json").write_text(json.dumps({
        x: {"total_cells": cells, "sequential_q_bits": ff, "combinational_cells": cells - ff}
        for x, cells, ff in (("baseline", 8000, 1000), ("instrumented", 9000, 1100), ("protected", 12000, 1600))
    }))
    (folder / "manifest.json").write_text(json.dumps({
        "campaign_sha256": "invalid" if mismatch else sha,
        "git_commit": "test-git", "yosys": "test-yosys", "sv2v": "test-sv2v",
    }))


def test_summary_and_case_filters(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "ROOT", tmp_path)
    make_evidence(tmp_path)
    client = TestClient(api.app)
    r = client.get("/api/summary")
    assert r.status_code == 200
    data = r.json()
    assert data["metrics"]["applied_faults"] == 1
    assert data["resources"][2]["generic_cells"] == 12000
    assert sum(x["detected"] for x in data["phases"]) == 1
    filtered = client.get("/api/cases?status=detected_fault&phase=0")
    assert filtered.status_code == 200 and filtered.json()["total"] == 1
    assert filtered.json()["rows"][0]["outcome"] == "detected_fault"
    assert client.get("/api/cases?limit=201").status_code == 422
    assert client.get("/api/cases?phase=-1").status_code == 422


def test_missing_evidence_is_not_replaced_by_mock_data(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "ROOT", tmp_path)
    client = TestClient(api.app)
    assert client.get("/api/health").json()["evidence_files_present"] is False
    assert client.get("/api/summary").status_code == 503


def test_tampered_campaign_hash_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "ROOT", tmp_path)
    make_evidence(tmp_path, mismatch=True)
    client = TestClient(api.app)
    r = client.get("/api/summary")
    assert r.status_code == 409
    assert "manifest" in r.json()["detail"].lower()
