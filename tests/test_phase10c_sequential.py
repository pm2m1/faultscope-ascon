"""Regression and opt-in bounded sequential formal checks (Phase 10C).

Run live solver on macOS: FAULTSCOPE_RUN_PHASE10C_FORMAL=1 uv run python -m
pytest tests/test_phase10c_sequential.py -v
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from experiments.phase10c_sequential import (
    COUNTEREXAMPLE, SUCCESS, DEFAULT_STEPS, MUTATIONS, ROOT, RTL,
    STUB, TOP, check_source, mutate, parse_verdict, run_campaign,
)


def test_real_controller_source_and_formal_scope():
    source = RTL.read_text(encoding='utf-8')
    check_source(source)
    assert 'module ascon_aead_encrypt_temporal' in source
    assert 'ascon_permutation_temporal u_permutation' in source
    assert '(* anyseq *) wire any_done;' in STUB
    assert '(* anyseq *) wire any_detected;' in STUB
    assert '(* anyseq *) wire [319:0] any_state;' in STUB
    assert 'reg boot_reset_n' in TOP
    assert 'output wire policy_ok, cover_clean, cover_alarm' in TOP
    assert 'assign cover_clean' in TOP and 'assign cover_alarm' in TOP


def test_mutants_do_not_modify_original_controller(tmp_path: Path):
    original = RTL.read_text(encoding='utf-8')
    for key in MUTATIONS:
        mutant = mutate(original, key)
        assert mutant != original
        assert mutant.count('module ascon_aead_encrypt_temporal') == 1
        assert 'ascon_permutation_temporal u_permutation' in mutant
        assert RTL.read_text(encoding='utf-8') == original
    assert 'assign ciphertext_o = ciphertext_q;' in mutate(original, 'leak')
    assert "if (1'b0) begin" in mutate(original, 'alarm_bypass')


def test_mutations_fail_closed_on_unexpected_rtl():
    original = RTL.read_text(encoding='utf-8')
    with pytest.raises(ValueError, match='Cannot uniquely locate'):
        mutate(original.replace(MUTATIONS['leak'][0], 'assign ciphertext_o = 128\'d0;'), 'leak')
    with pytest.raises(ValueError, match='alarm_bypass guard'):
        check_source(original.replace(MUTATIONS['alarm_bypass'][0], "if (1'b0) begin"))


def test_sat_verdict_requires_solver_success_and_exact_message():
    assert parse_verdict(0, SUCCESS, expect_counterexample=False)
    assert parse_verdict(0, COUNTEREXAMPLE, expect_counterexample=True)
    for rc, output in ((1, SUCCESS), (1, COUNTEREXAMPLE), (0, 'ERROR: malformed proof')):
        assert not parse_verdict(rc, output, expect_counterexample=False)
        assert not parse_verdict(rc, output, expect_counterexample=True)
    assert not parse_verdict(0, SUCCESS, expect_counterexample=True)
    assert not parse_verdict(0, COUNTEREXAMPLE, expect_counterexample=False)


def test_bounded_proof_rejects_bad_depth_before_solver(tmp_path):
    for depth in (0, 5, 11, 100):
        with pytest.raises(ValueError, match='Bound must be'):
            run_campaign(tmp_path, steps=depth)
    assert 12 <= DEFAULT_STEPS <= 32


@pytest.mark.skipif(os.environ.get('FAULTSCOPE_RUN_PHASE10C_FORMAL') != '1',
                    reason='Opt-in symbolic SAT run; execute dedicated Phase 10C CLI before CI adoption')
def test_live_bounded_formal_solver(tmp_path):
    assert shutil.which('yosys') and shutil.which('sv2v'), 'Yosys and sv2v required'
    result = run_campaign(tmp_path, steps=DEFAULT_STEPS)
    assert result['results']['policy_ok'].startswith('PASS')
    assert result['results']['cover_clean'].startswith('REACHABLE')
    assert result['results']['cover_alarm'].startswith('REACHABLE')
    assert result['results']['mutant_leak'].startswith('COUNTEREXAMPLE')
    assert result['results']['mutant_alarm_bypass'].startswith('COUNTEREXAMPLE')
    assert (tmp_path / 'phase10c_result.json').is_file()
