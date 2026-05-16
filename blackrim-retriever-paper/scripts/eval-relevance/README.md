# eval-relevance — pool → judge → relevance.jsonl pipeline

Builds the held-out relevance judgements (`data/raw/relevance.jsonl`) that
`run-eval-suite.py` needs to compute NDCG@10 per policy.

## Pipeline overview

```
data/raw/queries.jsonl
        │
        ▼
    pool.py                     → data/aggregated/relevance-pool.jsonl
        │
        ▼
    label.py  (LLM judge)       → data/raw/relevance.jsonl
        │
        ▼
    run-eval-suite.py           → data/aggregated/<policy>-results.csv
```

## Step 1 — Build the candidate pool

```bash
cd /path/to/research   # repo root
python blackrim-retriever-paper/scripts/eval-relevance/pool.py \
    --queries blackrim-retriever-paper/data/raw/queries.jsonl \
    --out     blackrim-retriever-paper/data/aggregated/relevance-pool.jsonl \
    --top-k   10
```

`pool.py` reads every record in `queries.jsonl`, takes the top-k results from
each scorer present in the record, and unions them into a deduplicated set of
`(query_hash, doc_id)` candidate pairs. The output is committed to the repo
(aggregated data is tracked); the raw `queries.jsonl` is gitignored.

**Schema note — actual data vs. brief expectation:**
The production `queries.jsonl` contains two scorers (`keyword` and
`depgraph`), not the four originally anticipated (`bm25`, `splade`, `dense`,
`keyword`). The `scorers` dict has shape:

```json
{
  "keyword": {
    "method": "keyword",
    "top_k": 5,
    "scores": [1, 1, 1, 1, 1],
    "latency_ms": 0
  }
}
```

`scores[i]` aligns positionally with `final_ranks[i].doc_id`. Records with no
`scores` (e.g. `depgraph` records with `top_k=0`) are excluded from pooling.
Pool output schema (one row per candidate pair):

| Field        | Type          | Description                                      |
|--------------|---------------|--------------------------------------------------|
| `query_hash` | string        | Anonymised query identifier                      |
| `query_class`| string        | `lookup`, `depgraph`, `unknown`                  |
| `doc_id`     | string        | Candidate document identifier                    |
| `found_by`   | list[string]  | Scorers that returned this doc                   |
| `scores`     | dict          | Best score per scorer: `{scorer: float}`         |
| `min_rank`   | int           | Best (lowest) rank this doc received             |

## Step 2 — Label with LLM judge

### Dry-run (no API key required — for pipeline testing)

```bash
python blackrim-retriever-paper/scripts/eval-relevance/label.py --dry-run
```

Emits `relevance.jsonl` with canned label `1` (marginal) for every pair.
All downstream scripts (`run-eval-suite.py`, `aggregate-by-class.py`) can be
exercised against this stub before real labeling runs.

### Production run

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python blackrim-retriever-paper/scripts/eval-relevance/label.py \
    --pool     blackrim-retriever-paper/data/aggregated/relevance-pool.jsonl \
    --out      blackrim-retriever-paper/data/raw/relevance.jsonl \
    --model    claude-haiku-4-5-20251001 \
    --cost-budget-usd 5.0 \
    --rate-limit-rps  2.0
```

`label.py` is **resumable**: pairs already present in `--out` are skipped.
Interrupt and restart freely.

**Cost gate:** before the first API call, `label.py` prints an estimated
cost and aborts if it exceeds `--cost-budget-usd`. The estimate uses
~550 input tokens and ~80 output tokens per call at published haiku pricing.

## Labeling rubric

TREC-style graded relevance (0/1/2):

| Label | Meaning            | When to assign                                                |
|-------|--------------------|---------------------------------------------------------------|
| 0     | Not relevant       | Document does not address the query                           |
| 1     | Partially relevant | Touches the topic but is incomplete or tangential             |
| 2     | Relevant           | Directly addresses the query; a user would find it useful     |

The full rubric and 3 in-prompt examples are in `judge_prompt.py`.

## Human spot-check procedure

After a production labeling run, sample 5% of LLM labels for human review:

```bash
python - <<'EOF'
import json, random, pathlib
rows = [json.loads(l) for l in
        pathlib.Path("blackrim-retriever-paper/data/raw/relevance.jsonl").open()]
sample = random.sample(rows, max(1, len(rows) // 20))
for r in sample:
    print(json.dumps(r))
EOF
```

Review each sampled `(query_hash, doc_id, label)` triple against the rubric.
A label disagreement rate above 15% on the sample suggests the judge prompt
needs tuning — file a bd issue before using labels for NDCG computation.

## Cost expectations

| Scenario       | Pairs | Estimated cost (haiku) |
|----------------|-------|------------------------|
| Current data   | ~31   | < $0.01                |
| 978 queries    | ~978  | ~$0.50                 |
| 10k queries    | ~10k  | ~$5.00                 |

Current data has 14 unique query hashes × ~2.2 docs/query ≈ 31 pairs.
Costs scale linearly. Raise `--cost-budget-usd` as needed.

## Files

| File               | Role                                          |
|--------------------|-----------------------------------------------|
| `pool.py`          | Build candidate pool from queries.jsonl       |
| `judge_prompt.py`  | Prompt builder + label parser                 |
| `label.py`         | CLI: call LLM judge, write relevance.jsonl    |
| `README.md`        | This file                                     |
