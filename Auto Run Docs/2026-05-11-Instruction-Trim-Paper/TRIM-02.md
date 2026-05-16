# TRIM-02 — Per-section attribution telemetry

## Goal
Back the §5 algorithm's "worked example" (worktree-isolation 75→16 lines)
and the §3 frequency-weighted decision rule with **measured per-section
data**, not asserted numbers. Extend the telemetry pipeline to emit a CSV
that has one row per CLAUDE.md top-level section, with line counts at each
of (Baseline / Wave 1 / Wave 2) and a hand-applied classification of
{must-resident, frequency-deciding, redundant}.

## Context — what to read first
- Paper dir: `/Users/jayse/research/blackrim-instruction-trim-paper/`
- TRIM-01 must have completed first — this phase reads
  `data/aggregated/trim-results.csv` to find the SHAs to walk.
- The §5 worked example currently lives at the bottom of
  `sections/05-algorithm.tex` as a `\tothink` placeholder.
- CLAUDE.md uses Markdown `##`-level (or `#`-level — check) headings to
  partition sections. The current pre-trim CLAUDE.md is at
  `git -C /Users/jayse/Code/blackrim show <baseline-sha>:CLAUDE.md`.

## Tasks
- [ ] Read the baseline CLAUDE.md
  (`git -C /Users/jayse/Code/blackrim show <baseline-sha>:CLAUDE.md | head -50`)
  to confirm heading depth. The aggregator should split on the heading
  level that yields ~10-30 sections (too few = useless, too many = noisy).
  Standard Markdown is `##`-level; verify before coding.
- [ ] Create `scripts/aggregate-section-residency.py`. Inputs: paths to
  the baseline and Wave-2 CLAUDE.md contents (provided as CLI args, or
  read from the same SHAs that `pull-telemetry.py` already discovered).
  Outputs CSV with columns: `section_title, baseline_lines, wave1_lines,
  wave2_lines, delta_lines, delta_pct, classification, externalised_to`.
  The `classification` and `externalised_to` columns are empty initially —
  filled by the next task.
- [ ] Run the new script: `python scripts/aggregate-section-residency.py
  --repo /Users/jayse/Code/blackrim
  --baseline-sha <from-trim-results.csv-row-1>
  --wave1-sha <from-trim-results.csv-wave1-row>
  --wave2-sha <from-trim-results.csv-last-row>
  > data/aggregated/section-residency.csv`. Verify it has one row per
  top-level section in the baseline.
- [ ] Hand-fill the `classification` column for each row using the §5
  taxonomy: **must-resident** (every spawn semantically needs this —
  e.g. "File Layout", "Commit Path"), **frequency-deciding** (read-mostly,
  large — e.g. "Worktree Isolation deep dive"), **redundant** (duplicated
  elsewhere — e.g. "PRODUCT.md duplicate", "Customisation fork"). For
  rows that were externalised, fill `externalised_to` with the canonical
  file path (e.g. `mkdocs/operations/worktree-guard.md`).
- [ ] Update the §5 `\tothink{}` worked example
  (`sections/05-algorithm.tex` near line 63-65) to a real subsection
  citing 2-3 rows from `section-residency.csv` (the Worktree-Isolation
  row is the headline; pick one redundancy-removal row + one frequency-
  deciding keep-resident row for contrast).
- [ ] Update §3 (`sections/03-problem-formulation.tex`) — the decision
  rule Eq.\,\eqref{eq:decision} substitutes ρ=0.85 and α=0.10 to give
  the f·r < 0.235·|s| break-even. Add a one-paragraph "Empirical fit"
  remark right after that equation citing a specific section from
  `section-residency.csv` where the inequality holds (i.e. the section
  the algorithm CORRECTLY externalised) and ideally one row where it
  doesn't (a section the algorithm correctly KEPT). Cite as
  `\Cref{tab:section-residency}` and add the table in the appendix.
- [ ] Add a longtable in `sections/A-appendix.tex` that renders the
  full `section-residency.csv` for reproducibility. Label
  `tab:section-residency`.
- [ ] Commit: `data(trim): per-section residency CSV + §3/§5 worked
  examples grounded in measurement`.

## Acceptance criteria
- `data/aggregated/section-residency.csv` exists with one row per
  baseline section and all rows have a non-empty `classification`.
- §5 worked-example subsection cites at least 2 specific rows by name.
- §3 has the empirical-fit remark.
- §A appendix renders the full table.

## Out of scope
- Automating the classification (requires the eval suite from TRIM-03).
- Updating the cost-model numbers themselves (TRIM-01 already did).
