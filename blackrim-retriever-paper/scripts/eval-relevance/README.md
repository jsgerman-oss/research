# eval-relevance — pool → judge → relevance.jsonl pipeline

Builds the held-out relevance judgements (`data/raw/relevance.jsonl`) that
`run-eval-suite.py` needs to compute NDCG@10 per policy.

## The 30/978 split — two distinct corpora

The pipeline works with two query corpora that serve different purposes.

**30 gold evaluation queries** (`/Users/jayse/Code/blackrim/evals/embedding-retrieval/queries.jsonl`)

Hand-curated by the Blackrim project team.  Each query has a `type` annotation
mapping to one of the paper's 6 query classes, and a `judgment` field (currently
`UNMARKED` — manual annotation is a future step).  These 30 queries are the
**authoritative evaluation corpus** for all NDCG@10 figures reported in the paper.

**978 operational telemetry records** (`data/raw/queries.jsonl`)

Real production traffic captured by the `bdmemory.AppendRecallEvent` sidecar
(Go: `internal/bdmemory/paper_stream.go`).  Raw query text is **never stored** —
only a SHA-256[:16] hash, query length, and query class tag.  These records are
used for **operational characterisation only**: latency distributions, class
frequencies, scorer coverage.  They are not used for NDCG evaluation because
there is no way to recover plaintext from the hash.

| Corpus          | Count  | Plaintext? | Purpose                        |
|-----------------|--------|------------|--------------------------------|
| Gold eval set   | 30     | Yes        | NDCG@10 evaluation (paper §4)  |
| Telemetry log   | 978    | No (hashed)| Operational characterisation   |

## Pipeline overview

```
Gold eval set (30 queries)       Operational pool (978 records)
        │                                    │
        ▼                                    ▼
    hydrate.py (gold-set mode)      hydrate.py (--production-mode)
        │                                    │
        ▼                                    ▼
  relevance-pool-hydrated.jsonl    relevance-pool-hydrated.jsonl
  (query_text + doc_text filled)   (query_text = stub, doc_text filled)
        │                                    │
        ▼                                    ▼
    label.py (LLM judge)           label.py (LLM judge, lower quality)
        │                                    │
        ▼                                    ▼
    relevance.jsonl               (operational labels — not for NDCG)
        │
        ▼
    run-eval-suite.py   → data/aggregated/<policy>-results.csv
```

The raw pool builder (`pool.py`) is only used for the operational corpus:

```
data/raw/queries.jsonl (978 records, hashed)
        │
        ▼
    pool.py                → data/aggregated/relevance-pool.jsonl
```

## Step 0 — Hydrate with plaintext (required before labeling)

`hydrate.py` resolves query text and doc snippets so the LLM judge has
meaningful content to assess.

### Gold-set mode (default — recommended for evaluation)

```bash
cd /path/to/research   # repo root
python blackrim-retriever-paper/scripts/eval-relevance/hydrate.py
```

Reads the 30 gold queries, fetches all bd memory docs via `bd recall`, and
writes a cross-product pool (30 queries × N docs) to
`data/aggregated/relevance-pool-hydrated.jsonl`.  With ~42 current memories
this produces ~1 260 candidate pairs.

### Production mode (operational traffic, lower-quality labels)

```bash
python blackrim-retriever-paper/scripts/eval-relevance/hydrate.py \
    --production-mode \
    --pool blackrim-retriever-paper/data/aggregated/relevance-pool.jsonl
```

Joins the 978-record operational pool with doc snippets via `bd recall`.
Query text is not recoverable (hash-only), so `query_text` is set to a stub.
LLM labels from this mode are lower quality and are **not** used for NDCG
computation.

### Doc-snippet source

`hydrate.py` fetches doc content via `bd recall <slug>` in the Blackrim
project root (`/Users/jayse/Code/blackrim`).  The `doc_id` field in every
pool row is a bd memory slug.

**Remaining blocker:** Blackrim does not yet expose a direct
`(doc_id → snippet)` lookup API (e.g. `bd memory get --json <slug>`).
The current `bd recall` shell-out is the only available surface.  When
Blackrim ships a programmatic memory-lookup endpoint, replace the
`_fetch_doc_snippet()` function in `hydrate.py` — the call site is isolated
and clearly marked with a `TODO` comment.

## Step 1 — Build the candidate pool (operational path only)

```bash
cd /path/to/research   # repo root
python blackrim-retriever-paper/scripts/eval-relevance/pool.py \
    --queries blackrim-retriever-paper/data/raw/queries.jsonl \
    --out     blackrim-retriever-paper/data/aggregated/relevance-pool.jsonl \
    --top-k   10
```

`pool.py` is only needed for the operational telemetry corpus.  Skip this step
if you are using gold-set mode exclusively.

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
# Uses hydrated pool by default (creates relevance.jsonl with canned label=1)
python blackrim-retriever-paper/scripts/eval-relevance/label.py --dry-run
```

With the hydrated pool, the dry-run output now shows real query text in the
`query_text` field of each output row — confirming the pipeline is wired end
to end before any API cost is incurred.

### Production run (gold-set evaluation)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python blackrim-retriever-paper/scripts/eval-relevance/label.py \
    --pool     blackrim-retriever-paper/data/aggregated/relevance-pool-hydrated.jsonl \
    --out      blackrim-retriever-paper/data/raw/relevance.jsonl \
    --model    claude-haiku-4-5-20251001 \
    --cost-budget-usd 5.0 \
    --rate-limit-rps  2.0
```

Pass `--gold-set-mode` to skip LLM judging for pairs that already carry a
human judgment in the gold set.  Currently a no-op (all gold judgments are
`UNMARKED`) but is ready for future manual annotation rounds.

`label.py` is **resumable**: pairs already present in `--out` are skipped.
Interrupt and restart freely.

**Cost gate:** before the first API call, `label.py` prints an estimated
cost and aborts if it exceeds `--cost-budget-usd`.

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

Review each sampled `(query_text, doc_id, label)` triple against the rubric.
A label disagreement rate above 15% on the sample suggests the judge prompt
needs tuning — file a bd issue before using labels for NDCG computation.

## Cost expectations

| Scenario                     | Pairs   | Estimated cost (haiku) |
|------------------------------|---------|------------------------|
| Gold-set × 42 memories       | ~1 260  | ~$0.001                |
| Gold-set × 200 memories      | ~6 000  | ~$0.003                |
| Production pool (current)    | ~31     | < $0.001               |

Costs scale linearly with pair count. Raise `--cost-budget-usd` as needed.

## Files

| File                            | Role                                          |
|---------------------------------|-----------------------------------------------|
| `hydrate.py`                    | Resolve query text + doc snippets             |
| `pool.py`                       | Build operational candidate pool              |
| `judge_prompt.py`               | Prompt builder + label parser                 |
| `label.py`                      | CLI: call LLM judge, write relevance.jsonl    |
| `README.md`                     | This file                                     |
