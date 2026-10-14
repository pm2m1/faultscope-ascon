"""Phase 17: compare a fresh CONFIG-voltage Vivado route against preserved Phase 15.

Only accepts a *routed candidate for manual review*, never physical-board signoff.
"""
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
from scripts.phase16_gap_report import baseline
from scripts.phase15_board_report import PINS, records, kv, file_sha

BASE_XDC = ROOT / 'constraints' / 'phase15_nexys4_ddr_rev_c.xdc'
OVERLAY = ROOT / 'constraints' / 'phase17_cfg_rev_c_overlay.xdc'
PHASE15_DEFAULT = ROOT / 'build' / 'reproduction' / 'phase15' / 'nexys4_ddr_rev_c_20261014T045950Z'
OVERLAY_CMDS = {
    'set_property CFGBVS VCCO [current_design]',
    'set_property CONFIG_VOLTAGE 3.3 [current_design]',
}
REQUIRED_REPORTS = (
    'post_route.dcp', 'post_route_drc.rpt', 'post_route_timing.rpt',
    'post_route_status.rpt', 'post_route_utilization.rpt',
    'methodology.rpt', 'clock_interaction.rpt', 'clock_networks.rpt',
    'check_timing.rpt', 'cdc.rpt', 'IMPLEMENTATION_COMPLETE',
)
RTLS = ('ascon_round.sv','ascon_permutation_faultable.sv','ascon_permutation_temporal.sv',
        'ascon_aead_encrypt_temporal.sv','fs_reset_sync.sv','fs_uart_rx.sv',
        'fs_uart_tx.sv','faultscope_uart_top.sv')


def validate_overlay(path: Path = OVERLAY) -> None:
    text = path.read_text(encoding='utf-8')
    commands = [x.strip() for x in text.splitlines() if x.strip() and not x.lstrip().startswith('#')]
    if len(commands) != 2 or set(commands) != OVERLAY_CMDS:
        raise ValueError('Phase 17 config overlay must contain exactly CFGBVS=VCCO and CONFIG_VOLTAGE=3.3')
    if 'Nexys 4 DDR' not in text or 'Rev. C' not in text or 'CFG_BVS_0' not in text:
        raise ValueError('Missing physical-board schematic provenance/commentary')


