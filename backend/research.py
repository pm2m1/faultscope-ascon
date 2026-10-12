"""Read-only, hash-pinned Phase 7A/7B experimental evidence API.

Hash pins refer to the committed, independently verified campaign CSV blobs.
This API does not execute simulations, allow file uploads, or accept file paths.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parents[1]
router = APIRouter(prefix="/api/research", tags=["Research evidence"])

CAMPAIGNS = {
    "permutation": {
        "path": "reports/phase7_adversarial.csv",
        "sha256": "c249e85323d901c115463b6ebce8d0693368e3b960756919762256012629eabc",
        "id": "7A", "output_label": "Silent incorrect permutation release",
        "scope": "320-bit permutation p[8]/p[12] only",
        "fault_model": "Independently controlled execution/replay, checkpoint, comparator hooks",
    },
    "aead": {
        "path": "reports/phase7b_aead.csv",
        "sha256": "4d1757ef06d079f6ed810112876699404d1709b8fb0da47f5e8baac85aeb5b04",
        "id": "7B", "output_label": "Incorrect ciphertext/tag release",
        "scope": "Bounded Ascon-AEAD128 encryption/tag generation, up to 16 B each AD/message",
        "fault_model": "Independently controlled execution/replay, checkpoint, comparator hooks",
    },
}
SCENARIOS = (
    "clean", "first_only", "replay_only", "dual_identical", "dual_different",
    "checkpoint_shared", "checkpoint_replay", "suppress_replay_alarm",
    "suppress_first_alarm", "first_invalid_bit", "replay_invalid_round",
    "checkpoint_invalid_bit",
)
COMMON_NUMERIC = (
    "case", "first_fired", "replay_fired", "checkpoint_fired",
    "raw_mismatch", "alarm", "valid", "cycles",
)
COLUMN_MAP = {
    "permutation": {"rounds", "silent_corruption", "first_round", "first_bit",
                    "replay_round", "replay_bit", "checkpoint_mode", "checkpoint_bit",
                    "suppress_alarm"},
    "aead": {"phase", "ad_len", "msg_len", "incorrect_release"},
}
BINARY = {"first_fired", "replay_fired", "checkpoint_fired", "raw_mismatch", "alarm", "valid"}
Outcome = Literal["all", "alarm", "incorrect_release", "raw_mismatch", "valid_correct", "no_alarm"]


def load_campaign(kind: Literal["permutation", "aead"]) -> list[dict]:
    config = CAMPAIGNS[kind]
    path = ROOT / config["path"]
    if not path.is_file():
        raise HTTPException(503, f"Missing recorded Phase {config['id']} evidence: {config['path']}")
    try:
        data = path.read_bytes()
    except OSError as e:
        raise HTTPException(503, f"Cannot read Phase {config['id']} evidence: {e}") from e
    sha = hashlib.sha256(data).hexdigest()
    if sha != config["sha256"]:
        raise HTTPException(
            409, f"Phase {config['id']} CSV SHA-256 disagrees with the pinned verified snapshot. "
                 "Do not display altered evidence; deliberately review and repin any new campaign.",
        )
    required = {"scenario", *COMMON_NUMERIC, *COLUMN_MAP[kind]}
    flag_columns = BINARY | {"silent_corruption" if kind == "permutation" else "incorrect_release"}
    try:
        import io
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
        if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
            raise ValueError("Duplicate CSV header")
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Missing required experiment fields")
        rows = []
        for raw in reader:
            if raw.get(None) is not None:
                raise ValueError("Unexpected extra CSV fields")
            scenario = raw["scenario"]
            if scenario not in SCENARIOS:
                raise ValueError("Unknown fault scenario")
            row = {k: int(raw[k]) for k in required if k != "scenario"}
            row["scenario"] = scenario
            if any(row[k] not in (0, 1) for k in flag_columns):
                raise ValueError("Invalid binary result flag")
            if row["case"] != len(rows):
                raise ValueError("Missing/duplicate/nonsequential case number")
            if row["cycles"] <= 0:
                raise ValueError("Nonpositive cycle count")
            if row["alarm"] and (row["valid"] or not row["raw_mismatch"]):
                raise ValueError("Inconsistent alarm or output-valid result")
            wrong = row["silent_corruption" if kind == "permutation" else "incorrect_release"]
            if wrong and not row["valid"]:
                raise ValueError("Invalid incorrect-release flag")
            if kind == "permutation":
                if row["rounds"] not in (8, 12):
                    raise ValueError("Invalid permutation rounds")
                row["incorrect_release"] = row.pop("silent_corruption")
            else:
                if not (0 <= row["phase"] <= 4 and 0 <= row["ad_len"] <= 16
                        and 0 <= row["msg_len"] <= 16):
                    raise ValueError("Invalid AEAD phase or bounded lengths")
            rows.append(row)
        expected_count = 240 if kind == "permutation" else 600
        if len(rows) != expected_count:
            raise ValueError(f"Expected {expected_count} recorded rows, received {len(rows)}")
        return rows
    except (ValueError, UnicodeError, TypeError, csv.Error, KeyError) as e:
        raise HTTPException(503, f"Malformed Phase {config['id']} evidence: {e}") from e


def calculate_metrics(rows: list[dict]) -> dict:
    return {
        "cases": len(rows),
        "raw_mismatches": sum(r["raw_mismatch"] for r in rows),
        "alarms": sum(r["alarm"] for r in rows),
        "incorrect_releases": sum(r["incorrect_release"] for r in rows),
        "valid_releases": sum(r["valid"] for r in rows),
        "first_fault_events": sum(r["first_fired"] for r in rows),
        "replay_fault_events": sum(r["replay_fired"] for r in rows),
        "checkpoint_fault_events": sum(r["checkpoint_fired"] for r in rows),
    }


def _matches(row: dict, outcome: Outcome) -> bool:
    return (
        outcome == "all" or
        outcome == "alarm" and row["alarm"] == 1 or
        outcome == "incorrect_release" and row["incorrect_release"] == 1 or
        outcome == "raw_mismatch" and row["raw_mismatch"] == 1 or
        outcome == "valid_correct" and row["valid"] == 1 and row["incorrect_release"] == 0 or
        outcome == "no_alarm" and row["alarm"] == 0
    )


@router.get("/summary")
def research_summary() -> dict:
    # Fail the whole combined comparison if either campaign is invalid.
    a = load_campaign("permutation")
    b = load_campaign("aead")
    result = {}
    for name, rows in (("permutation", a), ("aead", b)):
        meta = CAMPAIGNS[name]
        by_scenario = []
        counts = {scenario: [r for r in rows if r["scenario"] == scenario] for scenario in SCENARIOS}
        for scenario, subset in counts.items():
            by_scenario.append({"scenario": scenario, **calculate_metrics(subset)})
        by_phase = []
        if name == "aead":
            for phase in range(5):
                subset = [r for r in rows if r["phase"] == phase]
                by_phase.append({"phase": phase, **calculate_metrics(subset)})
        result[name] = {
            "label": "Phase " + meta["id"], "scope": meta["scope"],
            "output_label": meta["output_label"], "fault_model": meta["fault_model"],
            "sha256": meta["sha256"], "metrics": calculate_metrics(rows),
            "scenarios": by_scenario, "phases": by_phase,
        }
    return {
        "campaigns": result,
        "limitations": [
            "Digital fault-injection test fixtures, not physical fault-resistance measurements.",
            "Different threat models and deliberately selected cases; counts are not cross-phase detection rates or real-world attack probabilities.",
            "Incorrect release means output differs from the fault-free result; no authenticated-decryption acceptance or forgery is demonstrated.",
            "A raw mismatch may be suppressed deliberately by a compromised-comparator simulation hook.",
        ],
    }


@router.get("/cases")
def research_cases(
    kind: Literal["permutation", "aead"] = "aead",
    scenario: str = "all",
    outcome: Outcome = "all",
    phase: int | None = Query(None, ge=0, le=4),
    rounds: int | None = Query(None, ge=8, le=12),
    offset: int = Query(0, ge=0),
    limit: int = Query(15, ge=1, le=100),
) -> dict:
    if scenario != "all" and scenario not in SCENARIOS:
        raise HTTPException(422, "Unknown scenario")
    if (kind == "aead" and rounds is not None) or (kind == "permutation" and phase is not None):
        raise HTTPException(422, "Phase filter applies to AEAD, rounds filter to permutation only")
    if rounds is not None and rounds not in (8, 12):
        raise HTTPException(422, "Permutation rounds must be 8 or 12")
    rows = load_campaign(kind)
    selected = [r for r in rows if (scenario == "all" or r["scenario"] == scenario)
                and _matches(r, outcome) and (phase is None or r.get("phase") == phase)
                and (rounds is None or r.get("rounds") == rounds)]
    return {"kind": kind, "total": len(selected), "offset": offset, "limit": limit,
            "rows": selected[offset: offset + limit]}
