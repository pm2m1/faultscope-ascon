
"""Ascon p[8] and p[12] permutations (NIST SP 800-232).

State representation: five unsigned 64-bit words.
All bitwise operations are restricted to 64-bit words.
"""

MASK64 = (1 << 64) - 1

ROUND_CONSTANTS = (
    0xF0, 0xE1, 0xD2, 0xC3,
    0xB4, 0xA5, 0x96, 0x87,
    0x78, 0x69, 0x5A, 0x4B,
)


def rotr64(value: int, count: int) -> int:
    """Rotate a 64-bit word to the right."""
    count %= 64
    value &= MASK64
    return (
        (value >> count) | (value << (64 - count))
    ) & MASK64


def ascon_round(state: tuple, constant: int) -> tuple:
    """Apply one Ascon permutation round."""
    x0, x1, x2, x3, x4 = state

    # 1. Addition of the round constant
    x2 ^= constant

    # 2. Nonlinear substitution layer
    x0 ^= x4
    x4 ^= x3
    x2 ^= x1

    t0 = x0 ^ (~x1 & x2)
    t1 = x1 ^ (~x2 & x3)
    t2 = x2 ^ (~x3 & x4)
    t3 = x3 ^ (~x4 & x0)
    t4 = x4 ^ (~x0 & x1)

    t1 ^= t0
    t0 ^= t4
    t3 ^= t2
    t2 = ~t2

    # 3. Linear diffusion layer
    words = (t0, t1, t2, t3, t4)

    rotations = (
        (19, 28),
        (61, 39),
        (1, 6),
        (10, 17),
        (7, 41),
    )

    result = []

    for word, (a, b) in zip(words, rotations):
        word &= MASK64

        diffused = (
            word ^ rotr64(word, a) ^ rotr64(word, b)
        ) & MASK64

        result.append(diffused)

    return tuple(result)


def ascon_permutation(state: tuple, rounds: int = 12) -> tuple:
    """Apply the 8-round or 12-round Ascon permutation."""
    if len(state) != 5:
        raise ValueError("State must contain five words")

    if any(not isinstance(x, int) or not 0 <= x <= MASK64
           for x in state):
        raise ValueError("Each word must be an unsigned 64-bit integer")

    if rounds not in (8, 12):
        raise ValueError("Supported round counts: 8 and 12")

    for constant in ROUND_CONSTANTS[12 - rounds:]:
        state = ascon_round(state, constant)

    return state
