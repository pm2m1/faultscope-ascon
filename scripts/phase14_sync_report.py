"""Fail-closed Phase 14 mapped synchronizer audit. No Vivado execution.

The audit checks 5 mapped FFs and three direct FF->FF chains; no metastability
MTBF or external UART/reset signoff is inferred from passing this script.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

EXPECTED_STAGES = {"reset": (0, 1, 2), "rx": (0, 1)}
EXPECTED_EDGES = {("reset", 0, 1), ("reset", 1, 2), ("rx", 0, 1)}
PORTS = {"clk", "rst_n", "uart_rx_i", "uart_tx_o", "led_busy_o", "led_alarm_o"}


def table(folder: Path, name: str, fields: set[str]) -> list[dict[str, str]]:
    path = folder / name
    if not path.is_file():
        raise ValueError(f"Missing audit file: {name}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f, delimiter="\t")
        if not r.fieldnames or set(r.fieldnames) != fields:
            raise ValueError(f"Malformed column set in {name}")
        rows = list(r)
    if any(None in row or any(v is None or not v.strip() for v in row.values()) for row in rows):
        raise ValueError(f"Malformed or empty cells in {name}")
    return rows


def inspect(folder: Path) -> dict:
    folder = Path(folder)
    issues: list[str] = []
    cells = table(folder, "cells.tsv", {"group", "stage", "cell", "ref_name", "async_reg", "shreg_extract", "loc", "bel"})
    edges = table(folder, "edges.tsv", {"group", "from_stage", "to_stage", "from_cell", "to_cell", "net_overlap", "status"})
    ports = table(folder, "ports.tsv", {"port", "direction"})
    context = table(folder, "context.tsv", {"key", "value"})
    ctx = {r["key"]: r["value"] for r in context}
    if len(ctx) != len(context) or ctx.get("top") not in {"faultscope_uart_top", "checkpoint_post_route"}:
        issues.append("Unexpected top or duplicate context key")
    if ctx.get("clock_count") != "1" or ctx.get("clock_source") != "BUFGCTRL_X0Y0":
        issues.append("Missing expected OOC clock/context")
    try:
        if float(ctx.get("period_ns", "nan")) != 10.0:
            issues.append("Unexpected OOC clock period")
    except ValueError:
        issues.append("Clock period unparsable")
    if not ctx.get("vivado_version", "").strip() or ctx["vivado_version"] == "-":
        issues.append("Vivado version missing")
    if len(ports) != 6 or {r["port"] for r in ports} != PORTS:
        issues.append("Top-level signal set differs from six-port UART top")
    portdirs = {r["port"]: r["direction"].upper() for r in ports}
    if any(portdirs.get(p) != "IN" for p in ("clk", "rst_n", "uart_rx_i")) or any(portdirs.get(p) != "OUT" for p in ("uart_tx_o", "led_busy_o", "led_alarm_o")):
        # Vivado DIRECTION returns IN / OUT for ports.
        issues.append("Top-level port directions incorrect")

    expected = {(group, i) for group, inds in EXPECTED_STAGES.items() for i in inds}
    found = []
    for c in cells:
        try:
            pair = (c["group"], int(c["stage"]))
        except ValueError:
            issues.append("Unparseable synchronizer stage")
            continue
        found.append(pair)
        if not c["ref_name"].upper().startswith("FD"):
            issues.append(f"{pair}: mapped cell is not a Xilinx FF")
        if c["async_reg"].strip().upper() not in {"TRUE", "1"}:
            issues.append(f"{pair}: ASYNC_REG is not TRUE")
        if c["loc"] == "-" or c["bel"] == "-":
            issues.append(f"{pair}: register lacks a physical LOC/BEL")
        # SHREG_EXTRACT is a synthesis directive and may be dropped as a
        # netlist property; explicit FF cells establish non-SRL mapping.
    if set(found) != expected or len(found) != len(expected):
        issues.append(f"Missing, unexpected, or duplicated synchronizer stages: {found}")

    found_edges = []
    cells_by_name = {c["cell"] for c in cells}
    for e in edges:
        try:
            pair = (e["group"], int(e["from_stage"]), int(e["to_stage"]))
        except ValueError:
            issues.append("Unparseable stage edge")
            continue
        found_edges.append(pair)
        if e["status"] != "DIRECT" or e["net_overlap"] == "-":
            issues.append(f"{pair}: FF-to-FF connection not independently established")
        if e["from_cell"] not in cells_by_name or e["to_cell"] not in cells_by_name:
            issues.append(f"{pair}: edge references unrecognized FF")
    if set(found_edges) != EXPECTED_EDGES or len(found_edges) != len(EXPECTED_EDGES):
        issues.append("Missing, duplicated or unexpected stage connections")
    report = {
        "phase": "14", "scope": "mapped post-route synchronizer structure only",
        "verdict": "PASS" if not issues else "NOT_VERIFIED",
        "issues": issues, "rtl_stages_expected": 5, "mapped_stages_found": len(cells),
        "required_direct_edges": 3, "edges_found": len(edges),
        "vivado_version": ctx.get("vivado_version"), "period_ns": ctx.get("period_ns"),
        "board_io_timing": "NOT VERIFIED", "uart_metastability_mtbf": "NOT VERIFIED",
        "reset_recovery_removal_and_board_power_up": "NOT VERIFIED",
    }
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("audit_dir", type=Path)
    p.add_argument("--require-pass", action="store_true")
    args = p.parse_args()
    try:
        result = inspect(args.audit_dir)
    except (ValueError, OSError, KeyError) as exc:
        result = {"phase": "14", "verdict": "NOT_VERIFIED", "issues": [str(exc)]}
    print(json.dumps(result, indent=2))
    if args.require_pass and result["verdict"] != "PASS":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
