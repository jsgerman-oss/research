# TRIM-07 — Flesh §1 Introduction + §2 Related Work + §4 System

## Goal
Take §1, §2, §4 from skeleton-with-pointers to publication prose. By the
end of this phase the front matter (everything before §5 Algorithm) should
read coherently end-to-end. Word-count targets:
- §1 Introduction: 600-900 words
- §2 Related Work: 800-1100 words
- §4 System: 400-600 words

## Context — read every source before writing
- Paper dir: `/Users/jayse/research/blackrim-instruction-trim-paper/`
- Source material (already-written substrate; do NOT re-research from
  scratch — synthesise, don't restart):
  - `/Users/jayse/Code/blackrim/docs/research/multi-agent-optimization-landscape.md`
    (9000-word survey; §2 should compress to 5-8 paragraphs)
  - `/Users/jayse/Code/blackrim/docs/research/cache-control-deep-dive.md`
  - `/Users/jayse/Code/blackrim/docs/research/cache-control-markers.md`
    (the negative-result doc on Anthropic cache markers — §1 hook)
  - The current §3, §5, §6 prose in this paper (must match terminology)
- Read current placeholders before rewriting:
  - `sections/01-introduction.tex`
  - `sections/02-related-work.tex`
  - `sections/04-system.tex`
- TRIM-06 (bibliography) should be complete; if any `\cite{X}` you
  want to use isn't in refs.bib yet, add it as part of this phase
  (don't leave dangling cites).

## Tasks
- [ ] **§1 Introduction.** Rewrite `sections/01-introduction.tex` with
  this structure:
  1. *Hook* (1 paragraph). Open with the empirical fact: static-prefix
     multi-agent systems load the same instruction document into every
     spawn; for Blackrim that's CLAUDE.md at ~700 lines × 50 spawns/day
     × cache-miss multiplier. Cite a real number from
     `data/aggregated/trim-results.csv` or §6.
  2. *Problem statement* (1 paragraph). The naive solutions (manual
     pruning / no caching / LLM-based compression) each have a known
     failure mode. The middle ground — frequency-weighted progressive
     disclosure — has no public methodology.
  3. *Approach* (1 paragraph). Conservative trim algorithm: only two
     fidelity-neutral interventions (redundancy removal,
     externalisation-with-pointer). Cite §5.
  4. *Contributions* (4 bullets). (i) cost model decomposing static-
     prefix loading under cache hit rate ρ, (ii) conservative algorithm,
     (iii) measured 21.5%/17.1% reduction on Blackrim with fidelity
     check, (iv) reproducibility artifacts.
  5. *Paper roadmap* (1 short paragraph).
- [ ] **§2 Related Work.** Rewrite `sections/02-related-work.tex`.
  Organise as 4-5 paragraphs, each surveying one strand:
  1. *Prompt caching* — Anthropic's cache_control markers, prefix
     caching in vLLM/SGLang, the 5-min TTL constraint.
  2. *Progressive disclosure / RAG* — Lewis 2020 → RETRO → modern
     retrieval-augmented systems. The key difference: those retrieve
     *facts*; we externalise *instructions*. Discuss why that's a
     different problem (instruction-following is more brittle to
     missing context).
  3. *Prefix bloat / context degradation* — "Lost in the Middle"
     (Liu et al. 2307.03172); the empirical reason short prefixes
     are not just cheaper but often *better*.
  4. *LLM-based compression* — LLMLingua, prompt distillation. Note
     the missing benchmark: no public eval suite for compressed
     instruction documents specifically. This is the gap the
     conservative-trim methodology sidesteps.
  5. *Multi-agent systems with static prefixes* — MetaGPT, AutoGen,
     ChatDev architectures. None measure per-section instruction
     residency cost; that's the paper's contribution.
- [ ] **§4 System.** Rewrite `sections/04-system.tex`. Cover:
  1. *Blackrim overview* (2 paragraphs). Admiral + 6 crew + workers
     architecture; static-prefix loading via Claude Code SDK; CLAUDE.md
     as the canonical instruction document.
  2. *Telemetry* (1 paragraph). What `pull-telemetry.py` measures
     (commit-level CLAUDE.md size + bd lifecycle); what it doesn't
     (per-section attribution requires `aggregate-section-residency.py`,
     from TRIM-02). This is the system-under-measurement description;
     keep it descriptive, not prescriptive.
- [ ] Update `sections/00-abstract.tex` to reflect the now-fleshed
  introduction. Abstract structure: motivation (1 sentence), method
  (2 sentences), result (2 sentences with the 21.5%/17.1% number and
  fidelity Δ from TRIM-04 if available, else "qualitative fidelity
  check passed"), artifacts (1 sentence on reproducibility). Target
  150-200 words.
- [ ] Build: `make clean && make`. Verify no warnings beyond
  citation/figure ones that should be resolved by TRIM-05/06.
- [ ] Run `make wordcount` and record the per-section counts in
  the commit body.
- [ ] Commit: `prose(trim): flesh §1 intro, §2 related work, §4
  system; update §0 abstract`.

## Acceptance criteria
- Each section meets its word-count target ±20%.
- Every `\cite{}` resolves (add to refs.bib if needed).
- No `\tothink{}` markers remain in §1, §2, §4.
- §0 abstract names the concrete result (21.5%/17.1% reduction).

## Style guidance
- Past tense for measurements ("We measured 21.5% reduction"), present
  tense for methodology ("The algorithm classifies each section").
- Don't repeat between §1 and §2: §1 motivates with the system's empirical
  problem, §2 surveys what others have done. If a sentence could fit in
  either, it usually belongs in §2.
- Avoid "we observe", "we note" filler. State the observation directly.
