# Phase 24 — Independent research-release candidate review

**Disposition:** ACCEPT for a **scoped draft pull request** as a qualified, **pre-silicon research-release milestone**. The pilot is **not a final frozen release** until fresh Phase 24 PR CI, PR merge, and a post-merge audit of the final `main` commit have been reviewed. **No physical FPGA, board, reset, external-I/O timing, UART MTBF or bitstream signoff is implied.**

**Reviewed artifacts:** the user-supplied `faultscope_phase24_review.zip` (SHA-256 `7d133920837c7257f3bbb0d8841ee39153de431dcb8492d4aae2f944a2a1d50b`), the Windows Phase 24 terminal transcript, the original review archives for Phases 15–23, the available Phase 23 validator, and the GitHub tree at `pm2m1/faultscope-ascon` commit `1ce848e480dcfb65045ee04b89d2b67de57ade39`.

## 1. Archive and manifest verification

- Exact ZIP inventory: `verification.json`, `source_manifest.tsv`, `evidence_manifest.tsv`, `release_gates.tsv`, `release_candidate.md`. No extra members, duplicate entries or CRC errors.
- `verification.json` has `phase=24`, `verdict=RESEARCH_RELEASE_REVIEW_REQUIRED`, `source_head_commit=1ce848e480dcfb65045ee04b89d2b67de57ade39`, `source_tracked_file_count=190`, `evidence_archives=9`, `phase23_reproduced_reports=5`, and `board_signoff=NOT VERIFIED`. No `source_or_checkpoint_modified` claim was made.
- Independent SHA-256 of each report equals its recorded `verification.json.report_sha256` value:

| Report | Verified SHA-256 |
|---|---|
| `source_manifest.tsv` | `c1243792df0f55dc84a17de07083522107d81da2d46f97c658f9f0d35816a5f5` |
| `evidence_manifest.tsv` | `2f9af82611f4841905ffa687d855e5ed77b9a21fd576fd98f241cfac2ab3adda` |
| `release_gates.tsv` | `bdb82158fcbc87e0560ca042dbcacc8a6413d3b1858af4d73c89fc83e9738fda` |
| `release_candidate.md` | `e7e30313d8a9e69700bd004765a32b98e0f0e68132118fe6f3980b0d38539f63` |

- The nine `evidence_manifest.tsv` ZIP SHA-256 values all matched the original archived ZIP bytes available for review. These hashes bind the local review bundle to those archive bytes; they **do not** provide an externally trusted signature of original producer authenticity.
- The `source_manifest.tsv` lists 190 unique, sorted tracked paths. The independent GitHub commit tree also has exactly 190 blobs. Canonicalizing each `path<TAB>git_blob_sha1<TAB>size_bytes<LF>` entry and hashing the complete sorted stream gives **SHA-256 `c48f8f5e76c6fd7886bdc3494c8446b9314ce3cae1f2515a526c9f8719d46a40`** for *both* the uploaded manifest and the GitHub tree. This independently corroborates path names, Git blob IDs and sizes at the stated base commit. It does **not** authenticate untracked Phase 24 source files or later commits; nor is the manifest's separate per-blob SHA-256 column independently recalculated against all 190 remote blob bodies.

## 2. Reproduction and provenance boundary

- The Windows transcript reports **30/30 Phase 24 tests passed**, `PHASE24_RELEASE_INPUTS_VERIFIED`, successful generation of `RESEARCH_RELEASE_REVIEW_REQUIRED`, and matching Phase 17 DCP SHA-256 `633115341bee563ef5c0cca8dc39cffc0e20a2e8de93db58dadafb61f0136340`.
- Separately, the Phase 23 validator was used offline to rebuild all **five** Phase 23 derived files from the available Phase 15–22 archives. They matched the original Phase 23 ZIP **byte for byte**, using an explicitly simulated accepted DCP digest for this archive-only reproducibility check. **The actual routed DCP was not available in this review environment** and its live bytes were **not** independently rehashed; the true DCP-byte gate relies on the successful Windows execution.
- The release's `source_head_commit` is deliberately **the pre-Phase-24 merge base** (`1ce848e...`). This means the first release candidate is a base-source snapshot, **not** a completed freeze of Phase 24 source changes. A mandatory **post-merge audit from final `main`** must create a new manifest for the final merge commit (with the additional Phase 24 source files). Do not represent the pre-merge 190-file manifest as the post-merge project snapshot.
- The locally observed Phase 24 run does not itself rerun Verilator, Yosys or formal proofs; it relies on their separate CI workflows. Main-branch CI for the Phase 23 merge passed previously, but **fresh Phase 24 PR CI must be checked independently**.

## 3. Release gate assessment

The 11 `release_gates.tsv` states are explicitly bounded:

| Gate | Review classification |
|---|---|
| Historical Phase 15–22 evidence | `VERIFIED_OFFLINE` against supplied archives |
| Phase 23 derived report reproduction | `BYTE_IDENTICAL` |
| Checkpoint digest | `VERIFIED_LOCALLY`, **not independently rehashed here** |
| Git source commit | `VERIFIED_GIT` for base-source snapshot |
| Current Phase 24 PR CI | `PENDING_EXTERNAL_REVIEW` |
| Physical board revision | `NOT_VERIFIED` |
| Physical reset/oscillator/recovery-removal | `NOT_VERIFIED` |
| External I/O constraints | `NOT_QUALIFIED` — **five TIMING-18 warnings remain** |
| UART analog metastability MTBF | `NOT_VERIFIED` |
| Bitstream and board operation | `NOT_VERIFIED` |
| Phase 15–18 legacy member-hash coverage | `PARTIAL` |

The research ledger retains **8 evidence-bounded claims, 8 OPEN dependencies and 1 separate archive-integrity LIMITATION**. Six external `rst_n` timing paths have **unavailable** finite slack; four modeled UART preset paths retain the Phase 21–22 observations. Neither finite internal slack nor correct routed I/O pins establish physical board-level timing signoff.

## 4. Acceptable PR scope and final gates

The draft PR may add **only these five source/documentation files**:

1. `scripts/phase24_release_candidate.py`
2. `scripts/phase24_release_candidate.ps1`
3. `tests/test_phase24_release_candidate.py`
4. `docs/phase24_research_release.md`
5. `docs/phase24_manual_review.md` (this addendum)

Do **not** stage generated `build/` reports, review ZIPs, RTL, XDC, DCP, source locks, bitstreams, or changes to historical test/evidence files. Run `git diff --cached --check` and verify exactly five additions. Create a **draft PR**; inspect exact file scope, GitHub CI for the Phase 24 PR head (including Python/Verilator, Yosys/formal and dashboard jobs), and mergeability **before** promoting/merging.

**Mandatory after merge:** sync local `main`, rerun the Phase 24 audit from the merged source using the same nine original review archives and accepted local Phase 17 DCP; independently review new source-manifest counts/hashes, final Git commit, retained hardware-limitations gate states, and fresh CI. This is the gate for declaring the **24-phase pre-silicon research roadmap complete**. A public release, GitHub tag, board programming or hardware-signoff statement needs a separate explicit decision; **do not create any automatically**.
