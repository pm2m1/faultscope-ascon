# FaultScope-Ascon — Phase 5 synthesis/latency report

## Scope and reproducibility

- Model: single transient pre-round state-bit flip in first permutation execution; clean replay/checkpoint/comparator.
- RTL: encryption and tag generation only, 0–16 bytes of plaintext and associated data.
- Phase 4B CSV input: `/Users/kiyo/Projects/faultscope-ascon/reports/phase4b_temporal.csv`
- Git HEAD at analysis: `1b7d727136033174c32828f50385a1c7afe7ee1b`
- Yosys: `Yosys 0.69+post (git sha1 143eb14f9cc55d6f8927e68523b0c9d2166ed02c, Release, AppleClang clang++ 21.0.0.21000334)`; sv2v: `0.0.13`
- Synthesis: `sv2v; Yosys hierarchy -check; synth -flatten -noabc; check -assert; write_json`

## Fault security and cycle overhead (from Verilator CSV)

| Metric | Observed |
|---|---:|
| Campaign scenarios | 424 |
| Applied fault events | 93 |
| Detected applied faults | 93 |
| Coverage in *this model* | 100.00% |
| False alarms / no-injection cases | 0 / 331 |
| False alarm rate among no-injection cases | 0.00% |
| Alarm-and-valid policy violations | 0 |
| Mean baseline cycles | 47.17 |
| Mean protected cycles | 95.64 |
| Mean additional cycles | 48.47 |
| Relative increase in mean cycles | 102.77% |
| Baseline p95 cycles | 65 |
| Protected p95 cycles | 133 |

## Generic synthesis resources (Yosys, identical flow)

| Design | Total generic cells | FF Q bits | Combinational cells |
|---|---:|---:|---:|
| baseline | 8,277 | 1,625 | 6,652 |
| instrumented | 9,865 | 1,659 | 8,206 |
| protected | 12,863 | 2,645 | 10,218 |

| Comparison | Generic cell change | FF Q bit change |
|---|---:|---:|
| Protected vs baseline | +55.41% | +62.77% |
| Protected vs instrumented | +30.39% | +59.43% |

The *baseline* has no injection ports. The *instrumented* comparison helps separate fault-injection circuitry from the added temporal-replay defense, but these are distinct RTL architectures, not isolated gate-by-gate additions.

## Interpretation limits

- Generic cell counts are synthesis-configuration-dependent **structural proxies**, NOT silicon area in mm², FPGA LUTs, power consumption, or a maximum clock frequency.
- The mean-cycle ratio does not imply a clock-frequency ratio; no timing analysis or place-and-route was performed.
- No physical fault testing, replay-fault injection, checkpoint tampering, comparator bypass, or authenticated decryption security evaluation was performed.
- A fault effect observed during encryption is not evidence of AEAD authentication bypass.
- Detection for a single pre-round state bit flip with an unfaulted replay is expected for a bijective permutation. This does not establish resistance to realistic correlated attacks.
- Preserve the manifest, individual synthesis logs, per-design converted Verilog and JSON netlists alongside the CSV for auditability.

