# Phase 23 — Independent evidence-gap matrix review

**Disposition:** ACCEPT for a **bounded, read-only research-evidence milestone**, subject to normal PR scope/CI review. **Not a physical FPGA, board, or external-timing signoff.**

**Reviewed:** `faultscope_phase23_review.zip` (five derived files), the user-provided successful Phase 23 terminal transcript, and independently available original Phase 15–22 review ZIPs. The terminal transcript reports 30/30 Phase 23 tests passing, a successful `PHASE23_INPUT_EVIDENCE_VERIFIED` preflight, and `EVIDENCE_MATRIX_REVIEW_REQUIRED` after matrix generation.

## Independent artifact checks

- The derived archive contains exactly `verification.json`, `evidence_sources.tsv`, `qualified_claims.tsv`, `open_gaps.tsv`, and `dossier.md`; no RTL, XDC, DCP, or bitstream is included.
- Recomputed SHA-256 for the four derived reports equals the four `verification.json.output_sha256` entries:

  | Report | Verified SHA-256 |
  |---|---|
  | `dossier.md` | `1cc79c46710204633a1c1983140f3dcaf2ca0b15d85152b0f97eb272a3516021` |
  | `evidence_sources.tsv` | `84cf8746aa18229283ea50856345a4b42eddd44a89cc1e03dbca60fd1fc34cc0` |
  | `qualified_claims.tsv` | `8d705c19b3ce9d30f7d2165b45da9806a887552148b801d082e084600acafbb1` |
  | `open_gaps.tsv` | `a43c58077ed865b1c208e39c259bdd66bf626a69f0cea77833e09c4824285e1a` |

- All eight ZIP SHA-256 values in `evidence_sources.tsv` independently match the Phase 15–22 review archive bytes available for review. For Phases 16–22, all manifest-listed report hashes were checked against the corresponding members, with no mismatches. Phase 15 has no per-member report hash list in its `verification.json`.
- Member-level recorded hash coverage agrees with the matrix: Phase 15 **0/13**, Phase 16 **7/10**, Phase 17 **9/15**, Phase 18 **5/13**; Phases 19–22 respectively **9/9, 6/6, 10/10, 16/16**. These counts exclude `verification.json` itself. ZIP digests and self-reported manifest hashes establish internal consistency, not a trusted external signature or independent producer authenticity.

## Cross-phase consistency findings

- The accepted Phase 15 and Phase 17 DCP anchors recorded in the matrix match the historical manifests: Phase 15 `869b84e1636e36a308507d52a6c6238374d44e937bd39bcdc4e0a24b7f22b199`; Phase 17 `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`. The user-side preflight also reports matching the **actual local Phase 17 DCP**. **This review did not independently receive and rehash that large DCP**; it relies on the local validator's reported checkpoint-byte check for that specific gate.
- Phase 17 `pin_assignment.tsv` and Phase 22 `ports.tsv` agree for all six provisional board interfaces: `clk=E3`, `rst_n=C12`, `uart_rx_i=C4`, `uart_tx_o=D4`, `led_busy_o=H17`, `led_alarm_o=K15`, with `LVCMOS33`.
- Phase 20's `pin_edges.tsv` reports eight expected routed reset connections and `lut_truth.tsv` reports two `LUT1` inverters (`INIT=2'h1`). These are **netlist/Boolean observations**, not reset-button electrical polarity or bounce measurements.
- Phase 21 `path_observations.tsv` and Phase 22 `path_bindings.tsv` agree on ten individual path queries: six external `rst_n → FDCE/CLR` queries report paths **without finite slack**, and four modeled UART release-to-`FDPE/PRE` queries report finite slack (max **+4.283 ns**, min **+2.075 ns** for both UART stages). `PATH_REPORTED_SLACK_UNAVAILABLE` must never be represented as a timing pass. Phase 22's `/C` timing source versus `/Q` net driver remains a distinct clock-to-Q timing-report interpretation, not a change in connectivity.
- Five missing external I/O timing-delay warnings remain open: `rst_n`, `uart_rx_i`, `uart_tx_o`, `led_busy_o`, `led_alarm_o`. Nothing in Phase 23 introduces or qualifies new external input/output delays.

## Ledger and signoff boundary

`qualified_claims.tsv` contains **eight bounded claims** (P23-C01 through P23-C08). The word *qualified* means **limited to the stated evidence scope**; it does not mean all eight are hardware-certified. In particular, P23-C07 documents an **open constraint-coverage failure**, and P23-C08 documents **partial historical integrity coverage**.

`open_gaps.tsv` has **eight `OPEN` rows** (G23-01 through G23-08) and **one distinct `LIMITATION` row** (G23-09). Hence `verification.json.open_gaps = 8` and `evidence_limitations = 1` are internally correct; neither indicates nine resolved issues.

Physical board/revision confirmation, external reset timing and pulse width/bounce, oscillator startup/jitter, analog UART synchronizer MTBF, USB-UART and LED external timing models, and actual programming/hardware operation remain **NOT VERIFIED**. Do not claim hardware signoff, assign invented delays, suppress `TIMING-18` with blanket exceptions, reroute, or generate a bitstream for this phase.

## PR scope and next gate

A Phase 23 **draft PR** may add only:

1. `scripts/phase23_evidence_gap_matrix.py`
2. `scripts/phase23_evidence_gap_matrix.ps1`
3. `tests/test_phase23_evidence_gap.py`
4. `docs/phase23_evidence_gap_matrix.md`
5. `docs/phase23_manual_review.md` (this addendum)

The five derived report files and eight historic review ZIPs must **not** be committed. Before merge, review the exact GitHub file scope, ensure CI passes on the PR head, and preserve all outstanding gaps. Phase 24 can package a **qualified research release**; physical hardware validation remains a separate, unresolved workstream.
