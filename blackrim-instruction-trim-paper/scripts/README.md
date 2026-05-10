# Scripts

Reproduce `data/aggregated/*.csv` from `data/raw/*.json`. The full pipeline:

```bash
# 1. Pull session telemetry from the Blackrim repo
python scripts/pull-telemetry.py --since 2026-05-09 \
  --repo /Users/jayse/Code/blackrim \
  > data/raw/session-telemetry.json

# 2. Aggregate into a CSV the paper can pgfplots-render
python scripts/aggregate-trim-results.py \
  < data/raw/session-telemetry.json \
  > data/aggregated/trim-results.csv

# 3. Build the PDF
make
```

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
