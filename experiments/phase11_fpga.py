"""Out-of-context FPGA mapping screen for the Phase 11 UART top.

This does NOT include a Vivado board XDC, placement, routing or timing.
It proves no board deployment claims. Run only after RTL UART simulation passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess

from experiments.phase10d_fpga import count_primitives, validate_out_dir
from experiments.run_phase5 import ROOT, tool_version

TOP = "faultscope_uart_top"
NAMES = (
    "ascon_round.sv", "ascon_permutation_faultable.sv",
    "ascon_permutation_temporal.sv", "ascon_aead_encrypt_temporal.sv",
    "fs_uart_rx.sv", "fs_uart_tx.sv", "faultscope_uart_top.sv",
)
PORTS = {"clk", "rst_n", "uart_rx_i", "uart_tx_o", "led_busy_o", "led_alarm_o"}


def validate_ports(netlist: dict) -> None:
    ports = netlist["modules"][TOP].get("ports", {})
    if set(ports) != PORTS or any(len(p.get("bits", [])) != 1 for p in ports.values()):
        raise ValueError(f"Unexpected physical top-level port map: {list(ports)}")
    if len(PORTS) > 210:
        raise ValueError("XC7A100T CSG324 maximum user I/O exceeded")


def synthesize(out_dir: Path) -> dict:
    out_dir = validate_out_dir(out_dir)
    yosys, sv2v = shutil.which("yosys"), shutil.which("sv2v")
    if not yosys or not sv2v:
        raise RuntimeError("Phase 11 screen needs yosys and sv2v")
    if tool_version(sv2v, ["--numeric-version"]) != "0.0.13":
        raise RuntimeError("Expected pinned sv2v 0.0.13")
    recorded = json.loads((ROOT / "reports/phase5/manifest.json").read_text())["sources_sha256"]
    for name, sha in recorded.items():
        if hashlib.sha256((ROOT / "rtl" / name).read_bytes()).hexdigest() != sha:
            raise ValueError(f"Original Ascon RTL source differs from Phase 5: {name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    converted = out_dir / "uart_top.v"
    conversion = subprocess.run([sv2v, *[str(ROOT / "rtl" / n) for n in NAMES]],
                                capture_output=True, text=True, timeout=120, cwd=ROOT)
    (out_dir / "sv2v.log").write_text(conversion.stderr)
    if conversion.returncode:
        raise RuntimeError("sv2v conversion failed: " + conversion.stderr[-1500:])
    converted.write_text(conversion.stdout)
    netlist = out_dir / "uart_top_mapped.json"
    script = (
        f'read_verilog "{converted.resolve()}"; '
        f'hierarchy -check -top {TOP}; '
        f'synth_xilinx -top {TOP} -family xc7 -flatten -noiopad -noclkbuf; '
        f'check -assert; stat -tech xilinx; write_json "{netlist.resolve()}"'
    )
    executed = subprocess.run([yosys,"-Q","-T","-p",script],capture_output=True,text=True,
                              timeout=500,cwd=ROOT)
    (out_dir / "yosys.log").write_text(executed.stdout+"\n"+executed.stderr)
    if executed.returncode:
        raise RuntimeError(f"Yosys XC7 UART mapping failed ({executed.returncode}): " + executed.stderr[-1600:])
    mapped = json.loads(netlist.read_text())
    validate_ports(mapped)
    metrics = count_primitives(mapped, TOP)
    report = {
        "scope": "out-of-context Xilinx xc7 mapping; not placement, routing, timing or board operation",
        "target_family": "xc7",
        "target_device_screen": "XC7A100T-CSG324 (package pin constraints NOT supplied)",
        "clock_parameter": "100 MHz expected external clock; CLOCKS_PER_BIT=868 (115207 expected baud)",
        "num_top_level_signal_bits": len(PORTS),
        "top_ports": sorted(PORTS),
        "rtl_sha256": {name: hashlib.sha256((ROOT/"rtl"/name).read_bytes()).hexdigest() for name in NAMES},
        "historical_rtl_pinned": True,
        "yosys": tool_version(yosys,["-V"]),
        "sv2v": tool_version(sv2v,["--numeric-version"]),
        "metrics": metrics,
        "utc_time": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "uart_resource_screen.json").write_text(json.dumps(report,indent=2)+"\n")
    print(f"PASS: UART wrapper XC7 mapping; {metrics['lut_total']} LUTs, {metrics['flip_flops']} FFs; six top-level bits")
    print(f"Report: {out_dir / 'uart_resource_screen.json'}")
    return report


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',type=Path,default=ROOT/'build/reproduction/phase11')
    args=p.parse_args()
    synthesize(args.out_dir)


if __name__=='__main__':
    main()
