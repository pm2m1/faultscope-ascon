"""Out-of-context Xilinx Series-7 FPGA primitive synthesis for the three Ascon variants.

This runs the real RTL through sv2v + Yosys synth_xilinx -family xc7. It does
not select a board part, perform placement/routing, meet timing, or measure power.
All outputs go into build/ by default; committed historical evidence is immutable.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from experiments.run_phase5 import DESIGNS, ROOT, source_hashes, tool_version

ARCHITECTURE = "xc7"
EXPECTED_SV2V = "0.0.13"
FLOW_FLAGS = ("-family", "xc7", "-flatten", "-noiopad", "-noclkbuf")
OUTPUT_NAMES = ("fpga_resources.json", "fpga_resources.csv", "REPORT.md", "manifest.json")
# Regs native to xc7; count separately from latch primitives when appropriate.
FF_PRIMITIVES = frozenset({"FDRE", "FDSE", "FDCE", "FDPE"})
LATCH_PRIMITIVES = frozenset({"LDCE", "LDPE"})
IO_PRIMITIVES = frozenset({"IBUF", "OBUF", "IOBUF", "OBUFT", "IBUFG", "IOBUFDS", "IBUFDS", "OBUFDS"})


def is_lut(name: str) -> bool:
    return bool(re.fullmatch(r"LUT[1-6]", name))


def count_primitives(netlist: dict, top: str) -> dict:
    """Count only *mapped top-level* XC7 cells, never generic gates or metadata."""
    modules = netlist.get("modules")
    if not isinstance(modules, dict) or top not in modules:
        raise ValueError(f"Missing mapped top module {top!r}")
    cells = modules[top].get("cells")
    if not isinstance(cells, dict) or not cells:
        raise ValueError("FPGA netlist is missing mapped cells")
    types = Counter()
    for entry in cells.values():
        typ = entry.get("type")
        if not isinstance(typ, str) or not typ:
            raise ValueError("Malformed cell type")
        types[typ] += 1
    # The first condition catches failed technology mapping. The second catches
    # accidental omission of -flatten, which would undercount resources.
    unmapped = sorted(k for k in types if k.startswith("$") and k != "$scopeinfo")
    nested = sorted(k for k in types if k in modules and k != top and not
                    _is_blackbox(modules[k]))
    if unmapped or nested or any(k.startswith("ascon_") for k in types):
        raise ValueError(f"FPGA netlist not fully technology mapped/flattened: {unmapped}, {nested}")
    if any(k in IO_PRIMITIVES for k in types):
        raise ValueError("Unexpected I/O pads; expected out-of-context -noiopad synthesis")
    lut_counts = {f"LUT{i}": types.get(f"LUT{i}", 0) for i in range(1, 7)}
    metadata = types.get("$scopeinfo", 0)
    if sum(lut_counts.values()) == 0:
        raise ValueError("No LUT primitives; did synth_xilinx run?")
    return {
        "total_primitives_excluding_metadata": sum(types.values()) - metadata,
        "metadata_excluded": metadata,
        "lut_total": sum(lut_counts.values()),
        "lut_by_size": lut_counts,
        "flip_flops": sum(types.get(k, 0) for k in FF_PRIMITIVES),
        "latches": sum(types.get(k, 0) for k in LATCH_PRIMITIVES),
        "carry4": types.get("CARRY4", 0),
        "muxf7": types.get("MUXF7", 0),
        "muxf8": types.get("MUXF8", 0),
        "bram18": sum(v for k,v in types.items() if k.startswith("RAMB18")),
        "bram36": sum(v for k,v in types.items() if k.startswith("RAMB36")),
        "dsp48": sum(v for k,v in types.items() if k.startswith("DSP48")),
        "srl": sum(v for k,v in types.items() if k.startswith(("SRL16", "SRLC32"))),
        "distributed_ram": sum(v for k,v in types.items() if re.match(r"RAM(16|32|64|128|256|512)X|RAM(32|64)M", k)),
        "cell_types": dict(sorted(types.items())),
    }


def _is_blackbox(mod: dict) -> bool:
    attr = mod.get("attributes", {}).get("blackbox", "0")
    if isinstance(attr, int):
        return bool(attr)
    try:
        return bool(int(attr, 2))
    except (ValueError, TypeError):
        return False


def percent_overhead(new: int, old: int) -> float | None:
    return round((new / old - 1) * 100, 4) if old > 0 else None


def build_comparison(rows: dict) -> dict:
    for name in DESIGNS:
        if name not in rows:
            raise ValueError(f"Missing synthesized architecture: {name}")
    result = {}
    for metric in ("lut_total", "flip_flops", "carry4", "bram18", "bram36", "dsp48"):
        result[metric] = {
            "protected_vs_baseline_percent": percent_overhead(rows["protected"][metric], rows["baseline"][metric]),
            "protected_vs_instrumented_percent": percent_overhead(rows["protected"][metric], rows["instrumented"][metric]),
        }
    return result


def verify_historical_rtl_hashes(actual: dict[str, str], pinned: dict) -> None:
    recorded = pinned.get("sources_sha256", {})
    if not isinstance(recorded, dict) or not recorded:
        raise ValueError("Missing Phase 5 source provenance")
    if set(actual) != set(recorded):
        raise ValueError("Source set disagrees with historical manifest")
    for path, digest in recorded.items():
        if actual.get(path) != digest:
            raise ValueError(f"RTL source differs from Phase 5 provenance: {path}")


def validate_out_dir(out_dir: Path, root: Path = ROOT) -> Path:
    result = out_dir.resolve()
    approved_root = (root / "build").resolve()
    if not result.is_relative_to(approved_root) or result == approved_root:
        raise ValueError("Phase 10D output must be a subdirectory of build/ (never reports/ or rtl/)")
    return result


def yosys_script(top: str, converted: Path, mapped: Path) -> str:
    # Yosys's command parser accepts quoted names, including Mac paths with spaces.
    def path_arg(p: Path) -> str:
        return '"' + str(p.resolve()).replace('\\', '\\\\').replace('"', '\\"') + '"'
    return "; ".join((
        f"read_verilog {path_arg(converted)}",
        f"hierarchy -check -top {top}",
        f"synth_xilinx -top {top} -family xc7 -flatten -noiopad -noclkbuf",
        "check -assert",
        "stat -tech xilinx",
        f"write_json {path_arg(mapped)}",
    ))


def run_logged(args: list[str], log: Path, *, timeout: int) -> str:
    try:
        run = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        log.write_text(f"Timed out after {timeout}s: {shlex.join(args)}\n")
        raise RuntimeError(f"Synthesis timed out; inspect {log}") from e
    output = run.stdout + "\n" + run.stderr
    log.write_text("$ " + shlex.join(args) + "\n\n" + output)
    if run.returncode != 0:
        raise RuntimeError(f"Synthesis failed (exit {run.returncode}); inspect {log}\n{output[-2000:]}")
    return run.stdout


def make_report(summary: dict) -> str:
    entries = summary["architectures"]
    lines = ["# Phase 10D — Series-7 FPGA synthesis (out-of-context)", "",
        "**Model:** Yosys `synth_xilinx -family xc7` after sv2v conversion; no I/O pads or clock-buffer insertion.",
        "**Not measured:** Vivado placement/routing, actual XC7A100T capacity percentage, timing closure, power, or board pin feasibility.",
        "", "| Architecture | LUT1–6 total | FF | CARRY4 | MUXF7/8 | BRAM18/36 | DSP48 |",
        "|---|---:|---:|---:|---:|---:|---:|",]
    for design in DESIGNS:
        e = entries[design]
        lines.append(f"| {design} | {e['lut_total']:,} | {e['flip_flops']:,} | {e['carry4']:,} | {e['muxf7']:,}/{e['muxf8']:,} | {e['bram18']:,}/{e['bram36']:,} | {e['dsp48']:,} |")
    lines.extend(["", "## Overheads", "", "| Primitive | Protected vs baseline | Protected vs instrumented |", "|---|---:|---:|"])
    for metric, r in summary["comparison"].items():
        def fmt(value: float | None) -> str:
            return f"{value:+.2f}%" if value is not None else "N/A (zero reference)"
        lines.append(f"| {metric} | {fmt(r['protected_vs_baseline_percent'])} | {fmt(r['protected_vs_instrumented_percent'])} |")
    lines.extend(["", "## Reproducibility", "",
        f"- Yosys: `{summary['tools']['yosys']}`",
        f"- sv2v: `{summary['tools']['sv2v']}`",
        f"- RTL source hashes match the Phase 5 historical manifest: **{summary['historical_rtl_verified']}**",
        f"- Git revision: `{summary['git_commit']}`",
        "- Scripts, complete cell types, logs, and mapped JSON netlists are in this output directory.",
        "- FPGA primitive counts depend on tool versions, optimization, flags and architecture.",
        "- `LUT1`–`LUT6` here count mapped LUT primitives, not placed FPGA slice utilization.",
        "- No design was placed, routed, timed, powered, loaded onto an FPGA, or subjected to a physical fault attack.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("build/reproduction/phase10d"))
    args = parser.parse_args()
    out = validate_out_dir(args.out_dir)
    yosys, sv2v = shutil.which("yosys"), shutil.which("sv2v")
    if not yosys or not sv2v:
        raise RuntimeError("Both yosys and sv2v are required: brew install yosys sv2v")
    versions = {"yosys": tool_version(yosys, ["-V"]), "sv2v": tool_version(sv2v, ["--numeric-version"])}
    if versions["sv2v"] != EXPECTED_SV2V:
        raise RuntimeError(f"Expected sv2v {EXPECTED_SV2V}, got {versions['sv2v']!r}")
    historical = json.loads((ROOT / "reports/phase5/manifest.json").read_text())
    hashes = source_hashes()
    verify_historical_rtl_hashes(hashes, historical)
    out.mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)
    (out / "netlists").mkdir(exist_ok=True)
    measurements: dict[str, dict] = {}
    for label, (top, filenames) in DESIGNS.items():
        verilog_path = out / "netlists" / f"{label}_sv2v.v"
        output = run_logged([sv2v, *(str(ROOT / "rtl" / f) for f in filenames)],
                            out / "logs" / f"{label}_sv2v.log", timeout=180)
        verilog_path.write_text(output)
        mapped = out / "netlists" / f"{label}_xc7.json"
        script = yosys_script(top, verilog_path, mapped)
        run_logged([yosys, "-Q", "-T", "-p", script],
                   out / "logs" / f"{label}_yosys.log", timeout=1200)
        cells = count_primitives(json.loads(mapped.read_text()), top)
        measurements[label] = {"top_module": top, **cells}
        print(f"{label}: {cells['lut_total']} LUTs, {cells['flip_flops']} FFs, "
              f"{cells['carry4']} CARRY4, {cells['bram18']+cells['bram36']} BRAM cells")
    git = shutil.which("git")
    head = "unavailable"
    if git:
        p = subprocess.run([git, "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        if p.returncode == 0:
            head = p.stdout.strip()
    summary = {
        "experiment": "phase10d_xilinx_7series_out_of_context",
        "target_family": ARCHITECTURE,
        "board_reference": "Digilent Nexys 4 DDR / Xilinx Artix-7 XC7A100T (not selected as a synthesis part)",
        "scope": "XC7 LUT/FF/CARRY/BRAM/DSP primitive estimates; no placement, routing, timing, power, physical tests",
        "command": "sv2v; hierarchy -check; synth_xilinx -top TOP -family xc7 -flatten -noiopad -noclkbuf; check -assert; stat -tech xilinx; write_json",
        "tools": versions,
        "git_commit": head,
        "source_sha256": hashes,
        "historical_rtl_verified": True,
        "architectures": measurements,
        "comparison": build_comparison(measurements),
    }
    (out / "fpga_resources.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (out / "fpga_resources.csv").open("w") as handle:
        import csv
        columns = ["design", "lut_total", "flip_flops", "carry4", "muxf7", "muxf8", "bram18", "bram36", "dsp48", "srl", "distributed_ram"]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for label in DESIGNS:
            row = measurements[label]
            writer.writerow({"design": label, **{f: row[f] for f in columns if f != "design"}})
    (out / "manifest.json").write_text(json.dumps({
        "utc_time": datetime.now(timezone.utc).isoformat(),
        "git_commit": head,
        "yosys": versions["yosys"],
        "sv2v": versions["sv2v"],
        "target_family": "xc7",
        "synthesis_options": list(FLOW_FLAGS),
        "source_sha256": hashes,
    }, indent=2) + "\n")
    (out / "REPORT.md").write_text(make_report(summary))
    print(f"PASS: Phase 10D mapped FPGA resource report: {out / 'REPORT.md'}")


if __name__ == "__main__":
    main()
