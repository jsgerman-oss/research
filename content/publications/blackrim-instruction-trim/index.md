---
title: 'Frequency-Weighted Progressive Disclosure for Static-Prefix Multi-Agent Coding Systems'

authors:
  - me

date: '2026-05-15T00:00:00Z'
publishDate: '2026-05-15T00:00:00Z'

publication_types: ['article']
publication: 'Working paper, skeleton'
publication_short: ''

abstract: |
  Multi-agent LLM coding systems load a static instruction document (`CLAUDE.md` or equivalent) into every agent spawn as a cached prefix. As the document grows, it dominates first-spawn cost and human maintenance burden, but aggressive compression of instruction text risks fidelity loss that is measurable in retrieval contexts but unmeasured in instruction-following contexts. We argue that the right primitive is not compression but **frequency-weighted progressive disclosure**: content needed every spawn stays in-prefix; content needed sometimes externalizes to on-demand Read calls; content needed rarely is dropped or moved to external archive.

  We formalise this as a cost minimisation problem under a per-section access frequency $f_i$ and prompt-cache hit-rate $\rho$, and apply it to Blackrim's 49 KB `CLAUDE.md` through a literature-aligned conservative trim. The trim removes 21.5% of lines (708 → 556) and 17.1% of characters (48,840 → 40,492) without compressing any instruction-bearing text — only redundancy removal and externalisation to existing or new documentation.

  We report the methodology, the measured deltas, and the integrated literature review we conducted to ground the conservative target. We also enumerate ten further optimisation directions (speculative decoding, KV-cache sharing, eval pre-generation, function-calling migration, code-specific embeddings) ranked by reward-per-effort and discuss which fit a static-prefix architecture and which do not.

summary: |
  Static instruction documents in multi-agent LLM systems are best optimised by frequency-weighted progressive disclosure, not compression. A literature-aligned trim of Blackrim's 49 KB CLAUDE.md removes 21.5% of lines with zero instruction-text compression.

tags:
  - Prompt caching
  - Context engineering
  - Progressive disclosure
  - Multi-agent systems
  - Static prefix
  - LLM cost optimization

featured: false

links:
  - type: source
    url: https://github.com/jsgerman-oss/research/tree/main/blackrim-instruction-trim-paper

image:
  caption: ''
  focal_point: ''
  preview_only: false

projects: []
slides: ''
---

## Status

Skeleton. Sections are structure-only; full prose drafting is sequenced after the model-advisor paper. The current PDF is a typeset draft of the scaffold with placeholder figures.

## Companion software

The paper describes the trim as applied to Blackrim's [`CLAUDE.md`](https://github.com/jsgerman-oss/blackrim.dev/blob/main/CLAUDE.md) and the planned `bd disclosure` telemetry path.
