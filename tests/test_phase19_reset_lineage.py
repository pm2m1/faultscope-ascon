"""Phase 19 fail-closed format/lineage tests; Vivado execution is external."""
from __future__ import annotations

import sys
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import phase19_reset_lineage_report as report


@pytest.fixture
def audit(tmp_path,monkeypatch):
    monkeypatch.setattr(report,'phase18_preflight',lambda _: {
        'phase17_checkpoint_sha256':'a'*64,
        'phase15_checkpoint_sha256':'b'*64,
        'phase17_overlay_original_sha256':'c'*64,
        'overlay_checkout_mode':'BYTE_IDENTICAL',
    })
    a=tmp_path/'audit';a.mkdir()
    (a/'context.tsv').write_text('key\tvalue\nphase\t19\nscope\tpost_route_read_only_reset_lineage\n'
        'part\txc7a100tcsg324-1\ndesign\tcheckpoint_post_route\nvivado_version\t2026.1\n'
        'clock_period_ns\t10.000\ncfgbvs\tVCCO\nconfig_voltage\t3.3\n')
    (a/'reset_input.tsv').write_text('port\tbuffer_count\tbuffer_cell\tbuffer_ref\tinput_net\toutput_net\n'
        'rst_n\t1\trst_n_IBUF_inst\tIBUF\trst_n\trst_n_IBUF\n')
    ctl=['\t'.join(report.CONTROL_FIELDS)]
    src=['\t'.join(report.SOURCE_FIELDS)]
    drv=['\t'.join(report.DRIVER_FIELDS)]
    comb=['group\tstage\tcell\tref_name\tinit']
    for group,typ,pin,num in [('reset','FDCE','CLR',3),('rx','FDPE','PRE',2)]:
        for i in range(num):
            name=('u_reset_sync/release_pipe_q_reg' if group=='reset' else 'receiver/sync_q_reg')+f'[{i}]'
            root='rst_n' if group=='reset' else 'u_reset_sync/release_pipe_q_reg[2]/Q'
            ctl.append(f'{group}\t{i}\t{name}\t{typ}\t{pin}\tHIGH\tnet_{i}\t1\t{root}\tCONNECTED_REVIEW_REQUIRED')
            src.append(f'{group}\t{i}\t{name}\tpin\t{root}\tQ')
            drv.append(f'{group}\t{i}\t{pin}\tPIN\tu_lut/O\tLUT1\tO\t2\'h1')
            comb.append(f'{group}\t{i}\tu_lut\tLUT1\t2\'h1')
    (a/'controls.tsv').write_text('\n'.join(ctl)+'\n')
    (a/'startpoints.tsv').write_text('\n'.join(src)+'\n')
    (a/'control_drivers.tsv').write_text('\n'.join(drv)+'\n')
    (a/'comb_cone.tsv').write_text('\n'.join(comb)+'\n')
    (a/'release_fanout.tsv').write_text('source_cell\tendpoint_count\trx_stage0_in_endpoints\t'
        'rx_stage1_in_endpoints\tendpoint_names\n'
        'u_reset_sync/release_pipe_q_reg[2]\t3\t1\t1\treceiver/sync_q_reg[0],receiver/sync_q_reg[1],other\n')
    for f in report.REPORTS:
        (a/f).write_text(('Report of Vivado reset input rst_n TIMING-18\n')*5)
    return a


def test_positive_research_evidence_does_not_signoff(audit):
    result=report.inspect(Path('/phase17'),audit)
    assert result['issues']==[]
    assert result['verdict']=='RESET_LINEAGE_EVIDENCE_REVIEW_REQUIRED'
    assert result['control_count']==5
    assert result['actual_signal_polarity']=='MANUAL_REVIEW_REQUIRED'
    assert result['board_signoff']=='NOT VERIFIED'
    assert result['reset_recovery_removal']=='NOT VERIFIED'
    assert result['bitstream_generated'] is False
    assert len(result['report_sha256'])==9


