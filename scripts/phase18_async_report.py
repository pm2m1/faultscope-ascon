"""Phase 18 read-only async-boundary evidence validator. No analog/board signoff."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.phase17_cfg_review import inspect as inspect17, PHASE15_DEFAULT
from scripts.phase15_board_report import records, kv
from scripts.phase16_gap_report import _xdc_provenance_mode

PHASE17_DEFAULT = ROOT / 'build/reproduction/phase17/nexys4_ddr_rev_c_cfg_20261014T131338Z'
OVERLAY = ROOT / 'constraints/phase17_cfg_rev_c_overlay.xdc'
REPORTS = ('check_timing.rpt', 'rx_interstage_max.rpt', 'rx_interstage_min.rpt',
           'methodology.rpt', 'cdc.rpt')
EXPECTED_STAGES = {
    ('reset', str(i), f'u_reset_sync/release_pipe_q_reg[{i}]') for i in range(3)
} | {('rx', str(i), f'receiver/sync_q_reg[{i}]') for i in range(2)}
EXPECTED_EDGES = {('reset', '0', '1'), ('reset', '1', '2'), ('rx', '0', '1')}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(phase17: Path) -> dict:
    saved = json.loads((phase17 / 'verification.json').read_text(encoding='utf-8'))
    if saved.get('verdict') != 'ROUTED_CFG_CANDIDATE_REVIEW_REQUIRED' or saved.get('issues'):
        raise ValueError('Phase 17 candidate is not previously accepted')
    current = inspect17(PHASE15_DEFAULT, phase17)
    if current.get('verdict') != 'ROUTED_CFG_CANDIDATE_REVIEW_REQUIRED' or current.get('issues'):
        raise ValueError('Phase 17 candidate fails fresh validation: ' + str(current.get('issues')))
    if saved.get('phase17_checkpoint_sha256') != current.get('phase17_checkpoint_sha256'):
        raise ValueError('Phase 17 routed DCP hash differs from accepted evidence')
    if saved.get('phase15_checkpoint_sha256') != current.get('phase15_checkpoint_sha256'):
        raise ValueError('Phase 15 baseline provenance has changed')
    if saved.get('phase15_original_xdc_sha256') != current.get('phase15_original_xdc_sha256'):
        raise ValueError('Phase 15 XDC provenance has changed')
    if saved.get('report_sha256') != current.get('report_sha256'):
        raise ValueError('Phase 17 exported report digests differ from accepted evidence')
    # The original overlay is LF; Git for Windows may produce a uniform CRLF checkout.
    original_overlay_sha = saved.get('overlay_sha256', '')
    if not re.fullmatch(r'[0-9a-f]{64}', original_overlay_sha):
        raise ValueError('Missing previously recorded Phase 17 overlay digest')
    mode = _xdc_provenance_mode(OVERLAY.read_bytes(), original_overlay_sha)
    if mode is None:
        raise ValueError('Phase 17 configuration overlay differs beyond LF/CRLF endings')
    return {'phase17_checkpoint_sha256': saved['phase17_checkpoint_sha256'],
            'phase15_checkpoint_sha256': saved['phase15_checkpoint_sha256'],
            'phase17_overlay_original_sha256': original_overlay_sha,
            'overlay_checkout_mode': mode,
            'phase17_setup_slack_ns': saved['phase17_setup_slack_ns'],
            'phase17_hold_slack_ns': saved['phase17_hold_slack_ns']}


def inspect(phase17: Path, audit: Path | None) -> dict:
    result: dict = {
        'phase': '18', 'scope': 'read-only Phase 17 async UART/reset boundary audit',
        'board': 'PROVISIONAL Nexys 4 DDR Rev. C',
        'bitstream_generated': False, 'board_programmed': False, 'board_revision_confirmed': False,
        'board_signoff': 'NOT VERIFIED', 'physical_reset_behavior': 'NOT VERIFIED',
        'uart_metastability_mtbf': 'NOT VERIFIED', 'external_io_timing': 'NOT VERIFIED',
        'clock_startup': 'NOT VERIFIED', 'reset_recovery_removal': 'NOT VERIFIED',
        'rtl_simulation': 'SEPARATE_TEST_REQUIRED',
    }
    issues: list[str] = []
    try:
        result.update(preflight(phase17))
        if audit is not None:
            context = kv(audit/'context.tsv')
            checks = {'phase':'18', 'scope':'post_route_read_only_async_boundary',
                      'part':'xc7a100tcsg324-1', 'clock_name':'board_clk_100mhz',
                      'cfgbvs':'VCCO'}
            for key, value in checks.items():
                if context.get(key) != value:
                    raise ValueError(f'invalid Phase 18 context: {key}')
            if context.get('design') not in {'checkpoint_post_route', 'faultscope_uart_top'}:
                raise ValueError('wrong design context')
            if not re.fullmatch(r'20\d\d\.\d+', context.get('vivado_version','')):
                raise ValueError('Vivado version missing')
            period = float(context.get('clock_period_ns','nan'))
            voltage = float(context.get('config_voltage','nan'))
            if not all(math.isfinite(v) for v in (period,voltage)) or abs(period-10.0)>1e-5 or abs(voltage-3.3)>1e-5:
                raise ValueError('Unexpected routed clock/voltage')
            rows = records(audit/'stages.tsv',
                           ['group','stage','cell','ref_name','async_reg','loc','bel','async_control_net'])
            if len(rows)!=5 or {(r['group'],r['stage'],r['cell']) for r in rows}!=EXPECTED_STAGES:
                raise ValueError('Missing or duplicated expected synchronizer stage')
            for r in rows:
                expected_ref = 'FDCE' if r['group']=='reset' else 'FDPE'
                if (r['ref_name']!=expected_ref or r['async_reg'].upper() not in {'TRUE','1'}
                        or not r['loc'].startswith('SLICE_X') or not r['bel'] or r['async_control_net']=='-'):
                    raise ValueError('Invalid async stage primitive, placement, reset connection or ASYNC_REG')
            edge_rows = records(audit/'interstage_timing.tsv',
                                ['group','from_stage','to_stage','shared_qd_net','max_slack_ns','min_slack_ns','status'])
            if len(edge_rows)!=3 or {(r['group'],r['from_stage'],r['to_stage']) for r in edge_rows}!=EXPECTED_EDGES:
                raise ValueError('Missing or duplicated direct interstage edge')
            for r in edge_rows:
                if r['status']!='DIRECT_AND_TIMED' or r['shared_qd_net']=='-':
                    raise ValueError('Missing direct/timed synchronizer path')
                slacks=[float(r['max_slack_ns']),float(r['min_slack_ns'])]
                if not all(math.isfinite(x) and x>=0 for x in slacks):
                    raise ValueError('Failing or invalid interstage timing')
            rx = records(audit/'async_input.tsv',
                         ['port','buffer_cell','buffer_ref','first_stage_cell','buffer_to_stage_net','status'])
            if len(rx)!=1 or rx[0]['port']!='uart_rx_i' or rx[0]['first_stage_cell']!='receiver/sync_q_reg[0]':
                raise ValueError('Wrong external RX source or first synchronizer stage')
            if (not rx[0]['buffer_ref'].startswith('IBUF') or rx[0]['buffer_to_stage_net']=='-'
                    or rx[0]['status']!='IBUF_TO_FIRST_STAGE_DIRECT'):
                raise ValueError('UART RX input not buffered directly to first synchronizer stage')
            for name in REPORTS:
                p=audit/name
                if not p.is_file() or p.stat().st_size < 80:
                    raise ValueError(f'Missing/short Vivado diagnostics: {name}')
            check=(audit/'check_timing.rpt').read_text(encoding='utf-8',errors='replace')
            method=(audit/'methodology.rpt').read_text(encoding='utf-8',errors='replace')
            if 'rst_n' not in check or 'uart_rx_i' not in check:
                raise ValueError('check_timing no longer exposes unresolved asynchronous inputs')
            if 'TIMING-18' not in method:
                # Not an automatic error: still no input-delay model. But require human inspection.
                result['methodology_missing_delay_warning'] = 'NOT_FOUND_REQUIRES_INVESTIGATION'
            else:
                result['methodology_missing_delay_warning'] = 'PRESENT_REQUIRES_MANUAL_REVIEW'
            result['interstage_timing_ns'] = [dict(r) for r in edge_rows]
            result['stage_count'] = 5
            result['rx_input_buffered_directly_to_first_stage'] = True
            result['report_sha256']={name:file_hash(audit/name) for name in REPORTS}
    except (OSError, ValueError, KeyError, TypeError, OverflowError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    result['issues']=issues
    result['verdict']=('NOT_VERIFIED' if issues else 'PHASE17_PROVENANCE_VERIFIED' if audit is None
                       else 'ASYNC_BOUNDARY_EVIDENCE_REVIEW_REQUIRED')
    return result


def main(argv: list[str] | None=None) -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--phase17',type=Path,default=PHASE17_DEFAULT)
    ap.add_argument('--audit',type=Path)
    ap.add_argument('--preflight-only',action='store_true')
    args=ap.parse_args(argv)
    if args.preflight_only and args.audit is not None:
        ap.error('preflight does not accept --audit')
    if not args.preflight_only and args.audit is None:
        ap.error('pass --audit or --preflight-only')
    result=inspect(args.phase17, None if args.preflight_only else args.audit)
    if args.audit is not None and args.audit.is_dir():
        (args.audit/'verification.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0 if result['verdict']==('PHASE17_PROVENANCE_VERIFIED' if args.preflight_only else 'ASYNC_BOUNDARY_EVIDENCE_REVIEW_REQUIRED') else 2

if __name__=='__main__':
    sys.exit(main())
