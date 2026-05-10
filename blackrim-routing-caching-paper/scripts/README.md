# Scripts

Reproduce `data/aggregated/*.csv` from the Blackrim repo's telemetry. Pipeline:

```bash
# 1. Pull session telemetry (filtered by date)
python scripts/pull-telemetry.py --since 2026-05-01 \
  --repo /Users/jayse/Code/blackrim \
  > data/raw/session-telemetry.json

# 2. Aggregate cache statistics into the §7 calibration baseline
python scripts/aggregate-cache-stats.py \
  --telemetry /Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl \
  > data/aggregated/cache-stats.csv

# 3. (Future) routing-evidence aggregator — once the Phase-B router lands
# python scripts/aggregate-routing-evidence.py \
#   < data/raw/session-telemetry.json \
#   > data/aggregated/routing-evidence.csv

# 4. Build the PDF
make
```

## What each script does

- **`pull-telemetry.py`** — reads `.beads/telemetry/invocations.jsonl` against
  the Blackrim repo, filters by `--since`, and emits per-invocation JSON
  records with `agent`, `model`, `session`, `input_tokens`,
  `output_tokens`, `cache_creation_input_tokens`,
  `cache_read_input_tokens`, `duration_ms`, `source`.

- **`aggregate-cache-stats.py`** — folds per-invocation cache fields into a
  single-row CSV with `cache_creation_total_tokens`,
  `cache_read_total_tokens`, `read_to_creation_ratio`,
  `cache_enabled_spawn_rate`, `sample_count`, `cache_enabled_count`. Backs §7's
  calibration baseline ("4.56× read-to-creation ratio").

## Why no LLM calls

Deterministic by design. All numbers reduce to telemetry-file inspection;
anyone with the Blackrim repo can reproduce them without API keys.
