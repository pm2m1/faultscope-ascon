"""Phase 16 fail-closed evidence-collection tests (no Vivado required)."""
from __future__ import annotations
from pathlib import Path
import sys
import json
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import phase16_gap_report as p16


def p15_stub():
    return {
        'checkpoint_sha256': 'a'*64,
        'xdc_sha256': 'b'*64,
        'internal_setup_slack_ns': 1.471,
        'internal_hold_slack_ns': 0.022,
    }


@pytest.fixture
def audit(tmp_path, monkeypatch):
    monkeypatch.setattr(p16, 'baseline', lambda _root: p15_stub())
    d = tmp_path / 'audit'
    d.mkdir()
    (d/'context.tsv').write_text(
        'key\tvalue\nphase\t16\ndesign_name\tcheckpoint_post_route\n'
        'vivado_version\t2026.1\nclock_name\tboard_clk_100mhz\n'
        'clock_period_ns\t10.000\ncfgbvs\tUNSET\nconfig_voltage\tUNSET\n'
        'clock_buffers\t1\ninput_buffers\t3\n'
        'scope\tpost-route read-only diagnostic, NOT board signoff\n', encoding='utf8')
    (d/'ports.tsv').write_text('port\tdirection\tpackage_pin\tiostandard\n' + ''.join(
        f'{name}\t{direction}\t{pin}\tLVCMOS33\n'
        for name, (direction, pin) in sorted(p16.PINS.items())), encoding='utf8')
    for report in p16.REPORTS:
        (d / report).write_text('Vivado report generated from the original routed checkpoint.\n', encoding='utf8')
    return tmp_path, d


def test_positive_still_not_signoff(audit):
    base, d = audit
    r = p16.inspect(base, d)
    assert r['verdict'] == 'EVIDENCE_COLLECTED_REVIEW_REQUIRED'
    assert r['configuration_property_state'] == 'MISSING_IN_PHASE15_CHECKPOINT'
    assert r['board_signoff'] == 'NOT VERIFIED'
    assert all(v != 'PASS' for v in r['signoff_gaps'].values())
    assert r['phase15_setup_slack_ns'] == 1.471
    p16.write_output(d, r)
    assert (d / 'gap_matrix.tsv').exists()
    assert json.loads((d / 'verification.json').read_text())['verdict'] == r['verdict']


def test_proposed_properties_not_hardware_signoff(audit):
    base, d = audit
    s = (d/'context.tsv').read_text()
    (d/'context.tsv').write_text(s.replace('cfgbvs\tUNSET', 'cfgbvs\tVCCO').replace(
        'config_voltage\tUNSET', 'config_voltage\t3.3'))
    r = p16.inspect(base, d)
    assert r['verdict'] == 'EVIDENCE_COLLECTED_REVIEW_REQUIRED'
    assert r['configuration_property_state'] == 'MATCHES_SCHEMATIC_PROPOSAL_NOT_SIGNOFF'
    assert r['signoff_gaps']['config_voltage'] == 'OPEN'


@pytest.mark.parametrize('file,old,new', [
    ('context.tsv','checkpoint_post_route', 'unexpected_top'),
    ('context.tsv','10.000','9.000'),
    ('context.tsv','10.000','nan'),
    ('context.tsv','board_clk_100mhz','fake_clk'),
    ('context.tsv','clock_buffers\t1','clock_buffers\t0'),
    ('context.tsv','input_buffers\t3','input_buffers\t0'),
    ('context.tsv','cfgbvs\tUNSET', 'cfgbvs\tGND'),
    ('context.tsv','config_voltage\tUNSET','config_voltage\t1.8'),
    ('context.tsv','2026.1','bad-version'),
    ('ports.tsv','C4','D4'),
    ('ports.tsv','LVCMOS33','LVCMOS18'),
    ('ports.tsv','uart_rx_i\tIN','uart_rx_i\tOUT'),
    ('ports.tsv','clk\tIN','clone\tIN'),
])
def test_mutation_fails_closed(audit, file, old, new):
    base, d = audit
    path = d/file
    body = path.read_text(encoding='utf8')
    assert old in body
    path.write_text(body.replace(old, new), encoding='utf8')
    assert p16.inspect(base, d)['verdict'] == 'NOT_VERIFIED'


def test_missing_report_fails_closed(audit):
    base, d = audit
    (d/'methodology.rpt').unlink()
    assert p16.inspect(base, d)['verdict'] == 'NOT_VERIFIED'


def test_short_report_fails_closed(audit):
    base, d = audit
    (d/'drc.rpt').write_text('OK')
    assert p16.inspect(base, d)['verdict'] == 'NOT_VERIFIED'


def test_duplicate_context_fails_closed(audit):
    base, d = audit
    with (d/'context.tsv').open('a') as f:
        f.write('clock_period_ns\t10.000\n')
    assert p16.inspect(base, d)['verdict'] == 'NOT_VERIFIED'


def test_baseline_provenance_error_fails_closed(audit, monkeypatch):
    base, d = audit
    def fail(_root):
        raise ValueError('checkpoint hash mismatch')
    monkeypatch.setattr(p16, 'baseline', fail)
    r = p16.inspect(base, d)
    assert r['verdict'] == 'NOT_VERIFIED'
    assert any('hash mismatch' in a for a in r['issues'])


