---
title: 'Per-Turn Model Routing and Agentic Plan Caching for Cost-Optimal Multi-Agent LLM Coding Systems'

authors:
  - me

date: '2026-05-15T00:00:00Z'
publishDate: '2026-05-15T00:00:00Z'

publication_types: ['article']
publication: 'Working paper, skeleton'
publication_short: ''

abstract: |
  Static-prefix multi-agent LLM coding systems route work across a cheap-to-expensive model-tier hierarchy (haiku / sonnet / opus) to manage cost. Existing routing research targets the **subagent-dispatch** problem and produces clear (role × signal) rules; the analogous **main-thread orchestrator** problem has no role taxonomy and requires per-turn classification, but it dominates the cost shape. We measure Blackrim's production cost split as 99.4% main-thread / 0.6% subagent dispatch, indicating that the orchestrator itself is the binding cost lever in a well-tuned multi-agent system.

  We present two complementary primitives that target this lever: (i) a **semantic-similarity per-turn router** for the main thread, drawing on FrugalGPT cascading and RouteLLM-style preference-data routing; (ii) an **agentic plan-level semantic cache** stacking on top of existing prefix caching, drawing on the 2025 NeurIPS Agentic Plan Caching result. The router is grounded in exemplar curation across ~150 hand-labeled turns (50 per tier) with a k-NN classifier and conservative escalation to opus when similarity falls below threshold; the plan cache is keyed on a semantic signature of the orchestration plan and indexes strategy-level reuse across structurally-similar bd dispatches.

  We report a 4.56× read-to-creation ratio on the existing prefix cache (69.3% baseline savings) as the calibration point the new techniques stack atop. We document an integration blocker: Claude Code currently exposes only session-level model selection, not per-turn routing; we evaluate three workaround paths (Agent SDK middleware, Claude Code feature request, prompt injection). Closing the loop, we discuss why Blackrim's prior subagent-dispatch advisor (CC-TS) does not transfer directly to the main thread and what would.

summary: |
  The orchestrator dominates multi-agent LLM cost (99.4% main-thread vs 0.6% subagent dispatch). Two stacking primitives target this lever: a semantic-similarity per-turn router (FrugalGPT/RouteLLM lineage) and an agentic plan-level semantic cache atop existing prefix caching.

tags:
  - Multi-agent systems
  - LLM cost optimization
  - Per-turn routing
  - Semantic caching
  - Agentic plan cache
  - FrugalGPT
  - RouteLLM

featured: false

links:
  - type: source
    url: https://github.com/jsgerman-oss/research/tree/main/blackrim-routing-caching-paper

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

The paper describes the router and plan-cache as system components of [Blackrim](https://github.com/jsgerman-oss/blackrim.dev), specifically a planned `internal/router/` package for per-turn classification and a planned `internal/plancache/` package for plan-signature indexing.
