"""Phase 20 diagnostic contract tests. Vivado DCP is still required on Windows."""
from __future__ import annotations
import csv
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import phase20_exact_pin_report as review

@pytest.fixture
def sample(tmp_path,monkeypatch):
    monkeypatch.setattr(review,'preflight',lambda _:{'phase17_checkpoint_sha256':'633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340',
                                                      'phase15_checkpoint_sha256':'a'*64,'overlay_checkout_mode':'BYTE_IDENTICAL'})
    d=tmp_path/'pin_trace';d.mkdir()
    (d/'context.tsv').write_text('key\tvalue\nphase\t20\nscope\tpost_route_read_only_pin_exact_trace\n'
        'part\txc7a100tcsg324-1\ndesign\tcheckpoint_post_route\nvivado_version\t2026.1\n'
        'clock_name\tboard_clk_100mhz\nclock_period_ns\t10.000\ncfgbvs\tVCCO\nconfig_voltage\t3.3\n')
    with (d/'pin_edges.tsv').open('w',newline='') as f:
        wr=csv.DictWriter(f,delimiter='\t',fieldnames=review.EDGE_FIELDS);wr.writeheader()
        for key,(src,dst,status) in review.EDGE_SPECS.items():
            first=key=='reset_port_to_ibuf'
            if src.startswith('rst_n_IBUF'):ref='IBUF'
            elif src.startswith('u_reset_sync/release_pipe_q_reg'):ref='FDCE'
            else:ref='LUT1'
            wr.writerow({'edge':key,'src_object':src,'dst_object':dst,'src_direction':'IN' if first else 'OUT',
                         'dst_direction':'IN','src_segments':'net_'+key,'dst_segments':'net_'+key,
                         'shared_segments':'net_'+key,'leaf_drivers':'-' if first else src+'|'+ref,
                         'driver_count':'0' if first else '1','status':status})
    (d/'lut_truth.tsv').write_text('role\tcell\tref_name\tinit\ti0_pin\to_pin\ttruth_status\n'
        "reset\tu_reset_sync/release_pipe_q[2]_i_1\tLUT1\t2'h1\tu_reset_sync/release_pipe_q[2]_i_1/I0\tu_reset_sync/release_pipe_q[2]_i_1/O\tONE_INPUT_INVERTER\n"
        "release\tu_reset_sync/FSM_sequential_state_q[1]_i_2\tLUT1\t2'h1\tu_reset_sync/FSM_sequential_state_q[1]_i_2/I0\tu_reset_sync/FSM_sequential_state_q[1]_i_2/O\tONE_INPUT_INVERTER\n")
    (d/'preset_startpoints.tsv').write_text('rx_stage\tcontrol_pin\tstartpoint_class\tstartpoint_name\tstartpoint_ref_pin\n'
        '0\treceiver/sync_q_reg[0]/PRE\tpin\tu_reset_sync/release_pipe_q_reg[2]/C\tC\n'
        '1\treceiver/sync_q_reg[1]/PRE\tpin\tu_reset_sync/release_pipe_q_reg[2]/C\tC\n')
    (d/'check_timing.rpt').write_text('External rst_n and uart_rx_i still unconstrained.\n'*5)
    (d/'methodology.rpt').write_text('Five TIMING-18 external input output delays missing.\n'*5)
    return d


def write_change(path,old,new):
    t=path.read_text()
    assert old in t
    path.write_text(t.replace(old,new,1))


def test_complete_candidate_is_not_board_signoff(sample):
    r=review.inspect(Path('/baseline'),sample)
    assert r['verdict']=='PIN_LEVEL_EVIDENCE_REVIEW_REQUIRED'
    assert r['physical_netlist_chain']=='CANDIDATE_ALL_EIGHT_LINKS_OBSERVED'
    assert r['physical_reset_polarity']=='NOT VERIFIED'
    assert r['board_signoff']=='NOT VERIFIED'
    assert r['unresolved_edges']==[]
    assert len(r['pin_edge_status'])==8


def test_missing_q_to_lut_remains_unresolved_not_pass(sample):
    lines=(sample/'pin_edges.tsv').read_text().splitlines()
    lines=[line.replace('SEGMENT_AND_SINGLE_EXPECTED_DRIVER','UNRESOLVED') if line.startswith('release_q_to_lut\t') else line for line in lines]
    (sample/'pin_edges.tsv').write_text('\n'.join(lines)+'\n')
    r=review.inspect(Path('/baseline'),sample)
    assert r['verdict']=='PIN_LEVEL_EVIDENCE_REVIEW_REQUIRED'
    assert r['physical_netlist_chain']=='INCOMPLETE_OR_AMBIGUOUS_REQUIRES_REVIEW'
    assert r['unresolved_edges']==['release_q_to_lut']


