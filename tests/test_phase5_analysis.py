"""Phase 5 tests: inspect report math and synthesis netlist parsing."""

import csv
import json
from pathlib import Path

import pytest

from experiments.run_phase5 import (
    REQUIRED_CAMPAIGN_COLUMNS,
    campaign_stats,
    cell_stats,
    change_percent,
    is_sequential,
    make_markdown,
    read_campaign,
    write_synthesis_csv,
)


def test_yosys_generic_cell_and_ff_count():
    netlist = {
        "modules": {
            "demo": {
                "cells": {
                    "ff0": {"type": "$_DFFE_PN0P_", "connections": {"Q": [5]}},
                    "ff1": {"type": "$_DFF_P_", "connections": {"Q": [6]}},
                    "and": {"type": "$_AND_", "connections": {"Y": [7]}},
                    "mux": {"type": "$_MUX_", "connections": {"Y": [8]}},
                }
            }
        }
    }
    stats = cell_stats(netlist, "demo")
    assert stats["total_cells"] == 4
    assert stats["sequential_cells"] == 2
    assert stats["sequential_q_bits"] == 2
    assert stats["combinational_cells"] == 2
    assert is_sequential("$_DFF_P_")
    assert not is_sequential("$_XOR_")
    with pytest.raises(ValueError, match="missing"):
        cell_stats(netlist, "wrong_top")


def test_campaign_metrics_and_policy(tmp_path):
    cases = [
        {"case": 0, "ad_len": 0, "msg_len": 0, "phase": 0,
         "injected": 1, "detected": 1, "valid": 0, "baseline_cycles": 40,
         "protected_cycles": 80, "faulted_cycles": 80},
        {"case": 1, "ad_len": 1, "msg_len": 16, "phase": 4,
         "injected": 0, "detected": 0, "valid": 1, "baseline_cycles": 60,
         "protected_cycles": 120, "faulted_cycles": 120},
    ]
    path = tmp_path / "campaign.csv"
    with path.open("w", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=list(cases[0]))
        w.writeheader()
        w.writerows(cases)
    assert REQUIRED_CAMPAIGN_COLUMNS <= set(cases[0])
    stats = campaign_stats(read_campaign(path))
    assert stats["cases"] == 2
    assert stats["applied_faults"] == stats["detected_faults"] == 1
    assert stats["unfaulted_cases"] == 1
    assert stats["coverage_percent"] == 100
    assert stats["false_alarms"] == 0
    assert stats["mean_baseline_cycles"] == 50
    assert stats["mean_protected_cycles"] == 100
    assert stats["relative_mean_latency_increase_percent"] == 100
    assert change_percent(100, 200) == 100


def test_reports_render(tmp_path):
    base = {"top": "top", "total_cells": 100, "sequential_cells": 30,
            "sequential_q_bits": 30, "combinational_cells": 70,
            "cell_types": {"$_AND_": 70, "$_DFF_P_": 30}}
    inst = {**base, "total_cells": 140, "sequential_q_bits": 35, "combinational_cells": 105}
    protected = {**base, "total_cells": 200, "sequential_q_bits": 70, "combinational_cells": 130}
    measure = {"baseline": base, "instrumented": inst, "protected": protected}
    out = tmp_path / "synth.csv"
    write_synthesis_csv(out, measure)
    assert len(out.read_text().splitlines()) == 4
    stats = campaign_stats([
        {"case": 0, "phase": 0, "injected": 1, "detected": 1, "valid": 0,
         "baseline_cycles": 47, "protected_cycles": 96}
    ])
    report = make_markdown(stats, measure, {"yosys": "yosys 0.69", "sv2v": "0.0.13", "flow": "noabc"}, Path("foo.csv"))
    assert "200" in report
    assert "physical fault" in report.lower()
    assert "100.00%" in report
