# Phase 09: Draft Intro, Discussion, Future-Work, Conclusion & Abstract — Both Papers

By this phase the meat of both papers exists: lit review (§2), problem + methods + algorithms (§3–§6), evaluation with real data (§7 or §6 + §7). This phase writes the narrative wrappers — abstracts, introductions, discussions, future-work, conclusions — and ensures both papers read end-to-end as coherent submissions.

## Tasks

- [ ] Re-read each paper end-to-end before writing narrative sections:
  - `blackrim-routing-caching-paper/main.tex` (compile a fresh PDF first via `make`)
  - `blackrim-instruction-trim-paper/main.tex` (likewise)
  - The two abstracts are the natural anchor — they should be the last thing you finalize, not the first
  - The previously-written methods + evaluation give you the load-bearing claims the intro must motivate and the discussion must contextualize

- [ ] Draft the introductions for both papers. Each `01-introduction.tex` should follow the standard structure: problem framing → why it matters → why it is hard → existing approaches' limitations → our contribution (3–4 enumerated bullets) → paper roadmap. Specifically:
  - **Routing-caching**: lead with the 99.4/0.6 main-thread cost reality and the static-prefix multi-agent setting. Contributions: (i) per-turn classifier-based routing for the main thread; (ii) semantic plan caching orthogonal to prefix caching; (iii) empirical measurement on production telemetry; (iv) reproducibility artifacts
  - **Instruction-trim**: lead with the per-spawn fixed-prefix cost in multi-agent systems and how it scales with fleet size. Contributions: (i) frequency-weighted residency model; (ii) measurement methodology; (iii) applied result on CLAUDE.md with fidelity preserved; (iv) reproducibility artifacts
  - Every claim in the intro must be supported by §2 (prior work), §5/6 (method), or §6/7 (evaluation)

- [ ] Draft the discussion sections (`08-discussion.tex` for routing-caching, `07-discussion.tex` for instruction-trim). Cover:
  - Interpretation of headline results — not restatement
  - Threats to validity already not in §evaluation (generalizability, telemetry-window bias, single-org evidence, model-version coupling)
  - Practical guidance: when our approach helps, when it doesn't (be honest about edge cases)
  - Failure modes observed and how the design handles or fails to handle them
  - Avoid weasel-language ("we believe...") — either back the claim with §evaluation or move it to future work

- [ ] Refresh `09-future-work.tex` (routing-caching) / `08-future-work.tex` (instruction-trim). The skeletons already have content from the scaffold commits — keep what's good and add:
  - Items flagged `\todo{}` during Phases 06–08
  - Items where the data didn't yet support a claim but the mechanism is plausible
  - Items derived from the multi-agent-optimization-landscape research doc that are "next" but not in scope here
  - Be specific — "extend to other models" is weak; "evaluate residency stability under model-version churn at monthly cadence" is strong

- [ ] Draft the conclusions (`10-conclusion.tex` routing-caching, `09-conclusion.tex` instruction-trim). One-page max. Restate the contribution, the strongest empirical claim, and one forward-looking sentence. No new material.

- [ ] Finalize the abstracts (`00-abstract.tex` in both papers). 150–250 words each. Structure: context → gap → approach → headline result → implication. Numbers in the abstract must match `Phase-06-Build.md` and `Phase-07-Build.md` exactly. If a number changed during evaluation rewriting, the abstract is the last place to catch it.

- [ ] Build, verify, and word-count both papers:
  - `make` in both directories
  - `make wordcount` and capture per-section totals
  - Check that the total page count is appropriate for the target venue (workshop typically 4–8 pages; full conference 8–12; arXiv preprint flexible)
  - Save the final-draft summary to `Auto Run Docs/Initiation/Working/Phase-09-FullDraft.md`: page count, word count, section status (all should be "substantive" now), any remaining `\todo{}` markers, any remaining undefined references

- [ ] Verify cross-paper consistency. These two papers are explicitly sibling contributions and may share citations, terminology, and even some prose. Run the following checks and record findings in the same Phase-09 summary doc:
  - Cite-key overlap between `blackrim-routing-caching-paper/bib/refs.bib` and `blackrim-instruction-trim-paper/bib/refs.bib` — overlapping keys must reference the same paper (no key collisions or version drift)
  - Terminology consistency: "static prefix", "main thread", "dispatch", "fleet scale", "spawn" — pick one phrasing per concept and use it identically across both papers; record the glossary in `_shared/GLOSSARY.md` if not already present
  - Cross-reference: each paper's intro and discussion should reference the other (one sentence is enough) so a reader of one is aware of the sibling
