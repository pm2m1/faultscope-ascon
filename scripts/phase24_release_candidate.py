"""Phase 24 qualified research-release candidate: offline, read-only, fail-closed.

Re-evaluates Phase 15–22 with Phase 23's accepted validator, requires exact
Phase 23 derived evidence, and snapshots Git HEAD *blobs* (not checkout EOLs).
Never asserts physical board signoff and never invokes FPGA tools.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA = '1ce848e480dcfb65045ee04b89d2b67de57ade39'
ASCON_C_SHA = '446347f21b209f3921c65ece70027c366cbe1693'
EXPECTED_PHASE23 = {
    'verification.json', 'evidence_sources.tsv', 'qualified_claims.tsv',
    'open_gaps.tsv', 'dossier.md',
}
PHASE23_ZIP = 'faultscope_phase23_review.zip'
ALLOWED_PHASE24_CHANGES = {
    'scripts/phase24_release_candidate.py',
    'scripts/phase24_release_candidate.ps1',
    'tests/test_phase24_release_candidate.py',
    'docs/phase24_research_release.md',
    'docs/phase24_manual_review.md',
}
SRC_FIELDS = ['path', 'git_blob_sha1', 'sha256_git_blob', 'size_bytes']
EVID_FIELDS = ['phase', 'archive', 'archive_sha256', 'integrity_qualification']
GATE_FIELDS = ['gate', 'state', 'basis', 'interpretation']
MAX_MEMBER_SIZE = 2 * 1024 * 1024
MAX_ARCHIVE_SIZE = 8 * 1024 * 1024


def require(ok: bool, detail: str) -> None:
    if not ok:
        raise ValueError(detail)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for buf in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(buf)
    return h.hexdigest()


def load_phase23_module(repo: Path):
    path = repo / 'scripts/phase23_evidence_gap_matrix.py'
    require(path.is_file(), 'Missing merged Phase 23 validator')
    spec = importlib.util.spec_from_file_location('phase23_release_dependency', path)
    require(spec is not None and spec.loader is not None, 'Could not load Phase 23 validator')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_phase23_review(path: Path) -> dict[str, bytes]:
    require(path.is_file(), f'Missing Phase 23 review ZIP: {path}')
    with zipfile.ZipFile(path) as bundle:
        members = bundle.infolist()
        names = [i.filename for i in members]
        require(len(names) == len(set(names)) and set(names) == EXPECTED_PHASE23,
                'Phase 23 review ZIP: unexpected/duplicate members')
        require(all(not i.is_dir() and '/' not in i.filename and '\\' not in i.filename
                    and i.file_size <= MAX_MEMBER_SIZE for i in members)
                and sum(i.file_size for i in members) <= MAX_ARCHIVE_SIZE,
                'Phase 23 ZIP: unsafe paths or oversized content')
        require(bundle.testzip() is None, 'Phase 23 ZIP CRC failure')
        return {name: bundle.read(name) for name in names}


def validate_phase23(repo: Path, archives: Path, checkpoint: Path):
    p23 = load_phase23_module(repo)
    result, recreated = p23.build(archives, checkpoint)
    require(result['verdict'] == 'EVIDENCE_MATRIX_REVIEW_REQUIRED',
            'Phase 23 historical evidence cannot be qualified')
    original = load_phase23_review(archives / PHASE23_ZIP)
    for name in sorted(EXPECTED_PHASE23):
        require(recreated[name] == original[name],
                f'Phase 23 derived output is not byte-reproducible: {name}')
    old = json.loads(original['verification.json'])
    for name, expected in old['output_sha256'].items():
        require(sha256_bytes(original[name]) == expected,
                f'Phase 23 recorded derived SHA mismatch: {name}')
    require(old == result, 'Phase 23 manifest is inconsistent with rebuilt evidence')
    require(result['claims_recorded'] == 8 and result['open_gaps'] == 8 and
            result['evidence_limitations'] == 1 and
            result['external_io_missing_delay_count'] == 5,
            'Phase 23 claims/gaps unexpectedly changed')
    require(result['board_signoff'] == 'NOT VERIFIED' and
            result['board_revision'] == 'PROVISIONAL_NOT_CONFIRMED' and
            result['bitstream_generated'] is False and
            result['board_programmed'] is False,
            'Unsupported physical-hardware qualification in Phase 23 evidence')
    return result, sha256_file(archives / PHASE23_ZIP), original


def git(repo: Path, *args: str) -> bytes:
    p = subprocess.run(['git', '-C', str(repo), *args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if p.returncode:
        raise ValueError(f'Git provenance query failed: {" ".join(args)}: '
                         + p.stderr.decode('utf-8', errors='replace')[:240])
    return p.stdout


def git_source_snapshot(repo: Path, expected_base: str = BASE_SHA):
    repo = repo.resolve()
    top = Path(git(repo, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
    require(top == repo, 'Expected repository root, not a nested/unrelated checkout')
    current = git(repo, 'rev-parse', 'HEAD').decode().strip()
    require(bool(re.fullmatch('[a-f0-9]{40}', current)), 'Invalid Git commit')
    git(repo, 'merge-base', '--is-ancestor', expected_base, 'HEAD')
    history_changed = {p for p in git(repo, 'diff', '--name-only', '-z', expected_base,
                                       'HEAD').decode('utf-8').split('\x00') if p}
    require(history_changed <= ALLOWED_PHASE24_CHANGES,
            'Non-Phase24 committed changes since accepted base: ' +
            repr(sorted(history_changed - ALLOWED_PHASE24_CHANGES)))

    changed = git(repo, 'diff', '--name-only', '-z', 'HEAD').decode('utf-8').split('\x00')
    changed = {s for s in changed if s}
    require(changed <= ALLOWED_PHASE24_CHANGES,
            'Unexpected changed tracked files: ' + repr(sorted(changed - ALLOWED_PHASE24_CHANGES)))
    # Untracked files (e.g. the new pilot) are not part of the frozen base snapshot.
    data = git(repo, 'ls-tree', '-r', '-z', 'HEAD')
    rows = []
    for item in data.split(b'\0'):
        if not item:
            continue
        meta, raw_path = item.split(b'\t', 1)
        mode, objtype, blob_sha = meta.decode().split()
        require(objtype == 'blob' and mode in {'100644', '100755'},
                'Source inventory contains a symlink/submodule/non-regular tracked file')
        path = raw_path.decode('utf-8')
        require(path and '\n' not in path and '\r' not in path and '\t' not in path,
                'Unexpected Git tree pathname')
        body = git(repo, 'cat-file', 'blob', blob_sha)
        rows.append([path, blob_sha, sha256_bytes(body), str(len(body))])
    require(rows and [row[0] for row in rows] == sorted(row[0] for row in rows),
            'Git tree inventory is missing or unordered')
    path_map = {row[0]: row for row in rows}
    for required in ['rtl/faultscope_uart_top.sv', 'rtl/fs_reset_sync.sv',
                     'constraints/phase15_nexys4_ddr_rev_c.xdc',
                     'constraints/phase17_cfg_rev_c_overlay.xdc',
                     'docs/ascon_reference_commit.txt', 'uv.lock',
                     'frontend/package-lock.json', '.github/workflows/verify.yml',
                     '.github/workflows/sequential-formal.yml',
                     'scripts/phase23_evidence_gap_matrix.py']:
        require(required in path_map, 'Missing research release source: ' + required)
    pinned = git(repo, 'show', 'HEAD:docs/ascon_reference_commit.txt').decode().strip()
    require(pinned == ASCON_C_SHA, 'Ascon-C reference pin is no longer accepted')
    return current, rows


def render_tsv(headers: list[str], rows: list[list[str]]) -> bytes:
    buf = io.StringIO(newline='')
    writer = csv.writer(buf, delimiter='\t', lineterminator='\n')
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue().encode()


def release_gates(result: dict, has_current_ci: bool = False):
    # CI is intentionally never established from offline artifacts.
    require(not has_current_ci, 'Offline validator cannot assert current commit CI status')
    return [
        ['historical_evidence', 'VERIFIED_OFFLINE', 'Phase 15–22 independently revalidated by Phase 23', 'Bounded routed-model evidence'],
        ['phase23_reproduction', 'BYTE_IDENTICAL', 'Five derived files reproduced byte-for-byte', 'Historical artifacts internally consistent'],
        ['checkpoint_digest', 'VERIFIED_LOCALLY', result['phase17_checkpoint_actual_sha256'], 'Checkpoint bytes checked on executing machine'],
        ['source_commit', 'VERIFIED_GIT', 'Accepted Phase 23 merge is ancestor of HEAD', 'Tracked Git blobs inventoried'],
        ['current_pr_ci', 'PENDING_EXTERNAL_REVIEW', 'GitHub Actions not invoked or checked by this tool', 'Must verify fresh Phase 24 PR checks separately'],
        ['board_revision', 'NOT_VERIFIED', 'No physical board identification', 'Provisional Nexys4 DDR Rev. C'],
        ['physical_reset', 'NOT_VERIFIED', 'Pulse, bounce, clock startup and recovery/removal unqualified', 'No external reset signoff'],
        ['external_io', 'NOT_QUALIFIED', 'Five TIMING-18 missing external I/O delays', 'No manufactured timing constraints'],
        ['uart_mtbf', 'NOT_VERIFIED', 'Analog metastability calculation absent', 'No synchronizer MTBF claim'],
        ['bitstream_board_operation', 'NOT_VERIFIED', 'No bitstream or board programming', 'Research release only'],
        ['legacy_member_integrity', 'PARTIAL', 'Phase 15–18 partially hashed historical ZIP members', 'No trusted producer signature'],
    ]


def build(repo: Path, archives: Path, checkpoint: Path, expected_base: str = BASE_SHA):
    phase23, p23_archive_sha, oldfiles = validate_phase23(repo, archives, checkpoint)
    head, source_rows = git_source_snapshot(repo, expected_base)
    evid_rows = []
    p23_sources = list(csv.DictReader(io.StringIO(oldfiles['evidence_sources.tsv'].decode()), delimiter='\t'))
    require(len(p23_sources) == 8 and
            [int(r['phase']) for r in p23_sources] == list(range(15, 23)),
            'Phase 23 source archive inventory incomplete')
    for row in p23_sources:
        evid_rows.append([row['phase'], row['archive'], row['archive_sha256'], row['integrity_class']])
    evid_rows.append(['23', PHASE23_ZIP, p23_archive_sha, 'BYTE_REPRODUCED_WITH_SELF_HASHES'])
    gates = release_gates(phase23)
    output = {
        'source_manifest.tsv': render_tsv(SRC_FIELDS, source_rows),
        'evidence_manifest.tsv': render_tsv(EVID_FIELDS, evid_rows),
        'release_gates.tsv': render_tsv(GATE_FIELDS, gates),
    }
    notes = [
        '# FaultScope-Ascon — Phase 24 qualified research release candidate', '',
        '**Status: RESEARCH_RELEASE_REVIEW_REQUIRED (NOT hardware signoff).**', '',
        f'- Frozen Git HEAD (source snapshot): `{head}`',
        f'- Accepted Phase 23 ancestry anchor: `{expected_base}`',
        f'- Accepted Phase 17 routed DCP SHA-256: `{phase23["phase17_checkpoint_actual_sha256"]}`',
        f'- Pinned Ascon-C source commit: `{ASCON_C_SHA}`',
        f'- Tracked Git source blobs inventoried: **{len(source_rows)}**',
        '- Phase 15–23 original review archives bound: **9**',
        '- Phase 23 generated reports reproduced **byte-for-byte**',
        '- Phase 23 engineering ledger: **8 evidence-bounded claims, 8 OPEN requirements, 1 archive-integrity LIMITATION**',
        '- Five external I/O timing-delay warnings persist; six external reset path slack values remain unavailable',
        '', '## Reproducibility', '',
        'From the matching Git checkout, run the original Phase 23 validator against the nine review archives',
        'and accepted routed checkpoint. This Phase 24 script repeats that validation, compares all Phase 23',
        'derived report bytes, and hashes all tracked Git HEAD blobs without rewriting source files.', '',
        'The GitHub PR for this candidate MUST pass fresh Python/Verilator, Yosys/formal, and dashboard CI.',
        'The baseline merge commit CI is informative but does not substitute for candidate PR CI.',
        'A full local Verilator/Yosys run is not implied by this offline script.', '',
        '## Hardware and source qualification boundaries', '',
        'This is a **pre-silicon research artifact**, not a verified board build, production cryptographic',
        'implementation, validated hardware countermeasure, or physical fault-injection demonstration.',
        'Board identification, external reset pulse/bounce and recovery/removal, oscillator startup/jitter,',
        'UART analog MTBF, USB-UART and LED delay budgets, programming and actual hardware operation are',
        'not verified. Do not invent XDC delays, add blanket timing exceptions, synthesize/reroute,',
        'generate a bitstream, create a public release or tag automatically.', '',
        '## Evidence nuance', '',
        'The SHA-256 digests prove consistency with supplied archived bytes, not externally signed provenance.',
        'Legacy Phases 15–18 include individually unhashed archive members. The DCP digest verifies only the',
        'actual checkpoint present on the machine that ran the validator. This pre-commit candidate includes',
        'only tracked Git HEAD blobs in its source snapshot; untracked Phase 24 pilot files are not frozen',
        'until their PR is committed and merged. Re-run after merge to bind the final release commit.', '',
        '## Mandatory post-merge gate', '',
        'Confirm final PR checks and merge commit, re-run the Phase 24 validator from merged main,',
        'review the final output digests and explicitly decide whether to create a GitHub research-release',
        'tag. Never label the result physical board signoff.', '',
    ]
    output['release_candidate.md'] = '\n'.join(notes).encode()
    summary = {
        'phase': '24',
        'verdict': 'RESEARCH_RELEASE_REVIEW_REQUIRED',
        'scope': 'offline read-only source/evidence provenance and qualified research release candidate',
        'base_phase23_merge_commit': expected_base,
        'source_head_commit': head,
        'source_tracked_file_count': len(source_rows),
        'evidence_archives': 9,
        'phase23_reproduced_reports': 5,
        'qualified_claims': 8,
        'open_dependencies': 8,
        'legacy_evidence_limitations': 1,
        'missing_io_delays': 5,
        'accepted_phase17_checkpoint_sha256': phase23['phase17_checkpoint_actual_sha256'],
        'current_pr_ci': 'PENDING_EXTERNAL_REVIEW',
        'board_revision': 'PROVISIONAL_NOT_CONFIRMED',
        'board_signoff': 'NOT VERIFIED',
        'reset_electrical_timing': 'NOT VERIFIED',
        'external_io_timing': 'NOT QUALIFIED',
        'uart_mtbf': 'NOT VERIFIED',
        'bitstream_generated': False,
        'board_programmed': False,
        'source_or_checkpoint_modified': False,
        'report_sha256': {name: sha256_bytes(data) for name, data in sorted(output.items())},
    }
    output['verification.json'] = (json.dumps(summary, indent=2, sort_keys=True) + '\n').encode()
    return summary, output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    if not args.preflight_only and args.out is None:
        parser.error('--out is required unless --preflight-only')
    try:
        if args.out is not None:
            require(not args.out.exists(), 'Output already exists: ' + str(args.out))
        summary, output = build(args.repo.resolve(), args.input_dir, args.checkpoint)
        if args.preflight_only:
            print(json.dumps({'phase': '24', 'verdict': 'PHASE24_RELEASE_INPUTS_VERIFIED',
                'source_head_commit': summary['source_head_commit'],
                'evidence_archives': 9, 'board_signoff': 'NOT VERIFIED'}, indent=2))
        else:
            args.out.mkdir(parents=True, exist_ok=False)
            for name, body in output.items():
                (args.out / name).write_bytes(body)
            print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, zipfile.BadZipFile) as exc:
        print(json.dumps({'phase': '24', 'verdict': 'NOT_VERIFIED',
                          'issues': [str(exc)], 'board_signoff': 'NOT VERIFIED'}, indent=2),
              file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
