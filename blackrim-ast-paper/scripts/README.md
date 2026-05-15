# scripts/ — empirical-pipeline harness

These scripts produce the CSVs in `data/aggregated/` that back the
figures and tables in §6 (Empirical Evaluation). Each script reads
from a Blackrim checkout (path via `--blackrim-root` or the
`$BLACKRIM_ROOT` environment variable, default `$HOME/Code/blackrim`)
and emits CSV on stdout.

The intent is *reproducibility-first*: anyone with a Blackrim checkout
at the paper's tagged commit can regenerate every empirical claim in §6.

## Pipeline

```
pull-compression-ratios.py   →  data/raw/compression-ratios.jsonl
aggregate-by-language.py     →  data/aggregated/by-language.csv      (§6.2)
measure-outline-latency.py   →  data/aggregated/outline-latency.csv  (§6.4)
pull-outline-telemetry.py    →  data/aggregated/outline-events.csv   (§6.5)
refactor-eval.py             →  data/aggregated/gate-verdicts.csv    (§6.6)
e2e-paired-traces.py         →  data/aggregated/e2e-deltas.csv       (§6.7)
```

Status (matches `\tothink{}` placeholders in §6):

| Script | Status | Backs |
|---|---|---|
| `pull-compression-ratios.py`   | Implemented (reads in-tree bench results) | §6.2 — measured |
| `aggregate-by-language.py`     | Implemented | §6.2 — measured |
| `measure-outline-latency.py`   | Stub | §6.4 — pending OQ-AST-2 |
| `pull-outline-telemetry.py`    | Stub | §6.5 — pending OQ-AST-3 |
| `refactor-eval.py`             | Stub | §6.6 — pending OQ-AST-4 |
| `e2e-paired-traces.py`         | Stub | §6.7 — pending OQ-AST-5 |

The stubs are intentional: they emit the CSV header and an explanatory
comment, so the LaTeX `\input{data/...}` chain does not break the build
while the datasets are still accumulating. Replace them with real
implementations as the corresponding open questions resolve.

## Corpus

`corpus.txt` pins the broader polyglot corpus used by the
budget-conformance, latency, and end-to-end scripts. One repository
per line, in the form `org/repo@ref` (e.g., `golang/go@release-branch.go1.22`).
The harness clones each into `data/scratch/corpora/` and prunes to
the pinned commit.

## Running

```bash
# Smoke-test the implemented scripts
make data       # from paper root; runs the four "ready" scripts

# Run a single script with explicit Blackrim root
python scripts/pull-compression-ratios.py \
    --blackrim-root=$HOME/Code/blackrim \
    > data/raw/compression-ratios.jsonl

python scripts/aggregate-by-language.py \
    < data/raw/compression-ratios.jsonl \
    > data/aggregated/by-language.csv
```

## Requirements

- Python 3.11+
- A Blackrim checkout with the in-tree `gt` binary built (`go build ./cmd/gt`).
- Network access for the first run of the JS/TS backends (npm install).
