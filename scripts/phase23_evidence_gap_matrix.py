"""Phase 23: read-only, fail-closed cross-phase evidence and unresolved-gap matrix.

Inputs are the *original* review ZIPs from Phases 15-22 and the accepted Phase 17
routed DCP. Output is a derived research inventory, never timing/board signoff.
This script does not invoke Vivado or modify any input.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import sys
import zipfile
from pathlib import Path

PHASE15_DCP = '869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199'
PHASE17_DCP = '633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340'
PHASE17_OVERLAY = '9f2b07df823b3fc1b4bf1c28a0cf4bc774e3a38f4a85e16b04acf4ab38149223'
DEFAULT_CHECKPOINT = ('build/reproduction/phase17/'
 'nexys4_ddr_rev_c_cfg_20261014T131338Z/post_route.dcp')
FILENAMES = {i: f'faultscope_phase{i}{"_review_reports" if i == 15 else "_review"}.zip'
             for i in range(15,23)}
VERDICTS = {
 15:'CANDIDATE_IMPLEMENTATION_REVIEW_REQUIRED',
 16:'EVIDENCE_COLLECTED_REVIEW_REQUIRED',
 17:'ROUTED_CFG_CANDIDATE_REVIEW_REQUIRED',
 18:'ASYNC_BOUNDARY_EVIDENCE_REVIEW_REQUIRED',
 19:'RESET_LINEAGE_EVIDENCE_REVIEW_REQUIRED',
 20:'PIN_LEVEL_EVIDENCE_REVIEW_REQUIRED',
 21:'RESET_TIMING_EVIDENCE_REVIEW_REQUIRED',
 22:'PATH_OBJECT_REPORTS_REVIEW_REQUIRED',
}
EXPECTED_PINS = {'clk':('IN','E3'),'rst_n':('IN','C12'),
 'uart_rx_i':('IN','C4'),'uart_tx_o':('OUT','D4'),
 'led_busy_o':('OUT','H17'),'led_alarm_o':('OUT','K15')}
MISSING_DELAYS = {'input:rst_n','input:uart_rx_i','output:uart_tx_o',
                  'output:led_busy_o','output:led_alarm_o'}
REQUIRED_MEMBERS = {
  15: {'source_context.tsv','internal_metrics.tsv','pin_assignment.tsv','synchronizer_cells.tsv','synchronizer_edges.tsv','post_route_drc.rpt','post_route_status.rpt','post_route_timing.rpt','post_route_utilization.rpt','check_timing.rpt','clocks.rpt','clock_networks.rpt','cdc.rpt'},
  16: {'gap_matrix.tsv','context.tsv','ports.tsv','drc.rpt','methodology.rpt','clock_interaction.rpt','clock_networks.rpt','timing_summary.rpt','check_timing.rpt','cdc.rpt'},
  17: {'source_context.tsv','internal_metrics.tsv','pin_assignment.tsv','synchronizer_cells.tsv','synchronizer_edges.tsv','post_route_drc.rpt','methodology.rpt','post_route_status.rpt','post_route_timing.rpt','post_route_utilization.rpt','check_timing.rpt','clocks.rpt','clock_networks.rpt','clock_interaction.rpt','cdc.rpt'},
  18: {'context.tsv','stages.tsv','interstage_timing.tsv','async_input.tsv','check_timing.rpt','rx_interstage_max.rpt','rx_interstage_min.rpt','methodology.rpt','cdc.rpt','simulation_result.txt','xvlog_console.log','xelab_console.log','xsim_console.log'},
  19: {'context.tsv','reset_input.tsv','controls.tsv','startpoints.tsv','control_drivers.tsv','comb_cone.tsv','release_fanout.tsv','check_timing.rpt','methodology.rpt'},
  20: {'context.tsv','pin_edges.tsv','lut_truth.tsv','preset_startpoints.tsv','check_timing.rpt','methodology.rpt'},
  21: {'context.tsv','path_observations.tsv','check_timing.rpt','timing_summary.rpt','methodology.rpt','clock_pulse_width.rpt','reset_from_port_max.rpt','reset_from_port_min.rpt','release_to_preset_max.rpt','release_to_preset_min.rpt'},
  22: {'context.tsv','ports.tsv','path_bindings.tsv','check_timing.rpt','methodology.rpt','timing_summary.rpt'} | {f'path_{group}{stage}_{delay}.rpt' for group,count in (('reset',3),('rx',2)) for stage in range(count) for delay in ('min','max')},
}
REPORT_FIELDS = ['phase','archive','archive_sha256','members','hashed_members',
                 'unhashed_members','manifest_verdict','integrity_class']
CLAIM_FIELDS = ['claim_id','class','evidence','qualified_statement','scope']
GAP_FIELDS = ['gap_id','status','dependency','scope','consequence']
MAX_TOTAL_UNCOMPRESSED = 10 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED = 3 * 1024 * 1024


def digest_bytes(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def demand(condition:bool, message:str):
    if not condition:
        raise ValueError(message)


def load_archive(path:Path, phase:int)->tuple[dict,dict[str,bytes],dict]:
    demand(path.is_file(), f'Missing Phase {phase} review ZIP: {path}')
    with zipfile.ZipFile(path) as z:
        infos=z.infolist()
        names=[f.filename for f in infos]
        demand(names and len(names)==len(set(names)),f'Phase {phase}: duplicate/empty member list')
        demand(set(names)==REQUIRED_MEMBERS[phase] | {'verification.json'},
           f'Phase {phase}: incomplete/unexpected archive member list')
        demand(all(not x.is_dir() and not x.filename.startswith(('/', '\\')) and
                   '\\' not in x.filename and len(Path(x.filename).parts)==1
                   for x in infos), f'Phase {phase}: unexpected member paths')
        demand(sum(x.file_size for x in infos)<=MAX_TOTAL_UNCOMPRESSED and
               all(x.file_size<=MAX_MEMBER_UNCOMPRESSED for x in infos),
               f'Phase {phase}: ZIP size bounds exceeded')
        demand(z.testzip() is None,f'Phase {phase}: ZIP CRC failure')
        files={n:z.read(n) for n in names}
    manifest=json.loads(files['verification.json'])
    demand(isinstance(manifest,dict),f'Phase {phase}: malformed manifest object')
    demand(manifest.get('phase')==str(phase),f'Phase {phase}: manifest phase mismatch')
    demand(manifest.get('verdict')==VERDICTS[phase],f'Phase {phase}: unexpected verdict')
    demand(manifest.get('issues',[])==[],f'Phase {phase}: unresolved evidence validation issues')
    demand(manifest.get('bitstream_generated') is False and manifest.get('board_programmed') is False,
           f'Phase {phase}: physical hardware activity assertion changed')
    demand(manifest.get('board_signoff',manifest.get('board_level_signoff'))=='NOT VERIFIED',
           f'Phase {phase}: unexpected board signoff assertion')
    hash_key='phase16_report_sha256' if phase==16 else 'report_sha256'
    hashes=manifest.get(hash_key, {})
    demand(isinstance(hashes,dict) and (bool(hashes) or phase==15),
           f'Phase {phase}: expected report hashes absent')
    demand(set(hashes).issubset(set(files)-{'verification.json'}),
           f'Phase {phase}: listed report absent from ZIP')
    for name,expected in hashes.items():
        demand(isinstance(expected,str) and re.fullmatch(r'[a-f0-9]{64}',expected) is not None,
               f'Phase {phase}: malformed hash for {name}')
        demand(digest_bytes(files[name])==expected,
               f'Phase {phase}: report digest mismatch: {name}')
    if phase>=19:
        demand(set(hashes)==set(files)-{'verification.json'},
               f'Phase {phase}: incomplete reported SHA-256 coverage')
    if phase>=16:
        demand(manifest.get('phase15_checkpoint_sha256')==PHASE15_DCP,
               f'Phase {phase}: Phase 15 checkpoint anchor mismatch')
    if phase>=17:
        demand(manifest.get('phase17_checkpoint_sha256')==PHASE17_DCP,
               f'Phase {phase}: Phase 17 checkpoint anchor mismatch')
    if phase in (18,19):
        field='phase17_overlay_original_sha256' if phase==18 else 'phase17_overlay_sha256'
        demand(manifest.get(field)==PHASE17_OVERLAY,
               f'Phase {phase}: overlay anchor mismatch')
    if phase==17:
        demand(manifest.get('overlay_sha256')==PHASE17_OVERLAY,
               'Phase 17 overlay anchor mismatch')
    if phase==15:
        demand(manifest.get('checkpoint_sha256')==PHASE15_DCP,
               'Phase 15 checkpoint anchor mismatch')
    unhashed=set(files)-{'verification.json'}-set(hashes)
    coverage='COMPLETE_RECORDED_HASHES' if not unhashed else 'PARTIAL_LEGACY_HASH_COVERAGE'
    record={'phase':str(phase),'archive':path.name,'archive_sha256':digest_file(path),
            'members':str(len(files)-1),'hashed_members':str(len(hashes)),
            'unhashed_members':str(len(unhashed)),
            'manifest_verdict':manifest['verdict'],'integrity_class':coverage}
    return manifest,files,record


def parse_tsv(raw:bytes, expected:list[str])->list[dict[str,str]]:
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')), delimiter='\t'))
    # Explicit fieldname inspection; reject values containing missing columns.
    header=next(csv.reader(io.StringIO(raw.decode('utf-8-sig')),delimiter='\t'),None)
    demand(header==expected, 'TSV columns mismatch: '+str(expected))
    demand(len(rows)>0 and all(set(r)==set(expected) and all(v is not None and v.strip() for v in r.values()) for r in rows),
           'TSV has missing or malformed rows')
    return rows


def finite_eq(left,right, tol:float=0.0001)->bool:
    try:
        a,b=float(left),float(right)
        return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tol
    except (ValueError,TypeError):
        return False


def validate_cross_phase(m:dict[int,dict],f:dict[int,dict[str,bytes]],checkpoint:Path):
    demand(checkpoint.is_file(),f'Missing Phase 17 routed checkpoint: {checkpoint}')
    demand(digest_file(checkpoint)==PHASE17_DCP,
           'Actual Phase 17 DCP digest differs from accepted anchor')
    demand(m[17]['phase15_original_xdc_sha256']==m[15]['xdc_sha256'],
           'Phase 15 XDC anchor disagreement')
    demand(m[16]['phase15_xdc_sha256']==m[15]['xdc_sha256'],
           'Phase 16 XDC anchor disagreement')
    for phase,key_s,key_h in [(15,'internal_setup_slack_ns','internal_hold_slack_ns'),
                              (17,'phase17_setup_slack_ns','phase17_hold_slack_ns'),
                              (18,'phase17_setup_slack_ns','phase17_hold_slack_ns')]:
        demand(finite_eq(m[phase][key_s],1.471) and finite_eq(m[phase][key_h],0.022),
               f'Phase {phase}: internal routed slack anchor differs')
    demand(m[17]['configuration_property_state']=='APPLIED_IN_ROUTED_CANDIDATE_NOT_BOARD_SIGNOFF',
           'Phase 17 configuration property qualification changed')
    demand(m[18]['stage_count']==5 and m[19]['control_count']==5,
           'Reset/UART stage topology differs')
    edges=parse_tsv(f[20]['pin_edges.tsv'],['edge','src_object','dst_object','src_direction',
        'dst_direction','src_segments','dst_segments','shared_segments','leaf_drivers',
        'driver_count','status'])
    expected_edges={'reset_port_to_ibuf','reset_ibuf_to_lut','release_q_to_lut',
                    'reset_lut_to_clr0','reset_lut_to_clr1','reset_lut_to_clr2',
                    'release_lut_to_pre0','release_lut_to_pre1'}
    demand(len(edges)==8 and {x['edge'] for x in edges}==expected_edges,
           'Phase 20 exact pin-edge inventory differs')
    for row in edges:
        expected='PORT_TO_IBUF_DIRECT' if row['edge']=='reset_port_to_ibuf' else 'SEGMENT_AND_SINGLE_EXPECTED_DRIVER'
        demand(row['status']==expected and row['driver_count']==('0' if row['edge']=='reset_port_to_ibuf' else '1'),
               'Phase 20 pin-level driver status changed: '+row['edge'])
    lut=parse_tsv(f[20]['lut_truth.tsv'],['role','cell','ref_name','init','i0_pin','o_pin','truth_status'])
    demand(len(lut)==2 and {r['role'] for r in lut}=={'reset','release'} and
           all(r['ref_name']=='LUT1' and r['init']=="2'h1" and r['truth_status']=='ONE_INPUT_INVERTER' for r in lut),
           'Phase 20 inverter truth evidence differs')
    demand(m[20]['physical_netlist_chain']=='CANDIDATE_ALL_EIGHT_LINKS_OBSERVED' and
           not m[20]['unresolved_edges'] and len(m[20]['pin_edge_status'])==8,
           'Phase 20 pin-level claim differs')
    demand(set(m[20]['lut_inverters_observed'])=={'reset','release'},
           'Phase 20 inverter observations differ')
    # Pin observations from the actual zipped reports, not only their summaries.
    port17=parse_tsv(f[17]['pin_assignment.tsv'],['port','direction','package_pin','iostandard'])
    port22=parse_tsv(f[22]['ports.tsv'],['port','direction','package_pin','iostandard'])
    for phase,ports in [(17,port17),(22,port22)]:
        demand(len(ports)==6 and set(p['port'] for p in ports)==set(EXPECTED_PINS),
               f'Phase {phase}: unexpected port collection')
        for p in ports:
            demand((p['direction'],p['package_pin'])==EXPECTED_PINS[p['port']] and p['iostandard']=='LVCMOS33',
                   f'Phase {phase}: port mapping differs for {p["port"]}')
    demand(m[22]['external_input_output_timing']=='NOT QUALIFIED' and
           set(m[22]['missing_io_delay_warnings'])==MISSING_DELAYS,
           'Phase 22: missing external delays must remain open')
    demand(m[21]['methodology_missing_external_delay_warnings']=='PRESENT',
           'Phase 21: missing delay methodology warnings absent')
    expected_keys={(g,str(s),d) for g,count in [('reset',3),('rx',2)]
                   for s in range(count) for d in ('min','max')}
    rows21=parse_tsv(f[21]['path_observations.tsv'],
        ['group','stage','source','sink','delay_type','query_state','path_count','slack_ns'])
    rows22=parse_tsv(f[22]['path_bindings.tsv'],
        ['group','stage','delay_type','requested_source','requested_sink','query_state','path_count',
         'slack_ns','report_file','report_state'])
    def keyed(rows):
        d={(r['group'],r['stage'],r['delay_type']):r for r in rows}
        demand(len(rows)==10 and set(d)==expected_keys,'Expected ten distinct path observations')
        return d
    a,b=keyed(rows21),keyed(rows22)
    for key in sorted(expected_keys):
        q,r=a[key],b[key]
        demand(q['source']==r['requested_source'] and q['sink']==r['requested_sink'] and
               q['query_state']==r['query_state'] and q['slack_ns']==r['slack_ns'] and
               q['path_count']==r['path_count']=='1',
               'Phase 21/22 path evidence disagrees: '+str(key))
        state='PATH_REPORTED_SLACK_UNAVAILABLE' if key[0]=='reset' else 'PATH_REPORTED'
        demand(q['query_state']==state and (q['slack_ns']=='-' if key[0]=='reset' else math.isfinite(float(q['slack_ns']))),
               'Phase 21/22 slack qualification changed: '+str(key))
        report_name=f'path_{key[0]}{key[1]}_{key[2]}.rpt'
        demand(r['report_file']==report_name and report_name in f[22],
               'Phase 22 individual report binding changed')
        report=f[22][report_name].decode('utf-8-sig',errors='replace')
        source=re.search(r'(?m)^\s*Source:\s*(\S+)',report)
        target=re.search(r'(?m)^\s*Destination:\s*(\S+)',report)
        path_type=re.search(r'(?m)^\s*Path Type:\s*(\w+)',report)
        slack=re.search(r'(?m)^\s*Slack(?:\s*\([^)]*\))?\s*:\s*([+-]?(?:inf|nan|[0-9]+(?:\.[0-9]+)?))',report,re.I)
        demand('report_timing -of_objects' in report and source and target and path_type and slack,
               'Phase 22 report body missing path-object identification')
        demand(target.group(1)==r['requested_sink'] and
               path_type.group(1).lower()==('recovery' if key[2]=='max' else 'removal'),
               'Phase 22 report destination/type changed')
        expected_source='rst_n' if key[0]=='reset' else 'u_reset_sync/release_pipe_q_reg[2]/C'
        demand(source.group(1)==expected_source,
               'Phase 22 actual timing-source labeling changed')
        if key[0]=='reset':
            demand(slack.group(1).lower()=='inf', 'Phase 22 external reset is not finite-slack qualified')
        else:
            demand(finite_eq(slack.group(1),r['slack_ns'],0.002),
                   'Phase 22 individual report slack changed')
        demand(r['report_state']=='REPORT_WRITTEN', 'Missing individual rendered report')
    demand(m[21]['timing_paths_found']==10 and m[21]['timing_paths_with_numeric_slack']==4 and
           m[21]['timing_paths_without_numeric_slack']==6 and m[21]['timing_paths_not_reported']==0,
           'Phase 21 summary count mismatch')
    demand(m[22]['paths_with_rendered_reports']==10 and len(m[22]['timing_startpoint_mismatches'])==4,
           'Phase 22 path rendering summary mismatch')
    demand(m[21]['reset_recovery_removal']=='NOT VERIFIED' and
           m[22]['external_reset_minimum_pulse_width']=='NOT VERIFIED' and
           m[22]['physical_board_revision']=='NOT CONFIRMED',
           'Reset/board limitation not preserved')


def claims():
    return [
      ['P23-C01','ROUTED_CANDIDATE','P15,P17 DCP+manifest',
       'Accepted Phase 17 DCP has fixed SHA-256; setup +1.471 ns, hold +0.022 ns under modeled clocks','MODEL_ONLY'],
      ['P23-C02','CONFIGURATION','P17 context/verification',
       'CFGBVS=VCCO and CONFIG_VOLTAGE=3.3 applied in routed candidate','MODEL_ONLY'],
      ['P23-C03','BOARD_PORTS','P17 pin_assignment.tsv; P22 ports.tsv',
       'Six implemented pin assignments agree across the routed evidence','PROVISIONAL_BOARD'],
      ['P23-C04','RESET_NETLIST','P19 controls; P20 pin_edges.tsv; lut_truth.tsv',
       'Eight expected pin-level links and two LUT1 inverters observed','ROUTED_NETLIST_ONLY'],
      ['P23-C05','RESET_TIMING','P21 path_observations.tsv; P22 path_bindings.tsv',
       'Ten matched path queries: six external reset with unavailable slack, four internal UART PRE with finite modeled slack','MODEL_ONLY'],
      ['P23-C06','TIMING_SOURCE','P22 individual timing reports',
       'Four UART path reports show /C as timing source; distinct from /Q as physical net driver','MODEL_ONLY'],
      ['P23-C07','CONSTRAINT_COVERAGE','P21 methodology.rpt; P22 verification.json',
       'Five external input/output delay warnings remain; no external timing budgets qualified','OPEN'],
      ['P23-C08','ARCHIVE_INTEGRITY','P15-P22 ZIPs, recorded report SHA-256 values',
       'Hashes match every report with a recorded hash; older phases have incomplete member-hash coverage','PARTIAL_LEGACY'],
    ]


def gaps():
    return [
      ['G23-01','OPEN','Physical Nexys4 DDR Rev C identification','HARDWARE','Board revision and as-built oscillator/electrical assumptions unconfirmed'],
      ['G23-02','OPEN','External rst_n arrival/release relationship, pulse width and bounce measurements','HARDWARE','Physical reset recovery/removal, minimum pulse and button behavior not signed off'],
      ['G23-03','OPEN','External UART RX input transition/MTBF analysis based on device/clock conditions','HARDWARE+MODEL','Analog synchronizer MTBF not established'],
      ['G23-04','OPEN','USB-UART bridge output/input timing and actual interface characterization','HARDWARE+DOCS','uart_rx_i / uart_tx_o external delay assumptions unqualified'],
      ['G23-05','OPEN','LED external loads and applicable output timing model','HARDWARE+DOCS','led_busy_o / led_alarm_o timing unqualified'],
      ['G23-06','OPEN','Oscillator startup/jitter characterization and clock/reset interactions','HARDWARE','Physical clock/reset startup not verified'],
      ['G23-07','OPEN','Physical bitstream generation/programming and board functional tests','HARDWARE','Not performed; no hardware signoff'],
      ['G23-08','OPEN','Five missing I/O timing constraints (TIMING-18)','MODEL+DOCS','Unconstrained external timing remains; do not fabricate delays or blanket exceptions'],
      ['G23-09','LIMITATION','Older Phase 15-18 archives lack hashes for some bundle members','EVIDENCE','Legacy evidence integrity coverage must not be overstated'],
    ]


def as_tsv(columns, rows):
    output=io.StringIO(newline='')
    writer=csv.writer(output,delimiter='\t',lineterminator='\n')
    writer.writerow(columns)
    writer.writerows(rows)
    return output.getvalue().encode('utf-8')


def build(inputs:Path,checkpoint:Path)->tuple[dict,dict[str,bytes]]:
    manifests,files,sources={},{},[]
    for phase in range(15,23):
        manifest,parts,source=load_archive(inputs/FILENAMES[phase],phase)
        manifests[phase]=manifest
        files[phase]=parts
        sources.append([source[k] for k in REPORT_FIELDS])
    validate_cross_phase(manifests,files,checkpoint)
    cc,gg=claims(),gaps()
    results={
       'phase':'23',
       'verdict':'EVIDENCE_MATRIX_REVIEW_REQUIRED',
       'scope':'offline, read-only Phase 15-22 research evidence consistency and gap inventory',
       'accepted_phase15_dcp_sha256':PHASE15_DCP,
       'accepted_phase17_dcp_sha256':PHASE17_DCP,
       'phase17_checkpoint_actual_sha256':digest_file(checkpoint),
       'phase17_checkpoint_file':checkpoint.name,
       'phases_consistent':list(range(15,23)),
       'review_archives':8,
       'claims_recorded':len(cc),
       'open_gaps':sum(x[1]=='OPEN' for x in gg),
       'evidence_limitations':sum(x[1]=='LIMITATION' for x in gg),
       'partially_hashed_legacy_phases':[i for i, row in zip(range(15,23),sources) if row[-1]=='PARTIAL_LEGACY_HASH_COVERAGE'],
       'reset_timing':'SIX_UNQUALIFIED_EXTERNAL_FOUR_MODELED_INTERNAL',
       'external_io_missing_delay_count':5,
       'board_revision':'PROVISIONAL_NOT_CONFIRMED',
       'board_signoff':'NOT VERIFIED',
       'physical_reset':'NOT VERIFIED',
       'external_timing':'NOT QUALIFIED',
       'uart_mtbf':'NOT VERIFIED',
       'bitstream_generated':False,
       'board_programmed':False,
       'rtl_xdc_dcp_modified':False,
    }
    output={'evidence_sources.tsv':as_tsv(REPORT_FIELDS,sources),
            'qualified_claims.tsv':as_tsv(CLAIM_FIELDS,cc),
            'open_gaps.tsv':as_tsv(GAP_FIELDS,gg)}
    lines=['# Phase 23 — evidence qualification dossier','',
           '**Verdict: EVIDENCE_MATRIX_REVIEW_REQUIRED. Research evidence only; no physical board signoff.**','',
           'This dossier checks that the archived Phase 15–22 manifests, available recorded report hashes,',
           'cross-phase paths, pin mappings and the actual Phase 17 checkpoint agree. ZIP SHA-256 values',
           'identify the local archive bytes; they are not an independent signature or proof of origin.','',
           '## Qualified claims','',
           '| ID | Evidence class | Bounded finding |','|---|---|---|']
    lines += [f'| {x[0]} | {x[1]} | {x[3]} |' for x in cc]
    lines += ['','## Open dependencies','', '| ID | Status | Requirement |','|---|---|---|']
    lines += [f'| {x[0]} | {x[1]} | {x[2]} |' for x in gg]
    lines += ['','## Strict acceptance boundary','',
              'Evidence collection does **not** imply safe physical reset recovery/removal, valid external I/O timing,',
              'actual UART metastability MTBF, confirmed board revision, verified oscillator startup, or board operation.',
              'The five TIMING-18 missing-delay warnings remain open. Do not introduce fabricated timing numbers,',
              'blanket false-path exceptions, placement/routing changes, or a bitstream to close documentation gaps.',
              '', 'The final Phase 24 release may package qualified evidence while retaining these explicit limitations.','']
    output['dossier.md']='\n'.join(lines).encode('utf-8')
    results['output_sha256']={name:digest_bytes(data) for name,data in sorted(output.items())}
    output['verification.json']=(json.dumps(results,indent=2,sort_keys=True)+'\n').encode('utf-8')
    return results,output


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir',required=True,type=Path,help='Directory containing Phase 15-22 review ZIPs')
    parser.add_argument('--checkpoint',type=Path,default=Path(DEFAULT_CHECKPOINT))
    parser.add_argument('--out',type=Path,help='New output directory, never overwritten')
    parser.add_argument('--preflight-only',action='store_true')
    args=parser.parse_args(argv)
    if not args.preflight_only and args.out is None:
        parser.error('--out is required unless --preflight-only is supplied')
    try:
        if args.out is not None:
            demand(not args.out.exists(),'Refusing overwrite of Phase 23 output: '+str(args.out))
        result,output=build(args.input_dir,args.checkpoint)
        if args.preflight_only:
            print(json.dumps({'phase':'23','verdict':'PHASE23_INPUT_EVIDENCE_VERIFIED',
                              'review_archives':result['review_archives'],
                              'open_gaps':result['open_gaps'],
                              'board_signoff':'NOT VERIFIED'},indent=2))
        else:
            args.out.mkdir(parents=True,exist_ok=False)
            for name,data in output.items():
                (args.out/name).write_bytes(data)
            print(json.dumps(result,indent=2,sort_keys=True))
        return 0
    except (OSError,ValueError,KeyError,zipfile.BadZipFile,UnicodeError,TypeError) as e:
        print(json.dumps({'phase':'23','verdict':'NOT_VERIFIED','issues':[str(e)],
                          'board_signoff':'NOT VERIFIED'},indent=2),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
