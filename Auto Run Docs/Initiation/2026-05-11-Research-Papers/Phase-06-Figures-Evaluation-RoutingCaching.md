# Phase 06: Figures & §7 Evaluation — Routing & Caching Paper

With the data pipeline producing CSVs in `data/aggregated/`, this phase generates the figures and tables that back §7 (Empirical Evaluation) of `blackrim-routing-caching-paper` and rewrites the section's prose against measured numbers. The deliverable is a compiled PDF whose §7 reflects real data, not placeholders.

## Tasks

- [ ] Read the current state before generating anything:
  - `blackrim-routing-caching-paper/sections/07-evaluation.tex` to identify every existing claim, figure ref (`\includegraphics`, `\ref{fig:...}`), and table ref
  - `Phase-05-DataReady.md` to confirm which CSVs are available
  - `Phase-05-Claims-vs-Data.md` to know which numbers need correction
  - Any existing TikZ/pgfplots sources under `figures/` so you can match style — search the repo for an established figure convention (font, colour palette, axis style) before inventing one

- [ ] Generate the figures required by §7. Preferred toolchain: pgfplots reading directly from CSV (most reproducible inside LaTeX); fallback: matplotlib in `scripts/render-figures.py` emitting PDF into `figures/`. Produce at minimum:
  - `figures/routing-cost-quality-frontier.{pdf,tex}` — cost vs. quality scatter or Pareto curve across haiku-4-5 / sonnet-4-6 / opus-4-7 tiers, sourced from the routing-evidence CSV
  - `figures/main-thread-cost-split.{pdf,tex}` — the 99.4/0.6 main-thread/dispatch split (a clean stacked-bar or sunburst, sourced from cache-stats CSV or routing-evidence CSV)
  - `figures/cache-read-creation-ratio.{pdf,tex}` — bar/line showing the 4.56× ratio across observation windows
  - `figures/plancache-projected-savings.{pdf,tex}` — projected vs. measured savings from plan caching layered on prefix caching
  - Each figure must include a caption describing the source CSV and data window

- [ ] Generate the tables for §7 as standalone `.tex` snippets in `figures/` (e.g. `figures/table-routing-rules.tex`) that the section file `\input`s. Cover:
  - Per-tier cost-per-token / quality matrix used in the cost-quality argument
  - Hit-rate summary for plan caching at multiple similarity thresholds (if data supports it)
  - Routing decision rules / classifier confusion summary (if a routing eval was run)

- [ ] Rewrite `blackrim-routing-caching-paper/sections/07-evaluation.tex`:
  - Replace every placeholder number with the matched measurement from `Phase-05-Claims-vs-Data.md`
  - Every quantitative sentence must reference the source CSV in a sentence-trailing comment (`% source: data/aggregated/X.csv col=Y`) so reviewers can audit
  - Reference figures via `\ref{fig:...}` and tables via `\ref{tab:...}`; use `\label{}` consistently
  - Structure: Setup → Routing results → Caching results → Combined savings → Threats to validity → Cost of measurement itself
  - Remove sentences that have no data support; either delete or move to §9 Future Work with a `\todo{}`

- [ ] Build and verify:
  - `make` in `blackrim-routing-caching-paper/`
  - Capture undefined-reference / undefined-citation warnings from the `.log` and `.blg`
  - Open the produced PDF and confirm every figure renders (no missing-graphics boxes) and §7 references resolve
  - Record build status, page count, and any open warnings to `Auto Run Docs/Initiation/Working/Phase-06-Build.md`

- [ ] Update `sections/00-abstract.tex` with the final measured headline numbers (routing savings, cache savings, combined). The abstract is the only other place these numbers should appear verbatim — the rest of the paper should reference §7. Note any abstract changes in the Phase-06 build log so they're easy to find in review.
