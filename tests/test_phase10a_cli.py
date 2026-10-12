"""Check the installed project CLI, without starting servers or changing evidence."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from faultscope_ascon.cli import main, verify_evidence

ROOT = Path(__file__).resolve().parents[1]


def test_cli_help_is_real_entry_point(capsys):
    try:
        main(["--help"])
    except SystemExit as e:
        assert e.code == 0
    else:
        raise AssertionError("argparse should exit after --help")
    help_text = capsys.readouterr().out
    assert "verify-evidence" in help_text and "serve" in help_text
    assert "Hello from faultscope-ascon!" not in help_text


def test_cli_verifies_committed_evidence_read_only(capsys):
    paths = [ROOT / "reports/phase4b_temporal.csv", ROOT / "reports/phase7_adversarial.csv",
             ROOT / "reports/phase7b_aead.csv"]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert verify_evidence(ROOT)
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    assert after == before
    captured = capsys.readouterr().out
    assert captured.count("PASS reports/") == 3


def test_cli_fails_closed_on_missing_csv(tmp_path: Path, capsys):
    (tmp_path / "reports/phase5").mkdir(parents=True)
    (tmp_path / "reports/phase5/manifest.json").write_text('{"campaign_sha256": "' + '0'*64 + '"}')
    assert not verify_evidence(tmp_path)
    assert "FAIL" in capsys.readouterr().out


def test_cli_detects_modified_rtl_source(tmp_path: Path, capsys):
    manifest_path = ROOT / "reports/phase5/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    (tmp_path / "reports/phase5").mkdir(parents=True)
    shutil.copy2(manifest_path, tmp_path / "reports/phase5/manifest.json")
    (tmp_path / "docs").mkdir()
    shutil.copy2(ROOT / "docs/ascon_reference_commit.txt", tmp_path / "docs/ascon_reference_commit.txt")
    (tmp_path / "rtl").mkdir()
    for name in manifest["sources_sha256"]:
        shutil.copy2(ROOT / "rtl" / name, tmp_path / "rtl" / name)
    for name in ("phase4b_temporal.csv", "phase7_adversarial.csv", "phase7b_aead.csv"):
        shutil.copy2(ROOT / "reports" / name, tmp_path / "reports" / name)
    assert verify_evidence(tmp_path)
    with (tmp_path / "rtl" / "ascon_round.sv").open("ab") as handle:
        handle.write(b"\n// deliberate mutation\n")
    assert not verify_evidence(tmp_path)
    assert "FAIL rtl/ascon_round.sv" in capsys.readouterr().out
