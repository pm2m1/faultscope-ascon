"""Phase 4B: temporal recomputation countermeasure simulation and comparison.

The attack model is a *single* transient pre-round state-bit flip in the
first permutation execution only. The replay and comparator are assumed
unfaulted. The resulting detection coverage is limited to this model.

Usage:
    uv run python -m experiments.run_phase4b --out reports/phase4b_temporal.csv
"""
import argparse
import csv
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from experiments.run_phase4a import as_sv_hex, generate_cases
from reference.ascon_aead import encrypt
from reference.ascon_fault_model import FaultSpec, encrypt_with_fault

ROOT = Path(__file__).resolve().parents[1]


def cases_for_protection():
    cases = list(generate_cases())
    rng = random.Random(20261013)
    # Include every 0..16-length combination in the clean, no-fault path.
    for ad_len in range(17):
        for msg_len in range(17):
            cases.append((
                rng.randbytes(16), rng.randbytes(16),
                rng.randbytes(ad_len), rng.randbytes(msg_len),
                FaultSpec(False, 4, 0, 0),
            ))
    return cases


def write_vectors(path: Path, cases):
    lines = []
    hits = 0
    for key, nonce, ad, msg, spec in cases:
        sealed = encrypt(key, nonce, msg, ad)
        _, hit = encrypt_with_fault(key, nonce, msg, ad, spec)
        hits += int(hit)
        lines.append(" ".join((
            as_sv_hex(key), as_sv_hex(nonce), str(len(ad)), as_sv_hex(ad),
            str(len(msg)), as_sv_hex(msg), as_sv_hex(sealed[:-16]),
            as_sv_hex(sealed[-16:]), str(int(spec.enable)),
            str(spec.phase), str(spec.round), str(spec.bit), str(int(hit)),
        )))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return hits


def run_campaign(workdir: Path):
    verilator = shutil.which("verilator")
    if not verilator:
        raise RuntimeError("Verilator is required; install it before running Phase 4B")
    workdir.mkdir(parents=True, exist_ok=True)
    cases = cases_for_protection()
    vector_file = workdir / "temporal_vectors.txt"
    expected_hits = write_vectors(vector_file, cases)
    build_dir = workdir / "obj_dir"
    cmd = [
        verilator, "--binary", "--timing", "-j", "4", "-Wno-fatal",
        "--top-module", "tb_ascon_temporal_campaign", "--Mdir", str(build_dir),
        str(ROOT / "rtl/ascon_round.sv"),
        str(ROOT / "rtl/ascon_permutation.sv"),
        str(ROOT / "rtl/ascon_aead_encrypt_bounded.sv"),
        str(ROOT / "rtl/ascon_permutation_faultable.sv"),
        str(ROOT / "rtl/ascon_permutation_temporal.sv"),
        str(ROOT / "rtl/ascon_aead_encrypt_temporal.sv"),
        str(ROOT / "tb/tb_ascon_temporal_campaign.sv"),
    ]
    build = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if build.returncode != 0:
        raise AssertionError("Verilator build failed:\n" + build.stdout + "\n" + build.stderr)
    exe = build_dir / "Vtb_ascon_temporal_campaign"
    run = subprocess.run(
        [str(exe), f"+VECTORS={vector_file}"],
        capture_output=True, text=True, timeout=180,
    )
    if run.returncode != 0:
        raise AssertionError("RTL simulation failed:\n" + run.stdout + "\n" + run.stderr)
    if f"PASS: {len(cases)} protected AEAD comparisons" not in run.stdout:
        raise AssertionError("RTL completion marker missing:\n" + run.stdout)
    keys = (
        "case", "ad_len", "msg_len", "armed", "phase", "round", "bit",
        "injected", "detected", "valid", "baseline_cycles",
        "protected_cycles", "faulted_cycles",
    )
    rows = []
    for line in run.stdout.splitlines():
        if not line.startswith("RESULT "):
            continue
        fields = line.split()
        if len(fields) != len(keys) + 1:
            raise AssertionError("Malformed RESULT line: " + line)
        row = dict(zip(keys, map(int, fields[1:])))
        if row["case"] != len(rows):
            raise AssertionError("Missing/duplicated case: " + line)
        if row["detected"] != row["injected"]:
            raise AssertionError("Observed detection disagrees with fault model")
        if row["valid"] != (1 - row["detected"]):
            raise AssertionError("Fail-closed policy inconsistency")
        if row["protected_cycles"] <= row["baseline_cycles"]:
            raise AssertionError("Expected latency overhead")
        rows.append(row)
    if len(rows) != len(cases):
        raise AssertionError(f"Expected {len(cases)} rows, observed {len(rows)}")
    assert sum(r["injected"] for r in rows) == expected_hits
    return rows


def summarize(rows):
    injected = sum(r["injected"] for r in rows)
    detected = sum(r["detected"] and r["injected"] for r in rows)
    false_alarms = sum(r["detected"] and not r["injected"] for r in rows)
    return {
        "campaigns": len(rows),
        "injections": injected,
        "detections": detected,
        "false_alarms": false_alarms,
        "coverage_percent": (100.0 * detected / injected) if injected else None,
        "mean_baseline_cycles": sum(r["baseline_cycles"] for r in rows) / len(rows),
        "mean_protected_cycles": sum(r["protected_cycles"] for r in rows) / len(rows),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=Path("reports/phase4b_temporal.csv"))
    args = p.parse_args()
    with tempfile.TemporaryDirectory(prefix="faultscope-temporal-") as temp:
        rows = run_campaign(Path(temp))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    stats = summarize(rows)
    print("PASS: {campaigns} scenarios, {injections} applied faults, "
          "{detections} alarms, {false_alarms} false alarms".format(**stats))
    print("Coverage in this SINGLE-FAULT, CLEAN-REPLAY model: "
          f"{stats['coverage_percent']:.2f}%")
    print("Mean cycles: baseline={mean_baseline_cycles:.2f}, protected={mean_protected_cycles:.2f}".format(**stats))
    print("CSV:", args.out)
    print("LIMITATION: no physical fault resistance, compromised-replay coverage, "
          "or authenticated-decryption bypass claim.")


if __name__ == "__main__":
    main()
