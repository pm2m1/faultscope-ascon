"""Phase 18 fail-closed evidence tests; actual Vivado and XSim remain external."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import phase18_async_report as review

@pytest.fixture
def fake_candidate(tmp_path,monkeypatch):
    expected = {'phase17_checkpoint_sha256':'a'*64,
                'phase15_checkpoint_sha256':'b'*64,
                'phase17_overlay_original_sha256':'c'*64,
                'overlay_checkout_mode':'BYTE_IDENTICAL',
                'phase17_setup_slack_ns':1.471,'phase17_hold_slack_ns':0.022}
    monkeypatch.setattr(review,'preflight',lambda _: expected)
    a=tmp_path/'audit'; a.mkdir()
    (a/'context.tsv').write_text('key\tvalue\nphase\t18\nscope\tpost_route_read_only_async_boundary\n'
        'part\txc7a100tcsg324-1\ndesign\tcheckpoint_post_route\nvivado_version\t2026.1\n'
        'clock_name\tboard_clk_100mhz\nclock_period_ns\t10.000\ncfgbvs\tVCCO\nconfig_voltage\t3.3\n')
    cells=[('reset',0,'FDCE'),('reset',1,'FDCE'),('reset',2,'FDCE'),('rx',0,'FDPE'),('rx',1,'FDPE')]
    lines=['group\tstage\tcell\tref_name\tasync_reg\tloc\tbel\tasync_control_net']
    for g,i,t in cells:
        n='u_reset_sync/release_pipe_q_reg' if g=='reset' else 'receiver/sync_q_reg'
        lines.append(f'{g}\t{i}\t{n}[{i}]\t{t}\t1\tSLICE_X2Y3\tAFF\treset_ctrl')
    (a/'stages.tsv').write_text('\n'.join(lines)+'\n')
    (a/'interstage_timing.tsv').write_text('group\tfrom_stage\tto_stage\tshared_qd_net\tmax_slack_ns\tmin_slack_ns\tstatus\n'
        'reset\t0\t1\tnet0\t2.4\t0.1\tDIRECT_AND_TIMED\n'
        'reset\t1\t2\tnet1\t2.4\t0.1\tDIRECT_AND_TIMED\n'
        'rx\t0\t1\trxnet\t4.5\t0.2\tDIRECT_AND_TIMED\n')
    (a/'async_input.tsv').write_text('port\tbuffer_cell\tbuffer_ref\tfirst_stage_cell\tbuffer_to_stage_net\tstatus\n'
         'uart_rx_i\tuart_rx_i_IBUF_inst\tIBUF\treceiver/sync_q_reg[0]\tuart_rx_i_IBUF\tIBUF_TO_FIRST_STAGE_DIRECT\n')
    for name in review.REPORTS:
        (a/name).write_text(('rst_n uart_rx_i TIMING-18 Vivado report review\n' * 4))
    return a

def test_positive_still_not_signoff(fake_candidate):
    r=review.inspect(Path('/phase17'),fake_candidate)
    assert r['verdict']=='ASYNC_BOUNDARY_EVIDENCE_REVIEW_REQUIRED'
    assert r['stage_count']==5 and r['rx_input_buffered_directly_to_first_stage'] is True
    assert r['uart_metastability_mtbf']=='NOT VERIFIED'
    assert r['reset_recovery_removal']=='NOT VERIFIED'
    assert r['board_signoff']=='NOT VERIFIED'
    assert r['rtl_simulation']=='SEPARATE_TEST_REQUIRED'

@pytest.mark.parametrize('filename,old,new',[
    ('context.tsv','phase\t18','phase\t17'),
    ('context.tsv','post_route_read_only_async_boundary','changed_scope'),
    ('context.tsv','xc7a100tcsg324-1','xc7a50tcsg324-1'),
    ('context.tsv','checkpoint_post_route','wrong_design'),
    ('context.tsv','board_clk_100mhz','fake_clk'),
    ('context.tsv','10.000','12.000'),
    ('context.tsv','10.000','nan'),
    ('context.tsv','VCCO','GND'),
    ('context.tsv','3.3','1.8'),
    ('stages.tsv','FDCE','SRL16E'),
    ('stages.tsv','FDPE','FDCE'),
    ('stages.tsv','\t1\tSLICE_X2Y3','\t0\tSLICE_X2Y3'),
    ('stages.tsv','SLICE_X2Y3','NOT_PLACED'),
    ('stages.tsv','reset_ctrl','-'),
    ('stages.tsv','receiver/sync_q_reg[0]','receiver/bad_reg[0]'),
    ('interstage_timing.tsv','DIRECT_AND_TIMED','NOT_VERIFIED'),
    ('interstage_timing.tsv','\trxnet\t','\t-\t'),
    ('interstage_timing.tsv','\t0.2\t','\tnan\t'),
    ('interstage_timing.tsv','\t0.2\t','\t-0.2\t'),
    ('async_input.tsv','uart_rx_i_IBUF_inst','uart_rx_i_IBUF_inst'),
    ('async_input.tsv','IBUF\treceiver/','LUT6\treceiver/'),
    ('async_input.tsv','receiver/sync_q_reg[0]','receiver/sync_q_reg[1]'),
    ('async_input.tsv','IBUF_TO_FIRST_STAGE_DIRECT','BYPASS'),
])
def test_reject_broken_evidence(fake_candidate,filename,old,new):
    f=fake_candidate/filename
    t=f.read_text()
    assert old in t
    if old==new:
        # An accidental duplicate header/data line must fail rather than deduplicate.
        f.write_text(t+t.splitlines()[-1]+'\n')
    else:
        f.write_text(t.replace(old,new))
    assert review.inspect(Path('/phase17'),fake_candidate)['verdict']=='NOT_VERIFIED'

@pytest.mark.parametrize('file', ['stages.tsv','interstage_timing.tsv','async_input.tsv',
                                 'check_timing.rpt','rx_interstage_max.rpt','methodology.rpt'])
def test_missing_evidence_fails(fake_candidate,file):
    (fake_candidate/file).unlink()
    assert review.inspect(Path('/phase17'),fake_candidate)['verdict']=='NOT_VERIFIED'

def test_absent_preflight_fail_closed(fake_candidate,monkeypatch):
    def fail(_): raise ValueError('route hash changed')
    monkeypatch.setattr(review,'preflight',fail)
    r=review.inspect(Path('/phase17'),fake_candidate)
    assert r['verdict']=='NOT_VERIFIED' and 'route hash changed' in r['issues'][0]

def test_tcl_audit_preserves_checkpoint_and_no_fake_constraints():
    t=(ROOT/'scripts/phase18_async_audit.tcl').read_text()
    assert 'open_checkpoint $dcp' in t
    for req in ('p18shared','stages.tsv','interstage_timing.tsv','async_input.tsv',
                'IBUF_TO_FIRST_STAGE_DIRECT','report_methodology','check_timing',
                'get_timing_paths','report_cdc','ASYNC_REG','all_fanout'):
        assert req in t
    for prohibited in ('write_bitstream','write_checkpoint','set_false_path',
                       'set_input_delay','set_output_delay','route_design','place_design','synth_design'):
        assert not any(prohibited in line for line in t.splitlines() if not line.lstrip().startswith('#'))

def test_runner_requires_read_only_and_provenance():
    t=(ROOT/'scripts/phase18_async_audit.ps1').read_text()
    assert 'phase18_async_report.py' in t and '--preflight-only' in t
    assert "post_route.dcp" in t and 'phase18_async_audit.tcl' in t
    assert t.index('--preflight-only')<t.index('phase18_async_audit.tcl')
    assert 'build\\reproduction\\phase18' in t

def test_simulation_is_genuine_hdl_and_marker_gated():
    ps=(ROOT/'scripts/phase18_xsim.ps1').read_text()
    tb=(ROOT/'tests/rtl/phase18_async_tb.sv').read_text()
    for req in ('xvlog.bat','xelab.bat','xsim.bat','PHASE18_XSIM_PASS','Select-String'):
        assert req in ps
    assert 'fs_reset_sync.sv' in ps and 'fs_uart_rx.sv' in ps
    for req in ('fs_reset_sync u_reset_sync','fs_uart_rx #','send_byte(8\'hA6)','send_byte(8\'h35)',
                'rst_n_core !== 1\'b0','$fatal','PHASE18_XSIM_PASS:'):
        assert req in tb

def test_documentation_is_explicit_on_open_gaps():
    doc=(ROOT/'docs/phase18_async_boundary.md').read_text()
    for req in ('PROVISIONAL','NOT VERIFIED','metastability','MTBF','bounce','TIMING-18',
                'no bitstream','no RTL','original', 'XSim'):
        assert req.lower() in doc.lower()

def test_tcl_is_syntactically_complete():
    import subprocess
    import shutil
    if not shutil.which('tclsh'):
        pytest.skip('tclsh not found for Tcl parse-only check')
    p=ROOT/'scripts/phase18_async_audit.tcl'
    # info complete parses groups without executing Vivado commands.
    script=f'set f [open {{{p}}} r]; set x [read $f]; close $f; if {{![info complete $x]}} {{exit 4}}; puts TCL_PARSE_COMPLETE'
    res=subprocess.run(['tclsh'], input=script,text=True,capture_output=True)
    assert res.returncode==0 and 'TCL_PARSE_COMPLETE' in res.stdout,repr(res.stderr)
