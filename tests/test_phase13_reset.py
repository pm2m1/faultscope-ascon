"""Phase 13 reset-release and external UART input synchronization pilot.

Real Verilator simulation is mandatory in the opt-in Linux workflow; the
ordinary Windows test subset only checks structural/source integration.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

from experiments.phase11_fpga import NAMES, PORTS

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_reset_release_pipe_is_async_assert_sync_release():
    src = text("rtl/fs_reset_sync.sv")
    assert "posedge clk or negedge rst_n_async" in src
    assert "release_pipe_q <= 3'b000" in src
    assert "release_pipe_q <= {release_pipe_q[1:0], 1'b1}" in src
    assert "assign rst_n_sync = release_pipe_q[2]" in src
    assert 'ASYNC_REG = "TRUE"' in src
    assert 'SHREG_EXTRACT = "NO"' in src


def test_top_only_raw_reset_drives_release_synchronizer():
    src = text("rtl/faultscope_uart_top.sv")
    assert "fs_reset_sync u_reset_sync" in src
    assert ".rst_n_async(rst_n), .rst_n_sync(rst_n_core)" in src
    assert src.count(".rst_n(rst_n_core)") == 3  # RX, TX, core
    assert "always_ff @(posedge clk or negedge rst_n_core)" in src
    assert "if (!rst_n_core) begin" in src
    assert ".rst_n(rst_n)," not in src
    assert "assign led_alarm_o = core_alarm" in src
    assert PORTS == {"clk", "rst_n", "uart_rx_i", "uart_tx_o", "led_busy_o", "led_alarm_o"}


def test_rx_only_second_stage_is_used_by_uart_fsm():
    src = text("rtl/fs_uart_rx.sv")
    assert 'ASYNC_REG = "TRUE"' in src
    assert 'SHREG_EXTRACT = "NO"' in src
    assert "sync_q <= {sync_q[0], rx_i}" in src
    # Only the sync assignment may reference the asynchronous rx_i.
    assert src.count("rx_i") == 2  # port declaration + synchronizer input
    assert "sync_q[1]" in src


def test_source_sets_and_vivado_have_reset_module():
    assert "fs_reset_sync.sv" in NAMES
    assert all((ROOT / "rtl" / name).exists() for name in NAMES)
    assert "fs_reset_sync.sv" in text("scripts/phase12_vivado_ooc.tcl")
    assert '"rtl/fs_reset_sync.sv"' in text("tests/test_phase11_uart.py")
    assert "faultscope_uart_top.sv" in NAMES


def test_reset_regression_targets_core_uart_and_alarm():
    bench = text("tb/tb_faultscope_phase13_reset.sv")
    for value in ("release_after_offset(1)", "release_after_offset(2)",
                  "release_after_offset(3)", "kill_reply", "kill_core",
                  "configure_zero_message(1)", "uart_tx !== 1'b1",
                  "reply[1] !== 8'h06", "dut.loaded_q !== 0",
                  "PASS: Phase 13 reset release"):
        assert value in bench


def test_real_reset_end_to_end_verilator(tmp_path: Path):
    if os.environ.get("FAULTSCOPE_RUN_PHASE13_UART") != "1":
        pytest.skip("Opt-in Phase 13 UART/core interruption simulation")
    verilator = shutil.which("verilator")
    assert verilator, "Verilator required for Phase 13 live verification"
    sources = [*(str(ROOT / "rtl" / n) for n in NAMES),
               str(ROOT / "tb/tb_faultscope_phase13_reset.sv")]
    obj = tmp_path / "obj_dir"
    build = subprocess.run(
        [verilator, "--binary", "--timing", "--assert", "-j", "2", "-Wno-fatal",
         "--top-module", "tb_faultscope_phase13_reset", "--Mdir", str(obj), *sources],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )
    assert build.returncode == 0, (build.stdout + build.stderr)[-7000:]
    binary = obj / ("Vtb_faultscope_phase13_reset" + (".exe" if os.name == "nt" else ""))
    run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, (run.stdout + run.stderr)[-7000:]
    assert "PASS: Phase 13 reset release and UART/core/fault interruption" in run.stdout
