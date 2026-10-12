"""Phase 7B: model-level checks and compulsory RTL-vs-model test."""
from collections import Counter
from pathlib import Path

from experiments.run_phase7b import cases_for_phase7b, run_campaign, summarize, write_vectors
from reference.ascon_aead import encrypt
from reference.ascon_aead_adversarial_model import evaluate_aead


def test_phase7b_clean_matches_all_bounded_length_pairs():
    cases = cases_for_phase7b()
    assert len(cases) == 600
    assert len({(c["phase"], len(c["ad"]), len(c["plaintext"])) for c in cases}) == 50
    for c in cases:
        o = evaluate_aead(c["key"], c["nonce"], c["plaintext"], c["ad"], c["attack"])
        if c["scenario"] == "clean":
            assert o.ciphertext + o.tag == encrypt(c["key"], c["nonce"], c["plaintext"], c["ad"])
            assert o.valid and not o.alarm and not o.incorrect_release
        if o.alarm:
            assert o.fail_closed
        if c["scenario"] in ("dual_identical", "checkpoint_shared", "suppress_replay_alarm"):
            if (o.first_fired or o.replay_fired or o.checkpoint_fired):
                assert o.incorrect_release and not o.alarm and o.valid
        if c["scenario"] in ("first_invalid_bit", "replay_invalid_round", "checkpoint_invalid_bit"):
            assert o.valid and not o.alarm and not o.incorrect_release


def test_phase7b_vectors_reproducible_and_complete(tmp_path: Path):
    cases = cases_for_phase7b()
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    write_vectors(a, cases)
    write_vectors(b, cases)
    assert a.read_bytes() == b.read_bytes()
    lines = a.read_text(encoding="ascii").splitlines()
    assert len(lines) == 600
    assert all(len(line.split()) == 28 for line in lines)
    assert all(len(line.split()[0]) == 32 for line in lines)
    assert Counter(c["scenario"] for c in cases) == {name: 50 for name in (
        "clean", "first_only", "replay_only", "dual_identical", "dual_different",
        "checkpoint_shared", "checkpoint_replay", "suppress_replay_alarm",
        "suppress_first_alarm", "first_invalid_bit", "replay_invalid_round",
        "checkpoint_invalid_bit",
    )}


def test_phase7b_verilator_aead_matches_oracle_and_gates_output(tmp_path: Path):
    rows = run_campaign(tmp_path / "sim")  # Verilator required: no skip / silent fallback
    stats = summarize(rows)
    assert stats["cases"] == 600
    assert stats["incorrect_releases"] > 0
    assert stats["alarms"] > 0
    assert stats["raw_mismatches"] >= stats["alarms"]
    assert all(r["cycles"] > 0 for r in rows)
    assert all((not r["alarm"] or not r["valid"]) for r in rows)
    assert all(not r["incorrect_release"] for r in rows if r["alarm"])
    assert all(not r["incorrect_release"] for r in rows if r["scenario"] == "clean")