def inspect(phase15: Path, candidate: Path | None, overlay: Path = OVERLAY) -> dict:
    result = {
        'phase': '17',
        'scope': 'PROVISIONAL Nexys 4 DDR Rev. C separate routed configuration-voltage candidate',
        'board_revision_confirmed': False, 'board_programmed': False,
        'bitstream_generated': False, 'board_signoff': 'NOT VERIFIED',
        'external_io_timing': 'NOT VERIFIED', 'uart_metastability_mtbf': 'NOT VERIFIED',
        'reset_recovery_removal': 'NOT VERIFIED', 'clock_jitter_hardware': 'NOT VERIFIED',
        'drc_manual_review': 'REQUIRED', 'methodology_manual_review': 'REQUIRED',
    }
    issues = []
    try:
        validate_overlay(overlay)
        b = baseline(phase15)  # Phase 16 verifies original checkpoint, accepted XDC and CRLF equivalence.
        result['phase15_checkpoint_sha256'] = b['checkpoint_sha256']
        result['phase15_original_xdc_sha256'] = b['accepted_xdc_sha256']
        result['phase15_xdc_checkout_mode'] = b['xdc_provenance_mode']
        result['phase15_setup_slack_ns'] = b['internal_setup_slack_ns']
        result['phase15_hold_slack_ns'] = b['internal_hold_slack_ns']
        result['overlay_sha256'] = file_sha(overlay)
        if candidate is not None:
            for name in REQUIRED_REPORTS + ('source_context.tsv', 'pin_assignment.tsv',
                                           'synchronizer_cells.tsv', 'synchronizer_edges.tsv', 'internal_metrics.tsv'):
                path = candidate / name
                if not path.is_file() or path.stat().st_size == 0:
                    raise ValueError(f'missing/empty Phase 17 output: {name}')
            cx, m = kv(candidate/'source_context.tsv'), kv(candidate/'internal_metrics.tsv')
            if cx.get('phase') != '17' or cx.get('top') != 'faultscope_uart_top' or cx.get('part') != 'xc7a100tcsg324-1':
                raise ValueError('wrong Phase 17 top/part/phase')
            if cx.get('board') != 'PROVISIONAL Nexys 4 DDR Rev. C' or cx.get('design_mode') != 'full_board_not_ooc':
                raise ValueError('out-of-context or wrong-board candidate')
            if not re.fullmatch(r'20\d\d\.\d+', cx.get('vivado_version', '')):
                raise ValueError('unknown Vivado version')
            if cx.get('rtl_sources') != ','.join(RTLS):
                raise ValueError('RTL source set does not match Phase 15')
            if not cx.get('xdc','').replace('\\','/').lower().endswith('/constraints/phase15_nexys4_ddr_rev_c.xdc'):
                raise ValueError('unexpected base XDC provenance')
            if not cx.get('overlay','').replace('\\','/').lower().endswith('/constraints/phase17_cfg_rev_c_overlay.xdc'):
                raise ValueError('unexpected overlay provenance')
            per = float(cx.get('clock_period_ns','nan'))
            volt = float(cx.get('config_voltage','nan'))
            if not math.isfinite(per) or abs(per-10.0)>1e-5 or not math.isfinite(volt) or abs(volt-3.3)>1e-5:
                raise ValueError('wrong clock or configuration bank voltage')
            if cx.get('cfgbvs') != 'VCCO':
                raise ValueError('CFGBVS was not retained in new routed checkpoint')
            pins = records(candidate/'pin_assignment.tsv',['port','direction','package_pin','iostandard'])
            if len(pins)!=6 or {p['port'] for p in pins}!=set(PINS):
                raise ValueError('new design has missing/duplicate top-level ports')
            if any((p['direction'],p['package_pin'])!=PINS[p['port']] or p['iostandard']!='LVCMOS33' for p in pins):
                raise ValueError('Phase 17 altered the board pin map or voltage')
            cells = records(candidate/'synchronizer_cells.tsv',['cell','ref_name','async_reg','loc','bel'])
            expected={f'u_reset_sync/release_pipe_q_reg[{i}]' for i in range(3)} | {f'receiver/sync_q_reg[{i}]' for i in range(2)}
            if len(cells)!=5 or {c['cell'] for c in cells} != expected:
                raise ValueError('Phase 17 lost or duplicated synchronizer FFs')
            for c in cells:
                if not c['ref_name'].startswith('FD') or c['async_reg'].upper() not in {'1','TRUE'} or not c['loc'].startswith('SLICE_X') or 'FF' not in c['bel']:
                    raise ValueError('synchronizer primitive/attribute/placement changed')
            edges = records(candidate/'synchronizer_edges.tsv',['group','from_stage','to_stage','net','status'])
            desired = {('reset','0','1'),('reset','1','2'),('rx','0','1')}
            if len(edges)!=3 or {(e['group'],e['from_stage'],e['to_stage']) for e in edges}!=desired:
                raise ValueError('wrong synchronizer edges')
            if any(e['status'] != 'DIRECT' or e['net']=='-' for e in edges):
                raise ValueError('synchronizer chain interstage connection not direct')
            if int(m.get('register_count','0'))<5 or m.get('setup_path_count')!='1' or m.get('hold_path_count')!='1':
                raise ValueError('missing internal timing coverage')
            su, ho = float(m.get('setup_slack_ns','nan')), float(m.get('hold_slack_ns','nan'))
            if not (math.isfinite(su) and math.isfinite(ho)) or su<0 or ho<0:
                raise ValueError('negative/nonfinite internal setup or hold slack')
            drc = (candidate/'post_route_drc.rpt').read_text(encoding='utf-8',errors='replace')
            if 'Report DRC' not in drc or 'REPORT SUMMARY' not in drc.upper():
                raise ValueError('Vivado DRC report does not have recognizable header')
            if re.search(r'\bCFGBVS-1\b',drc):
                raise ValueError('CFGBVS-1 still appears in new DRC report; investigate')
            result['configuration_property_state'] = 'APPLIED_IN_ROUTED_CANDIDATE_NOT_BOARD_SIGNOFF'
            result['cfgbvs_1_detected_in_drc'] = False
            result['phase17_setup_slack_ns'], result['phase17_hold_slack_ns'] = su, ho
            result['setup_delta_vs_phase15_ns'] = round(su - b['internal_setup_slack_ns'],6)
            result['hold_delta_vs_phase15_ns'] = round(ho - b['internal_hold_slack_ns'],6)
            result['phase17_checkpoint_sha256'] = file_sha(candidate/'post_route.dcp')
            result['report_sha256'] = {n:file_sha(candidate/n) for n in REQUIRED_REPORTS if n.endswith('.rpt')}
    except (OSError, KeyError, ValueError, TypeError, OverflowError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    result['issues'] = issues
    result['verdict'] = ('NOT_VERIFIED' if issues else 'BASELINE_AND_OVERLAY_VERIFIED' if candidate is None
                         else 'ROUTED_CFG_CANDIDATE_REVIEW_REQUIRED')
    return result


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase15', type=Path, default=PHASE15_DEFAULT)
    p.add_argument('--overlay', type=Path, default=OVERLAY)
    p.add_argument('--candidate', type=Path)
    p.add_argument('--preflight-only', action='store_true')
    a=p.parse_args(argv)
    if a.preflight_only and a.candidate:
        p.error('--preflight-only cannot be combined with --candidate')
    if not a.preflight_only and not a.candidate:
        p.error('--candidate is required unless --preflight-only')
    r=inspect(a.phase15,None if a.preflight_only else a.candidate,a.overlay)
    if a.candidate and a.candidate.is_dir():
        (a.candidate/'verification.json').write_text(json.dumps(r,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(r,sort_keys=True,indent=2))
    return 0 if r['verdict']==('BASELINE_AND_OVERLAY_VERIFIED' if a.preflight_only else 'ROUTED_CFG_CANDIDATE_REVIEW_REQUIRED') else 2

if __name__=='__main__':
    sys.exit(main())
