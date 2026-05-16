# eval-plan-cache — Plan-Cache Replay Harness

Implements the plan-cache evaluation pipeline described in §7 of the
routing-caching paper.  Two scripts — `index.py` and `replay.py` — cover
the full offline replay loop.  No live API calls are required.

## Quick start (CI / --dry-run)

```bash
# 1. Build the plan-cache index from the bundled fixture:
python scripts/eval-plan-cache/index.py \
    --dispatches tests/fixtures/sample-dispatches.jsonl \
    --out scripts/eval-plan-cache/plan-index.jsonl \
    --dry-run

# 2. Run leave-one-out replay:
python scripts/eval-plan-cache/replay.py \
    --index scripts/eval-plan-cache/plan-index.jsonl \
    --out data/aggregated/plancache-eval.csv \
    --summary data/aggregated/plancache-summary.csv \
    --dry-run

# 3. Optionally run the sanity check (doubled index → hit rate ~ 100%):
python scripts/eval-plan-cache/replay.py \
    --index scripts/eval-plan-cache/plan-index.jsonl \
    --dry-run --sanity-check
```

## Full pipeline (with embeddings)

Requires `sentence-transformers` (see `scripts/eval-routing/requirements.txt`):

```bash
pip install sentence-transformers

# Build index with all-MiniLM-L6-v2 query embeddings:
python scripts/eval-plan-cache/index.py \
    --dispatches tests/fixtures/sample-dispatches.jsonl \
    --out scripts/eval-plan-cache/plan-index.jsonl

# Replay with cosine-similarity retrieval:
python scripts/eval-plan-cache/replay.py \
    --index scripts/eval-plan-cache/plan-index.jsonl \
    --out data/aggregated/plancache-eval.csv \
    --summary data/aggregated/plancache-summary.csv
```

To use real Blackrim telemetry instead of the fixture, pass
`--dispatches /path/to/dispatches.jsonl` to `index.py`.  The dispatches file
must be JSONL with the schema described below.

## What is a plan signature?

A **plan signature** is an ordered, coarse-grained string encoding the
sequence of tool calls an agent emits to handle a request.  Each element is:

```
<ToolName>:<coarse-target>
```

Elements are joined with `|`.  Example:

```
Read:internal/|Bash:go|Edit:internal/|Bash:go
```

### Coarsening rules

| Tool   | Raw target                       | Coarsened form       |
|--------|----------------------------------|----------------------|
| Read   | `internal/cache/manager.go`      | `internal/`          |
| Edit   | `internal/cache/manager.go`      | `internal/`          |
| Write  | `docs/research/foo.md`           | `docs/`              |
| Bash   | `go test ./internal/cache/...`   | `go`                 |
| Bash   | `python scripts/run.py --flag`   | `python`             |
| Read   | `Makefile`                       | `makefile`           |

Only the top-level directory component is kept for file paths; only the
command verb is kept for Bash calls.  This is intentionally coarse:

- **Too fine** (full paths): every request looks unique → near-zero hit rate.
- **Too coarse** (tool name only): unrelated plans share signatures → high
  false-hit rate.

The chosen level targets ≥30% hit rate at <5% false-hit rate (§7 acceptance
bar).  Adjust granularity by modifying `_coarsen_target()` in `index.py`.

### Why this matters for the hit/false-hit trade-off

Agentic plan caching (NeurIPS 2025) shows that reusing plans across
semantically similar requests yields significant cost savings beyond prefix
caching.  The risk is **false hits**: returning a cached plan that looks
structurally correct but is semantically wrong for the new request.

Our coarsening design optimises for the operating point where:
- Plans for the same *type* of work (e.g. "fix a bug in `internal/`") share
  signatures and legitimately reuse each other's cached plans.
- Plans for structurally different work (e.g. a 3-step read-only research
  vs a 5-step write-heavy build) differ in signature and do not collide.

## Script reference

### `index.py`

Reads a JSONL dispatches file, extracts the plan signature for each record,
optionally embeds the user query with `all-MiniLM-L6-v2`, and writes a JSONL
index.

**Input schema** (one record per line):

```jsonc
{
  "dispatch_id": "d001",          // unique identifier
  "ts": "2026-05-09T05:03:26Z",  // ISO timestamp
  "user_query": "fix the race condition in the supervisor loop",
  "agent": "Builder",
  "task_type": "build",          // build | read | prose | test | operate | …
  "tool_calls": [                // ordered list of tool invocations
    {"tool": "Read",  "target": "internal/supervisor/loop.go"},
    {"tool": "Edit",  "target": "internal/supervisor/loop.go"},
    {"tool": "Bash",  "target": "go test -race ./internal/supervisor/..."}
  ],
  "response_summary": "Added mutex guard around task-notification dequeue"
}
```

