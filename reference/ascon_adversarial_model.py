"""Phase 7A permutation-level adversarial temporal replay oracle.

Models fault hooks in RTL/ascon_permutation_adversarial.sv, NOT physical
fault mechanisms, probability of attack, or AEAD authentication bypass.
"""
from dataclasses import dataclass
from reference.ascon_permutation import ascon_round, ascon_permutation, ROUND_CONSTANTS, MASK64


def unpack_state(state: int) -> tuple[int, int, int, int, int]:
    if not 0 <= state < 1 << 320:
        raise ValueError("Expected an unsigned 320-bit state")
    return tuple((state >> (64 * (4 - i))) & MASK64 for i in range(5))


def pack_state(words: tuple[int, int, int, int, int]) -> int:
    if len(words) != 5 or any(not 0 <= x <= MASK64 for x in words):
        raise ValueError("Expected five unsigned 64-bit lanes")
    return sum(x << (64 * (4 - i)) for i, x in enumerate(words))


@dataclass(frozen=True)
class AdversarialSpec:
    first_arm: bool = False
    first_round: int = 0
    first_bit: int = 0
    replay_arm: bool = False
    replay_round: int = 0
    replay_bit: int = 0
    checkpoint_mode: int = 0  # 0 none, 1 shared, 2 replay-only
    checkpoint_bit: int = 0
    suppress_alarm: bool = False


@dataclass(frozen=True)
class Observation:
    golden: int
    first_state: int
    replay_state: int
    output: int
    first_fired: bool
    replay_fired: bool
    checkpoint_fired: bool
    raw_mismatch: bool
    alarm: bool
    valid: bool

    @property
    def silent_corruption(self) -> bool:
        """Comparison allowed output that differs from unfaulted permutation."""
        return self.valid and self.output != self.golden


def permute_faulted(state: int, rounds: int, arm: bool, round_index: int, bit: int) -> tuple[int, bool]:
    if rounds not in (8, 12):
        raise ValueError("Rounds must be 8 or 12")
    fired = False
    words = unpack_state(state)
    for idx, constant in enumerate(ROUND_CONSTANTS[12 - rounds:]):
        if arm and idx == round_index and 0 <= bit < 320:
            words = unpack_state(pack_state(words) ^ (1 << bit))
            fired = True
        words = ascon_round(words, constant)
    return pack_state(words), fired


def evaluate(state: int, rounds: int, spec: AdversarialSpec) -> Observation:
    if spec.checkpoint_mode not in (0, 1, 2, 3):
        raise ValueError("checkpoint_mode outside two-bit hardware range")
    golden = pack_state(ascon_permutation(unpack_state(state), rounds))
    cp_hit = spec.checkpoint_mode in (1, 2) and 0 <= spec.checkpoint_bit < 320
    shared = state ^ ((1 << spec.checkpoint_bit) if cp_hit and spec.checkpoint_mode == 1 else 0)
    replay_input = shared ^ ((1 << spec.checkpoint_bit) if cp_hit and spec.checkpoint_mode == 2 else 0)
    first_result, first_hit = permute_faulted(
        shared, rounds, spec.first_arm, spec.first_round, spec.first_bit
    )
    replay_result, replay_hit = permute_faulted(
        replay_input, rounds, spec.replay_arm, spec.replay_round, spec.replay_bit
    )
    mismatch = first_result != replay_result
    alarm = mismatch and not spec.suppress_alarm
    valid = not mismatch or spec.suppress_alarm
    return Observation(
        golden=golden,
        first_state=first_result,
        replay_state=replay_result,
        output=replay_result if valid else 0,
        first_fired=first_hit,
        replay_fired=replay_hit,
        checkpoint_fired=cp_hit,
        raw_mismatch=mismatch,
        alarm=alarm,
        valid=valid,
    )
