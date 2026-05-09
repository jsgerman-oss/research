# Eval harness

These scripts back §6 (Empirical Evaluation) of `main.tex`. The pipeline is
deterministic given fixed RNG seeds and a snapshot of the production
telemetry.

## Pipeline

```bash
# 1. Pull and anonymise production telemetry (since 30 days back)
python scripts/pull-telemetry.py --since=30d > data/raw/telemetry.jsonl

# 2. Aggregate raw stream into per-cell rollup
python scripts/aggregate-by-shape.py < data/raw/telemetry.jsonl \
    > data/aggregated/by-shape.csv

# 3. Run each advisor against the trace; cost + quality projections.
for adv in opus-default static-frontmatter epsilon-greedy conservative-ts; do
    python scripts/run-eval-suite.py --advisor=$adv
done
# → data/aggregated/<advisor>-results.csv

# 4. (TODO scripts/build-figures.py) — render data/figures/*.csv into
#    pgfplots-readable tables so figures/*.tex can pick them up.
```

## Inputs

- `~/Code/blackrim/.beads/telemetry/invocations.jsonl` — production stream,
  anonymised by `pull-telemetry.py`.
- `data/raw/moa1b-prior.csv` (TODO) — per-cell confidence percentages from
  the MOA-1b deep landscape doc; provides the Bayesian prior pseudocounts
  via `beta_utils.prior_pseudocounts`.
- `data/raw/eval-fixtures.jsonl` (TODO) — held-out task fixtures with
  ground-truth quality; produced by MOA-11 (continuous eval) once landed.

## Outputs

- `data/raw/telemetry.jsonl` — anonymised production stream.
- `data/aggregated/by-shape.csv` — per-(agent, shape, model) cost+quality.
- `data/aggregated/<advisor>-results.csv` — per-dispatch tier choice + cost.
- `data/figures/*.csv` — pgfplots-readable tables (one per figure).

## Reproducibility

Each script accepts `--seed` (default `20260509`) and a `--telemetry` path
override. The published version of the paper anchors to a tagged commit of
the upstream Blackrim repo and the corresponding telemetry snapshot in
`data/raw/`.

## Extending: adding a new advisor

Add a `_select_<name>` function in `run-eval-suite.py`, register it in the
`--advisor` choices list, and run the pipeline. Decision rules belong here;
posterior tracking goes in `posteriors`. Keep advisors pure with respect to
the per-call signals they receive — every advisor in this file is a
mathematical function from `(signals, posteriors, prior, rng)` to a tier.
