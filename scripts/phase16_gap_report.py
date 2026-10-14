"""Fail-closed Phase 16 *evidence-collection* review; never a board signoff."""
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
from scripts.phase15_board_report import inspect as inspect_phase15, PINS
XDC = ROOT / 'constraints' / 'phase15_nexys4_ddr_rev_c.xdc'
# SHA-256 of the accepted Phase 15 XDC as originally written (LF endings).
# From the Phase 15 verification.json and archived pilot artifact.
ACCEPTED_PHASE15_XDC_SHA256 = '69bddc36a6142b41c47e4335bd3cb56e1051fe0cf52a33491fdcfd2338ffa4d8'
REPORTS = (
    'drc.rpt', 'methodology.rpt', 'clock_interaction.rpt',
    'clock_networks.rpt', 'timing_summary.rpt', 'check_timing.rpt', 'cdc.rpt',
)
STAGES = {
    'config_voltage': 'OPEN',
    'default_drc': 'MANUAL_REVIEW',
    'methodology': 'MANUAL_REVIEW',
    'clock_topology': 'MANUAL_REVIEW',
    'uart_async_input_and_mtbf': 'OPEN',
    'external_uart_tx_timing': 'OPEN',
    'led_external_timing': 'OPEN',
    'reset_recovery_removal': 'OPEN',
    'reset_button_bounce_and_power_up': 'HARDWARE_DEPENDENT',
    'board_revision_identification': 'HARDWARE_DEPENDENT',
    'programming_and_uarts': 'HARDWARE_DEPENDENT',
}


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_tsv(path: Path, headers: list[str]) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        rd = csv.DictReader(f, delimiter='\t')
        if rd.fieldnames != headers:
            raise ValueError(f'{path.name}: wrong columns: {rd.fieldnames}')
        rows = list(rd)
    if not rows or any(None in r or any(v is None or not str(v).strip() for v in r.values()) for r in rows):
        raise ValueError(f'{path.name}: blank/malformed rows')
    return rows


def kv(path: Path) -> dict[str, str]:
    records = read_tsv(path, ['key', 'value'])
    keys = [r['key'] for r in records]
    if len(set(keys)) != len(keys):
        raise ValueError(f'{path.name}: duplicate key')
    return {r['key']: r['value'] for r in records}



def _xdc_provenance_mode(raw: bytes, accepted_hash: str) -> str | None:
    """Accept byte-identical XDC or a *uniform CRLF* checkout of accepted LF bytes.

    Normalizes only newline encoding; every other byte must match the accepted
    Phase 15 SHA-256. Mixed/bare-CR line endings and semantic edits are rejected.
    """
    if hashlib.sha256(raw).hexdigest() == accepted_hash:
        return 'BYTE_IDENTICAL'
    if (b'\r\n' not in raw or
            raw.count(b'\r\n') != raw.count(b'\n') or
            raw.count(b'\r\n') != raw.count(b'\r')):
        return None
    original_lf = raw.replace(b'\r\n', b'\n')
    if hashlib.sha256(original_lf).hexdigest() == accepted_hash:
        return 'CRLF_CHECKOUT_EQUIVALENT_TO_ACCEPTED_LF'
    return None


def baseline(phase15: Path) -> dict:
    """Trust only a passing Phase 15 candidate with matching saved hashes."""
    saved = json.loads((phase15 / 'verification.json').read_text(encoding='utf-8'))
    if saved.get('verdict') != 'CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED' or saved.get('issues'):
        raise ValueError('Phase 15 is not a passing candidate')
    candidate = inspect_phase15(phase15, XDC)
    if candidate['verdict'] != 'CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED':
        raise ValueError('Phase 15 candidate no longer validates: ' + str(candidate.get('issues')))
    if saved.get('checkpoint_sha256') != candidate.get('checkpoint_sha256'):
        raise ValueError('Phase 15 routed checkpoint hash differs from accepted evidence')
    if saved.get('xdc_sha256') != ACCEPTED_PHASE15_XDC_SHA256:
        raise ValueError('Phase 15 accepted XDC digest does not match the pinned original')
    # Git for Windows can check out a previously accepted LF XDC with CRLF
    # endings. Retain raw checkpoint-hash validation; allow only that exact
    # XDC's newline-equivalent bytes, never a different XDC or changed pins.
    mode = _xdc_provenance_mode(XDC.read_bytes(), saved['xdc_sha256'])
    if mode is None:
        raise ValueError('Phase 15 XDC content differs from accepted evidence (not a uniform LF/CRLF conversion)')
    candidate['accepted_xdc_sha256'] = saved['xdc_sha256']
    candidate['xdc_provenance_mode'] = mode
    return candidate


