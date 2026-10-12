"""Educational Ascon-AEAD128 implementation (NIST SP 800-232).

The API returns ciphertext || 16-byte authentication tag.
For research and RTL verification, not production secret storage.
"""

import hmac

from reference.ascon_permutation import ascon_permutation

RATE = 16
KEY_SIZE = 16
NONCE_SIZE = 16
TAG_SIZE = 16
IV = 0x00001000808C0001


def _validate(key: bytes, nonce: bytes) -> None:
    if not isinstance(key, bytes) or len(key) != KEY_SIZE:
        raise ValueError("key must be exactly 16 bytes")
    if not isinstance(nonce, bytes) or len(nonce) != NONCE_SIZE:
        raise ValueError("nonce must be exactly 16 bytes")


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def _rate_bytes(state: list[int]) -> bytes:
    return state[0].to_bytes(8, "little") + state[1].to_bytes(8, "little")


def _set_rate(state: list[int], block: bytes) -> None:
    assert len(block) == RATE
    state[0] = int.from_bytes(block[:8], "little")
    state[1] = int.from_bytes(block[8:], "little")


def _initialize(key: bytes, nonce: bytes) -> tuple[list[int], int, int]:
    k0, k1 = (int.from_bytes(key[i:i + 8], "little") for i in (0, 8))
    n0, n1 = (int.from_bytes(nonce[i:i + 8], "little") for i in (0, 8))
    state = list(ascon_permutation((IV, k0, k1, n0, n1), 12))
    state[3] ^= k0
    state[4] ^= k1
    return state, k0, k1


def _absorb_ad(state: list[int], associated_data: bytes) -> None:
    if associated_data:
        offset = 0
        while offset + RATE <= len(associated_data):
            block = associated_data[offset:offset + RATE]
            _set_rate(state, _xor(_rate_bytes(state), block))
            state[:] = ascon_permutation(tuple(state), 8)
            offset += RATE
        tail = associated_data[offset:]
        padded = tail + b"\x01" + bytes(RATE - len(tail) - 1)
        _set_rate(state, _xor(_rate_bytes(state), padded))
        state[:] = ascon_permutation(tuple(state), 8)

    # NIST little-endian domain-separation bit.
    state[4] ^= 1 << 63


def _finalize(state: list[int], k0: int, k1: int) -> bytes:
    state[2] ^= k0
    state[3] ^= k1
    state[:] = ascon_permutation(tuple(state), 12)
    state[3] ^= k0
    state[4] ^= k1
    return state[3].to_bytes(8, "little") + state[4].to_bytes(8, "little")


def encrypt(key: bytes, nonce: bytes, plaintext: bytes, associated_data: bytes = b"") -> bytes:
    """Encrypt and authenticate; return ciphertext || tag."""
    _validate(key, nonce)
    if not isinstance(plaintext, bytes) or not isinstance(associated_data, bytes):
        raise TypeError("plaintext and associated_data must be bytes")

    state, k0, k1 = _initialize(key, nonce)
    _absorb_ad(state, associated_data)
    output = bytearray()
    offset = 0
    while offset + RATE <= len(plaintext):
        block = plaintext[offset:offset + RATE]
        cipher_block = _xor(block, _rate_bytes(state))
        output.extend(cipher_block)
        _set_rate(state, cipher_block)
        state[:] = ascon_permutation(tuple(state), 8)
        offset += RATE

    tail = plaintext[offset:]
    rate = bytearray(_rate_bytes(state))
    output.extend(_xor(tail, rate[:len(tail)]))
    for i, byte in enumerate(tail):
        rate[i] ^= byte
    rate[len(tail)] ^= 0x01  # Required padding, even for empty tail.
    _set_rate(state, bytes(rate))
    output.extend(_finalize(state, k0, k1))
    return bytes(output)


def decrypt(key: bytes, nonce: bytes, ciphertext_and_tag: bytes, associated_data: bytes = b"") -> bytes:
    """Verify tag before returning plaintext; raise ValueError if invalid."""
    _validate(key, nonce)
    if not isinstance(ciphertext_and_tag, bytes) or not isinstance(associated_data, bytes):
        raise TypeError("ciphertext_and_tag and associated_data must be bytes")
    if len(ciphertext_and_tag) < TAG_SIZE:
        raise ValueError("ciphertext must include a 16-byte authentication tag")

    ciphertext, supplied_tag = ciphertext_and_tag[:-TAG_SIZE], ciphertext_and_tag[-TAG_SIZE:]
    state, k0, k1 = _initialize(key, nonce)
    _absorb_ad(state, associated_data)
    plaintext = bytearray()
    offset = 0
    while offset + RATE <= len(ciphertext):
        block = ciphertext[offset:offset + RATE]
        plaintext.extend(_xor(block, _rate_bytes(state)))
        _set_rate(state, block)
        state[:] = ascon_permutation(tuple(state), 8)
        offset += RATE

    tail = ciphertext[offset:]
    rate = bytearray(_rate_bytes(state))
    plaintext.extend(_xor(tail, rate[:len(tail)]))
    rate[:len(tail)] = tail
    rate[len(tail)] ^= 0x01
    _set_rate(state, bytes(rate))

    calculated_tag = _finalize(state, k0, k1)
    if not hmac.compare_digest(calculated_tag, supplied_tag):
        raise ValueError("Authentication failed")
    return bytes(plaintext)