def test_tcl_is_read_only_and_queries_after_checkpoint():
    script = (ROOT/'scripts/phase16_gap_audit.tcl').read_text(encoding='utf8')
    commands = '\n'.join(line.strip() for line in script.splitlines() if not line.strip().startswith('#'))
    for dangerous in ('write_bitstream', 'write_checkpoint', 'synth_design', 'place_design',
                      'route_design', 'read_xdc', 'set_property ', 'set_false_path ', 'set_input_delay '):
        assert dangerous not in commands
    assert script.index('open_checkpoint $checkpoint') < script.index('get_clocks -quiet board_clk_100mhz')
    for cmd in ('report_methodology -file', 'report_drc -file', 'report_clock_interaction -file',
                'report_cdc -details -file', 'check_timing -verbose -file'):
        assert cmd in script
    assert 'if {[file exists $out]}' in script


def test_power_shell_avoids_reimplementation_and_uses_preflight():
    script = (ROOT/'scripts/phase16_gap_audit.ps1').read_text()
    assert '--preflight-only' in script
    assert '--require-evidence' in script
    assert 'phase16_gap_audit.tcl' in script
    assert 'phase15' in script
    assert 'write_bitstream' not in script


def test_documented_limitations():
    s = (ROOT/'docs/phase16_board_signoff_gaps.md').read_text(encoding='utf8')
    for t in ('PROVISIONAL', 'CFGBVS', 'CONFIG_VOLTAGE', 'VCCO', '3.3',
              'NOT VERIFIED', 'report_methodology', 'no bitstream', 'Nexys 4 DDR Rev. C'):
        assert t in s


def test_cli_can_start_from_outside_repository(tmp_path):
    import subprocess
    proc = subprocess.run([sys.executable, str(ROOT/'scripts/phase16_gap_report.py'), '--help'],
                          cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert '--preflight-only' in proc.stdout


def _phase15_provenance_fixture(tmp_path, monkeypatch, xdc_bytes: bytes):
    """Exercise REAL Phase 16 provenance gate; isolate costly Phase 15 reports."""
    import hashlib
    source = (ROOT / 'constraints' / 'phase15_nexys4_ddr_rev_c.xdc').read_bytes()
    original_lf = source.replace(b'\r\n', b'\n')
    assert hashlib.sha256(original_lf).hexdigest() == p16.ACCEPTED_PHASE15_XDC_SHA256
    xc = tmp_path / 'phase15_xdc.xdc'
    xc.write_bytes(xdc_bytes)
    monkeypatch.setattr(p16, 'XDC', xc)
    phase15 = tmp_path / 'phase15'
    phase15.mkdir()
    saved = {
        'verdict': 'CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED',
        'issues': [],
        'xdc_sha256': p16.ACCEPTED_PHASE15_XDC_SHA256,
        'checkpoint_sha256': 'a'*64,
    }
    (phase15 / 'verification.json').write_text(json.dumps(saved), encoding='utf-8')

    # Existing Phase 15 candidate parser already verifies 6-port exact XDC;
    # emulate its result only to isolate the Phase 16 raw-byte hash comparison.
    def phase15_inspect(_root, _xdc):
        return {
            'verdict': 'CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED',
            'issues': [],
            'checkpoint_sha256': 'a'*64,
            'xdc_sha256': p16.file_hash(xc),
            'internal_setup_slack_ns': 1.471,
            'internal_hold_slack_ns': 0.022,
        }
    monkeypatch.setattr(p16, 'inspect_phase15', phase15_inspect)
    return phase15, xc, original_lf


@pytest.mark.parametrize('endings,expected_mode', [
    ('LF','BYTE_IDENTICAL'),
    ('CRLF','CRLF_CHECKOUT_EQUIVALENT_TO_ACCEPTED_LF'),
])
def test_real_phase15_xdc_line_ending_equivalence(tmp_path, monkeypatch, endings, expected_mode):
    canonical = (ROOT / 'constraints' / 'phase15_nexys4_ddr_rev_c.xdc').read_bytes().replace(b'\r\n', b'\n')
    raw = canonical if endings == 'LF' else canonical.replace(b'\n', b'\r\n')
    phase15, _, _ = _phase15_provenance_fixture(tmp_path, monkeypatch, raw)
    candidate = p16.baseline(phase15)
    assert candidate['xdc_provenance_mode'] == expected_mode
    assert candidate['accepted_xdc_sha256'] == p16.ACCEPTED_PHASE15_XDC_SHA256


@pytest.mark.parametrize('mutation', ['pin_swap','changed_comment','mixed_endings','bare_cr'])
def test_provenance_rejects_more_than_line_endings(tmp_path, monkeypatch, mutation):
    canonical = (ROOT / 'constraints' / 'phase15_nexys4_ddr_rev_c.xdc').read_bytes().replace(b'\r\n', b'\n')
    if mutation == 'pin_swap':
        bad = canonical.replace(b'PACKAGE_PIN C4', b'PACKAGE_PIN D4')
    elif mutation == 'changed_comment':
        bad = canonical + b'# new content\n'
    elif mutation == 'mixed_endings':
        bad = canonical.replace(b'\n', b'\r\n', 1)
    else:
        bad = canonical.replace(b'\n', b'\r', 1)
    phase15, _, _ = _phase15_provenance_fixture(tmp_path, monkeypatch, bad)
    with pytest.raises(ValueError, match='XDC content differs'):
        p16.baseline(phase15)


def test_provenance_rejects_tampered_saved_xdc_digest(tmp_path, monkeypatch):
    canonical = (ROOT / 'constraints' / 'phase15_nexys4_ddr_rev_c.xdc').read_bytes().replace(b'\r\n', b'\n')
    phase15, _, _ = _phase15_provenance_fixture(tmp_path, monkeypatch, canonical)
    saved_path = phase15 / 'verification.json'
    saved = json.loads(saved_path.read_text())
    saved['xdc_sha256'] = 'e'*64
    saved_path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='pinned original'):
        p16.baseline(phase15)
