"""Phase 10E: source-checked XC7A100T resource-fit screen, not a timing or board-fit proof.

Reads an existing Phase 10D out-of-context mapping report. Never writes to
committed reports or changes hardware RTL.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path
from datetime import datetime, timezone

from experiments.source_provenance import verify_rtl_source

ROOT = Path(__file__).resolve().parents[1]
PART = 'xc7a100tcsg324-1'
CAPACITY = {
    'lut_total': 63400,
    'flip_flops': 126800,
    'bram18_equivalents': 270,
    'dsp48': 240,
}
PACKAGE_USER_IO = 210
PINNED_RTL_SHA256 = 'd4f711fb95b7cd2d74f124a30360f2aa09ac3cdcd85ad3f7d74a66a469e84739'
DESIGNS = ('baseline', 'instrumented', 'protected')
SOURCE_URLS = {
    'logic': 'https://docs.amd.com/r/en-US/ug474_7Series_CLB/7-Series-FPGA-CLB-Resources',
    'board': 'https://digilent.com/reference/_media/reference/programmable-logic/nexys-a7/nexys-a7_rm.pdf',
    'package': 'https://docs.amd.com/api/khub/documents/kHyYQ6XzXnQwR2O~gaV~MQ/content',
    'package_io_ds180': 'https://www.xilinx.com/support/documentation/data_sheets/ds180_7Series_Overview.pdf',
}


def parse_top_ports(rtl: str, module: str='ascon_aead_encrypt_temporal') -> dict:
    """Read strictly ANSI-style declarations in the checked-in bounded AEAD top."""
    match = re.search(r'\bmodule\s+' + re.escape(module) + r'\s*\((.*?)\)\s*;', rtl, re.S)
    if not match:
        raise ValueError('Expected top module with ANSI port declarations not found')
    header = re.sub(r'//[^\n]*', '', match.group(1))
    parts = header.split(',')
    ports = {}
    for item in parts:
        item = item.strip()
        m = re.fullmatch(r'(input|output)\s+(?:logic|wire)\s+(?:\[\s*(\d+)\s*:\s*(\d+)\s*\]\s*)?([A-Za-z_]\w*)', item)
        if not m:
            raise ValueError(f'Unsupported or missing-width ANSI port declaration: {item!r}')
        direction, msb, lsb, name = m.groups()
        if name in ports:
            raise ValueError(f'Duplicate RTL port {name}')
        width = abs(int(msb)-int(lsb))+1 if msb is not None else 1
        ports[name] = {'direction': direction, 'bits': width}
    if not ports or 'clk' not in ports or 'result_valid_o' not in ports:
        raise ValueError('Unexpected RTL port set')
    return {
        'input_bits': sum(v['bits'] for v in ports.values() if v['direction']=='input'),
        'output_bits': sum(v['bits'] for v in ports.values() if v['direction']=='output'),
        'ports': ports,
    }


def validate_phase10d(data: dict) -> dict:
    if data.get('target_family') != 'xc7' or data.get('historical_rtl_verified') is not True:
        raise ValueError('Require a provenance-verified xc7 Phase 10D report')
    designs = data.get('architectures')
    if not isinstance(designs, dict) or set(designs) != set(DESIGNS):
        raise ValueError('Require exactly the three original architectures')
    checked = {}
    for label in DESIGNS:
        row = designs[label]
        if not isinstance(row,dict) or not isinstance(row.get('cell_types'),dict):
            raise ValueError(f'Missing mapped primitive inventory for {label}')
        for k in ('lut_total','flip_flops','bram18','bram36','dsp48'):
            v = row.get(k)
            if not isinstance(v,int) or isinstance(v,bool) or v<0:
                raise ValueError(f'Invalid {k} in {label}')
        if not row['lut_total'] or not row['flip_flops']:
            raise ValueError(f'Unmapped/empty design {label}')
        lut_sum=sum(row['cell_types'].get('LUT'+str(i),0) for i in range(1,7))
        if row['lut_total'] != lut_sum:
            raise ValueError(f'LUT count disagrees with primitive inventory for {label}')
        ff_sum=sum(row['cell_types'].get(k,0) for k in ('FDRE','FDSE','FDCE','FDPE'))
        if row['flip_flops'] != ff_sum:
            raise ValueError(f'FF count disagrees with primitive inventory for {label}')
        if any(k.startswith('$') and k!='$scopeinfo' for k in row['cell_types']):
            raise ValueError(f'Unmapped Yosys primitive in {label}')
        checked[label] = {
            'lut_total': row['lut_total'], 'flip_flops': row['flip_flops'],
            'bram18_equivalents': row['bram18']+2*row['bram36'], 'dsp48': row['dsp48'],
        }
    return checked


def fit_screen(counts: dict, cap: dict = CAPACITY) -> dict:
    out={}
    for d in DESIGNS:
        usage={}
        for k,limit in cap.items():
            v=counts[d][k]
            if not isinstance(limit,int) or limit<=0:
                raise ValueError('Invalid device capacity')
            usage[k]={'used':v,'available':limit,'percent':round(100*v/limit,3),'within':v<=limit}
        out[d]={'resources':usage,'screen_pass':all(x['within'] for x in usage.values())}
    return out


def validate_out_dir(path: Path, root: Path | None = None) -> Path:
    root = ROOT if root is None else root
    p=path.resolve()
    build=(root/'build').resolve()
    if not p.is_relative_to(build) or p == build:
        raise ValueError('Output must be a subdirectory of build/; committed evidence is immutable')
    return p


def analyze(input_file:Path, rtl_file:Path, out_dir:Path)->dict:
    output=validate_out_dir(out_dir)
    content=input_file.read_bytes()
    source=rtl_file.read_bytes()
    mapping=json.loads(content)
    source_digest = hashlib.sha256(source).hexdigest()
    source_match = verify_rtl_source(rtl_file, PINNED_RTL_SHA256)
    if mapping.get('source_sha256',{}).get('ascon_aead_encrypt_temporal.sv') not in (source_digest, PINNED_RTL_SHA256):
        raise ValueError('Phase 10D provenance disagrees with actual checked-in AEAD RTL')
    counts=validate_phase10d(mapping)
    io=parse_top_ports(source.decode('utf-8'))
    screen=fit_screen(counts)
    physical_io=io['input_bits']+io['output_bits']
    result={
       'phase':'10E', 'scope':'resource capacity screening of xc7 OOC mapped netlists; no Vivado timing, placement, routing or bitstream',
       'device':PART,'profile':CAPACITY,'package_max_user_io':PACKAGE_USER_IO,
       'source_urls':SOURCE_URLS, 'time_utc':datetime.now(timezone.utc).isoformat(),
       'source_sha256':{'phase10d_fpga_resources_json':hashlib.sha256(content).hexdigest(),
                        'rtl_aead_top':hashlib.sha256(source).hexdigest()},
       'mapping_tools': mapping.get('tools','not present in input'),
       'source_provenance':mapping.get('historical_rtl_verified'),
       'rtl_source_match':source_match,
       'designs':screen,
       'io':{'input_bits':io['input_bits'],'output_bits':io['output_bits'],'total_bits':physical_io,
             'package_max_user_io':PACKAGE_USER_IO,
             'direct_parallel_pin_interface_feasible':physical_io<=PACKAGE_USER_IO,
             'note':'Upper-bound package user I/O; fewer signals may be usable on the actual board. Requires a proper interface/wrapper.'},
       'conclusion':'Core passes a limited resource-capacity screen; package I/O direct connection exceeds limit' if all(x['screen_pass'] for x in screen.values()) and physical_io>PACKAGE_USER_IO else 'Inspect resource and I/O constraints; no physical implementation proven'
    }
    output.mkdir(parents=True,exist_ok=True)
    (output/'feasibility.json').write_text(json.dumps(result,indent=2)+'\n')
    report=[f'# Phase 10E — {PART} capacity screen','',
            '**NOT a place-and-route, clock-frequency, power or board I/O implementation result.**','',
            '| Variant | LUT used / available | LUT % | FF used / available | FF % | BRAM18 eq. | DSP48 | Resource screen |',
            '|---|---:|---:|---:|---:|---:|---:|---|']
    for d in DESIGNS:
        r=screen[d]['resources']; ok=screen[d]['screen_pass']
        report.append(f"| {d} | {r['lut_total']['used']:,} / {CAPACITY['lut_total']:,} | {r['lut_total']['percent']:.3f}% | {r['flip_flops']['used']:,} / {CAPACITY['flip_flops']:,} | {r['flip_flops']['percent']:.3f}% | {r['bram18_equivalents']['used']} | {r['dsp48']['used']} | {'PASS' if ok else 'EXCEEDS'} |")
    report +=['','## Parallel I/O limitation','',
              f"- Actual RTL interface: **{io['input_bits']} input bits + {io['output_bits']} output bits = {physical_io} bits**.",
              f'- Device CSG324 package ceiling: **{PACKAGE_USER_IO} user I/O** (not all of them accessible from board headers).',
              f"- Direct pin-to-pin top level: **{'within nominal I/O limit' if physical_io<=PACKAGE_USER_IO else 'not feasible'}**.",
              '- A serial/UART/SPI, memory-mapped or internally registered host wrapper is required for hardware demonstration.',
              '', '## Timing status','',
              '- No timing claims are made here. Optional Vivado OOC implementation script produces routed timing reports on a supported OS.',
              '- Even a passing OOC internal-clock constraint does not validate external interface timing or board deployment.',
              '', '## Provenance','',
              f"- Phase 10D input SHA-256: `{result['source_sha256']['phase10d_fpga_resources_json']}`",
              f"- Top-level RTL SHA-256: `{result['source_sha256']['rtl_aead_top']}`",
              f"- Target `xc7` source provenance verified: {mapping['historical_rtl_verified']}",
              '', '## Datasheet references','']
    for name,url in SOURCE_URLS.items(): report.append(f'- {name}: {url}')
    (output/'REPORT.md').write_text('\n'.join(report)+'\n')
    print('PASS: device resource-capacity screening; this is not placement or timing verification')
    for d in DESIGNS:
        rr=screen[d]['resources']; print(f"{d}: LUT {rr['lut_total']['used']}/{rr['lut_total']['available']} ({rr['lut_total']['percent']:.3f}%), FF {rr['flip_flops']['used']}/{rr['flip_flops']['available']} ({rr['flip_flops']['percent']:.3f}%)")
    print(f"Top-level I/O: {physical_io} bits vs {PACKAGE_USER_IO} maximum package user I/O: {'FAIL direct pin interface' if physical_io>PACKAGE_USER_IO else 'within max pin count only'}")
    print('Report:',output/'REPORT.md')
    return result


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fpga-json',type=Path,default=Path('build/reproduction/phase10d/fpga_resources.json'))
    parser.add_argument('--rtl',type=Path,default=ROOT/'rtl/ascon_aead_encrypt_temporal.sv')
    parser.add_argument('--out-dir',type=Path,default=ROOT/'build/reproduction/phase10e')
    args=parser.parse_args()
    analyze(args.fpga_json,args.rtl,args.out_dir)
if __name__=='__main__': main()
