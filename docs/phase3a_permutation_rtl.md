# Phase 3A — Ascon permutation RTL

This milestone implements the NIST SP 800-232 320-bit Ascon permutation in an **unprotected** one-round-per-clock architecture.

## State lane order
`{x0,x1,x2,x3,x4}` = 320 bits; each lane is 64 bits. `x0` occupies bits `[319:256]`, `x4` occupies `[63:0]`. Round constants are XORed into the low 8 bits of `x2`.

## Behavior
* `start_i` is sampled when `busy_o == 0` and `rounds_i` is 8 or 12. Unsupported values are ignored.
* At start the input state is latched. During the next 8 or 12 clock edges the round logic updates the state.
* `done_o` goes high for one clock after the final round, `busy_o` falls, and `state_o` holds the result until another operation completes.
* For p[8], round constants begin at `0xb4`; for p[12], they begin at `0xf0`.
* The design intentionally exposes no fault-injection controls yet. Those will be added after the fault-free RTL passes tests.

## Verification
`uv run python -m pytest tests/test_rtl_permutation.py -v`

The test generates 206 deterministic reference outputs using the previously verified Python implementation, compiles the RTL and SV testbench with Verilator, and checks each output, completion pulse and cycle count.

## Caveat
Passing simulation does not establish robustness against physical fault injection, side channels, or silicon timing closure. The design is for pre-silicon experiments.
