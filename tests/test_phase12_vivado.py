"""Evidence validation tests: missing checks and negative slack cannot pass."""
from pathlib import Path
import json
import pytest
from scripts.phase12_report import PART, constraint_status, route_status, utilization, inspect_run, generate, compare_overhead

UTIL = f'''| Device : {PART}
| Slice LUTs* | 100 | 0 |
| Slice Registers | 80 | 0 |
| Register as Flip Flop | 80 | 0 |
| Block RAM Tile | 0 | 0 |
| RAMB18 | 0 | 0 |
| RAMB36/FIFO* | 0 | 0 |
| DSPs | 0 | 0 |
7. Primitives
| Ref Name | Used | Functional Category |
| LUT6 | 100 | LUT |
'''
CHECK = '''1. checking constant_clock (0)
2. checking loops (0)
3. checking latch_loops (0)
4. checking generated_clocks (0)
There are 0 register/latch pins with no clock.
There are 0 register/latch pins with multiple clocks.
There are 0 pins that are not constrained for maximum delay.
'''
ROUTE = '''# of routable nets : 500
# of fully routed nets : 500
# of unrouted nets : 0
# of nets with routing errors : 0
'''


def fixture_run(root, design='protected', setup=0.2, hold=0.03, period=10.0):
    out = root / (design + f'_{period:g}ns'); out.mkdir()
    for stage in ('post_synth','post_place','post_route'):
        (out / f'{stage}_utilization.rpt').write_text(UTIL)
    (out/'run_metadata.tsv').write_text(f'design\t{design}\npart\t{PART}\nperiod_ns\t{period}\nvivado_version\t2026.1\nsettings\tdefault\nclock_source\tBUFGCTRL_X0Y0\n')
    (out/'internal_metrics.tsv').write_text(f'setup_path_count\t1\nhold_path_count\t1\nsetup_slack_ns\t{setup}\nhold_slack_ns\t{hold}\nclock_period_ns\t{period}\nclock_source\tBUFGCTRL_X0Y0\n')
    (out/'check_timing.rpt').write_text(CHECK)
    (out/'post_route_status.rpt').write_text(ROUTE)
    (out/'post_route_drc.rpt').write_text('DRC Report\nNo violations found.')
    for name in ('IMPLEMENTATION_COMPLETE','post_route.dcp','post_route_timing.rpt','internal_setup_paths.rpt','internal_hold_paths.rpt'):
        (out/name).write_text('fixture')
    (out/'post_route_timing.rpt').write_text(f' WNS(ns) TNS(ns) TNS Failing Endpoints TNS Total Endpoints WHS(ns) THS(ns) THS Failing Endpoints THS Total Endpoints WPWS(ns) TPWS(ns) TPWS Failing Endpoints TPWS Total Endpoints\n --------\n {setup} 0 {int(setup<0)} 80 {hold} 0 {int(hold<0)} 80 4.5 0 0 80\n')
    if design == 'uart_protected':
        (out/'top_ports.txt').write_text('clk\nrst_n\nuart_rx_i\nuart_tx_o\nled_busy_o\nled_alarm_o\n', encoding='utf-8')
    return out


def test_utilization_and_missing_evidence():
    assert utilization(UTIL) == dict(lut=100, ff=80, carry4=0, bram_tiles=0, bram18=0, bram36=0, dsp=0)
    assert utilization(UTIL + '| CARRY4 | 2 | Carry |\n')['carry4'] == 2
    with pytest.raises(ValueError): utilization(UTIL.replace(PART, 'xc7a35t'))
    with pytest.raises(ValueError): utilization(UTIL.replace('| DSPs | 0 | 0 |', ''))
    assert all(v is None for v in constraint_status('no evidence').values())
    assert route_status('no evidence')['unrouted_nets'] is None


@pytest.mark.parametrize('setup,hold,status', [(0.2,0.03,'MET'),(-0.1,0.03,'FAILED'),(0.2,-0.02,'FAILED')])
def test_setup_and_hold_required(tmp_path,setup,hold,status):
    result=inspect_run(fixture_run(tmp_path,setup=setup,hold=hold))
    assert result['implementation']=='VERIFIED'
    assert result['internal_setup_hold']==status
    assert result['external_timing']=='NOT VERIFIED'


@pytest.mark.parametrize('file,text', [('check_timing.rpt',''), ('check_timing.rpt',CHECK.replace('0 pins','1 pins')),
    ('post_route_status.rpt',ROUTE.replace('unrouted nets : 0','unrouted nets : 2')),
    ('post_route_drc.rpt','DRC Critical Warning'), ('internal_metrics.tsv','')])
def test_fail_closed(tmp_path,file,text):
    out=fixture_run(tmp_path); (out/file).write_text(text)
    assert inspect_run(out)['internal_setup_hold']=='NOT VERIFIED'


