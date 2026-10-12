"""Phase 7B software oracle for adversarial *bounded AEAD encryption*.

Research-only hook semantics are inherited from Phase 7A.  An alarm makes
ciphertext/tag invalid and externally zero.  The oracle does not model physical
faults, receiver-side authentication acceptance, or persistent compromises.
"""
from dataclasses import dataclass

from reference.ascon_aead import IV, RATE, encrypt
from reference.ascon_adversarial_model import (
    AdversarialSpec, evaluate, pack_state, unpack_state,
)


@dataclass(frozen=True)
class AeadAdversarialSpec:
    enabled: bool = False
    phase: int = 0
    fault: AdversarialSpec = AdversarialSpec()


@dataclass(frozen=True)
class AeadObservation:
    ciphertext: bytes
    tag: bytes
    golden_ciphertext: bytes
    golden_tag: bytes
    first_fired: bool
    replay_fired: bool
    checkpoint_fired: bool
    raw_mismatch: bool
    alarm: bool
    valid: bool

    @property
    def incorrect_release(self) -> bool:
        return self.valid and (
            self.ciphertext != self.golden_ciphertext or self.tag != self.golden_tag
        )

    @property
    def fail_closed(self) -> bool:
        return self.alarm and not self.valid and self.ciphertext == b"" and self.tag == bytes(16)


def evaluate_aead(
    key: bytes, nonce: bytes, plaintext: bytes, associated_data: bytes,
    spec: AeadAdversarialSpec,
) -> AeadObservation:
    if len(key) != 16 or len(nonce) != 16:
        raise ValueError("Key and nonce must be 16 bytes")
    if len(plaintext) > 16 or len(associated_data) > 16:
        raise ValueError("Bounded AEAD input lengths must be 0..16")
    golden = encrypt(key, nonce, plaintext, associated_data)
    k0 = int.from_bytes(key[:8], "little")
    k1 = int.from_bytes(key[8:], "little")
    n0 = int.from_bytes(nonce[:8], "little")
    n1 = int.from_bytes(nonce[8:], "little")
    state = [IV, k0, k1, n0, n1]
    first = replay = checkpoint = mismatch = alarm = False

    def permute(rounds: int, phase: int) -> None:
        nonlocal first, replay, checkpoint, mismatch, alarm
        chosen = spec.fault if spec.enabled and phase == spec.phase else AdversarialSpec()
        o = evaluate(pack_state(tuple(state)), rounds, chosen)
        first |= o.first_fired
        replay |= o.replay_fired
        checkpoint |= o.checkpoint_fired
        mismatch |= o.raw_mismatch
        alarm |= o.alarm
        state[:] = unpack_state(o.output)

    permute(12, 0)
    state[3] ^= k0
    state[4] ^= k1
    if associated_data:
        padded = associated_data.ljust(16, b"\x00") if len(associated_data) == 16 else (
            associated_data + b"\x01" + bytes(15 - len(associated_data))
        )
        state[0] ^= int.from_bytes(padded[:8], "little")
        state[1] ^= int.from_bytes(padded[8:], "little")
        permute(8, 1)
        if len(associated_data) == 16:
            state[0] ^= 1
            permute(8, 2)
    state[4] ^= 1 << 63

    if len(plaintext) == 16:
        # Full-rate ciphertext is produced before the message p[8].
        ciphertext = bytes(x ^ y for x, y in zip(
            plaintext, state[0].to_bytes(8, "little") + state[1].to_bytes(8, "little")
        ))
        state[0] ^= int.from_bytes(plaintext[:8], "little")
        state[1] ^= int.from_bytes(plaintext[8:], "little")
        permute(8, 3)
        state[0] ^= 1
    else:
        current_rate = state[0].to_bytes(8, "little") + state[1].to_bytes(8, "little")
        ciphertext = bytes(x ^ y for x, y in zip(plaintext, current_rate))
        padded = plaintext + b"\x01" + bytes(15 - len(plaintext))
        state[0] ^= int.from_bytes(padded[:8], "little")
        state[1] ^= int.from_bytes(padded[8:], "little")

    state[2] ^= k0
    state[3] ^= k1
    permute(12, 4)
    state[3] ^= k0
    state[4] ^= k1
    tag = state[3].to_bytes(8, "little") + state[4].to_bytes(8, "little")

    # RTL gates both outputs with result_valid; suppressed data is not released.
    valid = not alarm
    return AeadObservation(
        ciphertext=ciphertext if valid else b"",
        tag=tag if valid else bytes(16),
        golden_ciphertext=golden[:-16], golden_tag=golden[-16:],
        first_fired=first, replay_fired=replay, checkpoint_fired=checkpoint,
        raw_mismatch=mismatch, alarm=alarm, valid=valid,
    )
