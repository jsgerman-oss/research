# Scripts

## How to refresh data

Run `make data` from the paper root to pull live telemetry from the
Blackrim repo and regenerate `data/aggregated/trim-results.csv`:

```bash
make data
# or, pointing at a different Blackrim checkout:
make data BLACKRIM_REPO=/path/to/blackrim
```

This runs the two-step pipeline below and is idempotent.

### Manual pipeline

```bash
# 1. Pull session telemetry from the Blackrim repo (CLAUDE.md commits only)
python scripts/pull-telemetry.py \
  --repo /Users/jayse/Code/blackrim \
  > data/raw/session-telemetry.json

# 2. Aggregate into a CSV the paper can pgfplots-render
python scripts/aggregate-trim-results.py \
  < data/raw/session-telemetry.json \
  > data/aggregated/trim-results.csv

# 3. Build the PDF
make
```

The default `--since` in `pull-telemetry.py` is `2026-05-09T03:17:00-07:00`,
chosen so the pre-Wave-1 baseline commit (64149950, the supervisor pattern
commit that brought CLAUDE.md to 708 lines) is always the first record.
A bare date like `2026-05-09` would resolve to midnight UTC and exclude
early-morning PDT commits.

## What each script does

- **`pull-telemetry.py`** — reads `git log` + `git show` against the Blackrim
  repo, captures CLAUDE.md size at each session commit, and emits JSON-lines
  with `sha`, `author_iso`, `subject`, `author`, `claude_md.lines`,
  `claude_md.chars`, and `files_changed`.

- **`aggregate-trim-results.py`** — folds the per-commit JSON records into a
  single CSV with absolute sizes plus deltas (`delta_lines_vs_baseline`,
  `delta_pct_lines`, `delta_chars_vs_baseline`, `delta_pct_chars`). The
  baseline is the first commit in the input.

## Why no LLM calls

This pipeline is deterministic by design. The paper's quantitative claims
all reduce to git-log inspection, so anyone with the Blackrim repo can
reproduce the numbers without API keys.
