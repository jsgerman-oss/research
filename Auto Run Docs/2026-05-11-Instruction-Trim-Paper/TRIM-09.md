# TRIM-09 — §0 abstract + Appendix + final polish

## Goal
Final-mile work: ensure §0 abstract reflects every measured number from
the now-complete paper, fill the Appendix with reference material, kill
remaining `\tothink` markers, and produce a clean `main.pdf` that builds
warning-free with the bibliography rendered.

## Context — read first
- Paper dir: `/Users/jayse/research/blackrim-instruction-trim-paper/`
- Current Appendix placeholder: `sections/A-appendix.tex`
- All prior phases TRIM-01..08 must be complete. Run `grep -rn '\\tothink'
  sections/` first to enumerate every remaining red marker — these MUST
  go to zero by the end of this phase. If any `\tothink` can't be resolved,
  EITHER do the work it asks for OR delete the surrounding sentence and
  flag in §7 limitations.

## Tasks
- [ ] **Abstract.** Rewrite `sections/00-abstract.tex`. Target 150-200
  words. Required content:
  1. Setting: static-prefix multi-agent coding systems load the same
     instruction document into every spawn.
  2. Problem: that document grows over time, and the cache hit rate ρ
     compounds wasted tokens.
  3. Method: frequency-weighted progressive disclosure with a
     conservative trim algorithm (redundancy + externalisation).
  4. Result: 21.5% line / 17.1% char reduction on Blackrim's CLAUDE.md
     with measured fidelity Δ from TRIM-04 (state the number; if Δ
     was within ε, say "within tolerance"; if not, say "Δ = X.X% on
     dimension Y, see §7 limitations").
  5. Artifacts: scripts + CSVs + this paper repo are public.
- [ ] **Appendix §A.** Rewrite `sections/A-appendix.tex`. Sections:
  1. **§A.1 — Full pre/post diff stats.** Render the full
     `section-residency.csv` as a `longtable` (already added in
     TRIM-02 if you followed that phase; verify it's present).
  2. **§A.2 — Fidelity eval prompt set.** Embed the prompt set
     from `scripts/eval-fidelity/prompts.yml` as a `lstlisting`
     block. This is what makes the fidelity claim auditable.
  3. **§A.3 — Reproducibility cookbook.** Step-by-step shell
     transcript from clean clone to built PDF. Should be 6-10
     lines. This is THE acceptance bar for "reproducible".
  4. **§A.4 — Decision-rule worked examples.** Pick 3 sections
     from `section-residency.csv` — one in each classification
     bucket — and show the inequality from Eq.\,\eqref{eq:decision}
     evaluated with measured `f`, `r`, `|s|` values, and the
     resulting keep/externalise decision. Demonstrates the rule
     ISN'T circular post-hoc.
- [ ] **`\tothink` sweep.** Run `grep -rn '\\tothink' sections/`.
  For each remaining marker:
  - If the work-it-describes was completed by a prior phase: delete
    the marker (the text it produced is now in-place).
  - If the work wasn't done and won't be done before submission:
    EITHER do it now if scope permits (<15 min) OR delete the
    surrounding sentence + add a future-work entry referencing it.
    Do NOT leave `\tothink` in a "submission-ready" draft.
- [ ] **Final build + check.** Run `make clean && make 2>&1 | tee
  /tmp/trim-build.log`. Verify:
  - `main.pdf` exists and has page count ~15-25.
  - No `LaTeX Warning: Reference X undefined`.
  - No `LaTeX Warning: Citation X undefined`.
  - No `Overfull \hbox` exceeding 50pt (small overfulls are OK).
  - All three figures render in their expected sections.
- [ ] **Cosmetics.** Run `make wordcount` and confirm the per-section
  distribution roughly matches venue norms (intro ~10%, related work
  ~12%, eval ~25%, discussion ~15%; if any section is >2x its sibling,
  trim or expand). Re-pass for any consistency issues spotted on the
  full read-through (terminology drift between §3/§5/§6 is the most
  common; the macros `\prefix`, `\section_{i}`, `\frequency`, `\size`,
  `\readsize`, `\cachehit` should be the only way these notions are
  written in math mode).
- [ ] **README.** Update `README.md` "Status" section to reflect
  draft-complete: change "Section content is placeholder-with-substantive-
  where-data-exists" to "Draft complete; pending external review."
  Update build instructions if anything changed.
- [ ] **Final commit.** Single commit:
  `release(trim): draft v1 complete — abstract + appendix + final
  polish; pdf builds clean`.
- [ ] **Bundle.** Run `Skill(paper-bundle)` to produce
  `blackrim-instruction-trim-paper.zip` at the repo root, ready for
  Overleaf upload. (Or: `cd .. && zip -r blackrim-instruction-trim-paper.zip
  blackrim-instruction-trim-paper -x '**/__pycache__/*' '**/build/*'`.)

## Acceptance criteria
- `main.pdf` builds clean (no warnings).
- Zero `\tothink` markers in `sections/`.
- Abstract names the concrete result + fidelity Δ.
- §A Appendix contains the four subsections above.
- `blackrim-instruction-trim-paper.zip` is built at the repo root.

## What this phase does NOT do
- Submission packaging beyond the zip (no arxiv upload).
- Author-affiliation/email final formatting (already in title).
- LICENSE file (a TODO in README; can wait for actual submission).
