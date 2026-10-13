"""Strict Phase 12 evidence reader; absent or ambiguous evidence never means pass."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path

DESIGNS = ('baseline', 'instrumented', 'protected', 'uart_protected')
PART = 'xc7a100tcsg324-1'


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8-sig', errors='replace') if path.is_file() else ''


def tsv(path: Path) -> dict:
    return dict(line.split('\t', 1) for line in read(path).splitlines() if '\t' in line)


def table_value(text: str, labels: tuple[str, ...]) -> float:
    for label in labels:
        matches = re.findall(r'^\|\s*' + re.escape(label) + r'\s*\*?\s*\|\s*([\d,.]+)\s*\|', text, re.M)
        if matches:
            return float(matches[0].replace(',', ''))
    raise ValueError('Missing utilization row: ' + '/'.join(labels))


def utilization(text: str) -> dict:
    if 'Device' not in text or PART not in text:
        raise ValueError('Missing or incorrect utilization device')
    result = {}
    for key, labels in {
        'lut': ('Slice LUTs', 'CLB LUTs'), 'ff': ('Register as Flip Flop',),
        'carry4': ('CARRY4',), 'bram_tiles': ('Block RAM Tile',), 'bram18': ('RAMB18',), 'bram36': ('RAMB36/FIFO',), 'dsp': ('DSPs', 'DSP48E1'),
    }.items():
        if key == 'carry4' and not re.search(r'^\|\s*CARRY4\s*\|', text, re.M):
            if not re.search(r'\d+\. Primitives', text) or '| Ref Name' not in text:
                raise ValueError('Missing primitive table')
            result[key] = 0
        else:
            result[key] = table_value(text, labels)
    for key in ('lut', 'ff', 'carry4', 'bram18', 'bram36', 'dsp'):
        if result[key] != int(result[key]):
            raise ValueError('Non-integral primitive count')
        result[key] = int(result[key])
    if result['lut'] <= 0 or result['ff'] <= 0:
        raise ValueError('Empty implementation')
    return result


def route_status(text: str) -> dict:
    # Vivado report_route_status uses this exact label for total unrouted nets.
    match = re.search(r'# of unrouted nets[.\s]*[:=]?\s*(\d+)', text, re.I)
    errors = re.search(r'# of nets with routing errors[.\s]*[:=]?\s*(\d+)', text, re.I)
    routable = re.search(r'# of routable nets[.\s]*[:=]?\s*(\d+)', text, re.I)
    fully = re.search(r'# of fully routed nets[.\s]*[:=]?\s*(\d+)', text, re.I)
    return {'unrouted_nets': int(match[1]) if match else (int(routable[1]) - int(fully[1]) if routable and fully else None),
            'routing_error_nets': int(errors[1]) if errors else None,
            'routable_nets': int(routable[1]) if routable else None,
            'fully_routed_nets': int(fully[1]) if fully else None}


def constraint_status(text: str) -> dict:
    patterns = {
        'no_clock_register_pins': r'There (?:are|is) (\d+) register/latch pins? with no clock',
        'multiple_clock_register_pins': r'There (?:are|is) (\d+) register/latch pins? with multiple clocks',
        'unconstrained_internal_endpoints': r'There (?:are|is) (\d+) pins? that (?:are|is) not constrained for maximum delay',
    }
    result = {k: int(m[1]) if (m := re.search(p, text, re.I)) else None for k, p in patterns.items()}
    for category in ('constant_clock', 'loops', 'latch_loops', 'generated_clocks'):
        m = re.search(r'checking ' + category + r' \((\d+)\)', text)
        result[category] = int(m[1]) if m else None
    return result


def timing_summary(text: str) -> dict:
    header = re.search(r'^\s*WNS\(ns\).*WPWS\(ns\).*$', text, re.M)
    if not header:
        raise ValueError('Missing design timing summary')
    lines = text[header.end():].splitlines()
    for line in lines:
        values = line.split()
        if len(values) == 12:
            try:
                numbers = [float(v) for v in values]
            except ValueError:
                continue
            if not all(math.isfinite(v) for v in numbers):
                raise ValueError('Non-finite timing summary')
            return dict(zip(('wns_ns', 'tns_ns', 'setup_failing', 'setup_endpoints', 'whs_ns', 'ths_ns', 'hold_failing', 'hold_endpoints', 'wpws_ns', 'tpws_ns', 'pulse_failing', 'pulse_endpoints'), numbers))
    raise ValueError('Unrecognized design timing summary')


def inspect_run(directory: Path) -> dict:
    meta = tsv(directory / 'run_metadata.tsv')
    metric = tsv(directory / 'internal_metrics.tsv')
    result = {'directory': directory.name, 'metadata': meta, 'implementation': 'NOT VERIFIED',
              'internal_setup_hold': 'NOT VERIFIED', 'external_timing': 'NOT VERIFIED',
              'wns_ns': None, 'whs_ns': None, 'utilization': {}, 'issues': []}
    try:
        for stage in ('post_synth', 'post_place', 'post_route'):
            result['utilization'][stage] = utilization(read(directory / f'{stage}_utilization.rpt'))
        for label, target in (('setup', 'wns_ns'), ('hold', 'whs_ns')):
            if int(metric.get(f'{label}_path_count', '0')) < 1:
                raise ValueError(f'No constrained {label} path')
            result[target] = float(metric[f'{label}_slack_ns'])
        if not all(math.isfinite(result[k]) for k in ('wns_ns', 'whs_ns')):
            raise ValueError('Non-finite timing slack')
        result['design_timing_summary'] = timing_summary(read(directory / 'post_route_timing.rpt'))
        result['critical_path'] = {k: v for k, v in metric.items() if 'point' in k}
        constraints = constraint_status(read(directory / 'check_timing.rpt'))
        result['constraints'] = constraints
        route = route_status(read(directory / 'post_route_status.rpt'))
        result['route'] = route
        drc = read(directory / 'post_route_drc.rpt')
        # The actual report must exist even when there are no violations.
        if not drc or 'DRC' not in drc:
            raise ValueError('Missing DRC report')
        result['drc_critical'] = bool(re.search(r'\b(?:critical\s+warning|error)\b', drc, re.IGNORECASE))
        required = ('IMPLEMENTATION_COMPLETE', 'post_route.dcp', 'post_route_timing.rpt', 'internal_setup_paths.rpt', 'internal_hold_paths.rpt')
        if any(not (directory / n).is_file() for n in required):
            raise ValueError('Incomplete implementation evidence')
        if meta.get('part') != PART or float(meta['period_ns']) != float(metric['clock_period_ns']):
            raise ValueError('Wrong target part or clock period')
        if route['unrouted_nets'] != 0 or route['routing_error_nets'] != 0:
            raise ValueError('Unverified or incomplete routing')
        if route['routable_nets'] is None or route['routable_nets'] <= 0 or route['fully_routed_nets'] != route['routable_nets']:
            raise ValueError('Fully routed net counts do not agree')
        if result['drc_critical']:
            raise ValueError('Critical DRC issue')
        result['implementation'] = 'VERIFIED'
        if meta.get('clock_source') != 'BUFGCTRL_X0Y0' or metric.get('clock_source') != meta.get('clock_source'):
            raise ValueError('OOC clock source context not verified')
        if any(v != 0 for v in constraints.values()):
            raise ValueError('Internal clock/endpoint coverage not verified')
        timing = result['design_timing_summary']
        if abs(timing['wns_ns'] - result['wns_ns']) > 0.002 or abs(timing['whs_ns'] - result['whs_ns']) > 0.002:
            raise ValueError('Path metrics disagree with full timing summary')
        result['internal_setup_hold'] = 'MET' if (result['wns_ns'] >= 0 and result['whs_ns'] >= 0 and timing['wpws_ns'] >= 0 and all(timing[k] == 0 for k in ('setup_failing','hold_failing','pulse_failing'))) else 'FAILED'
        if meta['design'] == 'uart_protected':
            ports = read(directory / 'top_ports.txt').splitlines()
            expected = ['clk', 'rst_n', 'uart_rx_i', 'uart_tx_o', 'led_busy_o', 'led_alarm_o']
            if sorted(ports) != sorted(expected):
                raise ValueError('UART synthesized scalar port mismatch')
            result['scalar_ports'] = sorted(ports)
    except (KeyError, ValueError) as error:
        result['internal_setup_hold'] = 'NOT VERIFIED'
        result['issues'].append(str(error))
    result['warnings'] = [line.strip() for line in read(directory.parent / (directory.name + '.log')).splitlines()
                          if line.startswith(('WARNING:', 'CRITICAL WARNING:', 'ERROR:'))]
    return result


def compare_overhead(runs: list[dict]) -> list[dict]:
    overhead = []
    for protected in runs:
        if protected['metadata'].get('design') != 'protected' or protected['implementation'] != 'VERIFIED':
            continue
        for base in runs:
            if base['metadata'].get('design') not in ('baseline', 'instrumented') or base['implementation'] != 'VERIFIED':
                continue
            if any(base['metadata'].get(k) != protected['metadata'].get(k) for k in ('part', 'vivado_version', 'period_ns', 'settings', 'clock_source')):
                continue
            p, b = protected['utilization']['post_route'], base['utilization']['post_route']
            overhead.append({'against': base['metadata']['design'], 'period_ns': float(protected['metadata']['period_ns']),
                             'lut_percent': 100 * (p['lut'] / b['lut'] - 1), 'ff_percent': 100 * (p['ff'] / b['ff'] - 1)})
    return overhead


def collection_status(runs: list[dict], expected_designs=None, expected_periods=None) -> dict:
    designs = list(DESIGNS if expected_designs is None else expected_designs)
    if not designs or len(designs) != len(set(designs)) or any(d not in DESIGNS for d in designs):
        raise ValueError('Expected designs must be a nonempty unique selection of known architectures')
    periods = None if expected_periods is None else [float(p) for p in expected_periods]
    if periods is not None and (not periods or len(periods) != len(set(periods)) or
            any(not math.isfinite(p) or not 2 <= p <= 1000 for p in periods)):
        raise ValueError('Expected periods must be finite, unique, and within 2..1000 ns')
    issues, seen = [], set()
    for run in runs:
        match = re.fullmatch(r'(.+)_([^_]+)ns', run['directory'])
        try:
            if not match:
                raise ValueError('Invalid run directory')
            design, period = match[1], float(match[2])
            if design not in DESIGNS or not math.isfinite(period) or not 2 <= period <= 1000:
                raise ValueError('Unexpected architecture or invalid period')
            if run['metadata'].get('design') != design or float(run['metadata']['period_ns']) != period:
                raise ValueError('Architecture/period metadata disagrees with directory')
            pair = (design, period)
            if pair in seen:
                raise ValueError('Duplicate architecture/period combination')
            seen.add(pair)
            if design not in designs or (periods is not None and period not in periods):
                raise ValueError('Unexpected architecture/period combination for selected scope')
        except (KeyError, ValueError) as error:
            issues.append(f"{run['directory']}: {error}")
    if periods is None:
        periods = sorted({period for _, period in seen})
    if not periods:
        issues.append('No expected clock periods available')
    missing = [{'design':d, 'period_ns':p} for p in periods for d in designs if (d,p) not in seen]
    full_complete = bool(periods) and not issues and all((d,p) in seen for p in periods for d in DESIGNS)
    return {'acceptance_scope': 'full-suite' if set(designs) == set(DESIGNS) else 'explicit-subset',
            'expected_designs': designs, 'expected_periods_ns': periods,
            'missing_expected_combinations': missing, 'collection_issues': issues,
            'full_suite_complete': full_complete}


def generate(root: Path, *, expected_designs=None, expected_periods=None, write_reports=True) -> dict:
    # Include unknown run-shaped directories so they cannot be silently ignored.
    runs = [inspect_run(p) for p in sorted(root.iterdir()) if p.is_dir() and (re.fullmatch(r'.+_[^_]+ns', p.name) or (p/'run_metadata.tsv').is_file())]
    provenance = json.loads(read(root / 'provenance.json')) if (root / 'provenance.json').is_file() else None
    summary = {'schema_version': 1, 'scope': 'OOC internal register-to-register setup/hold only; external IO/reset and board timing NOT VERIFIED',
               'provenance': provenance, 'runs': runs, 'overhead': compare_overhead(runs),
               'missing_architectures': [d for d in DESIGNS if not any(r['metadata'].get('design') == d for r in runs)],
               **collection_status(runs, expected_designs, expected_periods)}
    if not write_reports:
        return summary
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    fields = ['design', 'period_ns', 'implementation', 'internal_setup_hold', 'lut', 'ff', 'carry4', 'bram_tiles', 'dsp', 'wns_ns', 'whs_ns']
    rows = []
    with (root / 'comparison.csv').open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for r in runs:
            row = {k: r.get(k, 'NOT VERIFIED') for k in fields}
            row.update({k: r['metadata'].get(k, 'NOT VERIFIED') for k in ('design', 'period_ns')})
            row.update(r['utilization'].get('post_route', {}))
            row = {k: ('NOT VERIFIED' if row[k] is None else row[k]) for k in fields}
            writer.writerow(row)
            rows.append(row)
        for design in summary['missing_architectures']:
            row = dict.fromkeys(fields, 'NOT VERIFIED'); row['design'] = design
            writer.writerow(row); rows.append(row)
    lines = ['# Phase 12 implementation evidence', '', summary['scope'], '',
             '| Design | ns | Implementation | Internal setup/hold | LUT | FF | Carry4 | BRAM tiles | DSP | WNS ns | WHS ns |',
             '|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append('| ' + ' | '.join(str(row[k]) for k in fields) + ' |')
    lines += ['', 'Acceptance scope: ' + summary['acceptance_scope'],
              'Expected designs: ' + ', '.join(summary['expected_designs']),
              'Expected periods (ns): ' + str(summary['expected_periods_ns']),
              'Missing expected combinations: ' + json.dumps(summary['missing_expected_combinations']),
              'Collection issues: ' + json.dumps(summary['collection_issues']),
              'Full architecture set complete: ' + str(summary['full_suite_complete'])]
    lines += ['', 'Protected post-route overhead (same part/version/period/settings):', '']
    for item in summary['overhead']:
        lines.append(f"- Against {item['against']} at {item['period_ns']} ns: LUT {item['lut_percent']:.2f}%, FF {item['ff_percent']:.2f}%.")
    for r in runs:
        lines += ['', f"## {r['directory']}", '', f"Metadata: `{json.dumps(r['metadata'], sort_keys=True)}`", '',
                  f"Constraint checks: `{json.dumps(r.get('constraints'))}`; routing: `{json.dumps(r.get('route'))}`.", '',
                  'Issues: ' + ('; '.join(r['issues']) or 'No parser acceptance issues.'), '', 'Tool warnings:', '']
        lines += ['- ' + w for w in r['warnings']] or ['- None in log.']
    (root / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    hashes = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*')
              if p.is_file() and p.name != 'artifact_sha256.json'}
    (root / 'artifact_sha256.json').write_text(json.dumps(hashes, indent=2) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_root', type=Path)
    parser.add_argument('--require-verified', action='store_true', help='Exit nonzero for incomplete implementation/constraint evidence or failed timing')
    parser.add_argument('--expected-designs', nargs='+', choices=DESIGNS, help='Explicit selected architectures; default requires all four')
    parser.add_argument('--expected-periods', nargs='+', type=float, help='Explicit clock periods; default requires all selected architectures at every observed period')
    parser.add_argument('--validate-only', action='store_true', help='Read-only validation; preserve existing reports and inventories')
    args = parser.parse_args()
    try:
        result = generate(args.output_root.resolve(), expected_designs=args.expected_designs, expected_periods=args.expected_periods, write_reports=not args.validate_only)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({'runs': len(result['runs']), 'missing': result['missing_architectures'],
                      'acceptance_scope': result['acceptance_scope'],
                      'full_suite_complete': result['full_suite_complete'],
                      'missing_expected_combinations': result['missing_expected_combinations'],
                      'collection_issues': result['collection_issues'],
                      'status': [(r['directory'], r['implementation'], r['internal_setup_hold']) for r in result['runs']]}, indent=2))

    if args.require_verified:
        if not result['runs'] or result['missing_expected_combinations'] or result['collection_issues'] or any(r['implementation'] != 'VERIFIED' or r['internal_setup_hold'] == 'NOT VERIFIED' for r in result['runs']):
            sys.exit(2)
        if any(r['internal_setup_hold'] == 'FAILED' for r in result['runs']):
            sys.exit(3)
