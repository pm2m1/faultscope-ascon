"""Phase 19 read-only physical reset lineage evidence validator; never board signoff.

A positive verdict means correctly formed DIAGNOSTIC EVIDENCE, *not* proven
logic polarity. Vivado net aliases never establish driver identity.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.phase18_async_report import preflight as phase18_preflight, PHASE17_DEFAULT
from scripts.phase15_board_report import records, kv

EXPECTED = {
    ('reset', str(i), f'u_reset_sync/release_pipe_q_reg[{i}]', 'FDCE', 'CLR')
    for i in range(3)
} | {
    ('rx', str(i), f'receiver/sync_q_reg[{i}]', 'FDPE', 'PRE')
    for i in range(2)
}
REPORTS = ('check_timing.rpt', 'methodology.rpt')
CONTROL_FIELDS = ['group', 'stage', 'cell', 'primitive', 'control_pin', 'active_level',
                  'control_net_segments', 'startpoint_count', 'startpoint_names', 'status']
SOURCE_FIELDS = ['sink_group', 'sink_stage', 'sink_cell', 'startpoint_class',
                 'startpoint_name', 'startpoint_ref_pin']
DRIVER_FIELDS = ['group', 'stage', 'control_pin', 'driver_kind', 'driver_name',
                 'driver_cell_ref', 'driver_ref_pin', 'driver_init']


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_optional_tsv(path: Path, fields: list[str]) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        rd = csv.DictReader(f, delimiter='\t')
        if rd.fieldnames != fields:
            raise ValueError(f'{path.name}: wrong fields {rd.fieldnames}')
        rows = list(rd)
    if any(None in r or any(x is None or x == '' for x in r.values()) for r in rows):
        raise ValueError(f'{path.name}: malformed TSV')
    return rows


def inspect(phase17: Path, audit: Path | None) -> dict:
    result: dict = {
        'phase': '19',
        'scope': 'read-only Phase 17 post-route reset source and control-polarity diagnostics',
        'board': 'PROVISIONAL Nexys 4 DDR Rev. C',
        'board_signoff': 'NOT VERIFIED',
        'bitstream_generated': False,
        'board_programmed': False,
        'physical_reset_behavior': 'NOT VERIFIED',
        'actual_signal_polarity': 'MANUAL_REVIEW_REQUIRED',
        'reset_recovery_removal': 'NOT VERIFIED',
        'reset_bounce_and_clock_startup': 'NOT VERIFIED',
        'uart_analog_mtbf': 'NOT VERIFIED',
        'external_timing': 'NOT VERIFIED',
    }
    issues = []
    try:
        baseline = phase18_preflight(phase17)
        result['phase17_checkpoint_sha256'] = baseline['phase17_checkpoint_sha256']
        result['phase15_checkpoint_sha256'] = baseline['phase15_checkpoint_sha256']
        result['phase17_overlay_sha256'] = baseline['phase17_overlay_original_sha256']
        result['overlay_checkout_mode'] = baseline['overlay_checkout_mode']
        if audit is not None:
            cx = kv(audit/'context.tsv')
            for k,v in {
                'phase':'19', 'scope':'post_route_read_only_reset_lineage',
                'part':'xc7a100tcsg324-1', 'cfgbvs':'VCCO',
            }.items():
                if cx.get(k) != v: raise ValueError(f'Invalid Phase 19 context {k}')
            if cx.get('design') not in {'checkpoint_post_route', 'faultscope_uart_top'}:
                raise ValueError('Unexpected checkpoint design')
            if not re.fullmatch(r'20\d\d\.\d+', cx.get('vivado_version', '')):
                raise ValueError('Missing Vivado version')
            clk = float(cx.get('clock_period_ns', 'nan'))
            voltage = float(cx.get('config_voltage', 'nan'))
            if not math.isfinite(clk) or abs(clk - 10) > 1e-5 or not math.isfinite(voltage) or abs(voltage-3.3)>1e-5:
                raise ValueError('Unexpected clock or configuration voltage')
            inp = records(audit/'reset_input.tsv',
                ['port','buffer_count','buffer_cell','buffer_ref','input_net','output_net'])
            if len(inp) != 1 or inp[0]['port']!='rst_n':
                raise ValueError('Wrong reset input port')
            buf = inp[0]
            if buf['buffer_count']!='1' or not buf['buffer_ref'].startswith('IBUF') or any(buf[k]=='-' for k in ('buffer_cell','input_net','output_net')):
                raise ValueError('No unique physical reset input buffer')
            ctrls = records(audit/'controls.tsv', CONTROL_FIELDS)
            if len(ctrls) != 5 or {
                (r['group'],r['stage'],r['cell'],r['primitive'],r['control_pin']) for r in ctrls
            } != EXPECTED:
                raise ValueError('Incorrect five asynchronously controlled register pins')
            if any(r['active_level'] != 'HIGH' or r['control_net_segments']=='-' or
                   r['status'] not in {'CONNECTED_REVIEW_REQUIRED','SOURCE_NOT_RESOLVED'} for r in ctrls):
                raise ValueError('Async control polarity, nets or status malformed')
            starts = parse_optional_tsv(audit/'startpoints.tsv', SOURCE_FIELDS)
            keys = {(r['group'],r['stage'],r['cell']) for r in ctrls}
            if any((r['sink_group'],r['sink_stage'],r['sink_cell']) not in keys for r in starts):
                raise ValueError('Startpoints contain unexpected sink')
            drivers = records(audit/'control_drivers.tsv', DRIVER_FIELDS)
            if any((r['group'],r['stage']) not in {(c['group'],c['stage']) for c in ctrls}
                   or r['control_pin'] not in {'CLR','PRE'} or r['driver_kind'] not in {'PIN','PORT','NONE'}
                   for r in drivers):
                raise ValueError('Driver export contains unexpected rows')
            for r in ctrls:
                count = int(r['startpoint_count'])
                if count < 0 or count > 50000:
                    raise ValueError('Invalid fanin startpoint count')
                these = [x for x in starts if (x['sink_group'],x['sink_stage'],x['sink_cell']) ==
                         (r['group'],r['stage'],r['cell'])]
                if len(these) != count:
                    raise ValueError('Startpoint count disagrees with exported objects')
                these_drivers = [x for x in drivers if (x['group'],x['stage']) == (r['group'],r['stage'])]
                if not these_drivers: raise ValueError('Missing driver survey for async pin')
                if r['status']=='CONNECTED_REVIEW_REQUIRED' and (count==0 or all(x['driver_kind']=='NONE' for x in these_drivers)):
                    raise ValueError('Falsely labeled connected control')
            # A named net is never counted as evidence of its physical source.
            comb = parse_optional_tsv(audit/'comb_cone.tsv', ['group','stage','cell','ref_name','init'])
            if any((r['group'],r['stage']) not in {(c['group'],c['stage']) for c in ctrls} for r in comb):
                raise ValueError('Wrong combinational cone attribution')
            fan = records(audit/'release_fanout.tsv',
                          ['source_cell','endpoint_count','rx_stage0_in_endpoints','rx_stage1_in_endpoints','endpoint_names'])
            if len(fan)!=1 or fan[0]['source_cell']!='u_reset_sync/release_pipe_q_reg[2]':
                raise ValueError('Wrong release fanout root')
            endpoints = int(fan[0]['endpoint_count'])
            if endpoints < 0 or endpoints > 100000 or any(fan[0][k] not in {'0','1'}
                    for k in ('rx_stage0_in_endpoints','rx_stage1_in_endpoints')):
                raise ValueError('Malformed reset fanout count')
            for name in REPORTS:
                p = audit/name
                if not p.is_file() or p.stat().st_size < 80:
                    raise ValueError(f'Missing or truncated Vivado report: {name}')
            source_observations = {}
            for c in ctrls:
                rows = [x for x in starts if (x['sink_group'],x['sink_stage'])==(c['group'],c['stage'])]
                names = [x['startpoint_name'] for x in rows]
                # These are candidate source names. Do not certify polarity or combinational truth table.
                expected = ('rst_n' if c['group']=='reset' else 'u_reset_sync/release_pipe_q_reg[2]/Q')
                source_observations[f"{c['group']}{c['stage']}"] = {
                    'expected_startpoint': expected,
                    'observed': expected in names,
                    'startpoint_objects': names,
                    'direct_drivers': [x['driver_name'] for x in drivers if
                        (x['group'],x['stage'])==(c['group'],c['stage'])],
                }
            result['source_observations'] = source_observations
            result['control_count'] = len(ctrls)
            result['input_buffer_cell'] = buf['buffer_cell']
            result['combinational_cell_count'] = len(comb)
            result['reset_release_endpoint_count'] = endpoints
            result['unresolved_controls'] = [f"{r['group']}{r['stage']}" for r in ctrls if r['status']=='SOURCE_NOT_RESOLVED']
            names = ('context.tsv','reset_input.tsv','controls.tsv','startpoints.tsv',
                     'control_drivers.tsv','comb_cone.tsv','release_fanout.tsv') + REPORTS
            result['report_sha256'] = {n:sha(audit/n) for n in names}
    except (OSError, ValueError, KeyError, TypeError, OverflowError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    result['issues'] = issues
    result['verdict'] = ('NOT_VERIFIED' if issues else 'PHASE17_PROVENANCE_VERIFIED' if audit is None
                         else 'RESET_LINEAGE_EVIDENCE_REVIEW_REQUIRED')
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase17',type=Path,default=PHASE17_DEFAULT)
    p.add_argument('--audit',type=Path)
    p.add_argument('--preflight-only', action='store_true')
    a=p.parse_args(argv)
    if a.preflight_only and a.audit is not None: p.error('Cannot combine audit with preflight')
    if not a.preflight_only and a.audit is None: p.error('Specify --audit or --preflight-only')
    result=inspect(a.phase17,None if a.preflight_only else a.audit)
    if a.audit is not None and a.audit.is_dir():
        (a.audit/'verification.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result['verdict']==('PHASE17_PROVENANCE_VERIFIED' if a.preflight_only else
                                   'RESET_LINEAGE_EVIDENCE_REVIEW_REQUIRED') else 2

if __name__=='__main__':
    sys.exit(main())
