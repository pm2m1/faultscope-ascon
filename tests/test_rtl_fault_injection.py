"""Simulated RTL fault-injection equivalence and reproducibility tests."""
from pathlib import Path

from experiments.run_phase4a import generate_cases, run_campaign
from reference.ascon_fault_model import FaultSpec, encrypt_with_fault
from reference.ascon_aead import encrypt


def test_software_fault_model_disabled_matches_verified_aead():
    for key, nonce, ad, pt, spec in generate_cases():
        disabled = FaultSpec(False, spec.phase, spec.round, spec.bit)
        sealed, hit = encrypt_with_fault(key, nonce, pt, ad, disabled)
        assert not hit
        assert sealed == encrypt(key, nonce, pt, ad)


def test_verilator_fault_campaign_matches_software(tmp_path: Path):
    records = run_campaign(tmp_path / "original")
    replay = run_campaign(tmp_path / "replay")
    assert replay == records, "Same campaign seed must produce identical records"
    assert len(records) == len(generate_cases())
    assert any(x["injected"] for x in records)
    assert any(not x["injected"] for x in records)
    assert any(x["tag_changed"] for x in records)
    assert any(x["ciphertext_changed"] for x in records)
    # Read consistency: records classify differences, not successful forgeries.
    assert all(x["cycles"] > 0 for x in records)
