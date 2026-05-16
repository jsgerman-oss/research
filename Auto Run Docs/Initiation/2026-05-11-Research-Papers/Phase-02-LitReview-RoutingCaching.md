# Phase 02: Literature Review — Routing & Caching Paper

Deep arXiv-grounded literature review for `blackrim-routing-caching-paper`. The paper has two contributions: per-turn model routing (FrugalGPT / RouteLLM lineage) and agentic plan caching (semantic plan-level cache complementary to prefix caching). This phase produces a structured knowledge graph of every prior work that bears on either contribution, with one markdown note per paper, theme syntheses, and a refreshed BibTeX. Output feeds Phase 04 (Related Work drafting).

## Tasks

- [ ] Survey routing literature on arXiv and produce structured notes. Before writing new notes, read `_shared/literature/_TEMPLATE-paper-note.md` (created Phase 01) and reuse its front-matter schema. For each paper write one file at `_shared/literature/routing-caching/papers/<arxiv-id>-<short-slug>.md`. Cover these clusters:
  - **Foundational cost-quality routing**: FrugalGPT (2305.05176), RouteLLM (2406.18665), Tryage (2308.11601), Hybrid LLM (2404.14618), AutoMix (2310.12963)
  - **Confidence-based / cascade routing**: Cascading (2410.13284), Mixture-of-Experts gating papers, EcoAssistant
  - **Routing for agents specifically**: anything from 2024–2026 on tier selection inside multi-agent systems
  - For each paper capture method, datasets evaluated, headline cost/quality numbers, and an explicit "How it relates to per-turn main-thread routing" paragraph

- [ ] Survey caching literature on arXiv and produce structured notes in `_shared/literature/routing-caching/papers/`. Cover:
  - **Prefix / KV caching**: Anthropic prompt caching, DeepSeek MLA, vLLM prefix caching, RadixAttention
  - **Semantic caching**: GPTCache, SCALM, MeanCache, semantic similarity caches for LLM outputs
  - **Plan caching specifically**: NeurIPS 2025 *Agentic Plan Caching* (this is the headline citation — give it a dedicated rich note), plus any related "tool plan reuse" or "trajectory caching" work
  - **Adjacent**: speculative decoding caches, retrieval caches, embedding caches

- [ ] Triangulate against the companion Blackrim research docs referenced in `blackrim-routing-caching-paper/README.md`:
  - If readable, summarize key findings from `docs/research/tier-down-main-thread-landscape.md`, `cache-control-deep-dive.md`, `multi-agent-optimization-landscape.md`, and `model-cost-quality-landscape.md` at `/Users/jayse/Code/blackrim/`
  - If not readable from this repo, note the dependency and synthesize from the paper README's summary
  - Cross-link each Blackrim research doc as a wiki-link reference inside the relevant theme synthesis

- [ ] Write theme-level synthesis docs at `_shared/literature/routing-caching/themes/`. Each is a standalone markdown with YAML front matter (`type: analysis`, tags, related), wiki-linking the underlying paper notes. Produce at least:
  - `cost-quality-frontier.md` — how prior work characterizes the Pareto frontier across tiers, where our 99.4/0.6 main-thread split + measured tier costs sit on it
  - `routing-decision-mechanisms.md` — taxonomy: scoring head / classifier / cascade / similarity-retrieval / confidence threshold; identify which family our approach belongs to and the closest precedents
  - `semantic-cache-design-space.md` — embedding choice, similarity threshold, staleness/eviction, hit-rate vs. correctness tradeoff
  - `plan-caching-vs-prefix-caching.md` — orthogonality argument (this is the central novelty claim of contribution #2 — make it rigorous)

- [ ] Update `blackrim-routing-caching-paper/bib/refs.bib`:
  - Add a BibTeX entry for every paper that earned a note in `papers/`
  - Use consistent cite keys matching the `cite_key` field in each note's front matter
  - Preserve existing entries; deduplicate any overlap with `_shared/refs-base.bib`
  - For arXiv-only papers use `@misc` with `eprint`, `archivePrefix={arXiv}`, `primaryClass`; for published work use the published `@inproceedings` / `@article`

- [ ] Draft a Related-Work skeleton at `_shared/literature/routing-caching/synthesis.md` organized into the same sub-sections the final §2 will need (Cost-quality routing for LLMs, Cascade and confidence-based selection, Caching for LLM systems, Plan reuse and agent memory, Position of this work). Each paragraph cites the theme docs via wiki-links and lists the cite-keys it intends to use in the LaTeX version. This is the bridge artifact Phase 04 will convert into `sections/02-related-work.tex`.

- [ ] Produce a coverage report at `Auto Run Docs/Initiation/Working/Phase-02-Coverage.md` listing:
  - Total papers reviewed, by cluster
  - Open citations the paper's existing `02-related-work.tex` currently relies on that lack a note (gap to close before drafting)
  - Notable papers deliberately excluded and why
  - Any claim in the README's "Estimated 35–50% cost reduction" or "50% additional cost reduction / 27% latency" that now has stronger or weaker prior-art support than initially stated
