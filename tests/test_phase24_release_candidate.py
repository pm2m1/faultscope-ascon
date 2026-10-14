"""Phase 24 negative controls. Synthetic inputs are NOT research evidence."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('phase24_release_candidate', ROOT/'scripts/phase24_release_candidate.py')
p24 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p24
SPEC.loader.exec_module(p24)


def tsv(cols, rows):
    buffer = io.StringIO(); writer = csv.writer(buffer, delimiter='\t', lineterminator='\n')
    writer.writerow(cols); writer.writerows(rows)
    return buffer.getvalue().encode()


def run_git(repo, *args):
    p = subprocess.run(['git', '-C', str(repo), *args], check=True, capture_output=True)
    return p.stdout.decode().strip()


@pytest.fixture
def fake_repo(tmp_path):
    repo = tmp_path / 'repo'; repo.mkdir()
    run_git(repo, 'init', '-q')
    run_git(repo, 'config', 'user.email', 'test@example.invalid')
    run_git(repo, 'config', 'user.name', 'Test Fixture')
    required = [
        'rtl/faultscope_uart_top.sv', 'rtl/fs_reset_sync.sv',
        'constraints/phase15_nexys4_ddr_rev_c.xdc',
        'constraints/phase17_cfg_rev_c_overlay.xdc',
        'docs/ascon_reference_commit.txt', 'uv.lock', 'frontend/package-lock.json',
        '.github/workflows/verify.yml', '.github/workflows/sequential-formal.yml',
        'scripts/phase23_evidence_gap_matrix.py',
    ]
    for name in required:
        path = repo / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(p24.ASCON_C_SHA + '\n' if name.endswith('ascon_reference_commit.txt') else f'synthetic fixture for {name}\n')
    run_git(repo, 'add', '.')
    run_git(repo, 'commit', '-qm', 'FAKE baseline fixture')
    return repo, run_git(repo, 'rev-parse', 'HEAD')


@pytest.fixture
def fabricated_phase23(tmp_path, monkeypatch):
    """Fixture tests the release wrapper; it never masquerades as a real DCP."""
    root = tmp_path / 'archive_dir'; root.mkdir()
    for i in range(15,23):
        name = 'faultscope_phase15_review_reports.zip' if i == 15 else f'faultscope_phase{i}_review.zip'
        (root / name).write_bytes(f'UNTRUSTED-SYNTHETIC-ZIP-{i}'.encode())
    result = {
        'verdict': 'EVIDENCE_MATRIX_REVIEW_REQUIRED',
        'claims_recorded': 8, 'open_gaps': 8, 'evidence_limitations': 1,
        'external_io_missing_delay_count': 5,
        'phase17_checkpoint_actual_sha256': p24.sha256_bytes(b'FAKE-DCP'),
        'board_signoff': 'NOT VERIFIED',
        'board_revision': 'PROVISIONAL_NOT_CONFIRMED',
        'bitstream_generated': False, 'board_programmed': False,
    }
    sources = [[str(i),
        'faultscope_phase15_review_reports.zip' if i == 15 else f'faultscope_phase{i}_review.zip',
        p24.sha256_file(root / ('faultscope_phase15_review_reports.zip' if i == 15 else f'faultscope_phase{i}_review.zip')),
        'PARTIAL_LEGACY_HASH_COVERAGE' if i<=18 else 'COMPLETE_RECORDED_HASHES']
        for i in range(15,23)]
    output = {
        'evidence_sources.tsv': tsv(['phase','archive','archive_sha256','members','hashed_members',
                                     'unhashed_members','manifest_verdict','integrity_class'],
                                    [[x[0],x[1],x[2],'1','1','0','SYNTHETIC',x[3]] for x in sources]),
        'qualified_claims.tsv': b'fake synthetic claims\n',
        'open_gaps.tsv': b'fake synthetic gaps\n',
        'dossier.md': b'fake synthetic dossier\n',
    }
    result['output_sha256'] = {k:p24.sha256_bytes(v) for k,v in output.items()}
    output['verification.json'] = (json.dumps(result,sort_keys=True)+'\n').encode()
    with zipfile.ZipFile(root / p24.PHASE23_ZIP, 'w') as z:
        for k,v in output.items():z.writestr(k,v)
    checkpoint = root / 'fake_post_route.dcp'; checkpoint.write_bytes(b'FAKE-DCP')
    monkeypatch.setattr(p24, 'load_phase23_module',
        lambda repo: SimpleNamespace(build=lambda archives, dcp: (result, output)))
    return root, checkpoint, result, output


def test_phase23_review_byte_identical(fabricated_phase23, tmp_path):
    root, cp, result, original = fabricated_phase23
    verified, digest, read = p24.validate_phase23(tmp_path,root,cp)
    assert verified==result and digest==p24.sha256_file(root/p24.PHASE23_ZIP)
    assert original==read


@pytest.mark.parametrize('target', [
    'verification.json', 'evidence_sources.tsv','qualified_claims.tsv','open_gaps.tsv','dossier.md'
])
def test_phase23_rebuilt_byte_mismatch_rejected(fabricated_phase23, monkeypatch, target):
    root, cp, result, original = fabricated_phase23
    changed = dict(original)
    changed[target] = b'TAMPERED, still syntactically valid'
    monkeypatch.setattr(p24, 'load_phase23_module',
        lambda repo: SimpleNamespace(build=lambda a,c: (result, changed)))
    with pytest.raises(ValueError,match='byte-reproducible'):
        p24.validate_phase23(root,root,cp)


def rewrite_zip(path, mutate):
    with zipfile.ZipFile(path) as z: items={i.filename:z.read(i) for i in z.infolist()}
    mutate(items)
    with zipfile.ZipFile(path,'w') as z:
        for k,v in items.items():z.writestr(k,v)


def test_missing_phase23_zip_rejected(fabricated_phase23):
    root,cp,_,_=fabricated_phase23
    (root/p24.PHASE23_ZIP).unlink()
    with pytest.raises(ValueError,match='Missing Phase 23'):
        p24.validate_phase23(root,root,cp)


def test_unexpected_zip_member_rejected(fabricated_phase23):
    root, cp, _,_ = fabricated_phase23
    rewrite_zip(root/p24.PHASE23_ZIP,lambda f:f.update({'../escape':b'BAD'}))
    with pytest.raises(ValueError,match='unexpected/duplicate'):
        p24.validate_phase23(root,root,cp)


def test_bad_phase23_recorded_digest_rejected(fabricated_phase23):
    root,cp,_,_=fabricated_phase23
    def mutate(f):
        m=json.loads(f['verification.json'])
        m['output_sha256']['open_gaps.tsv']='0'*64
        f['verification.json']=json.dumps(m).encode()
    rewrite_zip(root/p24.PHASE23_ZIP,mutate)
    with pytest.raises(ValueError,match='byte-reproducible|SHA mismatch'):
        p24.validate_phase23(root,root,cp)


@pytest.mark.parametrize('field,bad', [
    ('claims_recorded',7),('open_gaps',0),('evidence_limitations',0),
    ('external_io_missing_delay_count',0),('board_signoff','VERIFIED'),
    ('board_revision','CONFIRMED'),('bitstream_generated',True),('board_programmed',True),
])
def test_false_qualification_rejected(fabricated_phase23, monkeypatch, field, bad):
    root,cp,result,output=fabricated_phase23
    new_result=dict(result);new_result[field]=bad
    new_output=dict(output);new_output['verification.json']=(json.dumps(new_result,sort_keys=True)+'\n').encode()
    with zipfile.ZipFile(root/p24.PHASE23_ZIP,'w') as z:
        for k,v in new_output.items():z.writestr(k,v)
    monkeypatch.setattr(p24,'load_phase23_module',
        lambda repo: SimpleNamespace(build=lambda a,b: (new_result,new_output)))
    with pytest.raises(ValueError,match='unexpectedly changed|Unsupported'):
        p24.validate_phase23(root,root,cp)


def test_git_inventory_and_source_digests(fake_repo):
    repo, sha=fake_repo
    head,rows=p24.git_source_snapshot(repo,sha)
    assert head==sha and len(rows)==10
    for name, blob, sha256,size in rows:
        assert len(blob)==40 and len(sha256)==64
        assert sha256==p24.sha256_bytes(p24.git(repo,'show','HEAD:'+name))
        assert int(size)>0


def test_wrong_git_base_rejected(fake_repo):
    repo,_=fake_repo
    with pytest.raises(ValueError,match='Git provenance query failed'):
        p24.git_source_snapshot(repo, 'f'*40)


def test_dirty_historical_rtl_rejected(fake_repo):
    repo,sha=fake_repo
    (repo/'rtl/fs_reset_sync.sv').write_text('not original\n')
    with pytest.raises(ValueError,match='Unexpected changed tracked'):
        p24.git_source_snapshot(repo,sha)


def test_dirty_constraint_rejected(fake_repo):
    repo,sha=fake_repo
    (repo/'constraints/phase17_cfg_rev_c_overlay.xdc').write_text('set_false_path -from all\n')
    with pytest.raises(ValueError,match='Unexpected changed tracked'):
        p24.git_source_snapshot(repo,sha)


def test_added_phase24_source_is_only_allowed_tracked_change(fake_repo):
    repo,sha=fake_repo
    path=repo/'docs/phase24_research_release.md';path.write_text('synthetic draft\n')
    run_git(repo,'add',str(path.relative_to(repo)))
    head, rows=p24.git_source_snapshot(repo,sha)
    assert head==sha and not any(row[0]==str(path.relative_to(repo)) for row in rows)



def test_committed_non_phase24_change_after_base_rejected(fake_repo):
    repo,sha=fake_repo
    (repo/'rtl/fs_reset_sync.sv').write_text('changed committed hardware\n')
    run_git(repo,'add','rtl/fs_reset_sync.sv')
    run_git(repo,'commit','-qm','unauthorized implementation change')
    with pytest.raises(ValueError,match='Non-Phase24 committed changes'):
        p24.git_source_snapshot(repo,sha)


def test_committed_phase24_file_after_base_is_allowed(fake_repo):
    repo,sha=fake_repo
    path=repo/'docs/phase24_research_release.md';path.write_text('candidate doc\n')
    run_git(repo,'add','docs/phase24_research_release.md')
    run_git(repo,'commit','-qm','test Phase24 file')
    head,rows=p24.git_source_snapshot(repo,sha)
    assert head!=sha
    assert 'docs/phase24_research_release.md' in [r[0] for r in rows]


def test_wrong_reference_pin_rejected(fake_repo):
    repo,sha=fake_repo
    (repo/'docs/ascon_reference_commit.txt').write_text('0'*40+'\n')
    run_git(repo,'add','docs/ascon_reference_commit.txt')
    run_git(repo,'commit','-qm','bad reference pin')
    with pytest.raises(ValueError,match='Non-Phase24 committed changes|Ascon-C reference pin'):
        p24.git_source_snapshot(repo,sha)


def test_full_release_is_deterministic(fake_repo,fabricated_phase23,monkeypatch):
    repo,sha=fake_repo
    root,cp,_,_=fabricated_phase23
    first, files1=p24.build(repo,root,cp,sha)
    second,files2=p24.build(repo,root,cp,sha)
    assert first==second and files1==files2
    assert first['verdict']=='RESEARCH_RELEASE_REVIEW_REQUIRED'
    assert first['board_signoff']=='NOT VERIFIED'
    assert first['current_pr_ci']=='PENDING_EXTERNAL_REVIEW'
    assert set(files1)=={'verification.json','source_manifest.tsv','evidence_manifest.tsv',
                         'release_gates.tsv','release_candidate.md'}
    assert all(p24.sha256_bytes(files1[k])==v for k,v in first['report_sha256'].items())
    assert b'not a verified board build' in files1['release_candidate.md']


def test_preflight_writes_nothing(fake_repo,fabricated_phase23,capsys,monkeypatch):
    repo,sha=fake_repo
    root,cp,_,_=fabricated_phase23
    real=p24.build
    monkeypatch.setattr(p24,'build',lambda a,b,c:real(a,b,c,sha))
    assert p24.main(['--repo',str(repo),'--input-dir',str(root),'--checkpoint',str(cp),
                     '--preflight-only'])==0
    assert 'PHASE24_RELEASE_INPUTS_VERIFIED' in capsys.readouterr().out
    assert not (repo/'build').exists()


def test_output_directory_refuses_overwrite(fake_repo,fabricated_phase23,monkeypatch):
    repo,sha=fake_repo
    root,cp,_,_=fabricated_phase23
    real=p24.build
    monkeypatch.setattr(p24,'build',lambda a,b,c:real(a,b,c,sha))
    out=root/'existing';out.mkdir()
    assert p24.main(['--repo',str(repo),'--input-dir',str(root),
                     '--checkpoint',str(cp),'--out',str(out)])==2
    assert list(out.iterdir())==[]


def test_no_vivado_or_fake_timing_changes():
    src=(ROOT/'scripts/phase24_release_candidate.py').read_text()
    ps=(ROOT/'scripts/phase24_release_candidate.ps1').read_text()
    for forbidden in ('vivado.bat','write_bitstream','route_design',
                      'set_input_delay','set_output_delay','set_false_path'):
        assert forbidden not in ps and forbidden not in src
    assert 'report_timing' not in src
    assert 'github release create' not in ps
    assert 'git push' not in ps


def test_docs_preserve_open_gates():
    doc=(ROOT/'docs/phase24_research_release.md').read_text()
    for term in ('TIMING-18','NOT VERIFIED','NOT QUALIFIED', 'Phase 23', 're-run','no physical'):
        assert term.lower() in doc.lower()
