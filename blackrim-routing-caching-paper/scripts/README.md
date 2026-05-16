# Scripts

Reproduce `data/aggregated/*.csv` from the Blackrim repo's telemetry. Pipeline:

```bash
# 1. Pull session telemetry (filtered by date)
python scripts/pull-telemetry.py --since 2026-05-01 \
  --repo /Users/jayse/Code/blackrim \
  > data/raw/session-telemetry.json

# 2. Aggregate cost split into the §7 Table 1 cost-split baseline
python scripts/aggregate-cost-split.py \
  --telemetry /Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl \
  --pricing /Users/jayse/Code/blackrim/internal/pricing/sheets/anthropic-public.toml \
  --session-evidence data/raw/session-evidence.json \
  > data/aggregated/cost-split.csv

# 3. Aggregate cache statistics into the §7 calibration baseline
python scripts/aggregate-cache-stats.py \
  --telemetry /Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl \
  > data/aggregated/cache-stats.csv

# 4. (Future) routing-evidence aggregator — once the Phase-B router lands
# python scripts/aggregate-routing-evidence.py \
#   < data/raw/session-telemetry.json \
#   > data/aggregated/routing-evidence.csv

# 5. Plan-cache evaluation (RC-05) — no API calls required
python scripts/eval-plan-cache/index.py \
  --dispatches tests/fixtures/sample-dispatches.jsonl \
  --out scripts/eval-plan-cache/plan-index.jsonl \
  --dry-run
python scripts/eval-plan-cache/replay.py \
  --index scripts/eval-plan-cache/plan-index.jsonl \
  --out data/aggregated/plancache-eval.csv \
  --summary data/aggregated/plancache-summary.csv \
  --dry-run

# 6. Build the PDF
make
```

## What each script does

- **`pull-telemetry.py`** — reads `.beads/telemetry/invocations.jsonl` against
  the Blackrim repo, filters by `--since`, and emits per-invocation JSON
  records with `agent`, `model`, `session`, `input_tokens`,
  `output_tokens`, `cache_creation_input_tokens`,
  `cache_read_input_tokens`, `duration_ms`, `source`.

