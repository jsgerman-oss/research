# TRIM-08 — Flesh §7 Discussion + §8 Future Work + §9 Conclusion

## Goal
Take the back-matter (§7-§9) from skeleton to publication prose. By the
end of this phase, every section between §6 Evaluation and the
bibliography reads coherently. Word-count targets:
- §7 Discussion: 600-900 words
- §8 Future Work: 500-700 words
- §9 Conclusion: 200-300 words

## Context — read first
- Paper dir: `/Users/jayse/research/blackrim-instruction-trim-paper/`
- Source material for future-work entries:
  `/Users/jayse/Code/blackrim/docs/research/multi-agent-optimization-landscape.md`
  has a ranked top-10 list of optimisation directions. Several are direct
  extensions of this paper (learned compression, dynamic loading,
  cross-session prefix sharing).
- Current placeholders:
  - `sections/07-discussion.tex`
  - `sections/08-future-work.tex`
  - `sections/09-conclusion.tex`
- TRIM-04 fidelity results matter for §7 — limitations section depends
  on whether the measured Δ was within ε or not.

## Tasks
- [ ] **§7 Discussion.** Rewrite `sections/07-discussion.tex`.
  Structure as 4 subsections:
  1. *Why conservative beat learned compression* — argue that
     fidelity-neutral interventions (redundancy removal +
     externalisation) deliver most of the easy gain on real
     instruction documents because human-authored CLAUDE.md
     files tend to accumulate duplication and over-explained
     edge cases. Cite specific section examples from
     `data/aggregated/section-residency.csv`.
  2. *Generalisability* — to what extent does Blackrim's
     21.5%/17.1% transfer to other multi-agent systems? Argue
     it depends on (a) prefix size, (b) duplication rate in the
     original doc, (c) availability of external homes for
     externalised content. List 2-3 specific signals practitioners
     can use to estimate ROI before applying the algorithm.
  3. *Limitations*. (a) Single-system case study; (b) eval-suite
     dimension coverage; (c) static-only — no measurement of
     in-conversation dynamic disclosure costs; (d) cache hit
     rate ρ assumed constant.
  4. *Threats to validity*. The measurement repo is also the
     author's daily-driver, so the trim was applied with the
     author's domain knowledge. A held-out maintainer applying
     the algorithm cold might classify sections differently.
     Flag this explicitly.
- [ ] **§8 Future Work.** Rewrite `sections/08-future-work.tex`.
  5-7 entries, each ~1 paragraph. Suggested entries (refine
  against `multi-agent-optimization-landscape.md`):
  1. *Learned compression* with a benchmark — propose building
     the missing instruction-doc compression eval and using it
     to compare conservative trim vs LLMLingua-style compression.
  2. *Dynamic loading via tool calls* — externalising sections
     all the way: have the agent retrieve sections on-demand
     via a `read_instruction(section_id)` tool. Trade-off: latency
     vs token cost.
  3. *Cross-session prefix sharing* — for multi-instance
     deployments, share the prompt cache across instances. Open
     question per Anthropic's docs: cache scope (per-API-key vs
     per-org).
  4. *Per-section frequency estimation from logs* — replace the
     hand-classified `frequency` column in `section-residency.csv`
     with a measured fraction-of-spawns-that-needed-this-section.
     Requires session-level annotation of "which sections were
     touched semantically" — non-trivial.
  5. *Multi-doc residency* — extend the model from single
     CLAUDE.md to (CLAUDE.md + AGENTS.md + RTK.md + plugins).
     Inter-doc cross-references complicate the decision rule.
  6. *Application to non-coding agents* — does the model transfer
     to instruction prefixes for customer-support, retrieval,
     research agents?
- [ ] **§9 Conclusion.** Rewrite `sections/09-conclusion.tex`. One
  paragraph, ~250 words. Cover: restate the contribution (cost
  model + algorithm + measurement), the concrete result (21.5%
  reduction + fidelity Δ from TRIM-04), and the broader point
  (instruction documents in multi-agent systems are an
  unexplored cache-replacement problem). Close with a forward
  pointer to the companion routing-and-caching paper.
- [ ] Build: `make clean && make`. Resolve any new cites by
  adding to `bib/refs.bib`.
- [ ] Run `make wordcount` and confirm targets.
- [ ] Commit: `prose(trim): flesh §7 discussion, §8 future work,
  §9 conclusion`.

## Acceptance criteria
- Word counts within ±20% of targets.
- All `\cite{}` resolve.
- No `\tothink{}` left in §7, §8, §9.
- §7 limitations section honestly reports any TRIM-04 fidelity
  Δ that approaches or exceeds ε.

## Style guidance
- Don't hedge limitations into invisibility. "Limitations" is a
  trust-building section; concrete, named limitations beat vague
  hand-waving.
- Future-work entries should be one-paragraph proposals, not
  one-line bullets. Each names the research question and a
  plausible attack.
