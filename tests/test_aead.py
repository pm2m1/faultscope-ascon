"""Validate educational Ascon-AEAD128 against the official NIST KAT file.

Run from project root with: uv run python -m pytest tests/test_aead.py -v
"""

from pathlib import Path

import pytest

from reference.ascon_aead import decrypt, encrypt

KAT_PATH = (
    Path(__file__).resolve().parents[1]
    / "references/ascon-c/crypto_aead/asconaead128/LWC_AEAD_KAT_128_128.txt"
)


def _load_official_vectors():
    if not KAT_PATH.is_file():
        pytest.fail(f"Official KAT file is missing: {KAT_PATH}")

    records = []
    for block in KAT_PATH.read_text(encoding="utf-8").strip().split("\n\n"):
        fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
        expected_keys = {"Count", "Key", "Nonce", "PT", "AD", "CT"}
        assert set(fields) == expected_keys, f"Unexpected KAT fields: {fields}"
        records.append(
            (
                int(fields["Count"]),
                bytes.fromhex(fields["Key"]),
                bytes.fromhex(fields["Nonce"]),
                bytes.fromhex(fields["PT"]),
                bytes.fromhex(fields["AD"]),
                bytes.fromhex(fields["CT"]),
            )
        )
    assert len(records) == 1089, f"Expected 1089 official vectors, got {len(records)}"
    return records


def test_all_official_known_answer_vectors():
    for count, key, nonce, pt, ad, expected_ct_and_tag in _load_official_vectors():
        actual = encrypt(key, nonce, pt, ad)
        assert actual == expected_ct_and_tag, f"Encryption KAT failed: Count = {count}"
        decrypted = decrypt(key, nonce, expected_ct_and_tag, ad)
        assert decrypted == pt, f"Decryption KAT failed: Count = {count}"


@pytest.mark.parametrize("length", [0, 1, 7, 8, 15, 16, 17, 31, 32, 33, 48, 64])
def test_roundtrip_multiple_lengths(length):
    key = bytes(range(16))
    nonce = bytes(range(16, 32))
    msg = bytes(range(length))
    ad = bytes(range(length))
    sealed = encrypt(key, nonce, msg, ad)
    assert len(sealed) == length + 16
    assert decrypt(key, nonce, sealed, ad) == msg


@pytest.mark.parametrize("length", [0, 1, 16, 17, 32])
def test_tampering_rejected(length):
    key = bytes(range(16))
    nonce = bytes(range(16, 32))
    msg = bytes(range(length))
    ad = b"header"
    sealed = encrypt(key, nonce, msg, ad)

    bad_tag = bytearray(sealed)
    bad_tag[-1] ^= 1
    with pytest.raises(ValueError, match="Authentication failed"):
        decrypt(key, nonce, bytes(bad_tag), ad)

    if length:
        bad_cipher = bytearray(sealed)
        bad_cipher[0] ^= 1
        with pytest.raises(ValueError, match="Authentication failed"):
            decrypt(key, nonce, bytes(bad_cipher), ad)

    with pytest.raises(ValueError, match="Authentication failed"):
        decrypt(key, nonce, sealed, b"different header")

    with pytest.raises(ValueError, match="Authentication failed"):
        decrypt(key, bytes(16), sealed, ad)


@pytest.mark.parametrize("size", [0, 15])
def test_invalid_ciphertext_size_rejected(size):
    with pytest.raises(ValueError, match="16-byte authentication tag"):
        decrypt(bytes(16), bytes(16), bytes(size))


def test_invalid_key_or_nonce_rejected():
    with pytest.raises(ValueError, match="key"):
        encrypt(bytes(15), bytes(16), b"")
    with pytest.raises(ValueError, match="nonce"):
        encrypt(bytes(16), bytes(15), b"")
