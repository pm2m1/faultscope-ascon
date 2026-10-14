"""Phase 15 provisional board constraint, interface and review-policy tests."""
from __future__ import annotations
import copy
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.phase15_board_report import validate_xdc, inspect, PINS

XDC = ROOT / 'constraints/phase15_nexys4_ddr_rev_c.xdc'


def test_official_six_port_mapping():
    assert PINS == {
        'clk': ('IN', 'E3'), 'rst_n': ('IN', 'C12'),
        'uart_rx_i': ('IN', 'C4'), 'uart_tx_o': ('OUT', 'D4'),
        'led_busy_o': ('OUT', 'H17'), 'led_alarm_o': ('OUT', 'K15')}
    validate_xdc(XDC)


@pytest.mark.parametrize('extra', [
    'set_false_path -from [get_ports {rst_n}]',
    'set_input_delay -clock board_clk_100mhz 1 [get_ports uart_rx_i]',
    'set_clock_groups -asynchronous -group [get_clocks board_clk_100mhz]',
    'set_property PACKAGE_PIN D4 [get_ports {uart_rx_i}]',
])
def test_prohibit_unjustified_extra_constraints(tmp_path, extra):
    xdc = tmp_path / 'test.xdc'
    xdc.write_text(XDC.read_text(encoding='utf-8') + '\n' + extra + '\n')
    with pytest.raises(ValueError):
        validate_xdc(xdc)


@pytest.mark.parametrize('old,new', [
    ('PACKAGE_PIN C4', 'PACKAGE_PIN D4'),
    ('PACKAGE_PIN C12', 'PACKAGE_PIN F12'),
    ('-period 10.000', '-period 12.000'),
    ('IOSTANDARD LVCMOS33', 'IOSTANDARD LVCMOS18'),
])
def test_reject_wrong_pin_clock_or_voltage(tmp_path, old, new):
    xdc = tmp_path / 'test.xdc'
    xdc.write_text(XDC.read_text(encoding='utf-8').replace(old, new), encoding='utf-8')
    with pytest.raises(ValueError):
        validate_xdc(xdc)


def test_flow_uses_full_board_and_no_bitstream():
    script = (ROOT/'scripts/phase15_board_impl.tcl').read_text()
    assert 'synth_design -top faultscope_uart_top -part $part' in script
    assert 'route_design' in script and 'place_design' in script
    assert 'report_drc' in script and 'report_cdc' in script
    assert 'write_bitstream' not in script
    assert not any('HD.CLK_SRC' in line for line in script.splitlines() if not line.lstrip().startswith('#'))
    assert '-mode out_of_context' not in script.split('synth_design -top faultscope_uart_top')[1]
    assert 'set_false_path' not in script.split('synth_design -top faultscope_uart_top')[1]
    assert 'synchronizer_cells.tsv' in script


def test_reports_refuse_missing_evidence(tmp_path):
    r = inspect(tmp_path, XDC)
    assert r['verdict'] == 'NOT_VERIFIED'
    assert r['board_level_signoff'] == 'NOT VERIFIED'
    assert r['board_programmed'] is False


def test_documented_scope_is_provisional():
    doc = (ROOT/'docs/phase15_nexys4_ddr_rev_c.md').read_text()
    for token in ('PROVISIONAL', 'Rev. C', 'C4', 'D4', 'NOT VERIFIED', 'not suitable for production keys'):
        assert token in doc

