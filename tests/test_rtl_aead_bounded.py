"""Compare encrypt-only bounded RTL AEAD with the verified Python NIST reference.

No code is copied from the Python AEAD into RTL: the Python reference generates
expected ciphertext/tag values that the compiled SystemVerilog must match.
"""
import random
import shutil
import subprocess
from pathlib import Path

from reference.ascon_aead import encrypt


def _as_sv_hex(data: bytes) -> str:
    return f"{int.from_bytes(data.ljust(16, bytes(1)), 'little'):032x}"


def test_verilator_bounded_aead_matches_python(tmp_path):
    verilator = shutil.which("verilator")
    assert verilator, "Verilator is required: brew install verilator"

    root = Path(__file__).resolve().parents[1]
    rng = random.Random(20261012)
    vectors = tmp_path / "aead_bounded_vectors.txt"
    lengths = [(ad, msg) for ad in range(17) for msg in range(17)]
    lengths += [(rng.randrange(17), rng.randrange(17)) for _ in range(48)]
    lines = []

    for index, (ad_len, msg_len) in enumerate(lengths):
        key = bytes(range(16)) if index == 0 else rng.randbytes(16)
        nonce = bytes(range(16, 32)) if index == 0 else rng.randbytes(16)
        associated_data = rng.randbytes(ad_len)
        plaintext = rng.randbytes(msg_len)
        sealed = encrypt(key, nonce, plaintext, associated_data)
        ciphertext, tag = sealed[:-16], sealed[-16:]
        lines.append(" ".join([
            _as_sv_hex(key), _as_sv_hex(nonce), str(ad_len),
            _as_sv_hex(associated_data), str(msg_len),
            _as_sv_hex(plaintext), _as_sv_hex(ciphertext), _as_sv_hex(tag),
        ]))

    vectors.write_text("\n".join(lines) + "\n", encoding="ascii")
    build_dir = tmp_path / "obj_dir"
    build = subprocess.run(
        [
            verilator, "--binary", "--timing", "-j", "4", "-Wno-fatal",
            "--top-module", "tb_ascon_aead_encrypt_bounded",
            "--Mdir", str(build_dir),
            str(root / "rtl/ascon_round.sv"),
            str(root / "rtl/ascon_permutation.sv"),
            str(root / "rtl/ascon_aead_encrypt_bounded.sv"),
            str(root / "tb/tb_ascon_aead_encrypt_bounded.sv"),
        ],
        capture_output=True, text=True, timeout=120,
    )
    assert build.returncode == 0, build.stdout + "\n" + build.stderr
    exe = build_dir / "Vtb_ascon_aead_encrypt_bounded"
    run = subprocess.run(
        [str(exe), f"+VECTORS={vectors}"],
        capture_output=True, text=True, timeout=75,
    )
    assert run.returncode == 0, run.stdout + "\n" + run.stderr
    assert f"PASS: {len(lines)} bounded AEAD encryptions" in run.stdout, run.stdout