def test_missing_architectures_and_overhead(tmp_path):
    fixture_run(tmp_path)
    result=generate(tmp_path)
    assert result['missing_architectures']==['baseline','instrumented','uart_protected']
    assert 'NOT VERIFIED' in (tmp_path/'comparison.csv').read_text()
    fixture_run(tmp_path,'baseline')
    result=generate(tmp_path)
    assert result['overhead'][0]['lut_percent']==0
    result['runs'][0]['metadata']['vivado_version']='other'
    assert compare_overhead(result['runs'])==[]


def test_vivado_dotted_route_status_and_omitted_zero_unrouted():
    actual = '# of routable nets..................... : 500 :\n# of fully routed nets................. : 500 :\n# of nets with routing errors.......... : 0 :\n'
    result = route_status(actual)
    assert result['unrouted_nets'] == result['routing_error_nets'] == 0
    assert result['routable_nets'] == result['fully_routed_nets'] == 500
    assert route_status(actual.replace('fully routed nets................. : 500','fully routed nets................. : 499'))['unrouted_nets'] == 1


def test_missing_clock_context_is_not_a_timing_pass(tmp_path):
    out=fixture_run(tmp_path)
    meta=(out/'run_metadata.tsv').read_text().replace('clock_source\tBUFGCTRL_X0Y0\n','')
    (out/'run_metadata.tsv').write_text(meta)
    result=inspect_run(out)
    assert result['implementation']=='VERIFIED'
    assert result['internal_setup_hold']=='NOT VERIFIED'
    assert 'clock source' in result['issues'][0]


def test_pulse_width_failure_and_inconsistent_slack(tmp_path):
    out=fixture_run(tmp_path)
    report=(out/'post_route_timing.rpt').read_text()
    (out/'post_route_timing.rpt').write_text(report.replace('4.5 0 0 80','-0.1 -0.1 1 80'))
    assert inspect_run(out)['internal_setup_hold']=='FAILED'
    (out/'post_route_timing.rpt').write_text(report.replace('0.2 0 0 80','0.5 0 0 80'))
    assert inspect_run(out)['internal_setup_hold']=='NOT VERIFIED'


def test_uart_port_mismatch_never_preserves_timing_pass(tmp_path):
    out = fixture_run(tmp_path, 'uart_protected')
    (out / 'top_ports.txt').write_text('clk\nrst_n\nextra_o\n', encoding='utf-8')
    result = inspect_run(out)
    assert result['internal_setup_hold'] == 'NOT VERIFIED'
    assert 'UART synthesized scalar port mismatch' in result['issues']


@pytest.mark.parametrize('severity', ['CRITICAL WARNING', 'ERROR', 'cRiTiCaL wArNiNg', 'error'])
def test_drc_severity_capitalization_cannot_pass(tmp_path, severity):
    out = fixture_run(tmp_path)
    (out/'post_route_drc.rpt').write_text('Report DRC\nTEST-1#1 ' + severity + '\n', encoding='utf-8')
    result = inspect_run(out)
    assert result['implementation'] == 'NOT VERIFIED'
    assert result['internal_setup_hold'] == 'NOT VERIFIED'


def test_require_verified_rejects_incomplete_architecture_set(tmp_path):
    import subprocess, sys
    fixture_run(tmp_path)
    proc = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1]/'scripts/phase12_report.py'), str(tmp_path), '--require-verified'], capture_output=True, text=True)
    assert proc.returncode != 0, proc.stdout


# Vivado 2026.1 report_drc summary/detail layout, including its noncritical warning.
VIVADO_DRC = """Report DRC
1. REPORT SUMMARY
Checks found: 1
| Rule | Severity | Description | Checks |
| CFGBVS-1 | Warning | Missing CFGBVS and CONFIG_VOLTAGE Design Properties | 1 |
2. REPORT DETAILS
CFGBVS-1#1 Warning
Missing CFGBVS and CONFIG_VOLTAGE Design Properties
"""


@pytest.mark.parametrize('severity', ['Critical Warning', 'CRITICAL WARNING', 'Error', 'ERROR'])
@pytest.mark.parametrize('location', ['summary', 'details'])
def test_vivado_2026_drc_layout_rejects_critical_severity(tmp_path, severity, location):
    out=fixture_run(tmp_path)
    text=VIVADO_DRC
    if location=='summary':
        text=text.replace('| Warning |', '| '+severity+' |')
    else:
        text=text.replace('CFGBVS-1#1 Warning', 'CFGBVS-1#1 '+severity)
    (out/'post_route_drc.rpt').write_text(text,encoding='utf-8')
    result=inspect_run(out)
    assert result['implementation']==result['internal_setup_hold']=='NOT VERIFIED'


