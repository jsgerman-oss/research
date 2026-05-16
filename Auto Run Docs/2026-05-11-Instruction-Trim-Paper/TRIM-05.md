# TRIM-05 — Figures

## Goal
Produce three TikZ/pgfplots figures backed by CSVs from TRIM-01/02/04 and
wire them into the relevant sections.

## Context
- Paper dir: `/Users/jayse/research/blackrim-instruction-trim-paper/`
- Figures dir (currently empty): `figures/`
- main.tex already imports `tikz` + `pgfplots` (compat=1.18) — no extra
  preamble work needed.
- CSV inputs (must exist from prior phases):
  - `data/aggregated/trim-results.csv` (TRIM-01)
  - `data/aggregated/section-residency.csv` (TRIM-02)
  - `data/aggregated/fidelity-delta.csv` (TRIM-04) — optional for fig3,
    can render placeholder bars if TRIM-04 hasn't run yet

## Tasks
- [ ] **fig1 — size trajectory.** Create `figures/fig1-size-trajectory.tex`
  as a self-contained `\begin{figure}` block. Inside: a pgfplots bar
  chart with three bars (Baseline / Wave 1 / Wave 2) and two grouped
  series (lines, chars on a secondary axis or scaled). Caption:
  "CLAUDE.md size trajectory across Wave 1 (redundancy removal) and
  Wave 2 (worktree-isolation externalization); 21.5% line reduction,
  17.1% char reduction." Label: `fig:size-trajectory`. Data source:
  use `\pgfplotstableread{data/aggregated/trim-results.csv}{\trim}`
  and reference rows by their `subject` field, OR hardcode the three
  values inline if pgfplotstable feels heavy. Inline is fine —
  reproducibility is via the CSV existing, not the .tex parsing it.
- [ ] Include fig1 in §6 Evaluation right after the size-trajectory
  table (`sections/06-evaluation.tex`, after `\end{table}` at line
  ~50). `\input{figures/fig1-size-trajectory}`.
- [ ] **fig2 — section classification.** Create
  `figures/fig2-section-classification.tex` as a stacked horizontal
  bar chart: one row per top-level section in baseline CLAUDE.md,
  each row colored by its classification (must-resident / frequency-
  deciding-kept / frequency-deciding-externalised / redundant-removed)
  with bar length = baseline line count. Data source:
  `data/aggregated/section-residency.csv`. This is the headline figure
  for §5 — it visualises what the conservative trim algorithm did to
  the real CLAUDE.md. Caption + label `fig:section-classification`.
- [ ] Include fig2 in §5 Algorithm right after the worked example
  subsection.
- [ ] **fig3 — cost-model break-even curve.** Create
  `figures/fig3-breakeven.tex`. Plot the Eq.\,\eqref{eq:decision}
  decision rule: x-axis = frequency `f`, y-axis = ratio
  `f·r / |s|`, with the break-even line at 0.235 (for ρ=0.85,
  α=0.10). Overlay 4-6 SCATTER POINTS for actual sections from
  `section-residency.csv` (need a `frequency` estimate per section
  in the CSV — if TRIM-02 didn't add this column, add it now with
  rough estimates: 1.0 for must-resident, 0.1-0.5 for frequency-
  deciding, 0.0 for redundant). Caption: "Decision-rule break-even
  curve with measured sections overlaid; points below the line
  externalise, points above stay resident." Label:
  `fig:breakeven`.
- [ ] Include fig3 in §3 Problem Formulation right after the
  decision-rule equation.
- [ ] Build the paper end-to-end: `make` from the paper dir.
  Verify zero "Reference X on page Y undefined" warnings for
  `fig:*` labels and zero "Float too large" errors. The PDF
  should now have three figures.
- [ ] Commit: `figures(trim): fig1 size trajectory, fig2 section
  classification, fig3 breakeven curve; data-backed`.

## Acceptance criteria
- Three `figures/fig*-*.tex` files exist and compile via main.tex.
- Each figure is referenced via `\cref{fig:*}` at least once in
  prose (not just `\input`'d).
- `make` exits 0 and the resulting `main.pdf` has three figures
  in the expected sections.

## Style guidance
- Keep colors print-safe (no light yellow on white). Use the
  pgfplots default palette + `cycle list name=color list`.
- Bars should have visible numerical labels on top
  (`nodes near coords`).
- Don't auto-size — set `width=0.85\textwidth, height=6cm` for
  consistency across all three figures.

## Out of scope
- Animation, color theming for slides, vector tracing.
- Figure 4+ (none planned).
