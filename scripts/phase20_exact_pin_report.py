"""Phase 20: validate read-only, pin-to-pin reset lineage diagnostic evidence.

A positive result never signs off reset hardware, MTBF, or external I/O timing.
In particular Vivado fanin's /C startpoint must not be silently treated as /Q.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.phase18_async_report import preflight as phase17_preflight, PHASE17_DEFAULT

EDGE_SPECS = {
    'reset_port_to_ibuf': ('rst_n', 'rst_n_IBUF_inst/I', 'PORT_TO_IBUF_DIRECT'),
    'reset_ibuf_to_lut': ('rst_n_IBUF_inst/O', 'u_reset_sync/release_pipe_q[2]_i_1/I0', 'SEGMENT_AND_SINGLE_EXPECTED_DRIVER'),
    'reset_lut_to_clr0': ('u_reset_sync/release_pipe_q[2]_i_1/O', 'u_reset_sync/release_pipe_q_reg[0]/CLR', 'SEGMENT_AND_SINGLE_EXPECTED_DRIVER'),
    'reset_lut_to_clr1': ('u_reset_sync/release_pipe_q[2]_i_1/O', 'u_reset_sync/release_pipe_q_reg[1]/CLR', 'SEGMENT_AND_SINGLE_EXPECTED_DRIVER'),
    'reset_lut_to_clr2': ('u_reset_sync/release_pipe_q[2]_i_1/O', 'u_reset_sync/release_pipe_q_reg[2]/CLR', 'SEGMENT_AND_SINGLE_EXPECTED_DRIVER'),
    'release_q_to_lut': ('u_reset_sync/release_pipe_q_reg[2]/Q', 'u_reset_sync/FSM_sequential_state_q[1]_i_2/I0', 'SEGMENT_AND_SINGLE_EXPECTED_DRIVER'),
    'release_lut_to_pre0': ('u_reset_sync/FSM_sequential_state_q[1]_i_2/O', 'receiver/sync_q_reg[0]/PRE', 'SEGMENT_AND_SINGLE_EXPECTED_DRIVER'),
    'release_lut_to_pre1': ('u_reset_sync/FSM_sequential_state_q[1]_i_2/O', 'receiver/sync_q_reg[1]/PRE', 'SEGMENT_AND_SINGLE_EXPECTED_DRIVER'),
}
EDGE_FIELDS = ['edge','src_object','dst_object','src_direction','dst_direction',
               'src_segments','dst_segments','shared_segments','leaf_drivers','driver_count','status']
LUT_FIELDS = ['role','cell','ref_name','init','i0_pin','o_pin','truth_status']
SP_FIELDS = ['rx_stage','control_pin','startpoint_class','startpoint_name','startpoint_ref_pin']
REPORTS = ('context.tsv','pin_edges.tsv','lut_truth.tsv','preset_startpoints.tsv',
           'check_timing.rpt','methodology.rpt')


def rows(path: Path, fields: list[str], *, allow_empty: bool=False) -> list[dict[str,str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f, delimiter='\t')
        if r.fieldnames != fields:
            raise ValueError(f'Invalid TSV header: {path.name}')
        data = list(r)
    if not data and not allow_empty:
        raise ValueError(f'Empty evidence: {path.name}')
    if any(None in d or any(v is None or not v.strip() for v in d.values()) for d in data):
        raise ValueError(f'Malformed evidence: {path.name}')
    return data


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(phase17: Path) -> dict:
    base = phase17_preflight(phase17)
    if base.get('phase17_checkpoint_sha256') != '633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340':
        raise ValueError('Phase 17 routed candidate DCP does not match accepted SHA-256')
    return base


def inspect(phase17: Path, audit: Path | None) -> dict:
    r = {
        'phase':'20', 'scope':'read-only Phase 17 reset pin-level exact connection investigation',
        'board':'PROVISIONAL Nexys 4 DDR Rev. C',
        'bitstream_generated':False, 'board_programmed':False,
        'board_signoff':'NOT VERIFIED', 'external_io_timing':'NOT VERIFIED',
        'physical_reset_polarity':'NOT VERIFIED', 'reset_recovery_removal':'NOT VERIFIED',
        'clock_startup_and_bounce':'NOT VERIFIED', 'analog_mtbf':'NOT VERIFIED'
    }
    issues=[]
    try:
        provenance = preflight(phase17)
        r['phase17_checkpoint_sha256'] = provenance['phase17_checkpoint_sha256']
        r['phase15_checkpoint_sha256'] = provenance['phase15_checkpoint_sha256']
        r['overlay_checkout_mode'] = provenance['overlay_checkout_mode']
        if audit is not None:
            for file in REPORTS:
                p = audit/file
                if not p.is_file() or p.stat().st_size < 25:
                    raise ValueError(f'Missing/short Phase 20 evidence: {file}')
            ctx = rows(audit/'context.tsv',['key','value'])
            if len({x['key'] for x in ctx}) != len(ctx):
                raise ValueError('Duplicate context key')
            c = {x['key']:x['value'] for x in ctx}
            for k,v in dict(phase='20',scope='post_route_read_only_pin_exact_trace',
                            part='xc7a100tcsg324-1',clock_name='board_clk_100mhz',
                            cfgbvs='VCCO').items():
                if c.get(k)!=v: raise ValueError('Unexpected context: '+k)
            if c.get('design') not in {'checkpoint_post_route','faultscope_uart_top'}:
                raise ValueError('Unexpected design')
            if not re.fullmatch(r'20\d\d\.\d+',c.get('vivado_version','')):
                raise ValueError('Unexpected Vivado version')
            for k,v in [('clock_period_ns',10.),('config_voltage',3.3)]:
                number=float(c.get(k,'nan'))
                if not math.isfinite(number) or abs(number-v)>0.00001:
                    raise ValueError('Bad clock or config voltage: '+k)
            edges = rows(audit/'pin_edges.tsv', EDGE_FIELDS)
            if len(edges)!=len(EDGE_SPECS) or {e['edge'] for e in edges}!=set(EDGE_SPECS):
                raise ValueError('Missing, duplicated or unexpected physical links')
            unresolved=[]
            for e in edges:
                source, destination, expected_status = EDGE_SPECS[e['edge']]
                if e['src_object']!=source or e['dst_object']!=destination:
                    raise ValueError('Incorrect source or destination pin: '+e['edge'])
                if e['dst_direction']!='IN' or e['src_direction'] != ('IN' if e['edge']=='reset_port_to_ibuf' else 'OUT'):
                    raise ValueError('Wrong pin direction: '+e['edge'])
                drvcount = int(e['driver_count'])
                if drvcount<0 or drvcount>100:
                    raise ValueError('Out-of-range physical driver count')
                if e['status'] not in {'UNRESOLVED',expected_status}:
                    raise ValueError('Invalid link status: '+e['edge'])
                if e['status']==expected_status:
                    segments=lambda k: set(e[k].split(',')) - {'-'}
                    if not segments('shared_segments') or not segments('shared_segments').issubset(segments('src_segments') & segments('dst_segments')):
                        raise ValueError('Unsubstantiated shared net segment: '+e['edge'])
                    if e['edge']=='reset_port_to_ibuf':
                        if drvcount!=0 or e['leaf_drivers']!='-':
                            raise ValueError('Input port is not a primitive output')
                    else:
                        ref = ('IBUF' if source.startswith('rst_n_IBUF_inst/') else
                               'FDCE' if source.endswith('/Q') else 'LUT1')
                        if drvcount!=1 or e['leaf_drivers']!=source+'|'+ref:
                            raise ValueError('Driver identity or uniqueness false: '+e['edge'])
                else:
                    unresolved.append(e['edge'])
            luts = rows(audit/'lut_truth.tsv', LUT_FIELDS)
            if len(luts)!=2 or {x['role'] for x in luts}!={'reset','release'}:
                raise ValueError('Missing inverter LUT record')
            for l in luts:
                exp_cell = ('u_reset_sync/release_pipe_q[2]_i_1' if l['role']=='reset'
                            else 'u_reset_sync/FSM_sequential_state_q[1]_i_2')
                if (l['cell'] != exp_cell or l['ref_name']!='LUT1'
                        or l['i0_pin']!=exp_cell+'/I0' or l['o_pin']!=exp_cell+'/O'):
                    raise ValueError('Wrong LUT cell/pins')
                if l['truth_status'] not in {'ONE_INPUT_INVERTER','NOT_VERIFIED'}:
                    raise ValueError('Bad LUT truth status')
                if l['truth_status']=='ONE_INPUT_INVERTER' and l['init']!="2'h1":
                    raise ValueError('False inverter truth table')
                if l['init']=="2'h1" and l['truth_status']!='ONE_INPUT_INVERTER':
                    raise ValueError('LUT INIT/status conflict')
            st = rows(audit/'preset_startpoints.tsv', SP_FIELDS)
            if {s['rx_stage'] for s in st}!={'0','1'}:
                raise ValueError('Missing RX preset startpoint observations')
            for s in st:
                if s['control_pin'] != f"receiver/sync_q_reg[{s['rx_stage']}]/PRE":
                    raise ValueError('Startpoint linked to wrong PRE pin')
            for name in ('check_timing.rpt','methodology.rpt'):
                if (audit/name).stat().st_size<80:
                    raise ValueError('Truncated timing diagnostic: '+name)
            r['pin_edge_status'] = {e['edge']:e['status'] for e in edges}
            r['unresolved_edges'] = unresolved
            r['lut_inverters_observed'] = sorted(x['role'] for x in luts if x['truth_status']=='ONE_INPUT_INVERTER')
            r['preset_startpoints'] = {stage:sorted(x['startpoint_name'] for x in st if x['rx_stage']==stage) for stage in ('0','1')}
            r['physical_netlist_chain'] = ('CANDIDATE_ALL_EIGHT_LINKS_OBSERVED' if not unresolved and len(r['lut_inverters_observed'])==2
                                           else 'INCOMPLETE_OR_AMBIGUOUS_REQUIRES_REVIEW')
            r['report_sha256'] = {f:sha(audit/f) for f in REPORTS}
    except (OSError,ValueError,KeyError,TypeError,OverflowError,json.JSONDecodeError) as ex:
        issues.append(str(ex))
    r['issues']=issues
    r['verdict'] = ('NOT_VERIFIED' if issues else 'PHASE17_PROVENANCE_VERIFIED' if audit is None
                    else 'PIN_LEVEL_EVIDENCE_REVIEW_REQUIRED')
    return r


def main(argv=None) -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--phase17',type=Path,default=PHASE17_DEFAULT)
    ap.add_argument('--audit',type=Path)
    ap.add_argument('--preflight-only',action='store_true')
    a=ap.parse_args(argv)
    if a.preflight_only and a.audit is not None: ap.error('Preflight cannot be combined with --audit')
    if not a.preflight_only and a.audit is None: ap.error('Specify --audit or --preflight-only')
    result=inspect(a.phase17,None if a.preflight_only else a.audit)
    if a.audit is not None and a.audit.is_dir():
        (a.audit/'verification.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result['verdict']==('PHASE17_PROVENANCE_VERIFIED' if a.preflight_only else 'PIN_LEVEL_EVIDENCE_REVIEW_REQUIRED') else 2

if __name__=='__main__':
    sys.exit(main())
