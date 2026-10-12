"""Phase 7A: adversarial temporal permutation stress tests."""
from collections import Counter
from pathlib import Path

import pytest

from experiments.run_phase7 import (
    cases_for_adversarial,
    run_campaign,
    summarize,
    write_vectors,
)
from reference.ascon_adversarial_model import (
    AdversarialSpec,
    evaluate,
    pack_state,
    unpack_state,
)
from reference.ascon_permutation import ascon_permutation


def test_software_oracle_matches_clean_permutation():
    cases = cases_for_adversarial()
    assert len(cases) == 240
    assert {rounds for _, rounds, _, _ in cases} == {8, 12}
    assert len({name for name, _, _, _ in cases}) == 12
    for name, rounds, state, spec in cases:
        assert pack_state(unpack_state(state)) == state
        expected_golden = pack_state(ascon_permutation(unpack_state(state), rounds))
        o = evaluate(state, rounds, spec)
        assert o.golden == expected_golden
        assert o.valid == (not o.raw_mismatch or spec.suppress_alarm)
        assert o.alarm == (o.raw_mismatch and not spec.suppress_alarm)
        assert o.output == (o.replay_state if o.valid else 0)
        assert not o.alarm or (not o.valid and o.output == 0)
        if name == "clean":
            assert o.valid and not o.alarm and not o.silent_corruption
        elif name == "first_only":
            assert o.first_fired and o.raw_mismatch and o.alarm and not o.valid
        elif name == "replay_only":
            assert o.replay_fired and o.raw_mismatch and o.alarm and not o.valid
        elif name == "dual_identical":
            assert o.first_fired and o.replay_fired
            assert not o.raw_mismatch and o.valid and o.silent_corruption
        elif name == "checkpoint_shared":
            assert o.checkpoint_fired and not o.raw_mismatch
            assert o.valid and o.silent_corruption
        elif name == "checkpoint_replay":
            assert o.checkpoint_fired and o.raw_mismatch and o.alarm and not o.valid
        elif name == "suppress_replay_alarm":
            assert o.replay_fired and o.raw_mismatch and not o.alarm
            assert o.valid and o.silent_corruption
        elif name == "suppress_first_alarm":
            assert o.first_fired and o.raw_mismatch and not o.alarm
            assert o.valid and not o.silent_corruption
        elif name in ("first_invalid_bit", "replay_invalid_round", "checkpoint_invalid_bit"):
            assert o.valid and not o.alarm and not o.silent_corruption
    assert Counter(name for name, _, _, _ in cases) == {
        "clean": 20, "first_only": 20, "replay_only": 20,
        "dual_identical": 20, "dual_different": 20,
        "checkpoint_shared": 20, "checkpoint_replay": 20,
        "suppress_replay_alarm": 20, "suppress_first_alarm": 20,
        "first_invalid_bit": 20, "replay_invalid_round": 20,
        "checkpoint_invalid_bit": 20,
    }


def test_vectors_are_deterministic_and_well_formed(tmp_path: Path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    cases = cases_for_adversarial()
    write_vectors(a, cases)
    write_vectors(b, cases)
    assert a.read_bytes() == b.read_bytes()
    lines = a.read_text(encoding="ascii").splitlines()
    assert len(lines) == len(cases)
    assert all(len(line.split()) == 20 for line in lines)
    assert all(len(line.split()[1]) == 80 for line in lines)
    assert all(len(line.split()[18]) == 80 for line in lines)


def test_verilator_adversarial_temporal_comparisons(tmp_path: Path):
    # Fail rather than skip when Verilator is absent: the RTL is a required gate.
    rows = run_campaign(tmp_path / "sim")
    stats = summarize(rows)
    assert stats["cases"] == 240
    assert all(r["cycles"] > 0 for r in rows)
    assert all(r["raw_mismatch"] >= r["alarm"] for r in rows)
    assert all((not r["alarm"] or not r["valid"]) for r in rows)
    assert all(r["silent_corruption"] == 1 for r in rows if r["scenario"] in (
        "dual_identical", "checkpoint_shared", "suppress_replay_alarm"))
    assert all(r["silent_corruption"] == 0 for r in rows if r["scenario"] in (
        "clean", "first_only", "replay_only", "checkpoint_replay",
        "suppress_first_alarm", "first_invalid_bit", "replay_invalid_round",
        "checkpoint_invalid_bit"))
    assert stats["silent_corruptions"] >= 60
