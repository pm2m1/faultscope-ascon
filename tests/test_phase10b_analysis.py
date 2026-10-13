"""No synthesis tool needed: exercise resource accounting and provenance guards."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from experiments.phase10b_analysis import build_comparison, logic_metrics, percent_increase

ROOT = Path(__file__).resolve().parents[1]


def _historical():
    metrics = json.loads((ROOT / 'reports/phase5/synthesis_summary.json').read_text())
    manifest = json.loads((ROOT / 'reports/phase5/manifest.json').read_text())
    return metrics, manifest


def test_historical_metadata_is_not_logic():
    metrics, _ = _historical()
    expected = {'baseline': (8275, 2, 1625), 'instrumented': (9863, 2, 1659),
                'protected': (12860, 3, 2645)}
    for name, (logic, meta, bits) in expected.items():
        corrected = logic_metrics(metrics[name])
        assert corrected['logic_cells'] == logic
        assert corrected['metadata_cells_excluded'] == meta
        assert corrected['sequential_q_bits'] == bits
    assert percent_increase(12860, 8275) == pytest.approx(55.4079)
    assert percent_increase(12860, 9863) == pytest.approx(30.3853, abs=0.01)


def test_compare_to_historical_is_version_aware_and_non_destructive():
    metrics, manifest = _historical()
    new_manifest = copy.deepcopy(manifest)
    new_manifest['yosys'] = 'Yosys example newer/different version'
    report = build_comparison(metrics, metrics, new_manifest, manifest)
    assert report['same_synthesis_flow_and_RTL_hashes']
    assert all(delta == 0 for delta in report['tool_environment_delta_logic_cells'].values())
    assert report['tools']['current']['yosys'] != report['tools']['historical']['yosys']
    assert report['relative_overhead_percent']['protected_vs_baseline'] > 55


def test_invalid_cell_counts_and_different_rtl_rejected():
    metrics, manifest = _historical()
    broken = copy.deepcopy(metrics['baseline'])
    broken['total_cells'] += 1
    with pytest.raises(ValueError, match='total disagrees'):
        logic_metrics(broken)
    wrong_manifest = copy.deepcopy(manifest)
    wrong_manifest['sources_sha256']['ascon_round.sv'] = '0' * 64
    with pytest.raises(ValueError, match='source hash differs'):
        build_comparison(metrics, metrics, wrong_manifest, manifest)
    bad_flow = copy.deepcopy(manifest)
    bad_flow['flow'] = 'not the same synth flow'
    with pytest.raises(ValueError, match='flow differs'):
        build_comparison(metrics, metrics, bad_flow, manifest)
