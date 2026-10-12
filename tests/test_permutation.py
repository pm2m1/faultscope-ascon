
from pathlib import Path
import random
import shutil
import subprocess

import pytest

from reference.ascon_permutation import MASK64, ascon_permutation


if shutil.which("clang") is None:
    pytest.skip("clang is required for permutation tests", allow_module_level=True)


@pytest.fixture(scope="session")
def c_oracle(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    output = tmp_path_factory.mktemp("ascon") / "oracle"

    reference_dir = (
        root / "references/ascon-c/"
        "crypto_aead/asconaead128/ref"
    )

    subprocess.run(
        [
            "clang",
            "-O2",
            f"-I{reference_dir}",
            str(root / "tb/permutation_oracle.c"),
            "-o",
            str(output),
        ],
        check=True,
    )

    return output


@pytest.mark.parametrize("rounds", [8, 12])
def test_python_matches_official_c(c_oracle, rounds):
    rng = random.Random(20261012)

    states = [
        (0, 0, 0, 0, 0),
        (1, 2, 3, 4, 5),
        (MASK64,) * 5,
    ]

    for _ in range(100):
        states.append(
            tuple(rng.getrandbits(64) for _ in range(5))
        )

    inputs = "\n".join(
        f"{rounds} " + " ".join(f"{x:016x}" for x in state)
        for state in states
    ) + "\n"

    process = subprocess.run(
        [str(c_oracle)],
        input=inputs,
        text=True,
        capture_output=True,
        check=True,
    )

    lines = process.stdout.strip().splitlines()
    assert len(lines) == len(states)

    for state, line in zip(states, lines):
        expected = tuple(int(x, 16) for x in line.split())
        actual = ascon_permutation(state, rounds)

        assert actual == expected
