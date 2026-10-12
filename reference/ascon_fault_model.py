"""Controlled, single-bit transient faults in a bounded Ascon-AEAD128 model.

Research/testing code only.  Injects before a selected permutation round,
not into a physical circuit.  Validated using the official KAT-tested Python
Ascon permutation and the reference AEAD outputs for fault-disabled runs.
"""
from dataclasses import dataclass

from reference.ascon_aead import encrypt
from reference.ascon_permutation import ROUND_CONSTANTS, ascon_round

RATE = 16
IV = 0x00001000808C0001
PHASE_NAMES = {
    0: "initialization",
    1: "associated_data",
    2: "associated_data_full_padding",
    3: "full_plaintext_block",
    4: "finalization",
}


@dataclass(frozen=True)
class FaultSpec:
    enable: bool
    phase: int
    round: int
    bit: int


def _words(data: bytes) -> tuple[int, int]:
    return int.from_bytes(data[:8], "little"), int.from_bytes(data[8:16], "little")


def _rate(s: list[int]) -> bytes:
    return s[0].to_bytes(8, "little") + s[1].to_bytes(8, "little")


def _xor_rate(s: list[int], block: bytes) -> None:
    a, b = _words(block)
    s[0] ^= a
    s[1] ^= b


def _perm(s: list[int], count: int, phase: int, fault: FaultSpec) -> bool:
    """Mutate state through permutation; return true iff injection fired."""
    hit = False
    for ri, constant in enumerate(ROUND_CONSTANTS[12 - count:]):
        if (fault.enable and fault.phase == phase and ri == fault.round
                and 0 <= fault.bit < 320):
            lane = 4 - fault.bit // 64  # RTL state = {x0,x1,x2,x3,x4}
            s[lane] ^= 1 << (fault.bit % 64)
            hit = True
        s[:] = ascon_round(tuple(s), constant)
    return hit


def encrypt_with_fault(
    key: bytes, nonce: bytes, plaintext: bytes, ad: bytes, fault: FaultSpec
) -> tuple[bytes, bool]:
    """Return ciphertext||tag and whether a configured fault reached its target.

    Supports bounded 0..16-byte plaintext and associated data, matching RTL.
    A disabled or unreachable fault leaves the result equal to standard AEAD.
    """
    if len(key) != 16 or len(nonce) != 16:
        raise ValueError("key and nonce must contain 16 bytes")
    if len(plaintext) > 16 or len(ad) > 16:
        raise ValueError("bounded model supports at most 16 bytes")

    k0, k1 = _words(key)
    n0, n1 = _words(nonce)
    s = [IV, k0, k1, n0, n1]
    applied = _perm(s, 12, 0, fault)
    s[3] ^= k0
    s[4] ^= k1

    if ad:
        if len(ad) == RATE:
            _xor_rate(s, ad)
            applied |= _perm(s, 8, 1, fault)
            _xor_rate(s, b"\x01" + bytes(15))
            applied |= _perm(s, 8, 2, fault)
        else:
            padded = ad + b"\x01" + bytes(15 - len(ad))
            _xor_rate(s, padded)
            applied |= _perm(s, 8, 1, fault)

    s[4] ^= 1 << 63

    if len(plaintext) == RATE:
        out = bytes(a ^ b for a, b in zip(plaintext, _rate(s)))
        _xor_rate(s, plaintext)
        applied |= _perm(s, 8, 3, fault)
        s[0] ^= 1
    else:
        out = bytes(a ^ b for a, b in zip(plaintext, _rate(s)))
        padded = plaintext + b"\x01" + bytes(15 - len(plaintext))
        _xor_rate(s, padded)

    s[2] ^= k0
    s[3] ^= k1
    applied |= _perm(s, 12, 4, fault)
    s[3] ^= k0
    s[4] ^= k1
    result = out + s[3].to_bytes(8, "little") + s[4].to_bytes(8, "little")
    if not applied:
        assert result == encrypt(key, nonce, plaintext, ad)
    return result, applied
