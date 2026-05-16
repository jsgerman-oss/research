# Eval harness

These scripts back §6 (Empirical Evaluation) of `main.tex`. The pipeline is
deterministic given fixed RNG seeds and a snapshot of the production
telemetry.

## Pipeline

### Step 0 — copy raw JSONL into the repo (gitignored, one-time per machine)

Raw files are gitignored (see `.gitignore: data/raw/*.jsonl`). Copy from
production before running the pipeline:

```bash
mkdir -p data/raw
cp /path/to/blackrim/.beads/telemetry/invocations.jsonl data/raw/advisor-decisions.jsonl
cp /path/to/blackrim/.beads/telemetry/eval-triggered-observations.jsonl data/raw/
```

Current snapshot (2026-05-15):
- `advisor-decisions.jsonl` — 295 records, 2026-05-09 to 2026-05-15,
  3 active cells: Architect/A1 (1), Builder/Bu1 (293), Researcher/Re1 (1).
- `eval-triggered-observations.jsonl` — 360 stub records (`source=stub`);
  replace with real MOA-11 output once `eval-fixtures.jsonl` is available.

### Step 1 — regenerate `data/aggregated/by-shape.csv`

`aggregate-by-shape.py` reads normalized JSONL from stdin (the format
emitted by `pull-telemetry.py`). `advisor-decisions.jsonl` uses a different
schema (no `input_tokens`/`output_tokens`/`outcome` per dispatch), so choose
the appropriate path:

```bash
# Option A — full pipeline from live production telemetry:
python scripts/pull-telemetry.py --since=30d > data/raw/telemetry.jsonl
python scripts/aggregate-by-shape.py < data/raw/telemetry.jsonl \
    > data/aggregated/by-shape.csv

# Option B — from advisor-decisions.jsonl snapshot (v1 default):
# Convert advisor-decisions to normalized format first (maps recommended_tier
# to model name, uses per-tier average token profiles from _est_cost()).
# The v1 CSV was produced by an inline converter; a reusable script is tracked
# at TODO: scripts/convert-advisor-to-telemetry.py.
python scripts/aggregate-by-shape.py < data/raw/telemetry.jsonl \
    > data/aggregated/by-shape.csv
```

The committed `data/aggregated/by-shape.csv` was produced from the v1
advisor-decisions snapshot via Option B. Posterior validation (§5 formula):
`beta_credible_interval(n_success, n_failure)` correctly implements
Beta(1+s, 1+f) with flat prior — verified against all 3 rows in the CSV.

### Step 2 — run eval advisors

```bash
# Requires data/raw/telemetry.jsonl (Option A above).
for adv in opus-default static-frontmatter epsilon-greedy conservative-ts; do
    python scripts/run-eval-suite.py --advisor=$adv
done
# → data/aggregated/<advisor>-results.csv
```

Quality preservation pass rates (§6 Table 1) require `data/raw/eval-fixtures.jsonl`
(MOA-11 continuous eval, not yet landed). Without it, `run-eval-suite.py`
produces cost estimates only; quality columns will be empty.

### Step 3 — build figures (TODO)

```bash
# (TODO scripts/build-figures.py) — render data/figures/*.csv into
# pgfplots-readable tables so figures/*.tex can pick them up.
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
