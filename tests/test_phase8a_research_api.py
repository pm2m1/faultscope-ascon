"""Phase 8A research endpoint integration and fail-closed evidence tests."""
import csv
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from backend import api, research

SOURCE_REPORTS = Path(__file__).resolve().parents[1] / "reports"


def copied_evidence(tmp_path: Path, monkeypatch):
    dest = tmp_path / "reports"
    dest.mkdir()
    for kind, config in research.CAMPAIGNS.items():
        source = SOURCE_REPORTS / Path(config["path"]).name
        data = source.read_bytes()
        (tmp_path / config["path"]).write_bytes(data)
        assert hashlib.sha256(data).hexdigest() == config["sha256"], kind
    monkeypatch.setattr(research, "ROOT", tmp_path)
    return TestClient(api.app)


def test_live_uploaded_csv_summaries_match_recorded_outputs(tmp_path, monkeypatch):
    client = copied_evidence(tmp_path, monkeypatch)
    response = client.get("/api/research/summary")
    assert response.status_code == 200, response.text
    data = response.json()["campaigns"]
    assert data["permutation"]["metrics"]["cases"] == 240
    assert data["permutation"]["metrics"]["alarms"] == 80
    assert data["permutation"]["metrics"]["raw_mismatches"] == 120
    assert data["permutation"]["metrics"]["incorrect_releases"] == 60
    assert data["aead"]["metrics"]["cases"] == 600
    assert data["aead"]["metrics"]["raw_mismatches"] == 204
    assert data["aead"]["metrics"]["alarms"] == 136
    assert data["aead"]["metrics"]["incorrect_releases"] == 102
    for kind, expected in [("permutation", 240), ("aead", 600)]:
        scenarios = data[kind]["scenarios"]
        assert len(scenarios) == 12
        assert sum(s["cases"] for s in scenarios) == expected
        assert sum(s["incorrect_releases"] for s in scenarios) == data[kind]["metrics"]["incorrect_releases"]
    assert [r["cases"] for r in data["aead"]["phases"]] == [120] * 5


def test_filter_and_pagination_return_only_matching_evidence(tmp_path, monkeypatch):
    client = copied_evidence(tmp_path, monkeypatch)
    r = client.get("/api/research/cases", params={
        "kind": "aead", "scenario": "dual_identical", "outcome": "incorrect_release",
        "phase": 0, "offset": 0, "limit": 3,
    })
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 10
    assert len(data["rows"]) == 3
    assert all(x["phase"] == 0 and x["incorrect_release"] == 1 and
               x["scenario"] == "dual_identical" for x in data["rows"])
    r = client.get("/api/research/cases", params={
        "kind": "permutation", "rounds": 12, "scenario": "checkpoint_shared",
        "outcome": "incorrect_release"})
    assert r.status_code == 200
    assert r.json()["total"] == 10
    assert all(x["rounds"] == 12 for x in r.json()["rows"])
    for url in ("/api/research/cases?kind=invalid", "/api/research/cases?kind=aead&rounds=8",
                "/api/research/cases?kind=permutation&phase=1", "/api/research/cases?limit=101",
                "/api/research/cases?scenario=unrecognized", "/api/research/cases?kind=permutation&rounds=10"):
        assert client.get(url).status_code == 422, url


def test_missing_and_tampered_reports_fail_closed(tmp_path, monkeypatch):
    client = copied_evidence(tmp_path, monkeypatch)
    source = tmp_path / research.CAMPAIGNS["aead"]["path"]
    source.unlink()
    assert client.get("/api/research/summary").status_code == 503
    assert client.get("/api/research/cases?kind=aead").status_code == 503
    original = (SOURCE_REPORTS / "phase7b_aead.csv").read_bytes()
    source.write_bytes(original.replace(b"dual_identical", b"dual_difference", 1))
    assert client.get("/api/research/summary").status_code == 409
    assert client.get("/api/research/cases?kind=aead").status_code == 409
    # Permutation evidence remains independently readable when AEAD is broken.
    assert client.get("/api/research/cases?kind=permutation").status_code == 200


def test_malformed_pinned_evidence_is_not_used(tmp_path, monkeypatch):
    client = copied_evidence(tmp_path, monkeypatch)
    source = tmp_path / research.CAMPAIGNS["permutation"]["path"]
    original = source.read_bytes()
    source.write_bytes(original.replace(b"dual_identical", b"unknown_attack", 1))
    # Test parser separately by deliberately using the locally modified hash pin.
    monkeypatch.setitem(research.CAMPAIGNS["permutation"], "sha256", hashlib.sha256(source.read_bytes()).hexdigest())
    assert client.get("/api/research/cases?kind=permutation").status_code == 503
