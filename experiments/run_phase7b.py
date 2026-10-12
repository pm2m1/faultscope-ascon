"""Phase 7B adversarial bounded AEAD encryption *RTL-observed* campaign.

Verilator is a hard dependency: this script never substitutes model-only rows.
CLI: uv run python -m experiments.run_phase7b --out reports/phase7b_aead.csv
"""
import argparse
import csv
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from reference.ascon_aead_adversarial_model import (
    AeadAdversarialSpec, evaluate_aead,
)
from reference.ascon_adversarial_model import AdversarialSpec

ROOT = Path(__file__).resolve().parents[1]

# Includes no AD, full AD (extra padding permutation), partial AD,
# no message, full message (extra p[8]), and partial message.
LENGTH_PAIRS = (
    (0, 0), (0, 16), (16, 0), (16, 16), (1, 1),
    (15, 15), (8, 7), (7, 8), (16, 8), (8, 16),
)
SCENARIOS = (
    "clean", "first_only", "replay_only", "dual_identical",
    "dual_different", "checkpoint_shared", "checkpoint_replay",
    "suppress_replay_alarm", "suppress_first_alarm",
    "first_invalid_bit", "replay_invalid_round", "checkpoint_invalid_bit",
)


def make_fault(name: str, round_index: int, bit: int, rounds: int) -> AdversarialSpec:
    a = dict(first_round=round_index, first_bit=bit,
             replay_round=round_index, replay_bit=bit, checkpoint_bit=bit)
    if name == "first_only":
        a["first_arm"] = True
    elif name == "replay_only":
        a["replay_arm"] = True
    elif name == "dual_identical":
        a["first_arm"] = a["replay_arm"] = True
    elif name == "dual_different":
        a.update(first_arm=True, replay_arm=True,
                 replay_round=(round_index + 1) % rounds, replay_bit=(bit + 37) % 320)
    elif name == "checkpoint_shared":
        a["checkpoint_mode"] = 1
    elif name == "checkpoint_replay":
        a["checkpoint_mode"] = 2
    elif name == "suppress_replay_alarm":
        a.update(replay_arm=True, suppress_alarm=True)
    elif name == "suppress_first_alarm":
        a.update(first_arm=True, suppress_alarm=True)
    elif name == "first_invalid_bit":
        a.update(first_arm=True, first_bit=320)
    elif name == "replay_invalid_round":
        a.update(replay_arm=True, replay_round=15)
    elif name == "checkpoint_invalid_bit":
        a.update(checkpoint_mode=2, checkpoint_bit=320)
    elif name != "clean":
        raise ValueError(name)
    return AdversarialSpec(**a)


