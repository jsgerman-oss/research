# Phase 03: Literature Review — Instruction-Trim Paper

Deep arXiv-grounded literature review for `blackrim-instruction-trim-paper`. The paper's contribution is a **frequency-weighted residency model** for deciding what stays in the static instruction prefix vs. externalizes to on-demand Read calls — measured at ~17–21% line reduction on CLAUDE.md with no fidelity loss. This phase builds the knowledge graph of prior work on prompt compression, context engineering, progressive disclosure, and prefix/KV-cache economics. Output feeds Phase 04 (Related Work drafting).

## Tasks

- [ ] Survey prompt-compression and context-pruning literature on arXiv. Use the existing template at `_shared/literature/_TEMPLATE-paper-note.md` and write one file per paper at `_shared/literature/instruction-trim/papers/<arxiv-id>-<short-slug>.md`. Cover these clusters:
  - **Hard / soft prompt compression**: LLMLingua (2310.05736), LongLLMLingua (2310.06839), LLMLingua-2 (2403.12968), AutoCompressors, ICAE (In-Context Autoencoder)
  - **Selective context / pruning**: Selective Context (2304.12102), LeanContext, RECOMP
  - **Token-level importance scoring**: LLMLingua's contrastive scoring, attention-based pruning, perplexity-based pruning
  - For each capture method, compression ratio, downstream task degradation, and "How it relates to instruction-residency vs. on-demand-read"

- [ ] Survey context-engineering, RAG-vs-context, and prompt-design literature in `_shared/literature/instruction-trim/papers/`. Cover:
  - **Long-context vs. retrieval tradeoffs**: Lost in the Middle (2307.03172), Needle-in-a-Haystack analyses, RAG-vs-long-context recent papers
  - **Progressive disclosure / lazy loading for prompts**: any work on conditional prompt sections, retrieval-on-demand within an agent loop
  - **Prefix-tuning / static-prefix economics**: prefix tuning (2101.00190), P-Tuning, plus KV-cache economics papers
  - **Instruction-following + faithfulness when context changes**: how trimming affects instruction adherence

- [ ] Survey multi-agent system papers where instruction documents play a structural role:
  - AutoGen, MetaGPT, LangGraph, CrewAI, ChatDev, Voyager — note how each handles shared system prompts / role instructions and whether residency is fixed or dynamic
  - Tool-using agent literature where docs are loaded into prefix (ReAct, Toolformer, Gorilla)
  - Any work specifically on multi-agent prompt economics or per-spawn overhead

- [ ] Triangulate against the companion Blackrim research docs referenced in `blackrim-instruction-trim-paper/README.md`:
  - Summarize `docs/research/cache-control-markers.md` (the negative-result investigation) from `/Users/jayse/Code/blackrim/` if readable
  - Summarize relevant parts of `multi-agent-optimization-landscape.md`
  - Cross-link each Blackrim research doc via wiki-links inside the theme syntheses

- [ ] Write theme-level synthesis docs at `_shared/literature/instruction-trim/themes/`. Each is standalone markdown with YAML front matter (`type: analysis`, tags, related). Produce at least:
  - `compression-vs-trimming.md` — how our residency model differs from token/sentence-level compressors (we operate at the instruction-document line level with a frequency-of-use signal, not perplexity)
  - `frequency-weighted-residency.md` — formalize the core idea, compare to LRU/LFU caching analogues from systems research, identify nearest precedents
  - `static-prefix-economics-in-multiagent.md` — per-spawn fixed-cost amortization, KV-cache hit-rate dependence, why this matters at fleet scale
  - `progressive-disclosure-patterns.md` — taxonomy of on-demand-load patterns in agent literature; where line-by-line Read-on-demand fits

- [ ] Update `blackrim-instruction-trim-paper/bib/refs.bib`:
  - Add BibTeX entries for every paper that earned a note
  - Match cite_keys to the front-matter `cite_key` field
  - Dedupe against `_shared/refs-base.bib`; preserve existing entries
  - arXiv-only → `@misc` with `eprint`+`archivePrefix={arXiv}`; published → proper `@inproceedings`/`@article`

- [ ] Draft Related-Work skeleton at `_shared/literature/instruction-trim/synthesis.md` organized into the sub-sections §2 will need (Prompt compression and context pruning, Long-context vs. retrieval, Progressive disclosure in agents, Static-prefix economics and KV caching, Position of this work). Cite via wiki-links to theme docs and list intended cite-keys. Phase 04 will convert this into `sections/02-related-work.tex`.

- [ ] Produce coverage report at `Auto Run Docs/Initiation/Working/Phase-03-Coverage.md`:
  - Papers reviewed by cluster
  - Citations the existing `02-related-work.tex` relies on that still lack a note
  - Notable exclusions + rationale
  - Whether the README's "21.5% line reduction without instruction-fidelity loss" claim has stronger or weaker prior-art framing now (look specifically for prior compression papers that report comparable trims with fidelity metrics — those are the toughest baselines)