- **`aggregate-cost-split.py`** — partitions invocations by `source` field
  into `main_thread` / `subagent_dispatch` / `unclassified` buckets and
  emits `data/aggregated/cost-split.csv` with columns
  `bucket, cost_usd, n_calls, cost_share_pct`. Backs §7 Table 1
  ("99.4% main-thread cost"). Uses a hybrid approach: cost figures are
  taken from `data/raw/session-evidence.json` (dashboard ground truth);
  JSONL real-API records (`subagent_stop`, `dispatch`) are used for
  call-count cross-checking only. Exits 1 if unclassified records exceed
  5% of total (RC-02 acceptance criterion). See the
  [Cost-split pipeline](#cost-split-pipeline) section for details.

- **`aggregate-cache-stats.py`** — folds per-invocation cache fields into a
  single-row CSV with `cache_creation_total_tokens`,
  `cache_read_total_tokens`, `read_to_creation_ratio`,
  `cache_enabled_spawn_rate`, `sample_count`, `cache_enabled_count`. Backs §7's
  calibration baseline ("4.56× read-to-creation ratio").

## Cache-stats pipeline

`aggregate-cache-stats.py` computes the three headline metrics for §7's
"Cache calibration baseline":

| Metric | CSV key | §7 value |
|--------|---------|----------|
| Read-to-creation ratio | `read_to_creation_ratio` | 10.44× |
| Cache hit rate (real spawns) | `cache_enabled_real_spawn_rate` | 90.1% |
| Savings vs no-caching | `savings_vs_no_caching` | 78.6% |

**Two spawn rates are reported:**

- `cache_enabled_spawn_rate` — fraction of ALL 744 sampled spawns that
  carried any cache tokens. Low (~9.8%) because 663 records are
  `dispatch_estimated` or `subagent_stop_estimated` stubs with zero token
  counts.
- `cache_enabled_real_spawn_rate` — fraction of 81 real-API records
  (source in `{subagent_stop, gt-cache-warm, dispatch}`) that carried cache
  tokens. This is the operationally meaningful hit rate (~90.1%) cited in §7.

**Savings derivation** (from `docs/research/cache-control-deep-dive.md`):

```
cost_with_cache    = inp * price + cc * price * 1.25 + cr * price * 0.10
cost_without_cache = (inp + cc + cr) * price
savings            = 1 - cost_with_cache / cost_without_cache
```

Weighted-average price for `model=unknown` records: $2.40/MTok
(40% haiku at $1, 50% sonnet at $3, 10% opus at $5).

**Known limitation:** The telemetry JSONL at
`.beads/telemetry/invocations.jsonl` begins 2026-05-09; the paper's
stated window (§7 Setup) is 2026-05-01 through 2026-05-09. The 8-day
pre-JSONL window used in `docs/research/cache-control-deep-dive.md` (29
spawns, 4.56× ratio, 79.3% hit rate, 69.3% savings) cannot be reproduced
from the current JSONL. The CSV reflects the JSONL-available window
(2026-05-09 through present); §7 numbers have been updated accordingly.

## Cost-split pipeline

`aggregate-cost-split.py` computes the three headline metrics for §7
Table 1 ("\blackrim cost split"):

| Metric | CSV key | §7 value |
|--------|---------|----------|
| Session total | `session_total` | $115.54 |
| Main-thread share | `main_thread` cost\_share\_pct | 99.4% |
| Subagent dispatch share | `subagent_dispatch` cost\_share\_pct | 0.6% |

**Source classification** (by `source` field in each JSONL record):

| source value | Classification | Notes |
|---|---|---|
| `main-thread` | main\_thread | Not observed in current JSONL |
| `subagent_stop` | subagent\_dispatch (real API) | Real completed spawn |
| `dispatch` | subagent\_dispatch (real API) | Real dispatch event |
| `gt-cache-warm` | subagent\_dispatch (real API) | Cache-warming call |
| `dispatch_estimated` | subagent\_dispatch (estimated) | Synthetic token stub |
| `subagent_stop_estimated` | subagent\_dispatch (estimated) | Synthetic token stub |
| anything else | unclassified | Logged to stderr; must be <5% |

**Hybrid cost model.** The `invocations.jsonl` does not log main-thread
Gestalt conversation turns. The dashboard `/api/tokens/comprehensive`
captures both main-thread and subagent costs in a single session view.
Because of this architectural gap, the script uses:

- **Cost figures** from `data/raw/session-evidence.json` record 1
  (kind=session-evidence), which holds the verified dashboard snapshot.
- **Call counts** from JSONL real-API records (`subagent_stop` + `dispatch`)
  as a cross-check against the dashboard-reported 55 dispatch calls.

**Known limitation: JSONL-only mode does not reproduce 99.4/0.6.**
Running without `--session-evidence` shows ~$55 in the `subagent_dispatch`
bucket and $0 in `main_thread`, because the JSONL exclusively logs Agent
tool spawn events. The dashboard is the authoritative cost split source;
the JSONL is the authoritative call-count and dispatch-composition source.

**Call count delta.** The JSONL currently shows 98 real-API dispatch records
vs the 55 called out in the dashboard snapshot. This is expected: the JSONL
spans 2026-05-09 through 2026-05-16 (the full file), while the dashboard
snapshot was taken at 2026-05-09T22:04 PT (one day into the window).
The script warns when the delta exceeds 10 records.

## Plan-cache pipeline (RC-05)

`scripts/eval-plan-cache/` implements the plan-cache replay harness that §7
"Plan-cache evaluation" references.  Full documentation: `scripts/eval-plan-cache/README.md`.

**index.py** reads a JSONL dispatches file, extracts a coarse plan signature
(ordered sequence of `Tool:coarse-target` pairs) for each record, and optionally
embeds the user query with `all-MiniLM-L6-v2`.  Outputs `plan-index.jsonl`.

**replay.py** runs leave-one-out cross-validation: for each dispatch i, it
builds a temporary index from all other dispatches, retrieves the top-1
neighbour by cosine similarity (or exact signature-hash in `--dry-run` mode),
and records hit/miss/false-hit.  Emits `plancache-eval.csv` (per-dispatch)
and `plancache-summary.csv` (hit_rate, false_hit_rate, composed_cost_reduction).

| Output CSV | Key metrics |
|---|---|
| `data/aggregated/plancache-eval.csv` | per-dispatch: decision, similarity, false_hit |
| `data/aggregated/plancache-summary.csv` | hit_rate, false_hit_rate, composed_cost_reduction |

Target acceptance bar (§7): hit_rate ≥ 30%, false_hit_rate < 5%.
RC-06 will rerun on real dispatch data and update §7 with final numbers.

## Why no LLM calls

Deterministic by design. All numbers reduce to telemetry-file inspection;
anyone with the Blackrim repo can reproduce them without API keys.