@pytest.mark.parametrize('file,old,new',[
    ('context.tsv','phase\t20','phase\t19'),
    ('context.tsv','post_route_read_only_pin_exact_trace','unexpected_scope'),
    ('context.tsv','xc7a100tcsg324-1','xc7a50tcsg324-1'),
    ('context.tsv','10.000','nan'),
    ('context.tsv','VCCO','GND'),
    ('context.tsv','3.3','1.8'),
    ('pin_edges.tsv','release_q_to_lut','fake_q_to_lut'),
    ('pin_edges.tsv','u_reset_sync/release_pipe_q_reg[2]/Q','u_reset_sync/release_pipe_q_reg[2]/C'),
    ('pin_edges.tsv','receiver/sync_q_reg[0]/PRE','receiver/sync_q_reg[0]/D'),
    ('pin_edges.tsv','PORT_TO_IBUF_DIRECT','ELECTRICALLY_VERIFIED'),
    ('pin_edges.tsv','\t1\tSEGMENT_AND_SINGLE_EXPECTED_DRIVER','\t2\tSEGMENT_AND_SINGLE_EXPECTED_DRIVER'),
    ('pin_edges.tsv','\tnet_reset_ibuf_to_lut\t','\t-\t'),
    ('lut_truth.tsv',"2'h1","2'h2"),
    ('lut_truth.tsv','LUT1','LUT2'),
    ('lut_truth.tsv','ONE_INPUT_INVERTER','BOOLEAN_SIGNED_OFF'),
    ('preset_startpoints.tsv','receiver/sync_q_reg[0]/PRE','receiver/sync_q_reg[0]/CLR'),
])
def test_tampering_must_fail(sample,file,old,new):
    write_change(sample/file,old,new)
    assert review.inspect(Path('/baseline'),sample)['verdict']=='NOT_VERIFIED'


@pytest.mark.parametrize('filename',review.REPORTS)
def test_missing_evidence_fails(sample,filename):
    (sample/filename).unlink()
    assert review.inspect(Path('/baseline'),sample)['verdict']=='NOT_VERIFIED'


def test_duplicate_net_edge_fails(sample):
    p=sample/'pin_edges.tsv'
    t=p.read_text();p.write_text(t+t.splitlines()[-1]+'\n')
    assert review.inspect(Path('/baseline'),sample)['verdict']=='NOT_VERIFIED'


def test_baseline_provenance_fails_closed(sample,monkeypatch):
    def bad(_):raise ValueError('tampered DCP')
    monkeypatch.setattr(review,'preflight',bad)
    r=review.inspect(Path('/baseline'),sample)
    assert r['verdict']=='NOT_VERIFIED' and 'tampered DCP' in r['issues'][0]


def test_tcl_explicit_links_and_no_mutation():
    t=(ROOT/'scripts/phase20_exact_pin_trace.tcl').read_text()
    for item in ('open_checkpoint $dcp','release_q_to_lut','reset_port_to_ibuf','reset_ibuf_to_lut',
                 'reset_lut_to_clr','release_lut_to_pre','get_nets -quiet -segments',
                 'p20drivers','p20pin','I0','INIT','preset_startpoints.tsv'):
        assert item in t
    for forbidden in ('write_bitstream','write_checkpoint','read_xdc','set_false_path','set_input_delay',
                      'set_output_delay','place_design','route_design','synth_design','set_property'):
        assert not any(forbidden in line for line in t.splitlines() if not line.lstrip().startswith('#'))


def test_powershell_checks_provenance_before_vivado():
    t=(ROOT/'scripts/phase20_exact_pin_trace.ps1').read_text()
    assert 'phase20_exact_pin_report.py' in t and '--preflight-only' in t
    assert t.index('--preflight-only') < t.index('phase20_exact_pin_trace.tcl')
    assert 'post_route.dcp' in t and 'build\\reproduction\\phase20' in t


def test_docs_honestly_preserve_open_gaps():
    d=(ROOT/'docs/phase20_exact_pin_trace.md').read_text().lower()
    for x in ('not verified','bounce','/c','/q','timing-18','unresolved','no bitstream'):
        assert x in d


def test_tcl_syntax_complete():
    if not shutil.which('tclsh'):pytest.skip('tclsh unavailable')
    path=ROOT/'scripts/phase20_exact_pin_trace.tcl'
    cmd=f'set f [open {{{path}}} r]; set code [read $f]; close $f; if {{![info complete $code]}} {{exit 5}}; puts TCL_PARSE_COMPLETE'
    run=subprocess.run(['tclsh'],input=cmd,text=True,capture_output=True)
    assert run.returncode==0 and 'TCL_PARSE_COMPLETE' in run.stdout,run.stderr
