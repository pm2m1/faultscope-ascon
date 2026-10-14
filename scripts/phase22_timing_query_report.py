"""Phase 22: fail-closed validation of path-bound timing reports and board pin inventory.

Accepted verdict means EVIDENCE COLLECTED FOR MANUAL REVIEW only. It is not
FPGA board, physical reset, input/output timing, CDC or electrical signoff.
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
from scripts.phase21_reset_timing_report import preflight as phase21_preflight
from scripts.phase18_async_report import PHASE17_DEFAULT

PINS = {
    'clk': ('IN', 'E3'), 'rst_n': ('IN', 'C12'),
    'uart_rx_i': ('IN', 'C4'), 'uart_tx_o': ('OUT', 'D4'),
    'led_busy_o': ('OUT', 'H17'), 'led_alarm_o': ('OUT', 'K15'),
}
SOURCES = {
    ('reset', str(i)): ('rst_n', f'u_reset_sync/release_pipe_q_reg[{i}]/CLR')
    for i in range(3)
} | {
    ('rx', str(i)): ('u_reset_sync/release_pipe_q_reg[2]/Q', f'receiver/sync_q_reg[{i}]/PRE')
    for i in range(2)
}
PATH_FIELDS = ['group','stage','delay_type','requested_source','requested_sink',
               'query_state','path_count','slack_ns','report_file','report_state']
PORT_FIELDS = ['port','direction','package_pin','iostandard']
GENERAL_REPORTS = ['context.tsv','ports.tsv','path_bindings.tsv','check_timing.rpt',
                   'methodology.rpt','timing_summary.rpt']
PATH_REPORTS = [f'path_{g}{s}_{delay}.rpt' for g,s in SOURCES for delay in ('max','min')]
REPORTS = GENERAL_REPORTS + PATH_REPORTS
EXPECTED_WARNINGS = {
    ('input','rst_n'), ('input','uart_rx_i'),
    ('output','uart_tx_o'), ('output','led_busy_o'), ('output','led_alarm_o')
}


def sha256(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tsv(path:Path, columns:list[str])->list[dict[str,str]]:
    with path.open(encoding='utf-8-sig', newline='') as fh:
        reader=csv.DictReader(fh, delimiter='\t')
        if reader.fieldnames!=columns:
            raise ValueError(f'Invalid TSV column names: {path.name}')
        rows=list(reader)
    if not rows or any(None in r or any(x is None or not x.strip() for x in r.values()) for r in rows):
        raise ValueError(f'Missing/malformed TSV data: {path.name}')
    return rows


def preflight(phase17:Path)->dict:
    info=phase21_preflight(phase17)
    if info.get('phase17_checkpoint_sha256')!='633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340':
        raise ValueError('Accepted routed Phase 17 checkpoint provenance changed')
    return info


def path_evidence(report:str,group:str,stage:str,delay:str,slack_ns:str)->dict:
    if 'REPORT_QUERY_ERROR' in report or 'QUERY_ERROR' in report:
        raise ValueError('Vivado failed to render path-bound report')
    # A displayed header with grouped -from/-to is forbidden: it was misleading
    # in Phase 21. The -of_objects command binds to the selected timing path.
    command=re.search(r'(?m)^\| Command\s*:\s*([^\r\n]+)',report)
    if not command or 'report_timing -of_objects' not in command.group(1):
        raise ValueError('Report was not generated with report_timing -of_objects')
    src=re.search(r'(?m)^\s*Source:\s*(\S+)',report)
    dst=re.search(r'(?m)^\s*Destination:\s*(\S+)',report)
    pt=re.search(r'(?m)^\s*Path Type:\s*(\w+)',report)
    if not (src and dst and pt):
        raise ValueError('Missing actual source/destination/path type in timing report')
    expected_src,expected_sink=SOURCES[(group,stage)]
    if dst.group(1)!=expected_sink:
        raise ValueError(f'Actual report destination mismatched query for {group}{stage}{delay}')
    if pt.group(1).lower()!=('recovery' if delay=='max' else 'removal'):
        raise ValueError(f'Unexpected report path type for {group}{stage}{delay}')
    actual_src=src.group(1)
    shown=re.search(r'(?m)^\s*Slack(?:\s*\([^)]*\))?\s*:\s*([+-]?(?:inf|nan|[0-9]+(?:\.[0-9]+)?))',report,re.I)
    if shown is None:
        raise ValueError('Timing report lacks displayed slack')
    if slack_ns=='-':
        if shown.group(1).lower() not in {'inf','+inf','-inf'}:
            raise ValueError('Unavailable-slack path unexpectedly displays finite slack')
    else:
        text_value=float(shown.group(1))
        if not math.isfinite(text_value) or abs(text_value-float(slack_ns))>0.002:
            raise ValueError('Report slack does not match selected path slack')
    if group=='reset' and actual_src!='rst_n':
        raise ValueError('Reset source in report is not rst_n')
    if group=='rx' and actual_src not in {expected_src,'u_reset_sync/release_pipe_q_reg[2]/C'}:
        raise ValueError('Unexpected receiver preset timing startpoint')
    return {'reported_source':actual_src,'reported_destination':dst.group(1),
            'source_query_mismatch': actual_src!=expected_src,
            'path_type':pt.group(1)}


def inspect(phase17:Path,audit:Path|None)->dict:
    result={
        'phase':'22','scope':'read-only Phase 17 path-object timing report integrity',
        'board':'PROVISIONAL Nexys 4 DDR Rev. C','board_signoff':'NOT VERIFIED',
        'physical_board_revision':'NOT CONFIRMED','bitstream_generated':False,
        'board_programmed':False,'physical_reset_behavior':'NOT VERIFIED',
        'external_reset_minimum_pulse_width':'NOT VERIFIED',
        'external_input_output_timing':'NOT QUALIFIED',
        'uart_async_input_mtbf':'NOT VERIFIED',
        'timing_constraints_modified':False,
    }
    issues=[]
    try:
        origin=preflight(phase17)
        for key in ('phase15_checkpoint_sha256','phase17_checkpoint_sha256','overlay_checkout_mode'):
            result[key]=origin[key]
        if audit is not None:
            for name in REPORTS:
                p=audit/name
                if not p.is_file() or p.stat().st_size<20:
                    raise ValueError(f'Missing/short Phase 22 evidence: {name}')
            rows=tsv(audit/'context.tsv',['key','value'])
            if len(rows)!=len({r['key'] for r in rows}):
                raise ValueError('Repeated context field')
            c={r['key']:r['value'] for r in rows}
            for k,v in {
                'phase':'22', 'scope':'post_route_read_only_path_binding',
                'part':'xc7a100tcsg324-1','clock_name':'board_clk_100mhz',
                'cfgbvs':'VCCO', 'external_delay_model':'NOT_QUALIFIED',
                'board_revision':'PROVISIONAL','physical_reset_signoff':'NOT_VERIFIED'
            }.items():
                if c.get(k)!=v:
                    raise ValueError(f'Invalid implementation context: {k}')
            if c.get('design') not in {'checkpoint_post_route','faultscope_uart_top'}:
                raise ValueError('Unexpected top design')
            if not re.fullmatch(r'20\d\d\.\d+',c.get('vivado_version','')):
                raise ValueError('Unexpected Vivado version')
            for k,expected in [('clock_period_ns',10.0),('config_voltage',3.3)]:
                v=float(c.get(k,'nan'))
                if not math.isfinite(v) or abs(v-expected)>1e-5:
                    raise ValueError(f'Invalid implementation property {k}')
            ports=tsv(audit/'ports.tsv',PORT_FIELDS)
            if len(ports)!=6 or set(p['port'] for p in ports)!=set(PINS):
                raise ValueError('Missing/duplicate/unexpected port inventory')
            for p in ports:
                if (p['direction'],p['package_pin'])!=PINS[p['port']]:
                    raise ValueError(f'Changed board pin or direction: {p["port"]}')
                if p['iostandard']!='LVCMOS33':
                    raise ValueError(f'Changed electrical standard: {p["port"]}')
            result['implemented_port_inventory']={p['port']:p['package_pin'] for p in ports}
            obs=tsv(audit/'path_bindings.tsv',PATH_FIELDS)
            expected={(g,s,delay) for g,s in SOURCES for delay in ('max','min')}
            if len(obs)!=10 or set((r['group'],r['stage'],r['delay_type']) for r in obs)!=expected:
                raise ValueError('Unexpected/duplicate/missing timing queries')
            observed=[]
            for r in obs:
                g,s,delay=r['group'],r['stage'],r['delay_type']
                requested_src,requested_sink=SOURCES[(g,s)]
                if (r['requested_source'],r['requested_sink'])!=(requested_src,requested_sink):
                    raise ValueError('Query endpoints changed')
                filename=f'path_{g}{s}_{delay}.rpt'
                if r['report_file']!=filename or '/' in r['report_file'] or '\\' in r['report_file']:
                    raise ValueError('Report file mismatch')
                count=int(r['path_count'])
                state=r['query_state']
                slack=r['slack_ns']
                if state=='NO_PATH_REPORTED':
                    if count!=0 or slack!='-' or r['report_state']!='NO_PATH_REPORTED':
                        raise ValueError('Invalid no-path classification')
                    if not (audit/filename).read_text(encoding='utf-8',errors='replace').startswith('NO_PATH_REPORTED'):
                        raise ValueError('No-path report is missing sentinel')
                    rendered={'reported_source':'-','reported_destination':'-','source_query_mismatch':False,'path_type':'-'}
                elif state in {'PATH_REPORTED','PATH_REPORTED_SLACK_UNAVAILABLE'}:
                    if count!=1 or r['report_state']!='REPORT_WRITTEN':
                        raise ValueError('Reported timing path has invalid count/render state')
                    if state=='PATH_REPORTED':
                        slacknum=float(slack)
                        if not math.isfinite(slacknum):
                            raise ValueError('Nonfinite timing slack presented as finite')
                    elif g!='reset' or slack!='-':
                        raise ValueError('Slack-unavailable classification inconsistent with path')
                    rendered=path_evidence((audit/filename).read_text(encoding='utf-8',errors='replace'),g,s,delay,slack)
                else:
                    raise ValueError('Unknown timing path state or query error')
                observed.append({'group':g,'stage':s,'delay_type':delay,
                    'query_state':state,'slack_ns':slack,'report_file':filename,**rendered})
            result['timing_path_observations']=observed
            result['paths_with_rendered_reports']=sum(x['reported_source']!='-' for x in observed)
            result['timing_startpoint_mismatches']=[x['report_file'] for x in observed if x['source_query_mismatch']]
            methodology=(audit/'methodology.rpt').read_text(encoding='utf-8',errors='replace')
            warnings=set(re.findall(r'An (input|output) delay is missing on\s+(\w+)\s+relative',methodology))
            if warnings!=EXPECTED_WARNINGS:
                raise ValueError('TIMING-18 external delay inventory differs from accepted baseline')
            if methodology.count('TIMING-18#')!=5:
                raise ValueError('Expected five distinct methodology warnings')
            checks=(audit/'check_timing.rpt').read_text(encoding='utf-8',errors='replace')
            if not all(p in checks for p in ('rst_n','uart_rx_i','uart_tx_o','led_busy_o','led_alarm_o')):
                raise ValueError('Incomplete unconstrained I/O inventory')
            summary=(audit/'timing_summary.rpt').read_text(encoding='utf-8',errors='replace')
            if 'Timing Summary Report' not in summary:
                raise ValueError('Missing routed timing summary')
            result['missing_io_delay_warnings']=sorted([f'{typ}:{name}' for typ,name in warnings])
            result['report_sha256']={name:sha256(audit/name) for name in REPORTS}
    except (OSError,ValueError,TypeError,KeyError,OverflowError) as err:
        issues.append(str(err))
    result['issues']=issues
    result['verdict']=('NOT_VERIFIED' if issues else
        'PHASE17_PROVENANCE_VERIFIED' if audit is None else
        'PATH_OBJECT_REPORTS_REVIEW_REQUIRED')
    return result


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase17',type=Path,default=PHASE17_DEFAULT)
    p.add_argument('--audit',type=Path)
    p.add_argument('--preflight-only',action='store_true')
    a=p.parse_args(argv)
    if a.preflight_only==bool(a.audit):
        p.error('Select exactly one of --audit or --preflight-only')
    info=inspect(a.phase17,None if a.preflight_only else a.audit)
    if a.audit is not None and a.audit.is_dir():
        (a.audit/'verification.json').write_text(json.dumps(info,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(info,indent=2,sort_keys=True))
    return 0 if info['verdict']==('PHASE17_PROVENANCE_VERIFIED' if a.preflight_only else 'PATH_OBJECT_REPORTS_REVIEW_REQUIRED') else 2

if __name__=='__main__':
    raise SystemExit(main())
