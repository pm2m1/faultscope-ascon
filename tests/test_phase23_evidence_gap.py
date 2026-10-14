"""Self-contained Phase 23 negative controls; no Vivado or real FPGA checkpoint needed."""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import warnings
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('phase23_evidence_gap_matrix',ROOT/'scripts/phase23_evidence_gap_matrix.py')
p23=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=p23
SPEC.loader.exec_module(p23)
P15_XDC='69bddc36a6142b41c47e4335bd3cb56e1051fe0cf52a33491fdcfd2338ffa4d8'


def tsv(columns,rows):
    out=io.StringIO();w=csv.writer(out,delimiter='\t',lineterminator='\n')
    w.writerow(columns);w.writerows(rows)
    return out.getvalue().encode()


def fixture_archives(root):
    base={'bitstream_generated':False,'board_programmed':False,
          'board_signoff':'NOT VERIFIED','issues':[]}
    port_columns=['port','direction','package_pin','iostandard']
    port_rows=[[name,kind,pin,'LVCMOS33'] for name,(kind,pin) in p23.EXPECTED_PINS.items()]
    rows20=[]
    for edge in ['reset_port_to_ibuf','reset_ibuf_to_lut','reset_lut_to_clr0',
                 'reset_lut_to_clr1','reset_lut_to_clr2','release_q_to_lut',
                 'release_lut_to_pre0','release_lut_to_pre1']:
        rows20.append([edge,'src','dst','OUT','IN','segment','segment','segment','driver',
                    '0' if edge=='reset_port_to_ibuf' else '1',
                    'PORT_TO_IBUF_DIRECT' if edge=='reset_port_to_ibuf' else 'SEGMENT_AND_SINGLE_EXPECTED_DRIVER'])
    obs21=[];obs22=[];reports={}
    for g,n in [('reset',3),('rx',2)]:
        for stage in range(n):
            src='rst_n' if g=='reset' else 'u_reset_sync/release_pipe_q_reg[2]/Q'
            sink=f'u_reset_sync/release_pipe_q_reg[{stage}]/CLR' if g=='reset' else f'receiver/sync_q_reg[{stage}]/PRE'
            for delay in ['max','min']:
                slack='-' if g=='reset' else ('4.283' if delay=='max' else '2.075')
                state='PATH_REPORTED_SLACK_UNAVAILABLE' if g=='reset' else 'PATH_REPORTED'
                reportname=f'path_{g}{stage}_{delay}.rpt'
                obs21.append([g,str(stage),src,sink,delay,state,'1',slack])
                obs22.append([g,str(stage),delay,src,sink,state,'1',slack,reportname,'REPORT_WRITTEN'])
                source_display='rst_n' if g=='reset' else 'u_reset_sync/release_pipe_q_reg[2]/C'
                path_type='Recovery' if delay=='max' else 'Removal'
                shown='inf' if g=='reset' else slack
                reports[reportname]=('| Command : report_timing -of_objects ...\n'+
                    f'Source: {source_display}\nDestination: {sink}\nPath Type: {path_type}\n'+
                    f'Slack (MET) : {shown}ns\n').encode()
    data_by_phase={}
    for i in range(15,23):
        m=dict(base, phase=str(i),verdict=p23.VERDICTS[i])
        files={name:b'SYNTHETIC_FIXTURE_REPORT\n' for name in p23.REQUIRED_MEMBERS[i]}
        if i>=16: m['phase15_checkpoint_sha256']=p23.PHASE15_DCP
        if i>=17: m['phase17_checkpoint_sha256']=p23.PHASE17_DCP
        if i==15:
            m.update(checkpoint_sha256=p23.PHASE15_DCP,xdc_sha256=P15_XDC,
                     internal_setup_slack_ns=1.471,internal_hold_slack_ns=0.022)
        if i==16:
            m['phase15_xdc_sha256']=P15_XDC
        if i==17:
            m.update(phase15_original_xdc_sha256=P15_XDC,
                     overlay_sha256=p23.PHASE17_OVERLAY,
                     phase17_setup_slack_ns=1.471,phase17_hold_slack_ns=0.022,
                     configuration_property_state='APPLIED_IN_ROUTED_CANDIDATE_NOT_BOARD_SIGNOFF')
            files['pin_assignment.tsv']=tsv(port_columns,port_rows)
        if i==18:
            m.update(phase17_overlay_original_sha256=p23.PHASE17_OVERLAY,
                     phase17_setup_slack_ns=1.471,phase17_hold_slack_ns=0.022,stage_count=5)
        if i==19:
            m.update(phase17_overlay_sha256=p23.PHASE17_OVERLAY,control_count=5)
        if i==20:
            m.update(physical_netlist_chain='CANDIDATE_ALL_EIGHT_LINKS_OBSERVED',
                     unresolved_edges=[],pin_edge_status={r[0]:r[-1] for r in rows20},
                     lut_inverters_observed=['reset','release'])
            files['pin_edges.tsv']=tsv(['edge','src_object','dst_object','src_direction',
                'dst_direction','src_segments','dst_segments','shared_segments','leaf_drivers',
                'driver_count','status'],rows20)
            files['lut_truth.tsv']=tsv(['role','cell','ref_name','init','i0_pin','o_pin','truth_status'],
                [[name,'cell','LUT1',"2'h1",'cell/I0','cell/O','ONE_INPUT_INVERTER'] for name in ('reset','release')])
        if i==21:
            m.update(methodology_missing_external_delay_warnings='PRESENT',
                reset_recovery_removal='NOT VERIFIED',timing_paths_found=10,
                timing_paths_with_numeric_slack=4,timing_paths_without_numeric_slack=6,
                timing_paths_not_reported=0)
            files['path_observations.tsv']=tsv(['group','stage','source','sink','delay_type','query_state',
                                                'path_count','slack_ns'],obs21)
        if i==22:
            m.update(external_input_output_timing='NOT QUALIFIED',
                     missing_io_delay_warnings=sorted(p23.MISSING_DELAYS),
                     paths_with_rendered_reports=10,
                     timing_startpoint_mismatches=['path_rx0_max.rpt','path_rx0_min.rpt',
                                                   'path_rx1_max.rpt','path_rx1_min.rpt'],
                     external_reset_minimum_pulse_width='NOT VERIFIED',
                     physical_board_revision='NOT CONFIRMED')
            files['ports.tsv']=tsv(port_columns,port_rows)
            files['path_bindings.tsv']=tsv(['group','stage','delay_type','requested_source',
                'requested_sink','query_state','path_count','slack_ns','report_file','report_state'],obs22)
            files.update(reports)
        if i>=16:
            field='phase16_report_sha256' if i==16 else 'report_sha256'
            # Match the historical partial legacy hash coverage, without embedding user reports.
            hashes={k:hashlib.sha256(v).hexdigest() for k,v in files.items()
                    if i>=19 or k.endswith('.rpt')}
            m[field]=hashes
        files['verification.json']=(json.dumps(m,sort_keys=True)+'\n').encode()
        data_by_phase[i]=files
    for phase,files in data_by_phase.items():
        write_archive(root,phase,files)
    return data_by_phase


