"""Phase 22 positive and fail-closed evidence tests (no Vivado required)."""
import csv
import json
from pathlib import Path
import re
import shutil
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import phase22_timing_query_report as p22

GOOD_PREFLIGHT={'phase17_checkpoint_sha256':'633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340',
                'phase15_checkpoint_sha256':'869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199',
                'overlay_checkout_mode':'CRLF_CHECKOUT_EQUIVALENT_TO_ACCEPTED_LF'}


def write_tsv(file, header, rows):
    with file.open('w',encoding='utf-8',newline='') as f:
        writer=csv.writer(f,delimiter='\t',lineterminator='\n')
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture
def valid(tmp_path,monkeypatch):
    monkeypatch.setattr(p22,'preflight',lambda p:dict(GOOD_PREFLIGHT))
    audit=tmp_path/'audit'; audit.mkdir()
    write_tsv(audit/'context.tsv',['key','value'],[
        ('phase','22'),('scope','post_route_read_only_path_binding'),
        ('part','xc7a100tcsg324-1'),('design','faultscope_uart_top'),
        ('vivado_version','2026.1'),('clock_name','board_clk_100mhz'),
        ('clock_period_ns','10.000'),('cfgbvs','VCCO'),('config_voltage','3.3'),
        ('external_delay_model','NOT_QUALIFIED'),('board_revision','PROVISIONAL'),
        ('physical_reset_signoff','NOT_VERIFIED')])
    write_tsv(audit/'ports.tsv',p22.PORT_FIELDS,[(port,d,pin,'LVCMOS33') for port,(d,pin) in p22.PINS.items()])
    rows=[]
    for (g,s),(src,sink) in p22.SOURCES.items():
        for delay in ('max','min'):
            file=f'path_{g}{s}_{delay}.rpt'
            state='PATH_REPORTED_SLACK_UNAVAILABLE' if g=='reset' else 'PATH_REPORTED'
            slack='-' if g=='reset' else ('4.283' if delay=='max' else '2.075')
            rows.append((g,s,delay,src,sink,state,'1',slack,file,'REPORT_WRITTEN'))
            reported_src=src if g=='reset' else 'u_reset_sync/release_pipe_q_reg[2]/C'
            typ='Recovery' if delay=='max' else 'Removal'
            shown_slack='inf' if g=='reset' else slack
            report=(f'| Tool Version : Vivado 2026.1\n'
                    f'| Command      : report_timing -of_objects fake_path -file {file}\n'
                    f'| Design : faultscope_uart_top\n'
                    f'Timing Report\nSlack (MET) : {shown_slack}ns\n'
                    f'  Source:                 {reported_src}\n'
                    f'  Destination:            {sink}\n'
                    f'  Path Type:              {typ} (Max at Slow Process Corner)\n'
                    f'  Logic Levels:           1\n')
            (audit/file).write_text(report,encoding='utf-8')
    write_tsv(audit/'path_bindings.tsv',p22.PATH_FIELDS,rows)
    (audit/'check_timing.rpt').write_text('check_timing: no_input_delay rst_n uart_rx_i; no_output_delay uart_tx_o led_busy_o led_alarm_o'+(' .'*5),encoding='utf-8')
    m='Report Methodology\n'
    for idx,(typ,port) in enumerate(sorted(p22.EXPECTED_WARNINGS),1):
        m+=f'TIMING-18#{idx} Warning\nAn {typ} delay is missing on {port} relative to the rising and/or falling clock edge(s) of board_clk_100mhz.\n'
    (audit/'methodology.rpt').write_text(m,encoding='utf-8')
    (audit/'timing_summary.rpt').write_text('Vivado 2026.1 Timing Summary Report\n'+('valid summary\n'*10),encoding='utf-8')
    return audit


def inspect(audit):
    return p22.inspect(Path('fake-phase17'),audit)


def replace(audit,name,old,new):
    path=audit/name
    content=path.read_text(encoding='utf-8')
    assert old in content, (name,old)
    path.write_text(content.replace(old,new,1),encoding='utf-8')


def test_complete_candidate_review_not_physical_signoff(valid):
    d=inspect(valid)
    assert d['verdict']=='PATH_OBJECT_REPORTS_REVIEW_REQUIRED'
    assert not d['issues'] and d['paths_with_rendered_reports']==10
    assert len(d['timing_startpoint_mismatches'])==4
    assert d['external_input_output_timing']=='NOT QUALIFIED'
    assert d['board_signoff']=='NOT VERIFIED'
    assert d['timing_constraints_modified'] is False
    assert len(d['report_sha256'])==16


def test_preflight_provenance_fails_closed(monkeypatch):
    monkeypatch.setattr(p22,'phase21_preflight',lambda _:dict(GOOD_PREFLIGHT,phase17_checkpoint_sha256='tampered'))
    with pytest.raises(ValueError,match='provenance'):
        p22.preflight(Path('fake'))


