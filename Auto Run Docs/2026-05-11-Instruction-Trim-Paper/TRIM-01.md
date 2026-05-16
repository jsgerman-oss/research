# TRIM-01 — Telemetry pull + aggregation (instruction-trim paper)

## Goal
Replace the illustrative raw telemetry in
`/Users/jayse/research/blackrim-instruction-trim-paper/data/raw/session-telemetry.json`
with **real** records pulled from the live Blackrim repo, then regenerate
`data/aggregated/trim-results.csv` and reconcile against the hardcoded
numbers in §6 (Evaluation).

## Context — read before touching anything
- Paper dir: `/Users/jayse/research/blackrim-instruction-trim-paper/`
- Blackrim repo (the system under measurement): `/Users/jayse/Code/blackrim`
- Pull script: `scripts/pull-telemetry.py` — emits JSON-lines per commit, with
  `claude_md` size (`lines`, `chars`).
- Aggregate script: `scripts/aggregate-trim-results.py` — reads JSON-lines on
  stdin, writes CSV on stdout. Uses the FIRST record as the size baseline,
  so order matters (`pull-telemetry.py` already emits oldest-first).
- The current `data/raw/session-telemetry.json` has fake/illustrative SHAs
  (e.g. `eb8c3d0b3e98f4d99a6c5d8a9b1e2f4c5d6a7b8c` — too long; real git SHAs
  are 40 hex chars but the first 7 should match a real commit). Verify by
  attempting `git -C /Users/jayse/Code/blackrim show eb8c3d0b3e98f4d99a6c5d8a9b1e2f4c5d6a7b8c` first.
- §6 has hardcoded numbers in the size-trajectory table: 708→618→556 lines,
  48,840→45,185→40,492 chars. After refresh, these must either still match
  the CSV or be updated to match.

## Tasks
- [ ] Verify the Blackrim repo path and commit history are usable for the
  pull. Run, from the paper directory: `test -d /Users/jayse/Code/blackrim
  && git -C /Users/jayse/Code/blackrim log --since=2026-05-09 --oneline -- CLAUDE.md
  | head -30`. There MUST be at least one baseline commit (pre-Wave-1) and at
  least one Wave-2-close commit ("Wave 2" or "worktree-isolation" in subject).
  If neither exists, STOP and report — do not fabricate data.
- [ ] Snapshot the existing illustrative data: `cp data/raw/session-telemetry.json
  data/raw/session-telemetry.illustrative.json` (this stays untracked; it lets
  you diff against the real pull). Then run
  `python scripts/pull-telemetry.py --since 2026-05-09
   --repo /Users/jayse/Code/blackrim > data/raw/session-telemetry.json`.
  Verify ≥6 records: `wc -l data/raw/session-telemetry.json`.
- [ ] Run `python scripts/aggregate-trim-results.py
  < data/raw/session-telemetry.json > data/aggregated/trim-results.csv`.
  Verify: header row + ≥6 data rows; the LAST row's `claude_md_lines` should
  be ≤ the FIRST row's (since Wave 2 trims lines). If `data/aggregated/`
  does not exist, `mkdir` it first.
- [ ] Cross-check the CSV against §6 Table 1 (`sections/06-evaluation.tex`,
  the "size trajectory" table). For each of {Baseline / Wave 1 / Wave 2}:
  if the CSV row's lines+chars match the table, leave §6 unchanged. If they
  drift, edit the table values **and** the cost-model worked example
  (Eq.\,\cost_flat, \cost_wave2 in §6 use the same numbers; both must update
  together). Document any drift in the commit message body.
- [ ] Update §6's reproducibility subsection (`\label{sec:repro}`) to remove
  the inline command comments and replace with a single line pointing at
  `scripts/README.md`, **provided** `scripts/README.md` already documents
  the pipeline (read it first; it should).
- [ ] Run `make data` from the paper dir and confirm it regenerates
  `data/aggregated/trim-results.csv` byte-for-byte (no diff). If `make data`
  isn't wired in the Makefile, add the target — it should run the pull then
  the aggregate.
- [ ] `git add data/raw/session-telemetry.json data/aggregated/trim-results.csv
  sections/06-evaluation.tex Makefile && git commit -m "data(trim): refresh
  raw + aggregated telemetry from blackrim main (2026-05-09 → now)"`. If §6
  was untouched, just commit the data files.

## Acceptance criteria
- `data/raw/session-telemetry.json` has ≥6 records with real 40-hex-char
  SHAs traceable in `/Users/jayse/Code/blackrim`.
- `data/aggregated/trim-results.csv` exists, header + ≥6 rows, last row
  has `delta_pct_lines` and `delta_pct_chars` matching (or replacing) §6.
- `make data` is idempotent.
- One commit on the paper branch.

## Out of scope
- Per-section attribution (TRIM-02 handles that).
- Fidelity eval (TRIM-03/04).
- Figures (TRIM-05). The CSV from this phase is the input for fig1 in TRIM-05.