def write_archive(root,phase,files):
    with zipfile.ZipFile(root/p23.FILENAMES[phase],'w',zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):z.writestr(name,files[name])


@pytest.fixture
def evidence(tmp_path,monkeypatch):
    fixture_archives(tmp_path)
    checkpoint=tmp_path/'post_route.dcp';checkpoint.write_bytes(b'FAKE_DCP_UNTRUSTED_UNIT_TEST_ONLY')
    actual=p23.digest_file
    monkeypatch.setattr(p23,'digest_file',lambda path:
      p23.PHASE17_DCP if Path(path)==checkpoint else actual(Path(path)))
    return tmp_path,checkpoint


def check(root,checkpoint):
    return p23.build(root,checkpoint)


def rewrite(root,phase,fn):
    path=root/p23.FILENAMES[phase]
    with zipfile.ZipFile(path) as z:
        files={k:z.read(k) for k in z.namelist()}
    fn(files)
    write_archive(root,phase,files)


def change_manifest(files,field,value):
    m=json.loads(files['verification.json'])
    m[field]=value
    files['verification.json']=json.dumps(m).encode()


def mutate_text(files,name,old,new,rehash=False,phase=22):
    b=files[name]
    assert old.encode() in b
    files[name]=b.replace(old.encode(),new.encode(),1)
    if rehash:
        m=json.loads(files['verification.json'])
        key='phase16_report_sha256' if phase==16 else 'report_sha256'
        m[key][name]=hashlib.sha256(files[name]).hexdigest()
        files['verification.json']=json.dumps(m).encode()


