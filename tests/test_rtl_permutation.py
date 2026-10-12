"""Build and test SystemVerilog p[8] and p[12] with Verilator.

Run: uv run python -m pytest tests/test_rtl_permutation.py -v
"""
import random
import shutil
import subprocess
from pathlib import Path

from reference.ascon_permutation import MASK64, ascon_permutation


def test_verilator_permutation_matches_python(tmp_path):
    verilator = shutil.which("verilator")
    assert verilator, "Verilator is required: brew install verilator"

    root = Path(__file__).resolve().parents[1]
    vectors = tmp_path / "permutation_vectors.txt"
    rng = random.Random(20261012)
    lines = []

    for rounds in (8, 12):
        states = [
            (0, 0, 0, 0, 0),
            (1, 2, 3, 4, 5),
            (MASK64,) * 5,
        ]
        states += [tuple(rng.getrandbits(64) for _ in range(5))
                   for _ in range(100)]

        for state in states:
            expected = ascon_permutation(state, rounds)
            words = [*state, *expected]
            lines.append(str(rounds) + " " + " ".join(
                f"{word:016x}" for word in words
            ))

    vectors.write_text("\n".join(lines) + "\n", encoding="ascii")

    build_dir = tmp_path / "obj_dir"
    build = subprocess.run(
        [
            verilator, "--binary", "--timing", "-j", "4", "-Wno-fatal",
            "--top-module", "tb_ascon_permutation", "--Mdir", str(build_dir),
            str(root / "rtl/ascon_round.sv"),
            str(root / "rtl/ascon_permutation.sv"),
            str(root / "tb/tb_ascon_permutation.sv"),
        ],
        capture_output=True, text=True,
    )
    assert build.returncode == 0, build.stdout + "\n" + build.stderr

    executable = build_dir / "Vtb_ascon_permutation"
    run = subprocess.run(
        [str(executable), f"+VECTORS={vectors}"],
        capture_output=True, text=True,
        timeout=45,
    )
    assert run.returncode == 0, run.stdout + "\n" + run.stderr
    assert f"PASS: {len(lines)} RTL permutations" in run.stdout, run.stdout