@pytest.mark.parametrize('name,old,new',[
    ('context.tsv','phase\t22','phase\t21'),
    ('context.tsv','PROVISIONAL','CONFIRMED'),
    ('context.tsv','NOT_QUALIFIED','QUALIFIED'),
    ('context.tsv','3.3','1.8'),
    ('context.tsv','10.000','nan'),
    ('ports.tsv','rst_n\tIN\tC12','rst_n\tIN\tC13'),
    ('ports.tsv','uart_rx_i\tIN\tC4','uart_rx_i\tOUT\tC4'),
    ('ports.tsv','LVCMOS33','LVCMOS18'),
    ('path_bindings.tsv','release_pipe_q_reg[2]/Q','release_pipe_q_reg[2]/C'),
    ('path_bindings.tsv','PATH_REPORTED_SLACK_UNAVAILABLE','FAKE_PASS'),
    ('path_bindings.tsv','PATH_REPORTED_SLACK_UNAVAILABLE\t1\t-','PATH_REPORTED\t1\t-'),
    ('path_bindings.tsv','PATH_REPORTED\t1\t4.283','PATH_REPORTED\t1\tinf'),
    ('path_bindings.tsv','path_rx0_max.rpt','path_rx3_max.rpt'),
    ('path_rx0_max.rpt','report_timing -of_objects','report_timing -from'),
    ('path_rx0_max.rpt','receiver/sync_q_reg[0]/PRE','receiver/sync_q_reg[1]/PRE'),
    ('path_rx0_max.rpt','u_reset_sync/release_pipe_q_reg[2]/C','totally_unrelated/C'),
    ('path_rx0_max.rpt','Path Type:              Recovery','Path Type:              Removal'),
    ('path_rx0_max.rpt','Slack (MET) : 4.283ns','Slack (MET) : 3.283ns'),
    ('path_reset0_max.rpt','Slack (MET) : infns','Slack (MET) : 0.100ns'),
    ('methodology.rpt','uart_rx_i','uart_fake_input'),
    ('check_timing.rpt','led_alarm_o','wrong_led'),
    ('timing_summary.rpt','Timing Summary Report','Other Report'),
])
def test_evidence_tampering_is_rejected(valid,name,old,new):
    replace(valid,name,old,new)
    assert inspect(valid)['verdict']=='NOT_VERIFIED'


@pytest.mark.parametrize('name',p22.REPORTS)
def test_missing_evidence_fails_closed(valid,name):
    (valid/name).unlink()
    assert inspect(valid)['verdict']=='NOT_VERIFIED'


def test_duplicate_timing_row_fails(valid):
    f=valid/'path_bindings.tsv'
    lines=f.read_text().splitlines()
    f.write_text('\n'.join(lines+[lines[1]])+'\n')
    assert inspect(valid)['verdict']=='NOT_VERIFIED'


def test_missing_field_fails(valid):
    replace(valid,'path_bindings.tsv','\tREPORT_WRITTEN','\t')
    assert inspect(valid)['verdict']=='NOT_VERIFIED'


def test_internal_blank_slack_fails(valid):
    replace(valid,'path_bindings.tsv','PATH_REPORTED\t1\t4.283','PATH_REPORTED_SLACK_UNAVAILABLE\t1\t-')
    assert inspect(valid)['verdict']=='NOT_VERIFIED'


def test_missing_path_can_only_be_unverified(valid):
    replace(valid,'path_bindings.tsv','PATH_REPORTED_SLACK_UNAVAILABLE\t1\t-\tpath_reset0_max.rpt\tREPORT_WRITTEN',
            'NO_PATH_REPORTED\t0\t-\tpath_reset0_max.rpt\tNO_PATH_REPORTED')
    (valid/'path_reset0_max.rpt').write_text('NO_PATH_REPORTED for reset 0 max: rst_n to u_reset_sync/release_pipe_q_reg[0]/CLR\n')
    d=inspect(valid)
    assert d['verdict']=='PATH_OBJECT_REPORTS_REVIEW_REQUIRED'
    assert d['paths_with_rendered_reports']==9
    assert d['board_signoff']=='NOT VERIFIED'


def test_c_startpoint_mismatch_flagged_never_claimed_q(valid):
    d=inspect(valid)
    r=next(x for x in d['timing_path_observations'] if x['report_file']=='path_rx0_max.rpt')
    assert r['source_query_mismatch'] is True
    assert r['reported_source'].endswith('/C')


def test_tcl_uses_path_objects_not_grouped_reports():
    script=(Path(__file__).resolve().parents[1]/'scripts/phase22_timing_query_integrity.tcl').read_text()
    active='\n'.join(line for line in script.splitlines() if not line.lstrip().startswith('#'))
    assert 'get_timing_paths -quiet -from $src -to $dst -delay_type $delay -max_paths 1' in active
    assert 'report_timing -of_objects $p -file $path_file' in active
    assert not re.search(r'\breport_timing\s+-from\b',active)
    for forbidden in ('set_property','create_clock','write_checkpoint','write_bitstream',
                      'place_design','route_design','synth_design','set_input_delay','set_output_delay','set_false_path'):
        assert not re.search(r'\b'+forbidden+r'\b',active)


def test_powershell_runs_provenance_first_and_no_mutation():
    s=(Path(__file__).resolve().parents[1]/'scripts/phase22_timing_query_integrity.ps1').read_text()
    assert s.index('--preflight-only')<s.index('-mode batch')
    assert "-source \"$tcl\"" in s
    assert 'Refusing overwrite' in s


def test_docs_keep_open_constraints():
    d=(Path(__file__).resolve().parents[1]/'docs/phase22_timing_query_integrity.md').read_text()
    for phrase in ('NOT_QUALIFIED','TIMING-18','-of_objects','no physical','FT2232HQ'):
        assert phrase.lower() in d.lower()


def test_tcl_syntactically_complete():
    src=(Path(__file__).resolve().parents[1]/'scripts/phase22_timing_query_integrity.tcl').read_text()
    import shutil,subprocess
    shell=shutil.which('tclsh')
    if not shell:
        pytest.skip('tclsh not installed, syntax verified on Windows')
    # The actual syntax-completeness check is performed via a file here to
    # avoid interpolating Tcl syntax in the checker itself.
    p=subprocess.run([shell],input='set fp [open {%s} r]\nset data [read $fp]\nclose $fp\nputs [info complete $data]\n'%str(Path(__file__).resolve().parents[1]/'scripts/phase22_timing_query_integrity.tcl'),encoding='utf-8',capture_output=True)
    assert p.returncode==0 and p.stdout.strip()=='1',p.stderr