def inspect(phase15: Path, audit: Path | None) -> dict:
    issues: list[str] = []
    result: dict = {
        'phase': '16', 'scope': 'read-only Phase 15 post-route signoff-gap audit',
        'board': 'PROVISIONAL Nexys 4 DDR Rev. C',
        'board_revision_confirmed': False, 'bitstream_generated': False,
        'board_programmed': False, 'board_signoff': 'NOT VERIFIED',
        'analog_mtbf': 'NOT VERIFIED', 'physical_reset_behavior': 'NOT VERIFIED',
        'signoff_gaps': dict(STAGES),
    }
    try:
        p15 = baseline(phase15)
        result['phase15_checkpoint_sha256'] = p15['checkpoint_sha256']
        result['phase15_xdc_sha256'] = p15.get('accepted_xdc_sha256', p15['xdc_sha256'])
        result['phase15_current_xdc_sha256'] = p15['xdc_sha256']
        result['phase15_xdc_provenance_mode'] = p15.get('xdc_provenance_mode', 'NOT_RECORDED')
        result['phase15_setup_slack_ns'] = p15['internal_setup_slack_ns']
        result['phase15_hold_slack_ns'] = p15['internal_hold_slack_ns']
        if audit is not None:
            cx = kv(audit / 'context.tsv')
            if cx.get('phase') != '16' or cx.get('design_name') not in {'checkpoint_post_route', 'faultscope_uart_top'}:
                raise ValueError('wrong Phase 16 routed checkpoint context')
            if cx.get('clock_name') != 'board_clk_100mhz':
                raise ValueError('board clock is absent or renamed')
            p = float(cx.get('clock_period_ns', 'nan'))
            if not math.isfinite(p) or abs(p - 10) > 1e-5:
                raise ValueError('incorrect Phase 16 clock period')
            if not re.fullmatch(r'20\d\d\.\d+', cx.get('vivado_version', '')):
                raise ValueError('Vivado version missing')
            if int(cx.get('clock_buffers', '-1')) < 1 or int(cx.get('input_buffers', '-1')) < 1:
                raise ValueError('missing clock or input buffers')
            props = (cx.get('cfgbvs'), cx.get('config_voltage'))
            if props == ('UNSET', 'UNSET'):
                result['configuration_property_state'] = 'MISSING_IN_PHASE15_CHECKPOINT'
            elif props == ('VCCO', '3.3'):
                result['configuration_property_state'] = 'MATCHES_SCHEMATIC_PROPOSAL_NOT_SIGNOFF'
            else:
                raise ValueError(f'unexpected configuration property combination: {props!r}')
            rows = read_tsv(audit / 'ports.tsv', ['port', 'direction', 'package_pin', 'iostandard'])
            if len(rows) != len(PINS) or {r['port'] for r in rows} != set(PINS):
                raise ValueError('missing or extra board ports')
            for r in rows:
                if (r['direction'], r['package_pin']) != PINS[r['port']] or r['iostandard'] != 'LVCMOS33':
                    raise ValueError('mismatched Phase 16 package pin/direction/voltage: ' + str(r))
            for n in REPORTS:
                path = audit / n
                if not path.is_file() or path.stat().st_size < 32:
                    raise ValueError(f'Phase 16 report missing/short: {n}')
            result['phase16_report_sha256'] = {n: file_hash(audit / n) for n in REPORTS}
            result['phase16_clock_period_ns'] = p
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        issues.append(str(exc))
    result['issues'] = issues
    result['verdict'] = 'EVIDENCE_COLLECTED_REVIEW_REQUIRED' if not issues and audit is not None else (
        'PHASE15_PROVENANCE_PASS' if not issues else 'NOT_VERIFIED')
    return result


def write_output(audit: Path, result: dict) -> None:
    (audit / 'verification.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    with (audit / 'gap_matrix.tsv').open('w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['check', 'status', 'meaning'])
        meanings = {
            'config_voltage': 'Rev. C schematic proposal VCCO/3.3; original Phase 15 DCP unchanged',
            'default_drc': 'Inspect drc.rpt for CFGBVS and other warnings',
            'methodology': 'Inspect methodology.rpt; no auto-acceptance',
            'clock_topology': 'Inspect clock_networks.rpt and clock_interaction.rpt',
            'uart_async_input_and_mtbf': 'Externally asynchronous input; no analog MTBF or complete CDC signoff',
            'external_uart_tx_timing': 'No documented board/bridge output timing budget',
            'led_external_timing': 'No validated external output timing budget',
            'reset_recovery_removal': 'No physical reset recovery/removal signoff',
            'reset_button_bounce_and_power_up': 'Needs physical board stimulus and clock-up evidence',
            'board_revision_identification': 'Provisional board variant not physically confirmed',
            'programming_and_uarts': 'No bitstream/hardware performed',
        }
        for k, v in result['signoff_gaps'].items():
            w.writerow([k, v, meanings[k]])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase15', required=True, type=Path)
    p.add_argument('--audit', type=Path)
    p.add_argument('--preflight-only', action='store_true')
    p.add_argument('--require-evidence', action='store_true')
    args = p.parse_args(argv)
    if args.preflight_only and args.audit is not None:
        p.error('preflight does not accept --audit')
    if not args.preflight_only and args.audit is None:
        p.error('--audit is required unless --preflight-only')
    result = inspect(args.phase15, None if args.preflight_only else args.audit)
    if not args.preflight_only:
        write_output(args.audit, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['verdict'] == ('PHASE15_PROVENANCE_PASS' if args.preflight_only else 'EVIDENCE_COLLECTED_REVIEW_REQUIRED') else 2


if __name__ == '__main__':
    sys.exit(main())
