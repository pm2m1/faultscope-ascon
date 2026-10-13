"""Combinational Yosys SAT proof of the actual extracted output gates.

The Yosys-dependent test is also run as a mandatory step in the synthesis CI
job; local environments without Yosys run the extraction tests and skip SAT.
"""
import shutil

import pytest

from experiments.phase10b_formal import SOURCE, extract_output_assignments, make_harness, run_proof


def test_output_policy_is_extracted_from_real_RTL():
    source = SOURCE.read_text()
    assignments = extract_output_assignments(source)
    assert "result_valid_o ? ciphertext_q : 128'd0" in assignments
    assert "result_valid_o ? tag_q : 128'd0" in assignments
    harness = make_harness(source)
    assert "output wire policy_ok" in harness
    assert "assign policy_ok" in harness
    assert "assert (" not in harness
    assert "ciphertext_o == 128'd0" in harness
    assert "ciphertext_o == ciphertext_q" in harness


def test_output_policy_rejects_multiple_or_missing_drivers():
    source = SOURCE.read_text()
    with pytest.raises(ValueError):
        extract_output_assignments(source.replace('assign tag_o =', 'assign nonexistent ='))
    with pytest.raises(ValueError):
        extract_output_assignments(source + "\nassign ciphertext_o = 128'd0;\n")


def test_sat_proof_and_negative_control(tmp_path):
    if not shutil.which('yosys'):
        pytest.skip('Yosys not installed; required in dedicated CI synthesis job')
    assert run_proof(tmp_path)[0]
    assert run_proof(tmp_path, negative_control=True)[0]
