---
title: 'Three-Axis Judge Reliability for Multi-Agent Eval Suites: Calibration, Agreement, and Bias Bounds for LLM-as-Judge Scoring'

authors:
  - me

date: '2026-05-09T00:00:00Z'
publishDate: '2026-05-09T00:00:00Z'

publication_types: ['article']
publication: 'Working paper, skeleton'
publication_short: ''

abstract: |
  A multi-agent eval-suite mixes heterogeneous scorer kinds (heuristic, embedding, LLM classifier, LLM rubric, trajectory) over heterogeneous task shapes (single-file edits, Q&A lookups, ADR judgments, threat models, long-form docs, debug triage, code review, rubric writing). The dominant single-axis framing in the eval literature ("judge agreement with humans" or "calibration error") collapses three distinct reliability axes that fail in different cells of the (scorer-class × task-shape) grid for different reasons.

  We propose a **three-axis** methodology for eval-suite scoring: (i) calibration-no-regression for scorers with a meaningful confidence-vs-correctness baseline (LLM classifier, pairwise rubric); (ii) agreement-no-regression for scorers with no calibration baseline but a stable inter-rater signal (LLM rubric, trajectory rubric on subjective shapes); (iii) a bias-bound precondition on all LLM-judge cells (position-bias flip-rate ≤ 5%, verbosity-bias correlation |ρ| ≤ 0.20, self-preference advantage ≤ 0.05).

  v1 ships four surgical upgrades anchored to the algorithm survey: probability-weighted scoring (G-Eval), a position-bias swap test, ECE + reliability diagnostics with temperature scaling, and stratified sampling for production-trace suites. The headline implementation finding: probability-weighted scoring is a ~30-LoC change that recovers a 22% Spearman correlation gain already paid for in the judge's log-probs.

  The headline empirical claim, drawn from the calibration literature and reproduced on Blackrim's judge fleet, is that RLHF-tuned LLM judges are systematically worse-calibrated than their pretrained ancestors of the same scale. The implication: the dominant deployed configuration (forced-tool-use LLM-as-judge on an instruction-tuned model) is precisely the configuration that needs explicit calibration correction before its confidence numbers can be used to gate anything.

summary: |
  Three reliability axes for LLM-as-judge eval suites: calibration, agreement, and bias bounds. Probability-weighted scoring, position-bias swap tests, ECE diagnostics with temperature scaling, stratified sampling. Headline finding: RLHF-tuned judges are systematically worse-calibrated than their pretrained ancestors.

tags:
  - LLM-as-judge
  - Calibration
  - Expected calibration error
  - Inter-rater agreement
  - Bias bounds
  - Agent eval
  - G-Eval
  - Bradley-Terry pairwise judging
  - RLHF calibration

featured: false

links:
  - type: pdf
    url: blackrim-eval-suite.pdf
  - type: source
    url: https://github.com/jsgerman-oss/research/tree/main/blackrim-eval-suite-paper

image:
  caption: ''
  focal_point: ''
  preview_only: false

projects: []
slides: ''
---

## Status

Skeleton. Sections are structure-only; full prose drafting is sequenced after the model-advisor paper. PDF will appear here once the paper compiles.