def cases_for_phase7b() -> list[dict]:
    rng = random.Random(20261013)
    cases = []
    for pair_index, (al, ml) in enumerate(LENGTH_PAIRS):
        key = rng.randbytes(16)
        nonce = rng.randbytes(16)
        ad = rng.randbytes(al)
        message = rng.randbytes(ml)
        for phase in range(5):
            rounds = 12 if phase in (0, 4) else 8
            r = (0, rounds - 1, rounds // 2)[pair_index % 3]
            bit = (0, 319, 64, 127, 255, 1, 92, 314, 197, 311)[pair_index]
            for scenario in SCENARIOS:
                attack = AeadAdversarialSpec(True, phase, make_fault(scenario, r, bit, rounds))
                cases.append({"scenario": scenario, "phase": phase, "key": key,
                              "nonce": nonce, "ad": ad, "plaintext": message,
                              "attack": attack})
    assert len(cases) == 600
    return cases


def h128(data: bytes) -> str:
    return f"{int.from_bytes(data, 'little'):032x}"


def write_vectors(path: Path, cases: list[dict]) -> None:
    rows = []
    for c in cases:
        spec = c["attack"].fault
        obs = evaluate_aead(c["key"], c["nonce"], c["plaintext"], c["ad"], c["attack"])
        # 28 fixed-width/decimal fields, no scenario strings for robust SV fscanf.
        row = (
            h128(c["key"]), h128(c["nonce"]), len(c["ad"]), h128(c["ad"]),
            len(c["plaintext"]), h128(c["plaintext"]), c["phase"], int(c["attack"].enabled),
            int(spec.first_arm), spec.first_round, spec.first_bit,
            int(spec.replay_arm), spec.replay_round, spec.replay_bit,
            spec.checkpoint_mode, spec.checkpoint_bit, int(spec.suppress_alarm),
            h128(obs.golden_ciphertext), h128(obs.golden_tag),
            int(obs.first_fired), int(obs.replay_fired), int(obs.checkpoint_fired),
            int(obs.raw_mismatch), int(obs.alarm), int(obs.valid),
            h128(obs.ciphertext), h128(obs.tag), int(obs.incorrect_release),
        )
        assert len(row) == 28
        rows.append(" ".join(map(str, row)))
    path.write_text("\n".join(rows) + "\n", encoding="ascii")


def run_campaign(workdir: Path) -> list[dict]:
    verilator = shutil.which("verilator")
    if verilator is None:
        raise RuntimeError("Verilator required for Phase 7B; model-only results are not substituted")
    workdir.mkdir(parents=True, exist_ok=True)
    cases = cases_for_phase7b()
    vector_path = workdir / "phase7b_vectors.txt"
    write_vectors(vector_path, cases)
    obj_dir = workdir / "obj_dir"
    cmd = [
        verilator, "--binary", "--timing", "-j", "4", "-Wno-fatal",
        "--top-module", "tb_ascon_aead_adversarial", "--Mdir", str(obj_dir),
        str(ROOT / "rtl/ascon_round.sv"),
        str(ROOT / "rtl/ascon_permutation_faultable.sv"),
        str(ROOT / "rtl/ascon_permutation_adversarial.sv"),
        str(ROOT / "rtl/ascon_aead_encrypt_adversarial.sv"),
        str(ROOT / "tb/tb_ascon_aead_adversarial.sv"),
    ]
    build = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if build.returncode:
        raise AssertionError("Verilator build error:\n" + build.stdout + "\n" + build.stderr)
    sim = subprocess.run(
        [str(obj_dir / "Vtb_ascon_aead_adversarial"), f"+VECTORS={vector_path}"],
        capture_output=True, text=True, timeout=180,
    )
    if sim.returncode:
        raise AssertionError("Verilator simulation error:\n" + sim.stdout + "\n" + sim.stderr)
    if f"PASS: {len(cases)} bounded AEAD adversarial comparisons" not in sim.stdout:
        raise AssertionError("RTL completion marker missing:\n" + sim.stdout)

    fields = ("case", "first_fired", "replay_fired", "checkpoint_fired",
              "raw_mismatch", "alarm", "valid", "incorrect_release", "cycles")
    rows = []
    for line in sim.stdout.splitlines():
        if not line.startswith("RESULT "):
            continue
        values = line.split()[1:]
        if len(values) != len(fields):
            raise AssertionError(f"Malformed Verilator result: {line}")
        datum = dict(zip(fields, map(int, values)))
        i = datum.pop("case")
        if i != len(rows) or i >= len(cases):
            raise AssertionError(f"Unordered or out of range RTL case {i}")
        c = cases[i]
        obs = evaluate_aead(c["key"], c["nonce"], c["plaintext"], c["ad"], c["attack"])
        for field, exp in (
            ("first_fired", obs.first_fired), ("replay_fired", obs.replay_fired),
            ("checkpoint_fired", obs.checkpoint_fired), ("raw_mismatch", obs.raw_mismatch),
            ("alarm", obs.alarm), ("valid", obs.valid),
            ("incorrect_release", obs.incorrect_release),
        ):
            if datum[field] != int(exp):
                raise AssertionError(f"RTL result differs from software model at case {i} field {field}")
        rows.append({"case": i, "scenario": c["scenario"], "phase": c["phase"],
                     "ad_len": len(c["ad"]), "msg_len": len(c["plaintext"]),
                     **datum})
    if len(rows) != len(cases):
        raise AssertionError(f"Got {len(rows)} RTL result rows, expected {len(cases)}")
    return rows


def summarize(rows: list[dict]) -> dict:
    return {"cases": len(rows), "raw_mismatches": sum(r["raw_mismatch"] for r in rows),
            "alarms": sum(r["alarm"] for r in rows),
            "incorrect_releases": sum(r["incorrect_release"] for r in rows),
            "first_events": sum(r["first_fired"] for r in rows),
            "replay_events": sum(r["replay_fired"] for r in rows),
            "checkpoint_events": sum(r["checkpoint_fired"] for r in rows)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/phase7b_aead.csv"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="faultscope-phase7b-") as tmp:
        rows = run_campaign(Path(tmp))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    stats = summarize(rows)
    print("PASS: {cases} AEAD adversarial simulations; raw mismatches={raw_mismatches}, "
          "alarms={alarms}, incorrect releases={incorrect_releases}".format(**stats))
    print("CSV:", args.out)
    print("LIMITATION: modeled RTL hooks and encryption result validity only; "
          "not physical faults, decryption, or authentication bypass.")


if __name__ == "__main__":
    main()
