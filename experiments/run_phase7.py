"""Phase 7A adversarial permutation-level temporal recomputation campaign.

The injected conditions are *RTL simulation hooks*; this is not a physical
attack test and does not test AEAD tag verification or acceptance.

Usage:
  uv run python -m experiments.run_phase7 --out reports/phase7_adversarial.csv
"""
import argparse
import csv
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from reference.ascon_adversarial_model import AdversarialSpec, evaluate

ROOT = Path(__file__).resolve().parents[1]


def cases_for_adversarial() -> list[tuple[str, int, int, AdversarialSpec]]:
    """Deterministic cases exercising each distinct fault and detection mechanism."""
    rng = random.Random(20261013)
    cases = []
    scenarios = (
        ("clean", lambda r, b: AdversarialSpec()),
        ("first_only", lambda r, b: AdversarialSpec(first_arm=True, first_round=r, first_bit=b)),
        ("replay_only", lambda r, b: AdversarialSpec(replay_arm=True, replay_round=r, replay_bit=b)),
        ("dual_identical", lambda r, b: AdversarialSpec(
            first_arm=True, first_round=r, first_bit=b,
            replay_arm=True, replay_round=r, replay_bit=b)),
        ("dual_different", lambda r, b: AdversarialSpec(
            first_arm=True, first_round=r, first_bit=b,
            replay_arm=True, replay_round=(r + 1) % 8, replay_bit=(b + 37) % 320)),
        ("checkpoint_shared", lambda r, b: AdversarialSpec(checkpoint_mode=1, checkpoint_bit=b)),
        ("checkpoint_replay", lambda r, b: AdversarialSpec(checkpoint_mode=2, checkpoint_bit=b)),
        ("suppress_replay_alarm", lambda r, b: AdversarialSpec(
            replay_arm=True, replay_round=r, replay_bit=b, suppress_alarm=True)),
        ("suppress_first_alarm", lambda r, b: AdversarialSpec(
            first_arm=True, first_round=r, first_bit=b, suppress_alarm=True)),
        ("first_invalid_bit", lambda r, b: AdversarialSpec(first_arm=True, first_round=r, first_bit=320)),
        ("replay_invalid_round", lambda r, b: AdversarialSpec(replay_arm=True, replay_round=15, replay_bit=b)),
        ("checkpoint_invalid_bit", lambda r, b: AdversarialSpec(checkpoint_mode=2, checkpoint_bit=320)),
    )
    seeds = [0, (1 << 320) - 1, int("0123456789abcdef" * 5, 16)]
    seeds.extend(rng.getrandbits(320) for _ in range(7))
    for rounds in (8, 12):
        for index, state in enumerate(seeds):
            round_idx = [0, rounds - 1, rounds // 2][index % 3]
            bit = [0, 319, 64, 127, 255, 1, 92, 314, 197, 311][index]
            for name, constructor in scenarios:
                spec = constructor(round_idx, bit)
                # Make the different-fault replay index valid for both p[8] and p[12].
                cases.append((name, rounds, state, spec))
    return cases


def write_vectors(path: Path, cases: list) -> None:
    lines = []
    for name, rounds, state, spec in cases:
        obs = evaluate(state, rounds, spec)
        lines.append(" ".join(map(str, (
            rounds, f"{state:080x}",
            int(spec.first_arm), spec.first_round, spec.first_bit,
            int(spec.replay_arm), spec.replay_round, spec.replay_bit,
            spec.checkpoint_mode, spec.checkpoint_bit, int(spec.suppress_alarm),
            f"{obs.golden:080x}",
            int(obs.first_fired), int(obs.replay_fired), int(obs.checkpoint_fired),
            int(obs.raw_mismatch), int(obs.alarm), int(obs.valid),
            f"{obs.output:080x}", int(obs.silent_corruption),
        ))))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def run_campaign(workdir: Path) -> list[dict]:
    verilator = shutil.which("verilator")
    if verilator is None:
        raise RuntimeError("Verilator executable required for Phase 7 RTL verification")
    workdir.mkdir(parents=True, exist_ok=True)
    cases = cases_for_adversarial()
    vector_path = workdir / "phase7_vectors.txt"
    write_vectors(vector_path, cases)
    obj_dir = workdir / "obj_dir"
    cmd = [
        verilator, "--binary", "--timing", "-j", "4", "-Wno-fatal",
        "--top-module", "tb_ascon_temporal_adversarial", "--Mdir", str(obj_dir),
        str(ROOT / "rtl/ascon_round.sv"),
        str(ROOT / "rtl/ascon_permutation_faultable.sv"),
        str(ROOT / "rtl/ascon_permutation_adversarial.sv"),
        str(ROOT / "tb/tb_ascon_temporal_adversarial.sv"),
    ]
    build = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if build.returncode:
        raise AssertionError("Verilator build failure:\n" + build.stdout + "\n" + build.stderr)
    run = subprocess.run(
        [str(obj_dir / "Vtb_ascon_temporal_adversarial"), f"+VECTORS={vector_path}"],
        capture_output=True, text=True, timeout=180,
    )
    if run.returncode:
        raise AssertionError("Verilator simulation failure:\n" + run.stdout + "\n" + run.stderr)
    if f"PASS: {len(cases)} adversarial temporal permutations" not in run.stdout:
        raise AssertionError("RTL completion marker missing:\n" + run.stdout)

    fields = ["case", "rounds", "first_fired", "replay_fired", "checkpoint_fired",
              "raw_mismatch", "alarm", "valid", "silent_corruption", "cycles"]
    rows = []
    for line in run.stdout.splitlines():
        if not line.startswith("RESULT "):
            continue
        parts = line.split()
        if len(parts) != len(fields) + 1:
            raise AssertionError("Malformed RESULT: " + line)
        result = dict(zip(fields, map(int, parts[1:])))
        if result["case"] != len(rows):
            raise AssertionError("Missing or duplicate case number")
        scenario, rounds, state, spec = cases[len(rows)]
        result["scenario"] = scenario
        result["first_round"] = spec.first_round
        result["first_bit"] = spec.first_bit
        result["replay_round"] = spec.replay_round
        result["replay_bit"] = spec.replay_bit
        result["checkpoint_mode"] = spec.checkpoint_mode
        result["checkpoint_bit"] = spec.checkpoint_bit
        result["suppress_alarm"] = int(spec.suppress_alarm)
        rows.append(result)
    if len(rows) != len(cases):
        raise AssertionError(f"Expected {len(cases)} rows, observed {len(rows)}")
    return rows


def summarize(rows: list[dict]) -> dict:
    total = len(rows)
    return {
        "cases": total,
        "raw_mismatches": sum(r["raw_mismatch"] for r in rows),
        "alarms": sum(r["alarm"] for r in rows),
        "silent_corruptions": sum(r["silent_corruption"] for r in rows),
        "replay_fault_events": sum(r["replay_fired"] for r in rows),
        "checkpoint_fault_events": sum(r["checkpoint_fired"] for r in rows),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/phase7_adversarial.csv"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="faultscope-phase7-") as temp:
        rows = run_campaign(Path(temp))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = summarize(rows)
    print("PASS: {cases} permutation-level adversarial cases; "
          "raw mismatches={raw_mismatches}, alarms={alarms}, "
          "silent corruptions={silent_corruptions}".format(**result))
    print("CSV:", args.out)
    print("LIMITATION: simulated hooks, not physical faults or an AEAD authentication bypass.")


if __name__ == "__main__":
    main()
