"""Phase 10D Series-7 synthesis accounting and provenance regression checks.

Full synthesis is deliberately opt-in locally; CI workflow runs it as its own job.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from experiments.phase10d_fpga import (
    build_comparison, count_primitives, is_lut, make_report, percent_overhead,
    validate_out_dir, verify_historical_rtl_hashes, yosys_script,
)
from experiments.run_phase5 import DESIGNS, ROOT, source_hashes


def mock_netlist():
    return {"modules": {
        "example": {"cells": {
            "u0": {"type": "LUT6"}, "u1": {"type": "LUT2"},
            "u2": {"type": "FDRE"}, "u3": {"type": "FDCE"},
            "u4": {"type": "CARRY4"}, "u5": {"type": "RAMB18E1"},
            "u6": {"type": "DSP48E1"}, "u7": {"type": "MUXF7"},
            "u8": {"type": "SRLC32E"}, "u9": {"type": "RAM32M"},
            "u10": {"type": "$scopeinfo"},
        }},
    }}


def test_fpga_primitive_accounting_and_metadata_exclusion():
    stats = count_primitives(mock_netlist(), "example")
    assert stats["lut_total"] == 2
    assert stats["lut_by_size"]["LUT6"] == 1
    assert stats["flip_flops"] == 2
    assert stats["carry4"] == 1 and stats["muxf7"] == 1
    assert stats["bram18"] == 1 and stats["dsp48"] == 1
    assert stats["srl"] == 1 and stats["distributed_ram"] == 1
    assert stats["metadata_excluded"] == 1
    assert stats["total_primitives_excluding_metadata"] == 10
    assert is_lut("LUT6") and not is_lut("LUT7") and not is_lut("LUT0")


def test_unmapped_and_unflattened_rtl_are_rejected():
    example = mock_netlist()
    example["modules"]["example"]["cells"]["new"] = {"type": "$_MUX_"}
    with pytest.raises(ValueError, match="not fully"):
        count_primitives(example, "example")
    example["modules"]["example"]["cells"]["new"] = {"type": "ascon_permutation"}
    with pytest.raises(ValueError, match="not fully"):
        count_primitives(example, "example")
    example["modules"]["example"]["cells"]["new"] = {"type": "IBUF"}
    with pytest.raises(ValueError, match="I/O pads"):
        count_primitives(example, "example")


def test_missing_lut_or_top_is_not_accepted_as_mapped_synthesis():
    example = mock_netlist()
    with pytest.raises(ValueError, match="Missing mapped"):
        count_primitives(example, "wrong")
    example["modules"]["example"]["cells"] = {"only_ff": {"type": "FDRE"}}
    with pytest.raises(ValueError, match="No LUT"):
        count_primitives(example, "example")


def test_comparison_has_two_baselines_and_handles_zero_reference():
    rows = {
        "baseline": {"lut_total": 100, "flip_flops": 50, "carry4": 0, "bram18": 0, "bram36": 0, "dsp48": 0},
        "instrumented": {"lut_total": 120, "flip_flops": 60, "carry4": 1, "bram18": 0, "bram36": 0, "dsp48": 0},
        "protected": {"lut_total": 150, "flip_flops": 70, "carry4": 2, "bram18": 0, "bram36": 0, "dsp48": 0},
    }
    comparison = build_comparison(rows)
    assert comparison["lut_total"] == {"protected_vs_baseline_percent": 50.0,
                                        "protected_vs_instrumented_percent": 25.0}
    assert comparison["carry4"]["protected_vs_baseline_percent"] is None
    assert comparison["carry4"]["protected_vs_instrumented_percent"] == 100.0
    assert percent_overhead(99, 0) is None
    assert "out-of-context" in make_report({"architectures": {
        k: {"lut_total": v["lut_total"], "flip_flops": v["flip_flops"], "carry4": v["carry4"],
            "muxf7": 0, "muxf8": 0, "bram18": 0, "bram36": 0, "dsp48": 0} for k,v in rows.items()},
        "comparison": comparison, "tools": {"yosys": "test", "sv2v": "test"},
        "historical_rtl_verified": True, "git_commit": "123"}).lower()


def test_output_directory_cannot_overwrite_committed_evidence(tmp_path):
    project = tmp_path / "project"
    (project / "build").mkdir(parents=True)
    assert validate_out_dir(project / "build" / "phase10d", project) == (project / "build" / "phase10d")
    for unsafe in [project / "reports" / "phase5", project / "rtl", project, project / "build"]:
        with pytest.raises(ValueError, match="subdirectory of build"):
            validate_out_dir(unsafe, project)


def test_yosys_flow_requests_real_xilinx_mapping():
    script = yosys_script("ascon_aead_encrypt_temporal", Path("build/source.v"), Path("build/fpga.json"))
    assert "synth_xilinx -top ascon_aead_encrypt_temporal -family xc7 -flatten -noiopad -noclkbuf" in script
    assert "hierarchy -check -top" in script
    assert "write_json" in script
    assert "check -assert" in script
    assert "-noabc" not in script  # LUT mapping should use ABC


def test_historical_digest_guard_requires_exact_source_set():
    actual = {"one.sv": "abc", "two.sv": "def"}
    verify_historical_rtl_hashes(actual, {"sources_sha256": dict(actual)})
    with pytest.raises(ValueError, match="disagrees"):
        verify_historical_rtl_hashes(actual, {"sources_sha256": {"one.sv": "abc"}})
    with pytest.raises(ValueError, match="one.sv"):
        verify_historical_rtl_hashes(actual, {"sources_sha256": {"one.sv": "oops", "two.sv": "def"}})


def test_real_report_provenance_from_committed_rtl():
    historical = json.loads((ROOT / "reports/phase5/manifest.json").read_text())
    assert set(DESIGNS) == {"baseline", "instrumented", "protected"}
    verify_historical_rtl_hashes(source_hashes(), historical, source_dir=ROOT / "rtl")


def test_live_fpga_synthesis_opt_in(tmp_path):
    if os.environ.get("FAULTSCOPE_RUN_PHASE10D_FPGA") != "1":
        pytest.skip("Optional live FPGA synthesis: run experiments.phase10d_fpga CLI or opt in")
    from experiments.phase10d_fpga import main
    # The full run is validated by the standalone CLI/CI; this test just checks
    # the created result after a separate, successful invocation.
    import subprocess, sys
    p = subprocess.run([sys.executable, "-m", "experiments.phase10d_fpga", "--out-dir",
                        str(ROOT / "build" / "phase10d_pytest")], cwd=ROOT,
                       capture_output=True, text=True, timeout=3600)
    assert p.returncode == 0, p.stdout + "\n" + p.stderr
    result = json.loads((ROOT / "build" / "phase10d_pytest" / "fpga_resources.json").read_text())
    assert result["target_family"] == "xc7"
    assert all(result["architectures"][name]["lut_total"] > 0 for name in DESIGNS)
