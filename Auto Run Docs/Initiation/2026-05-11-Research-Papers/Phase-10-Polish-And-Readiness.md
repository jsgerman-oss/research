# Phase 10: Polish & Conference-Readiness Assessment — Both Papers

The drafts are complete. This phase tightens prose, verifies every claim against its data source one last time, ensures reproducibility holds from a cold checkout, and produces a conference-readiness scorecard for each paper. The user can use the scorecard to decide whether to submit to a venue or keep the paper as an internal writeup.

## Tasks

- [ ] Run a claim-traceability audit on both papers. For each, grep every quantitative claim in all `sections/*.tex` files (`\d+(?:\.\d+)?%`, `\d+\.\d+\times`, large absolute numbers) and confirm each is either:
  - Backed by a sentence-trailing `% source: data/aggregated/X.csv col=Y` comment introduced in Phase 06/07
  - Or — for numbers from cited prior work — accompanied by a `\cite{}` to the source
  - Or — for derived numbers — accompanied by a footnote explaining the derivation
  - Save audit table to `Auto Run Docs/Initiation/Working/Phase-10-Claim-Audit.md`. Any row without a source category is a blocker for submission

- [ ] Prose polish pass on both papers. Read each paper top-to-bottom and tighten:
  - Hedge words ("might", "could", "we believe") — either commit to the claim with evidence or move to future work
  - Redundant phrasing across §intro / §evaluation / §discussion — each load-bearing fact should appear in only one place (others reference it)
  - Active voice over passive where it sharpens the claim
  - Consistent tense (papers conventionally describe completed work in past tense, the system in present tense)
  - Apply changes directly to the `.tex` files; no shadow-edits
  - Do not introduce new content — this is polish, not extension. If you find a gap, log it to `Phase-10-Open-Issues.md` rather than fixing in-place

- [ ] Reproducibility cold-run. Simulate a fresh reviewer trying to reproduce the empirical results:
  - For each paper, in a temp working directory: `cd $(mktemp -d) && rsync -a ~/research/<paper>/ ./ && make data && make` — record whether `make data` produces the expected CSVs and `make` produces the expected PDF
  - Capture missing dependencies, hard-coded paths that break (`/Users/jayse/Code/blackrim` is a likely offender), and any required env vars
  - Document the cold-run procedure precisely in each paper's `README.md` under a "Reproducing the results" section, including the workaround for any unportable paths discovered

- [ ] LaTeX hygiene sweep for both papers:
  - No `\todo{}`, `% TODO`, or `% FIXME` left anywhere
  - All `\ref{}` and `\eqref{}` resolve (zero "Reference undefined" warnings in `.log`)
  - All `\cite{}` resolve (zero "Citation undefined" in `.blg`)
  - No unused BibTeX entries (the `.blg` will list them; remove or justify)
  - Spell-check (`aspell` or equivalent on each `.tex` file); fix typos
  - Run `chktex` if available and address relevant warnings
  - Save the clean-build evidence to `Auto Run Docs/Initiation/Working/Phase-10-CleanBuild.md`

- [ ] Cross-paper consistency final check. Both papers will likely be read together. Verify:
  - The glossary in `_shared/GLOSSARY.md` matches usage in both papers' final drafts
  - The cite-key intersection has identical BibTeX (same authors, title, venue, year)
  - The sibling-reference sentence in each intro/discussion is present and accurate
  - Any shared figure style (palette, font, axis) matches across the two PDFs
  - Log findings to `Auto Run Docs/Initiation/Working/Phase-10-CrossPaper.md`

- [ ] Produce per-paper conference-readiness scorecards at `Auto Run Docs/Initiation/Working/Phase-10-Readiness-RoutingCaching.md` and `Auto Run Docs/Initiation/Working/Phase-10-Readiness-InstructionTrim.md`. Each scorecard uses YAML front matter (`type: report`, `created: 2026-05-11`, tags) and rates the paper on:
  - **Contribution clarity** (1–5): is the headline contribution crisp enough to land in a 3-sentence pitch?
  - **Evidence strength** (1–5): how robust is the empirical backing — single-org telemetry vs. multi-org, controlled experiment vs. observational
  - **Reproducibility** (1–5): did the cold-run produce identical CSVs/figures
  - **Prior-art coverage** (1–5): are the strongest competing approaches all cited and differentiated
  - **Writing polish** (1–5): is the prose submission-ready or just internal-ready
  - For each axis include a one-sentence justification and the next-best lever to raise the score by one point
  - End with a venue recommendation: arXiv preprint now / arXiv + workshop submission / hold for full conference / not-yet-ready

- [ ] Produce a unified Playbook completion summary at `Auto Run Docs/Initiation/Working/Phase-10-Playbook-Complete.md`:
  - One section per phase (01–10) with a one-paragraph "what was produced" recap
  - Per-paper final artifact list: PDF page count, section word counts, CSV inventory, figure inventory, bib entry count
  - The combined readiness scorecard summary (table form: 5 axes × 2 papers)
  - Top 3 next actions for the user, ranked, with rough effort estimates — e.g. "submit routing-caching to MLSys workshop (low effort, deadline X)" vs. "extend instruction-trim with multi-org telemetry (medium effort, blocks full conference submission)"
  - YAML front matter with `type: report`, `tags: [playbook, completion]`, and wiki-links to both paper READMEs and both readiness scorecards
