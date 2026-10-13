"""Compare new Yosys synthesis with historical metrics without rewriting evidence.

Historical measurements are immutable. Metadata-only $scopeinfo entries are not
logic resources. Tool-version differences are reported, never silently treated
as functional RTL regressions or proof of equivalent physical implementations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGNS = ("baseline", "instrumented", "protected")
METADATA_CELLS = frozenset({"$scopeinfo"})


def logic_metrics(entry: dict) -> dict:
    """Derive corrected resource counts from a Phase 5-compatible JSON entry."""
    types = entry["cell_types"]
    if not isinstance(types, dict) or not types:
        raise ValueError("Synthesis entry must include cell_types")
    if any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in types.values()):
        raise ValueError("Invalid cell-type counts")
    total = entry["total_cells"]
    if sum(types.values()) != total:
        raise ValueError("cell_types total disagrees with total_cells")
    sequential = entry["sequential_cells"]
    bits = entry["sequential_q_bits"]
    if not (0 <= sequential <= total and bits >= sequential):
        raise ValueError("Invalid sequential resource count")
    metadata = sum(n for name, n in types.items() if name.lower() in METADATA_CELLS)
    if sequential > total - metadata:
        raise ValueError("Sequential count cannot exceed logic-cell count")
    return {
        "reported_cells_including_metadata": total,
        "metadata_cells_excluded": metadata,
        "logic_cells": total - metadata,
        "sequential_cells": sequential,
        "sequential_q_bits": bits,
        "combinational_logic_cells": total - metadata - sequential,
    }


def percent_increase(new: int, base: int) -> float:
    if base <= 0:
        raise ValueError("Cannot compare with zero/negative baseline")
    return round(100 * (new / base - 1), 4)


def build_comparison(current: dict, historical: dict, current_manifest: dict,
                     historical_manifest: dict, root: Path = ROOT) -> dict:
    # If the RTL differs, this is no longer a tool-only reproducibility comparison.
    for name, digest in historical_manifest["sources_sha256"].items():
        actual = hashlib.sha256((root / "rtl" / name).read_bytes()).hexdigest()
        if actual != digest or current_manifest["sources_sha256"].get(name) != digest:
            raise ValueError(f"RTL source hash differs from historical manifest: {name}")
    if current_manifest["flow"] != historical_manifest["flow"]:
        raise ValueError("Synthesis flow differs from historical flow")
    measured, old = {}, {}
    for name in DESIGNS:
        measured[name] = logic_metrics(current[name])
        old[name] = logic_metrics(historical[name])
    return {
        "interpretation": (
            "Technology-independent Yosys logic-cell/FF comparison only; no LUT, "
            "timing, power, area, or security guarantee. Tool-version changes can change counts."
        ),
        "tools": {
            "current": {"yosys": current_manifest["yosys"], "sv2v": current_manifest["sv2v"]},
            "historical": {"yosys": historical_manifest["yosys"], "sv2v": historical_manifest["sv2v"]},
        },
        "same_synthesis_flow_and_RTL_hashes": True,
        "current": measured,
        "historical_corrected": old,
        "relative_overhead_percent": {
            "protected_vs_baseline": percent_increase(measured["protected"]["logic_cells"], measured["baseline"]["logic_cells"]),
            "protected_vs_instrumented": percent_increase(measured["protected"]["logic_cells"], measured["instrumented"]["logic_cells"]),
        },
        "tool_environment_delta_logic_cells": {
            name: measured[name]["logic_cells"] - old[name]["logic_cells"] for name in DESIGNS
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("build/reproduction/phase10b"))
    args = parser.parse_args()
    out_dir = args.out_dir.resolve()
    current = json.loads((out_dir / "synthesis_summary.json").read_text())
    current_manifest = json.loads((out_dir / "manifest.json").read_text())
    historical = json.loads((ROOT / "reports/phase5/synthesis_summary.json").read_text())
    historical_manifest = json.loads((ROOT / "reports/phase5/manifest.json").read_text())
    comparison = build_comparison(current, historical, current_manifest, historical_manifest)
    (out_dir / "phase10b_comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    print("RTL hashes and synthesis flow agree with pinned historical evidence.")
    print("Tool versions: current", comparison["tools"]["current"])
    print("Tool versions: historical", comparison["tools"]["historical"])
    for name in DESIGNS:
        print(name, comparison["current"][name])
    print("Corrected logic-cell overhead (%):", comparison["relative_overhead_percent"])
    print("Historical cell-count differences (not automatic regressions):", comparison["tool_environment_delta_logic_cells"])
    print("Wrote", out_dir / "phase10b_comparison.json")


if __name__ == "__main__":
    main()
