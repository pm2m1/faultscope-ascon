"""Phase 21: fail-closed validation of read-only reset timing observations.

The observed reset path counts and clock pulse-width report DO NOT constitute
board minimum reset pulse-width, recovery/removal, or oscillator signoff.
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
from scripts.phase20_exact_pin_report import preflight as accepted_preflight
from scripts.phase18_async_report import PHASE17_DEFAULT

EXPECTED_CONTROL = {
    ('reset',str(i)):('rst_n',f'u_reset_sync/release_pipe_q_reg[{i}]/CLR') for i in range(3)
} | {
    ('rx',str(i)):('u_reset_sync/release_pipe_q_reg[2]/Q',f'receiver/sync_q_reg[{i}]/PRE') for i in range(2)
}
PATH_FIELDS = ['group','stage','source','sink','delay_type','query_state','path_count','slack_ns']
REPORTS = ('context.tsv','path_observations.tsv','check_timing.rpt','timing_summary.rpt',
           'methodology.rpt','clock_pulse_width.rpt','reset_from_port_max.rpt',
           'reset_from_port_min.rpt','release_to_preset_max.rpt','release_to_preset_min.rpt')


def read_tsv(path:Path,fields:list[str],*,allow_legacy_blank_slack:bool=False)->list[dict[str,str]]:
    with path.open(encoding='utf-8-sig',newline='') as fh:
        reader=csv.DictReader(fh,delimiter='\t')
        if reader.fieldnames!=fields:
            raise ValueError(f'Invalid columns: {path.name}')
        data=list(reader)
    if not data:
        raise ValueError(f'Missing or malformed records: {path.name}')
    for row in data:
        # Vivado 2026.1 can return a real path object without a SLACK value
        # when the external reset input lacks a timing model. Accept a truly
        # empty *eighth* field only for legacy path_observations.tsv; the
        # observation loop below checks its path state, count, and source.
        if None in row or any(
            val is None or (not val.strip() and not (
                allow_legacy_blank_slack and path.name == 'path_observations.tsv'
                and key == 'slack_ns' and val == ''))
            for key, val in row.items()
        ):
            raise ValueError(f'Missing or malformed records: {path.name}')
    return data


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(phase17:Path)->dict:
    p=accepted_preflight(phase17)
    if p.get('phase17_checkpoint_sha256') != '633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340':
        raise ValueError('Accepted Phase 17 checkpoint hash changed')
    return p


def inspect(phase17:Path,audit:Path|None)->dict:
    result={
        'phase':'21','scope':'read-only routed async reset timing-model diagnostic',
        'board':'PROVISIONAL Nexys 4 DDR Rev. C','board_signoff':'NOT VERIFIED',
        'bitstream_generated':False,'board_programmed':False,'analog_mtbf':'NOT VERIFIED',
        'external_reset_minimum_pulse_width':'NOT VERIFIED',
        'reset_recovery_removal':'NOT VERIFIED',
        'oscillator_startup_and_jitter':'NOT VERIFIED',
        'board_reset_bounce':'NOT VERIFIED',
        'external_uart_and_led_timing':'NOT VERIFIED',
        'clock_pulse_report_scope':'CLOCK_NETWORK_ONLY_NOT_EXTERNAL_RESET'
    }
    issues=[]
    try:
        origin=preflight(phase17)
        result['phase17_checkpoint_sha256']=origin['phase17_checkpoint_sha256']
        result['phase15_checkpoint_sha256']=origin['phase15_checkpoint_sha256']
        result['overlay_checkout_mode']=origin['overlay_checkout_mode']
        if audit is not None:
            for filename in REPORTS:
                p=audit/filename
                if not p.is_file() or p.stat().st_size<30:
                    raise ValueError(f'Missing/short diagnostic report: {filename}')
            ctx=read_tsv(audit/'context.tsv',['key','value'])
            if len(ctx)!=len({r['key'] for r in ctx}):
                raise ValueError('Duplicate context key')
            context={r['key']:r['value'] for r in ctx}
            for key,val in {
                'phase':'21','scope':'post_route_read_only_reset_timing','part':'xc7a100tcsg324-1',
                'clock_name':'board_clk_100mhz','cfgbvs':'VCCO',
                'reset_external_delay_qualification':'NOT_VERIFIED',
                'board_oscillator_startup':'NOT_VERIFIED',
                'board_reset_pulse_width':'NOT_VERIFIED'
            }.items():
                if context.get(key)!=val:
                    raise ValueError(f'Unexpected context: {key}')
            if context.get('design') not in {'checkpoint_post_route','faultscope_uart_top'}:
                raise ValueError('Unexpected design')
            if not re.fullmatch(r'20\d\d\.\d+',context.get('vivado_version','')):
                raise ValueError('Invalid Vivado version')
            for key,target in [('clock_period_ns',10.0),('config_voltage',3.3)]:
                val=float(context.get(key,'nan'))
                if not math.isfinite(val) or abs(val-target)>0.00001:
                    raise ValueError(f'Unexpected clock or voltage: {key}')
            observations=read_tsv(audit/'path_observations.tsv',PATH_FIELDS,allow_legacy_blank_slack=True)
            target={(group,stage,dt) for (group,stage) in EXPECTED_CONTROL for dt in ('max','min')}
            actual={(r['group'],r['stage'],r['delay_type']) for r in observations}
            if len(observations)!=10 or actual!=target:
                raise ValueError('Missing, unexpected or duplicate reset timing observation')
            seen=[]
            for obs in observations:
                g,s,dt=obs['group'],obs['stage'],obs['delay_type']
                src,sink=EXPECTED_CONTROL[(g,s)]
                if obs['source']!=src or obs['sink']!=sink:
                    raise ValueError(f'Incorrect query endpoint: {g}{s} {dt}')
                state=obs['query_state']
                if state not in {'PATH_REPORTED','PATH_REPORTED_SLACK_UNAVAILABLE','NO_PATH_REPORTED'}:
                    raise ValueError('Vivado query failed or unknown path state')
                count=int(obs['path_count'])
                slack=obs['slack_ns']
                if state=='NO_PATH_REPORTED':
                    if count!=0 or slack!='-':
                        raise ValueError('No-path query falsely reports slack/count')
                elif count!=1:
                    raise ValueError('Reported path must have exactly one timing path')
                elif state=='PATH_REPORTED' and slack=='':
                    # Backward compatibility with the original Phase 21 export.
                    # Never turn a path with no available slack into a timing PASS.
                    if g!='reset' or src!='rst_n':
                        raise ValueError('Unexpected missing modeled slack on internal path')
                    state='PATH_REPORTED_SLACK_UNAVAILABLE'
                    slack='-'
                elif state=='PATH_REPORTED_SLACK_UNAVAILABLE':
                    if g!='reset' or src!='rst_n' or slack!='-':
                        raise ValueError('Invalid unavailable-slack path classification')
                else:
                    # A nonblank, reported slack must be a finite number.
                    if not math.isfinite(float(slack)):
                        raise ValueError('Invalid reported path/slack')
                seen.append({'group':g,'stage':s,'delay_type':dt,'status':state,
                             'slack_ns':slack})
            result['timing_path_observations']=seen
            result['timing_paths_found']=sum(x['status'].startswith('PATH_REPORTED') for x in seen)
            result['timing_paths_with_numeric_slack']=sum(x['status']=='PATH_REPORTED' for x in seen)
            result['timing_paths_without_numeric_slack']=sum(
                x['status']=='PATH_REPORTED_SLACK_UNAVAILABLE' for x in seen)
            result['timing_paths_not_reported']=sum(x['status']=='NO_PATH_REPORTED' for x in seen)
            checks=(audit/'check_timing.rpt').read_text(encoding='utf-8',errors='replace')
            methodology=(audit/'methodology.rpt').read_text(encoding='utf-8',errors='replace')
            if 'rst_n' not in checks or 'uart_rx_i' not in checks:
                raise ValueError('Missing expected unconstrained async input indicators')
            result['methodology_missing_external_delay_warnings']=(
                'PRESENT' if 'TIMING-18' in methodology else 'NOT_FOUND_INVESTIGATE')
            pulse=(audit/'clock_pulse_width.rpt').read_text(encoding='utf-8',errors='replace')
            if 'QUERY_ERROR' in pulse:
                raise ValueError('Clock pulse-width command did not succeed')
            for f in REPORTS[6:]:
                if 'QUERY_ERROR' in (audit/f).read_text(encoding='utf-8',errors='replace'):
                    raise ValueError(f'Timing report query failed: {f}')
            result['report_sha256']={f:sha(audit/f) for f in REPORTS}
    except (OSError,ValueError,TypeError,KeyError,OverflowError,json.JSONDecodeError) as exc:
        issues.append(str(exc))
    result['issues']=issues
    result['verdict']=('NOT_VERIFIED' if issues else 'PHASE17_PROVENANCE_VERIFIED' if audit is None
                       else 'RESET_TIMING_EVIDENCE_REVIEW_REQUIRED')
    return result


def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase17',type=Path,default=PHASE17_DEFAULT)
    p.add_argument('--audit',type=Path)
    p.add_argument('--preflight-only',action='store_true')
    a=p.parse_args(argv)
    if a.preflight_only and a.audit is not None: p.error('Do not combine --audit with preflight')
    if not a.preflight_only and a.audit is None: p.error('Specify --audit or --preflight-only')
    res=inspect(a.phase17,None if a.preflight_only else a.audit)
    if a.audit is not None and a.audit.is_dir():
        (a.audit/'verification.json').write_text(json.dumps(res,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(res,indent=2,sort_keys=True))
    return 0 if res['verdict']==('PHASE17_PROVENANCE_VERIFIED' if a.preflight_only else 'RESET_TIMING_EVIDENCE_REVIEW_REQUIRED') else 2

if __name__=='__main__':
    sys.exit(main())
