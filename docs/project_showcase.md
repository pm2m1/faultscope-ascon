# Research Dashboard and project showcase

The selected presentation retains the original dark navy background, cyan/blue accents, sidebar, research cards and charts. The two pages form one narrative: the dashboard explains what was built and tested; Algorithm Walkthrough explains how the actual browser-local calculation works.

## Research Dashboard

The project introduction asks, "Can hardware detect when encryption goes wrong?" Problem, solution and investigation cards introduce controlled fault simulation and temporal recomputation without assuming cryptography knowledge.

Architecture flows show the bounded encryption controller, protected permutation, comparison/alarm and gated ciphertext/tag output. A separate verification path connects simulated fault injection, Verilator, Python comparison and recorded evidence. Component details distinguish Yosys/Vivado analysis from physical FPGA operation.

The five-step protection demonstration uses actual p[12] computations from `compareReplay`, with a shared calculation engine and input checkpoint. Try No fault, One faulty calculation, and The same fault twice. Advanced details expose golden/first/replay states and mismatch/alarm/valid/incorrect-release flags. Steps are explanatory stages, not RTL clock cycles.

Simple View emphasizes the interpretation. Technical View reveals exact phase/scenario IDs, hardware signals, aggregate metrics, component roles and provenance. Both views share the same API data and controls. The original charts, phase comparison, ledger filters/pagination, adversarial scenario tables and Learning Lab remain available. The sidebar automatically opens the Learning Lab disclosure.

## Recorded findings and interpretation

All numerical research cards use the existing verified read-only API. Interactive input does not change these measurements.

| Recorded measurement | Value | Meaning and limit |
|---|---|---|
| Clean replay | 424 cases; 93 applied/detected; 331 without injection; 0 false alarms | Trusted replay/checkpoint/comparator; not universal fault coverage |
| Adversarial permutation | 240 cases; 60 incorrect releases | Constructed permutation-level cases, not attack probabilities |
| Adversarial bounded AEAD | 600 cases; 102 incorrect ciphertext/tag releases | Release from the sender controller is not receiver acceptance or forgery |
| Historical generic Yosys cells | 8,277 baseline; 9,865 instrumented; 12,863 protected | Includes historical metadata entries; not FPGA LUTs or silicon area |
| Mean simulation cycles | 47.17 baseline; 95.64 protected; +102.77% | Simulation clock counts, not milliseconds or board throughput |

Each major metric has an expandable explanation of its measurement, importance, supported conclusion and limits. "Technical evidence and reproducibility" retains original phase identifiers, campaign SHA-256 values, tool/reference provenance, source documentation and limitations. Raw campaign hashes remain byte-exact; no historical values were repinned.

The conclusion is specific to tested models: clean replay detected every applied fault, but correlated/checkpoint/comparison faults exposed limitations. The RTL provides bounded encryption/tag generation, not authenticated decryption. Browser decryption is educational software. No physical board operation, physical injection, production cryptography, guaranteed fault security or successful authenticated forgery is claimed. Phase 25 remains separate and unaccepted.

## Source map

- `frontend/src/App.tsx`: API-backed dashboard, filters/charts, presentation toggle and evidence disclosures.
- `frontend/src/ProjectStory.tsx`: introduction, architecture, metric explanations and real permutation protection demo.
- `frontend/src/projectStory.css`: scoped dark-theme presentation and responsive rules.
- `frontend/src/SiteApp.tsx`: two-page navigation and dashboard state retention.
- `frontend/src/AlgorithmWalkthrough.tsx`: input/trace/receiver/fault interactions and project bridge.
- `frontend/src/asconAeadTrace.ts`: actual browser encryption/decryption and trace generation.
- `frontend/e2e/project-showcase.spec.ts`, `walkthrough.spec.ts`: research control and crypto UI regressions.
- `.github/workflows/website.yml`: separate Chromium browser CI; existing research/formal workflows remain intact.

`AsconLab.tsx`, `asconTrace.ts`, original `styles.css`, backend and accepted research implementations are unchanged. A scoped scroll container keeps all original Lab timeline controls usable on narrow screens.

## Run and validate

See [README](../README.md#start-here-run-the-project) for dependency setup, backend/frontend launch and Windows commands. The page URLs are:

- http://127.0.0.1:5173/#/
- http://127.0.0.1:5173/#/walkthrough
- http://127.0.0.1:5173/#/results

The relevant Python/reference/API set initially recorded 54 passing tests. Earlier local browser validation recorded 16 passing tests; release validation adds the explicit dark-theme test. The suite checks API/card agreement, provenance, filters/pagination, real protection states, Lab access, HELLO/decryption/tampering, playback, UTF-8 limits, keyboard navigation and responsive layouts. See current local/CI execution logs for final counts.

Browser tests create a unique ignored `build/reproduction/website_ui/` directory per run. Optional `FAULTSCOPE_UI_OUTPUT` selects a separate output location. Screenshots, ZIPs, machine-specific review scripts and old capture manifests remain local build artifacts and are not repository source. The original 32-view capture collection is not overwritten by the tests or committed.

## Five-minute demonstration

1. **0:00-0:45:** Introduce the dashboard problem and distinguish the encryption circuit from the test/reference path.
2. **0:45-2:00:** Open the walkthrough, encrypt HELLO, inspect XOR/tag output, authenticate/decrypt, then demonstrate rejection after tampering.
3. **2:00-3:00:** Return to the dashboard; compare clean, first-pass-fault and identical-fault modes. Explain why agreement does not establish correctness.
4. **3:00-4:00:** Show 93/93 under clean replay, then the separate 60/240 and 102/600 adversarial findings. Filter recorded cases; do not describe ratios as attack probabilities.
5. **4:00-5:00:** Explain Yosys cells and simulation-cycle costs, open Technical View for provenance, and finish with the scientific limitations.

No new Verilator campaign, FPGA implementation or physical demonstration is required to reproduce this educational website. Separate toolchains and qualified evidence remain necessary for hardware research claims.
