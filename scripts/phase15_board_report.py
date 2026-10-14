"""Strict Phase 15 *candidate implementation* review; never a board signoff.

The provisional Nexys 4 DDR Rev. C XDC is intentionally narrow and has no
fabricated input/output delays or CDC timing exceptions.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

PINS = {
    'clk': ('IN', 'E3'),
    'rst_n': ('IN', 'C12'),
    'uart_rx_i': ('IN', 'C4'),
    'uart_tx_o': ('OUT', 'D4'),
    'led_busy_o': ('OUT', 'H17'),
    'led_alarm_o': ('OUT', 'K15'),
}
XDC_LINES = {f'set_property -dict {{ PACKAGE_PIN {pin} IOSTANDARD LVCMOS33 }} [get_ports {{{port}}}]'
             for port, (_, pin) in PINS.items()}
XDC_LINES.add('create_clock -name board_clk_100mhz -period 10.000 -waveform {0.000 5.000} [get_ports {clk}]')
REQUIRED = ('source_context.tsv', 'internal_metrics.tsv', 'pin_assignment.tsv',
            'synchronizer_cells.tsv', 'synchronizer_edges.tsv', 'post_route.dcp', 'post_route_timing.rpt',
            'post_route_drc.rpt', 'post_route_status.rpt', 'check_timing.rpt',
            'cdc.rpt', 'clock_networks.rpt', 'IMPLEMENTATION_COMPLETE')


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_xdc(path: Path) -> None:
    raw = path.read_text(encoding='utf-8')
    commands = {line.strip() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith('#')}
    # Fail even when unwanted commands duplicate an allowed command.
    command_list = [line.strip() for line in raw.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if len(command_list) != len(XDC_LINES) or commands != XDC_LINES:
        raise ValueError('Wrong, extra, duplicated or missing XDC command (no exceptions/guessed I/O delays allowed)')
    if 'Nexys-4-DDR-Master.xdc' not in raw or 'Rev. C' not in raw:
        raise ValueError('Nexys 4 DDR Rev. C provenance missing')


def records(path: Path, fields: list[str]) -> list[dict[str, str]]:
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if reader.fieldnames != fields:
            raise ValueError(f'{path.name}: unexpected TSV columns {reader.fieldnames}')
        result = list(reader)
    if not result:
        raise ValueError(f'{path.name}: empty records')
    if any(None in r or any(v is None or not v.strip() for v in r.values()) for r in result):
        raise ValueError(f'{path.name}: blank or malformed fields')
    return result


def kv(path: Path) -> dict[str, str]:
    result = records(path, ['key', 'value'])
    keys = [row['key'] for row in result]
    if len(keys) != len(set(keys)):
        raise ValueError(f'{path.name}: duplicate context key')
    return {r['key']: r['value'] for r in result}


def inspect(root: Path, xdc: Path) -> dict:
    issues: list[str] = []
    result = {
        'phase': '15', 'board': 'PROVISIONAL Nexys 4 DDR Rev. C',
        'board_revision_confirmed': False, 'board_programmed': False,
        'bitstream_generated': False, 'external_io_timing': 'NOT VERIFIED',
        'uart_metastability_mtbf': 'NOT VERIFIED',
        'reset_recovery_removal': 'NOT VERIFIED',
        'board_level_signoff': 'NOT VERIFIED',
        'drc_manual_review': 'REQUIRED', 'clock_network_manual_review': 'REQUIRED',
    }
    try:
        validate_xdc(xdc)
        result['xdc_sha256'] = file_sha(xdc)
    except (OSError, ValueError) as exc:
        issues.append(str(exc))
    for name in REQUIRED:
        path = root / name
        if not path.is_file() or path.stat().st_size == 0:
            issues.append(f'missing or empty implementation evidence: {name}')
    if not issues:
        try:
            context, metrics = kv(root / 'source_context.tsv'), kv(root / 'internal_metrics.tsv')
            if context.get('board') != 'PROVISIONAL Nexys 4 DDR Rev. C':
                raise ValueError('wrong board scope')
            if context.get('top') != 'faultscope_uart_top' or context.get('part') != 'xc7a100tcsg324-1':
                raise ValueError('wrong FPGA part or top')
            if context.get('design_mode') != 'full_board_not_ooc':
                raise ValueError('OOC implementation is not board implementation')
            import math
            clock_period = float(context.get('clock_period_ns', 'nan'))
            if not math.isfinite(clock_period) or abs(clock_period - 10.0) > 1e-5:
                raise ValueError('incorrect board clock')
            if not re.fullmatch(r'20\d\d\.\d+', context.get('vivado_version', '')):
                raise ValueError('Vivado version unrecognized')
            source_xdc = context.get('xdc', '').replace('\\', '/').lower()
            if not source_xdc.endswith('/constraints/phase15_nexys4_ddr_rev_c.xdc'):
                raise ValueError('wrong XDC path provenance')
            pins = records(root / 'pin_assignment.tsv', ['port', 'direction', 'package_pin', 'iostandard'])
            if len(pins) != 6 or len({p['port'] for p in pins}) != 6:
                raise ValueError('expected six distinct board ports')
            for p in pins:
                if p['port'] not in PINS or (p['direction'], p['package_pin']) != PINS[p['port']] or p['iostandard'] != 'LVCMOS33':
                    raise ValueError('invalid pin/direction/IOSTANDARD: ' + str(p))
            flops = records(root / 'synchronizer_cells.tsv', ['cell','ref_name','async_reg','loc','bel'])
            expected = {'u_reset_sync/release_pipe_q_reg[' + str(i) + ']' for i in range(3)}
            expected |= {'receiver/sync_q_reg[' + str(i) + ']' for i in range(2)}
            if len(flops) != 5 or {r['cell'] for r in flops} != expected:
                raise ValueError('missing or duplicated synchronizer stages')
            for f in flops:
                if not f['ref_name'].startswith('FD') or f['async_reg'].upper() not in {'TRUE','1'} or not f['loc'].startswith('SLICE_X') or 'FF' not in f['bel']:
                    raise ValueError('lost mapped stage or location: ' + f['cell'])
            edges = records(root / 'synchronizer_edges.tsv', ['group','from_stage','to_stage','net','status'])
            want_edges = {('reset','0','1'), ('reset','1','2'), ('rx','0','1')}
            if len(edges) != 3 or {(e['group'],e['from_stage'],e['to_stage']) for e in edges} != want_edges:
                raise ValueError('missing or duplicated synchronization edge')
            if any(e['status'] != 'DIRECT' or e['net'] == '-' for e in edges):
                raise ValueError('not all synchronizer connections are direct')
            if int(metrics.get('register_count', '0')) < 5 or metrics.get('setup_path_count') != '1' or metrics.get('hold_path_count') != '1':
                raise ValueError('missing internal timing coverage')
            setup, hold = float(metrics['setup_slack_ns']), float(metrics['hold_slack_ns'])
            if not math.isfinite(setup) or not math.isfinite(hold):
                raise ValueError('nonfinite timing values')
            result['internal_setup_slack_ns'], result['internal_hold_slack_ns'] = setup, hold
            if setup < 0 or hold < 0:
                raise ValueError('internal setup or hold slack negative')
            # Keep full DRC and routing report review manual. They need contextual signoff.
            result['checkpoint_sha256'] = file_sha(root / 'post_route.dcp')
        except (OSError, KeyError, ValueError) as exc:
            issues.append(str(exc))
    result['issues'] = issues
    result['verdict'] = 'CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED' if not issues else 'NOT_VERIFIED'
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, nargs='?')
    parser.add_argument('--xdc', type=Path, default=Path('constraints/phase15_nexys4_ddr_rev_c.xdc'))
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--require-candidate', action='store_true')
    args = parser.parse_args(argv)
    if args.preflight_only:
        try:
            validate_xdc(args.xdc)
            print('PASS: provisional Nexys 4 DDR Rev. C exact six-port XDC preflight')
            return 0
        except (ValueError, OSError) as exc:
            print('FAIL: XDC preflight: ' + str(exc))
            return 2
    if args.output is None:
        parser.error('output directory required unless --preflight-only')
    result = inspect(args.output, args.xdc)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['verdict'] == 'CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED' else 2


if __name__ == '__main__':
    sys.exit(main())
