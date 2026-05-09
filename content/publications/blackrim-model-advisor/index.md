---
title: 'Conservative Adaptive Model-Tier Selection for Multi-Agent LLM Workflows under Asymmetric Cost-Quality Loss'

authors:
  - me

date: '2026-05-09T00:00:00Z'
publishDate: '2026-05-09T00:00:00Z'

# CSL publication type — preprint until arXiv lands
publication_types: ['article']
publication: 'Working paper, draft'
publication_short: ''

abstract: |
  Multi-agent workflows built on large language models (LLMs) increasingly route work across heterogeneous model tiers — a small fast model for lookups, a mid-sized model for routine implementation, a frontier model for judgment calls. Selecting the cheapest model that preserves task quality is the central cost-control problem in production agent systems, but it sits in a regime that existing online-learning theory addresses awkwardly: rewards are quality-vs-cost trade-offs that are asymmetric (a single poor decision in a critical-path task can erase weeks of cost savings), per-cell sample sizes are small, and a meaningful Bayesian prior is available from offline evaluation but is itself imperfect.

  We formalise the problem as a constrained Bayesian decision problem: choose the cost-minimal tier whose posterior probability of preserving quality exceeds a per-task tolerance $\tau$. We instantiate this with **Conservative Constrained Thompson Sampling** (CC-TS): hierarchical Beta priors seeded from an empirical landscape of 17 × 5 × 3 agent–shape–tier cells; per-cell Beta-Bernoulli posteriors updated from production telemetry; conformal-prediction wrappers that bound quality drop at a chosen confidence level; uncertainty-triggered eval to resolve underdetermined cells. The conservative property — never downgrade unless the posterior credibly exceeds tolerance — is preserved through a one-sided hypothesis-testing rule with explicit asymmetric loss.

summary: |
  A constrained Bayesian decision framework for routing LLM calls across model tiers under asymmetric cost–quality loss. Hierarchical Beta priors, conformal-bounded quality, conservative one-sided downgrades.

tags:
  - Multi-agent systems
  - LLM cost optimization
  - Thompson sampling
  - Conformal prediction
  - Bayesian decision theory

featured: true

# Custom links — populated as the work progresses.
links:
  - type: pdf
    url: blackrim-model-advisor.pdf
  - type: source
    url: https://github.com/jsgerman-oss/research/tree/main/blackrim-model-advisor-paper
  - type: code
    url: https://github.com/jsgerman-oss/blackrim.dev

image:
  caption: ''
  focal_point: ''
  preview_only: false

projects: []
slides: ''
---

## Status

Working draft. Not yet peer-reviewed. Targeting an arXiv preprint as the first submission; workshop venues under consideration.

## Reproducibility

Every quantitative claim in §6 (Empirical Evaluation) of the paper is backed by a CSV under `data/` produced by a script under `scripts/`. To reproduce from scratch:

```bash
python scripts/pull-telemetry.py --since=30d > data/raw/telemetry.jsonl
python scripts/aggregate-by-shape.py < data/raw/telemetry.jsonl > data/aggregated/by-shape.csv
python scripts/run-eval-suite.py --advisor=conservative-ts > data/aggregated/eval-results.csv
make             # latex picks up new data/*.csv automatically via pgfplots
```

## Companion software

The paper describes the advisor as a system component of [Blackrim](https://github.com/jsgerman-oss/blackrim.dev), specifically `internal/dispatch/model.go` and the planned MOA-9 (Bayesian scoring) layer.
