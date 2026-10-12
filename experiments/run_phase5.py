"""Phase 5: reproducible generic-cell synthesis and Phase 4B latency analysis.

Requires Homebrew Yosys and sv2v; input CSV from the verified Phase 4B
simulation. This is technology-independent RTL synthesis, NOT ASIC area,
FPGA LUT/timing/power, or post-route evidence.

    uv run python -m experiments.run_phase5 \\
        --campaign reports/phase4b_temporal.csv --out-dir reports/phase5
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import statistics
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Identical synthesis settings for all three implementations.
# - baseline: no fault hardware
# - instrumented: fault controls but no defense
# - protected: fault controls and temporal recomputation
DESIGNS = {
    "baseline": (
        "ascon_aead_encrypt_bounded",
        ["ascon_round.sv", "ascon_permutation.sv", "ascon_aead_encrypt_bounded.sv"],
    ),
    "instrumented": (
        "ascon_aead_encrypt_faultable",
        ["ascon_round.sv", "ascon_permutation_faultable.sv", "ascon_aead_encrypt_faultable.sv"],
    ),
    "protected": (
        "ascon_aead_encrypt_temporal",
        ["ascon_round.sv", "ascon_permutation_faultable.sv", "ascon_permutation_temporal.sv", "ascon_aead_encrypt_temporal.sv"],
    ),
}

REQUIRED_CAMPAIGN_COLUMNS = {
    "case", "ad_len", "msg_len", "injected", "detected", "valid",
    "baseline_cycles", "protected_cycles", "faulted_cycles",
}


def is_sequential(cell_type: str) -> bool:
    """Recognize Yosys simple FF/latch cells, and higher-level FF variants."""
    normalized = cell_type.lower()
    return ("dff" in normalized or "latch" in normalized or
            normalized.startswith("$_ff_") or normalized in {"$ff", "$sr"})


def cell_stats(netlist: dict, top: str) -> dict:
    modules = netlist.get("modules", {})
    if top not in modules:
        raise ValueError(f"Synthesized top {top!r} missing from netlist; found {list(modules)}")
    cells = modules[top].get("cells", {})
    types = Counter(str(cell["type"]) for cell in cells.values())
    # A hierarchical submodule here would invalidate the top-only cell count.
    unresolved = [name for name in types if name in modules and name != top]
    if unresolved:
        raise ValueError(f"Netlist is not fully flattened: {unresolved}")
    seq_cells = [cell for cell in cells.values() if is_sequential(str(cell["type"]))]
    # After 'synth -noabc', FFs are normally mapped to 1-bit $_DFF* cells.
    # We inspect Q widths rather than assume that mapping is always single-bit.
    seq_bits = sum(len(cell.get("connections", {}).get("Q", [])) for cell in seq_cells)
    return {
        "total_cells": len(cells),
        "sequential_cells": len(seq_cells),
        "sequential_q_bits": seq_bits,
        "combinational_cells": len(cells) - len(seq_cells),
        "cell_types": dict(sorted(types.items())),
    }


def run_command(cmd: list[str], log_path: Path, timeout: int = 300) -> str:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    log_path.write_text(
        "$ " + " ".join(cmd) + "\n\n" + p.stdout + "\n" + p.stderr,
        encoding="utf-8",
    )
    if p.returncode != 0:
        tail = (p.stdout + "\n" + p.stderr)[-3500:]
        raise RuntimeError(f"Command failed (exit {p.returncode}); see {log_path}\n{tail}")
    return p.stdout


def tool_version(executable: str, args: list[str]) -> str:
    p = subprocess.run([executable, *args], capture_output=True, text=True, timeout=20)
    return (p.stdout or p.stderr).strip().splitlines()[0] if p.returncode == 0 else "unknown"


def source_hashes() -> dict[str, str]:
    names = sorted({filename for _, paths in DESIGNS.values() for filename in paths})
    return {
        name: hashlib.sha256((ROOT / "rtl" / name).read_bytes()).hexdigest()
        for name in names
    }


def synthesize_all(out_dir: Path) -> tuple[dict[str, dict], dict]:
    yosys = shutil.which("yosys")
    sv2v = shutil.which("sv2v")
    missing = [name for name, path in (("yosys", yosys), ("sv2v", sv2v)) if not path]
    if missing:
        raise RuntimeError(
            f"Missing synthesis tool(s): {', '.join(missing)}. "
            "On macOS run: brew install yosys sv2v"
        )

    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    (out_dir / "netlists").mkdir(parents=True, exist_ok=True)
    measurements: dict[str, dict] = {}
    for label, (top, source_names) in DESIGNS.items():
        source_files = [str(ROOT / "rtl" / name) for name in source_names]
        converted = out_dir / "netlists" / f"{label}.v"
        conversion_log = out_dir / "logs" / f"{label}_sv2v.log"
        verilog = run_command([sv2v, *source_files], conversion_log)
        converted.write_text(verilog, encoding="utf-8")

        netlist_path = out_dir / "netlists" / f"{label}.json"
        yosys_script = (
            f"read_verilog {converted.resolve()}; "
            f"hierarchy -check -top {top}; "
            f"synth -top {top} -flatten -noabc; "
            f"check -assert; "
            f"write_json {netlist_path.resolve()}"
        )
        run_command(
            [yosys, "-Q", "-T", "-p", yosys_script],
            out_dir / "logs" / f"{label}_yosys.log",
        )
        netlist = json.loads(netlist_path.read_text(encoding="utf-8"))
        measurements[label] = {"top": top, **cell_stats(netlist, top)}
        print(f"{label}: {measurements[label]['total_cells']} generic cells, "
              f"{measurements[label]['sequential_q_bits']} FF output bits")

    manifest = {
        "utc_time": datetime.now(timezone.utc).isoformat(),
        "yosys": tool_version(yosys, ["-V"]),
        "sv2v": tool_version(sv2v, ["--numeric-version"]),
        "flow": "sv2v; Yosys hierarchy -check; synth -flatten -noabc; check -assert; write_json",
        "sources_sha256": source_hashes(),
        "scope": "RTL generic gate/FF-cell counts, not physical area, LUTs, timing or power",
    }
    git = shutil.which("git")
    if git:
        p = subprocess.run([git, "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        manifest["git_commit"] = p.stdout.strip() if p.returncode == 0 else "unavailable"
    reference_commit_file = ROOT / "docs" / "ascon_reference_commit.txt"
    if reference_commit_file.exists():
        manifest["ascon_reference_commit"] = reference_commit_file.read_text(encoding="utf-8").strip()
    return measurements, manifest


def read_campaign(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Phase 4B campaign is missing: {path}. Generate it first with "
            "uv run python -m experiments.run_phase4b --out reports/phase4b_temporal.csv"
        )
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = set(reader.fieldnames or [])
        if not REQUIRED_CAMPAIGN_COLUMNS <= fields:
            raise ValueError(f"Campaign missing columns: {sorted(REQUIRED_CAMPAIGN_COLUMNS - fields)}")
        rows = [{key: int(value) for key, value in raw.items() if key in fields and value != ""}
                for raw in reader]
    if not rows:
        raise ValueError("Campaign CSV is empty")
    seen = [row["case"] for row in rows]
    if seen != list(range(len(rows))):
        raise ValueError("Campaign case IDs must be sequential and begin at zero")
    for r in rows:
        if r["injected"] not in (0, 1) or r["detected"] not in (0, 1) or r["valid"] not in (0, 1):
            raise ValueError(f"Invalid binary field for case {r['case']}")
        if min(r["baseline_cycles"], r["protected_cycles"]) <= 0:
            raise ValueError(f"Nonpositive cycle count in case {r['case']}")
    return rows


def percentile_nearest(values: list[int], percentile: float) -> int:
    return sorted(values)[max(0, math.ceil(percentile * len(values)) - 1)]


def campaign_stats(rows: list[dict]) -> dict:
    hit = sum(r["injected"] for r in rows)
    detected = sum(r["injected"] and r["detected"] for r in rows)
    alarms_without_injection = sum(not r["injected"] and r["detected"] for r in rows)
    non_injected = len(rows) - hit
    baseline = [r["baseline_cycles"] for r in rows]
    protected = [r["protected_cycles"] for r in rows]
    phase_data: dict[str, dict] = {}
    phases = sorted({r.get("phase", -1) for r in rows})
    for phase in phases:
        subset = [r for r in rows if r.get("phase", -1) == phase]
        applied = sum(r["injected"] for r in subset)
        phase_data[str(phase)] = {
            "cases": len(subset),
            "injected": applied,
            "detected": sum(r["injected"] and r["detected"] for r in subset),
        }
    return {
        "cases": len(rows),
        "applied_faults": hit,
        "detected_faults": detected,
        "coverage_percent": (100 * detected / hit) if hit else None,
        "unfaulted_cases": non_injected,
        "false_alarms": alarms_without_injection,
        "false_alarm_rate_percent": (100 * alarms_without_injection / non_injected) if non_injected else None,
        "fail_closed_violations": sum(r["detected"] and r["valid"] for r in rows),
        "mean_baseline_cycles": statistics.mean(baseline),
        "mean_protected_cycles": statistics.mean(protected),
        "mean_overhead_cycles": statistics.mean(p - b for p, b in zip(protected, baseline)),
        "relative_mean_latency_increase_percent": 100 * (statistics.mean(protected) / statistics.mean(baseline) - 1),
        "min_baseline_cycles": min(baseline),
        "max_baseline_cycles": max(baseline),
        "p95_baseline_cycles": percentile_nearest(baseline, .95),
        "min_protected_cycles": min(protected),
        "max_protected_cycles": max(protected),
        "p95_protected_cycles": percentile_nearest(protected, .95),
        "phases": phase_data,
    }


def change_percent(base: int, new: int) -> float | None:
    return (100 * (new / base - 1)) if base else None


def write_synthesis_csv(path: Path, measurements: dict[str, dict]) -> None:
    rows = []
    for label, metrics in measurements.items():
        rows.append({"design": label,
                     "top_module": metrics["top"],
                     "total_generic_cells": metrics["total_cells"],
                     "sequential_cells": metrics["sequential_cells"],
                     "sequential_Q_bits": metrics["sequential_q_bits"],
                     "combinational_cells": metrics["combinational_cells"]})
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def make_markdown(stats: dict, measurements: dict[str, dict], manifest: dict, campaign: Path) -> str:
    header = [
        "# FaultScope-Ascon — Phase 5 synthesis/latency report",
        "",
        "## Scope and reproducibility",
        "",
        "- Model: single transient pre-round state-bit flip in first permutation execution; clean replay/checkpoint/comparator.",
        "- RTL: encryption and tag generation only, 0–16 bytes of plaintext and associated data.",
        f"- Phase 4B CSV input: `{campaign}`",
        f"- Git HEAD at analysis: `{manifest.get('git_commit', 'unavailable')}`",
        f"- Yosys: `{manifest['yosys']}`; sv2v: `{manifest['sv2v']}`",
        f"- Synthesis: `{manifest['flow']}`",
        "",
        "## Fault security and cycle overhead (from Verilator CSV)",
        "",
        "| Metric | Observed |",
        "|---|---:|",
        f"| Campaign scenarios | {stats['cases']} |",
        f"| Applied fault events | {stats['applied_faults']} |",
        f"| Detected applied faults | {stats['detected_faults']} |",
        f"| Coverage in *this model* | {stats['coverage_percent']:.2f}% |" if stats['coverage_percent'] is not None else "| Coverage | N/A |",
        f"| False alarms / no-injection cases | {stats['false_alarms']} / {stats['unfaulted_cases']} |",
        f"| False alarm rate among no-injection cases | {stats['false_alarm_rate_percent']:.2f}% |" if stats['false_alarm_rate_percent'] is not None else "| False alarm rate | N/A |",
        f"| Alarm-and-valid policy violations | {stats['fail_closed_violations']} |",
        f"| Mean baseline cycles | {stats['mean_baseline_cycles']:.2f} |",
        f"| Mean protected cycles | {stats['mean_protected_cycles']:.2f} |",
        f"| Mean additional cycles | {stats['mean_overhead_cycles']:.2f} |",
        f"| Relative increase in mean cycles | {stats['relative_mean_latency_increase_percent']:.2f}% |",
        f"| Baseline p95 cycles | {stats['p95_baseline_cycles']} |",
        f"| Protected p95 cycles | {stats['p95_protected_cycles']} |",
        "",
        "## Generic synthesis resources (Yosys, identical flow)",
        "",
        "| Design | Total generic cells | FF Q bits | Combinational cells |",
        "|---|---:|---:|---:|",
    ]
    for label in ("baseline", "instrumented", "protected"):
        m = measurements[label]
        header.append(f"| {label} | {m['total_cells']:,} | {m['sequential_q_bits']:,} | {m['combinational_cells']:,} |")
    baseline = measurements["baseline"]
    instrumented = measurements["instrumented"]
    protected = measurements["protected"]
    header += [
        "",
        "| Comparison | Generic cell change | FF Q bit change |",
        "|---|---:|---:|",
        f"| Protected vs baseline | {change_percent(baseline['total_cells'], protected['total_cells']):+.2f}% | {change_percent(baseline['sequential_q_bits'], protected['sequential_q_bits']):+.2f}% |",
        f"| Protected vs instrumented | {change_percent(instrumented['total_cells'], protected['total_cells']):+.2f}% | {change_percent(instrumented['sequential_q_bits'], protected['sequential_q_bits']):+.2f}% |",
        "",
        "The *baseline* has no injection ports. The *instrumented* comparison helps separate fault-injection circuitry from the added temporal-replay defense, but these are distinct RTL architectures, not isolated gate-by-gate additions.",
        "",
        "## Interpretation limits",
        "",
        "- Generic cell counts are synthesis-configuration-dependent **structural proxies**, NOT silicon area in mm², FPGA LUTs, power consumption, or a maximum clock frequency.",
        "- The mean-cycle ratio does not imply a clock-frequency ratio; no timing analysis or place-and-route was performed.",
        "- No physical fault testing, replay-fault injection, checkpoint tampering, comparator bypass, or authenticated decryption security evaluation was performed.",
        "- A fault effect observed during encryption is not evidence of AEAD authentication bypass.",
        "- Detection for a single pre-round state bit flip with an unfaulted replay is expected for a bijective permutation. This does not establish resistance to realistic correlated attacks.",
        "- Preserve the manifest, individual synthesis logs, per-design converted Verilog and JSON netlists alongside the CSV for auditability.",
        "",
    ]
    return "\n".join(header)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--campaign", type=Path, default=Path("reports/phase4b_temporal.csv"))
    p.add_argument("--out-dir", type=Path, default=Path("reports/phase5"))
    args = p.parse_args()
    campaign = args.campaign.resolve()
    rows = read_campaign(campaign)
    stats = campaign_stats(rows)
    if stats["fail_closed_violations"]:
        raise RuntimeError("Fail-closed policy violated; investigate before reporting coverage")
    if stats["applied_faults"] and stats["detected_faults"] > stats["applied_faults"]:
        raise RuntimeError("Detected count cannot exceed applied fault count")
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    measurements, manifest = synthesize_all(out_dir)
    manifest["campaign_sha256"] = hashlib.sha256(campaign.read_bytes()).hexdigest()
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (out_dir / "synthesis_summary.json").write_text(json.dumps(measurements, indent=2) + "\n", encoding="utf-8")
    (out_dir / "campaign_summary.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    write_synthesis_csv(out_dir / "synthesis_summary.csv", measurements)
    (out_dir / "REPORT.md").write_text(make_markdown(stats, measurements, manifest, campaign) + "\n", encoding="utf-8")
    print(f"PASS: Phase 5 reports written to {out_dir}")
    print(f"Applied faults {stats['applied_faults']}, detections {stats['detected_faults']}, "
          f"false alarms {stats['false_alarms']}")
    print(f"Mean cycles baseline={stats['mean_baseline_cycles']:.2f}, "
          f"protected={stats['mean_protected_cycles']:.2f}, "
          f"overhead={stats['relative_mean_latency_increase_percent']:.2f}%")
    print(f"Read: {out_dir / 'REPORT.md'}")


if __name__ == "__main__":
    main()
