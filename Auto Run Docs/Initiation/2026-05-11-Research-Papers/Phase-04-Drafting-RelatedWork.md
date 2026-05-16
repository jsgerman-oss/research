# Phase 04: Convert Lit-Review Syntheses Into LaTeX §2 Related Work

Both papers already have skeleton `02-related-work.tex` files. This phase converts the markdown syntheses produced in Phases 02–03 into substantive, citation-dense LaTeX for the Related Work sections of both papers in parallel. The output is two compiled PDFs with a fully-drafted §2 backed by every cite-key that exists in the refreshed bib files.

## Tasks

- [ ] Read both lit-review synthesis docs end-to-end before drafting:
  - `_shared/literature/routing-caching/synthesis.md` and all files in `_shared/literature/routing-caching/themes/`
  - `_shared/literature/instruction-trim/synthesis.md` and all files in `_shared/literature/instruction-trim/themes/`
  - Read both current `sections/02-related-work.tex` files to preserve any already-good prose and identify what to replace vs. extend
  - Read the Phase-02 and Phase-03 coverage reports for known gaps

- [ ] Draft `blackrim-routing-caching-paper/sections/02-related-work.tex`. Structure as four to five subsections (`\subsection{...}`) covering: cost-quality routing for LLMs, cascade and confidence-based selection, caching for LLM systems (prefix + semantic), plan reuse and agent memory, and a "position of this work" close. Each subsection should:
  - Cite 4–8 papers using `\cite{key}` with keys that exist in `bib/refs.bib`
  - Compare-and-contrast — never list-and-summarize. Every cited work should be positioned against ours
  - End the position-of-work paragraph by stating the two specific gaps this paper closes (per-turn main-thread routing; plan-level semantic cache orthogonal to prefix cache)

- [ ] Draft `blackrim-instruction-trim-paper/sections/02-related-work.tex` with the same discipline. Subsections: prompt compression and context pruning, long-context vs. retrieval, progressive disclosure in agents, static-prefix economics and KV-cache, position of this work. Make the differentiation explicit: line-level instruction residency on a frequency-of-use signal, not token-level perplexity compression.

- [ ] Cross-check every `\cite{...}` invocation in both new §2 drafts against the refreshed bib files. For each paper run:
  ```bash
  grep -oE '\\cite\{[^}]+\}' sections/02-related-work.tex \
    | sed 's/\\cite{//;s/}//' | tr ',' '\n' | sort -u
  ```
  and verify each key has an entry in `bib/refs.bib`. Report any missing keys to `Auto Run Docs/Initiation/Working/Phase-04-CiteCheck.md` and either add the BibTeX entry (preferred, if a lit-review note exists) or remove the citation.

- [ ] Build both PDFs and capture the citation-resolution log:
  - Run `make` in `blackrim-routing-caching-paper/` and `blackrim-instruction-trim-paper/`
  - Capture `*.blg` warnings for undefined references or unused entries
  - Save the build summary (success/fail, undefined-cite count, undefined-ref count, page count for each PDF) to `Auto Run Docs/Initiation/Working/Phase-04-Build.md`
  - If either build fails, diagnose from the `.log` and fix — do not hand back a broken paper

- [ ] Run `make wordcount` on both papers and append per-section counts to `Auto Run Docs/Initiation/Working/Phase-04-Build.md`. Flag if §2 is now disproportionate (more than ~20% of total target wordcount — for a typical 8–10 page workshop paper, that means §2 above ~1500 words probably needs trimming).