@pytest.mark.parametrize('file,old,new',[
    ('context.tsv','phase\t19','phase\t18'),
    ('context.tsv','post_route_read_only_reset_lineage','unrelated'),
    ('context.tsv','xc7a100tcsg324-1','xc7a50tcsg324-1'),
    ('context.tsv','10.000','nan'),
    ('context.tsv','VCCO','GND'),
    ('context.tsv','3.3','1.8'),
    ('reset_input.tsv','rst_n\t1','rst_n\t0'),
    ('reset_input.tsv','\tIBUF\t','\tLUT1\t'),
    ('controls.tsv','FDCE','FDPE'),
    ('controls.tsv','HIGH','LOW'),
    ('controls.tsv','\tCLR\t','\tPRE\t'),
    ('controls.tsv','CONNECTED_REVIEW_REQUIRED','POLARITY_VERIFIED'),
    ('controls.tsv','net_0','-'),
    ('controls.tsv','\t1\trst_n\t','\t2\trst_n\t'),
    ('control_drivers.tsv','\tPIN\t','\tUNTRUSTED\t'),
    ('startpoints.tsv','u_reset_sync/release_pipe_q_reg[2]/Q','unrelated_source'),
    ('release_fanout.tsv','\t3\t1\t1\t','\t-4\t1\t1\t'),
    ('release_fanout.tsv','\t3\t1\t1\t','\t3\t9\t1\t'),
])
def test_mutation_rejected_or_flagged(audit,file,old,new):
    p=audit/file
    contents=p.read_text()
    assert old in contents
    p.write_text(contents.replace(old,new))
    result=report.inspect(Path('/phase17'),audit)
    if file=='startpoints.tsv':
        assert result['verdict']=='RESET_LINEAGE_EVIDENCE_REVIEW_REQUIRED'
        assert result['source_observations']['rx0']['observed'] is False
        assert result['actual_signal_polarity']=='MANUAL_REVIEW_REQUIRED'
    else:
        assert result['verdict']=='NOT_VERIFIED'

@pytest.mark.parametrize('name', ['context.tsv','reset_input.tsv','controls.tsv','startpoints.tsv',
    'control_drivers.tsv','comb_cone.tsv','release_fanout.tsv','check_timing.rpt','methodology.rpt'])
def test_missing_file_rejected(audit,name):
    (audit/name).unlink()
    assert report.inspect(Path('/phase17'),audit)['verdict']=='NOT_VERIFIED'


def test_duplicate_control_rejected(audit):
    f=audit/'controls.tsv';f.write_text(f.read_text()+f.read_text().splitlines()[1]+'\n')
    assert report.inspect(Path('/phase17'),audit)['verdict']=='NOT_VERIFIED'


def test_bad_baseline_fails_closed(audit,monkeypatch):
    def bad(_):raise ValueError('checkpoint hash mismatch')
    monkeypatch.setattr(report,'phase18_preflight',bad)
    r=report.inspect(Path('/phase17'),audit)
    assert r['verdict']=='NOT_VERIFIED' and 'checkpoint hash mismatch' in r['issues'][0]


def test_tcl_is_read_only_and_captures_driver_objects():
    t=(ROOT/'scripts/phase19_reset_lineage.tcl').read_text()
    for req in ('open_checkpoint $dcp','all_fanin','all_fanout','get_pins','get_ports',
                'get_property','DIRECTION == OUT','DIRECTION == IN','control_drivers.tsv',
                'startpoints.tsv','comb_cone.tsv','release_fanout.tsv','reset_input.tsv',
                'REF_PIN_NAME','report_methodology'):
        assert req in t
    for line in t.splitlines():
        if line.strip().startswith('#'): continue
        for forbidden in ('write_checkpoint','write_bitstream','read_xdc','set_false_path',
                          'set_input_delay','set_output_delay','synth_design','opt_design',
                          'place_design','route_design','set_property '):
            assert forbidden not in line


def test_runner_checks_provenance_before_opening_checkpoint():
    t=(ROOT/'scripts/phase19_reset_lineage.ps1').read_text()
    assert '--preflight-only' in t and 'phase19_reset_lineage.tcl' in t
    assert t.index('--preflight-only')<t.index('phase19_reset_lineage.tcl')
    assert "build\\reproduction\\phase19" in t


def test_no_physical_claims_in_docs():
    s=(ROOT/'docs/phase19_reset_lineage.md').read_text().lower()
    for token in ('manual','not verified','net name','polarity','lut','rst_n','recovery',
                  'physical','timing-18','no bitstream','analog','phase 17'):
        assert token in s


def test_tcl_parse_only():
    if not shutil.which('tclsh'): pytest.skip('tclsh unavailable')
    path=ROOT/'scripts/phase19_reset_lineage.tcl'
    t='set f [open {%s} r]; set data [read $f]; close $f; if {![info complete $data]} {exit 4}; puts OK\n'%path
    p=subprocess.run(['tclsh'],input=t,text=True,capture_output=True)
    assert p.returncode==0 and 'OK' in p.stdout, p.stderr