@pytest.mark.parametrize('text',[VIVADO_DRC, 'Report DRC\nChecks found: 0\nNo violations found.'])
def test_genuine_zero_critical_drc_reports_remain_accepted(tmp_path,text):
    out=fixture_run(tmp_path)
    (out/'post_route_drc.rpt').write_text(text,encoding='utf-8')
    result=inspect_run(out)
    assert not result['drc_critical']
    assert result['implementation']=='VERIFIED' and result['internal_setup_hold']=='MET'


def parser_cli(root,*args):
    import subprocess,sys
    return subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'scripts/phase12_report.py'),str(root),'--require-verified','--validate-only',*args],capture_output=True,text=True)


def suite_fixture(root,period=10):
    for design in ('baseline','instrumented','protected','uart_protected'):
        fixture_run(root,design,period=period)


def test_complete_suite_readonly_cli_accepts(tmp_path):
    import hashlib
    suite_fixture(tmp_path)
    before={p.relative_to(tmp_path):hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    proc=parser_cli(tmp_path,'--expected-periods','10')
    assert proc.returncode==0,proc.stderr
    result=json.loads(proc.stdout)
    assert result['acceptance_scope']=='full-suite' and result['full_suite_complete']
    assert not result['missing_expected_combinations'] and not result['collection_issues']
    after={p.relative_to(tmp_path):hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    assert after==before


def test_explicit_subset_is_distinct_from_full_suite(tmp_path):
    fixture_run(tmp_path)
    proc=parser_cli(tmp_path,'--expected-designs','protected','--expected-periods','10')
    assert proc.returncode==0,proc.stderr
    result=json.loads(proc.stdout)
    assert result['acceptance_scope']=='explicit-subset' and not result['full_suite_complete']
    assert set(result['missing'])=={'baseline','instrumented','uart_protected'}
    assert parser_cli(tmp_path).returncode==2


@pytest.mark.parametrize('kind',['alias_duplicate','unnamed_duplicate','unexpected_architecture','metadata_design','metadata_period','unexpected_period'])
def test_ambiguous_run_combinations_rejected(tmp_path,kind):
    import shutil
    out=fixture_run(tmp_path)
    if kind=='alias_duplicate':
        shutil.copytree(out,tmp_path/'protected_10.0ns')
    elif kind=='unnamed_duplicate':
        shutil.copytree(out,tmp_path/'unnamed')
    elif kind=='unexpected_architecture':
        shutil.copytree(out,tmp_path/'unknown_10ns')
    elif kind=='metadata_design':
        p=out/'run_metadata.tsv';p.write_text(p.read_text().replace('design\tprotected','design\tbaseline'))
    elif kind=='metadata_period':
        p=out/'run_metadata.tsv';p.write_text(p.read_text().replace('period_ns\t10.0','period_ns\t15'))
    elif kind=='unexpected_period':
        fixture_run(tmp_path,period=15)
    proc=parser_cli(tmp_path,'--expected-designs','protected','--expected-periods','10')
    assert proc.returncode==2,proc.stdout
    assert json.loads(proc.stdout)['collection_issues']


@pytest.mark.parametrize('selection',[
    ('--expected-designs','protected','protected'),('--expected-designs','unknown'),
    ('--expected-periods','10','10.0'),('--expected-periods','nan'),('--expected-periods','inf'),
    ('--expected-periods','1')])
def test_invalid_expected_selections_rejected(tmp_path,selection):
    fixture_run(tmp_path)
    assert parser_cli(tmp_path,*selection).returncode==2


def test_missing_architectures_at_one_sweep_period_rejected(tmp_path):
    suite_fixture(tmp_path)
    fixture_run(tmp_path,'protected',period=15)
    proc=parser_cli(tmp_path)
    assert proc.returncode==2
    result=json.loads(proc.stdout)
    assert result['missing']==[]
    assert len(result['missing_expected_combinations'])==3


def test_missing_entire_explicit_period_rejected(tmp_path):
    suite_fixture(tmp_path)
    proc=parser_cli(tmp_path,'--expected-periods','10','15')
    assert proc.returncode==2
    assert len(json.loads(proc.stdout)['missing_expected_combinations'])==4


def test_extra_architectures_outside_selected_subset_rejected(tmp_path):
    suite_fixture(tmp_path)
    proc=parser_cli(tmp_path,'--expected-designs','protected')
    assert proc.returncode==2
    assert json.loads(proc.stdout)['collection_issues']


def test_complete_multi_period_suite_is_accepted(tmp_path):
    suite_fixture(tmp_path,10)
    suite_fixture(tmp_path,15)
    proc=parser_cli(tmp_path,'--expected-periods','10','15')
    assert proc.returncode==0,proc.stderr
    assert json.loads(proc.stdout)['full_suite_complete']
