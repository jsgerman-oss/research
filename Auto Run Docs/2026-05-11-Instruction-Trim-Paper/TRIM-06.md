# TRIM-06 — Bibliography fill

## Goal
Populate `bib/refs.bib` with the citations referenced throughout the
sections (currently the file may be empty or near-empty), and verify
`make` builds without `LaTeX Warning: Citation ... undefined`.

## Context
- Paper dir: `/Users/jayse/research/blackrim-instruction-trim-paper/`
- biblatex backend = biber, style = numeric-comp (see main.tex preamble)
- Citation keys already used in sections (grep `\\cite{` across
  `sections/*.tex` to enumerate). Likely keys based on the current
  drafts:
  - `anthropic-cache` — Anthropic prompt-caching docs (used in §3)
  - `moa1landscape` — internal Blackrim research doc (used in §7
    of the routing-caching paper; may also be cited here)
  - others surfaced by grep
- The companion research docs referenced in the README live in
  `/Users/jayse/Code/blackrim/docs/research/`:
  - `tier-down-main-thread-landscape.md` (commit `ecfdcba`)
  - `cache-control-deep-dive.md` (commit `660054d`)
  - `multi-agent-optimization-landscape.md` (commit `aa9ddba`)
  - `cache-control-markers.md`
  - `model-cost-quality-landscape.md` (commit `59d333d`)
  These cite as `@misc` with `howpublished = {Blackrim repo, commit XXX}`.

## Tasks
- [ ] Enumerate every `\cite{...}` and `\citep{...}` key currently
  in `sections/*.tex`: run `grep -ohE '\\\\cite[a-z]*\\{[^}]+\\}'
  sections/*.tex | sort -u`. This is the **target set**; every key
  must end up in `refs.bib` or be removed from prose.
- [ ] Populate `bib/refs.bib` with biblatex entries for each key.
  Required external citations (verify URLs + arxiv IDs before
  including — do NOT fabricate):
  - **Anthropic prompt caching** — `@misc{anthropic-cache, ...}`,
    cite the Anthropic docs page.
  - **Static-prefix RAG / progressive disclosure** — find 1-2
    representative papers. Candidates: Lewis et al. RAG 2020
    (arXiv:2005.11401), Borgeaud et al. RETRO 2022.
  - **Context length / prefix bloat degradation** — Liu et al.
    "Lost in the Middle" (arXiv:2307.03172) is the standard cite.
  - **LLM compression** — LLMLingua family (Jiang et al.
    arXiv:2310.05736).
  - **Multi-agent LLM systems** — MetaGPT (arXiv:2308.00352),
    AutoGen (arXiv:2308.08155), ChatDev (arXiv:2307.07924) if §2
    surveys the space.
  - **Caching theory** — Belady's algorithm (1966) as the
    classical reference if §3 frames the residency model as a
    cache-replacement problem.
  Add internal docs as `@misc`-entries with `howpublished` field
  pointing at the Blackrim commit SHA.
- [ ] For each entry: use a stable, descriptive key (`@article{lewis2020rag,
  ...}` not `@article{key1, ...}`); fill `author`, `title`, `year`,
  and either `journal`/`booktitle` or `eprint`+`archivePrefix`+
  `primaryClass` for arxiv.
- [ ] Re-run sections grep: every `\cite{X}` must have matching
  `@type{X, ...}` in refs.bib.
- [ ] Build: `make clean && make`. Capture stderr; there should be
  ZERO `Citation 'X' undefined` warnings. If there are, either add
  the missing entry or drop the cite from prose (don't paper over
  with `?`).
- [ ] Build the bibliography list pdf-page check: open `main.pdf`,
  confirm references render with numeric labels and the per-cite
  links work.
- [ ] Commit: `bib(trim): populate refs.bib — N entries covering
  prompt caching, progressive disclosure, multi-agent systems,
  internal landscape docs`.

## Acceptance criteria
- Every `\cite{X}` key resolves.
- `make` completes without citation warnings.
- No fabricated authors, titles, years, or arxiv IDs. If you
  can't verify an external citation, drop the cite from prose
  and add a `\tothink` to find the right reference later.

## Failure mode
- If you find a `\cite{X}` whose intended reference you can't
  identify with high confidence: leave a `% TODO(cite): need
  reference for X — current prose claims Y` comment in the
  section file and remove the cite. Don't guess.
