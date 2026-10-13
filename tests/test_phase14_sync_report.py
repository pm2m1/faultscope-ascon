"""Phase 14 negative controls: missing stages, attributes, and routes cannot pass."""
import csv
import json
from pathlib import Path
import pytest
from scripts.phase14_sync_report import inspect, main

COLUMNS = {
    'cells.tsv': ['group','stage','cell','ref_name','async_reg','shreg_extract','loc','bel'],
    'edges.tsv': ['group','from_stage','to_stage','from_cell','to_cell','net_overlap','status'],
    'ports.tsv': ['port','direction'],
    'context.tsv': ['key','value'],
}

def write(folder, name, rows):
    with (folder/name).open('w', encoding='utf-8', newline='') as fp:
        w = csv.DictWriter(fp, COLUMNS[name], delimiter='\t'); w.writeheader(); w.writerows(rows)

def fixture(folder):
    stages = [('reset',i) for i in range(3)] + [('rx',i) for i in range(2)]
    write(folder,'cells.tsv',[dict(group=g,stage=str(i),cell=f'{g}/q[{i}]',ref_name='FDCE',async_reg='TRUE',shreg_extract='-',loc=f'SLICE_X1Y{i}',bel='AFF') for g,i in stages])
    write(folder,'edges.tsv',[dict(group=g,from_stage=str(i),to_stage=str(j),from_cell=f'{g}/q[{i}]',to_cell=f'{g}/q[{j}]',net_overlap=f'n_{g}_{i}',status='DIRECT') for g,i,j in [('reset',0,1),('reset',1,2),('rx',0,1)]])
    write(folder,'ports.tsv',[dict(port=k,direction='IN' if k in ('clk','rst_n','uart_rx_i') else 'OUT') for k in ('clk','rst_n','uart_rx_i','uart_tx_o','led_busy_o','led_alarm_o')])
    write(folder,'context.tsv',[dict(key=k,value=v) for k,v in {'top':'faultscope_uart_top','vivado_version':'2026.1','clock_count':'1','period_ns':'10.0','clock_source':'BUFGCTRL_X0Y0','scope':'OOC'}.items()])


def test_audit_positive_has_explicit_limitations(tmp_path):
    fixture(tmp_path)
    r = inspect(tmp_path)
    assert r['verdict'] == 'PASS'
    assert r['board_io_timing'] == 'NOT VERIFIED'
    assert r['uart_metastability_mtbf'] == 'NOT VERIFIED'

@pytest.mark.parametrize('mutation', ['delete-stage','duplicate-stage','bad-attribute','srl','no-location','edge-disconnected','missing-edge','extra-port','clock-missing','wrong-period','missing-file','edge-bad-cell','bad-direction'])
def test_audit_fails_closed(tmp_path,mutation):
    fixture(tmp_path)
    cells = list(csv.DictReader((tmp_path/'cells.tsv').open(), delimiter='\t'))
    edges = list(csv.DictReader((tmp_path/'edges.tsv').open(), delimiter='\t'))
    ports = list(csv.DictReader((tmp_path/'ports.tsv').open(), delimiter='\t'))
    ctx = list(csv.DictReader((tmp_path/'context.tsv').open(), delimiter='\t'))
    if mutation == 'delete-stage': cells.pop()
    if mutation == 'duplicate-stage': cells.append(cells[0].copy())
    if mutation == 'bad-attribute': cells[0]['async_reg']='FALSE'
    if mutation == 'srl': cells[0]['ref_name']='SRL16E'
    if mutation == 'no-location': cells[0]['loc']='-'
    if mutation == 'edge-disconnected': edges[0]['status']='NOT_VERIFIED'
    if mutation == 'missing-edge': edges.pop()
    if mutation == 'extra-port': ports.append(dict(port='secret',direction='OUT'))
    if mutation == 'clock-missing': ctx=[x for x in ctx if x['key']!='clock_source']
    if mutation == 'wrong-period': next(x for x in ctx if x['key']=='period_ns')['value']='12.0'
    if mutation == 'edge-bad-cell': edges[0]['from_cell']='mystery'
    if mutation == 'bad-direction': ports[0]['direction']='OUT'
    for n, rows in (('cells.tsv',cells),('edges.tsv',edges),('ports.tsv',ports),('context.tsv',ctx)):
        write(tmp_path,n,rows)
    if mutation == 'missing-file': (tmp_path/'edges.tsv').unlink()
    if mutation == 'missing-file':
        with pytest.raises(ValueError): inspect(tmp_path)
    else:
        assert inspect(tmp_path)['verdict'] == 'NOT_VERIFIED'


def test_python_cli_rejects_unverified(tmp_path):
    import subprocess,sys
    fixture(tmp_path)
    script=Path(__file__).resolve().parents[1]/'scripts/phase14_sync_report.py'
    ok=subprocess.run([sys.executable,str(script),str(tmp_path),'--require-pass'],capture_output=True,text=True)
    assert ok.returncode==0 and json.loads(ok.stdout)['verdict']=='PASS'
    (tmp_path/'edges.tsv').unlink()
    bad=subprocess.run([sys.executable,str(script),str(tmp_path),'--require-pass'],capture_output=True,text=True)
    assert bad.returncode==2 and json.loads(bad.stdout)['verdict']=='NOT_VERIFIED'


def test_tcl_is_readonly_and_targets_actual_rtl_names():
    s=(Path(__file__).resolve().parents[1]/'scripts/phase14_sync_audit.tcl').read_text()
    for token in ('open_checkpoint','u_reset_sync/release_pipe_q_reg','receiver/sync_q_reg','ASYNC_REG','get_nets','edges.tsv','cells.tsv'):
        assert token in s
    for forbidden in ('write_checkpoint ', 'route_design\n', 'synth_design ', 'write_bitstream ', 'set_property '):
        # The source comments include words naming forbidden actions; ignore comments.
        assert forbidden not in '\n'.join(l for l in s.splitlines() if not l.lstrip().startswith('#'))


def test_vivado_renames_opened_checkpoint_design(tmp_path):
    """A routed checkpoint's generated design name is not its RTL top."""
    fixture(tmp_path)
    context = list(csv.DictReader((tmp_path / 'context.tsv').open(), delimiter='\t'))
    next(x for x in context if x['key'] == 'top')['value'] = 'checkpoint_post_route'
    write(tmp_path, 'context.tsv', context)
    assert inspect(tmp_path)['verdict'] == 'PASS'

    next(x for x in context if x['key'] == 'top')['value'] = 'unrelated_design'
    write(tmp_path, 'context.tsv', context)
    assert inspect(tmp_path)['verdict'] == 'NOT_VERIFIED'
