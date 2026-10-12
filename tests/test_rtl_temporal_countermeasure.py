"""Phase 4B end-to-end verification of temporal recomputation countermeasure."""
from pathlib import Path

from experiments.run_phase4b import (
    cases_for_protection,
    run_campaign,
    summarize,
    write_vectors,
)


def test_temporal_vectors_and_expected_fault_occurrence(tmp_path: Path):
    cases = cases_for_protection()
    hits = write_vectors(tmp_path / "vectors.txt", cases)
    assert len(cases) == 424  # Phase 4A 135 + 289 length-boundary vectors
    assert hits == 93
    assert (tmp_path / "vectors.txt").read_text().count("\n") == len(cases)


def test_temporal_protection_matches_golden_and_blocks_injected_faults(tmp_path: Path):
    rows = run_campaign(tmp_path / "sim")
    stats = summarize(rows)
    assert len(rows) == len(cases_for_protection())
    assert stats["injections"] == stats["detections"]
    assert stats["false_alarms"] == 0
    assert all(row["protected_cycles"] > row["baseline_cycles"] for row in rows)
    assert all(row["protected_cycles"] == row["faulted_cycles"] for row in rows)
    assert any(row["phase"] == 4 and row["injected"] for row in rows)
    assert any(row["ad_len"] == 16 and row["msg_len"] == 16 for row in rows)
