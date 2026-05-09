# Eval harness

These scripts back §6 (Empirical Evaluation) of `main.tex`. The pipeline is
deterministic given fixed RNG seeds and a snapshot of the production
paper-stream telemetry.

## Pipeline

```bash
# 1. Pull and project paper-stream queries (since 30 days back)
python scripts/pull-telemetry.py --since=30d \
    --src ~/research/blackrim-retriever-paper/data/raw/queries.jsonl \
    --out data/raw/queries.filtered.jsonl

# 2. Aggregate raw stream into per-(class, arm) rollup
python scripts/aggregate-by-class.py < data/raw/queries.filtered.jsonl \
    > data/aggregated/by-class.csv

# 3. Run each policy against the trace; per-class NDCG@10 projections.
for pol in keyword bm25 bm25-decay hybrid-rrf hybrid-cc conservative-cb; do
    python scripts/run-eval-suite.py --policy=$pol
done
# → data/aggregated/<policy>-results.csv

# 4. (TODO scripts/build-figures.py) — render data/figures/*.csv into
#    pgfplots-readable tables so figures/*.tex can pick them up.
```

## Inputs

- `~/research/blackrim-retriever-paper/data/raw/queries.jsonl` — production
  paper-stream from `internal/bdmemory/paper_stream.go` (bd:
  blackrim-41nn). Per-query records of query hash, query length, inferred
  query class, per-scorer top-k scores and latency, final fused ranks,
  total latency.
- `data/raw/relevance.jsonl` (TODO) — held-out per-query relevance
  judgements; produced by the labeling pipeline (see §6.1 of the paper).

## Outputs

- `data/raw/queries.filtered.jsonl` — time-windowed paper-stream.
- `data/aggregated/by-class.csv` — per-(query-class, arm) cost+quality.
- `data/aggregated/<policy>-results.csv` — per-query arm choice + NDCG@10.
- `data/figures/*.csv` — pgfplots-readable tables (one per figure).

## Reproducibility

Each script accepts `--seed` (default `20260509`) and explicit input
paths. The published version of the paper anchors to a tagged commit of
the Blackrim repo and the corresponding paper-stream snapshot in
`data/raw/`.

## Extending: adding a new policy

Add a `_select_<name>` branch in `run-eval-suite.py`, register it in the
`--policy` choices list, and run the pipeline. Decision rules belong here;
posterior tracking goes in `posteriors`. Keep policies pure with respect
to the per-call signals they receive — every policy in this file is a
mathematical function from `(signals, posteriors, rng)` to an arm.
