"""Phase 21 isolated negative tests; actual Vivado post-route queries run on Windows."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import phase21_reset_timing_report as review

@pytest.fixture
def dataset(tmp_path,monkeypatch):
    monkeypatch.setattr(review,'preflight',lambda p:{
        'phase17_checkpoint_sha256':'633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340',
        'phase15_checkpoint_sha256':'869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199',
        'overlay_checkout_mode':'CRLF_CHECKOUT_EQUIVALENT_TO_ACCEPTED_LF'})
    p=tmp_path/'audit';p.mkdir()
    (p/'context.tsv').write_text('key\tvalue\nphase\t21\nscope\tpost_route_read_only_reset_timing\n'
        'part\txc7a100tcsg324-1\ndesign\tcheckpoint_post_route\n'
        'vivado_version\t2026.1\nclock_name\tboard_clk_100mhz\n'
        'clock_period_ns\t10.000\ncfgbvs\tVCCO\nconfig_voltage\t3.3\n'
        'reset_external_delay_qualification\tNOT_VERIFIED\n'
        'board_oscillator_startup\tNOT_VERIFIED\nboard_reset_pulse_width\tNOT_VERIFIED\n')
    rows=['\t'.join(review.PATH_FIELDS)]
    for (g,s),(src,sink) in sorted(review.EXPECTED_CONTROL.items()):
        for d in ['max','min']:
            rows.append('\t'.join([g,s,src,sink,d,'NO_PATH_REPORTED','0','-']))
    (p/'path_observations.tsv').write_text('\n'.join(rows)+'\n')
    for name in review.REPORTS[2:]:
        (p/name).write_text(('Vivado 2026.1 reset timing diagnostic, rst_n uart_rx_i TIMING-18\n')*3)
    return p

def test_positive_all_queries_unconstrained_not_signoff(dataset):
    r=review.inspect(Path('/baseline'),dataset)
    assert r['verdict']=='RESET_TIMING_EVIDENCE_REVIEW_REQUIRED'
    assert not r['issues'] and r['timing_paths_found']==0
    assert r['external_reset_minimum_pulse_width']=='NOT VERIFIED'
    assert r['reset_recovery_removal']=='NOT VERIFIED'
    assert r['clock_pulse_report_scope']=='CLOCK_NETWORK_ONLY_NOT_EXTERNAL_RESET'


def test_single_reported_path_is_diagnostic_not_signoff(dataset):
    f=dataset/'path_observations.tsv'
    f.write_text(f.read_text().replace('NO_PATH_REPORTED\t0\t-','PATH_REPORTED\t1\t1.250',1))
    r=review.inspect(Path('/baseline'),dataset)
    assert r['verdict']=='RESET_TIMING_EVIDENCE_REVIEW_REQUIRED' and r['timing_paths_found']==1
    assert r['reset_recovery_removal']=='NOT VERIFIED'

def _rewrite_observation(dataset, *, group, stage, delay, state, count, slack):
    path=dataset/'path_observations.tsv'
    lines=path.read_text().splitlines()
    changed=False
    for i, line in enumerate(lines[1:],1):
        columns=line.split('\t')
        if columns[:2]==[group,stage] and columns[4]==delay:
            lines[i]='\t'.join(columns[:5]+[state,str(count),slack])
            changed=True
            break
    assert changed
    path.write_text('\n'.join(lines)+'\n')


def test_original_vivado_2026_1_missing_slack_is_a_diagnostic_not_pass(dataset):
    # Reproduce the user's actual 10-row export: six real rst_n paths with
    # blank SLACK fields, four release -> PRE paths with finite modeled slack.
    for stage in ('0','1','2'):
        for delay in ('max','min'):
            _rewrite_observation(dataset,group='reset',stage=stage,delay=delay,
                                 state='PATH_REPORTED',count=1,slack='')
    for stage in ('0','1'):
        for delay,slack in [('max','4.283'),('min','2.075')]:
            _rewrite_observation(dataset,group='rx',stage=stage,delay=delay,
                                 state='PATH_REPORTED',count=1,slack=slack)
    r=review.inspect(Path('/baseline'),dataset)
    assert r['verdict']=='RESET_TIMING_EVIDENCE_REVIEW_REQUIRED' and not r['issues']
    assert r['timing_paths_found']==10
    assert r['timing_paths_without_numeric_slack']==6
    assert r['timing_paths_with_numeric_slack']==4
    assert r['timing_paths_not_reported']==0
    assert sum(x['slack_ns']=='-' for x in r['timing_path_observations'])==6
    assert r['reset_recovery_removal']=='NOT VERIFIED'
    assert r['external_reset_minimum_pulse_width']=='NOT VERIFIED'


def test_new_explicit_unavailable_slack_state(dataset):
    _rewrite_observation(dataset,group='reset',stage='1',delay='min',
                         state='PATH_REPORTED_SLACK_UNAVAILABLE',count=1,slack='-')
    r=review.inspect(Path('/baseline'),dataset)
    assert r['verdict']=='RESET_TIMING_EVIDENCE_REVIEW_REQUIRED'
    assert r['timing_paths_without_numeric_slack']==1
    assert r['timing_paths_found']==1


@pytest.mark.parametrize('group,stage,delay,state,count,slack',[
    ('reset','0','min','PATH_REPORTED_SLACK_UNAVAILABLE',0,'-'),
    ('reset','0','min','PATH_REPORTED_SLACK_UNAVAILABLE',1,'1.23'),
    ('reset','0','min','PATH_REPORTED',0,''),
    ('reset','0','min','PATH_REPORTED',1,'junk'),
    ('reset','0','min','NO_PATH_REPORTED',0,''),
    ('rx','0','min','PATH_REPORTED',1,''),
    ('rx','0','min','PATH_REPORTED_SLACK_UNAVAILABLE',1,'-'),
    ('rx','0','min','PATH_REPORTED',1,'nan'),
    ('rx','0','min','PATH_REPORTED',1,'inf'),
])
def test_bad_missing_slack_classifications_fail_closed(dataset,group,stage,delay,state,count,slack):
    _rewrite_observation(dataset,group=group,stage=stage,delay=delay,
                         state=state,count=count,slack=slack)
    assert review.inspect(Path('/baseline'),dataset)['verdict']=='NOT_VERIFIED'


def test_missing_tab_column_is_not_legacy_empty_slack(dataset):
    f=dataset/'path_observations.tsv'
    lines=f.read_text().splitlines()
    lines[1]='\t'.join(lines[1].split('\t')[:-1])
    f.write_text('\n'.join(lines)+'\n')
    assert review.inspect(Path('/baseline'),dataset)['verdict']=='NOT_VERIFIED'

@pytest.mark.parametrize('file,old,new',[
    ('context.tsv','phase\t21','phase\t20'),
    ('context.tsv','post_route_read_only_reset_timing','test_scope'),
    ('context.tsv','xc7a100tcsg324-1','xc7a50tcsg324-1'),
    ('context.tsv','checkpoint_post_route','bad_design'),
    ('context.tsv','2026.1','unknown'),
    ('context.tsv','board_clk_100mhz','false_clock'),
    ('context.tsv','10.000','nan'),
    ('context.tsv','VCCO','GND'),
    ('context.tsv','3.3','1.8'),
    ('context.tsv','reset_external_delay_qualification\tNOT_VERIFIED','reset_external_delay_qualification\tVERIFIED'),
    ('context.tsv','board_reset_pulse_width\tNOT_VERIFIED','board_reset_pulse_width\tPASS'),
    ('path_observations.tsv','u_reset_sync/release_pipe_q_reg[2]/Q','u_reset_sync/release_pipe_q_reg[2]/C'),
    ('path_observations.tsv','receiver/sync_q_reg[0]/PRE','receiver/sync_q_reg[0]/D'),
    ('path_observations.tsv','NO_PATH_REPORTED','FAKE_TIMING_SIGNOFF'),
    ('path_observations.tsv','NO_PATH_REPORTED\t0\t-','NO_PATH_REPORTED\t1\t-'),
    ('path_observations.tsv','NO_PATH_REPORTED\t0\t-','PATH_REPORTED\t1\tnan'),
    ('path_observations.tsv','NO_PATH_REPORTED\t0\t-','PATH_REPORTED\t1\tinf'),
    ('path_observations.tsv','NO_PATH_REPORTED\t0\t-','QUERY_ERROR\t0\t-'),
])
def test_invalid_evidence_rejected(dataset,file,old,new):
    f=dataset/file
    t=f.read_text()
    assert old in t
    f.write_text(t.replace(old,new))
    assert review.inspect(Path('/baseline'),dataset)['verdict']=='NOT_VERIFIED'

@pytest.mark.parametrize('name',review.REPORTS)
def test_missing_report_rejected(dataset,name):
    (dataset/name).unlink()
    assert review.inspect(Path('/baseline'),dataset)['verdict']=='NOT_VERIFIED'

def test_duplicate_observation_fails(dataset):
    f=dataset/'path_observations.tsv'
    t=f.read_text()
    f.write_text(t+t.splitlines()[-1]+'\n')
    assert review.inspect(Path('/baseline'),dataset)['verdict']=='NOT_VERIFIED'

def test_duplicate_context_fails(dataset):
    with (dataset/'context.tsv').open('a') as f:
        f.write('phase\t21\n')
    assert review.inspect(Path('/baseline'),dataset)['verdict']=='NOT_VERIFIED'

def test_failing_preflight_blocks_analysis(dataset,monkeypatch):
    def bad(_):raise ValueError('checkpoint changed')
    monkeypatch.setattr(review,'preflight',bad)
    r=review.inspect(Path('/baseline'),dataset)
    assert r['verdict']=='NOT_VERIFIED' and 'checkpoint changed' in r['issues'][0]

def test_read_only_tcl_and_timing_scope():
    t=(ROOT/'scripts/phase21_reset_timing.tcl').read_text()
    for phrase in ('open_checkpoint $dcp','get_timing_paths','path_observations.tsv',
                   'report_pulse_width','report_timing_summary','check_timing','report_methodology',
                   'NO_PATH_REPORTED','PATH_REPORTED_SLACK_UNAVAILABLE','-report_unconstrained','reset_external_delay_qualification'):
        assert phrase in t
    forbidden=('write_checkpoint','write_bitstream','route_design','place_design','synth_design',
               'set_false_path','set_input_delay','set_output_delay','set_clock_groups')
    for line in t.splitlines():
        if not line.lstrip().startswith('#'):
            assert not any(cmd in line for cmd in forbidden)

def test_runner_guards_provenance():
    ps=(ROOT/'scripts/phase21_reset_timing.ps1').read_text()
    assert 'phase21_reset_timing_report.py' in ps
    assert ps.index('--preflight-only')<ps.index('phase21_reset_timing.tcl')
    assert 'post_route.dcp' in ps and 'build\\reproduction\\phase21' in ps

def test_scope_documented():
    doc=(ROOT/'docs/phase21_reset_timing.md').read_text().lower()
    for term in ('clock pulse','not external reset','recovery','removal','minimum pulse',
                 'timing-18','no bitstream','no rtl','not verified','xsim'):
        assert term in doc

def test_tcl_complete():
    if not shutil.which('tclsh'):
        pytest.skip('tclsh unavailable')
    p=ROOT/'scripts/phase21_reset_timing.tcl'
    src=f'set f [open {{{p}}} r]; set s [read $f]; close $f; if {{![info complete $s]}} {{exit 7}}; puts TCL_COMPLETE'
    res=subprocess.run(['tclsh'],input=src,text=True,capture_output=True)
    assert res.returncode==0 and 'TCL_COMPLETE' in res.stdout,res.stderr