**Output schema** (plan-index.jsonl):

```jsonc
{
  "dispatch_id": "d001",
  "ts": "...",
  "user_query": "...",
  "agent": "Builder",
  "task_type": "build",
  "plan_signature": "Read:internal/|Edit:internal/|Bash:go",
  "signature_hash": "a3f1b2c4d5e6f7a8",  // 16-char hex
  "response_summary": "Added mutex guard around …",
  "query_embedding": [0.12, -0.34, ...]   // 384-dim; empty list in --dry-run
}
```

**Flags:**

| Flag              | Default                                    | Description                            |
|-------------------|--------------------------------------------|----------------------------------------|
| `--dispatches`    | `tests/fixtures/sample-dispatches.jsonl`   | Input JSONL dispatches file            |
| `--out`           | `scripts/eval-plan-cache/plan-index.jsonl` | Output index path                      |
| `--dry-run`       | off                                        | Skip embedding model; CI-safe          |

### `replay.py`

Runs LOO cross-validation over the index and emits per-dispatch and summary
CSVs.

**Per-dispatch CSV columns:**

| Column           | Description                                                    |
|------------------|----------------------------------------------------------------|
| `dispatch_id`    | Identifier of the held-out dispatch                           |
| `gold_signature` | The actual plan signature for this dispatch                   |
| `top1_signature` | Signature of the top-1 retrieved neighbour                    |
| `similarity`     | Cosine similarity (or 0/1 in dry-run mode)                    |
| `decision`       | `hit` or `miss`                                               |
| `correct`        | `True` if hit and not a false hit                             |
| `false_hit`      | `True` if signatures match but task types differ              |
| `gold_task_type` | Task type of the held-out dispatch                            |
| `top1_task_type` | Task type of the retrieved neighbour                          |

**Summary CSV columns:**

| Column                                 | Description                                                |
|----------------------------------------|------------------------------------------------------------|
| `hit_rate`                             | Fraction of dispatches where top-1 signature matches gold |
| `false_hit_rate`                       | Fraction where signature matched but task type differs    |
| `true_hit_rate`                        | `hit_rate - false_hit_rate`                               |
| `composed_cost_reduction_vs_prefix_only` | Estimated total savings; see formula below              |

**Composed cost reduction formula:**

```
composed = prefix_savings + true_hit_rate * (1 - prefix_savings)
```

where `prefix_savings = 0.786` is the §7 calibration baseline.  This models
plan-cache savings as applying to the remaining 21.4% of cost that prefix
caching does not cover.

**Flags:**

| Flag              | Default                                        | Description                            |
|-------------------|------------------------------------------------|----------------------------------------|
| `--index`         | `scripts/eval-plan-cache/plan-index.jsonl`    | Index file to replay against           |
| `--out`           | `data/aggregated/plancache-eval.csv`           | Per-dispatch output CSV                |
| `--summary`       | `data/aggregated/plancache-summary.csv`        | Summary output CSV                     |
| `--dry-run`       | off                                            | Exact-hash matching; CI-safe           |
| `--sanity-check`  | off                                            | Run doubled-index validation after LOO |

## Adding new similarity functions

The retrieval function is `retrieve_top1()` in `replay.py`.  To add a new
similarity function:

1. Add a branch in `retrieve_top1()` controlled by a new `--similarity` flag
   (e.g. `bm25`, `jaccard`, `hybrid`).
2. The function must accept two records and return a float in [0, 1].
3. The rest of the LOO loop is similarity-function-agnostic.

## Data sources

| Source                                                          | Records | Notes                                  |
|-----------------------------------------------------------------|---------|----------------------------------------|
| `tests/fixtures/sample-dispatches.jsonl`                        | 40      | Hand-crafted fixture; CI default       |
| `/Users/jayse/Code/blackrim/.beads/telemetry/plan-events.jsonl` | 6       | Real telemetry; only 3 unique queries  |
| `/Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl` | 780+    | Real spawns; lacks plan/query fields   |

The fixture covers the acceptance bar of ≥30 dispatches.  RC-06 will collect
additional real dispatch data and rerun the harness to produce the final §7
numbers.

## Acceptance criteria (RC-05)

- [x] `scripts/eval-plan-cache/index.py` exists
- [x] `scripts/eval-plan-cache/replay.py` exists
- [x] `tests/fixtures/sample-dispatches.jsonl` has 40 dispatch records
- [x] `--dry-run` mode runs end-to-end without external data or API calls
- [x] `data/aggregated/plancache-eval.csv` produced by `replay.py`
- [x] `data/aggregated/plancache-summary.csv` produced by `replay.py`
- [ ] RC-06: update §7 with final hit_rate / false_hit_rate numbers
