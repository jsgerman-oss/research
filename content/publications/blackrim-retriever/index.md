---
title: 'Adaptive Conservative Selection for Hybrid Retrieval in Multi-Agent Memory Systems'

authors:
  - me

date: '2026-05-09T00:00:00Z'
publishDate: '2026-05-09T00:00:00Z'

publication_types: ['article']
publication: 'Working paper, skeleton'
publication_short: ''

abstract: |
  Multi-agent memory pools are heterogeneous — short bd-memory entries, mixed-shape queries, recency-sensitive — and the retriever sits on the hot path of every agent spawn. A wrong recall poisons every downstream prompt, and no single scorer or fusion configuration dominates across the six query classes Blackrim observes (technical-lookup, failure-recall, agent-scoped, continuity, concept-bridge, exact-id-or-slug).

  We frame fusion-config selection as a **conservative contextual bandit**: arms are fusion-config combinations (BM25 + SPLADE + dense + RRF + decay + MMR + optional cross-encoder reranker), context is the query class, reward is per-query NDCG@10, and the safety constraint is per-class no-regression below the BM25 (or BM25+decay) baseline. A SPLADE corpus-size threshold gates dense-retrieval activation; a Critical-tier reranker hook gates reranker activation. The contextual-bandit policy on top selects per-class fusion weights subject to the conservative-bandit constraint.

  Evaluation uses paper-stream telemetry, with held-out per-class NDCG@10 and recall@k against a labeled relevance set. Baselines: keyword, BM25, hybrid-RRF, hybrid-CC, and the proposed adaptive policy.

summary: |
  A per-query-class adaptive policy for combining BM25, SPLADE, dense retrieval, RRF fusion, recency decay, MMR, and an optional cross-encoder reranker. Conservative contextual bandit with a per-class baseline (BM25 / BM25+decay) safety constraint.

tags:
  - Hybrid retrieval
  - Contextual bandits
  - Conservative exploration
  - Agent memory
  - BM25
  - SPLADE
  - RRF

featured: false

links:
  - type: source
    url: https://github.com/jsgerman-oss/research/tree/main/blackrim-retriever-paper

image:
  caption: ''
  focal_point: ''
  preview_only: false

projects: []
slides: ''
---

## Status

Skeleton — sections are structure-only; full prose drafting is sequenced after the model-advisor paper. PDF will appear here once the paper compiles.

## Companion software

The paper describes the retriever as a system component of [Blackrim](https://github.com/jsgerman-oss/blackrim.dev), specifically the `internal/bdmemory/` package (BM25, SPLADE, dense, RRF, decay, MMR, reranker) and the paper-stream telemetry path in `internal/bdmemory/paper_stream.go`.
