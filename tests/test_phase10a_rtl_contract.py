"""Execute actual protected RTL with fail-closed SVA and a known-bad monitor test.

A simulation assertion is not a proof of all reachable hardware states.
"""
from __future__ import annotations

import shutil
import subprocess
import os

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tb" / "ascon_temporal_safety_contract.sv"
RTL = [ROOT / "rtl" / p for p in (
    "ascon_round.sv", "ascon_permutation_faultable.sv",
    "ascon_permutation_temporal.sv", "ascon_aead_encrypt_temporal.sv",
)]


def simulation_run_options(platform: str) -> dict:
    """Suppress POSIX assertion core dumps without Windows-only import errors."""
    if platform != "posix":
        return {}
    import resource

    def no_core_dumps() -> None:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return {"preexec_fn": no_core_dumps}


def compile_and_run(tmp_path: Path, top: str, extra_sources: list[Path]) -> subprocess.CompletedProcess:
    verilator = shutil.which("verilator")
    if os.name == "nt" and not verilator:
        pytest.skip("Verilator is not installed on this Windows machine; Linux CI remains mandatory")
    assert verilator, "Verilator must be installed; RTL property checks are mandatory"
    output_dir = tmp_path / top
    output_dir.mkdir()
    sources = [CONTRACT, *extra_sources]
    cmd = [verilator, "--binary", "--assert", "--timing", "-Wno-fatal", "-j", "2",
           "--top-module", top, "--Mdir", str(output_dir),
           *[str(p) for p in sources]]
    built = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180)
    assert built.returncode == 0, f"Contract compilation failed:\n{built.stdout}\n{built.stderr}"
    executable = output_dir / (f"V{top}" + (".exe" if os.name == "nt" else ""))
    return subprocess.run([str(executable)], cwd=ROOT,
                          capture_output=True, text=True, timeout=90,
                          **simulation_run_options(os.name))


def test_temporal_controller_obeys_contract(tmp_path: Path):
    run = compile_and_run(tmp_path, "tb_ascon_safety_contract",
                          [*RTL, ROOT / "tb/tb_ascon_safety_contract.sv"])
    assert run.returncode == 0, f"RTL assertion failed:\n{run.stdout}\n{run.stderr}"
    assert "PASS: temporal RTL safety assertions" in run.stdout


def test_contract_detects_deliberately_leaking_fake_output(tmp_path: Path):
    run = compile_and_run(tmp_path, "tb_ascon_contract_violation",
                          [ROOT / "tb/tb_ascon_contract_violation.sv"])
    combined = run.stdout + run.stderr
    assert run.returncode != 0, "Expected an SVA failure for deliberately exposed invalid data"
    assert "CONTRACT_OUTPUT_MASK" in combined, f"Wrong failure reason:\n{combined}"


def test_simulation_subprocess_options_are_portable(monkeypatch):
    import sys
    from types import SimpleNamespace
    calls = []
    fake_resource = SimpleNamespace(RLIMIT_CORE=4, setrlimit=lambda *args: calls.append(args))
    monkeypatch.setitem(sys.modules, "resource", fake_resource)
    assert simulation_run_options("nt") == {}
    options = simulation_run_options("posix")
    options["preexec_fn"]()
    assert calls == [(4, (0, 0))]


def test_contract_still_requires_verilator_on_posix(monkeypatch, tmp_path):
    from types import SimpleNamespace
    monkeypatch.setitem(globals(), "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(shutil, "which", lambda executable: None)
    with pytest.raises(AssertionError, match="RTL property checks are mandatory"):
        compile_and_run(tmp_path, "unused", [])
