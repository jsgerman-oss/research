# Phase 05: Experiment Pipelines — Pull Telemetry, Aggregate, Validate

Both papers have `scripts/pull-telemetry.py` and aggregator scripts. This phase runs the full reproducibility pipeline end-to-end so every quantitative claim in either paper traces back to a CSV in `data/aggregated/`. Output is populated `data/raw/` and `data/aggregated/` directories plus a validation report comparing measured numbers against the claims currently asserted in each paper's README and section files.

## Tasks

- [ ] Inventory and read existing scripts before running anything. For each paper read every file under `scripts/` and document:
  - What each script ingests (file paths, CLI args, env vars)
  - What it emits (output path, schema)
  - External dependencies (Python packages, paths into `/Users/jayse/Code/blackrim`, beads telemetry)
  - Save to `Auto Run Docs/Initiation/Working/Phase-05-Script-Inventory.md`
  - If a script imports a package that is not installed, install via pip into a venv at `_shared/.venv/` and record what was installed; reuse this venv across both papers

- [ ] Run the routing-caching telemetry pipeline:
  - `cd blackrim-routing-caching-paper`
  - `python scripts/pull-telemetry.py --since 2026-05-01 --repo /Users/jayse/Code/blackrim > data/raw/session-telemetry.json` — if `--repo` path is unreadable, fall back to whatever paths the script defaults to and record the deviation
  - `python scripts/aggregate-cache-stats.py --telemetry /Users/jayse/Code/blackrim/.beads/telemetry/invocations.jsonl > data/aggregated/cache-stats.csv` — same fallback policy
  - If a `scripts/aggregate-routing-evidence.py` exists run it; if not, scaffold it from the existing aggregator's structure and add a stub that emits the columns referenced in `sections/07-evaluation.tex`
  - Capture any errors and either fix or document the blocker

- [ ] Run the instruction-trim telemetry pipeline:
  - `cd blackrim-instruction-trim-paper`
  - `python scripts/pull-telemetry.py --since 2026-05-09 > data/raw/session-telemetry.json`
  - `python scripts/aggregate-trim-results.py < data/raw/session-telemetry.json > data/aggregated/trim-results.csv`
  - Capture errors, fix if internal, document if external

- [ ] Validate every aggregated CSV. For each CSV created:
  - Check it is non-empty and parseable (`python -c "import pandas as pd; print(pd.read_csv('PATH').shape)"`)
  - Compute summary statistics for each numeric column (min / max / mean / median / N)
  - Save the summary to `Auto Run Docs/Initiation/Working/Phase-05-CSV-Validation.md`
  - Flag any CSV where the row count is suspiciously small (<10) — that is likely a sign the telemetry source path was wrong

- [ ] Cross-check measured numbers against paper claims. Build a claim/measurement reconciliation table at `Auto Run Docs/Initiation/Working/Phase-05-Claims-vs-Data.md`. For each paper grep the section files for percentage claims (`\d+(?:\.\d+)?%`) and ratio claims, and for each:
  - Paper claim verbatim (with file + line)
  - Measured value from aggregated CSV
  - Source CSV + column
  - Status: `confirmed` (within 2pp) / `revised-needed` (drift) / `unsourced` (no CSV backs it)
  - Pay particular attention to the README's headline numbers: 99.4/0.6 main-thread split, 4.56× cache read-to-creation, 17.1% (or 21.5%) line reduction, 35–50% routing savings

- [ ] For any "unsourced" or "revised-needed" claim, decide a remediation path and record it in the same file. Options:
  - Update the .tex section to match the measured number (preferred when measured is sound)
  - Add a missing aggregator/script that produces the needed CSV (if telemetry exists but isn't extracted)
  - Mark the claim as "future work" with a `\todo{}` and leave it — only acceptable for tangential numbers, not headline claims

- [ ] Commit a `Phase-05-DataReady.md` status at `Auto Run Docs/Initiation/Working/` listing every CSV now present in each paper's `data/aggregated/`, the script that produced it, and the section/figure it backs. This is the input contract for Phases 06–07 (figures + evaluation drafting).
