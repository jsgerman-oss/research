# Phase 07: Figures & §6 Evaluation — Instruction-Trim Paper

Mirror of Phase 06 for `blackrim-instruction-trim-paper`. Generates figures and tables backing §6 (Empirical Evaluation) and rewrites the section against measured trim results. Deliverable: a compiled PDF whose §6 is data-grounded.

## Tasks

- [ ] Read the current state before generating:
  - `blackrim-instruction-trim-paper/sections/06-evaluation.tex` for existing claims, figure refs, table refs
  - `Phase-05-DataReady.md` to confirm `data/aggregated/trim-results.csv` (and any other CSVs) exist
  - `Phase-05-Claims-vs-Data.md` for the 17.1% / 21.5% reduction reconciliation
  - Existing TikZ/pgfplots conventions in `figures/` or the routing-caching paper — match style across both papers for visual cohesion

- [ ] Generate figures required by §6. Prefer pgfplots reading CSVs directly; fallback to `scripts/render-figures.py`. Produce at minimum:
  - `figures/trim-before-after.{pdf,tex}` — line-count before vs. after on CLAUDE.md and any other instruction files trimmed, sourced from trim-results CSV
  - `figures/frequency-residency-scatter.{pdf,tex}` — per-line frequency-of-reference vs. retain/evict decision (the core empirical artifact for the residency model)
  - `figures/fidelity-vs-trim-rate.{pdf,tex}` — instruction-fidelity score vs. % trimmed, showing the no-degradation plateau
  - `figures/per-spawn-savings.{pdf,tex}` — tokens / cost saved per agent spawn, projected to fleet scale
  - Each caption must reference the source CSV and observation window

- [ ] Generate tables as standalone `.tex` snippets in `figures/` (e.g. `figures/table-trim-by-section.tex`) that §6 `\input`s. Cover:
  - Per-document trim statistics (lines retained / evicted / total, % reduction) across every instruction file in scope
  - Frequency-bucket residency decisions (e.g., "lines referenced >N times / spawn → retain", with measured N)
  - Fidelity evaluation: task list + retain-status correlation, if data exists

- [ ] Rewrite `blackrim-instruction-trim-paper/sections/06-evaluation.tex`:
  - Replace placeholders with measured values from `Phase-05-Claims-vs-Data.md`
  - Sentence-trailing `% source: data/aggregated/X.csv col=Y` comments on every quantitative claim
  - Use `\ref{fig:...}` / `\ref{tab:...}` consistently
  - Structure: Setup (which instruction docs, which agents) → Trim mechanics (the frequency-residency model in action) → Fidelity results (the "no degradation" defence) → Cost results (per-spawn + fleet-scale) → Threats to validity → Limitations of frequency as a signal
  - Delete unsupported sentences or move to §9 Future Work with `\todo{}`

- [ ] Build and verify:
  - `make` in `blackrim-instruction-trim-paper/`
  - Capture undefined-cite/undefined-ref from `.log` and `.blg`
  - Open the PDF and confirm every figure renders and §6 cross-references resolve
  - Record to `Auto Run Docs/Initiation/Working/Phase-07-Build.md`

- [ ] Update `sections/00-abstract.tex` with the final measured headline reduction number (17.1% or whatever the validated CSV produces). Reconcile against the README's claim — if the README says 21.5% but the data says 17.1%, update the README too so the artifact set is self-consistent. Log the reconciliation in the Phase-07 build doc.
