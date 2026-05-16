# Phase 01: Foundation, Build Verification & Lit-Review Infrastructure

This phase establishes the working baseline for the two-paper research effort. We verify both LaTeX papers compile end-to-end, audit the current state of every section file (placeholder vs. substantive), and stand up a structured literature-review folder (YAML front-matter + wiki-links) that subsequent phases will populate. By the end of this phase you have buildable PDFs of both papers, a state-of-the-papers snapshot, and an organized home for arXiv notes — enough tangible scaffolding to make the rest of the playbook execute smoothly.

## Tasks

- [ ] Verify the LaTeX build toolchain for both papers:
  - Run `which latexmk pdflatex bibtex` and report what is installed
  - If `latexmk` is missing, record the install command (`brew install --cask basictex` or `mactex-no-gui`) into `_shared/BUILD-PREREQS.md` and proceed using available tools
  - From `blackrim-routing-caching-paper/`, run `make` and capture stdout/stderr
  - From `blackrim-instruction-trim-paper/`, run `make` and capture stdout/stderr
  - If a build succeeds, run `make wordcount` and save per-section word counts
  - Do NOT block the phase on build failure — record errors to `Auto Run Docs/Initiation/Working/build-log-YYYY-MM-DD.md` and continue

- [ ] Audit current draft state for both papers. For each paper create `Auto Run Docs/Initiation/Working/<paper-slug>-section-audit.md` with one row per section file listing:
  - File path and current line count
  - Status: `placeholder` (mostly TODO / lorem) / `partial` (some real content, gaps) / `substantive` (drafted with data)
  - Concrete gaps observed (missing citations, missing numbers, missing figure refs)
  - Notes flagged in the .tex itself (`% TODO`, `% FIXME`, `\todo{...}`)

- [ ] Inventory existing bibliography and data assets:
  - Parse `blackrim-routing-caching-paper/bib/refs.bib` and `blackrim-instruction-trim-paper/bib/refs.bib` — list every `@`-entry with its key, type, and any arXiv ID
  - Parse `_shared/refs-base.bib` the same way
  - Walk both papers' `data/raw/` and `data/aggregated/` directories — report which files exist, are empty, or are placeholders
  - Walk both papers' `figures/` directories — list any existing figure sources (TikZ/pgfplots) or generated PDFs/PNGs
  - Save consolidated inventory to `Auto Run Docs/Initiation/Working/bib-data-inventory.md`

- [ ] Stand up the shared literature-review knowledge graph. Create the folder tree below and a seed `_index.md` at each level:
  ```
  _shared/literature/
  ├── _index.md                    # top-level map; links to both paper indexes
  ├── routing-caching/
  │   ├── _index.md                # paper-specific entry point + open questions
  │   ├── papers/                  # one .md per arXiv paper (created in Phase 02)
  │   ├── themes/                  # synthesis docs grouping papers by topic
  │   └── synthesis.md             # rolling Related-Work draft
  └── instruction-trim/
      ├── _index.md
      ├── papers/                  # populated in Phase 03
      ├── themes/
      └── synthesis.md
  ```
  Each `_index.md` MUST include YAML front matter (`type: reference`, `tags`, `related`) and use `[[Wiki-Links]]` to connect to the corresponding paper README and synthesis doc. Search the repo first for any existing `literature/` or `research-notes/` folder convention — if one is present, mirror it rather than inventing a new shape.

- [ ] Create a paper-template for arXiv note files at `_shared/literature/_TEMPLATE-paper-note.md`. Front matter must include `type: research`, `arxiv_id`, `authors`, `year`, `venue`, `tags`, `cite_key` (matching the BibTeX key), `relevance` (high/medium/low), `relates_to_paper` (routing-caching / instruction-trim / both), and `related` (wiki-links). Body sections: TL;DR (3 lines), Method, Key Results, How It Connects To Our Paper, Quotes Worth Citing, Open Questions Raised. Phases 02–03 will copy this template per arXiv paper.

- [ ] Produce a consolidated baseline status report at `Auto Run Docs/Initiation/Working/Phase-01-Status.md` that summarizes:
  - Build status for each paper (pass / fail + error excerpt)
  - Section-level draft status table (placeholder / partial / substantive counts per paper)
  - Bib entries currently present, by paper
  - Data + figure inventory deltas (what exists vs. what each paper's README claims should exist)
  - The top 5 most urgent gaps for each paper, ranked by blocking-impact on final submission
  - Use YAML front matter (`type: report`, `created: 2026-05-11`, tags including both paper slugs) and wiki-link to both paper READMEs