def test_complete_offline_dossier_preserves_open_gaps(evidence):
    result,files=check(*evidence)
    assert result['verdict']=='EVIDENCE_MATRIX_REVIEW_REQUIRED'
    assert result['review_archives']==8
    assert result['open_gaps']==8
    assert result['external_io_missing_delay_count']==5
    assert result['partially_hashed_legacy_phases']==[15,16,17,18]
    assert result['board_signoff']=='NOT VERIFIED'
    assert len(files)==5
    assert all(hashlib.sha256(files[k]).hexdigest()==v for k,v in result['output_sha256'].items())
    assert b'NOT VERIFIED' in files['dossier.md'] or b'no physical board signoff' in files['dossier.md']


def test_preflight_does_not_write(evidence,capsys):
    root,checkpoint=evidence
    rc=p23.main(['--input-dir',str(root),'--checkpoint',str(checkpoint),'--preflight-only'])
    assert rc==0
    assert 'PHASE23_INPUT_EVIDENCE_VERIFIED' in capsys.readouterr().out
    assert not list(root.glob('evidence_gap_*'))


def test_output_refuses_existing_folder(evidence):
    root,checkpoint=evidence
    out=root/'existing';out.mkdir()
    assert p23.main(['--input-dir',str(root),'--checkpoint',str(checkpoint),'--out',str(out)])==2
    assert list(out.iterdir())==[]


def test_new_output_contains_only_derived_reports(evidence):
    root,checkpoint=evidence
    out=root/'new_inventory'
    assert p23.main(['--input-dir',str(root),'--checkpoint',str(checkpoint),'--out',str(out)])==0
    assert {p.name for p in out.iterdir()}=={'evidence_sources.tsv','qualified_claims.tsv','open_gaps.tsv',
                                               'dossier.md','verification.json'}


def test_missing_zip_fails_closed(evidence):
    root,checkpoint=evidence
    (root/p23.FILENAMES[20]).unlink()
    with pytest.raises(ValueError,match='Missing Phase 20'):check(root,checkpoint)


def test_corrupt_zip_rejected(evidence):
    root,checkpoint=evidence
    (root/p23.FILENAMES[22]).write_bytes(b'not_zip')
    with pytest.raises(zipfile.BadZipFile):check(root,checkpoint)


@pytest.mark.parametrize('phase,field,bad',[
    (15,'checkpoint_sha256','bad'),(16,'phase15_checkpoint_sha256','bad'),
    (17,'phase17_checkpoint_sha256','bad'),(18,'phase17_overlay_original_sha256','bad'),
    (19,'phase17_overlay_sha256','bad'),(20,'physical_netlist_chain','WRONG'),
    (21,'timing_paths_found',9),(22,'external_input_output_timing','QUALIFIED'),
    (22,'missing_io_delay_warnings',[]),(22,'board_signoff','VERIFIED'),
    (21,'reset_recovery_removal','VERIFIED'),(22,'physical_board_revision','CONFIRMED'),
    (22,'bitstream_generated',True),
])
def test_changed_manifest_claim_rejected(evidence,phase,field,bad):
    root,checkpoint=evidence
    rewrite(root,phase,lambda files:change_manifest(files,field,bad))
    with pytest.raises(ValueError):check(root,checkpoint)


