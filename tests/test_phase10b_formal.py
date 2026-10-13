"""Combinational Yosys SAT proof of the actual extracted output gates.

The Yosys-dependent test is also run as a mandatory step in the synthesis CI
job; local environments without Yosys run the extraction tests and skip SAT.
"""
import subprocess
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


def test_negative_control_portable_verdict(tmp_path, monkeypatch):
    """A genuine counterexample passes; a Yosys error never counts as one."""
    from experiments import phase10b_formal

    captured = []

    def counterexample(cmd, **kwargs):
        captured.append(cmd[-1])
        return subprocess.CompletedProcess(
            cmd, 0, stdout="SAT proof finished - model found: FAIL!\n", stderr=""
        )

    monkeypatch.setattr(phase10b_formal.subprocess, 'run', counterexample)
    assert run_proof(tmp_path, negative_control=True, yosys='yosys')[0]
    assert '-verify' not in captured[-1]

    def tool_error(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, 1, stdout="ERROR: Called with -verify and proof did fail!\n", stderr=""
        )

    monkeypatch.setattr(phase10b_formal.subprocess, 'run', tool_error)
    with pytest.raises(AssertionError, match='Negative control did not produce'):
        run_proof(tmp_path, negative_control=True, yosys='yosys')
