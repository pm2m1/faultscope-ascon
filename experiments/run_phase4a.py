"""Reproducible bounded Ascon RTL single-bit fault campaign.

Example:
    uv run python experiments/run_phase4a.py --out reports/phase4a.csv

An RTL-instrumented pre-round state-bit flip is compared to a Python fault
model. All cases are replayed fault-free first. No security-bypass verdicts
are produced: output changes are not equivalent to tag-verification bypass.
"""
import argparse
import csv
import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from reference.ascon_aead import encrypt
from reference.ascon_fault_model import FaultSpec, encrypt_with_fault

ROOT = Path(__file__).resolve().parents[1]
PHASES = (0, 1, 2, 3, 4)


def as_sv_hex(data: bytes) -> str:
    if len(data) > 16:
        raise ValueError("bounded vector field too long")
    return f"{int.from_bytes(data.ljust(16, b'\x00'), 'little'):032x}"


def generate_cases() -> list[tuple[bytes, bytes, bytes, bytes, FaultSpec]]:
    rng = random.Random(20261012)
    cases = []

    def add(ad_len: int, msg_len: int, spec: FaultSpec) -> None:
        cases.append((rng.randbytes(16), rng.randbytes(16),
                      rng.randbytes(ad_len), rng.randbytes(msg_len), spec))

    # All structurally present phases and their absent-path negatives.
    for ad_len, msg_len in ((0, 0), (1, 1), (15, 15), (16, 16),
                            (0, 16), (16, 0)):
        for phase in PHASES:
            add(ad_len, msg_len, FaultSpec(True, phase, 0, 319))

    # Phase, round and bit sweeps (including each final round).
    for phase in PHASES:
        rounds = 12 if phase in (0, 4) else 8
        for round_index in range(rounds):
            add(16, 16, FaultSpec(True, phase, round_index,
                                  (round_index * 67 + phase * 31) % 320))

    # Disabled fault and deliberately unreachable configurations.
    for phase in PHASES:
        add(16, 16, FaultSpec(False, phase, 0, 0))
        add(16, 16, FaultSpec(True, phase, 15, 0))
        add(16, 16, FaultSpec(True, phase, 0, 320))

    # Additional random conditions, including absence of some phases.
    for _ in range(42):
        ad_len, msg_len = rng.randrange(17), rng.randrange(17)
        phase = rng.choice(PHASES)
        rounds = 12 if phase in (0, 4) else 8
        add(ad_len, msg_len,
            FaultSpec(True, phase, rng.randrange(rounds), rng.randrange(320)))

    return cases


def write_vectors(path: Path, cases) -> None:
    lines = []
    for key, nonce, ad, pt, spec in cases:
        sealed = encrypt(key, nonce, pt, ad)
        faulty, hit = encrypt_with_fault(key, nonce, pt, ad, spec)
        lines.append(" ".join([
            as_sv_hex(key), as_sv_hex(nonce), str(len(ad)), as_sv_hex(ad),
            str(len(pt)), as_sv_hex(pt), as_sv_hex(sealed[:-16]),
            as_sv_hex(sealed[-16:]), str(int(spec.enable)), str(spec.phase),
            str(spec.round), str(spec.bit), str(int(hit)),
            as_sv_hex(faulty[:-16]), as_sv_hex(faulty[-16:]),
        ]))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def run_campaign(workdir: Path) -> list[dict]:
    verilator = shutil.which("verilator")
    if verilator is None:
        raise RuntimeError("Verilator executable is required")
    workdir.mkdir(parents=True, exist_ok=True)
    cases = generate_cases()
    vectors = workdir / "fault_vectors.txt"
    write_vectors(vectors, cases)
    build_dir = workdir / "obj_dir"
    build = subprocess.run(
        [
            verilator, "--binary", "--timing", "-j", "4", "-Wno-fatal",
            "--top-module", "tb_ascon_fault_campaign", "--Mdir", str(build_dir),
            str(ROOT / "rtl/ascon_round.sv"),
            str(ROOT / "rtl/ascon_permutation_faultable.sv"),
            str(ROOT / "rtl/ascon_aead_encrypt_faultable.sv"),
            str(ROOT / "tb/tb_ascon_fault_campaign.sv"),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if build.returncode != 0:
        raise AssertionError(build.stdout + "\n" + build.stderr)
    exe = build_dir / "Vtb_ascon_fault_campaign"
    run = subprocess.run(
        [str(exe), f"+VECTORS={vectors}"],
        capture_output=True, text=True, timeout=120,
    )
    if run.returncode != 0:
        raise AssertionError(run.stdout + "\n" + run.stderr)
    if f"PASS: {len(cases)} bounded fault-injection comparisons" not in run.stdout:
        raise AssertionError("Missing success marker:\n" + run.stdout)

    rows = []
    keys = ["case", "ad_len", "msg_len", "armed", "phase", "round",
            "bit", "injected", "ciphertext_changed", "tag_changed", "cycles"]
    for line in run.stdout.splitlines():
        if not line.startswith("RESULT "):
            continue
        parts = line.split()
        if len(parts) != len(keys) + 1:
            raise AssertionError("Malformed RESULT line: " + line)
        row = dict(zip(keys, map(int, parts[1:])))
        if row["case"] != len(rows):
            raise AssertionError("Missing or duplicate case: " + line)
        rows.append(row)
    if len(rows) != len(cases):
        raise AssertionError(f"Expected {len(cases)} result rows, got {len(rows)}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("reports/phase4a.csv"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="faultscope-") as td:
        rows = run_campaign(Path(td))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    hits = sum(row["injected"] for row in rows)
    changes = sum(row["ciphertext_changed"] or row["tag_changed"] for row in rows)
    print(f"PASS: {len(rows)} campaigns, {hits} injections, "
          f"{changes} output changes; CSV: {args.out}")
    print("NOTE: Differences in encryption outputs do not establish authentication bypass.")


if __name__ == "__main__":
    main()