def test_actual_checkpoint_digest_gate(evidence,monkeypatch):
    root,checkpoint=evidence
    monkeypatch.setattr(p23,'digest_file',lambda path: '1'*64 if Path(path)==checkpoint else '2'*64)
    with pytest.raises(ValueError,match='Actual Phase 17 DCP digest'):check(root,checkpoint)


def test_sha_tampering_report_rejected(evidence):
    root,checkpoint=evidence
    rewrite(root,22,lambda fs:mutate_text(fs,'ports.tsv','E3','E4'))
    with pytest.raises(ValueError,match='report digest mismatch'):check(root,checkpoint)


def test_pin_tampering_even_with_rehashed_manifest_fails(evidence):
    root,checkpoint=evidence
    rewrite(root,22,lambda fs:mutate_text(fs,'ports.tsv','E3','E4',True))
    with pytest.raises(ValueError,match='port mapping differs'):check(root,checkpoint)


def test_missing_legacy_member_even_without_hash_rejected(evidence):
    root,checkpoint=evidence
    rewrite(root,15,lambda fs:fs.pop('cdc.rpt'))
    with pytest.raises(ValueError,match='archive member list'):check(root,checkpoint)


def test_timing_slack_changed_even_with_rehashed_manifest(evidence):
    root,checkpoint=evidence
    rewrite(root,22,lambda fs:mutate_text(fs,'path_bindings.tsv','4.283','3.000',True))
    with pytest.raises(ValueError,match='path evidence disagrees'):check(root,checkpoint)


def test_timing_report_body_changed_even_with_rehashed_manifest(evidence):
    root,checkpoint=evidence
    rewrite(root,22,lambda fs:mutate_text(fs,'path_rx0_max.rpt','Source: u_reset_sync/release_pipe_q_reg[2]/C',
                                         'Source: totally_unrelated/C',True))
    with pytest.raises(ValueError,match='timing-source labeling changed'):check(root,checkpoint)


def test_false_external_reset_slack_rejected(evidence):
    root,checkpoint=evidence
    rewrite(root,21,lambda fs:mutate_text(fs,'path_observations.tsv',
          'PATH_REPORTED_SLACK_UNAVAILABLE\t1\t-','PATH_REPORTED\t1\t0.010',True,21))
    with pytest.raises(ValueError):check(root,checkpoint)


def test_unknown_archive_member_rejected(evidence):
    root,checkpoint=evidence
    rewrite(root,21,lambda fs:fs.update({'surprise.bin':b'unknown'}))
    with pytest.raises(ValueError,match='archive member list'):check(root,checkpoint)


def test_traversal_entry_rejected(evidence):
    root,checkpoint=evidence
    rewrite(root,21,lambda fs:fs.update({'../escape.txt':b'bad'}))
    with pytest.raises(ValueError,match='archive member list'):check(root,checkpoint)


def test_no_implementation_mutation_or_vivado_calls():
    code=(ROOT/'scripts/phase23_evidence_gap_matrix.py').read_text()
    runner=(ROOT/'scripts/phase23_evidence_gap_matrix.ps1').read_text()
    for forbidden in ('-mode batch','vivado.bat','route_design','write_bitstream','set_false_path',
                      'set_input_delay','set_output_delay','set_property','write_checkpoint'):
        assert forbidden not in runner
    assert 'subprocess.run' not in code and 'os.system' not in code
    assert '--preflight-only' in runner and '--out' in runner and 'Refusing overwrite' in runner


def test_deterministic_report_content(evidence):
    root,checkpoint=evidence
    a,fa=check(root,checkpoint)
    b,fb=check(root,checkpoint)
    assert fa==fb and a['output_sha256']==b['output_sha256']
