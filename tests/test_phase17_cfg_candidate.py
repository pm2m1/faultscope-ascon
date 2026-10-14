"""Phase 17 config-voltage experiment; fail-closed behavior and no signoff claim."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import phase17_cfg_review as r


@pytest.fixture
def accepted(monkeypatch):
    b={'checkpoint_sha256':'869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199',
       'accepted_xdc_sha256':'69bddc36a6142b41c47e4335bd3cb56e1051fe0cf52a33491fdcfd2338ffa4d8',
       'xdc_provenance_mode':'CRLF_CHECKOUT_EQUIVALENT_TO_ACCEPTED_LF',
       'internal_setup_slack_ns':1.471,'internal_hold_slack_ns':0.022}
    monkeypatch.setattr(r,'baseline',lambda _p:dict(b))
    return b


@pytest.fixture
def candidate(tmp_path,accepted):
    def wr(name,s):
        p=tmp_path/name;p.write_text(s,encoding='utf-8')
    wr('source_context.tsv','key\tvalue\nphase\t17\nboard\tPROVISIONAL Nexys 4 DDR Rev. C\n'
       'part\txc7a100tcsg324-1\ntop\tfaultscope_uart_top\n'
       'vivado_version\t2026.1\nrtl_sources\t'+','.join(r.RTLS)+'\n'
       'xdc\tC:/Projects/faultscope-ascon/constraints/phase15_nexys4_ddr_rev_c.xdc\n'
       'overlay\tC:/Projects/faultscope-ascon/constraints/phase17_cfg_rev_c_overlay.xdc\n'
       'design_mode\tfull_board_not_ooc\nclock_period_ns\t10.000\n'
       'cfgbvs\tVCCO\nconfig_voltage\t3.3\n')
    wr('internal_metrics.tsv','key\tvalue\nregister_count\t3772\nsetup_path_count\t1\n'
       'hold_path_count\t1\nsetup_slack_ns\t1.420\nhold_slack_ns\t0.029\n')
    wr('pin_assignment.tsv','port\tdirection\tpackage_pin\tiostandard\n'+
       ''.join(f'{k}\t{d}\t{pin}\tLVCMOS33\n' for k,(d,pin) in r.PINS.items()))
    ffs=[f'u_reset_sync/release_pipe_q_reg[{i}]' for i in range(3)]+[f'receiver/sync_q_reg[{i}]' for i in range(2)]
    wr('synchronizer_cells.tsv','cell\tref_name\tasync_reg\tloc\tbel\n'+
       ''.join(f'{name}\tFDCE\t1\tSLICE_X40Y51\tSLICEL.AFF\n' for name in ffs))
    wr('synchronizer_edges.tsv','group\tfrom_stage\tto_stage\tnet\tstatus\n'
       'reset\t0\t1\treset0\tDIRECT\nreset\t1\t2\treset1\tDIRECT\nrx\t0\t1\trx0\tDIRECT\n')
    for name in r.REQUIRED_REPORTS:
        wr(name,'Vivado 2026.1 synthetic fixture\nReport DRC\n1. REPORT SUMMARY\n' if name=='post_route_drc.rpt' else 'synthetic fixture\n')
    return tmp_path


def test_overlay_exact_proposal():
    r.validate_overlay()


@pytest.mark.parametrize('mut',[
    'set_property CFGBVS GND [current_design]',
    'set_property CONFIG_VOLTAGE 1.8 [current_design]',
    'set_property CFGBVS VCCO [current_design]\nset_false_path -from [get_ports rst_n]',
    'set_property PACKAGE_PIN A1 [get_ports clk]',
])
def test_overlay_mutations_rejected(tmp_path,mut):
    raw=r.OVERLAY.read_text(encoding='utf-8')
    if 'CFGBVS GND' in mut: raw=raw.replace('CFGBVS VCCO','CFGBVS GND')
    elif 'VOLTAGE 1.8' in mut: raw=raw.replace('VOLTAGE 3.3','VOLTAGE 1.8')
    else: raw+='\n'+mut+'\n'
    p=tmp_path/'overlay.xdc';p.write_text(raw)
    with pytest.raises(ValueError):r.validate_overlay(p)


def test_candidate_requires_review(candidate):
    x=r.inspect(ROOT,candidate)
    assert x['verdict']=='ROUTED_CFG_CANDIDATE_REVIEW_REQUIRED'
    assert x['board_signoff']=='NOT VERIFIED'
    assert x['board_revision_confirmed'] is False
    assert x['bitstream_generated'] is False
    assert x['setup_delta_vs_phase15_ns']==-0.051
    assert x['hold_delta_vs_phase15_ns']==0.007


def test_preflight_only_accepted(accepted):
    x=r.inspect(ROOT,None)
    assert x['verdict']=='BASELINE_AND_OVERLAY_VERIFIED'
    assert x['phase15_checkpoint_sha256']==accepted['checkpoint_sha256']


@pytest.mark.parametrize('filename,old,new',[
    ('source_context.tsv','cfgbvs\tVCCO','cfgbvs\tGND'),
    ('source_context.tsv','config_voltage\t3.3','config_voltage\t1.8'),
    ('source_context.tsv','clock_period_ns\t10.000','clock_period_ns\t12.000'),
    ('source_context.tsv','full_board_not_ooc','out_of_context'),
    ('source_context.tsv','phase\t17','phase\t15'),
    ('source_context.tsv','2026.1','broken-version'),
    ('source_context.tsv','ascon_round.sv','changed_round.sv'),
    ('source_context.tsv','phase15_nexys4_ddr_rev_c.xdc','phase15_other.xdc'),
    ('source_context.tsv','phase17_cfg_rev_c_overlay.xdc','bad_overlay.xdc'),
    ('pin_assignment.tsv','C4','D4'),
    ('pin_assignment.tsv','LVCMOS33','LVCMOS18'),
    ('synchronizer_cells.tsv','FDCE','SRL16E'),
    ('synchronizer_cells.tsv','\t1\t','\t0\t'),
    ('synchronizer_edges.tsv','\tDIRECT','\tNOT_VERIFIED'),
    ('internal_metrics.tsv','setup_slack_ns\t1.420','setup_slack_ns\t-0.001'),
    ('internal_metrics.tsv','hold_slack_ns\t0.029','hold_slack_ns\tnan'),
    ('post_route_drc.rpt','Report DRC','CFGBVS-1 Warning\nReport DRC'),
])
def test_mutation_rejected(candidate,filename,old,new):
    path=candidate/filename
    s=path.read_text(encoding='utf-8');assert old in s
    path.write_text(s.replace(old,new),encoding='utf-8')
    assert r.inspect(ROOT,candidate)['verdict']=='NOT_VERIFIED'


@pytest.mark.parametrize('name',['post_route.dcp','methodology.rpt','source_context.tsv','synchronizer_cells.tsv'])
def test_missing_report_fails(candidate,name):
    (candidate/name).unlink()
    assert r.inspect(ROOT,candidate)['verdict']=='NOT_VERIFIED'


def test_failed_baseline_never_accepted(monkeypatch,candidate):
    def bad(_p):raise ValueError('bad phase15 SHA-256')
    monkeypatch.setattr(r,'baseline',bad)
    assert 'bad phase15' in r.inspect(ROOT,candidate)['issues'][0]


def test_tcl_contract_and_order():
    t=(ROOT/'scripts/phase17_cfg_impl.tcl').read_text(encoding='utf-8')
    assert t.index('read_xdc $xdc')<t.index('synth_design -top faultscope_uart_top')<t.index('read_xdc $overlay')<t.index('opt_design')<t.index('place_design')<t.index('route_design')
    assert 'CFGBVS [current_design]' in t and 'CONFIG_VOLTAGE [current_design]' in t
    assert 'report_methodology' in t and 'report_drc' in t
    assert 'write_bitstream' not in '\n'.join(line for line in t.splitlines() if not line.lstrip().startswith('#'))
    assert t.count('route_design\n')==1
    assert 'synchronizer_cells.tsv' in t and 'synchronizer_edges.tsv' in t
    assert 'source_context.tsv' in t


def test_windows_runner_protects_baseline():
    s=(ROOT/'scripts/phase17_cfg_candidate.ps1').read_text(encoding='utf-8')
    assert 'phase17_cfg_review.py' in s
    assert '--preflight-only' in s
    assert 'git diff --quiet HEAD -- rtl' in s
    assert 'phase17_cfg_impl.tcl' in s
    assert 'build\\reproduction\\phase17' in s
    assert 'write_bitstream' not in s


def test_doc_scope():
    doc=(ROOT/'docs/phase17_cfg_rev_c_pilot.md').read_text(encoding='utf-8')
    for val in ('PROVISIONAL','Rev. C','VCCO','3.3','CFGBVS-1',
                'NOT VERIFIED','Phase 15','Phase 16','UART','bitstream'):
        assert val in doc