@pytest.fixture
def complete_candidate(tmp_path):
    from scripts.phase15_board_report import REQUIRED
    for name in REQUIRED:
        (tmp_path / name).write_bytes(b'nonempty evidence placeholder')
    (tmp_path / 'source_context.tsv').write_text(
        'key\tvalue\n'
        'board\tPROVISIONAL Nexys 4 DDR Rev. C\n'
        'top\tfaultscope_uart_top\n'
        'part\txc7a100tcsg324-1\n'
        'design_mode\tfull_board_not_ooc\n'
        'clock_period_ns\t10.000\n'
        'vivado_version\t2026.1\n'
        'xdc\tC:/Projects/faultscope-ascon/constraints/phase15_nexys4_ddr_rev_c.xdc\n', encoding='utf-8')
    (tmp_path / 'internal_metrics.tsv').write_text(
        'key\tvalue\n'
        'register_count\t3772\n'
        'setup_path_count\t1\n'
        'hold_path_count\t1\n'
        'setup_slack_ns\t1.1\n'
        'hold_slack_ns\t0.05\n', encoding='utf-8')
    (tmp_path / 'pin_assignment.tsv').write_text(
        'port\tdirection\tpackage_pin\tiostandard\n' +
        ''.join(f'{port}\t{direction}\t{pin}\tLVCMOS33\n'
                for port, (direction, pin) in PINS.items()), encoding='utf-8')
    ff_names = [f'u_reset_sync/release_pipe_q_reg[{i}]' for i in range(3)] + [f'receiver/sync_q_reg[{i}]' for i in range(2)]
    (tmp_path / 'synchronizer_cells.tsv').write_text(
        'cell\tref_name\tasync_reg\tloc\tbel\n' +
        ''.join(f'{ff}\tFDCE\t1\tSLICE_X40Y51\tSLICEL.AFF\n' for ff in ff_names), encoding='utf-8')
    (tmp_path / 'synchronizer_edges.tsv').write_text(
        'group\tfrom_stage\tto_stage\tnet\tstatus\n'
        'reset\t0\t1\treset_net0\tDIRECT\n'
        'reset\t1\t2\treset_net1\tDIRECT\n'
        'rx\t0\t1\trx_net0\tDIRECT\n', encoding='utf-8')
    return tmp_path


def test_candidate_requires_manual_review(complete_candidate):
    result = inspect(complete_candidate, XDC)
    assert result['verdict'] == 'CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED'
    assert result['board_level_signoff'] == 'NOT VERIFIED'
    assert result['board_revision_confirmed'] is False
    assert result['external_io_timing'] == 'NOT VERIFIED'
    assert result['internal_setup_slack_ns'] == 1.1


@pytest.mark.parametrize('filename,old,new', [
    ('source_context.tsv','full_board_not_ooc','OOC'),
    ('source_context.tsv','10.000','nan'),
    ('internal_metrics.tsv','1.1','-0.01'),
    ('internal_metrics.tsv','0.05','nan'),
    ('pin_assignment.tsv','C4','D4'),
    ('pin_assignment.tsv','LVCMOS33','LVCMOS18'),
    ('synchronizer_cells.tsv','FDCE','SRL16E'),
    ('synchronizer_cells.tsv','\t1\t','\t0\t'),
    ('synchronizer_edges.tsv','\tDIRECT','\tNOT_VERIFIED'),
])
def test_candidate_rejects_broken_evidence(complete_candidate, filename, old, new):
    path = complete_candidate / filename
    text = path.read_text(encoding='utf-8')
    assert old in text
    path.write_text(text.replace(old,new),encoding='utf-8')
    assert inspect(complete_candidate, XDC)['verdict'] == 'NOT_VERIFIED'


def test_candidate_rejects_missing_report(complete_candidate):
    (complete_candidate/'post_route.dcp').unlink()
    assert inspect(complete_candidate, XDC)['verdict'] == 'NOT_VERIFIED'


def test_clock_queries_and_context_follow_open_synthesized_design():
    """Regression: pre-synthesis get_clocks caused Vivado 2026.1 No open design."""
    script = (ROOT / 'scripts/phase15_board_impl.tcl').read_text(encoding='utf-8')
    assert script.count('read_xdc $xdc') == 1
    assert script.count('synth_design -top faultscope_uart_top') == 1
    assert script.count('get_clocks -quiet board_clk_100mhz') == 1
    assert script.index('read_xdc $xdc') < script.index('synth_design -top faultscope_uart_top')
    assert script.index('synth_design -top faultscope_uart_top') < script.index('get_clocks -quiet board_clk_100mhz')
    assert script.index('get_clocks -quiet board_clk_100mhz') < script.index('opt_design')
    assert script.index('synth_design -top faultscope_uart_top') < script.index('source_context.tsv')
    assert 'create_project -in_memory' in script
    assert 'write_bitstream' not in script
